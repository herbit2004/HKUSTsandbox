#!/usr/bin/env python3
"""Build the pinned, source-specific 12-NW-11A-8-U70 correction.

The removal set is deliberately an evidence list of global triangle ordinals.
It is never selected by height, AABB, normal, material, or a disconnectedness
heuristic.  The second evidence component is converted from primitive-local
ordinals only after asserting primitive 0's source triangle count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
TILE_ID = "12-NW-11A/12-NW-11A-8/Tile_302_142_L17_001"
SOURCE_REL = "preview-glb/12-NW-11A/12-NW-11A-8/Tile_302_142_L17_001.glb"
CORRECTED_REL = "source-corrections/floating-stones-12-nw-11a-8-u70/Tile_302_142_L17_001.corrected.glb"
SOURCE_SHA256 = "48dce7201378cdd09992cb70cc965eb80a45a5abd8a2c76c127342699ca3a1cc"
PRIMITIVE0_TRIANGLES = 1282
FIRST_GROUP = [1502, 1521, 1541, 1599, 1600]
SECOND_LOCAL_COMPONENT = list(range(2176, 2187))

DTYPES = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path):
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(raw)
    pos = 12
    chunks = []
    while pos < len(raw):
        length, kind = struct.unpack_from("<II", raw, pos)
        chunks.append((kind, raw[pos + 8 : pos + 8 + length]))
        pos += 8 + length
    js = next(data for kind, data in chunks if kind == 0x4E4F534A)
    binary = next(data for kind, data in chunks if kind == 0x004E4942)
    return raw, json.loads(js), binary


def accessor(gltf, binary: bytes, index: int) -> np.ndarray:
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    dtype = np.dtype(DTYPES[a["componentType"]])
    width = WIDTHS[a["type"]]
    offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", width * dtype.itemsize)
    if stride == width * dtype.itemsize:
        return np.frombuffer(binary, dtype=dtype, count=a["count"] * width, offset=offset).reshape(a["count"], width).copy()
    return np.ndarray(
        (a["count"], width), dtype=dtype, buffer=binary, offset=offset,
        strides=(stride, dtype.itemsize),
    ).copy()


def set_accessor(gltf, binary_views, index: int, values: np.ndarray):
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    assert not view.get("byteStride") and not a.get("byteOffset", 0)
    assert sum(v["bufferView"] == a["bufferView"] for v in gltf["accessors"]) == 1
    binary_views[a["bufferView"]] = values.tobytes()
    a["count"] = int(len(values))
    if a.get("type") == "VEC3" and a.get("componentType") == 5126:
        a["min"] = values.min(axis=0).astype(float).tolist()
        a["max"] = values.max(axis=0).astype(float).tolist()


def global_indices(gltf):
    primitive_counts = []
    total = 0
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            count = int(gltf["accessors"][primitive["indices"]]["count"]) // 3
            primitive_counts.append(count)
            total += count
    return primitive_counts, total


def transform_from_preview_manifest(project: Path):
    manifest = json.loads((project / "public/models/preview-manifest.json").read_text())
    entry = next(item for item in manifest["tiles"] if item["id"] == TILE_ID)
    return entry["matrix"]


def world_triangles(gltf, binary, matrix):
    m = np.asarray(matrix, dtype=float).reshape(4, 4, order="F")
    out = []
    global_start = 0
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            positions = accessor(gltf, binary, primitive["attributes"]["POSITION"])[indices]
            xyz = np.concatenate([positions, np.ones((*positions.shape[:2], 1), dtype=positions.dtype)], axis=2)
            out.extend((xyz @ m.T)[:, :, :3])
            global_start += len(indices)
    return np.asarray(out)


def bilinear_dtm(project: Path, xyz: np.ndarray):
    grid = json.loads((project / "public/terrain/height-grid-5m.json").read_text())
    heights = np.asarray(grid["heights"], dtype=float).reshape(grid["rows"], grid["columns"])
    result = []
    for x, _y, z in xyz:
        easting = 844800.0 + x
        northing = 820500.0 - z
        rf = (grid["first_northing"] - northing) / grid["sample_spacing_m"]
        cf = (easting - grid["first_easting"]) / grid["sample_spacing_m"]
        r, c = int(np.floor(rf)), int(np.floor(cf))
        dr, dc = rf - r, cf - c
        q = heights[r : r + 2, c : c + 2]
        assert q.shape == (2, 2) and np.isfinite(q).all()
        result.append(float(q[0, 0] * (1 - dr) * (1 - dc) + q[0, 1] * (1 - dr) * dc + q[1, 0] * dr * (1 - dc) + q[1, 1] * dr * dc))
    return np.asarray(result)


def evidence(gltf, binary, matrix, project):
    triangles = world_triangles(gltf, binary, matrix)
    groups = []
    for name, indices, rationale in [
        ("click-ray-isolated-stones", FIRST_GROUP, "ray-hit source component; all vertices are 3.47..5.63 m above bilinear DTM"),
        ("vertical-source-skirt", list(range(PRIMITIVE0_TRIANGLES + SECOND_LOCAL_COMPONENT[0], PRIMITIVE0_TRIANGLES + SECOND_LOCAL_COMPONENT[-1] + 1)), "face3460 local anchor; sky-visible near-vertical source skirt/remnant; lower edge touches DTM"),
    ]:
        xyz = triangles[indices]
        cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
        areas = np.linalg.norm(cross, axis=1) / 2.0
        normals = cross / np.maximum(np.linalg.norm(cross, axis=1)[:, None], 1e-30)
        flat = xyz.reshape(-1, 3)
        deltas = flat[:, 1] - bilinear_dtm(project, flat)
        groups.append({
            "name": name,
            "globalTriangleIndices": indices,
            "triangles": len(indices),
            "bounds": {"min": flat.min(axis=0).tolist(), "max": flat.max(axis=0).tolist()},
            "areaM2": float(areas.sum()),
            "normalYAbsAreaFraction": float(np.sum(areas * np.abs(normals[:, 1])) / areas.sum()),
            "rationale": rationale,
            "bilinearDtmVertexDeltaM": {"min": float(deltas.min()), "max": float(deltas.max())},
            **({"expectedDtmBand": "+3.47..+5.63 m"} if name == "click-ray-isolated-stones" else {"lowerEdgeTouchesDtm": bool(deltas.min() <= 0.1)}),
        })
    return {
        "sourceTileId": TILE_ID,
        "sourceSha256": SOURCE_SHA256,
        "primitiveTriangleCounts": [1282, 2447, 1792, 1290],
        "primitive0TriangleCountUsedForMapping": PRIMITIVE0_TRIANGLES,
        "secondComponentPrimitive": 1,
        "secondComponentLocalTriangleIndices": SECOND_LOCAL_COMPONENT,
        "secondComponentGlobalTriangleIndices": list(range(PRIMITIVE0_TRIANGLES + 2176, PRIMITIVE0_TRIANGLES + 2187)),
        "face3460Mapping": {"globalTriangleIndex": 3460, "primitive": 1, "primitiveLocalTriangleIndex": 2178},
        "groups": groups,
        "selectionPolicy": "Exact source SHA256 plus the two listed evidence groups only; no generic height, AABB, normal, material, or disconnectedness rule.",
    }


def build(project: Path, folder: Path):
    source = project / "public/models" / SOURCE_REL
    output = project / "public/models" / CORRECTED_REL
    assert sha(source) == SOURCE_SHA256, "Pinned source changed; re-audit the evidence before rebuilding."
    raw, gltf, binary = read_glb(source)
    counts, total = global_indices(gltf)
    assert counts == [1282, 2447, 1792, 1290] and total == 6811
    second_global = [PRIMITIVE0_TRIANGLES + i for i in SECOND_LOCAL_COMPONENT]
    removed = set(FIRST_GROUP + second_global)
    assert len(removed) == 16
    views = [binary[v.get("byteOffset", 0) : v.get("byteOffset", 0) + v["byteLength"]] for v in gltf["bufferViews"]]
    global_tri = 0
    removed_here = 0
    removed_vertices = 0
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            local = [i - global_tri for i in sorted(removed) if global_tri <= i < global_tri + len(indices)]
            global_tri += len(indices)
            if not local:
                continue
            kept = np.delete(indices, local, axis=0)
            used = np.unique(kept)
            remap = np.zeros(int(indices.max()) + 1, dtype=indices.dtype)
            remap[used] = np.arange(len(used), dtype=indices.dtype)
            kept = remap[kept]
            for name, accessor_index in primitive["attributes"].items():
                old = accessor(gltf, binary, accessor_index)
                if name == "POSITION":
                    removed_vertices += len(old) - len(used)
                set_accessor(gltf, views, accessor_index, old[used])
            set_accessor(gltf, views, primitive["indices"], kept.reshape(-1, 1))
            removed_here += len(local)
    assert removed_here == len(removed) and global_tri == total
    rebuilt = bytearray()
    for view, data in zip(gltf["bufferViews"], views):
        while len(rebuilt) % 4:
            rebuilt.append(0)
        view["byteOffset"] = len(rebuilt)
        view["byteLength"] = len(data)
        rebuilt.extend(data)
    while len(rebuilt) % 4:
        rebuilt.append(0)
    gltf["buffers"][0]["byteLength"] = len(rebuilt)
    gltf.setdefault("asset", {}).setdefault("extras", {})["sourceCorrection"] = {
        "id": "floating-stones-12-nw-11a-8-u70",
        "sourcePreviewSha256": SOURCE_SHA256,
        "removedSourceGlobalTriangleIndices": sorted(removed),
        "scope": "Two evidence-bound source groups only; no generic geometry rule.",
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(rebuilt))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(rebuilt), 0x004E4942) + rebuilt
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out)
    matrix = transform_from_preview_manifest(project)
    ev = evidence(read_glb(source)[1], read_glb(source)[2], matrix, project)
    (folder / "evidence.json").write_text(json.dumps(ev, indent=2) + "\n")
    manifest = {
        "id": "floating-stones-12-nw-11a-8-u70",
        "checkedAt": "2026-09-07",
        "tileId": TILE_ID,
        "sourcePreview": {"url": SOURCE_REL, "sha256": SOURCE_SHA256, "triangles": total, "primitiveTriangleCounts": counts},
        "correctedPreview": {"url": CORRECTED_REL, "sha256": sha(output), "triangles": total - removed_here, "trianglesRemoved": removed_here, "verticesRemoved": removed_vertices},
        "placementMatrix": matrix,
        "removedSourceGlobalTriangleIndices": sorted(removed),
        "removedGroups": [{"name": "click-ray-isolated-stones", "globalTriangleIndices": FIRST_GROUP}, {"name": "vertical-source-skirt", "primitive": 1, "localTriangleIndices": SECOND_LOCAL_COMPONENT, "globalTriangleIndices": second_global}],
        "evidence": "evidence.json",
        "validation": "retained-source-validation.json",
        "correctionValidation": "correction-validation.json",
        "buildScript": "build_correction.py",
        "validator": "validate_correction.py",
        "registration": "intentionally unregistered; preview-manifest.json is unchanged",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"sourceSha256": SOURCE_SHA256, "correctedSha256": manifest["correctedPreview"]["sha256"], "trianglesRemoved": removed_here, "trianglesAfter": total - removed_here, "verticesRemoved": removed_vertices}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--folder", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    build(args.project, args.folder)
