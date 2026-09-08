#!/usr/bin/env python3
"""Ray-audit an iVillage screenshot ROI against exact staged source triangles.

This is a diagnostic only. It keeps current-form occlusion, registered source
corrections and the current rebuilt Hall mesh in the visibility test, then
groups nearest visible source hits by the full source connected component from
the whole-neighborhood audit. It never rewrites a GLB or manifest.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from hkust_source_geometry import geometry


ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/tmp/hkust-ivillage-rebuild-source")
FORMS = ROOT / "public/models/current-forms/ivillage-rebuild"
DEFAULT_POSE = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-west-live-pose-u70.json"
DEFAULT_COMPONENTS = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.json"
DEFAULT_OUTPUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-west-live-rays-u70.json"


def prepare_rays(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cache invariant triangle edges once for a whole screenshot audit."""
    return triangles, triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]


def ray_hits(prepared: tuple[np.ndarray, np.ndarray, np.ndarray], origin: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    triangles, edge1, edge2 = prepared
    q = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
    determinant = np.einsum("ij,ij->i", edge1, q)
    inverse = np.divide(1, determinant, out=np.zeros_like(determinant), where=np.abs(determinant) > 1e-10)
    tvec = origin - triangles[:, 0]
    u = np.einsum("ij,ij->i", tvec, q) * inverse
    r = np.cross(tvec, edge1)
    v = r @ direction * inverse
    distance = np.einsum("ij,ij->i", edge2, r) * inverse
    found = np.flatnonzero((np.abs(determinant) > 1e-10) & (u >= 0) & (v >= 0) & (u + v <= 1) & (distance > 0))
    order = np.argsort(distance[found])
    return found[order], distance[found][order]


def sample(descriptor: dict, pixels: np.ndarray, point: np.ndarray) -> np.ndarray | None:
    x, z = point[0], point[2]
    left, top = descriptor["boundsXZ"]["min"]
    right, bottom = descriptor["boundsXZ"]["max"]
    if not left <= x < right or not top <= z < bottom:
        return None
    return pixels[
        int((z - top) / descriptor["pixelSizeMeters"]),
        int((x - left) / descriptor["pixelSizeMeters"]),
    ]


def registered_corrections() -> set[tuple[int, int]]:
    removed: set[tuple[int, int]] = set()
    for evidence in (ROOT / "public/models/hires/source-corrections").glob("*/evidence.json"):
        value = json.loads(evidence.read_text())
        for tile in value.get("sourceTiles", []):
            source_tile = tile.get("sourceTileIndex")
            if source_tile is None:
                continue
            removed.update((int(source_tile), int(face)) for face in tile.get("removedSourceTriangleIndices", []))
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pose", type=Path, default=DEFAULT_POSE)
    parser.add_argument("--components", type=Path, default=DEFAULT_COMPONENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    pose = json.loads(args.pose.read_text())
    staged = np.load(STAGE / "terminal-triangles.npz")
    source = staged["positions"]
    source_normals = staged["normals"]
    source_tiles = staged["sourceTileIndex"].astype(int)
    source_faces = staged["triangleIndex"].astype(int)
    source_meta = json.loads((STAGE / "sources.json").read_text())["sources"]

    manifest = json.loads((FORMS / "manifest.json").read_text())
    masks = [
        (member["mask"], np.asarray(Image.open(FORMS / member["mask"]["url"]).convert("RGBA")))
        for member in manifest["members"]
    ]
    protection_descriptor = manifest["sourceProtection"]
    protection = np.frombuffer(
        (FORMS / protection_descriptor["url"]).read_bytes(), np.uint8
    ).reshape(protection_descriptor["height"], protection_descriptor["width"], 4)

    rebuilt, _ = geometry(FORMS / "ivillage-x-xiii-v1.glb")
    removed = registered_corrections()
    source_rays = prepare_rays(source)
    rebuilt_rays = prepare_rays(rebuilt)
    components = json.loads(args.components.read_text())
    component_by_pair: dict[tuple[int, int], str] = {}
    component_record: dict[str, dict] = {}
    for component in components["components"]:
        component_record[component["id"]] = component
        for face in component["scopedTriangleIndices"]:
            component_by_pair[(int(component["sourceTileIndex"]), int(face))] = component["id"]

    def discarded(index: int, point: np.ndarray) -> bool:
        pair = (int(source_tiles[index]), int(source_faces[index]))
        if pair in removed:
            return True
        protected = sample(protection_descriptor, protection, point)
        if protected is not None and protected[0]:
            reference = int(protected[0]) + int(protected[1]) / 256
            if abs(point[1] - reference) <= protection_descriptor["groundBandMeters"] and abs(source_normals[index, 1]) >= 0.6:
                return False
        for descriptor, pixels in masks:
            value = sample(descriptor, pixels, point)
            if value is None or value[0] < 128:
                continue
            lower = descriptor["replacementMinY"] if value[3] == 255 else max(descriptor["replacementMinY"], int(value[3]))
            if lower <= point[1] <= descriptor["replacementMaxY"]:
                return True
        return False

    origin = np.asarray(pose["camera"], dtype=float)
    target = np.asarray(pose["lookTarget"], dtype=float)
    forward = target - origin
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    center_x, center_y = pose["viewport"]["targetPixel"]
    scale = 2 * np.tan(np.deg2rad(pose["fovDegrees"] / 2)) / pose["viewport"]["height"]
    roi = pose["reviewRoi"]

    rays = []
    counts: Counter[str] = Counter()
    pairs_by_component: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    for y in range(roi["y"][0], roi["y"][1] + 1, roi["step"]):
        for x in range(roi["x"][0], roi["x"][1] + 1, roi["step"]):
            direction = forward + right * ((x - center_x) * scale) + up * ((center_y - y) * scale)
            direction /= np.linalg.norm(direction)
            rebuilt_hits, rebuilt_distances = ray_hits(rebuilt_rays, origin, direction)
            rebuilt_distance = float(rebuilt_distances[0]) if len(rebuilt_hits) else float("inf")
            source_indices, source_distances = ray_hits(source_rays, origin, direction)
            visible = None
            for index, distance in zip(source_indices, source_distances):
                if distance >= rebuilt_distance:
                    break
                point = origin + direction * distance
                if discarded(int(index), point):
                    continue
                pair = (int(source_tiles[index]), int(source_faces[index]))
                component = component_by_pair.get(pair, "unmapped")
                visible = {
                    "pixel": [x, y],
                    "distance": float(distance),
                    "point": point.tolist(),
                    "sourceTileIndex": pair[0],
                    "sourceTriangleIndex": pair[1],
                    "sourceId": source_meta[pair[0]]["id"],
                    "sourceUrl": source_meta[pair[0]]["url"],
                    "componentId": component,
                    "rebuiltDistance": None if not np.isfinite(rebuilt_distance) else rebuilt_distance,
                }
                counts[component] += 1
                pairs_by_component[component].add(pair)
                break
            if visible:
                rays.append(visible)

    ranked = []
    for component, count in counts.most_common():
        record = component_record.get(component, {})
        ranked.append({
            "componentId": component,
            "rays": count,
            "uniqueFaces": len(pairs_by_component[component]),
            "sourceTileIndex": record.get("sourceTileIndex"),
            "bounds": record.get("bounds"),
            "dtmGapMeters": record.get("dtmGapMeters"),
            "areaSquareMeters": record.get("areaSquareMeters"),
            "auditStatus": record.get("status"),
        })
    report = {
        "status": "live-pose-ray-audit-no-runtime-write",
        "pose": pose,
        "sourceTriangles": int(len(source)),
        "registeredCorrectionPairs": len(removed),
        "raysWithVisibleSourceBeforeRebuiltHall": len(rays),
        "rankedComponents": ranked,
        "rays": rays,
        "limitations": [
            "The saved source stage predates the newest manifest hash; registered correction pairs are removed explicitly before visibility ranking.",
            "One live camera pose and one ROI identify owners but do not by themselves prove that a component is disconnected from all valid terrain or structures.",
            "This script does not alter source assets, manifests, masks, GOAL or the fixed preview."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "rays": len(rays), "ranked": ranked[:12]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
