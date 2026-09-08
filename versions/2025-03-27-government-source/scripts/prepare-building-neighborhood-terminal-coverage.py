#!/usr/bin/env python3
"""Prepare complete native source frontiers for the v4 building-neighborhood plan.

This is a source preparation step only.  It never writes ``public`` or any
runtime manifest.  By default the output is under ``/tmp`` and the network
path, when preparation is requested, consists only of bounded HTTP ZIP range
requests.  The selected L18 owner is kept as the unit of selection: all of its
high frontier and all of its error-zero terminal leaves are retained together.
Selecting only leaves whose conservative bounds touch a footprint can split a
surface in half, so this script deliberately does not do that.

Requires numpy and Pillow, plus scripts/hkust_source_geometry.py.  No network
request is made by ``--plan-only``.
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import struct
import time
import urllib.request
import zlib

import numpy as np
from PIL import Image

from hkust_source_geometry import geometry


PROJECT = Path(__file__).resolve().parents[1]
PLAN_DEFAULT = PROJECT / "docs/source-evidence-v4/building-quality/targeted-terminal-coverage-plan-u68.json"
LIVE_MANIFEST = PROJECT / "public/models/hires/manifest.json"
RENDER_MANIFEST = PROJECT / "public/models/render-manifest.json"
STEP = 0.5
HIGH_ERROR = 1.75
DEFAULT_GUARD = 80 * 1024 * 1024


def read_json(path):
    return json.loads(path.read_text())


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_path(path):
    return sha_bytes(path.read_bytes())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def slug(value):
    return value.replace("/", "_").replace(" ", "-")


def owner_stem(owner_id):
    return owner_id.rsplit("/", 1)[-1]


def leaf_id(sheet, sub, uri):
    return f"{sheet}/{sub}/{Path(uri).stem}"


def uri_of(node):
    content = node.get("content", {})
    return content.get("uri", content.get("url"))


def find_owner_node(root, source_node_path, owner_id):
    """Find the exact content node represented by the plan's L18 path."""
    wanted = [Path(item).name for item in source_node_path]
    matches = []

    def visit(node, chain):
        uri = uri_of(node)
        next_chain = chain + ([Path(uri).name] if uri else [])
        if next_chain == wanted:
            matches.append(node)
        for child in node.get("children", []):
            visit(child, next_chain)

    visit(root, [])
    assert len(matches) == 1, f"Expected one source owner path for {owner_id}, got {len(matches)}"
    node = matches[0]
    assert uri_of(node) and Path(uri_of(node)).stem == owner_stem(owner_id), owner_id
    assert "L18_" in Path(uri_of(node)).stem, owner_id
    return node


def complete_frontier(node, threshold, owner_id):
    """Return complete source descendants at a geometric-error frontier."""
    children = node.get("children", [])
    uri = uri_of(node)
    if threshold == 0:
        if children:
            result = []
            for child in children:
                result.extend(complete_frontier(child, threshold, owner_id))
            return result
        assert uri and node.get("geometricError", 0) == 0, f"Non-terminal error frontier for {owner_id}"
        return [node]
    if uri and (node.get("geometricError", 0) <= threshold or not children):
        return [node]
    assert children, f"Owner {owner_id} has no usable source frontier"
    result = []
    for child in children:
        result.extend(complete_frontier(child, threshold, owner_id))
    assert result, owner_id
    return result


def frontier_names(frontier, sheet, sub, owner_id, expected=None):
    names = [uri_of(node) for node in frontier]
    assert all(names) and len(names) == len(set(names)), owner_id
    ids = [leaf_id(sheet, sub, name) for name in names]
    if expected is not None:
        # The plan's candidate leaves are an intersection hint.  They must be
        # present in the owner subtree, while the preparation deliberately
        # expands to the complete owner frontier to avoid half tiles.
        assert set(expected) <= set(ids), f"Plan leaf outside source owner subtree for {owner_id}"
    return names, ids


