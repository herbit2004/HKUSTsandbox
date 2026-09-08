#!/usr/bin/env python3
"""Ray-audit Hall XI floating-remnant ROIs against the runtime high frontier.

This deliberately reads the high-level GLBs named by the production manifest.
The terminal audit cannot prove what appears during the high -> fine transition.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from hkust_source_geometry import geometry

ROOT = Path(__file__).resolve().parents[1]


def hits(triangles: np.ndarray, origin: np.ndarray, direction: np.ndarray):
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]
    q = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
    determinant = np.einsum("ij,ij->i", edge1, q)
    inverse = np.divide(1, determinant, out=np.zeros_like(determinant), where=abs(determinant) > 1e-10)
    tvec = origin - triangles[:, 0]
    u = np.einsum("ij,ij->i", tvec, q) * inverse
    r = np.cross(tvec, edge1)
    v = r @ direction * inverse
    distance = np.einsum("ij,ij->i", edge2, r) * inverse
    found = np.flatnonzero((abs(determinant) > 1e-10) & (u >= 0) & (v >= 0) & (u + v <= 1) & (distance > 0))
    return [(int(i), float(distance[i])) for i in found[np.argsort(distance[found])]]


def matrix(values):
    return np.asarray(values, dtype=float).reshape(4, 4, order="F")


def sample(descriptor, pixels, point):
    x, z = point[0], point[2]
    left, top = descriptor["boundsXZ"]["min"]
    right, bottom = descriptor["boundsXZ"]["max"]
    if not left <= x < right or not top <= z < bottom:
        return None
    return pixels[
        int((z - top) / descriptor["pixelSizeMeters"]),
        int((x - left) / descriptor["pixelSizeMeters"]),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pose", type=Path, default=ROOT / "docs/source-evidence-v4/ivillage-remnants/hall11-close-final-pose-u69.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pose = json.loads(args.pose.read_text())
    manifest = json.loads((ROOT / "public/models/hires/manifest.json").read_text())
    target_bounds = (690, 750, -1110, -1030)
    entries = {}
    for patch in manifest["patches"]:
        bounds = patch["bounds"]
        if bounds["max"][0] < target_bounds[0] or bounds["min"][0] > target_bounds[1] or bounds["max"][2] < target_bounds[2] or bounds["min"][2] > target_bounds[3]:
            continue
        for tile in patch["levels"]["high"]["tiles"]:
            entries.setdefault(tile["id"], tile)

    all_triangles = []
    owner = []
    source_paths = []
    for source_index, tile in enumerate(entries.values()):
        path = ROOT / "public/models/hires" / tile["url"]
        triangles, _ = geometry(path, matrix(tile["matrix"]))
        all_triangles.append(triangles)
        owner.extend((source_index, i) for i in range(len(triangles)))
        source_paths.append({"id": tile["id"], "url": tile["url"], "triangles": len(triangles), "matrix": tile["matrix"]})
    source = np.concatenate(all_triangles)
    owner = np.asarray(owner, dtype=int)

    current, _ = geometry(ROOT / "public/models/current-forms/ivillage-rebuild/ivillage-x-xiii-v1.glb")
    form_manifest = json.loads((ROOT / "public/models/current-forms/ivillage-rebuild/manifest.json").read_text())
    form_masks = [
        (member["mask"], np.asarray(Image.open(ROOT / "public/models/current-forms/ivillage-rebuild" / member["mask"]["url"]).convert("RGBA")))
        for member in form_manifest["members"]
    ]
    protection_descriptor = form_manifest["sourceProtection"]
    protection = np.frombuffer(
        (ROOT / "public/models/current-forms/ivillage-rebuild" / protection_descriptor["url"]).read_bytes(),
        np.uint8,
    ).reshape(protection_descriptor["height"], protection_descriptor["width"], 4)

    def discarded(point, normal):
        protected = sample(protection_descriptor, protection, point)
        if protected is not None and protected[0]:
            reference = int(protected[0]) + int(protected[1]) / 256
            if abs(point[1] - reference) <= protection_descriptor["groundBandMeters"] and abs(normal[1]) >= 0.6:
                return False
        for descriptor, pixels in form_masks:
            value = sample(descriptor, pixels, point)
            if value is None or value[0] < 128:
                continue
            lower = descriptor["replacementMinY"] if value[3] == 255 else max(descriptor["replacementMinY"], int(value[3]))
            if lower <= point[1] <= descriptor["replacementMaxY"]:
                return True
        return False

    centroids = source.mean(axis=1)
    normals = np.cross(source[:, 2] - source[:, 0], source[:, 1] - source[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals = np.divide(normals, lengths[:, None], out=np.zeros_like(normals), where=lengths[:, None] > 1e-10)
    origin = np.asarray(pose["camera"], dtype=float)
    target = np.asarray(pose["target"], dtype=float)
    forward = target - origin
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    center_x, center_y = pose["viewport"]["targetPixel"]
    scale = 2 * np.tan(np.deg2rad(42 / 2)) / pose["viewport"]["height"]
    rois = {
        "left": {"x": [648, 712], "y": [730, 844], "step": 4},
        "right": {"x": [1028, 1120], "y": [690, 844], "step": 4},
    }
    report = {"status": "audited", "pose": pose, "sources": source_paths, "rois": {}}
    for name, roi in rois.items():
        records = []
        face_hits = set()
        for y in range(roi["y"][0], roi["y"][1] + 1, roi["step"]):
            for x in range(roi["x"][0], roi["x"][1] + 1, roi["step"]):
                direction = forward + right * ((x - center_x) * scale) + up * ((center_y - y) * scale)
                direction /= np.linalg.norm(direction)
                model_hits = hits(current, origin, direction)
                model_distance = model_hits[0][1] if model_hits else float("inf")
                visible = []
                for index, distance in hits(source, origin, direction):
                    if distance >= model_distance:
                        break
                    point = origin + direction * distance
                    if discarded(point, normals[index]):
                        continue
                    source_index, face = owner[index]
                    visible.append({
                        "sourceIndex": int(source_index),
                        "sourceId": source_paths[source_index]["id"],
                        "sourceUrl": source_paths[source_index]["url"],
                        "triangleIndex": int(face),
                        "point": point.tolist(),
                        "normal": normals[index].tolist(),
                        "centroid": centroids[index].tolist(),
                        "distance": distance,
                    })
                    face_hits.add((int(source_index), int(face)))
                    break
                if visible:
                    records.append({"pixel": [x, y], "modelDistance": None if not np.isfinite(model_distance) else model_distance, "nearestVisibleHigh": visible[0]})
        report["rois"][name] = {
            "pixelROI": roi,
            "raysWithVisibleHigh": len(records),
            "uniqueNearestFaces": len(face_hits),
            "records": records,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({name: {"rays": value["raysWithVisibleHigh"], "faces": value["uniqueNearestFaces"]} for name, value in report["rois"].items()}, indent=2))


if __name__ == "__main__":
    main()
