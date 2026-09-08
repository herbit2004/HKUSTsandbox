#!/usr/bin/env python3
"""Read-only integrity checks for the i-Village source-cleanup handoff.

The cleanup mask is an RGBA ownership handoff.  Its red channel marks an
occupied pixel, green/blue stay zero, and alpha stores the integer lower guard
height.  This checker never rewrites a mask, manifest, evidence file, or GLB.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MASK_ROOT = ROOT / "public/models/current-forms/ivillage-rebuild"
MASK_MANIFEST = MASK_ROOT / "manifest.json"
MASK_EVIDENCE = MASK_ROOT / "evidence/source-cleanup-mask-u69.json"
CORRECTION_EVIDENCE = (
    ROOT / "public/models/hires/source-corrections/hall11-lower-floaters-v3/evidence.json"
)
PUBLIC_MANIFESTS = (
    ROOT / "public/models/hires/manifest.json",
    ROOT / "public/models/hires/partial-residential-ias/manifest.json",
)
EXPECTED_MARKERS = 899
CORRECTION_ID = "hall11-lower-floaters-v3"


class CheckError(AssertionError):
    """A failed named invariant."""


def require(condition: bool, name: str, **details: object) -> None:
    if not condition:
        detail = ", ".join(f"{key}={value!r}" for key, value in details.items())
        raise CheckError(f"{name}: {detail}" if detail else name)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def walk_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def correction_entries(manifest: dict) -> list[dict]:
    return [
        value
        for value in walk_dicts(manifest)
        if isinstance(value.get("sourceCorrection"), dict)
        and value["sourceCorrection"].get("id") == CORRECTION_ID
    ]


def check_mask(manifest: dict, evidence: dict, correction: dict) -> dict:
    member = next(item for item in manifest["members"] if item["nodeName"] == "ug-hall-13")
    descriptor = member["mask"]
    target = MASK_ROOT / descriptor["url"]
    backup = MASK_ROOT / evidence["baseMask"]

    require(target.exists(), "target exists", path=str(target))
    require(backup.exists(), "backup exists", path=str(backup))
    target_sha = sha256(target)
    backup_sha = sha256(backup)
    target_bytes = target.stat().st_size
    backup_bytes = backup.stat().st_size

    require(target_sha == descriptor["sha256"], "target hash matches mask manifest", actual=target_sha)
    require(target_bytes == descriptor["bytes"], "target bytes match mask manifest", actual=target_bytes)
    require(target_sha == evidence["maskSha256"], "target hash matches cleanup evidence", actual=target_sha)
    require(backup.name == evidence["baseMask"], "backup name matches cleanup evidence")
    require(backup_sha == evidence["baseMaskSha256"], "backup hash matches cleanup evidence", actual=backup_sha)
    require(evidence["maskMember"] == member["buildingId"], "cleanup member matches mask manifest")
    require(evidence["sourceCorrection"] == correction["id"], "cleanup correction id matches correction evidence")
    require(evidence["removedSourceTriangles"] == correction["removedTriangles"], "removed triangle total matches correction evidence")

    target_image = Image.open(target).convert("RGBA")
    backup_image = Image.open(backup).convert("RGBA")
    require(target_image.size == (descriptor["width"], descriptor["height"]), "target dimensions match mask manifest", actual=target_image.size)
    require(backup_image.size == target_image.size, "backup and target dimensions match")
    target_rgba = target_image.tobytes()
    backup_rgba = backup_image.tobytes()
    expected_raw_bytes = descriptor["width"] * descriptor["height"] * 4
    require(len(target_rgba) == expected_raw_bytes, "target decoded RGBA bytes", actual=len(target_rgba))
    require(len(backup_rgba) == expected_raw_bytes, "backup decoded RGBA bytes", actual=len(backup_rgba))

    width, height = target_image.size
    target_pixels = [target_rgba[index : index + 4] for index in range(0, len(target_rgba), 4)]
    backup_pixels = [backup_rgba[index : index + 4] for index in range(0, len(backup_rgba), 4)]
    changed = {
        (index % width, index // width)
        for index, (before, after) in enumerate(zip(backup_pixels, target_pixels))
        if before != after
    }
    markers = {
        (index % width, index // width)
        for index, pixel in enumerate(target_pixels)
        if pixel[0] > 0 and pixel[1] == 0 and pixel[2] == 0 and pixel[3] > 0
    }
    require(len(changed) == EXPECTED_MARKERS, "changed pixel count", actual=len(changed))
    require(len(markers) == EXPECTED_MARKERS, "special marker count", actual=len(markers))
    require(changed == markers, "only changed pixels are special markers", changed=len(changed), markers=len(markers))
    require(evidence["projectedPixels"] == EXPECTED_MARKERS, "projected pixel evidence count")
    require(evidence["changedPixels"] == EXPECTED_MARKERS, "changed pixel evidence count")

    records = evidence["changedPixelRecords"]
    record_coords = {(int(record["col"]), int(record["row"])) for record in records}
    require(len(records) == EXPECTED_MARKERS, "changed pixel record count", actual=len(records))
    require(len(record_coords) == EXPECTED_MARKERS, "changed pixel record coordinates are unique")
    require(record_coords == markers, "evidence coordinates equal target markers")
    require(evidence["boundsXZ"] == descriptor["boundsXZ"], "evidence bounds match mask manifest")
    require(evidence["pixelSizeMeters"] == descriptor["pixelSizeMeters"], "evidence pixel size matches mask manifest")

    min_x, min_z = descriptor["boundsXZ"]["min"]
    step = float(descriptor["pixelSizeMeters"])
    for record in records:
        col, row = int(record["col"]), int(record["row"])
        require(0 <= col < width and 0 <= row < height, "marker coordinate in mask", col=col, row=row)
        index = row * width + col
        before = list(backup_pixels[index])
        after = list(target_pixels[index])
        require(before == record["previousRGBA"], "marker backup pixel matches evidence", col=col, row=row)
        require(after[0:3] == [255, 0, 0], "marker RGB encoding", col=col, row=row, rgba=after)
        expected_xz = [min_x + (col + 0.5) * step, min_z + (row + 0.5) * step]
        actual_xz = record["worldXZ"]
        require(
            len(actual_xz) == 2 and all(math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9) for a, b in zip(actual_xz, expected_xz)),
            "marker world coordinate matches pixel center",
            col=col,
            row=row,
        )
        dtm_y = float(record["dtmY"])
        lower_guard = int(record["lowerGuardY"])
        require(math.isfinite(dtm_y), "DTM record is finite", col=col, row=row)
        expected_guard = max(math.floor(dtm_y), math.ceil(float(descriptor["replacementMinY"])))
        require(lower_guard == expected_guard, "DTM record yields lowerGuardY", col=col, row=row)
        require(after[3] == lower_guard, "marker alpha matches lowerGuardY", col=col, row=row, alpha=after[3], lowerGuardY=lower_guard)

    return {
        "target": {"path": str(target), "sha256": target_sha, "bytes": target_bytes},
        "backup": {"path": str(backup), "sha256": backup_sha, "bytes": backup_bytes},
        "decodedRGBABytes": expected_raw_bytes,
        "dimensions": [width, height],
        "specialMarkers": len(markers),
        "changedPixels": len(changed),
        "markerAlphaRange": [min(int(record["lowerGuardY"]) for record in records), max(int(record["lowerGuardY"]) for record in records)],
    }


def check_v3_manifests(correction: dict) -> dict:
    expected = {tile["sourceId"]: tile for tile in correction["sourceTiles"]}
    require(len(expected) == len(correction["sourceTiles"]) == 3, "correction evidence has three unique source tiles")
    manifest_reports = {}
    expected_evidence = "source-corrections/hall11-lower-floaters-v3/evidence.json"

    for manifest_path in PUBLIC_MANIFESTS:
        manifest = load_json(manifest_path)
        manifest_prefix = "public/models/hires/"

        def manifest_url(path: str) -> str:
            require(path.startswith(manifest_prefix), "correction evidence URL is under public/models/hires", path=path)
            return path.removeprefix(manifest_prefix)

        entries = correction_entries(manifest)
        require(len(entries) == len(expected), "manifest v3 registration count", manifest=str(manifest_path), actual=len(entries))
        actual_ids = {entry["id"] for entry in entries}
        require(actual_ids == set(expected), "manifest v3 source ids", manifest=str(manifest_path))

        for entry in entries:
            source = expected[entry["id"]]
            source_correction = entry["sourceCorrection"]
            require(entry["url"] == manifest_url(source["correctedUrl"]), "manifest corrected URL matches evidence", id=entry["id"])
            require(entry["bytes"] == source["bytes"], "manifest corrected bytes match evidence", id=entry["id"])
            require(entry["sha256"] == source["correctedSha256"], "manifest corrected hash matches evidence", id=entry["id"])
            require(source_correction["originalUrl"] == manifest_url(source["sourceUrl"]), "manifest source URL provenance", id=entry["id"])
            require(source_correction["originalSha256"] == source["sourceSha256"], "manifest source hash provenance", id=entry["id"])
            require(source_correction["originalTriangles"] == source["sourceTriangles"], "manifest source triangle provenance", id=entry["id"])
            require(source_correction["removedTriangleCount"] == source["removedTriangles"], "manifest removed triangle provenance", id=entry["id"])
            require(source_correction["removedSourceTriangleIndices"] == source["removedSourceTriangleIndices"], "manifest removed index provenance", id=entry["id"])
            require(source_correction["evidence"] == expected_evidence, "manifest correction evidence path", id=entry["id"])

            source_path = ROOT / source["sourceUrl"]
            corrected_path = ROOT / source["correctedUrl"]
            require(source_path.exists() and corrected_path.exists(), "correction source and derived files exist", id=entry["id"])
            require(source_path.stat().st_size == source["sourceBytes"] if "sourceBytes" in source else True, "source byte metadata", id=entry["id"])
            require(corrected_path.stat().st_size == source["bytes"], "derived bytes match correction evidence", id=entry["id"])
            require(sha256(source_path) == source["sourceSha256"], "derived source hash matches correction evidence", id=entry["id"])
            require(sha256(corrected_path) == source["correctedSha256"], "derived correction hash matches correction evidence", id=entry["id"])

        manifest_reports[str(manifest_path.relative_to(ROOT))] = len(entries)

    registered = correction.get("registeredManifests", {})
    require(registered.get("public/models/hires/manifest.json") == 3, "correction evidence main registration count")
    require(registered.get("public/models/hires/partial-residential-ias/manifest.json") == 3, "correction evidence partial registration count")
    return manifest_reports


def main() -> None:
    manifest = load_json(MASK_MANIFEST)
    evidence = load_json(MASK_EVIDENCE)
    correction = load_json(CORRECTION_EVIDENCE)
    mask_report = check_mask(manifest, evidence, correction)
    manifest_report = check_v3_manifests(correction)
    report = {
        "status": "pass",
        "checks": [
            "backup/target hashes and encoded bytes are consistent with manifest/evidence metadata",
            "exactly 899 occupied red-only marker pixels",
            "all and only those 899 pixels differ from backup",
            "marker backup RGBA, pixel-center coordinates, DTM lower guards, and alpha are consistent",
            "hall11-lower-floaters-v3 source/derived hashes, bytes, indices, and registrations are consistent",
        ],
        "mask": mask_report,
        "v3Registrations": manifest_report,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (CheckError, KeyError, FileNotFoundError, ValueError) as error:
        raise SystemExit(f"FAIL: {error}") from error
