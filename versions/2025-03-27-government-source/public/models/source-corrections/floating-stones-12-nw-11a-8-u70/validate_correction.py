#!/usr/bin/env python3
"""Validate the U70 correction against its pinned source and manifest."""
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
    out = []
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = acc(gltf, binary, primitive["indices"]).reshape(-1, 3)
            assert int(indices.max()) < gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
            out.append((primitive, indices, {k: acc(gltf, binary, i) for k, i in primitive["attributes"].items()}))
    return out


def image_bytes(gltf, binary):
    out = []
    for image in gltf.get("images", []):
        view = gltf["bufferViews"][image["bufferView"]]
        out.append(binary[view.get("byteOffset", 0) : view.get("byteOffset", 0) + view["byteLength"]])
    return out


def without_offsets(images):
    return [{k: v for k, v in image.items() if k != "bufferView"} for image in images]


def validate(project: Path, folder: Path):
    manifest = json.loads((folder / "manifest.json").read_text())
    source = project / "public/models" / manifest["sourcePreview"]["url"]
    corrected = project / "public/models" / manifest["correctedPreview"]["url"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sourcePreview"]["sha256"]
    assert manifest["sourcePreview"]["sha256"] == "48dce7201378cdd09992cb70cc965eb80a45a5abd8a2c76c127342699ca3a1cc"
    assert hashlib.sha256(corrected.read_bytes()).hexdigest() == manifest["correctedPreview"]["sha256"]
    source_gltf, source_bin = read(source)
    corrected_gltf, corrected_bin = read(corrected)
    original = primitives(source_gltf, source_bin)
    fixed = primitives(corrected_gltf, corrected_bin)
    assert [len(x[1]) for x in original] == [1282, 2447, 1792, 1290]
    assert [len(x[1]) for x in fixed] == [1282, 2431, 1792, 1290]
    removed = set(manifest["removedSourceGlobalTriangleIndices"])
    expected_groups = [[1502, 1521, 1541, 1599, 1600], list(range(3458, 3469))]
    assert sorted(removed) == sorted(sum(expected_groups, [])) and len(removed) == 16
    checks = {}
    global_start = 0
    retained_ordinals = []
    for (source_primitive, source_indices, source_attrs), (fixed_primitive, fixed_indices, fixed_attrs) in zip(original, fixed):
        count = len(source_indices)
        local_removed = [i - global_start for i in sorted(removed) if global_start <= i < global_start + count]
        retained = [i for i in range(count) if i not in set(local_removed)]
        retained_ordinals.extend([global_start + i for i in retained])
        for name in ("POSITION", "TEXCOORD_0"):
            expected = np.delete(source_attrs[name][source_indices], local_removed, axis=0)
            actual = fixed_attrs[name][fixed_indices]
            assert np.array_equal(expected, actual)
            checks[f"{name}ExactRetainedTriangleEquality"] = True
        # Primitive semantics (mode/material/attribute names) stay the same.
        assert {k: v for k, v in source_primitive.items() if k not in ("indices", "attributes")} == {k: v for k, v in fixed_primitive.items() if k not in ("indices", "attributes")}
        global_start += count
    assert retained_ordinals == [i for i in range(6811) if i not in removed]
    checks["removedGlobalTriangleOrdinalsExact"] = True
    assert image_bytes(source_gltf, source_bin) == image_bytes(corrected_gltf, corrected_bin)
    checks["imagesPayloadByteExact"] = True
    assert without_offsets(source_gltf.get("images", [])) == without_offsets(corrected_gltf.get("images", []))
    checks["imagesSemanticMetadataUnchanged"] = True
    for key in ("textures", "samplers", "materials", "nodes", "scenes", "scene"):
        assert source_gltf.get(key) == corrected_gltf.get(key), key
    checks["materialsTexturesSamplersNodesTransformsScenesUnchanged"] = True
    assert corrected_gltf["asset"]["extras"]["sourceCorrection"]["sourcePreviewSha256"] == manifest["sourcePreview"]["sha256"]
    checks["sourceCorrectionMetadataPinned"] = True
    result = {
        "pass": True,
        "sourceSha256": manifest["sourcePreview"]["sha256"],
        "correctedSha256": manifest["correctedPreview"]["sha256"],
        "trianglesBefore": 6811,
        "trianglesAfter": 6795,
        "removedTriangles": 16,
        "primitiveTriangleCountsBefore": [1282, 2447, 1792, 1290],
        "primitiveTriangleCountsAfter": [1282, 2431, 1792, 1290],
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
