#!/usr/bin/env python3
"""Small GLB helpers for evidence-bound source triangle corrections."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np

DTYPES = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path):
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(raw), path
    pos = 12
    chunks = []
    while pos < len(raw):
        length, kind = struct.unpack_from("<II", raw, pos)
        chunks.append((kind, raw[pos + 8 : pos + 8 + length]))
        pos += 8 + length
    json_bytes = next(data for kind, data in chunks if kind == 0x4E4F534A)
    bin_bytes = next(data for kind, data in chunks if kind == 0x004E4942)
    return raw, json.loads(json_bytes), bin_bytes


def accessor(gltf, binary: bytes, index: int) -> np.ndarray:
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    dtype = np.dtype(DTYPES[a["componentType"]])
    width = WIDTHS[a["type"]]
    offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", width * dtype.itemsize)
    if stride == width * dtype.itemsize:
        out = np.frombuffer(binary, dtype=dtype, count=a["count"] * width, offset=offset)
        return out.reshape(a["count"], width).copy()
    out = np.ndarray(
        (a["count"], width),
        dtype=dtype,
        buffer=binary,
        offset=offset,
        strides=(stride, dtype.itemsize),
    )
    return out.copy()


def set_accessor(gltf, binary_views, index: int, values: np.ndarray):
    a = gltf["accessors"][index]
    view = gltf["bufferViews"][a["bufferView"]]
    assert not view.get("byteStride"), "interleaved source is not safe for exact excision"
    assert not a.get("byteOffset", 0), "accessor offset is not safe for exact excision"
    binary_views[a["bufferView"]] = values.tobytes()
    a["count"] = int(len(values))
    if a.get("type") == "VEC3" and a.get("componentType") == 5126:
        a["min"] = values.min(axis=0).astype(float).tolist()
        a["max"] = values.max(axis=0).astype(float).tolist()


def rewrite(path: Path, removed: set[int], output: Path):
    original_sha = sha(path)
    _, gltf, binary = read_glb(path)
    views = []
    for view in gltf["bufferViews"]:
        start = view.get("byteOffset", 0)
        views.append(binary[start : start + view["byteLength"]])

    global_tri = 0
    removed_here = 0
    vertices_removed = 0
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            local = [
                i - global_tri
                for i in sorted(removed)
                if global_tri <= i < global_tri + len(indices)
            ]
            global_tri += len(indices)
            if not local:
                continue
            kept = np.delete(indices, local, axis=0)
            used = np.unique(kept)
            # Only indices present in ``used`` are read after this assignment.
            # A zero fill works for unsigned source index accessors and avoids
            # NumPy 2 rejecting the out-of-range ``-1`` sentinel for uint16.
            remap = np.zeros(int(indices.max()) + 1, dtype=indices.dtype)
            remap[used] = np.arange(len(used), dtype=indices.dtype)
            kept = remap[kept]
            for name, accessor_index in primitive["attributes"].items():
                old = accessor(gltf, binary, accessor_index)
                if name == "POSITION":
                    vertices_removed += len(old) - len(used)
                set_accessor(gltf, views, accessor_index, old[used])
            set_accessor(gltf, views, primitive["indices"], kept.reshape(-1, 1))
            removed_here += len(local)

    assert removed_here == len(removed), (path, removed_here, len(removed))
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
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(rebuilt))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(rebuilt), 0x004E4942) + rebuilt
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out)
    return {
        "source": str(path),
        "sourceSha256": original_sha,
        "derived": str(output),
        "derivedSha256": sha(output),
        "sourceTriangles": global_tri,
        "removedTriangles": removed_here,
        "removedVertices": vertices_removed,
        "bytes": len(out),
    }
