#!/usr/bin/env python3
"""Register the reviewed Hall XIII boundary-remnant candidate for runtime QA.

The same terminal source tile is exposed through the native-corridor descriptor,
the native-corridor aggregate, the top-level hires manifest, and the earlier
residential/IAS aggregate. Keep those four runtime views consistent and rebuild
only the two masks whose retained triangle sets actually change.
"""
from __future__ import annotations

import copy
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
TOP_MANIFEST = HIRES / "manifest.json"
NATIVE_MANIFEST = HIRES / "native-corridor/manifest.json"
NATIVE_PATCH_ID = "native-12-NW-6C_12-NW-6C-19_Tile_303_144_L18_002"
NATIVE_DESCRIPTOR = (
    HIRES / "native-corridor/descriptors" / f"{NATIVE_PATCH_ID}.json"
)
PARTIAL_MANIFEST = HIRES / "partial-residential-ias/manifest.json"
PARTIAL_PATCH_ID = "residential-ias-terminal-cluster"
EVIDENCE = (
    HIRES
    / "source-corrections/ivillage-hall13-boundary-remnant-v4/evidence.json"
)
CORRECTION_ID = "ivillage-hall13-boundary-remnant-v4"
SOURCE_TILE_ID = "12-NW-6C/12-NW-6C-19/Tile_303_144_L21_002021"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    assert magic == b"glTF" and version == 2 and declared_length == len(raw)
    length, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + length])
    triangles = vertices = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            triangles += int(gltf["accessors"][primitive["indices"]]["count"]) // 3
            vertices += int(
                gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
            )
    return triangles, vertices


def find_patch(data: dict, patch_id: str) -> dict:
    patches = data.get("patches")
    if patches is None:
        assert data["id"] == patch_id
        return data
    matches = [patch for patch in patches if patch["id"] == patch_id]
    assert len(matches) == 1, (patch_id, len(matches))
    return matches[0]


def find_tile(patch: dict) -> tuple[str, dict]:
    matches = []
    for level_name, level in patch["levels"].items():
        for tile in level.get("tiles", []):
            if tile["id"] == SOURCE_TILE_ID:
                matches.append((level_name, tile))
    assert len(matches) == 1, (patch["id"], len(matches))
    return matches[0]


def update_tile(patch: dict, item: dict) -> str:
    level_name, tile = find_tile(patch)
    assert tile["sha256"] == item["sourceSha256"]
    assert tile["triangles"] == item["sourceTriangles"]

    source = ROOT / item["sourceUrl"]
    corrected = ROOT / item["correctedUrl"]
    assert source.exists() and sha(source) == item["sourceSha256"]
    assert corrected.exists() and sha(corrected) == item["correctedSha256"]
    triangles, vertices = counts(corrected)
    assert triangles == item["sourceTriangles"] - item["removedTriangles"]

    matrix = np.asarray(tile["matrix"]).reshape(4, 4, order="F")
    transformed, _ = geometry(corrected, matrix)
    low = transformed.min(axis=(0, 1))
    high = transformed.max(axis=(0, 1))
    predecessor = tile.get("sourceCorrection") or item.get("upstreamSourceCorrection")
    tile.update(
        {
            "url": str(corrected.relative_to(HIRES)).replace("\\", "/"),
            "sha256": item["correctedSha256"],
            "bytes": corrected.stat().st_size,
            "triangles": triangles,
            "vertices": vertices,
            "bounds": {"min": low.tolist(), "max": high.tolist()},
            "center": ((low + high) / 2).tolist(),
            "sourceCorrection": {
                "id": CORRECTION_ID,
                "originalUrl": item["sourceUrl"].removeprefix(
                    "public/models/hires/"
                ),
                "originalSha256": item["sourceSha256"],
                "originalTriangles": item["sourceTriangles"],
                "removedTriangleCount": item["removedTriangles"],
                "removedSourceTriangleIndices": item[
                    "removedSourceTriangleIndices"
                ],
                "evidence": str(EVIDENCE.relative_to(HIRES)).replace("\\", "/"),
            },
        }
    )
    if predecessor and predecessor.get("id") != CORRECTION_ID:
        tile["sourceCorrection"]["upstream"] = predecessor
    return level_name


def level_triangles(level: dict) -> np.ndarray:
    pieces = []
    for tile in level["tiles"]:
        triangles, _ = geometry(
            HIRES / tile["url"],
            np.asarray(tile["matrix"]).reshape(4, 4, order="F"),
        )
        pieces.append(triangles)
    assert pieces
    return np.concatenate(pieces)


def refresh_level(level: dict) -> np.ndarray:
    merged = level_triangles(level)
    low = merged.min(axis=(0, 1))
    high = merged.max(axis=(0, 1))
    level["bounds"] = {"min": low.tolist(), "max": high.tolist()}
    for field in (
        "triangles",
        "vertices",
        "bytes",
        "textureBytes",
        "textureMipBytes",
        "textureEncodedBytes",
    ):
        if field in level:
            level[field] = sum(int(tile.get(field, 0)) for tile in level["tiles"])
    return merged


def refresh_patch_bounds(patch: dict) -> None:
    bounds = [level["bounds"] for level in patch["levels"].values()]
    low = np.min(np.asarray([item["min"] for item in bounds]), axis=0)
    high = np.max(np.asarray([item["max"] for item in bounds]), axis=0)
    patch["bounds"] = {"min": low.tolist(), "max": high.tolist()}
    patch["center"] = ((low + high) / 2).tolist()


