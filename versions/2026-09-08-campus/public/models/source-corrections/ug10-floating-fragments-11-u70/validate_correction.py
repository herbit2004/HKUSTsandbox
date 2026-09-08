#!/usr/bin/env python3
"""Validate the successor correction from the original preview source."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

DTYPES = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read(path):
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(raw)
    n, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + n])
    p = 20 + n
    n, kind = struct.unpack_from("<II", raw, p)
    assert kind == 0x004E4942
    return gltf, raw[p + 8 : p + 8 + n]


def acc(gltf, binary, index):
    a = gltf["accessors"][index]
    v = gltf["bufferViews"][a["bufferView"]]
    dtype = np.dtype(DTYPES[a["componentType"]])
    width = WIDTHS[a["type"]]
    stride = v.get("byteStride", width * dtype.itemsize)
    offset = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    if stride == width * dtype.itemsize:
        return np.frombuffer(binary, dtype=dtype, count=a["count"] * width, offset=offset).reshape(a["count"], width).copy()
    return np.ndarray((a["count"], width), dtype=dtype, buffer=binary, offset=offset, strides=(stride, dtype.itemsize)).copy()


def primitives(gltf, binary):
    result = []
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = acc(gltf, binary, primitive["indices"]).reshape(-1, 3)
            assert int(indices.max()) < gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
            result.append((primitive, indices, {k: acc(gltf, binary, i) for k, i in primitive["attributes"].items()}))
    return result


def image_bytes(gltf, binary):
    out = []
    for image in gltf.get("images", []):
        v = gltf["bufferViews"][image["bufferView"]]
        out.append(binary[v.get("byteOffset", 0) : v.get("byteOffset", 0) + v["byteLength"]])
    return out


def validate(project: Path, folder: Path):
    manifest = json.loads((folder / "manifest.json").read_text())
    source = project / "public/models" / manifest["sourcePreview"]["url"]
    corrected = project / "public/models" / manifest["correctedPreview"]["url"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == "eb0a2c37da99bfb3d8e788e3928552c6b295230dc60e9c6b4eba0bf335a60d9c"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sourcePreview"]["sha256"]
    assert hashlib.sha256(corrected.read_bytes()).hexdigest() == manifest["correctedPreview"]["sha256"]
    source_gltf, source_bin = read(source)
    fixed_gltf, fixed_bin = read(corrected)
    original = primitives(source_gltf, source_bin)
    fixed = primitives(fixed_gltf, fixed_bin)
    assert [len(x[1]) for x in original] == [104, 648, 9587]
    assert [len(x[1]) for x in fixed] == [104, 648, 9576]
    removed = set(manifest["removedSourceGlobalTriangleIndices"])
    assert sorted(removed) == [2554, 4000] + list(range(6548, 6557))
    assert len(removed) == 11
    checks = {}
    global_start = 0
    retained_ordinals = []
    for (old_primitive, old_indices, old_attrs), (new_primitive, new_indices, new_attrs) in zip(original, fixed):
        local_removed = [i - global_start for i in sorted(removed) if global_start <= i < global_start + len(old_indices)]
        local_removed_set = set(local_removed)
        retained = [i for i in range(len(old_indices)) if i not in local_removed_set]
        retained_ordinals.extend(global_start + i for i in retained)
        for name in ("POSITION", "TEXCOORD_0"):
            expected = np.delete(old_attrs[name][old_indices], local_removed, axis=0)
            actual = new_attrs[name][new_indices]
            assert np.array_equal(expected, actual)
            checks[f"{name}ExactRetainedTriangleEquality"] = True
        assert {k: v for k, v in old_primitive.items() if k not in ("indices", "attributes")} == {k: v for k, v in new_primitive.items() if k not in ("indices", "attributes")}
        global_start += len(old_indices)
    assert retained_ordinals == [i for i in range(10339) if i not in removed]
    checks["removedGlobalTriangleOrdinalsExact"] = True
    assert image_bytes(source_gltf, source_bin) == image_bytes(fixed_gltf, fixed_bin)
    checks["imagesPayloadByteExact"] = True
    assert [{k: v for k, v in x.items() if k != "bufferView"} for x in source_gltf.get("images", [])] == [{k: v for k, v in x.items() if k != "bufferView"} for x in fixed_gltf.get("images", [])]
    checks["imagesSemanticMetadataUnchanged"] = True
    for key in ("textures", "samplers", "materials", "nodes", "scenes", "scene"):
        assert source_gltf.get(key) == fixed_gltf.get(key), key
    checks["materialsTexturesSamplersNodesTransformsScenesUnchanged"] = True
    assert fixed_gltf["asset"]["extras"]["sourceCorrection"]["sourcePreviewSha256"] == manifest["sourcePreview"]["sha256"]
    checks["successorMetadataAndSourcePin"] = True
    old_folder = folder.parent / "ug10-isolated-photogrammetry-fragment-9"
    old_manifest = json.loads((old_folder / "manifest.json").read_text())
    assert old_manifest["id"] == "ug10-isolated-photogrammetry-fragment-9"
    old_output = project / "public/models" / old_manifest["correctedPreview"]["url"]
    assert hashlib.sha256(old_output.read_bytes()).hexdigest() == old_manifest["correctedPreview"]["sha256"]
    checks["predecessorCorrectionRemainsByteIntact"] = True
    result = {
        "pass": True,
        "sourceSha256": manifest["sourcePreview"]["sha256"],
        "correctedSha256": manifest["correctedPreview"]["sha256"],
        "trianglesBefore": 10339,
        "trianglesAfter": 10328,
        "removedTriangles": 11,
        "primitiveTriangleCountsBefore": [104, 648, 9587],
        "primitiveTriangleCountsAfter": [104, 648, 9576],
        **checks,
    }
    (folder / "retained-source-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (folder / "correction-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--folder", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(validate(args.project, args.folder), indent=2))
