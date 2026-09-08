#!/usr/bin/env python3
"""Render offline Hall XI blob before/after comparison without touching manifests."""
from __future__ import annotations

import importlib.util
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "public/models/current-forms/ivillage-rebuild/ivillage-x-xiii-v1.glb"
EVIDENCE = ROOT / "public/models/hires/source-corrections/hall11-source-blob-v1/evidence.json"
STAGE = np.load("/tmp/hkust-ivillage-rebuild-source/terminal-triangles.npz")
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall11-blob-review"


def read(path):
    raw = path.read_bytes(); n = struct.unpack_from("<I", raw, 12)[0]
    return json.loads(raw[20:20+n]), bytearray(raw[28+n:])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gltf, binary = read(BASE)
    evidence = json.loads(EVIDENCE.read_text())
    ids = np.concatenate([np.asarray(item["stagedTriangleIndices"], dtype=np.int64) for item in evidence["sourceTiles"]])
    positions = STAGE["positions"][ids].reshape(-1, 3).astype("<f4")
    while len(binary) % 4: binary.append(0)
    view_pos = len(gltf["bufferViews"]); offset = len(binary); binary.extend(positions.tobytes())
    gltf["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": positions.nbytes, "target": 34962})
    access_pos = len(gltf["accessors"]); gltf["accessors"].append({"bufferView": view_pos, "componentType": 5126, "count": len(positions), "type": "VEC3", "min": positions.min(0).tolist(), "max": positions.max(0).tolist()})
    indices = np.arange(len(positions), dtype="<u4").reshape(-1, 3)
    view_idx = len(gltf["bufferViews"]); offset = len(binary); binary.extend(indices.tobytes())
    gltf["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": indices.nbytes, "target": 34963})
    access_idx = len(gltf["accessors"]); gltf["accessors"].append({"bufferView": view_idx, "componentType": 5125, "count": len(indices) * 3, "type": "SCALAR"})
    material = len(gltf["materials"]); gltf["materials"].append({"name": "HALL XI exact ray faces before correction", "doubleSided": True, "pbrMetallicRoughness": {"baseColorFactor": [0.95, 0.05, 0.04, 0.9], "metallicFactor": 0, "roughnessFactor": 1}, "alphaMode": "BLEND", "extensions": {"KHR_materials_unlit": {}}})
    mesh = len(gltf["meshes"]); gltf["meshes"].append({"name": "HALL XI exact ray faces before correction", "primitives": [{"attributes": {"POSITION": access_pos}, "indices": access_idx, "material": material}]})
    node = len(gltf["nodes"]); gltf["nodes"].append({"name": "HALL XI exact ray faces before correction", "mesh": mesh}); gltf["scenes"][gltf.get("scene", 0)]["nodes"].append(node)
    while len(binary) % 4: binary.append(0)
    gltf["buffers"][0]["byteLength"] = len(binary)
    js = json.dumps(gltf, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    before = OUT / "before-overlay.glb"; before.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(binary)) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(binary), b"BIN\0") + binary)
    spec = importlib.util.spec_from_file_location("renderer", ROOT / "scripts/render-photo-candidate.py"); renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
    views = {"east": (1, .45, -.8), "west": (-1, .45, .8), "north": (.2, .75, 1), "south": (-.2, .75, -1)}
    for name, view in views.items():
        renderer.render(before, OUT / f"before-{name}.png", size=(900, 650), view=view)
        renderer.render(BASE, OUT / f"after-{name}.png", size=(900, 650), view=view)
    report = {"status": "offline-before-after-rendered", "selectedFaces": len(ids), "views": list(views), "beforeOverlay": str(before.relative_to(ROOT)), "afterBase": str(BASE.relative_to(ROOT)), "limitations": ["Same projected views, not a live WebGL camera/LOD capture.", "Red overlay marks source faces selected by dense rays; it is not an assertion that every surrounding source face is removable.", "Runtime visual acceptance remains pending until local server reload is available."]}
    (OUT / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__": main()
