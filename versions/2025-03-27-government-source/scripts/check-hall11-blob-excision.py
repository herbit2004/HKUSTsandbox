#!/usr/bin/env python3
"""Check exact Hall XI blob face coverage and manifest registration."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "public/models/hires/source-corrections/hall11-source-blob-v1/evidence.json"
RAYS = Path("/tmp/hall11-blob-dense-rays.json")
ID = "hall11-source-blob-v1"


def glb_triangles(path):
    raw = path.read_bytes(); n, kind = struct.unpack_from("<II", raw, 12); assert kind == 0x4E4F534A
    g = json.loads(raw[20:20+n])
    return sum(int(g["accessors"][p["indices"]]["count"]) // 3 for m in g.get("meshes", []) for p in m.get("primitives", []))


def source_topology(path, selected):
    raw = path.read_bytes(); n, kind = struct.unpack_from("<II", raw, 12); assert kind == 0x4E4F534A
    g = json.loads(raw[20:20+n]); b = raw[28+n:]
    dtypes = {5121: "u1", 5123: "<u2", 5125: "<u4"}
    selected_components = []
    retained_shared_vertices = 0
    global_tri = 0
    for mi, mesh in enumerate(g.get("meshes", [])):
        for pi, primitive in enumerate(mesh.get("primitives", [])):
            a = g["accessors"][primitive["indices"]]; v = g["bufferViews"][a["bufferView"]]
            dtype = dtypes[a["componentType"]]; offset = v.get("byteOffset", 0) + a.get("byteOffset", 0)
            indices = np.frombuffer(b, dtype=dtype, count=a["count"], offset=offset).reshape(-1, 3)
            selected_local = {index - global_tri for index in selected if global_tri <= index < global_tri + len(indices)}
            if selected_local:
                retained_local = set(range(len(indices))) - selected_local
                selected_vertices = set(int(x) for x in indices[sorted(selected_local)].ravel())
                retained_vertices = set(int(x) for x in indices[sorted(retained_local)].ravel()) if retained_local else set()
                retained_shared_vertices += len(selected_vertices & retained_vertices)
                by_vertex = {}
                for local in selected_local:
                    for vertex in indices[local]:
                        by_vertex.setdefault(int(vertex), []).append(local)
                seen = set()
                for root in sorted(selected_local):
                    if root in seen: continue
                    stack = [root]; seen.add(root); size = 0
                    while stack:
                        item = stack.pop(); size += 1
                        for vertex in indices[item]:
                            for neighbor in by_vertex[int(vertex)]:
                                if neighbor not in seen:
                                    seen.add(neighbor); stack.append(neighbor)
                    selected_components.append(size)
            global_tri += len(indices)
    return {
        "vertexConnectedComponents": sorted(selected_components, reverse=True),
        "verticesSharedWithRetainedFaces": retained_shared_vertices,
    }


def manifest_hits(value):
    out = []
    if isinstance(value, dict):
        c = value.get("sourceCorrection")
        if isinstance(c, dict) and c.get("id") == ID:
            out.append(c)
        for child in value.values(): out.extend(manifest_hits(child))
    elif isinstance(value, list):
        for child in value: out.extend(manifest_hits(child))
    return out


def main():
    evidence = json.loads(EVIDENCE.read_text())
    selected = {int(x["sourceTileIndex"]): set(x["removedSourceTriangleIndices"]) for x in evidence["sourceTiles"]}
    rays = json.loads(RAYS.read_text())
    before = {(int(h["sourceTileIndex"]), int(h["triangleIndex"]))
              for ray in rays["rays"] for h in ray["sourceBeforeModel"]
              if not h["removed"] and int(h["sourceTileIndex"]) in selected}
    selected_pairs = {(tile, tri) for tile, tris in selected.items() for tri in tris}
    assert before <= selected_pairs, (len(before), len(selected_pairs), sorted(before - selected_pairs)[:5])
    outputs = []
    for item in evidence["sourceTiles"]:
        path = ROOT / Path(item["derived"]).relative_to(ROOT)
        actual = glb_triangles(path)
        assert actual == item["sourceTriangles"] - item["removedTriangles"]
        topology = source_topology(ROOT / item["source"], selected[int(item["sourceTileIndex"])])
        assert topology["verticesSharedWithRetainedFaces"] == 0
        outputs.append({"tile": item["sourceTileIndex"], "sourceTriangles": item["sourceTriangles"], "removed": item["removedTriangles"], "derivedTriangles": actual,
                        "selectedTopology": topology})
    manifests = {}
    for path in [ROOT / "public/models/hires/manifest.json", ROOT / "public/models/hires/partial-residential-ias/manifest.json"]:
        hits = manifest_hits(json.loads(path.read_text())); assert len(hits) == 2
        manifests[str(path.relative_to(ROOT))] = len(hits)
    result = {"status": "pass", "denseRaySeedFaceSet": len(before), "seedFacesCoveredByCompleteIslands": True,
              "removedFacesShareNoSourceVerticesWithRetainedFaces": True, "outputs": outputs, "registeredManifests": manifests,
              "limitations": ["This verifies source-face accounting and complete disconnected topology; runtime screenshots remain a separate acceptance gate."]}
    out = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall11-blob-excision-check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
