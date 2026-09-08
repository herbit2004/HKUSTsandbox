#!/usr/bin/env python3
"""Independently validate a staged building-neighborhood source manifest.

The checker re-extracts each GLB from its staged b3dm, validates the original
ZIP CRC/SHA and baseline matrix, recomputes transformed geometry statistics and
rebuilds each high/fine mask from actual triangle pixel-centre projection.
Only ``independent-validation.json`` is written, inside the supplied stage.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import zlib

import numpy as np
from PIL import Image

from hkust_source_geometry import geometry


PROJECT = Path(__file__).resolve().parents[1]
LIVE_MANIFEST = PROJECT / "public/models/hires/manifest.json"
RENDER_MANIFEST = PROJECT / "public/models/render-manifest.json"
STEP = 0.5
HIGH_ERROR = 1.75


def read_json(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha_path(path):
    return digest(path.read_bytes())


def uri_of(node):
    content = node.get("content", {})
    return content.get("uri", content.get("url"))


def source_id(sheet, sub, uri):
    return f"{sheet}/{sub}/{Path(uri).stem}"


def find_owner(root, source_ancestor):
    wanted = Path(source_ancestor).stem
    matches = []

    def visit(node):
        uri = uri_of(node)
        if uri and Path(uri).stem == wanted:
            matches.append(node)
        for child in node.get("children", []):
            visit(child)

    visit(root)
    if len(matches) != 1:
        raise AssertionError(f"source owner {source_ancestor!r} found {len(matches)} times")
    return matches[0]


def frontier(node, threshold):
    children = node.get("children", [])
    uri = uri_of(node)
    if threshold == 0:
        if children:
            return [item for child in children for item in frontier(child, threshold)]
        if not uri or node.get("geometricError", 0) != 0:
            raise AssertionError("fine frontier contains a non-terminal/error source node")
        return [node]
    if uri and (node.get("geometricError", 0) <= threshold or not children):
        return [node]
    if not children:
        raise AssertionError("high frontier has no content")
    return [item for child in children for item in frontier(child, threshold)]


def extract_glb(data, path):
    if len(data) < 28:
        raise AssertionError(f"b3dm too short: {path}")
    magic, version, byte_length, ft_json, ft_bin, bt_json, bt_bin = struct.unpack_from("<4s6I", data)
    if magic != b"b3dm" or version not in (0, 1):
        raise AssertionError(f"b3dm header mismatch: {path}")
    if byte_length != len(data):
        raise AssertionError(f"b3dm byteLength mismatch: {path}")
    glb = data[28 + ft_json + ft_bin + bt_json + bt_bin:]
    if len(glb) < 20 or glb[:4] != b"glTF":
        raise AssertionError(f"embedded GLB magic mismatch: {path}")
    if struct.unpack_from("<I", glb, 8)[0] != len(glb):
        raise AssertionError(f"embedded GLB byteLength mismatch: {path}")
    return glb


def mip_bytes(width, height):
    total = 0
    while True:
        total += width * height * 4
        if width == height == 1:
            return total
        width, height = max(1, width // 2), max(1, height // 2)


def glb_textures(glb, path):
    json_length, json_type = struct.unpack_from("<I4s", glb, 12)
    if json_type != b"JSON" or 20 + json_length > len(glb):
        raise AssertionError(f"GLB JSON chunk mismatch: {path}")
    document = json.loads(glb[20:20 + json_length].decode("utf-8").rstrip(" \t\r\n\x00"))
    binary = glb[20 + json_length:]
    if binary:
        binary_length, binary_type = struct.unpack_from("<I4s", binary, 0)
        if binary_type != b"BIN\x00" or 8 + binary_length > len(binary):
            raise AssertionError(f"GLB BIN chunk mismatch: {path}")
        binary = binary[8:8 + binary_length]
    textures = []
    for index, image in enumerate(document.get("images", [])):
        if "bufferView" not in image:
            raise AssertionError(f"image {index} is not embedded: {path}")
        view = document["bufferViews"][image["bufferView"]]
        begin = view.get("byteOffset", 0)
        encoded = binary[begin:begin + view["byteLength"]]
        if len(encoded) != view["byteLength"]:
            raise AssertionError(f"image bufferView truncated: {path}")
        with Image.open(io.BytesIO(encoded)) as picture:
            width, height = picture.size
            picture.load()
        textures.append({"index": index, "width": width, "height": height, "encodedBytes": len(encoded), "mipBytes": mip_bytes(width, height), "sha256": digest(encoded)})
    primitives = [primitive for mesh in document.get("meshes", []) for primitive in mesh.get("primitives", [])]
    if not primitives or any("POSITION" not in p.get("attributes", {}) for p in primitives):
        raise AssertionError(f"GLB has no POSITION primitive: {path}")
    if any("TEXCOORD_0" not in p.get("attributes", {}) for p in primitives):
        raise AssertionError(f"GLB UV missing: {path}")
    return document, textures


def close(a, b, tolerance=1e-6):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), rtol=0, atol=tolerance)


def exact_mask(triangles):
    if len(triangles) == 0 or not np.isfinite(triangles).all():
        raise AssertionError("empty/non-finite triangle set")
    lo, hi = triangles.min(axis=(0, 1)), triangles.max(axis=(0, 1))
    x0, z0 = np.floor(lo[[0, 2]] / STEP) * STEP
    x1, z1 = np.ceil(hi[[0, 2]] / STEP) * STEP
    width, height = int(round((x1 - x0) / STEP)), int(round((z1 - z0) / STEP))
    if width <= 0 or height <= 0:
        raise AssertionError("empty mask bounds")
    mask = np.zeros((height, width), np.uint8)
    for triangle in triangles:
        projected = triangle[:, [0, 2]]
        a, b, c = projected
        denominator = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(denominator) < 1e-12:
            continue
        lower = np.ceil((projected.min(axis=0) - [x0, z0]) / STEP - 0.5 - 1e-9).astype(int)
        upper = np.floor((projected.max(axis=0) - [x0, z0]) / STEP - 0.5 + 1e-9).astype(int)
        c0, r0 = max(0, lower[0]), max(0, lower[1])
        c1, r1 = min(width - 1, upper[0]), min(height - 1, upper[1])
        if c0 > c1 or r0 > r1:
            continue
        xx, zz = np.meshgrid(x0 + (np.arange(c0, c1 + 1) + 0.5) * STEP,
                             z0 + (np.arange(r0, r1 + 1) + 0.5) * STEP)
        dx, dz = xx - a[0], zz - a[1]
        u = (dx * (c[1] - a[1]) - dz * (c[0] - a[0])) / denominator
        v = ((b[0] - a[0]) * dz - (b[1] - a[1]) * dx) / denominator
        mask[r0:r1 + 1, c0:c1 + 1][(u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)] = 255
    return mask, {"minX": float(x0), "minZ": float(z0), "maxX": float(x1), "maxZ": float(z1), "width": width, "height": height}


def resolve_stage_path(stage, value, fallback=None):
    if value:
        path = Path(value)
        if path.exists():
            return path
        if not path.is_absolute() and (stage / path).exists():
            return stage / path
    if fallback and (stage / fallback).exists():
        return stage / fallback
    raise FileNotFoundError(value or fallback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=Path("/tmp/hkust-targeted-terminal-u68"))
    args = parser.parse_args()
    stage = args.stage.resolve()
    manifest_path = stage / "manifest.json"
    manifest = read_json(manifest_path)
    preparation_path = stage / "source-preparation.json"
    preparation = read_json(preparation_path)
    live = read_json(LIVE_MANIFEST)
    render = read_json(RENDER_MANIFEST)
    live_owner_ids = {patch.get("sourceAncestor") for patch in live.get("patches", []) if patch.get("sourceAncestor")}
    live_tile_ids = {tile.get("id") for patch in live.get("patches", []) for level in patch.get("levels", {}).values() for tile in level.get("tiles", []) if tile.get("id")}
    baseline_by_id = {tile["id"]: tile for tile in render["tiles"]}
    mismatches = []
    rows = []
    patches = manifest.get("patches", [])
    prepared_owners = preparation.get("owners")
    prepared_owner_ids = None
    if isinstance(prepared_owners, int):
        expected_owner_count = prepared_owners
    elif isinstance(prepared_owners, list):
        expected_owner_count = len(prepared_owners)
        prepared_owner_ids = {
            item.get("id", item.get("ownerId", item)) if isinstance(item, dict) else item
            for item in prepared_owners
        }
    else:
        expected_owner_count = None
        mismatches.append({"scope": "source-preparation", "field": "owners", "error": "expected integer or list"})
    if expected_owner_count is not None and len(patches) != expected_owner_count:
        mismatches.append({"scope": "manifest", "field": "ownerCount", "expected": expected_owner_count, "actual": len(patches)})
    if prepared_owner_ids is not None:
        staged_ancestor_ids = {patch.get("sourceAncestor") for patch in patches}
        if prepared_owner_ids != staged_ancestor_ids:
            mismatches.append({"scope": "source-preparation", "field": "ownerIds", "expected": sorted(prepared_owner_ids), "actual": sorted(staged_ancestor_ids)})
    patch_ids = [patch.get("id") for patch in patches]
    if len(patch_ids) != len(set(patch_ids)):
        mismatches.append({"scope": "manifest", "field": "uniquePatchIds", "actual": patch_ids})
    ancestors = [patch.get("sourceAncestor") for patch in patches]
    if len(ancestors) != len(set(ancestors)):
        mismatches.append({"scope": "manifest", "field": "uniqueSourceAncestors", "actual": ancestors})
    if set(ancestors) & live_owner_ids:
        mismatches.append({"scope": "manifest", "field": "sourceAncestorLiveDuplicate", "ids": sorted(set(ancestors) & live_owner_ids)})
    tile_owners = {}
    for patch in patches:
        for level_name, level in patch.get("levels", {}).items():
            for tile in level.get("tiles", []):
                tile_owners.setdefault(tile.get("id"), set()).add(patch.get("id"))
                if tile.get("id") in live_tile_ids:
                    mismatches.append({"scope": patch.get("id"), "field": "liveTileDuplicate", "tile": tile.get("id")})
    for tile_id, owners in tile_owners.items():
        if len(owners) > 1:
            mismatches.append({"scope": "manifest", "field": "tileCrossOwner", "tile": tile_id, "owners": sorted(owners)})

    tree_cache = {}
    with tempfile.TemporaryDirectory(prefix="hkust-targeted-validation-") as temp_dir:
        temp_dir = Path(temp_dir)
        for patch in patches:
            patch_id = patch.get("id")
            owner_row = {"id": patch_id, "sourceAncestor": patch.get("sourceAncestor"), "levels": {}, "mismatches": []}
            try:
                if not patch.get("sourceAncestor") or patch["sourceAncestor"] in live_owner_ids:
                    raise AssertionError("sourceAncestor is missing or already published")
                tree_path = PROJECT / patch["sourceOriginalTree"]
                if sha_path(tree_path) != patch.get("sourceOriginalTreeSha256"):
                    raise AssertionError("source tree SHA mismatch")
                tree = tree_cache.setdefault(tree_path, read_json(tree_path))
                owner_node = find_owner(tree["root"], patch["sourceAncestor"])
                owner_name = Path(patch["sourceAncestor"]).stem
                sheet, sub = patch["sourceAncestor"].split("/")[:2]
                expected = {}
                for level_name, threshold in (("high", HIGH_ERROR), ("fine", 0)):
                    expected[level_name] = {source_id(sheet, sub, uri_of(node)) for node in frontier(owner_node, threshold)}
                if set(patch.get("levels", {})) != {"high", "fine"}:
                    raise AssertionError("levels must contain exactly high and fine")
                for level_name in ("high", "fine"):
                    level = patch["levels"][level_name]
                    level_mismatches = []
                    tiles = level.get("tiles", [])
                    if level.get("completeSelectedSubtree") is not True:
                        level_mismatches.append("completeSelectedSubtree is not true")
                    actual_ids = [tile.get("id") for tile in tiles]
                    if set(actual_ids) != expected[level_name] - live_tile_ids:
                        level_mismatches.append({"frontierIds": {"expected": sorted(expected[level_name] - live_tile_ids), "actual": sorted(actual_ids)}})
                    if len(actual_ids) != len(set(actual_ids)):
                        level_mismatches.append("duplicate tile within level")
                    all_triangles = []
                    tile_rows = []
                    for tile in tiles:
                        tile_id = tile.get("id")
                        tile_mismatch = []
                        try:
                            source_b3dm = resolve_stage_path(stage, tile.get("sourceB3dmPath"), Path("source-b3dm") / sheet / sub / (Path(tile_id).name + ".b3dm"))
                            data = source_b3dm.read_bytes()
                            entry = tile["sourceZipEntry"]
                            if len(data) != int(entry["size"]):
                                tile_mismatch.append("b3dm size")
                            if (zlib.crc32(data) & 0xffffffff) != int(entry["crc32"]):
                                tile_mismatch.append("b3dm CRC32")
                            if digest(data) != tile.get("sourceB3dmSha256"):
                                tile_mismatch.append("b3dm SHA256")
                            glb = extract_glb(data, source_b3dm)
                            glb_path = temp_dir / (digest(glb) + ".glb")
                            glb_path.write_bytes(glb)
                            staged_glb = resolve_stage_path(stage, tile.get("localPath"), tile.get("url"))
                            if staged_glb.read_bytes() != glb:
                                tile_mismatch.append("staged GLB bytes")
                            if digest(glb) != tile.get("sha256"):
                                tile_mismatch.append("GLB SHA256")
                            document, textures = glb_textures(glb, glb_path)
                            baseline = baseline_by_id.get(tile.get("matrixSourceBaselineId"))
                            if baseline is None or not close(tile.get("matrix"), baseline.get("matrix"), 1e-12):
                                tile_mismatch.append("matrix")
                            if not np.isfinite(np.asarray(tile.get("matrix"), dtype=float)).all():
                                tile_mismatch.append("non-finite matrix")
                            transformed, _ = geometry(glb_path, np.asarray(tile["matrix"], dtype=float).reshape(4, 4, order="F"))
                            if not np.isfinite(transformed).all():
                                tile_mismatch.append("non-finite transformed geometry")
                            all_triangles.append(transformed)
                            actual_bounds = {"min": transformed.min(axis=(0, 1)).tolist(), "max": transformed.max(axis=(0, 1)).tolist()}
                            if not close(actual_bounds["min"], tile["bounds"]["min"]) or not close(actual_bounds["max"], tile["bounds"]["max"]):
                                tile_mismatch.append("bounds")
                            if len(transformed) != int(tile.get("triangles", -1)):
                                tile_mismatch.append("triangle count")
                            expected_texture_mip = sum(item["mipBytes"] for item in textures)
                            expected_texture_bytes = sum(item["width"] * item["height"] * 4 for item in textures)
                            expected_encoded = sum(item["encodedBytes"] for item in textures)
                            if expected_texture_mip != tile.get("textureMipBytes") or expected_texture_bytes != tile.get("textureBytes") or expected_encoded != tile.get("textureEncodedBytes"):
                                tile_mismatch.append("texture byte accounting")
                            if tile.get("textureDimensions") != [[item["width"], item["height"]] for item in textures]:
                                tile_mismatch.append("texture dimensions")
                            if level_name == "high" and float(tile.get("originalError", 999)) > HIGH_ERROR:
                                tile_mismatch.append("high geometric error")
                            if level_name == "fine" and (tile.get("originalError") != 0 or tile.get("terminalLeaf") is not True):
                                tile_mismatch.append("fine terminal/error0")
                            tile_rows.append({"id": tile_id, "b3dm": str(source_b3dm), "glbSha256": digest(glb), "bounds": actual_bounds, "triangles": len(transformed), "textureMipBytes": expected_texture_mip, "mismatches": tile_mismatch})
                            if tile_mismatch:
                                level_mismatches.append({"tile": tile_id, "checks": tile_mismatch})
                        except Exception as error:
                            tile_mismatch.append(str(error))
                            level_mismatches.append({"tile": tile_id, "checks": tile_mismatch})
                    if not all_triangles:
                        level_mismatches.append("no readable tiles")
                    else:
                        combined = np.concatenate(all_triangles)
                        try:
                            expected_mask, bounds = exact_mask(combined)
                            mask_meta = level.get("mask", {})
                            mask_path = resolve_stage_path(stage, mask_meta.get("localPath"), mask_meta.get("url"))
                            with Image.open(mask_path) as image:
                                actual_mask = np.asarray(image.convert("L"))
                            if actual_mask.shape != expected_mask.shape or not np.array_equal(actual_mask, expected_mask):
                                level_mismatches.append({"mask": "pixel mismatch", "expectedShape": list(expected_mask.shape), "actualShape": list(actual_mask.shape), "differentPixels": int(np.count_nonzero(actual_mask != expected_mask)) if actual_mask.shape == expected_mask.shape else None})
                            if mask_meta.get("sha256") != sha_path(mask_path):
                                level_mismatches.append({"mask": "sha256 mismatch"})
                            for key, value in bounds.items():
                                if mask_meta.get(key) != value:
                                    level_mismatches.append({"mask": f"{key} mismatch", "expected": value, "actual": mask_meta.get(key)})
                        except Exception as error:
                            level_mismatches.append({"mask": str(error)})
                    if level_mismatches:
                        owner_row["mismatches"].append({"level": level_name, "checks": level_mismatches})
                    owner_row["levels"][level_name] = {"tileCount": len(tiles), "actualTileIds": actual_ids, "tileRows": tile_rows, "mismatches": level_mismatches}
            except Exception as error:
                owner_row["mismatches"].append(str(error))
            rows.append(owner_row)
            for issue in owner_row["mismatches"]:
                mismatches.append({"scope": patch_id, **(issue if isinstance(issue, dict) else {"error": issue})})

    report = {
        "version": 1, "stage": str(stage), "stageManifest": str(manifest_path), "stageSha256": sha_path(manifest_path),
        "sourcePreparation": str(preparation_path), "sourcePreparationSha256": sha_path(preparation_path),
        "status": "pass" if not mismatches else "fail", "ownerCount": len(patches), "expectedOwnerCount": expected_owner_count,
        "levelCount": sum(len(patch.get("levels", {})) for patch in patches), "rows": rows, "mismatches": mismatches,
        "checks": {"b3dmReextractedGLB": True, "zipCRC32": True, "b3dmAndGLBSHA256": True, "baselineMatrix": True, "actualTransformedBounds": True, "actualTriangleCounts": True, "textureBytesAndMipAccounting": True, "exactTrianglePixelCentreMasks": True, "uniqueOwners": True, "noLiveSourceAncestorDuplicate": True, "noTileCrossOwner": True, "highErrorAtMost": HIGH_ERROR, "fineTerminalError": 0, "completeSelectedSubtree": True, "finiteGeometry": True},
        "limits": ["This validates source and mask integrity; browser loading and visual quality remain separate acceptance steps.", "No runtime asset or manifest was modified."],
    }
    output = stage / "independent-validation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "stageSha256": report["stageSha256"], "ownerCount": report["ownerCount"], "levelCount": report["levelCount"], "mismatches": len(mismatches), "output": str(output)}, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