def mip_bytes(width, height):
    total = 0
    w, h = width, height
    while True:
        total += w * h * 4
        if w == h == 1:
            return total
        w, h = max(1, w // 2), max(1, h // 2)


def parse_glb(glb, path):
    assert glb[:4] == b"glTF", f"GLB magic mismatch: {path}"
    version, total = struct.unpack_from("<II", glb, 4)
    assert version == 2 and total == len(glb), f"GLB length mismatch: {path}"
    json_len, json_type = struct.unpack_from("<I4s", glb, 12)
    assert json_type == b"JSON" and 20 + json_len <= len(glb), f"GLB JSON chunk mismatch: {path}"
    document = json.loads(glb[20:20 + json_len].decode("utf-8").rstrip(" \t\r\n\x00"))
    binary = glb[20 + json_len:]
    if binary:
        binary_len, binary_type = struct.unpack_from("<I4s", binary, 0)
        assert binary_type == b"BIN\x00" and 8 + binary_len <= len(binary), f"GLB BIN chunk mismatch: {path}"
        binary = binary[8:8 + binary_len]
    textures = []
    for image_index, image in enumerate(document.get("images", [])):
        assert "bufferView" in image, f"External/non-embedded image {image_index} in {path}"
        view = document["bufferViews"][image["bufferView"]]
        begin = view.get("byteOffset", 0)
        encoded = binary[begin:begin + view["byteLength"]]
        assert len(encoded) == view["byteLength"], f"Image bufferView truncated: {path}"
        with Image.open(io.BytesIO(encoded)) as picture:
            width, height = picture.size
            picture.load()
        textures.append({
            "index": image_index,
            "width": width,
            "height": height,
            "encodedBytes": len(encoded),
            "mipBytes": mip_bytes(width, height),
            "sha256": sha_bytes(encoded),
        })
    primitives = [primitive for mesh in document.get("meshes", []) for primitive in mesh.get("primitives", [])]
    assert primitives and all("POSITION" in p.get("attributes", {}) for p in primitives), f"GLB has no positions: {path}"
    assert all("TEXCOORD_0" in p.get("attributes", {}) for p in primitives), f"GLB UV missing: {path}"
    return document, textures


def verify_b3dm(data, path):
    assert len(data) >= 28, f"b3dm too short: {path}"
    magic, version, byte_length, ft_json, ft_bin, bt_json, bt_bin = struct.unpack_from("<4s6I", data)
    assert magic == b"b3dm" and version in (0, 1), f"b3dm header mismatch: {path}"
    assert byte_length == len(data), f"b3dm byteLength mismatch: {path}"
    glb = data[28 + ft_json + ft_bin + bt_json + bt_bin:]
    assert glb[:4] == b"glTF" and struct.unpack_from("<I", glb, 8)[0] == len(glb), f"Embedded GLB length mismatch: {path}"
    return glb


def zip_range(url, key, entry, retries=4):
    """Read exactly one bounded ZIP member through HTTP Range."""
    offset = int(entry["offset"])
    compressed_size = int(entry["compressed"])
    # The local header's extra field is variable.  A bounded 64KiB allowance
    # avoids an unbounded ZIP request while leaving enough room for the source
    # archive's local header.  The payload itself is always sliced by the
    # header-declared compressed size.
    end = offset + 30 + len(key.encode("utf-8")) + 65536 + compressed_size - 1
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-{end}"})
            with urllib.request.urlopen(request, timeout=45) as response:
                assert response.status == 206, "Server ignored bounded ZIP range"
                payload = response.read()
            header = struct.unpack_from("<4s5H3L2H", payload)
            assert header[0] == b"PK\x03\x04", "ZIP local-header magic mismatch"
            name_len, extra_len = header[-2:]
            local_name = payload[30:30 + name_len].decode("utf-8")
            assert local_name == key, f"ZIP member mismatch: {local_name} != {key}"
            begin = 30 + name_len + extra_len
            compressed = payload[begin:begin + compressed_size]
            assert len(compressed) == compressed_size, "ZIP member range truncated"
            if int(entry.get("compression", 0)) == 0:
                data = compressed
            elif int(entry["compression"]) == 8:
                data = zlib.decompress(compressed, -15)
            else:
                raise AssertionError(f"Unsupported ZIP compression {entry['compression']}")
            assert len(data) == int(entry["size"]), "ZIP member size mismatch"
            assert (zlib.crc32(data) & 0xffffffff) == int(entry["crc32"]), "ZIP member CRC32 mismatch"
            return data
        except Exception as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(attempt + 1)
    raise last_error


def exact_mask(path, triangles, patch_id, level):
    """Rasterize actual transformed triangle projections at 0.5m pixel centres."""
    assert len(triangles) and np.isfinite(triangles).all()
    lo = triangles.min(axis=(0, 1))
    hi = triangles.max(axis=(0, 1))
    x0, z0 = np.floor(lo[[0, 2]] / STEP) * STEP
    x1, z1 = np.ceil(hi[[0, 2]] / STEP) * STEP
    width, height = int(round((x1 - x0) / STEP)), int(round((z1 - z0) / STEP))
    assert width > 0 and height > 0, f"Empty mask bounds: {patch_id}/{level}"
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
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, mode="L").save(path)
    return {
        "url": str(path),
        "localPath": str(path),
        "minX": float(x0), "minZ": float(z0), "maxX": float(x1), "maxZ": float(z1),
        "width": width, "height": height, "pixelSizeMeters": STEP,
        "coveredPixels": int((mask > 0).sum()), "sha256": sha_path(path),
        "rowDirection": "increasing local Z",
        "projection": "Actual complete-frontier transformed source triangle pixel-centre projection; no AABB, convex hull, rectangle or dilation fill.",
    }


