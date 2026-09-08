#!/usr/bin/env python3
"""Read-only audit of small connected components in Hall X-XIII preview tiles.

The report is deliberately a candidate inventory. It does not rewrite a GLB,
manifest, mask, or runtime asset. Components are connected only through exact
within-primitive source vertices after the checked-in tile transform; spatial
proximity is never used to join them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "public/models"
FORMS = MODELS / "current-forms/ivillage-rebuild"
DEFAULT_REPORT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-preview-component-candidates-u71.json"
DEFAULT_MD = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-preview-component-candidates-u71.md"
SCOPE = (571.0, -1171.5, 793.5, -1009.0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path) -> tuple[dict, bytes, int]:
    raw = path.read_bytes()
    # These preview GLBs carry an eight-byte JSON length quirk. Locate the BIN
    # marker and decode exactly the JSON payload before it.
    bin_marker = raw.find(b"BIN\x00")
    if bin_marker < 0:
        raise ValueError(f"BIN chunk missing: {path}")
    document = json.JSONDecoder().raw_decode(raw[20 : bin_marker - 4].decode("utf-8").rstrip(" \0"))[0]
    return document, raw, bin_marker + 4


def accessor(document: dict, raw: bytes, bin_start: int, index: int) -> np.ndarray:
    a = document["accessors"][index]
    view = document["bufferViews"][a["bufferView"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dtype = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}[a["componentType"]]
    item = np.dtype(dtype).itemsize
    base = bin_start + view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", item * width)
    return np.ndarray((a["count"], width), dtype=dtype, buffer=raw, offset=base, strides=(stride, item)).copy()


def world_positions(matrix: list[float], positions: np.ndarray) -> np.ndarray:
    homogeneous = np.c_[positions, np.ones(len(positions))]
    affine = np.asarray(matrix, dtype=float).reshape(4, 4, order="F")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        return (homogeneous @ affine.T)[:, :3]


def connected_faces(indices: np.ndarray, positions: np.ndarray) -> list[list[int]]:
    triangles = indices.reshape(-1, 3)
    parent = np.arange(len(positions))
    quantized = np.rint(positions / 1e-6).astype(np.int64)
    buckets: dict[tuple[int, int, int], list[int]] = {}

    def root(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return int(value)

    for index, point in enumerate(quantized):
        buckets.setdefault(tuple(int(x) for x in point), []).append(index)
    for vertices in buckets.values():
        first = root(vertices[0])
        for vertex in vertices[1:]:
            parent[root(vertex)] = first
    groups: dict[int, list[int]] = {}
    for face, triangle in enumerate(triangles):
        groups.setdefault(root(int(triangle[0])), []).append(face)
    return list(groups.values())


def point_in_polygon(x: float, z: float, polygon: list[list[float]]) -> bool:
    inside = False
    for i, point in enumerate(polygon):
        previous = polygon[i - 1]
        if ((point[1] > z) != (previous[1] > z)) and x < (previous[0] - point[0]) * (z - point[1]) / (previous[1] - point[1]) + point[0]:
            inside = not inside
    return inside


def bbox_intersects_polygon(polygon: list[list[float]], lo: np.ndarray, hi: np.ndarray) -> bool:
    if any(lo[0] <= x <= hi[0] and lo[1] <= z <= hi[1] for x, z in polygon):
        return True
    corners = ((lo[0], lo[1]), (lo[0], hi[1]), (hi[0], hi[1]), (hi[0], lo[1]))
    if any(point_in_polygon(x, z, polygon) for x, z in corners):
        return True

    def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def crosses(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
        ab1, ab2 = orientation(a, b, c), orientation(a, b, d)
        cd1, cd2 = orientation(c, d, a), orientation(c, d, b)
        eps = 1e-9
        return ((ab1 > eps and ab2 < -eps) or (ab1 < -eps and ab2 > eps) or abs(ab1) <= eps or abs(ab2) <= eps) and ((cd1 > eps and cd2 < -eps) or (cd1 < -eps and cd2 > eps) or abs(cd1) <= eps or abs(cd2) <= eps)

    box_edges = list(zip(corners, corners[1:] + corners[:1]))
    return any(crosses(tuple(a), tuple(b), tuple(c), tuple(d)) for a, b in zip(polygon, polygon[1:] + polygon[:1]) for c, d in box_edges)


def terrain_height(points: np.ndarray, grid: dict, values: np.ndarray) -> np.ndarray:
    east = grid["origin"]["easting"] + points[:, 0]
    north = grid["origin"]["northing"] - points[:, 2]
    columns = (east - grid["first_easting"]) / grid["easting_step"]
    rows = (north - grid["first_northing"]) / grid["northing_step"]
    output = np.full(len(points), np.nan)
    ncols = int(grid["columns"])
    valid = (rows >= 0) & (rows < grid["rows"] - 1) & (columns >= 0) & (columns < grid["columns"] - 1)
    for i in np.where(valid)[0]:
        row = int(np.floor(rows[i])); column = int(np.floor(columns[i]))
        fr = rows[i] - row; fc = columns[i] - column
        cell = np.array([values[row * ncols + column], values[row * ncols + column + 1], values[(row + 1) * ncols + column], values[(row + 1) * ncols + column + 1]])
        if np.isfinite(cell).all():
            output[i] = cell[0] * (1 - fc) * (1 - fr) + cell[1] * fc * (1 - fr) + cell[2] * (1 - fc) * fr + cell[3] * fc * fr
    return output


def mask_hits(member: dict, pixels: np.ndarray, points: np.ndarray) -> np.ndarray:
    x0, z0 = member["mask"]["boundsXZ"]["min"]
    step = float(member["mask"]["pixelSizeMeters"])
    columns = np.floor((points[:, 0] - x0) / step).astype(int)
    rows = np.floor((points[:, 2] - z0) / step).astype(int)
    valid = (rows >= 0) & (rows < pixels.shape[0]) & (columns >= 0) & (columns < pixels.shape[1])
    output = np.zeros(len(points), dtype=bool)
    alpha = pixels[rows[valid], columns[valid], 3]
    lower = np.where(alpha == 255, float(member["mask"]["replacementMinY"]), np.maximum(float(member["mask"]["replacementMinY"]), alpha))
    output[valid] = (pixels[rows[valid], columns[valid], 0] >= 128) & (points[valid, 1] >= lower) & (points[valid, 1] <= float(member["mask"]["replacementMaxY"]))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    manifest_path = MODELS / "preview-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    form_path = FORMS / "manifest.json"
    form = json.loads(form_path.read_text())
    geometry_path = FORMS / "evidence/geometry.json"
    geometry = json.loads(geometry_path.read_text())
    grid_path = ROOT / "public/terrain/height-grid-5m.json"
    grid = json.loads(grid_path.read_text())
    terrain = np.asarray(grid["heights"], dtype=float)
    masks = [(member, np.asarray(Image.open(FORMS / member["mask"]["url"]).convert("RGBA"))) for member in form["members"]]
    official = [(building["catalogId"], building["envelopeParts"][0]["rings"][0]) for building in geometry["buildings"]]
    selected = []
    for tile_index, tile in enumerate(manifest["tiles"]):
        bounds = tile["bounds"]
        if not (bounds["max"][0] < SCOPE[0] or bounds["min"][0] > SCOPE[2] or bounds["max"][2] < SCOPE[1] or bounds["min"][2] > SCOPE[3]):
            selected.append((tile_index, tile))

    all_components: list[dict] = []
    for tile_index, tile in selected:
        path = MODELS / tile["url"]
        document, raw, bin_start = read_glb(path)
        global_offset = 0
        for mesh_index, mesh in enumerate(document["meshes"]):
            for primitive_index, primitive in enumerate(mesh["primitives"]):
                if primitive.get("mode", 4) != 4:
                    continue
                indices = accessor(document, raw, bin_start, primitive["indices"]).ravel()
                positions = world_positions(tile["matrix"], accessor(document, raw, bin_start, primitive["attributes"]["POSITION"]))
                triangles = indices.reshape(-1, 3)
                for component_index, faces in enumerate(connected_faces(indices, positions)):
                    triangle_positions = positions[triangles[faces]]
                    lo = triangle_positions.min(axis=(0, 1)); hi = triangle_positions.max(axis=(0, 1))
                    if hi[0] < SCOPE[0] or lo[0] > SCOPE[2] or hi[2] < SCOPE[1] or lo[2] > SCOPE[3]:
                        continue
                    centers = triangle_positions.mean(axis=1)
                    component_center = centers.mean(axis=0)
                    areas = np.linalg.norm(np.cross(triangle_positions[:, 1] - triangle_positions[:, 0], triangle_positions[:, 2] - triangle_positions[:, 0]), axis=1) / 2.0
                    gaps = centers[:, 1] - terrain_height(centers, grid, terrain)
                    probes = np.concatenate((centers, triangle_positions.reshape(-1, 3)))
                    current_members = [member["catalogId"] for member, pixels in masks if mask_hits(member, pixels, probes).any()]
                    current_bounds = [member["catalogId"] for member in form["members"] if not (hi[0] < member["bounds"]["min"][0] or lo[0] > member["bounds"]["max"][0] or hi[1] < member["bounds"]["min"][1] or lo[1] > member["bounds"]["max"][1] or hi[2] < member["bounds"]["min"][2] or lo[2] > member["bounds"]["max"][2])]
                    official_intersections = [name for name, polygon in official if bbox_intersects_polygon(polygon, lo[[0, 2]], hi[[0, 2]])]
                    official_centers = [name for name, polygon in official if point_in_polygon(float(component_center[0]), float(component_center[2]), polygon)]
                    finite_gaps = gaps[np.isfinite(gaps)]
                    area = float(areas.sum())
                    median_gap = float(np.nanmedian(gaps)) if len(finite_gaps) else None
                    small = len(faces) <= 120 and area <= 50.0 and float(max(hi[0] - lo[0], hi[2] - lo[2])) <= 8.0 and float(hi[1] - lo[1]) <= 8.0
                    elevated = median_gap is not None and median_gap > 2.0
                    outside_owned_geometry = not current_bounds and not current_members and not official_intersections
                    candidate = small and elevated and outside_owned_geometry
                    reasons = []
                    if current_bounds or current_members: reasons.append("current-form-owned-or-overlapping")
                    if official_intersections: reasons.append("official-building-range-intersection")
                    if not elevated: reasons.append("DTM-compatible-or-no-valid-height")
                    if not small: reasons.append("large-or-non-isolated-component")
                    if candidate: reasons.append("small-isolated-elevated-component-outside-known-building-ranges")
                    all_components.append({
                        "id": f"tile{tile_index}-mesh{mesh_index}-primitive{primitive_index}-component{component_index}",
                        "tileIndex": tile_index, "sourceId": tile["id"], "previewUrl": tile["url"], "tileSha256": tile["sha256"], "sourceSha256": tile.get("sourceSha256"), "previewGlbSha256": sha(path),
                        "meshIndex": mesh_index, "primitiveIndex": primitive_index, "localFaces": [int(x) for x in faces], "globalFaces": [int(global_offset + x) for x in faces],
                        "faceCount": int(len(faces)), "worldBounds": {"min": lo.tolist(), "max": hi.tolist()}, "centroid": component_center.tolist(), "areaSquareMeters": area,
                        "verticalSpanMeters": float(hi[1] - lo[1]), "horizontalSpanMeters": float(max(hi[0] - lo[0], hi[2] - lo[2])),
                        "dtmGapMeters": {"min": float(np.nanmin(gaps)) if len(finite_gaps) else None, "p05": float(np.nanpercentile(gaps, 5)) if len(finite_gaps) else None, "median": median_gap, "p95": float(np.nanpercentile(gaps, 95)) if len(finite_gaps) else None, "max": float(np.nanmax(gaps)) if len(finite_gaps) else None, "validTriangleCount": int(len(finite_gaps))},
                        "currentForm": {"boundsIntersectionMembers": current_bounds, "maskWitnessMembers": current_members},
                        "officialBuildingRange": {"bboxIntersections": official_intersections, "centroidContainment": official_centers},
                        "candidate": candidate, "disposition": "needs-visual-review" if candidate else "must-retain-pending-owner-proof", "safeToDelete": False, "reasons": reasons,
                    })
                global_offset += len(indices) // 3

    candidates = [item for item in all_components if item["candidate"]]
    summary = {
        "status": "audit-complete-no-runtime-write", "task": "G39 Hall X-XIII baseline preview small/isolated component inventory",
        "scope": {"boundsXZ": list(SCOPE), "selection": "preview-manifest tile bounds intersect padded current-form extent", "selectedTileIndices": [i for i, _ in selected]},
        "inputs": {"previewManifest": str(manifest_path), "previewManifestSha256": sha(manifest_path), "currentFormManifest": str(form_path), "currentFormManifestSha256": sha(form_path), "heightGrid": str(grid_path), "heightGridSha256": sha(grid_path), "officialEnvelope": str(geometry_path), "officialEnvelopeSha256": sha(geometry_path)},
        "counts": {"selectedTiles": len(selected), "componentsIntersectingScope": len(all_components), "candidateComponents": len(candidates), "candidateSafeToDelete": 0, "candidateNeedsVisualReview": len(candidates), "mustRetainPendingOwnerProof": len(all_components) - len(candidates)},
        "candidateGate": {"maxFaces": 120, "maxAreaSquareMeters": 50.0, "maxHorizontalSpanMeters": 8.0, "maxVerticalSpanMeters": 8.0, "minimumMedianDtmGapMeters": 2.0, "outsideCurrentForm3DBounds": True, "outsideCurrentFormMaskWitnesses": True, "outsideOfficialBuildingEnvelope": True},
        "policy": ["No source triangle is deleted or rewritten by this audit.", "Exact within-primitive source-vertex connectivity is used; no cross-tile or proximity joins.", "DTM proximity alone cannot distinguish a road, slope, wall, canopy, roof fitting, or remnant.", "Every candidate remains visual-review only until independent multi-angle runtime owner evidence exists."],
        "writes": {"runtimeManifestModified": False, "glbModified": False, "sourceTrianglesDeleted": 0, "buildOrPublish": False}, "candidates": candidates,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Hall X–XIII baseline preview 小型/孤立组件候选（U71）", "", "只读审计；未修改运行时 manifest、GLB、遮罩，也未 build/publish。", "", f"- 选取 baseline manifest 中与 padded 范围相交的瓦片：{len(selected)}（索引 {', '.join(str(i) for i, _ in selected)}）", f"- 范围内组件总数：{len(all_components)}；候选：{len(candidates)}；安全删除：0；需视觉复核：{len(candidates)}", "- 候选门槛：面积 ≤50 m²、面数 ≤120、水平/垂直跨度 ≤8 m、中位 DTM gap >2 m，并且不与 current-form 3D/mask witness 或官方楼域相交。", "", "|候选|瓦片/源 SHA|global faces|世界 bounds (min → max)|面积 m²|DTM gap min/med/max m|current-form / 官方范围|判断|", "|---|---|---:|---|---:|---|---|---|"]
    for item in sorted(candidates, key=lambda x: (-x["dtmGapMeters"]["median"], -x["areaSquareMeters"])):
        b = item["worldBounds"]; g = item["dtmGapMeters"]; faces = item["globalFaces"]
        face_text = ",".join(map(str, faces)) if len(faces) <= 8 else f"{faces[0]}…{faces[-1]} ({len(faces)})"
        lines.append(f"| `{item['id']}`|tile {item['tileIndex']} `{item['tileSha256'][:12]}` / src `{(item['sourceSha256'] or '')[:12]}`|{face_text}|[{b['min'][0]:.2f},{b['min'][1]:.2f},{b['min'][2]:.2f}] → [{b['max'][0]:.2f},{b['max'][1]:.2f},{b['max'][2]:.2f}]|{item['areaSquareMeters']:.3f}|{g['min']:.2f}/{g['median']:.2f}/{g['max']:.2f}|none / none|需视觉复核，安全删除=否|")
    lines += ["", "## 解释边界", "", "这些候选只是几何上小、孤立且高于 DTM 的 source 组件。树冠、道路、坡面、挡土墙、屋面构件和旧摄影残片都可能满足数值门槛；没有独立的多角度运行时射线/截图 owner 证据时，统一保留为需视觉复核。", ""]
    args.markdown.parent.mkdir(parents=True, exist_ok=True); args.markdown.write_text("\n".join(lines))
    print(json.dumps({"report": str(args.report), "markdown": str(args.markdown), "tiles": len(selected), "components": len(all_components), "candidates": len(candidates), "safeToDelete": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