def write_mask(descriptor: dict, merged: np.ndarray) -> dict:
    x0 = float(descriptor["minX"])
    z0 = float(descriptor["minZ"])
    resolution = float(descriptor["pixelSizeMeters"])
    cross = np.cross(merged[:, 1] - merged[:, 0], merged[:, 2] - merged[:, 0])
    xz = merged[:, :, [0, 2]]
    valid = np.abs(cross[:, 1]) > 1e-9
    shapes = (
        (
            {
                "type": "Polygon",
                "coordinates": [[*triangle.tolist(), triangle[0].tolist()]],
            },
            255,
        )
        for triangle in xz[valid]
    )
    image = rasterize(
        shapes,
        out_shape=(int(descriptor["height"]), int(descriptor["width"])),
        transform=Affine(resolution, 0, x0, 0, resolution, z0),
        dtype="uint8",
        all_touched=False,
    )
    path = HIRES / descriptor["url"]
    Image.fromarray(image).save(path)
    result = dict(descriptor)
    result["coveredPixels"] = int(np.count_nonzero(image))
    result["sha256"] = sha(path)
    return result


def replace_patch(data: dict, patch: dict) -> None:
    matches = [
        index
        for index, value in enumerate(data["patches"])
        if value["id"] == patch["id"]
    ]
    assert len(matches) == 1
    data["patches"][matches[0]] = copy.deepcopy(patch)


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["id"] == CORRECTION_ID
    assert evidence["status"] == "exact-component-candidate-not-registered"
    item = evidence["sourceTiles"][0]
    assert item["sourceId"] == SOURCE_TILE_ID

    top = json.loads(TOP_MANIFEST.read_text())
    native = json.loads(NATIVE_MANIFEST.read_text())
    descriptor = json.loads(NATIVE_DESCRIPTOR.read_text())
    partial = json.loads(PARTIAL_MANIFEST.read_text())
    assert find_patch(top, NATIVE_PATCH_ID) == find_patch(native, NATIVE_PATCH_ID)
    assert find_patch(native, NATIVE_PATCH_ID) == descriptor

    native_level_name = update_tile(descriptor, item)
    assert native_level_name == "fine"
    native_level = descriptor["levels"][native_level_name]
    native_triangles = refresh_level(native_level)
    native_mask = write_mask(native_level["mask"], native_triangles)
    native_mask["projection"] = (
        "Actual retained complete-frontier source triangle pixel-center projection "
        "after the reviewed Hall XIII boundary-component correction; no "
        "rectangle/hull/dilation fill."
    )
    native_level["mask"] = native_mask
    refresh_patch_bounds(descriptor)

    replace_patch(native, descriptor)
    replace_patch(top, descriptor)

    partial_patch = find_patch(partial, PARTIAL_PATCH_ID)
    partial_level_name = update_tile(partial_patch, item)
    assert partial_level_name == "high"
    partial_level = partial_patch["levels"][partial_level_name]
    partial_triangles = refresh_level(partial_level)
    partial_mask = write_mask(partial_level["mask"], partial_triangles)
    partial_mask["source"] = (
        "Actual projected retained source triangles from 123 terminal leaves after "
        "three positively audited exact connected-component corrections. No "
        "bbox, hull or dilation fill."
    )
    partial_level["mask"] = partial_mask
    partial_patch["mask"] = dict(partial_mask)
    refresh_patch_bounds(partial_patch)
    partial_patch["evidence"]["retainedTriangleCountAfterCorrection"] = int(
        len(partial_triangles)
    )
    partial_patch["evidence"]["sourceCorrection"] = str(
        EVIDENCE.relative_to(HIRES)
    ).replace("\\", "/")
    partial_patch["evidence"]["sourceCorrectionRemovedTriangleCount"] = int(
        partial_patch["evidence"].get("sourceCorrectionRemovedTriangleCount", 0)
    ) + int(item["removedTriangles"])

    NATIVE_DESCRIPTOR.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n"
    )
    NATIVE_MANIFEST.write_text(json.dumps(native, ensure_ascii=False, indent=2) + "\n")
    TOP_MANIFEST.write_text(json.dumps(top, ensure_ascii=False, indent=2) + "\n")
    PARTIAL_MANIFEST.write_text(
        json.dumps(partial, ensure_ascii=False, indent=2) + "\n"
    )

    evidence["status"] = "candidate-registered-unpublished-runtime-qa-required"
    evidence["registeredRuntimeViews"] = {
        str(TOP_MANIFEST.relative_to(ROOT)): {
            "patchId": NATIVE_PATCH_ID,
            "level": "fine",
            "matches": 1,
        },
        str(NATIVE_MANIFEST.relative_to(ROOT)): {
            "patchId": NATIVE_PATCH_ID,
            "level": "fine",
            "matches": 1,
        },
        str(NATIVE_DESCRIPTOR.relative_to(ROOT)): {
            "patchId": NATIVE_PATCH_ID,
            "level": "fine",
            "matches": 1,
        },
        str(PARTIAL_MANIFEST.relative_to(ROOT)): {
            "patchId": PARTIAL_PATCH_ID,
            "level": "high",
            "matches": 1,
        },
    }
    evidence["coverage"] = {
        "nativeFine": native_mask,
        "partialResidentialHigh": partial_mask,
    }
    evidence["retainedNativeFineTriangles"] = int(len(native_triangles))
    evidence["retainedClusterTriangles"] = int(len(partial_triangles))
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")

    print(
        json.dumps(
            {
                "status": evidence["status"],
                "removedTriangles": item["removedTriangles"],
                "nativeFineTriangles": len(native_triangles),
                "nativeFineMaskPixels": native_mask["coveredPixels"],
                "nativeFineMaskSha256": native_mask["sha256"],
                "partialTriangles": len(partial_triangles),
                "partialMaskPixels": partial_mask["coveredPixels"],
                "partialMaskSha256": partial_mask["sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
