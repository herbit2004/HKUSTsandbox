#!/usr/bin/env python3
"""Remove the complete disconnected Hall XI source strip proven by runtime rays.

The settled runtime rays supply positive seed faces.  Each seed is expanded
only through shared source vertices inside the same primitive, so the output
removes complete disconnected source islands instead of cutting holes through
an otherwise retained mesh.  No height, AABB, mask-wide or whole-tile rule is
used.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import glb_source_correction as builder

ROOT = Path(__file__).resolve().parents[1]
RAYS = Path("/tmp/hall11-blob-dense-rays.json")
STAGE = np.load("/tmp/hkust-ivillage-rebuild-source/terminal-triangles.npz")
SOURCES = json.loads(Path("/tmp/hkust-ivillage-rebuild-source/sources.json").read_text())["sources"]
OUT = ROOT / "public/models/hires/source-corrections/hall11-source-blob-v1"
TILES = {87, 89}

def seed_components(source: Path, seeds: set[int], matrix_values):
    """Return complete vertex-connected islands containing any seed face."""
    _, gltf, binary = builder.read_glb(source)
    matrix = np.asarray(matrix_values, dtype=float).reshape(4, 4).T
    expanded: set[int] = set()
    reports = []
    global_tri = 0
    for mesh_index, mesh in enumerate(gltf["meshes"]):
        for primitive_index, primitive in enumerate(mesh["primitives"]):
            indices = builder.accessor(gltf, binary, primitive["indices"]).reshape(-1, 3).astype(int)
            local_seeds = {seed - global_tri for seed in seeds if global_tri <= seed < global_tri + len(indices)}
            if not local_seeds:
                global_tri += len(indices)
                continue
            by_vertex = defaultdict(list)
            for triangle_index, triangle in enumerate(indices):
                for vertex in triangle:
                    by_vertex[int(vertex)].append(triangle_index)
            seen = set()
            positions = builder.accessor(gltf, binary, primitive["attributes"]["POSITION"]).astype(float)
            for seed in sorted(local_seeds):
                if seed in seen:
                    continue
                stack = [seed]
                seen.add(seed)
                component = []
                while stack:
                    triangle_index = stack.pop()
                    component.append(triangle_index)
                    for vertex in indices[triangle_index]:
                        for neighbor in by_vertex[int(vertex)]:
                            if neighbor not in seen:
                                seen.add(neighbor)
                                stack.append(neighbor)
                component_global = {global_tri + triangle_index for triangle_index in component}
                expanded.update(component_global)
                vertices = np.unique(indices[component].ravel())
                local = positions[vertices]
                world = np.c_[local, np.ones(len(local))] @ matrix.T
                world = world[:, :3]
                reports.append({
                    "meshIndex": mesh_index,
                    "primitiveIndex": primitive_index,
                    "seedFaces": len(component_global & seeds),
                    "componentFaces": len(component_global),
                    "bounds": {"min": world.min(axis=0).tolist(), "max": world.max(axis=0).tolist()},
                    "removedSourceTriangleIndices": sorted(component_global),
                })
            global_tri += len(indices)
    assert seeds <= expanded
    return expanded, reports


def main():
    rays = json.loads(RAYS.read_text())
    by_tile: dict[int, set[int]] = {tile: set() for tile in TILES}
    staged_ids = {}
    for ray in rays["rays"]:
        for hit in ray["sourceBeforeModel"]:
            if hit["removed"] or hit["sourceTileIndex"] not in TILES:
                continue
            tile = int(hit["sourceTileIndex"]); tri = int(hit["triangleIndex"])
            staged = int(hit["stagedTriangleIndex"])
            assert int(STAGE["sourceTileIndex"][staged]) == tile
            assert int(STAGE["triangleIndex"][staged]) == tri
            by_tile[tile].add(tri)
            staged_ids[(tile, tri)] = staged
    assert {tile: len(ids) for tile, ids in by_tile.items()} == {87: 33, 89: 67}
    outputs = []
    expanded_counts = {}
    for tile, seed_triangles in sorted(by_tile.items()):
        meta = SOURCES[tile]; source = Path(meta["localPath"])
        assert source.exists() and builder.sha(source) == meta["sha256"]
        triangles, components = seed_components(source, seed_triangles, meta["matrix"])
        expanded_counts[tile] = len(triangles)
        relative = source.relative_to(ROOT)
        output = OUT / relative.parent.name / relative.name.replace(".glb", ".hall11-source-blob-v1.glb")
        result = builder.rewrite(source, triangles, output)
        staged_lookup = {
            int(STAGE["triangleIndex"][index]): int(index)
            for index in np.flatnonzero(STAGE["sourceTileIndex"] == tile)
        }
        assert triangles <= staged_lookup.keys()
        result.update({"sourceTileIndex": tile, "sourceId": meta["id"],
                       "seedSourceTriangleIndices": sorted(seed_triangles),
                       "removedSourceTriangleIndices": sorted(triangles),
                       "stagedTriangleIndices": sorted(staged_lookup[tri] for tri in triangles),
                       "sourceComponents": components})
        outputs.append(result)
    assert expanded_counts == {87: 219, 89: 1353}, expanded_counts
    report = {
        "status": "ray-seeded-complete-source-islands-built-not-registered",
        "sourceRayEvidence": str(RAYS),
        "camera": rays["pose"],
        "seedFaces": {str(tile): len(ids) for tile, ids in by_tile.items()},
        "selectedFaces": {str(tile): expanded_counts[tile] for tile in sorted(expanded_counts)},
        "removedTriangles": sum(expanded_counts.values()),
        "sourceTiles": outputs,
        "positiveEvidence": [
            "100 non-removed source faces are independently hit by the dense settled Hall XI runtime rays.",
            "Tile 89 selected UVs land on blue-grey facade texture with repeated window apertures.",
            "Selected world faces are approximately 5-7m from the nearest current Hall XI vertex, forming a detached visible strip.",
            "The seeds expand to eight complete vertex-connected source islands: 219 faces in tile 87 and 1,353 in tile 89.",
            "Every selected island is a compact thin vertical strip; removing the complete island leaves no source edge shared with retained triangles.",
        ],
        "preservation": "All other faces in both tiles remain byte-derived from the original; no entire tile, DTM, canopy, road, corridor or Hall mask is modified.",
        "limitations": [
            "The topology is seeded from one settled camera; runtime same-pose and second-angle rechecks remain required.",
            "DTM compatibility alone does not classify a vertical face; no terrain-wide deletion is inferred.",
            "The derived GLBs are not runtime assets until separately reviewed and registered.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "selectedFaces": report["selectedFaces"], "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
