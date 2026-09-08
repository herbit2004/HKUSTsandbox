#!/usr/bin/env python3
"""Expand runtime ray hits into complete per-primitive source mesh closures."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import glb_source_correction as glb

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads(Path("/tmp/hkust-ivillage-rebuild-source/sources.json").read_text())["sources"]


def world_bounds(positions, vertex_ids, matrix_values):
    matrix = np.asarray(matrix_values, dtype=float).reshape(4, 4).T
    local = positions[np.asarray(sorted(vertex_ids), dtype=int)]
    world = np.c_[local, np.ones(len(local))] @ matrix.T
    world = world[:, :3]
    low, high = world.min(axis=0), world.max(axis=0)
    return {
        "min": low.tolist(),
        "max": high.tolist(),
        "size": (high - low).tolist(),
        "centroid": world.mean(axis=0).tolist(),
    }


def closures(tile_index, seeds, seed_pixels):
    meta = SOURCES[tile_index]
    source = Path(meta["localPath"])
    assert source.exists() and glb.sha(source) == meta["sha256"]
    _, data, binary = glb.read_glb(source)
    reports = []
    global_start = 0
    for mesh_index, mesh in enumerate(data["meshes"]):
        for primitive_index, primitive in enumerate(mesh["primitives"]):
            indices = glb.accessor(data, binary, primitive["indices"]).reshape(-1, 3).astype(int)
            local_seeds = {seed - global_start for seed in seeds if global_start <= seed < global_start + len(indices)}
            if not local_seeds:
                global_start += len(indices)
                continue
            by_vertex = defaultdict(list)
            for face_index, face in enumerate(indices):
                for vertex in face:
                    by_vertex[int(vertex)].append(face_index)
            assigned = set()
            positions = glb.accessor(data, binary, primitive["attributes"]["POSITION"]).astype(float)
            for seed in sorted(local_seeds):
                if seed in assigned:
                    continue
                component = set([seed])
                stack = [seed]
                while stack:
                    face_index = stack.pop()
                    for vertex in indices[face_index]:
                        for neighbor in by_vertex[int(vertex)]:
                            if neighbor not in component:
                                component.add(neighbor)
                                stack.append(neighbor)
                component_seeds = component & local_seeds
                assigned.update(component_seeds)
                global_faces = sorted(global_start + face for face in component)
                global_seeds = sorted(global_start + face for face in component_seeds)
                vertices = set(map(int, np.unique(indices[list(component)]).tolist()))
                outside = set(range(len(indices))) - component
                outside_vertices = set(map(int, np.unique(indices[list(outside)]).tolist())) if outside else set()
                reports.append({
                    "componentId": f"tile{tile_index}-mesh{mesh_index}-primitive{primitive_index}-closure{len(reports)}",
                    "meshIndex": mesh_index,
                    "primitiveIndex": primitive_index,
                    "globalTriangleStart": global_start,
                    "faceCount": len(global_faces),
                    "faces": global_faces,
                    "seedFaces": global_seeds,
                    "seedPixels": sorted({tuple(pixel) for face in global_seeds for pixel in seed_pixels[face]}),
                    "worldBounds": world_bounds(positions, vertices, meta["matrix"]),
                    "sharesVertexWithRetainedFaces": bool(vertices & outside_vertices),
                })
            global_start += len(indices)
    assert seeds == {face for report in reports for face in report["seedFaces"]}
    return {
        "sourceTileIndex": tile_index,
        "sourceId": meta["id"],
        "url": meta["url"],
        "localPath": meta["localPath"],
        "sourceSha256": meta["sha256"],
        "seedFaceCount": len(seeds),
        "components": reports,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rays", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roi", type=json.loads, required=True, help="[x0,x1,y0,y1], inclusive")
    parser.add_argument("--tiles", type=json.loads, required=True)
    args = parser.parse_args()
    ray_data = json.loads(args.rays.read_text())
    x0, x1, y0, y1 = map(int, args.roi)
    wanted = set(map(int, args.tiles))
    by_tile = defaultdict(set)
    seed_pixels = defaultdict(lambda: defaultdict(list))
    considered = 0
    for ray in ray_data["rays"]:
        x, y = ray["pixel"]
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        considered += 1
        visible = [hit for hit in ray["sourceBeforeModel"] if not hit["removed"] and int(hit["sourceTileIndex"]) in wanted]
        if not visible:
            continue
        hit = visible[0]
        tile_index, face = int(hit["sourceTileIndex"]), int(hit["triangleIndex"])
        by_tile[tile_index].add(face)
        seed_pixels[tile_index][face].append([x, y])
    result = {
        "status": "runtime-ray-topology-report",
        "rayEvidence": str(args.rays),
        "roi": [x0, x1, y0, y1],
        "tilesRequested": sorted(wanted),
        "raysConsidered": considered,
        "selection": "Nearest visible-unremoved source hit in the requested source tiles for each sampled ROI pixel.",
        "connectivity": "Complete vertex-connected closure inside the same GLB primitive; no height, AABB or whole-tile inference.",
        "tiles": [closures(tile, seeds, seed_pixels[tile]) for tile, seeds in sorted(by_tile.items())],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "tiles": [{"sourceTileIndex": tile["sourceTileIndex"], "seeds": tile["seedFaceCount"], "components": [{"id": component["componentId"], "faces": component["faceCount"], "bounds": component["worldBounds"]} for component in tile["components"]]} for tile in result["tiles"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
