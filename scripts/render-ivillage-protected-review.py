#!/usr/bin/env python3
"""Render protected i-Village source components against current form, DTM and footprints.

This is an offline review scene only.  It does not change runtime assets.  The
protected components are colour-coded, the DTM is a translucent reference
surface, and official Hall X-XIII 2-D outlines are shown as orange lines.
Small source-tile candidates are included in charcoal so they can be checked
without being mistaken for an approved deletion set.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "public/models/current-forms/ivillage-rebuild"
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/protected-review"
STAGE = np.load("/tmp/hkust-ivillage-rebuild-source/terminal-triangles.npz")
SOURCE_POS = STAGE["positions"].astype("<f4")
REVIEW = json.loads((BASE / "evidence/nonbuilding-source-review.json").read_text())
PROTECTED = json.loads((BASE / "evidence/protected-unattributed-volumes.json").read_text())
GRID = np.load("/tmp/hkust-ivillage-rebuild-source/roof-grid.npz")
FOOTPRINTS = json.loads((ROOT / "public/data/building-footprints.json").read_text())["footprints"]

COMPONENT_COLOURS = {
    4: [0.93, 0.10, 0.10, 0.95],
    5: [1.00, 0.48, 0.02, 0.95],
    9: [0.00, 0.80, 0.95, 0.95],
    12: [0.70, 0.20, 0.95, 0.95],
    15: [0.98, 0.08, 0.62, 0.95],
    20: [1.00, 0.90, 0.05, 0.95],
}
CANDIDATE_TILES = [106, 44, 46, 7, 9, 91, 92, 93, 94, 95]


def read_glb(path: Path):
    raw = path.read_bytes()
    n = struct.unpack_from("<I", raw, 12)[0]
    return json.loads(raw[20 : 20 + n]), bytearray(raw[28 + n :])


def add_accessor(gltf, binary, values, typ="VEC3", component=5126, target=34962):
    arr = np.asarray(values)
    while len(binary) % 4:
        binary.append(0)
    view = len(gltf["bufferViews"])
    binary.extend(arr.tobytes())
    gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binary) - arr.nbytes,
                                 "byteLength": arr.nbytes, "target": target})
    accessor = {"bufferView": view, "componentType": component, "count": int(len(arr)), "type": typ}
    if typ == "VEC3" and component == 5126:
        accessor["min"] = arr.min(axis=0).astype(float).tolist()
        accessor["max"] = arr.max(axis=0).astype(float).tolist()
    ai = len(gltf["accessors"])
    gltf["accessors"].append(accessor)
    return ai


def add_mesh(gltf, binary, positions, indices, colour, mode=4, name="review"):
    pi = add_accessor(gltf, binary, np.asarray(positions, dtype="<f4"), "VEC3")
    ii = add_accessor(gltf, binary, np.asarray(indices, dtype="<u4").reshape(-1, 1), "SCALAR", 5125, 34963)
    mi = len(gltf["materials"])
    gltf["materials"].append({"name": name, "doubleSided": True,
        "pbrMetallicRoughness": {"baseColorFactor": colour, "metallicFactor": 0, "roughnessFactor": 1},
        "alphaMode": "BLEND" if colour[3] < 1 else "OPAQUE",
        "extensions": {"KHR_materials_unlit": {}}})
    mesh = len(gltf["meshes"])
    gltf["meshes"].append({"name": name, "primitives": [{"attributes": {"POSITION": pi},
        "indices": ii, "material": mi, "mode": mode}]})
    node = len(gltf["nodes"])
    gltf["nodes"].append({"name": name, "mesh": mesh})
    gltf["scenes"][gltf.get("scene", 0)]["nodes"].append(node)


def component_faces():
    out = {}
    for c in REVIEW["components"]:
        out[int(c["component"])] = np.asarray(c["stagedTriangleIndices"], dtype=np.int64)
    return out


def tile_candidates():
    ids = {t: [] for t in CANDIDATE_TILES}
    for f in PROTECTED["faces"]:
        if f["sourceTileIndex"] in ids:
            ids[f["sourceTileIndex"]].append(int(f["stagedTriangleIndex"]))
    return ids


def dtm_mesh(points):
    x0, z0, step = float(GRID["x0"]), float(GRID["z0"]), float(GRID["step"])
    ground = GRID["ground"]
    xmin, xmax = float(points[:, 0].min() - 8), float(points[:, 0].max() + 8)
    zmin, zmax = float(points[:, 2].min() - 8), float(points[:, 2].max() + 8)
    c0 = max(0, int(np.floor((xmin - x0) / step)))
    c1 = min(ground.shape[1] - 1, int(np.ceil((xmax - x0) / step)))
    r0 = max(0, int(np.floor((zmin - z0) / step)))
    r1 = min(ground.shape[0] - 1, int(np.ceil((zmax - z0) / step)))
    pos = []
    idx = []
    lookup = {}
    def vertex(r, c):
        key = (r, c)
        if key in lookup:
            return lookup[key]
        y = float(ground[r, c])
        if not np.isfinite(y):
            return -1
        i = len(pos); lookup[key] = i
        pos.append([x0 + (c + .5) * step, y, z0 + (r + .5) * step]); return i
    for r in range(r0, r1):
        for c in range(c0, c1):
            a, b, d, e = vertex(r, c), vertex(r, c + 1), vertex(r + 1, c), vertex(r + 1, c + 1)
            if min(a, b, d, e) >= 0:
                idx.extend([[a, d, b], [b, d, e]])
    return np.asarray(pos, "<f4"), np.asarray(idx, "<u4")


def footprint_lines():
    selected = {"ug-hall-10", "ug-hall-11", "ug-hall-12", "ug-hall-13"}
    lines = []
    for f in FOOTPRINTS:
        if f["catalogId"] not in selected:
            continue
        for part in f["parts"]:
            for ring in part["rings"]:
                for a, b in zip(ring, ring[1:]):
                    xa, za = a; xb, zb = b
                    ya = float(GRID["ground"][np.clip(int((za - GRID["z0"]) / GRID["step"]), 0, GRID["ground"].shape[0]-1), np.clip(int((xa - GRID["x0"]) / GRID["step"]), 0, GRID["ground"].shape[1]-1)])
                    yb = float(GRID["ground"][np.clip(int((zb - GRID["z0"]) / GRID["step"]), 0, GRID["ground"].shape[0]-1), np.clip(int((xb - GRID["x0"]) / GRID["step"]), 0, GRID["ground"].shape[1]-1)])
                    if np.isfinite(ya) and np.isfinite(yb):
                        dx, dz = xb - xa, zb - za
                        length = max((dx * dx + dz * dz) ** .5, 1e-6)
                        px, pz = -dz / length * .18, dx / length * .18
                        lines.extend([[xa - px, ya + .4, za - pz], [xa + px, ya + .4, za + pz],
                                      [xb + px, yb + .4, zb + pz], [xb - px, yb + .4, zb - pz]])
    pos = np.asarray(lines, "<f4"); indices = np.arange(len(pos), dtype="<u4").reshape(-1, 4)
    indices = np.column_stack([indices[:, 0], indices[:, 1], indices[:, 2], indices[:, 0], indices[:, 2], indices[:, 3]])
    return pos, indices


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gltf, binary = read_glb(BASE / "ivillage-x-xiii-v1.glb")
    comps = component_faces()
    all_ids = np.concatenate(list(comps.values()))
    cand = tile_candidates()
    cand_ids = np.concatenate([np.asarray(v, dtype=np.int64) for v in cand.values() if v])
    diagnostic_points = SOURCE_POS[np.concatenate([all_ids, cand_ids])]
    dtm_pos, dtm_idx = dtm_mesh(diagnostic_points)
    add_mesh(gltf, binary, dtm_pos, dtm_idx, [0.08, 0.32, 0.12, .30], name="DTM reference (CEDD ground)")
    for cid, ids in sorted(comps.items()):
        p = SOURCE_POS[ids].reshape(-1, 3)
        add_mesh(gltf, binary, p, np.arange(len(p), dtype="<u4").reshape(-1, 3), COMPONENT_COLOURS[cid], name=f"protected component {cid}")
    if len(cand_ids):
        p = SOURCE_POS[cand_ids].reshape(-1, 3)
        add_mesh(gltf, binary, p, np.arange(len(p), dtype="<u4").reshape(-1, 3), [0.06, .06, .06, .95], name="保守候选 source tiles")
    fp_pos, fp_idx = footprint_lines()
    add_mesh(gltf, binary, fp_pos, fp_idx, [1.0, .48, .02, .95], name="official Hall X-XIII footprint outlines")
    while len(binary) % 4: binary.append(0)
    gltf["buffers"][0]["byteLength"] = len(binary)
    js = json.dumps(gltf, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    raw = struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(binary)) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(binary), b"BIN\0") + binary
    glb = OUT / "protected-review.glb"; glb.write_bytes(raw)
    spec = importlib.util.spec_from_file_location("review_renderer", ROOT / "scripts/render-photo-candidate.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for name, view in [("east", (1, .45, -.8)), ("west", (-1, .45, .8)), ("north", (.2, .75, 1)), ("south", (-.2, .75, -1))]:
        module.render(glb, OUT / f"{name}.png", size=(900, 650), view=view)
    component_report = {}
    for c in REVIEW["components"]:
        cid = int(c["component"]); ids = comps[cid]
        component_report[str(cid)] = {"triangles": int(len(ids)), "colour": COMPONENT_COLOURS[cid],
            "areaSquareMeters": c["areaSquareMeters"], "bounds": c["bounds"],
            "centroidMinusDTM95": c["centroidMinusDTM95"],
            "withheldFromWallAttribution": c["withheldFromWallAttribution"],
            "sourceTileIndices": sorted(set(int(x) for x in STAGE["sourceTileIndex"][ids])),
            "interpretation": "Protected review candidate; this flag does not authorize deletion."}
    candidate_report = {}
    protected_by_tile = {t: [] for t in CANDIDATE_TILES}
    for f in PROTECTED["faces"]:
        if f["sourceTileIndex"] in protected_by_tile:
            protected_by_tile[f["sourceTileIndex"]].append(f)
    for tile, faces in protected_by_tile.items():
        if not faces:
            candidate_report[str(tile)] = {"triangles": 0, "status": "not-in-protected-set"}
            continue
        centers = np.asarray([f["center"] for f in faces]); gaps = np.asarray([f["centroidMinusDTM"] for f in faces])
        candidate_report[str(tile)] = {"triangles": len(faces), "bounds": {"min": centers.min(0).tolist(), "max": centers.max(0).tolist()},
            "dtmGapMeters": {"median": float(np.median(gaps)), "max": float(gaps.max())},
            "sourceId": next(s["id"] for s in json.loads(Path("/tmp/hkust-ivillage-rebuild-source/sources.json").read_text())["sources"] if s["sourceTileIndex"] == tile),
            "status": "conservative-protected-candidate; no deletion evidence"}
    report = {"status": "offline-multiview-review-only", "runtimeRegistration": False,
        "components": component_report, "candidateTiles": candidate_report,
        "dtm": {"source": "/tmp/hkust-ivillage-rebuild-source/roof-grid.npz", "surface": "CEDD ground samples around diagnostic bounds"},
        "officialBoundary": ["ug-hall-10", "ug-hall-11", "ug-hall-12", "ug-hall-13"],
        "images": ["east.png", "west.png", "north.png", "south.png"],
        "limitations": ["The six protected components are conservative non-building candidates and are not deletion approval.", "Footprints are official 2-D base-map drawings; they are not cadastral or as-built shells.", "The historical U57 east screenshot and this offline overlay do not prove what a particular runtime LOD displays.", "No component was registered or deleted from runtime after the safety correction."]}
    (OUT / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "components": {str(k): len(v) for k, v in comps.items()}, "candidateTiles": {str(k): len(v) for k, v in cand.items()}}, ensure_ascii=False))


if __name__ == "__main__": main()
