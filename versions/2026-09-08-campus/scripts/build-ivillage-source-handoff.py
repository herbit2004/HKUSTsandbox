#!/usr/bin/env python3
"""Build the exact DTM handoff left by audited i-Village source excisions."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/tmp/hkust-ivillage-rebuild-source")
OUT = ROOT / "public/surfaces/ivillage-source-handoff"
CORRECTIONS = ["hall11-lower-floaters-v3"]
TEXTURE_SOURCE = ROOT / "public/models/current-forms/ivillage-rebuild/textures/official-roof-paving.png"
TEXTURE_NAME = "official-2026-neutral-paving.png"
ASSET_NAME = "ivillage-source-handoff.glb"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_faces() -> set[tuple[int, int]]:
    selected: set[tuple[int, int]] = set()
    for correction in CORRECTIONS:
        path = ROOT / "public/models/hires/source-corrections" / correction / "evidence.json"
        evidence = json.loads(path.read_text())
        for tile in evidence["sourceTiles"]:
            source_tile = int(tile["sourceTileIndex"])
            selected.update((source_tile, int(face)) for face in tile["removedSourceTriangleIndices"])
    return selected


def coverage(point: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """XZ triangle inclusion using the same pixel-centre convention as coverage."""
    if not len(triangles):
        return np.zeros(0, dtype=bool)
    a = triangles[:, 0][:, (0, 2)]
    b = triangles[:, 1][:, (0, 2)]
    c = triangles[:, 2][:, (0, 2)]
    v0, v1, v2 = c - a, b - a, point - a
    denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    valid = np.abs(denominator) > 1e-12
    u = np.zeros(len(triangles))
    v = np.zeros(len(triangles))
    u[valid] = (v2[valid, 0] * v1[valid, 1] - v1[valid, 0] * v2[valid, 1]) / denominator[valid]
    v[valid] = (v0[valid, 0] * v2[valid, 1] - v2[valid, 0] * v0[valid, 1]) / denominator[valid]
    return valid & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)


def handoff_cells(step: float = 0.5):
    source = np.load(STAGE / "terminal-triangles.npz")
    triangles = source["positions"]
    tile, face = source["sourceTileIndex"], source["triangleIndex"]
    selected = selected_faces()
    removed = np.fromiter(((int(t), int(f)) in selected for t, f in zip(tile, face)), bool, len(tile))
    selected_triangles = triangles[removed]
    xz = selected_triangles[:, :, (0, 2)]
    min_x = math.floor(float(xz[:, :, 0].min()) / step) * step
    max_x = math.ceil(float(xz[:, :, 0].max()) / step) * step
    min_z = math.floor(float(xz[:, :, 1].min()) / step) * step
    max_z = math.ceil(float(xz[:, :, 1].max()) / step) * step
    tri_xz = triangles[:, :, (0, 2)]
    tri_min, tri_max = tri_xz.min(axis=1), tri_xz.max(axis=1)
    candidates = np.flatnonzero(
        (tri_max[:, 0] >= min_x) & (tri_min[:, 0] <= max_x)
        & (tri_max[:, 1] >= min_z) & (tri_min[:, 1] <= max_z)
    )
    deleted_candidates, retained_candidates = candidates[removed[candidates]], candidates[~removed[candidates]]
    cells: list[tuple[float, float]] = []
    for row in range(round((max_z - min_z) / step)):
        z = min_z + (row + 0.5) * step
        for col in range(round((max_x - min_x) / step)):
            x = min_x + (col + 0.5) * step
            point = np.array([x, z])
            if coverage(point, triangles[deleted_candidates]).any() and not coverage(point, triangles[retained_candidates]).any():
                cells.append((min_x + col * step, min_z + row * step))
    return cells, selected, {
        "bounds": [min_x, min_z, max_x, max_z],
        "candidateTriangles": int(len(candidates)),
        "deletedCandidateTriangles": int(len(deleted_candidates)),
        "retainedCandidateTriangles": int(len(retained_candidates)),
    }


def align4(data: bytearray) -> None:
    while len(data) % 4:
        data.append(0)


def append_view(binary: bytearray, data: bytes, target: int):
    align4(binary)
    offset = len(binary)
    binary.extend(data)
    return {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target}


def build_glb(cells: list[tuple[float, float]], grid) -> dict:
    ground = grid["ground"]
    x0, z0, step = float(grid["x0"]), float(grid["z0"]), float(grid["step"])

    def y(x: float, z: float) -> float:
        col, row = int(round((x - x0) / step)), int(round((z - z0) / step))
        return float(ground[row, col]) + 0.08

    positions, normals, uvs, indices = [], [], [], []
    for x, z in cells:
        points = np.array([
            [x, y(x, z), z], [x + step, y(x + step, z), z],
            [x + step, y(x + step, z + step), z + step], [x, y(x, z + step), z + step],
        ], dtype=np.float32)
        normal = np.cross(points[2] - points[0], points[1] - points[0])
        normal /= max(float(np.linalg.norm(normal)), 1e-12)
        base = len(positions)
        positions.extend(points.tolist())
        normals.extend([normal.tolist()] * 4)
        uvs.extend([[x / 7, z / 7], [(x + step) / 7, z / 7], [(x + step) / 7, (z + step) / 7], [x / 7, (z + step) / 7]])
        indices.extend([base, base + 2, base + 1, base, base + 3, base + 2])
    position, normal, uv = (np.asarray(v, dtype="<f4") for v in (positions, normals, uvs))
    index_dtype = "<u2" if len(position) < 65536 else "<u4"
    index = np.asarray(indices, dtype=index_dtype)
    binary = bytearray()
    views = [append_view(binary, position.tobytes(), 34962), append_view(binary, normal.tobytes(), 34962), append_view(binary, uv.tobytes(), 34962), append_view(binary, index.tobytes(), 34963)]
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": len(position), "type": "VEC3", "min": position.min(axis=0).astype(float).tolist(), "max": position.max(axis=0).astype(float).tolist()},
        {"bufferView": 1, "componentType": 5126, "count": len(normal), "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": len(uv), "type": "VEC2"},
        {"bufferView": 3, "componentType": 5123 if index_dtype == "<u2" else 5125, "count": len(index), "type": "SCALAR"},
    ]
    gltf = {
        "asset": {"version": "2.0", "generator": "HKUST exact source-to-DTM handoff"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "ivillage-source-handoff", "mesh": 0, "extras": {"surfaceNodeId": "ivillage-source-handoff"}}],
        "meshes": [{"name": "ivillage-source-handoff", "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
        "materials": [{"name": "official-2026-neutral-paving", "doubleSided": True, "pbrMetallicRoughness": {"baseColorFactor": [0.64, 0.69, 0.65, 1], "baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 0.92}}],
        "textures": [{"sampler": 0, "source": 0}], "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "images": [{"uri": TEXTURE_NAME}], "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors,
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    align4(binary)
    payload = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    payload += struct.pack("<II", len(js), 0x4E4F534A) + js
    payload += struct.pack("<II", len(binary), 0x004E4942) + binary
    asset = OUT / ASSET_NAME
    asset.write_bytes(payload)
    return {"url": ASSET_NAME, "sha256": sha(asset), "bytes": asset.stat().st_size, "vertices": len(position), "triangles": len(index) // 3, "bounds": {"min": accessors[0]["min"], "max": accessors[0]["max"]}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cells, selected, analysis = handoff_cells()
    if not cells:
        raise RuntimeError("No source-to-terrain ownership gaps found")
    asset = build_glb(cells, np.load(STAGE / "roof-grid.npz"))
    texture = OUT / TEXTURE_NAME
    texture.write_bytes(TEXTURE_SOURCE.read_bytes())
    image = Image.open(texture)
    manifest = {
        "version": 1, "id": "hkust-ivillage-source-handoff-v1", "asset": asset,
        "texture": {"url": TEXTURE_NAME, "sha256": sha(texture), "bytes": texture.stat().st_size, "dimensions": list(image.size), "source": "Byte-identical official-2026-derived neutral paving texture already used by the i-Village current-form set."},
        "coordinateSystem": "x=E-844800; y=source-local vertical; z=820500-N",
        "handoff": {"cellSizeMeters": 0.5, "cells": len(cells), "areaSquareMeters": len(cells) * 0.25, "verticalOffsetMeters": 0.08, "sourceCorrections": CORRECTIONS, "removedSourceFaces": len(selected), **analysis},
        "method": "At each 0.5 m centre covered by an audited deleted terminal triangle and no retained terminal triangle, reproduce the existing CEDD DTM corner heights. No broad polygon, hull, road, wall, tree, or building geometry is inferred.",
        "limitations": ["This is a renderer handoff surface, not a surveyed finished-ground model.", "The neutral material is an appearance bridge supported by the official 2026 i-Village completion photographs; it is not a calibrated orthophoto projection."],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
