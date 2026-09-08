#!/usr/bin/env python3
"""Validate exact retention and exact source ordinal deletion for this correction."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

DTYPES = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
SOURCE_SHA256 = "eb0a2c37da99bfb3d8e788e3928552c6b295230dc60e9c6b4eba0bf335a60d9c"
REMOVED = [2554, 4000, 4123, *range(6548, 6557)]
BEFORE = [104, 648, 9587]
AFTER = [104, 648, 9575]


def read(path: Path):
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    assert (magic, version, total) == (0x46546C67, 2, len(raw))
    n, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20:20 + n])
    p = 20 + n
    n, kind = struct.unpack_from("<II", raw, p)
    assert kind == 0x004E4942
    return gltf, raw[p + 8:p + 8 + n]


def acc(gltf, binary, index):
    a, v = gltf["accessors"][index], gltf["bufferViews"][gltf["accessors"][index]["bufferView"]]
    dtype, width = np.dtype(DTYPES[a["componentType"]]), WIDTHS[a["type"]]
    stride, offset = v.get("byteStride", width * dtype.itemsize), v.get("byteOffset", 0) + a.get("byteOffset", 0)
    if stride == width * dtype.itemsize:
        return np.frombuffer(binary, dtype=dtype, count=a["count"] * width, offset=offset).reshape(a["count"], width).copy()
    return np.ndarray((a["count"], width), dtype=dtype, buffer=binary, offset=offset, strides=(stride, dtype.itemsize)).copy()


def primitive_data(gltf, binary):
    out = []
    for mesh in gltf["meshes"]:
        for p in mesh["primitives"]:
            indices = acc(gltf, binary, p["indices"]).reshape(-1, 3)
            attrs = {name: acc(gltf, binary, index) for name, index in p["attributes"].items()}
            assert int(indices.max()) < len(attrs["POSITION"])
            out.append((p, indices, attrs))
    return out


def image_payloads(gltf, binary):
    result = []
    for image in gltf.get("images", []):
        view = gltf["bufferViews"][image["bufferView"]]
        result.append(binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]])
    return result


def validate(project: Path, folder: Path):
    manifest = json.loads((folder / "manifest.json").read_text())
    source = project / "public/models" / manifest["sourcePreview"]["url"]
    corrected = project / "public/models" / manifest["correctedPreview"]["url"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256 == manifest["sourcePreview"]["sha256"]
    corrected_sha = hashlib.sha256(corrected.read_bytes()).hexdigest()
    assert corrected_sha == manifest["correctedPreview"]["sha256"]
    source_gltf, source_bin, fixed_gltf, fixed_bin = (*read(source), *read(corrected))
    original, fixed = primitive_data(source_gltf, source_bin), primitive_data(fixed_gltf, fixed_bin)
    assert [len(x[1]) for x in original] == BEFORE
    assert [len(x[1]) for x in fixed] == AFTER
    assert len(REMOVED) == 12 and sorted(manifest["removedSourceGlobalTriangleIndices"]) == REMOVED
    checks = {}
    global_start, retained_ordinals = 0, []
    for (old_p, old_i, old_a), (new_p, new_i, new_a), expected_count in zip(original, fixed, AFTER):
        local_removed = [i - global_start for i in REMOVED if global_start <= i < global_start + len(old_i)]
        retained = [i for i in range(len(old_i)) if i not in set(local_removed)]
        retained_ordinals.extend(global_start + i for i in retained)
        assert len(new_i) == expected_count
        for name in old_a:
            assert name in new_a
            assert np.array_equal(old_a[name][old_i][retained], new_a[name][new_i])
        checks["allRetainedAttributesExact"] = True
        checks["POSITIONExactRetainedTriangleEquality"] = True
        checks["TEXCOORD_0ExactRetainedTriangleEquality"] = True
        assert {k: v for k, v in old_p.items() if k not in ("indices", "attributes")} == {k: v for k, v in new_p.items() if k not in ("indices", "attributes")}
        global_start += len(old_i)
    assert global_start == sum(BEFORE) == 10339
    assert retained_ordinals == [i for i in range(10339) if i not in REMOVED]
    checks["removedGlobalTriangleOrdinalsExact"] = True
    assert image_payloads(source_gltf, source_bin) == image_payloads(fixed_gltf, fixed_bin)
    checks["imagesPayloadByteExact"] = True
    assert [{k: v for k, v in x.items() if k != "bufferView"} for x in source_gltf.get("images", [])] == [{k: v for k, v in x.items() if k != "bufferView"} for x in fixed_gltf.get("images", [])]
    checks["imagesSemanticMetadataUnchanged"] = True
    for key in ("textures", "samplers", "materials", "nodes", "scenes", "scene"):
        assert source_gltf.get(key) == fixed_gltf.get(key), key
    checks["materialsTexturesSamplersNodesTransformsScenesUnchanged"] = True
    extras = fixed_gltf["asset"]["extras"]["sourceCorrection"]
    assert extras["id"] == manifest["id"] and extras["successorOf"] == "ug10-floating-fragments-11-u70" and extras["sourcePreviewSha256"] == SOURCE_SHA256
    assert extras["removedSourceGlobalTriangleIndices"] == REMOVED
    checks["successorMetadataAndSourcePin"] = True
    predecessor = folder.parent / "ug10-floating-fragments-11-u70"
    predecessor_manifest = json.loads((predecessor / "manifest.json").read_text())
    predecessor_output = project / "public/models" / predecessor_manifest["correctedPreview"]["url"]
    assert hashlib.sha256(predecessor_output.read_bytes()).hexdigest() == predecessor_manifest["correctedPreview"]["sha256"]
    checks["predecessorCorrectionRemainsByteIntact"] = True
    result = {"pass": True, "sourceSha256": SOURCE_SHA256, "correctedSha256": corrected_sha,
              "trianglesBefore": 10339, "trianglesAfter": 10327, "removedTriangles": 12,
              "primitiveTriangleCountsBefore": BEFORE, "primitiveTriangleCountsAfter": AFTER, **checks}
    for name in ("retained-source-validation.json", "correction-validation.json"):
        (folder / name).write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--folder", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(validate(args.project, args.folder), indent=2))