def select_focuses(plan, requested, all_flag):
    available = list(plan["focusSets"])
    if all_flag or not requested:
        return available
    selected = []
    for value in requested:
        for name in value.split(","):
            name = name.strip()
            if not name:
                continue
            if name not in plan["focusSets"]:
                raise SystemExit(f"Unknown focus {name!r}; choose from: {', '.join(available)}")
            if name not in selected:
                selected.append(name)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("/tmp/hkust-building-neighborhood-terminal-coverage"))
    parser.add_argument("--focus", action="append", help="Focus name; repeat or provide comma-separated names")
    parser.add_argument("--all", action="store_true", help="Select every owner in the plan")
    parser.add_argument("--plan-only", action="store_true", help="Write planning statistics only; never download")
    parser.add_argument("--source-guard-mib", type=float, default=80.0, help="Maximum unique compressed source bytes (default: 80 MiB)")
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    out = args.output.resolve()
    project = PROJECT
    assert not out.is_relative_to(project / "public"), "Output must not be inside public runtime assets"
    assert args.source_guard_mib > 0
    plan = read_json(plan_path)
    assert plan.get("planId") == "targeted-terminal-coverage-plan-u68"
    live = read_json(LIVE_MANIFEST)
    render = read_json(RENDER_MANIFEST)
    live_patches = live.get("patches", [])
    published_owner_ids = {p.get("sourceAncestor") for p in live_patches if p.get("sourceAncestor")}
    published_leaf_ids = set()
    for patch in live_patches:
        for level in patch.get("levels", {}).values():
            published_leaf_ids.update(tile.get("id") for tile in level.get("tiles", []) if tile.get("id"))
    published_owner_ids.update(owner["ownerId"] for owner in plan["owners"] if owner.get("publishedOwner"))
    published_leaf_ids.update(leaf_id for owner in plan["owners"] for leaf_id in owner.get("publishedLeafIds", []))
    for focus in plan["focusSets"].values():
        published_owner_ids.update(focus.get("publishedOwnerIds", []))
        published_leaf_ids.update(focus.get("publishedLeafIds", []))
    focus_names = select_focuses(plan, args.focus, args.all)
    selected_ids = []
    missing_from_plan = []
    owner_by_id = {owner["ownerId"]: owner for owner in plan["owners"]}
    if args.all or not args.focus:
        selected_ids = [owner["ownerId"] for owner in plan["owners"]]
    else:
        for focus_name in focus_names:
            for owner_id in plan["focusSets"][focus_name].get("ownerIds", []):
                if owner_id not in selected_ids:
                    selected_ids.append(owner_id)
            # Accept older v4 focus records that also listed candidate owners.
            for owner_id in plan["focusSets"][focus_name].get("candidateOwnerIds", []):
                if owner_id not in owner_by_id and owner_id not in published_owner_ids:
                    missing_from_plan.append(owner_id)
    assert not missing_from_plan, f"Focus candidates missing from plan owners: {missing_from_plan}"
    selected_owners = [owner_by_id[owner_id] for owner_id in selected_ids if owner_id in owner_by_id]
    candidate_ids_for_focus = {
        owner_id
        for focus_name in focus_names
        for owner_id in plan["focusSets"][focus_name].get("candidateOwnerIds", [])
    }
    skipped_published_owners = sorted(candidate_ids_for_focus & published_owner_ids)
    assert not any(owner["ownerId"] in published_owner_ids for owner in selected_owners), "Published owner selected for duplicate staging"

    baselines = {tile["id"]: tile for tile in render["tiles"]}
    jobs = {}
    owner_records = []
    tree_cache = {}
    index_cache = {}
    url_cache = {}
    for owner in selected_owners:
        owner_id = owner["ownerId"]
        tree_path = project / owner["sourceTree"]
        assert sha_path(tree_path) == owner["sourceTreeSha256"], f"Source tree changed: {owner_id}"
        if tree_path not in tree_cache:
            tree_cache[tree_path] = read_json(tree_path)
        node = find_owner_node(tree_cache[tree_path]["root"], owner["sourceNodePath"], owner_id)
        baseline = baselines.get(owner["sourceBaselineId"])
        assert baseline, f"Missing source baseline: {owner['sourceBaselineId']}"
        index_path = project / owner["sourceZipIndex"]
        # v4 stores the index digest on each leaf record (some owner records
        # predate the owner-level convenience field).
        expected_index_sha = owner.get("sourceZipIndexSha256")
        if expected_index_sha is None and owner.get("leaves"):
            expected_index_sha = owner["leaves"][0].get("sourceZipIndexSha256")
        actual_index_sha = sha_path(index_path)
        if expected_index_sha is not None:
            assert actual_index_sha == expected_index_sha, f"Source ZIP index changed: {owner_id}"
        if index_path not in index_cache:
            index_cache[index_path] = read_json(index_path)
        if owner["sheet"] not in url_cache:
            url_cache[owner["sheet"]] = read_json(project / "source-geodata/mesh" / owner["sheet"] / "subset-manifest.json")["source"]
        levels = {}
        for level, threshold in (("high", HIGH_ERROR), ("fine", 0)):
            frontier = complete_frontier(node, threshold, owner_id)
            expected = owner.get("candidateLeafIds") if level == "fine" else None
            names, ids = frontier_names(frontier, owner["sheet"], owner["sub"], owner_id, expected)
            if level == "fine":
                assert all(not n.get("children") and n.get("geometricError", 0) == 0 for n in frontier), owner_id
            levels[level] = {"names": names, "ids": ids, "nodes": frontier, "threshold": threshold}
            for name, tile_id, tile_node in zip(names, ids, frontier):
                entry = index_cache[index_path].get(f"{owner['sub']}/{name}")
                assert entry and entry.get("size") is not None, f"Missing ZIP index entry: {owner_id}/{name}"
                planned_entry = next((item for item in owner.get("leaves", []) if item["leafId"] == tile_id), None)
                if planned_entry:
                    assert planned_entry["sourceZipEntry"] == {k: entry[k] for k in ["size", "compressed", "offset", "crc32"]}, tile_id
                if tile_id in published_leaf_ids:
                    continue
                job = jobs.setdefault(tile_id, {
                    "id": tile_id, "sheet": owner["sheet"], "sub": owner["sub"], "name": name,
                    "entry": entry, "indexPath": index_path, "sourceURL": url_cache[owner["sheet"]],
                    "node": tile_node, "matrix": baseline["matrix"], "baselineId": baseline["id"],
                    "ownerIds": [],
                })
                assert job["entry"] == entry and job["matrix"] == baseline["matrix"], tile_id
                if owner_id not in job["ownerIds"]:
                    job["ownerIds"].append(owner_id)
        owner_records.append({"plan": owner, "node": node, "baseline": baseline, "levels": levels})

    source_bytes = sum(int(job["entry"]["compressed"]) for job in jobs.values())
    guard_bytes = int(args.source_guard_mib * 1024 * 1024)
    assert source_bytes <= guard_bytes, f"Bounded preparation is {source_bytes / 1024 / 1024:.3f} MiB, above --source-guard-mib {args.source_guard_mib:g}"
    selection = {
        "planId": plan["planId"], "planPath": str(plan_path), "planSha256": sha_path(plan_path),
        "focusSets": focus_names, "ownerCount": len(owner_records), "uniquePayloads": len(jobs),
        "sourceZipBytes": source_bytes, "sourceZipMiB": round(source_bytes / 1024 / 1024, 3),
        "expectedTextureMipBytes": None, "expectedTextureMipStatus": "unknown-until-download",
        "highErrorMeters": HIGH_ERROR, "fineErrorMeters": 0,
        "publishedOwnerCountSkipped": len(skipped_published_owners), "skippedPublishedOwners": skipped_published_owners,
        "publishedLeafCountSuppressed": sum(1 for owner in owner_records for level in owner["levels"].values() for tile_id in level["ids"] if tile_id in published_leaf_ids),
        "sourceGuardBytes": guard_bytes, "sourceGuardMiB": args.source_guard_mib,
        "completeOwnerFrontiers": True,
        "maskMethod": "Downloaded GLB actual transformed triangles projected at exact 0.5m pixel centres; no AABB/convex-hull mask.",
    }
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "plan.json", {
        "status": "bounded-source-plan", "selection": selection,
        "owners": [{
            "ownerId": record["plan"]["ownerId"], "sourceAncestor": record["plan"]["sourceAncestor"],
            "sourceTree": record["plan"]["sourceTree"], "sourceTreeSha256": record["plan"]["sourceTreeSha256"],
            "sourceZipIndex": record["plan"]["sourceZipIndex"], "sourceZipIndexSha256": sha_path(project / record["plan"]["sourceZipIndex"]), "sourceBaselineId": record["plan"]["sourceBaselineId"],
            "entityIds": record["plan"].get("entityIds", []),
            "highFiles": len(record["levels"]["high"]["ids"]), "fineFiles": len(record["levels"]["fine"]["ids"]),
            "highLeafIds": record["levels"]["high"]["ids"], "fineLeafIds": record["levels"]["fine"]["ids"],
            "suppressedPublishedLeafIds": [tile_id for level in record["levels"].values() for tile_id in level["ids"] if tile_id in published_leaf_ids],
        } for record in owner_records],
        "payloads": [{
            "id": job["id"], "sourceURL": job["sourceURL"], "sourceZipIndex": str(job["indexPath"].relative_to(project)),
            "sourceZipKey": f"{job['sub']}/{job['name']}", "sourceZipEntry": job["entry"], "ownerIds": job["ownerIds"],
            "expectedTextureMipBytes": None, "expectedTextureMipStatus": "unknown-until-download",
        } for job in jobs.values()],
    })
    if args.plan_only:
        write_json(out / "source-preparation.json", {"version": 1, "status": "plan-only-no-download", "selection": selection, "ownerCount": len(owner_records), "uniqueSourcePayloads": len(jobs), "sourceZipBytes": source_bytes, "expectedTextureMipBytes": None, "expectedTextureMipStatus": "unknown-until-download", "networkRequests": 0})
        print(json.dumps({"status": "plan-only", **selection}, ensure_ascii=False, indent=2), flush=True)
        return

    def acquire(job):
        entry, key = job["entry"], f"{job['sub']}/{job['name']}"
        b3dm_path = out / "source-b3dm" / job["sheet"] / job["sub"] / job["name"]
        candidates = [b3dm_path, project / "source-geodata/mesh" / job["sheet"] / job["sub"] / job["name"]]
        data, reused = None, None
        for candidate in candidates:
            if candidate.exists():
                value = candidate.read_bytes()
                if len(value) == int(entry["size"]) and (zlib.crc32(value) & 0xffffffff) == int(entry["crc32"]):
                    data, reused = value, str(candidate)
                    break
        if data is None:
            data = zip_range(job["sourceURL"], key, entry)
        glb = verify_b3dm(data, b3dm_path)
        glb_path = out / "source" / job["sheet"] / job["sub"] / Path(job["name"]).with_suffix(".glb")
        b3dm_path.parent.mkdir(parents=True, exist_ok=True)
        if b3dm_path.exists():
            assert b3dm_path.read_bytes() == data, f"Refusing to overwrite different b3dm: {b3dm_path}"
        else:
            b3dm_path.write_bytes(data)
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        if glb_path.exists():
            assert glb_path.read_bytes() == glb, f"Refusing to overwrite different GLB: {glb_path}"
        else:
            glb_path.write_bytes(glb)
        document, textures = parse_glb(glb, glb_path)
        triangles, _ = geometry(glb_path, np.asarray(job["matrix"], dtype=np.float64).reshape(4, 4, order="F"))
        assert len(triangles) and np.isfinite(triangles).all(), f"Invalid transformed triangles: {job['id']}"
        lo, hi = triangles.min(axis=(0, 1)), triangles.max(axis=(0, 1))
        vertices = sum(document["accessors"][primitive["attributes"]["POSITION"]]["count"] for primitive in [p for m in document.get("meshes", []) for p in m.get("primitives", [])])
        return job["id"], {
            "id": job["id"], "url": str(glb_path.relative_to(out)), "localPath": str(glb_path),
            "sourceB3dmPath": str(b3dm_path), "sourceUrl": job["sourceURL"], "sourceURL": job["sourceURL"],
            "sourceZipIndex": str(job["indexPath"].relative_to(project)), "sourceZipKey": key, "sourceZipEntry": entry,
            "sourceZipCRC32": entry["crc32"], "sourceZipOffset": entry["offset"],
            "sourceZipRange": {"start": entry["offset"], "end": entry["offset"] + 30 + len(key.encode("utf-8")) + 65536 + int(entry["compressed"]) - 1},
            "sourceB3dmSha256": sha_bytes(data), "sha256": sha_bytes(glb), "matrix": job["matrix"], "matrixSourceBaselineId": job["baselineId"],
            "originalError": job["node"].get("geometricError", 0), "terminalLeaf": not bool(job["node"].get("children")), "sourceAncestors": [],
            "bounds": {"min": lo.tolist(), "max": hi.tolist()}, "center": ((lo + hi) / 2).tolist(), "triangles": len(triangles), "vertices": vertices,
            "bytes": len(glb), "sourceB3dmBytes": len(data), "textureMipBytes": sum(t["mipBytes"] for t in textures),
            "textureBytes": sum(t["width"] * t["height"] * 4 for t in textures), "textureEncodedBytes": sum(t["encodedBytes"] for t in textures),
            "textureDimensions": [[t["width"], t["height"]] for t in textures], "textures": textures, "allUvPresent": True,
            "reusedVerifiedB3dm": reused, "sourcePreservation": "GLB byte-for-byte extracted from ZIP-CRC32-verified original b3dm; original geometry, UV and encoded image payloads retained.",
        }, triangles

    tiles, triangles_by_id = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(acquire, job) for job in jobs.values()]
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            tile_id, record, triangles = future.result()
            tiles[tile_id], triangles_by_id[tile_id] = record, triangles
            if count % 10 == 0 or count == len(futures):
                print(f"verified source payloads {count}/{len(futures)}", flush=True)

    patches = []
    for owner_record in owner_records:
        owner, levels_data = owner_record["plan"], owner_record["levels"]
        levels = {}
        for level_name in ("high", "fine"):
            ids = [tile_id for tile_id in levels_data[level_name]["ids"] if tile_id not in published_leaf_ids]
            selected_tiles = [tiles[tile_id] for tile_id in ids]
            assert selected_tiles, f"Published deduplication removed every tile from {owner['ownerId']}/{level_name}"
            all_triangles = np.concatenate([triangles_by_id[tile_id] for tile_id in ids])
            lo, hi = all_triangles.min(axis=(0, 1)), all_triangles.max(axis=(0, 1))
            mask_file = out / "masks" / f"{slug('native-targeted-' + owner['ownerId'])}-{level_name}.png"
            mask = exact_mask(mask_file, all_triangles, owner["ownerId"], level_name)
            for tile in selected_tiles:
                tile["sourceAncestors"] = owner.get("sourceNodePath", [])[:-1]
            levels[level_name] = {
                "maximumOriginalError": max(tile["originalError"] for tile in selected_tiles), "geometricErrorMax": max(tile["originalError"] for tile in selected_tiles),
                "completeSelectedSubtree": True, "publishedLeavesSuppressed": [tile_id for tile_id in levels_data[level_name]["ids"] if tile_id in published_leaf_ids],
                "tiles": selected_tiles, "bounds": {"min": lo.tolist(), "max": hi.tolist()}, "triangles": len(all_triangles), "bytes": sum(tile["bytes"] for tile in selected_tiles),
                "textureBytes": sum(tile["textureBytes"] for tile in selected_tiles), "textureMipBytes": sum(tile["textureMipBytes"] for tile in selected_tiles),
                "mask": mask, "frontier": "Complete original L18 subtree: " + ("first source frontier at error <=1.75m" if level_name == "high" else "all terminal error0 leaves"),
            }
        lo = np.minimum(levels["high"]["bounds"]["min"], levels["fine"]["bounds"]["min"])
        hi = np.maximum(levels["high"]["bounds"]["max"], levels["fine"]["bounds"]["max"])
        patches.append({
            "id": "native-targeted-" + slug(owner["ownerId"]), "sourceAncestor": owner["sourceAncestor"], "sourceOriginalTree": owner["sourceTree"],
            "sourceOriginalTreeSha256": owner["sourceTreeSha256"], "baselineIds": [owner["sourceBaselineId"]], "partial": True,
            "bounds": {"min": lo.tolist(), "max": hi.tolist()}, "center": ((lo + hi) / 2).tolist(), "levels": levels, "mask": levels["high"]["mask"],
            "sourceFrontier": {"completeSelectedSubtree": True, "fineMaximumOriginalError": 0, "fineTerminalCount": len(levels["fine"]["tiles"]), "highMaximumOriginalError": levels["high"]["maximumOriginalError"]},
            "sourceEntityIds": owner.get("entityIds", []), "focusSets": [name for name in focus_names if owner["ownerId"] in plan["focusSets"][name].get("ownerIds", [])],
        })
    metadata = {
        "version": 1, "status": "isolated source preparation, not installed or visually accepted", "coordinateSystem": live["coordinateSystem"], "source": live["source"],
        "selection": selection, "plan": str(plan_path), "patches": patches,
        "changesToSource": "None. Only lossless b3dm embedded GLB extraction and exact transformed-triangle masks were generated; no bridge, terrain plane, texture resize or gap geometry.",
    }
    write_json(out / "manifest.json", metadata)
    frontier_costs = {level: {"triangles": sum(p["levels"][level]["triangles"] for p in patches), "glbBytes": sum(p["levels"][level]["bytes"] for p in patches), "textureMipBytes": sum(p["levels"][level]["textureMipBytes"] for p in patches), "maskBytesR8": sum(p["levels"][level]["mask"]["width"] * p["levels"][level]["mask"]["height"] for p in patches)} for level in ("high", "fine")}
    report = {"version": 1, "status": "stage-ready-source-only", "selection": selection, "owners": len(patches), "uniqueSourcePayloads": len(tiles), "sourceZipBytes": source_bytes, "downloadedPayloads": sum(tile["reusedVerifiedB3dm"] is None for tile in tiles.values()), "frontierCosts": frontier_costs, "manifestSHA256": sha_path(out / "manifest.json"), "network": {"method": "HTTP Range only", "statusRequired": 206, "maxConcurrency": 3}, "limitations": ["Source ZIP index bounds are acquisition evidence; visual acceptance remains separate.", "Published source owners and leaves are suppressed before staging to prevent duplicate runtime ownership.", "No runtime manifest, app code, public asset or QA artifact was modified."]}
    write_json(out / "source-preparation.json", report)
    print(json.dumps({"status": "stage-ready", "output": str(out), "owners": len(patches), "uniqueSourcePayloads": len(tiles), "sourceZipBytes": source_bytes, "frontierCosts": frontier_costs}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
