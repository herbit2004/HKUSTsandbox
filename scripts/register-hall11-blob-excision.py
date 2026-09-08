#!/usr/bin/env python3
"""Register the reviewed Hall XI exact-face correction in hires manifests."""
from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIRES = ROOT / "public/models/hires"
EVIDENCE = HIRES / "source-corrections/hall11-source-blob-v1/evidence.json"
MANIFESTS = [HIRES / "manifest.json", HIRES / "partial-residential-ias/manifest.json"]
ID = "hall11-source-blob-v1"


def counts(path):
    raw = path.read_bytes(); n, kind = struct.unpack_from("<II", raw, 12); assert kind == 0x4E4F534A
    g = json.loads(raw[20:20+n]); t = v = 0
    for mesh in g.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            t += int(g["accessors"][primitive["indices"]]["count"]) // 3
            v += int(g["accessors"][primitive["attributes"]["POSITION"]]["count"])
    return t, v


def update(value, updates):
    if isinstance(value, dict):
        url = value.get("url")
        for u in updates:
            src = ROOT / u["sourceUrl"]; derived = ROOT / u["correctedUrl"]
            if not url or (HIRES / url).resolve() not in {src.resolve(), derived.resolve()}:
                continue
            assert derived.exists()
            tri, vertices = counts(derived)
            value["url"] = str(derived.relative_to(HIRES)).replace("\\", "/")
            value["sha256"] = u["correctedSha256"]; value["bytes"] = derived.stat().st_size
            value["triangles"] = tri; value["vertices"] = vertices
            value["sourceCorrection"] = {"id": ID, "originalUrl": u["sourceUrl"].removeprefix("public/models/hires/"),
                "originalSha256": u["sourceSha256"], "originalTriangles": tri + u["removedTriangles"],
                "removedTriangleCount": u["removedTriangles"], "removedSourceTriangleIndices": u["removedSourceTriangleIndices"],
                "evidence": str(EVIDENCE.relative_to(HIRES)).replace("\\", "/")}
            return 1
        return sum(update(child, updates) for child in value.values())
    if isinstance(value, list):
        return sum(update(child, updates) for child in value)
    return 0


def refresh_corrected_level_totals(value):
    """Keep every aggregate level consistent with its registered tile records."""
    if isinstance(value, dict):
        for child in value.values():
            refresh_corrected_level_totals(child)
        tiles = value.get("tiles")
        if not isinstance(tiles, list) or not any(
            isinstance(tile, dict) and tile.get("sourceCorrection", {}).get("id") == ID
            for tile in tiles
        ):
            return
        if "bytes" in value:
            value["bytes"] = sum(int(tile["bytes"]) for tile in tiles)
        if "triangles" in value:
            value["triangles"] = sum(int(tile["triangles"]) for tile in tiles)
        if "vertices" in value:
            value["vertices"] = sum(int(tile["vertices"]) for tile in tiles)
    elif isinstance(value, list):
        for child in value:
            refresh_corrected_level_totals(child)


def main():
    evidence = json.loads(EVIDENCE.read_text())
    updates = []
    for item in evidence["sourceTiles"]:
        item["sourceUrl"] = str(Path(item["source"]).relative_to(ROOT)).replace("\\", "/")
        item["correctedUrl"] = str(Path(item["derived"]).relative_to(ROOT)).replace("\\", "/")
        item["correctedSha256"] = item["derivedSha256"]
        updates.append(item)
    result = {}
    for path in MANIFESTS:
        data = json.loads(path.read_text()); n = update(data, updates)
        assert n == len(updates), (path, n, len(updates))
        refresh_corrected_level_totals(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        result[str(path.relative_to(ROOT))] = n
    evidence["registeredManifests"] = result
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
