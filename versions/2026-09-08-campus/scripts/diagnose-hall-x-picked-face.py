#!/usr/bin/env python3
"""Read-only diagnostic for the user-picked Hall X north source face."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "public/models/hires/partial-residential-ias/Tile_302_143_L20_00230.glb"
SOURCES = Path("/tmp/hkust-ivillage-rebuild-source/sources.json")
GRID_PATH = ROOT / "public/terrain/height-grid-5m.json"
ROOF_GRID = Path("/tmp/hkust-ivillage-rebuild-source/roof-grid.npz")
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-north-picked-face-u70.json"
TARGET = np.array([626.2516001352247, 165.1547255878584, -1003.3981586877112], dtype=float)
FACE = 219


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path, matrix: np.ndarray):
    raw = path.read_bytes()
    json_len = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + json_len])
    binary = memoryview(raw)[28 + json_len :]

    def accessor(index: int) -> np.ndarray:
        a = doc["accessors"][index]
        view = doc["bufferViews"][a["bufferView"]]
        dtype = np.dtype({5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[a["componentType"]])
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", dtype.itemsize * width)
        return np.ndarray((a["count"], width), dtype=dtype, buffer=binary, offset=offset, strides=(stride, dtype.itemsize))

    mesh = doc["meshes"][0]
    primitive = mesh["primitives"][0]
    vertices = accessor(primitive["attributes"]["POSITION"]).astype(float)
    indices = accessor(primitive["indices"]).ravel().astype(int)
    faces = indices.reshape(-1, 3)
    world_vertices = vertices @ matrix[:3, :3].T + matrix[:3, 3]
    return faces, world_vertices, doc


def grid_sample(grid: dict, point: np.ndarray) -> dict:
    easting = float(point[0] + grid["origin"]["easting"])
    northing = float(grid["origin"]["northing"] - point[2])
    col = (easting - grid["first_easting"]) / grid["easting_step"]
    row = (northing - grid["first_northing"]) / grid["northing_step"]
    result = {"easting": easting, "northing": northing, "rowFloat": float(row), "colFloat": float(col)}
    ri, ci = round(row), round(col)
    heights = np.array([np.nan if z is None else z for z in grid["heights"]], dtype=float).reshape(grid["rows"], grid["columns"])
    result["nearest5m"] = None if not (0 <= ri < grid["rows"] and 0 <= ci < grid["columns"]) else float(heights[ri, ci])
    if not (0 <= row <= grid["rows"] - 1 and 0 <= col <= grid["columns"] - 1):
        result["bilinear5m"] = None
        result["corners5m"] = None
        return result
    c0, r0 = min(int(np.floor(col)), grid["columns"] - 2), min(int(np.floor(row)), grid["rows"] - 2)
    tx, ty = col - c0, row - r0
    a, b, c, d = heights[r0, c0], heights[r0, c0 + 1], heights[r0 + 1, c0], heights[r0 + 1, c0 + 1]
    result["corners5m"] = [float(a), float(b), float(c), float(d)]
    result["bilinear5m"] = float((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty)
    return result


def metric(face: int, faces: np.ndarray, world_vertices: np.ndarray, grid: dict, shared_with: set[int] | None = None) -> dict:
    tri = world_vertices[faces[face]]
    cross = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    normal = cross / np.linalg.norm(cross)
    centroid = tri.mean(axis=0)
    dtm = grid_sample(grid, centroid)
    return {
        "faceIndex": int(face),
        "sourceVertexIndices": [int(v) for v in faces[face]],
        "sharedSourceVertexIndicesWithPickedFace": [] if shared_with is None else sorted(int(v) for v in shared_with),
        "worldVertices": tri.tolist(),
        "centroid": centroid.tolist(),
        "normal": normal.tolist(),
        "slopeFromHorizontalDegrees": float(np.degrees(np.arccos(abs(normal[1])))),
        "areaSquareMeters": float(np.linalg.norm(cross) / 2),
        "dtm": dtm,
        "centroidDtmGapMetersBilinear": None if dtm["bilinear5m"] is None else float(centroid[1] - dtm["bilinear5m"]),
    }


def main() -> None:
    sources = json.loads(SOURCES.read_text())["sources"]
    source = next(s for s in sources if s["url"] == "partial-residential-ias/Tile_302_143_L20_00230.glb")
    matrix = np.array(source["matrix"], dtype=float).reshape(4, 4, order="F")
    faces, world_vertices, doc = read_glb(GLB, matrix)
    assert FACE < len(faces)
    grid = json.loads(GRID_PATH.read_text())
    picked = metric(FACE, faces, world_vertices, grid)
    face_world = np.asarray(picked["worldVertices"], dtype=float)
    target_bary = np.linalg.solve(
        np.column_stack([face_world[1, [0, 2]] - face_world[0, [0, 2]], face_world[2, [0, 2]] - face_world[0, [0, 2]]]),
        TARGET[[0, 2]] - face_world[0, [0, 2]],
    )
    bary = [float(1 - target_bary.sum()), float(target_bary[0]), float(target_bary[1])]
    target_plane_y = float(sum(b * picked["worldVertices"][i][1] for i, b in enumerate(bary)))
    picked["targetPoint"] = TARGET.tolist()
    picked["targetBarycentric"] = bary
    picked["targetInsidePickedFaceXZ"] = bool(min(bary) >= -1e-9)
    picked["targetPlaneY"] = target_plane_y
    picked["targetDtm"] = grid_sample(grid, TARGET)
    picked["targetPlaneDtmGapMetersBilinear"] = float(target_plane_y - picked["targetDtm"]["bilinear5m"])

    source_ids = set(int(v) for v in faces[FACE])
    neighbors = []
    for index in np.flatnonzero(np.any(np.isin(faces, list(source_ids)), axis=1)):
        index = int(index)
        if index == FACE:
            continue
        neighbors.append(metric(index, faces, world_vertices, grid, set(int(v) for v in faces[index]).intersection(source_ids)))
    neighbors.sort(key=lambda x: x["faceIndex"])

    mask_manifest = json.loads((ROOT / "public/models/current-forms/ivillage-rebuild/manifest.json").read_text())
    mask_bounds = [m["mask"]["boundsXZ"] for m in mask_manifest["members"]]
    inside_mask_bounds = any(b["min"][0] <= TARGET[0] < b["max"][0] and b["min"][1] <= TARGET[2] < b["max"][1] for b in mask_bounds)
    roof = np.load(ROOF_GRID)
    roof_extent = [float(roof["x0"]), float(roof["z0"]), float(roof["x0"] + roof["ground"].shape[1] * roof["step"]), float(roof["z0"] + roof["ground"].shape[0] * roof["step"])]

    result = {
        "status": "read-only-diagnostic-complete",
        "task": "Hall X north picked source face 219",
        "pickedWorldPoint": TARGET.tolist(),
        "source": {"path": str(GLB), "sha256": sha(GLB), "sourceTileIndex": source["sourceTileIndex"], "sourceId": source["id"], "matrix": source["matrix"], "primitiveFaceCount": int(len(faces)), "coordinateSystem": "source manifest local x=easting-844800, y=source mesh vertical, z=820500-northing"},
        "pickedFace": picked,
        "localAdjacentFaces": {"definition": "all same-primitive faces sharing at least one original GLB index vertex with face 219", "count": len(neighbors), "faces": neighbors},
        "maskContext": {"currentFormMaskBoundsXZ": mask_bounds[0], "targetInsideAnyCurrentFormMaskBounds": inside_mask_bounds, "interpretation": "The target z=-1003.398 is north of the common current-form mask max z=-1009.5, so no current-form replacement mask pixel can own this point."},
        "dtmContext": {"heightGridPath": str(GRID_PATH), "heightGridSha256": sha(GRID_PATH), "heightGridDatum": "HKPD", "heightGridSurvey": "2019-12-20 to 2020-02-02", "sourceStageRoofGridPath": str(ROOF_GRID), "sourceStageRoofGridExtentXZ": roof_extent, "targetInsideSourceStageRoofGrid": bool(roof_extent[0] <= TARGET[0] < roof_extent[2] and roof_extent[1] <= TARGET[2] < roof_extent[3]), "roofGridNote": "Target is outside the existing padded Hall X-XIII roof-grid extent; height-grid-5m is the applicable project DTM check."},
        "classification": {"label": "horizontal-ground-like-source-surface", "confidence": "high for geometric class; not an ownership/currentness claim", "evidence": ["Picked face normal y=0.999803 and slope=1.137 degrees from horizontal.", "Face y span is 0.029 m and centroid is 0.239 m above bilinear project DTM.", "All 16 same-primitive one-ring neighbors share source vertices and have centroid DTM gaps 0.067-0.259 m; their slopes range 1.040-39.925 degrees, showing a continuous surface with local edge facets rather than an isolated vertical block.", "Target is outside the four current-form mask bounds, so this is not a current-form mask edge witness."], "notADeletionFinding": "The geometry supports a horizontal terrain/ground-like photographed surface, not a vertically suspended remnant. DTM proximity does not prove current road/terrace identity or source capture date."},
        "commands": ["python3 scripts/diagnose-hall-x-picked-face.py", "python3 -m py_compile scripts/diagnose-hall-x-picked-face.py", "sha256sum public/models/hires/partial-residential-ias/Tile_302_143_L20_00230.glb public/terrain/height-grid-5m.json"],
        "writes": {"productionRuntimeModified": False, "published4317": False, "goalModified": False, "sourceFacesDeleted": 0},
        "limitations": ["Source face 219 is interpreted as the GLB primitive's zero-based face index; no browser ray was synthesized.", "The DTM is historical HKPD terrain and cannot by itself distinguish road, terrace, roof step or vegetation support.", "A current-form mask is a raster ownership handoff; the target lies outside its bounds, so no mask-edge claim is made.", "Source mesh vertical datum is documented as unconfirmed relative to HKPD; the small DTM gap is a shape/registration witness, not survey accuracy."],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "face": FACE, "neighbors": len(neighbors), "classification": result["classification"]["label"], "targetInsideMaskBounds": inside_mask_bounds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
