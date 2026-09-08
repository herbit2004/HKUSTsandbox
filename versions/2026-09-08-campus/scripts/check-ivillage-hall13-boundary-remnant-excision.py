#!/usr/bin/env python3
"""Validate the registered Hall XIII boundary source correction."""
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
PATCH_ID = "native-12-NW-6C_12-NW-6C-19_Tile_303_144_L18_002"
PARTIAL_ID = "residential-ias-terminal-cluster"
TILE_ID = "12-NW-6C/12-NW-6C-19/Tile_303_144_L21_002021"
CORRECTION_ID = "ivillage-hall13-boundary-remnant-v4"
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
    matches = [value for value in data["patches"] if value["id"] == patch_id]
    assert len(matches) == 1
    return matches[0]


def tile_and_level(value: dict) -> tuple[str, dict]:
    matches = [
        (name, tile)
        for name, level in value["levels"].items()
        for tile in level["tiles"]
        if tile["id"] == TILE_ID
    ]
    assert len(matches) == 1
    return matches[0]


def projected_mask(level: dict) -> np.ndarray:
    pieces = []
    for tile in level["tiles"]:
        triangles, _ = geometry(
            HIRES / tile["url"],
            np.asarray(tile["matrix"]).reshape(4, 4, order="F"),
        )
        pieces.append(triangles)
    merged = np.concatenate(pieces)
    descriptor = level["mask"]
    cross = np.cross(merged[:, 1] - merged[:, 0], merged[:, 2] - merged[:, 0])
    xz = merged[:, :, [0, 2]]
    shapes = (
        (
            {
                "type": "Polygon",
                "coordinates": [[*tri.tolist(), tri[0].tolist()]],
            },
            255,
        )
        for tri in xz[np.abs(cross[:, 1]) > 1e-9]
    )
    return rasterize(
        shapes,
        out_shape=(descriptor["height"], descriptor["width"]),
        transform=Affine(
            descriptor["pixelSizeMeters"],
            0,
            descriptor["minX"],
            0,
            descriptor["pixelSizeMeters"],
            descriptor["minZ"],
        ),
        dtype="uint8",
        all_touched=False,
    )


def check_mask(level: dict) -> None:
    descriptor = level["mask"]
    path = HIRES / descriptor["url"]
    saved = np.asarray(Image.open(path))
    rebuilt = projected_mask(level)
    assert np.array_equal(saved, rebuilt)
    assert descriptor["coveredPixels"] == int(np.count_nonzero(saved))
    assert descriptor["sha256"] == sha(path)


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text())
    item = evidence["sourceTiles"][0]
    corrected = ROOT / item["correctedUrl"]
    assert sha(corrected) == item["correctedSha256"]
    assert glb_triangles(corrected) == item["sourceTriangles"] - item["removedTriangles"]
    assert len(item["removedSourceTriangleIndices"]) == item["removedTriangles"] == 1310

    top = json.loads((HIRES / "manifest.json").read_text())
    native = json.loads((HIRES / "native-corridor/manifest.json").read_text())
    descriptor = json.loads(
        (
            HIRES
            / "native-corridor/descriptors"
            / f"{PATCH_ID}.json"
        ).read_text()
    )
    top_patch = patch(top, PATCH_ID)
    native_patch = patch(native, PATCH_ID)
    assert top_patch == native_patch == descriptor
    name, native_tile = tile_and_level(descriptor)
    assert name == "fine"
    assert native_tile["sha256"] == item["correctedSha256"]
    assert native_tile["sourceCorrection"]["id"] == CORRECTION_ID
    check_mask(descriptor["levels"]["fine"])

    partial = json.loads((HIRES / "partial-residential-ias/manifest.json").read_text())
    partial_patch = patch(partial, PARTIAL_ID)
    name, partial_tile = tile_and_level(partial_patch)
    assert name == "high"
    assert partial_tile["sha256"] == item["correctedSha256"]
    assert partial_tile["sourceCorrection"]["id"] == CORRECTION_ID
    assert partial_patch["mask"] == partial_patch["levels"]["high"]["mask"]
    check_mask(partial_patch["levels"]["high"])

    print(
        json.dumps(
            {
                "status": "pass",
                "correction": CORRECTION_ID,
                "removedTriangles": item["removedTriangles"],
                "runtimeViews": 4,
                "nativeFineMask": descriptor["levels"]["fine"]["mask"][
                    "sha256"
                ],
                "partialMask": partial_patch["mask"]["sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
