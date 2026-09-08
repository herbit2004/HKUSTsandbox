#!/usr/bin/env python3
"""Extend the atomic i-Village current-form mask over audited source remnants.

The mask is level-independent: every baseline/high/fine photographic source is
cut only above the original DTM at pixels projected by the exact v3 components.
The terrain shader then hands those pixels to the existing DTM surface.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "public/models/current-forms/ivillage-rebuild"
MANIFEST = BASE / "manifest.json"
TARGET = BASE / "ug-hall-13-replacement.png"
BACKUP = BASE / "ug-hall-13-replacement-before-source-cleanup-u69.png"
EVIDENCE = BASE / "evidence/source-cleanup-mask-u69.json"
CORRECTION = ROOT / "public/models/hires/source-corrections/hall11-lower-floaters-v3/evidence.json"
STAGE = Path("/tmp/hkust-ivillage-rebuild-source")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def covered(point: np.ndarray, triangles: np.ndarray) -> bool:
    if not len(triangles):
        return False
    a = triangles[:, 0][:, (0, 2)]
    b = triangles[:, 1][:, (0, 2)]
    c = triangles[:, 2][:, (0, 2)]
    v0, v1, v2 = c - a, b - a, point - a
    denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    valid = np.abs(denominator) > 1e-12
    u = np.zeros(len(triangles))
    v = np.zeros(len(triangles))
    u[valid] = (v2[valid, 0] * v1[valid, 1] - v1[valid, 0] * v2[valid, 1]) / denominator[valid]
    v[valid] = (v0[valid, 0] * v2[valid, 1] - v2[valid, 0] * v0[valid, 1]) / denominator[valid]
    return bool(np.any(valid & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)))


def main():
    manifest = json.loads(MANIFEST.read_text())
    member = next(item for item in manifest["members"] if item["nodeName"] == "ug-hall-13")
    descriptor = member["mask"]
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    pixels = np.asarray(Image.open(BACKUP).convert("RGBA")).copy()
    before = pixels.copy()

    source = np.load(STAGE / "terminal-triangles.npz")
    correction = json.loads(CORRECTION.read_text())
    selected = {
        (int(tile["sourceTileIndex"]), int(face))
        for tile in correction["sourceTiles"]
        for face in tile["removedSourceTriangleIndices"]
    }
    keep = np.fromiter(
        ((int(tile), int(face)) in selected for tile, face in zip(source["sourceTileIndex"], source["triangleIndex"])),
        bool,
        len(source["triangleIndex"]),
    )
    triangles = source["positions"][keep]
    xz = triangles[:, :, (0, 2)]

    grid = np.load(STAGE / "roof-grid.npz")
    ground = grid["ground"]
    grid_x0, grid_z0, grid_step = float(grid["x0"]), float(grid["z0"]), float(grid["step"])
    mask_x0, mask_z0 = descriptor["boundsXZ"]["min"]
    step = float(descriptor["pixelSizeMeters"])
    col0 = max(0, math.floor((float(xz[:, :, 0].min()) - mask_x0) / step))
    col1 = min(descriptor["width"], math.ceil((float(xz[:, :, 0].max()) - mask_x0) / step))
    row0 = max(0, math.floor((float(xz[:, :, 1].min()) - mask_z0) / step))
    row1 = min(descriptor["height"], math.ceil((float(xz[:, :, 1].max()) - mask_z0) / step))
    added = []
    for row in range(row0, row1):
        z = mask_z0 + (row + 0.5) * step
        for col in range(col0, col1):
            x = mask_x0 + (col + 0.5) * step
            if not covered(np.asarray([x, z]), triangles):
                continue
            grid_col = int(round((x - grid_x0) / grid_step))
            grid_row = int(round((z - grid_z0) / grid_step))
            reference = float(ground[grid_row, grid_col])
            lower = max(int(math.floor(reference)), int(math.ceil(descriptor["replacementMinY"])))
            previous = pixels[row, col].copy()
            pixels[row, col, 0] = 255
            pixels[row, col, 1:3] = 0
            pixels[row, col, 3] = lower
            if not np.array_equal(previous, pixels[row, col]):
                added.append({"col": col, "row": row, "worldXZ": [x, z], "dtmY": reference, "lowerGuardY": lower, "previousRGBA": previous.tolist()})

    Image.fromarray(pixels).save(TARGET)
    descriptor["sha256"] = sha(TARGET)
    descriptor["bytes"] = TARGET.stat().st_size
    extension = {
        "id": "hall-x-xiii-level-independent-source-cleanup-u69",
        "maskMember": member["buildingId"],
        "sourceCorrection": correction["id"],
        "removedSourceTriangles": correction["removedTriangles"],
        "projectedPixels": int(np.count_nonzero(pixels[:, :, 0] > 127) - np.count_nonzero(before[:, :, 0] > 127) + sum((before[:, :, 0] > 127).ravel() & (pixels[:, :, 3] != before[:, :, 3]).ravel())),
        "changedPixels": len(added),
        "verticalPolicy": "At exact removed-component projection pixels, discard photographic source from floor(DTM) upward; lower source and all pixels outside the projection remain unchanged.",
        "terrainHandoff": "The terrain coverage fallback recognizes currentForms coverage and reveals the existing DTM surface at these pixels.",
        "baseMask": BACKUP.name,
        "baseMaskSha256": sha(BACKUP),
        "maskSha256": descriptor["sha256"],
        "pixelSizeMeters": step,
        "boundsXZ": descriptor["boundsXZ"],
        "limitations": [
            "The cleanup raster is a renderer ownership handoff, not an expansion of the official Hall XIII footprint.",
            "It does not assert a completed-era road, terrace, planting, or wall boundary.",
        ],
    }
    manifest["sourceCleanupExtension"] = extension
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    EVIDENCE.write_text(json.dumps({**extension, "changedPixelRecords": added}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: extension[key] for key in ["id", "removedSourceTriangles", "projectedPixels", "changedPixels", "baseMaskSha256", "maskSha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
