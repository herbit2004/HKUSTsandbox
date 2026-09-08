#!/usr/bin/env python3
"""Register the reviewed Hall XI floating-rock correction in hires manifests."""
from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIRES = ROOT / "public/models/hires"
EVIDENCE = HIRES / "source-corrections/hall11-floating-rock-v2/evidence.json"
MANIFESTS = [HIRES / "manifest.json", HIRES / "partial-residential-ias/manifest.json"]
ID = "hall11-floating-rock-v2"


def counts(path):
    raw = path.read_bytes()
    n, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(raw[20 : 20 + n])
    triangles = vertices = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            triangles += int(gltf["accessors"][primitive["indices"]]["count"]) // 3
            vertices += int(gltf["accessors"][primitive["attributes"]["POSITION"]]["count"])
    return triangles, vertices


def update(value, updates):
    if isinstance(value, dict):
        url = value.get("url")
        for item in updates:
            source = ROOT / item["sourceUrl"]
            derived = ROOT / item["correctedUrl"]
            if not url or (HIRES / url).resolve() not in {source.resolve(), derived.resolve()}:
                continue
            assert derived.exists()
            triangles, vertices = counts(derived)
            upstream = value.get("sourceCorrection") or item.get("upstreamSourceCorrection")
            value["url"] = str(derived.relative_to(HIRES)).replace("\\", "/")
            value["sha256"] = item["correctedSha256"]
            value["bytes"] = derived.stat().st_size
            value["triangles"] = triangles
            value["vertices"] = vertices
            value["sourceCorrection"] = {
                "id": ID,
                "originalUrl": item["sourceUrl"].removeprefix("public/models/hires/"),
                "originalSha256": item["sourceSha256"],
                "originalTriangles": triangles + item["removedTriangles"],
                "removedTriangleCount": item["removedTriangles"],
                "removedSourceTriangleIndices": item["removedSourceTriangleIndices"],
                "evidence": str(EVIDENCE.relative_to(HIRES)).replace("\\", "/"),
            }
            if upstream and upstream.get("id") != ID:
                value["sourceCorrection"]["upstream"] = upstream
            return 1
        return sum(update(child, updates) for child in value.values())
    if isinstance(value, list):
        return sum(update(child, updates) for child in value)
    return 0


def refresh_totals(value):
    if isinstance(value, dict):
        for child in value.values():
            refresh_totals(child)
        tiles = value.get("tiles")
        if not isinstance(tiles, list) or not any(
            isinstance(tile, dict) and tile.get("sourceCorrection", {}).get("id") == ID
            for tile in tiles
        ):
            return
        for key in ("bytes", "triangles", "vertices"):
            if key in value:
                value[key] = sum(int(tile[key]) for tile in tiles)
    elif isinstance(value, list):
        for child in value:
            refresh_totals(child)


def main():
    evidence = json.loads(EVIDENCE.read_text())
    updates = evidence["sourceTiles"]
    result = {}
    for path in MANIFESTS:
        data = json.loads(path.read_text())
        count = update(data, updates)
        assert count == len(updates), (path, count, len(updates))
        refresh_totals(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        result[str(path.relative_to(ROOT))] = count
    evidence["registeredManifests"] = result
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
