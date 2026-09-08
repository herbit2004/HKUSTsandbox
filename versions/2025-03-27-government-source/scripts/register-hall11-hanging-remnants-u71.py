#!/usr/bin/env python3
"""Register the reviewed Hall XI U71 hanging-remnant correction.

The target source branch is visible through the top-level native manifest, the
native-corridor aggregate and descriptor, plus the terminal residential/IAS
aggregate.  High and fine native frontiers are updated atomically and every
changed coverage mask is rebuilt from the retained triangles.
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize

from hkust_source_geometry import geometry


ROOT = Path(__file__).resolve().parents[1]
HIRES = ROOT / "public/models/hires"
TOP_MANIFEST = HIRES / "manifest.json"
NATIVE_MANIFEST = HIRES / "native-corridor/manifest.json"
PATCH_ID = "native-12-NW-11A_12-NW-11A-3_Tile_302_143_L18_003"
DESCRIPTOR = HIRES / "native-corridor/descriptors" / f"{PATCH_ID}.json"
PARTIAL_MANIFEST = HIRES / "partial-residential-ias/manifest.json"
PARTIAL_ID = "residential-ias-terminal-cluster"
CORRECTION_ID = "hall11-hanging-remnants-u71"
EVIDENCE = HIRES / f"source-corrections/{CORRECTION_ID}/evidence.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    assert magic == b"glTF" and version == 2 and declared_length == len(raw)
    length, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + length])
    triangles = vertices = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            triangles += int(gltf["accessors"][primitive["indices"]]["count"]) // 3
            vertices += int(gltf["accessors"][primitive["attributes"]["POSITION"]]["count"])
    return triangles, vertices


def patch(data: dict, patch_id: str) -> dict:
    if data.get("id") == patch_id:
        return data
    matches = [value for value in data["patches"] if value["id"] == patch_id]
    assert len(matches) == 1
    return matches[0]


def replace_patch(data: dict, value: dict) -> None:
    matches = [index for index, item in enumerate(data["patches"]) if item["id"] == value["id"]]
    assert len(matches) == 1
    data["patches"][matches[0]] = copy.deepcopy(value)


def find_tile(value: dict, tile_id: str) -> tuple[str, dict]:
    matches = [
        (level_name, tile)
        for level_name, level in value["levels"].items()
        for tile in level.get("tiles", [])
        if tile["id"] == tile_id
    ]
    assert len(matches) == 1, (value["id"], tile_id, len(matches))
    return matches[0]


def update_tile(value: dict, item: dict) -> str:
    level_name, tile = find_tile(value, item["sourceId"])
    assert tile["sha256"] == item["sourceSha256"]
    assert tile["triangles"] == item["sourceTriangles"]
    source = ROOT / item["sourceUrl"]
    corrected = ROOT / item["correctedUrl"]
    assert sha(source) == item["sourceSha256"]
    assert sha(corrected) == item["correctedSha256"]
    triangles, vertices = counts(corrected)
    assert triangles == item["retainedTriangles"]
    matrix = np.asarray(tile["matrix"]).reshape(4, 4, order="F")
    transformed, _ = geometry(corrected, matrix)
    low = transformed.min(axis=(0, 1))
    high = transformed.max(axis=(0, 1))
    predecessor = tile.get("sourceCorrection")
    tile.update(
        {
            "url": str(corrected.relative_to(HIRES)).replace("\\", "/"),
            "sha256": item["correctedSha256"],
            "bytes": corrected.stat().st_size,
            "triangles": triangles,
            "vertices": vertices,
            "bounds": {"min": low.tolist(), "max": high.tolist()},
            "center": ((low + high) / 2).tolist(),
            "sourceCorrection": {
                "id": CORRECTION_ID,
                "originalUrl": item["sourceUrl"].removeprefix("public/models/hires/"),
                "originalSha256": item["sourceSha256"],
                "originalTriangles": item["sourceTriangles"],
                "removedTriangleCount": item["removedTriangles"],
                "removedSourceTriangleIndices": item["removedSourceTriangleIndices"],
                "evidence": str(EVIDENCE.relative_to(HIRES)).replace("\\", "/"),
            },
        }
    )
    if predecessor and predecessor.get("id") != CORRECTION_ID:
        tile["sourceCorrection"]["upstream"] = predecessor
    return level_name


def level_triangles(level: dict) -> np.ndarray:
    pieces = []
    for tile in level["tiles"]:
        triangles, _ = geometry(
            HIRES / tile["url"],
            np.asarray(tile["matrix"]).reshape(4, 4, order="F"),
        )
        pieces.append(triangles)
    assert pieces
    return np.concatenate(pieces)


def refresh_level(level: dict) -> np.ndarray:
    merged = level_triangles(level)
    low = merged.min(axis=(0, 1))
    high = merged.max(axis=(0, 1))
    level["bounds"] = {"min": low.tolist(), "max": high.tolist()}
    for field in ("triangles", "vertices", "bytes", "textureBytes", "textureMipBytes", "textureEncodedBytes"):
        if field in level:
            level[field] = sum(int(tile.get(field, 0)) for tile in level["tiles"])
    return merged


def refresh_patch_bounds(value: dict) -> None:
    bounds = [level["bounds"] for level in value["levels"].values()]
    low = np.min(np.asarray([item["min"] for item in bounds]), axis=0)
    high = np.max(np.asarray([item["max"] for item in bounds]), axis=0)
    value["bounds"] = {"min": low.tolist(), "max": high.tolist()}
    value["center"] = ((low + high) / 2).tolist()


def write_mask(descriptor: dict, merged: np.ndarray, note: str) -> dict:
    resolution = float(descriptor["pixelSizeMeters"])
    cross = np.cross(merged[:, 1] - merged[:, 0], merged[:, 2] - merged[:, 0])
    projected = merged[:, :, [0, 2]][np.abs(cross[:, 1]) > 1e-9]
    shapes = (
        ({"type": "Polygon", "coordinates": [[*triangle.tolist(), triangle[0].tolist()]]}, 255)
        for triangle in projected
    )
    image = rasterize(
        shapes,
        out_shape=(int(descriptor["height"]), int(descriptor["width"])),
        transform=Affine(resolution, 0, descriptor["minX"], 0, resolution, descriptor["minZ"]),
        dtype="uint8",
        all_touched=False,
    )
    target = HIRES / descriptor["url"]
    Image.fromarray(image).save(target)
    result = dict(descriptor)
    result["coveredPixels"] = int(np.count_nonzero(image))
    result["sha256"] = sha(target)
    if "projection" in result:
        result["projection"] = note
    if "source" in result:
        result["source"] = note
    return result


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["id"] == CORRECTION_ID
    assert evidence["status"] == "exact-component-candidate-not-registered"
    items = {item["level"]: item for item in evidence["sourceTiles"]}
    assert set(items) == {"high", "fine"}

    top = json.loads(TOP_MANIFEST.read_text())
    native = json.loads(NATIVE_MANIFEST.read_text())
    partial = json.loads(PARTIAL_MANIFEST.read_text())
    authoritative = copy.deepcopy(patch(top, PATCH_ID))
    saved_descriptor = json.loads(DESCRIPTOR.read_text())
    assert patch(native, PATCH_ID)["id"] == saved_descriptor["id"] == PATCH_ID

    assert update_tile(authoritative, items["high"]) == "high"
    assert update_tile(authoritative, items["fine"]) == "fine"
    native_masks = {}
    for level_name in ("high", "fine"):
        level = authoritative["levels"][level_name]
        merged = refresh_level(level)
        level["mask"] = write_mask(
            level["mask"],
            merged,
            "Actual retained complete-frontier source triangle pixel-center projection after the reviewed Hall XI U71 hanging-remnant correction; no rectangle/hull/dilation fill.",
        )
        native_masks[level_name] = level["mask"]
    authoritative["mask"] = copy.deepcopy(authoritative["levels"]["high"]["mask"])
    refresh_patch_bounds(authoritative)
    replace_patch(top, authoritative)
    replace_patch(native, authoritative)

    partial_patch = patch(partial, PARTIAL_ID)
    assert update_tile(partial_patch, items["fine"]) == "high"
    partial_level = partial_patch["levels"]["high"]
    partial_triangles = refresh_level(partial_level)
    partial_level["mask"] = write_mask(
        partial_level["mask"],
        partial_triangles,
        "Actual projected retained source triangles from 123 terminal leaves after four positively audited exact connected-component corrections. No bbox, hull or dilation fill.",
    )
    partial_patch["mask"] = copy.deepcopy(partial_level["mask"])
    refresh_patch_bounds(partial_patch)
    partial_patch["evidence"]["retainedTriangleCountAfterCorrection"] = int(len(partial_triangles))
    partial_patch["evidence"]["sourceCorrection"] = str(EVIDENCE.relative_to(HIRES)).replace("\\", "/")
    partial_patch["evidence"]["sourceCorrectionRemovedTriangleCount"] = int(
        partial_patch["evidence"].get("sourceCorrectionRemovedTriangleCount", 0)
    ) + int(items["fine"]["removedTriangles"])

    DESCRIPTOR.write_text(json.dumps(authoritative, ensure_ascii=False, indent=2) + "\n")
    NATIVE_MANIFEST.write_text(json.dumps(native, ensure_ascii=False, indent=2) + "\n")
    TOP_MANIFEST.write_text(json.dumps(top, ensure_ascii=False, indent=2) + "\n")
    PARTIAL_MANIFEST.write_text(json.dumps(partial, ensure_ascii=False, indent=2) + "\n")

    evidence["status"] = "candidate-registered-unpublished-runtime-qa-required"
    evidence["registeredRuntimeViews"] = {
        "native": [
            str(TOP_MANIFEST.relative_to(ROOT)),
            str(NATIVE_MANIFEST.relative_to(ROOT)),
            str(DESCRIPTOR.relative_to(ROOT)),
        ],
        "terminalAggregate": str(PARTIAL_MANIFEST.relative_to(ROOT)),
    }
    evidence["coverage"] = {
        "nativeHigh": native_masks["high"],
        "nativeFine": native_masks["fine"],
        "partialResidentialHigh": partial_level["mask"],
    }
    evidence["retainedNativeTriangles"] = {
        level: int(authoritative["levels"][level]["triangles"]) for level in ("high", "fine")
    }
    evidence["retainedClusterTriangles"] = int(len(partial_triangles))
    evidence["checks"]["runtimeRegistrationPerformed"] = True
    evidence["limitations"] = [
        "Registration and exact mask validation are complete; browser owner-ray validation and production publication remain separate work."
    ]
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({
        "status": evidence["status"],
        "removedTriangles": evidence["removedTriangles"],
        "nativeHighTriangles": authoritative["levels"]["high"]["triangles"],
        "nativeFineTriangles": authoritative["levels"]["fine"]["triangles"],
        "nativeHighMask": native_masks["high"]["sha256"],
        "nativeFineMask": native_masks["fine"]["sha256"],
        "partialTriangles": len(partial_triangles),
        "partialMask": partial_level["mask"]["sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
