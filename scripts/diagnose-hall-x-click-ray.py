#!/usr/bin/env python3
"""Read-only exact ray/triangle audit for two Hall X north source tiles.

The GLB source indices are retained so a hit can be assigned to its exact
vertex-connected primitive component.  Manifest matrices are applied in the
same column-major convention used by the runtime.  This script never edits
models, the render manifest, GOAL.md, or a running server.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/models/render-manifest.json"
GRID = ROOT / "public/terrain/height-grid-5m.json"
DEFAULT_OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-north-click-ray-u70.json"

URLS = [
    "glb/12-NW-11A/12-NW-11A-7/Tile_301_142_L16_0.glb",
    "glb/12-NW-11A/12-NW-11A-8/Tile_302_142_L17_001.glb",
]
ORIGIN = np.array([443.061, 157.396, -895.947], dtype=np.float64)
TARGET = np.array([691.297, 143.659, -1122.641], dtype=np.float64)
FOV_DEG = 42.0
VIEWPORT = np.array([1030.996, 1242.988], dtype=np.float64)
CENTER = np.array([515.498, 652.48994], dtype=np.float64)
CLICK = np.array([884.0, 535.0], dtype=np.float64)
UNASSIGNED = np.array([501.3526249035271, 159.46281750603575, -929.071243334053], dtype=np.float64)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accessor(g: dict, binary: memoryview, index: int) -> np.ndarray:
    a = g["accessors"][index]
    view = g["bufferViews"][a["bufferView"]]
    dtype = np.dtype({5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[a["componentType"]])
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    stride = view.get("byteStride", dtype.itemsize * width)
    return np.ndarray(
        (a["count"], width),
        dtype=dtype,
        buffer=binary,
        offset=view.get("byteOffset", 0) + a.get("byteOffset", 0),
        strides=(stride, dtype.itemsize),
    )


def glb_primitives(path: Path, placement: np.ndarray) -> list[dict]:
    raw = path.read_bytes()
    json_len = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20 : 20 + json_len])
    binary = memoryview(raw)[28 + json_len :]
    records: list[dict] = []

    def walk(node_index: int, parent: np.ndarray) -> None:
        node = g["nodes"][node_index]
        local = np.array(node.get("matrix", np.eye(4).flatten(order="F")), dtype=float).reshape(4, 4, order="F")
        transform = parent @ local
        if "mesh" in node:
            for primitive_index, primitive in enumerate(g["meshes"][node["mesh"]]["primitives"]):
                positions = accessor(g, binary, primitive["attributes"]["POSITION"]).astype(float)
                if "indices" in primitive:
                    indices = accessor(g, binary, primitive["indices"]).reshape(-1).astype(np.int64)
                else:
                    indices = np.arange(len(positions), dtype=np.int64)
                indices = indices[: len(indices) // 3 * 3].reshape(-1, 3)
                world_vertices = positions @ (placement @ transform)[:3, :3].T + (placement @ transform)[:3, 3]
                records.append(
                    {
                        "primitiveIndex": primitive_index,
                        "vertices": world_vertices,
                        "indices": indices,
                        "triangles": world_vertices[indices],
                    }
                )
        for child in node.get("children", []):
            walk(child, transform)

    scene = g.get("scene", 0)
    for node_index in g["scenes"][scene]["nodes"]:
        walk(node_index, np.eye(4))
    return records


def ray_direction() -> np.ndarray:
    forward = TARGET - ORIGIN
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    scale = 2.0 * math.tan(math.radians(FOV_DEG / 2.0)) / VIEWPORT[1]
    direction = forward + right * ((CLICK[0] - CENTER[0]) * scale) + up * ((CENTER[1] - CLICK[1]) * scale)
    return direction / np.linalg.norm(direction)


def ray_hits(triangles: np.ndarray, origin: np.ndarray, direction: np.ndarray) -> list[dict]:
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    q = np.cross(np.broadcast_to(direction, e2.shape), e2)
    det = np.einsum("ij,ij->i", e1, q)
    good_det = np.abs(det) > 1e-12
    inv = np.divide(1.0, det, out=np.zeros_like(det), where=good_det)
    tvec = origin - triangles[:, 0]
    bary_u = np.einsum("ij,ij->i", tvec, q) * inv
    r = np.cross(tvec, e1)
    bary_v = r @ direction * inv
    distance = np.einsum("ij,ij->i", e2, r) * inv
    good = good_det & (bary_u >= -1e-9) & (bary_v >= -1e-9) & (bary_u + bary_v <= 1.0 + 1e-9) & (distance > 1e-9)
    ids = np.flatnonzero(good)
    ids = ids[np.argsort(distance[ids])]
    return [{"faceIndex": int(i), "distance": float(distance[i]), "barycentric": [float(1 - bary_u[i] - bary_v[i]), float(bary_u[i]), float(bary_v[i])]} for i in ids]


def point_barycentric(point: np.ndarray, triangle: np.ndarray) -> tuple[np.ndarray, float]:
    mat = np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
    uv, _, _, _ = np.linalg.lstsq(mat, point - triangle[0], rcond=None)
    bary = np.array([1.0 - uv[0] - uv[1], uv[0], uv[1]])
    residual = float(np.linalg.norm(triangle[0] + mat @ uv - point))
    return bary, residual


def triangle_metrics(triangle: np.ndarray) -> dict:
    normal_raw = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    length = float(np.linalg.norm(normal_raw))
    normal = normal_raw / length if length else np.zeros(3)
    area = length / 2.0
    slope = math.degrees(math.acos(min(1.0, abs(float(normal[1])))))
    return {"worldVertices": triangle.tolist(), "areaM2": area, "normal": normal.tolist(), "slopeDeg": slope}


def dtm_sample(point: np.ndarray, grid: dict) -> dict:
    # Grid coordinates are stored in HK80 eastings/northings. Runtime x/z are
    # local offsets: easting = origin.easting + x, northing = origin.northing - z.
    origin = grid["origin"]
    easting = float(origin["easting"] + point[0])
    northing = float(origin["northing"] - point[2])
    first_e = float(grid["first_easting"])
    first_n = float(grid["first_northing"])
    de = float(grid["easting_step"])
    dn = float(grid["northing_step"])
    rows, cols = int(grid["rows"]), int(grid["columns"])
    c = (easting - first_e) / de
    r = (northing - first_n) / dn
    result = {"easting": easting, "northing": northing, "gridColumn": c, "gridRow": r}
    if not (0 <= c < cols - 1 and 0 <= r < rows - 1):
        result.update({"bilinearHeightM": None, "gapM": None, "status": "outside-four-corner-grid"})
        return result
    heights = np.asarray(grid["heights"], dtype=object).reshape(rows, cols)
    c0, r0 = int(math.floor(c)), int(math.floor(r))
    u, v = c - c0, r - r0
    corners = [heights[r0, c0], heights[r0, c0 + 1], heights[r0 + 1, c0], heights[r0 + 1, c0 + 1]]
    if any(x is None for x in corners):
        result.update({"bilinearHeightM": None, "gapM": None, "status": "missing-four-corner-grid"})
        return result
    h = float(corners[0]) * (1 - u) * (1 - v) + float(corners[1]) * u * (1 - v) + float(corners[2]) * (1 - u) * v + float(corners[3]) * u * v
    result.update({"cornerHeightsM": [float(x) for x in corners], "bilinearHeightM": h, "gapM": float(point[1] - h), "status": "bilinear-four-corner"})
    return result


def component_for(records: list[dict], face_index: int) -> tuple[int, list[int], set[int]]:
    # Components are exact primitive-local index connectivity, matching the
    # source mesh topology. No world-space proximity join is performed.
    offset = 0
    for primitive_index, record in enumerate(records):
        count = len(record["indices"])
        if offset <= face_index < offset + count:
            local_face = face_index - offset
            indices = record["indices"]
            face_vertices = set(int(x) for x in indices[local_face])
            connected = {local_face}
            changed = True
            while changed:
                changed = False
                for i, tri_ids in enumerate(indices):
                    if i in connected:
                        continue
                    if face_vertices.intersection(int(x) for x in tri_ids):
                        connected.add(i)
                        face_vertices.update(int(x) for x in tri_ids)
                        changed = True
            return primitive_index, sorted(connected), face_vertices
        offset += count
    raise IndexError(face_index)


def component_metrics(record: dict, faces: list[int], vertex_ids: set[int], grid: dict) -> dict:
    tri = record["triangles"][faces]
    areas = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2.0
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals / np.maximum(lengths[:, None], 1e-30)
    centroid = tri.mean(axis=1).mean(axis=0)
    vertex_array = record["vertices"][sorted(vertex_ids)]
    d = [dtm_sample(p, grid) for p in vertex_array]
    gaps = [x["gapM"] for x in d if x["gapM"] is not None]
    mean_normal = (normals * areas[:, None]).sum(axis=0)
    mean_normal /= max(float(np.linalg.norm(mean_normal)), 1e-30)
    return {
        "faceCount": len(faces),
        "faceIndices": faces,
        "sourceVertexCount": len(vertex_ids),
        "sourceVertexIndices": sorted(vertex_ids),
        "worldBounds": {"min": vertex_array.min(axis=0).tolist(), "max": vertex_array.max(axis=0).tolist()},
        "surfaceAreaM2": float(areas.sum()),
        "normalMean": mean_normal.tolist(),
        "normalYAbsAreaFraction": float(np.sum(areas * np.abs(normals[:, 1])) / max(float(areas.sum()), 1e-30)),
        "slopeDegMin": float(np.degrees(np.arccos(np.clip(np.abs(normals[:, 1]), 0, 1))).min()),
        "slopeDegMax": float(np.degrees(np.arccos(np.clip(np.abs(normals[:, 1]), 0, 1))).max()),
        "centroid": centroid.tolist(),
        "centroidDTM": dtm_sample(centroid, grid),
        "vertexDTMGapM": {"min": min(gaps) if gaps else None, "max": max(gaps) if gaps else None, "mean": float(np.mean(gaps)) if gaps else None},
        "topologyDefinition": "same primitive and shared original POSITION index; no spatial proximity or cross-tile joins",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    entries = {entry["url"]: entry for entry in manifest["tiles"] if entry.get("url") in URLS}
    grid = json.loads(GRID.read_text())
    direction = ray_direction()
    ray = {"origin": ORIGIN.tolist(), "target": TARGET.tolist(), "direction": direction.tolist(), "fovDeg": FOV_DEG, "viewportWidth": float(VIEWPORT[0]), "viewportHeight": float(VIEWPORT[1]), "center": CENTER.tolist(), "click": CLICK.tolist(), "construction": "forward + right*((clickX-centerX)*2*tan(fov/2)/viewportHeight) + up*((centerY-clickY)*scale), normalized"}
    tile_reports = []
    reverse_reports = []
    for url in URLS:
        entry = entries[url]
        path = ROOT / "public/models" / url
        placement = np.array(entry["matrix"], dtype=float).reshape(4, 4, order="F")
        records = glb_primitives(path, placement)
        triangles = np.concatenate([r["triangles"] for r in records])
        hits = ray_hits(triangles, ORIGIN, direction)
        for h in hits:
            h["hitPoint"] = (ORIGIN + direction * h["distance"]).tolist()
            h["primitiveIndex"] = next(i for i, r in enumerate(records) if h["faceIndex"] < sum(len(x["indices"]) for x in records[: i + 1]))
            previous = sum(len(x["indices"]) for x in records[: h["primitiveIndex"]])
            h["primitiveFaceIndex"] = h["faceIndex"] - previous
            h["metrics"] = triangle_metrics(triangles[h["faceIndex"]])
            h["dtm"] = dtm_sample(np.array(h["hitPoint"]), grid)
            prim, faces, vertices = component_for(records, h["faceIndex"])
            h["component"] = component_metrics(records[prim], faces, vertices, grid)
            # Preserve exact index witness for the picked face.
            h["sourceVertexIndices"] = records[prim]["indices"][h["primitiveFaceIndex"]].tolist()
        reverse = []
        for prim_index, record in enumerate(records):
            for face_index, triangle in enumerate(record["triangles"]):
                bary, residual = point_barycentric(UNASSIGNED, triangle)
                if np.all(bary >= -1e-7) and np.all(bary <= 1 + 1e-7):
                    reverse.append({"primitiveIndex": prim_index, "primitiveFaceIndex": face_index, "barycentric": bary.tolist(), "planeResidualM": residual, "metrics": triangle_metrics(triangle), "dtm": dtm_sample(UNASSIGNED, grid)})
        reverse.sort(key=lambda x: x["planeResidualM"])
        empirical = [x for x in reverse if x["planeResidualM"] <= 1e-3]
        reverse_reports.append({"url": url, "point": UNASSIGNED.tolist(), "containingTriangles": reverse[:12], "containingTriangleCount": len(reverse), "empiricalContainmentCountResidualLE1mm": len(empirical), "interpretation": "Barycentric inclusion alone is a projection candidate; empirical containment additionally requires a 3D plane residual <= 1 mm."})
        tile_reports.append({"url": url, "path": str(path.relative_to(ROOT)), "sha256": digest(path), "manifest": {"id": entry["id"], "matrix": entry["matrix"], "bounds": entry["bounds"], "triangles": entry["triangles"], "vertices": entry["vertices"], "affineApproximationMaxErrorMeters": entry.get("affineApproximationMaxErrorMeters")}, "primitiveCount": len(records), "primitiveFaceCounts": [int(len(r["indices"])) for r in records], "rayHitCount": len(hits), "rayHitsNearestFirst": hits[:12], "rayInterpretation": "The first hit is the nearest exact source triangle for this constructed ray, subject only to the checked-in candidate tiles.", "unassignedReverseLookup": reverse_reports[-1]})
    result = {"status": "read-only-diagnostic-complete", "checkedAt": "2026-09-07", "inputs": {"manifest": str(MANIFEST.relative_to(ROOT)), "manifestSha256": digest(MANIFEST), "heightGrid": str(GRID.relative_to(ROOT)), "heightGridSha256": digest(GRID), "candidateUrls": URLS}, "ray": ray, "unassignedPoint": UNASSIGNED.tolist(), "tiles": tile_reports, "reverseLookup": reverse_reports, "judgment": {"safeIndependentFloatingMesh": False, "reason": "Exact ray hits and source-index components are evidence of geometry ownership, but deletion is unsafe unless the component is demonstrably isolated from terrain/retaining-wall/tree-canopy/current-form domains. This diagnostic alone does not establish that positive chain.", "empirical": ["GLB bytes, manifest matrix, ray intersections, source-index connectivity, world metrics, and grid samples"], "inference": ["pixel-to-world correspondence follows the supplied camera convention; any deletion classification beyond the measured geometry requires scene ownership and visual/context evidence"]}, "writes": {"productionManifestChanged": False, "productionModelsChanged": False, "goalChanged": False, "serverPublished": False}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for tile in tile_reports:
        nearest = tile["rayHitsNearestFirst"][0] if tile["rayHitsNearestFirst"] else None
        print(json.dumps({"url": tile["url"], "rayHitCount": tile["rayHitCount"], "nearest": None if nearest is None else {"face": nearest["faceIndex"], "distance": nearest["distance"], "point": nearest["hitPoint"], "componentFaces": nearest["component"]["faceCount"]}, "unassignedContains": tile["unassignedReverseLookup"]["containingTriangleCount"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
