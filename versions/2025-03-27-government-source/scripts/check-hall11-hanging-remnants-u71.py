#!/usr/bin/env python3
"""Validate all runtime views and masks for Hall XI U71 correction."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize

from hkust_source_geometry import geometry


ROOT = Path(__file__).resolve().parents[1]
HIRES = ROOT / "public/models/hires"
PATCH_ID = "native-12-NW-11A_12-NW-11A-3_Tile_302_143_L18_003"
PARTIAL_ID = "residential-ias-terminal-cluster"
CORRECTION_ID = "hall11-hanging-remnants-u71"
EVIDENCE = HIRES / f"source-corrections/{CORRECTION_ID}/evidence.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glb_triangles(path: Path) -> int:
    raw = path.read_bytes()
    length, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + length])
    return sum(
        int(gltf["accessors"][primitive["indices"]]["count"]) // 3
        for mesh in gltf.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    )


def patch(data: dict, patch_id: str) -> dict:
    if data.get("id") == patch_id:
        return data
    values = [value for value in data["patches"] if value["id"] == patch_id]
    assert len(values) == 1
    return values[0]


def tile(value: dict, tile_id: str) -> tuple[str, dict]:
    values = [
        (name, item)
        for name, level in value["levels"].items()
        for item in level["tiles"]
        if item["id"] == tile_id
    ]
    assert len(values) == 1
    return values[0]


def expected_mask(level: dict) -> np.ndarray:
    pieces = []
    for item in level["tiles"]:
        triangles, _ = geometry(
            HIRES / item["url"],
            np.asarray(item["matrix"]).reshape(4, 4, order="F"),
        )
        pieces.append(triangles)
    merged = np.concatenate(pieces)
    descriptor = level["mask"]
    cross = np.cross(merged[:, 1] - merged[:, 0], merged[:, 2] - merged[:, 0])
    projected = merged[:, :, [0, 2]][np.abs(cross[:, 1]) > 1e-9]
    shapes = (
        ({"type": "Polygon", "coordinates": [[*tri.tolist(), tri[0].tolist()]]}, 255)
        for tri in projected
    )
    return rasterize(
        shapes,
        out_shape=(descriptor["height"], descriptor["width"]),
        transform=Affine(descriptor["pixelSizeMeters"], 0, descriptor["minX"], 0, descriptor["pixelSizeMeters"], descriptor["minZ"]),
        dtype="uint8",
        all_touched=False,
    )


def check_mask(level: dict) -> str:
    descriptor = level["mask"]
    target = HIRES / descriptor["url"]
    actual = np.asarray(Image.open(target))
    expected = expected_mask(level)
    assert np.array_equal(actual, expected)
    assert descriptor["coveredPixels"] == int(np.count_nonzero(actual))
    assert descriptor["sha256"] == sha(target)
    return descriptor["sha256"]


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["status"] in {
        "candidate-registered-unpublished-runtime-qa-required",
        "registered-runtime-verified-awaiting-production-publish",
        "published-fixed-preview-runtime-verified",
    }
    assert evidence["removedTriangles"] == 268
    items = {item["level"]: item for item in evidence["sourceTiles"]}
    assert set(items) == {"high", "fine"}
    for item in items.values():
        corrected = ROOT / item["correctedUrl"]
        assert sha(corrected) == item["correctedSha256"]
        assert glb_triangles(corrected) == item["retainedTriangles"]
        assert len(item["removedSourceTriangleIndices"]) == item["removedTriangles"]

    top = json.loads((HIRES / "manifest.json").read_text())
    native = json.loads((HIRES / "native-corridor/manifest.json").read_text())
    descriptor = json.loads((HIRES / "native-corridor/descriptors" / f"{PATCH_ID}.json").read_text())
    top_patch = patch(top, PATCH_ID)
    assert top_patch == patch(native, PATCH_ID) == descriptor
    for level_name in ("high", "fine"):
        actual_level, item = tile(descriptor, items[level_name]["sourceId"])
        assert actual_level == level_name
        assert item["sha256"] == items[level_name]["correctedSha256"]
        assert item["triangles"] == items[level_name]["retainedTriangles"]
        assert item["sourceCorrection"]["id"] == CORRECTION_ID
    assert descriptor["mask"] == descriptor["levels"]["high"]["mask"]
    high_mask = check_mask(descriptor["levels"]["high"])
    fine_mask = check_mask(descriptor["levels"]["fine"])

    partial = json.loads((HIRES / "partial-residential-ias/manifest.json").read_text())
    partial_patch = patch(partial, PARTIAL_ID)
    level_name, item = tile(partial_patch, items["fine"]["sourceId"])
    assert level_name == "high"
    assert item["sha256"] == items["fine"]["correctedSha256"]
    assert item["sourceCorrection"]["id"] == CORRECTION_ID
    assert partial_patch["mask"] == partial_patch["levels"]["high"]["mask"]
    partial_mask = check_mask(partial_patch["levels"]["high"])
    assert partial_patch["evidence"]["retainedTriangleCountAfterCorrection"] == partial_patch["levels"]["high"]["triangles"]

    print(json.dumps({
        "status": "pass",
        "correction": CORRECTION_ID,
        "removedTriangles": 268,
        "runtimeViews": 4,
        "nativeHighMask": high_mask,
        "nativeFineMask": fine_mask,
        "partialMask": partial_mask,
    }, indent=2))


if __name__ == "__main__":
    main()
