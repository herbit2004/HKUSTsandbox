#!/usr/bin/env python3
"""Build ug10-floating-fragments-12-u70 from the pinned original preview GLB."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
TILE_ID = "12-NW-11A/12-NW-11A-3/Tile_302_143_L16_0"
SOURCE_REL = "preview-glb/12-NW-11A/12-NW-11A-3/Tile_302_143_L16_0.glb"
CORRECTED_REL = "source-corrections/ug10-floating-fragments-12-u70/Tile_302_143_L16_0.corrected.glb"
SOURCE_SHA256 = "eb0a2c37da99bfb3d8e788e3928552c6b295230dc60e9c6b4eba0bf335a60d9c"
OLD_GROUP = list(range(6548, 6557))
NEW_GROUPS = [[2554], [4000], [4123]]
REMOVE_GLOBAL = sorted(OLD_GROUP + [2554, 4000, 4123])
PRIMITIVE_TRIANGLE_COUNTS = [104, 648, 9587]
MATRIX = [
    -0.9117219534236938, -0.3801367557607591, -0.15562076610513031, 0.0,
    -0.41074872424360365, 0.8432718934491277, 0.34664696669794866, 0.0,
    -0.0005425795679911971, 0.37998494785279036, -0.9249700468499213, 0.0,
    574.99364810728, 164.52631378173828, -1025.0055075756973, 1.0,
]
DTYPES = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path):
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(raw)
    pos, chunks = 12, []
    while pos < len(raw):
        length, kind = struct.unpack_from("<II", raw, pos)
        chunks.append((kind, raw[pos + 8:pos + 8 + length]))
        pos += 8 + length
    js = next(data for kind, data in chunks if kind == 0x4E4F534A)
    binary = next(data for kind, data in chunks if kind == 0x004E4942)
    return raw, json.loads(js), binary


def accessor(gltf, binary: bytes, index: int) -> np.ndarray:
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    dtype, width = np.dtype(DTYPES[a["componentType"]]), WIDTHS[a["type"]]
    offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", width * dtype.itemsize)
    if stride == width * dtype.itemsize:
        return np.frombuffer(binary, dtype=dtype, count=a["count"] * width, offset=offset).reshape(a["count"], width).copy()
    return np.ndarray((a["count"], width), dtype=dtype, buffer=binary, offset=offset, strides=(stride, dtype.itemsize)).copy()


def set_accessor(gltf, views, index: int, values: np.ndarray):
    a, view = gltf["accessors"][index], gltf["bufferViews"][gltf["accessors"][index]["bufferView"]]
    assert not view.get("byteStride") and not a.get("byteOffset", 0)
    assert sum(v["bufferView"] == a["bufferView"] for v in gltf["accessors"]) == 1
    views[a["bufferView"]] = values.tobytes()
    a["count"] = int(len(values))
    if a.get("type") == "VEC3" and a.get("componentType") == 5126:
        a["min"], a["max"] = values.min(axis=0).astype(float).tolist(), values.max(axis=0).astype(float).tolist()


def primitive_triangles(gltf, binary):
    return [accessor(gltf, binary, p["indices"]).reshape(-1, 3) for m in gltf["meshes"] for p in m["primitives"]]


def world_triangles(gltf, binary):
    m = np.asarray(MATRIX, dtype=float).reshape(4, 4, order="F")
    result = []
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            pos = accessor(gltf, binary, primitive["attributes"]["POSITION"])[indices]
            homogeneous = np.concatenate([pos, np.ones((*pos.shape[:2], 1), dtype=pos.dtype)], axis=2)
            result.extend((homogeneous @ m.T)[:, :, :3])
    return np.asarray(result)


def face_evidence(triangles, indices, name, rationale):
    xyz = triangles[indices]
    cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2.0
    normal = cross / np.maximum(np.linalg.norm(cross, axis=1)[:, None], 1e-30)
    flat = xyz.reshape(-1, 3)
    return {"name": name, "globalTriangleIndices": indices, "triangles": len(indices),
            "bounds": {"min": flat.min(axis=0).tolist(), "max": flat.max(axis=0).tolist()},
            "areaM2": float(area.sum()),
            "slopeDegreesFromVertical": float(np.degrees(np.arccos(np.clip(np.abs(normal[:, 1]), 0.0, 1.0))).mean()),
            "rationale": rationale}


def build(project: Path, folder: Path):
    source, output = project / "public/models" / SOURCE_REL, project / "public/models" / CORRECTED_REL
    assert sha(source) == SOURCE_SHA256, "Pinned source changed; re-audit before rebuilding."
    _raw, gltf, binary = read_glb(source)
    prims = primitive_triangles(gltf, binary)
    assert [len(x) for x in prims] == PRIMITIVE_TRIANGLE_COUNTS
    assert 4123 - sum(PRIMITIVE_TRIANGLE_COUNTS[:2]) == 3371
    removed, views = set(REMOVE_GLOBAL), [binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]] for v in gltf["bufferViews"]]
    global_start = removed_here = removed_vertices = 0
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            local = [i - global_start for i in REMOVE_GLOBAL if global_start <= i < global_start + len(indices)]
            global_start += len(indices)
            if local:
                kept, used = np.delete(indices, local, axis=0), np.unique(np.delete(indices, local, axis=0))
                remap = np.zeros(int(indices.max()) + 1, dtype=indices.dtype)
                remap[used] = np.arange(len(used), dtype=indices.dtype)
                kept = remap[kept]
                for name, ai in primitive["attributes"].items():
                    old = accessor(gltf, binary, ai)
                    if name == "POSITION":
                        removed_vertices += len(old) - len(used)
                    set_accessor(gltf, views, ai, old[used])
                set_accessor(gltf, views, primitive["indices"], kept.reshape(-1, 1))
                removed_here += len(local)
    assert removed_here == 12 and global_start == 10339
    rebuilt = bytearray()
    for view, data in zip(gltf["bufferViews"], views):
        while len(rebuilt) % 4: rebuilt.append(0)
        view["byteOffset"], view["byteLength"] = len(rebuilt), len(data)
        rebuilt.extend(data)
    while len(rebuilt) % 4: rebuilt.append(0)
    gltf["buffers"][0]["byteLength"] = len(rebuilt)
    gltf.setdefault("asset", {}).setdefault("extras", {})["sourceCorrection"] = {
        "id": "ug10-floating-fragments-12-u70", "successorOf": "ug10-floating-fragments-11-u70",
        "sourcePreviewSha256": SOURCE_SHA256, "removedSourceGlobalTriangleIndices": REMOVE_GLOBAL,
        "scope": "Inherited nine-face group plus three explicitly evidenced single faces; no generic selector.",
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4: js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(rebuilt))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(rebuilt), 0x004E4942) + rebuilt)
    triangles = world_triangles(*read_glb(source)[1:])
    evidence = {
        "sourceTileId": TILE_ID, "sourceSha256": SOURCE_SHA256,
        "primitiveTriangleCounts": PRIMITIVE_TRIANGLE_COUNTS, "successorOf": "ug10-floating-fragments-11-u70",
        "oldRemovedGlobalTriangleIndices": OLD_GROUP, "newEvidenceGlobalTriangleIndices": [2554, 4000, 4123],
        "newEvidenceLocalMapping": [{"globalTriangleIndex": 2554, "primitive": 2, "primitiveLocalTriangleIndex": 1802}, {"globalTriangleIndex": 4000, "primitive": 2, "primitiveLocalTriangleIndex": 3248}, {"globalTriangleIndex": 4123, "primitive": 2, "primitiveLocalTriangleIndex": 3371}],
        "groups": [
            {"name": "inherited-old-isolated-component", "globalTriangleIndices": OLD_GROUP, "evidence": "ug10-isolated-photogrammetry-fragment-9/suspect-nine-triangles.json"},
            face_evidence(triangles, [2554], "low-angle-floating-stone", "Stable browser low-angle ray hit; independently confirmed isolated single face."),
            face_evidence(triangles, [4000], "small-floating-ring-fragment", "Stable browser ray hit; independently confirmed isolated single face."),
            face_evidence(triangles, [4123], "successor-floating-fragment", "Explicit successor-only source face; independently mapped to primitive2 local 3371. The exact source ordinal is selected by evidence, not a generic rule."),
        ],
        "removedUnion": REMOVE_GLOBAL,
        "selectionPolicy": "Exact original preview SHA256 plus the inherited nine-face group and the three explicitly listed single faces only; no generic height, AABB, slope, material, or disconnectedness selector.",
    }
    (folder / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    manifest = {
        "id": "ug10-floating-fragments-12-u70", "checkedAt": "2026-09-08", "tileId": TILE_ID,
        "successorOf": {"id": "ug10-floating-fragments-11-u70", "directory": "source-corrections/ug10-floating-fragments-11-u70", "sourceCorrectionRemainsUnchanged": True, "sourceOfTruth": "original preview GLB; this successor is a one-shot union correction"},
        "sourcePreview": {"url": SOURCE_REL, "sha256": SOURCE_SHA256, "triangles": 10339, "primitiveTriangleCounts": PRIMITIVE_TRIANGLE_COUNTS},
        "correctedPreview": {"url": CORRECTED_REL, "sha256": sha(output), "triangles": 10327, "trianglesRemoved": 12, "verticesRemoved": removed_vertices},
        "placementMatrix": MATRIX, "removedSourceGlobalTriangleIndices": REMOVE_GLOBAL,
        "removedGroups": [
            {"name": "inherited-old-isolated-component", "globalTriangleIndices": OLD_GROUP},
            {"name": "low-angle-floating-stone", "primitive": 2, "primitiveLocalTriangleIndex": 1802, "globalTriangleIndices": [2554]},
            {"name": "small-floating-ring-fragment", "primitive": 2, "primitiveLocalTriangleIndex": 3248, "globalTriangleIndices": [4000]},
            {"name": "successor-floating-fragment", "primitive": 2, "primitiveLocalTriangleIndex": 3371, "globalTriangleIndices": [4123]},
        ],
        "evidence": "evidence.json", "validation": "retained-source-validation.json", "correctionValidation": "correction-validation.json", "buildScript": "build_correction.py", "validator": "validate_correction.py", "registration": "intentionally unregistered; preview-manifest.json is unchanged",
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"sourceSha256": SOURCE_SHA256, "correctedSha256": manifest["correctedPreview"]["sha256"], "trianglesRemoved": removed_here, "trianglesAfter": 10327, "verticesRemoved": removed_vertices}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--folder", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    build(args.project, args.folder)
