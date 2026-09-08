#!/usr/bin/env python3
"""Register the reviewed U70 preview-tile floating-remnant corrections."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "public/models"
PREVIEW_MANIFEST = MODELS / "preview-manifest.json"

CORRECTIONS = (
    {
        "tileId": "12-NW-11A/12-NW-11A-8/Tile_302_142_L17_001",
        "id": "floating-stones-12-nw-11a-8-u70",
        "directory": "source-corrections/floating-stones-12-nw-11a-8-u70",
        "filename": "Tile_302_142_L17_001.corrected.glb",
    },
    {
        "tileId": "12-NW-11A/12-NW-11A-3/Tile_302_143_L16_0",
        "id": "ug10-floating-fragments-12-u70",
        "directory": "source-corrections/ug10-floating-fragments-12-u70",
        "filename": "Tile_302_143_L16_0.corrected.glb",
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def glb_counts(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    assert magic == b"glTF" and version == 2 and declared_length == len(raw)
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    assert json_kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + json_length])
    triangles = 0
    vertices = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            triangles += int(gltf["accessors"][primitive["indices"]]["count"]) // 3
            vertices += int(
                gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
            )
    return triangles, vertices


def main() -> None:
    preview = json.loads(PREVIEW_MANIFEST.read_text())
    by_id = {tile["id"]: tile for tile in preview["tiles"]}

    report = []
    for correction in CORRECTIONS:
        manifest_path = MODELS / correction["directory"] / "manifest.json"
        correction_manifest = json.loads(manifest_path.read_text())
        assert correction_manifest["id"] == correction["id"]
        assert correction_manifest["tileId"] == correction["tileId"]

        source = correction_manifest["sourcePreview"]
        corrected = correction_manifest["correctedPreview"]
        corrected_path = MODELS / correction["directory"] / correction["filename"]
        corrected_url = str(corrected_path.relative_to(MODELS)).replace("\\", "/")
        assert corrected_url == corrected["url"]
        assert sha256(corrected_path) == corrected["sha256"]

        triangles, vertices = glb_counts(corrected_path)
        assert triangles == corrected["triangles"]
        assert triangles == source["triangles"] - corrected["trianglesRemoved"]

        tile = by_id[correction["tileId"]]
        predecessor = tile.get("sourceCorrection")
        if predecessor and predecessor.get("id") == correction["id"]:
            predecessor = predecessor.get("predecessor")

        tile.update(
            {
                "url": corrected_url,
                "sha256": corrected["sha256"],
                "bytes": corrected_path.stat().st_size,
                "triangles": triangles,
                "vertices": vertices,
            }
        )
        tile["sourceCorrection"] = {
            "id": correction["id"],
            "manifest": str(manifest_path.relative_to(MODELS)).replace("\\", "/"),
            "uncorrectedPreviewUrl": source["url"],
            "uncorrectedPreviewSha256": source["sha256"],
            "originalTriangles": source["triangles"],
            "removedTriangleCount": corrected["trianglesRemoved"],
            "removedSourceTriangleIndices": correction_manifest[
                "removedSourceGlobalTriangleIndices"
            ],
            "evidence": str(
                (manifest_path.parent / correction_manifest["evidence"]).relative_to(MODELS)
            ).replace("\\", "/"),
        }
        if predecessor:
            tile["sourceCorrection"]["predecessor"] = predecessor

        correction_manifest["registration"] = {
            "manifest": "preview-manifest.json",
            "registeredAt": "2026-09-08",
        }
        manifest_path.write_text(
            json.dumps(correction_manifest, ensure_ascii=False, indent=2) + "\n"
        )
        report.append(
            {
                "tileId": correction["tileId"],
                "correction": correction["id"],
                "triangles": triangles,
                "vertices": vertices,
                "bytes": corrected_path.stat().st_size,
                "sha256": corrected["sha256"],
            }
        )

    preview["stats"]["glbBytes"] = sum(int(tile["bytes"]) for tile in preview["tiles"])
    preview["stats"]["triangles"] = sum(
        int(tile["triangles"]) for tile in preview["tiles"]
    )
    preview["stats"]["vertices"] = sum(int(tile["vertices"]) for tile in preview["tiles"])
    preview["previewProcessing"]["sourceCorrectionCount"] = sum(
        1 for tile in preview["tiles"] if tile.get("sourceCorrection")
    )
    PREVIEW_MANIFEST.write_text(json.dumps(preview, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"registered": report, "stats": preview["stats"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
