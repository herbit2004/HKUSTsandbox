#!/usr/bin/env python3
"""Install an independently validated building-neighborhood source stage.

The default operation is intentionally explicit and guarded.  It reads a
stage directory, verifies the stage manifest digest in both reports, rejects
any existing owner or tile collision, and only then copies byte-verified GLBs
and masks.  ``--dry-run`` performs every read-only guard and writes nothing.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
LIVE_MANIFEST = PROJECT / "public/models/hires/manifest.json"
DEFAULT_STAGE = Path("/tmp/hkust-targeted-terminal-u68")
EVIDENCE = PROJECT / "docs/source-evidence-v4/building-quality/targeted-terminal-integration-u68-all"


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def stage_path(stage: Path, value: str | None, fallback: str | None = None) -> Path:
    candidate = Path(value or fallback or "")
    if candidate.is_absolute():
        return candidate
    return stage / candidate


def validator_manifest_digests(value: Any) -> set[str]:
    keys = {"manifestSHA256", "manifestSha256", "stageManifestSHA256", "stageManifestSha256", "stageSha256"}
    found: set[str] = set()
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in keys and isinstance(item, str):
                    found.add(item)
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(value)
    return found


def source_for_tile(stage: Path, tile: dict[str, Any]) -> Path:
    return stage_path(stage, tile.get("localPath"), tile.get("url"))


def source_for_mask(stage: Path, mask: dict[str, Any]) -> Path:
    return stage_path(stage, mask.get("localPath"), mask.get("url"))


def checked_copy(source: Path, destination: Path, expected: str, dry_run: bool) -> str:
    if not source.is_file():
        raise RuntimeError(f"Missing staged payload: {source}")
    if digest(source) != expected:
        raise RuntimeError(f"Staged SHA mismatch: {source}")
    if destination.exists():
        if not destination.is_file() or digest(destination) != expected:
            raise RuntimeError(f"Refusing to overwrite different payload: {destination}")
        return "existing"
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if digest(destination) != expected:
            raise RuntimeError(f"Destination SHA mismatch after copy: {destination}")
    return "planned" if dry_run else "copied"


def relative_public(path: Path) -> str:
    return path.relative_to(PROJECT / "public/models/hires").as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--dry-run", action="store_true", help="Run all guards and print actions without writing files")
    args = parser.parse_args()
    stage = args.stage.resolve()
    stage_manifest_path = stage / "manifest.json"
    preparation_path = stage / "source-preparation.json"
    validation_path = stage / "independent-validation.json"
    try:
        for path in (stage_manifest_path, preparation_path, validation_path, LIVE_MANIFEST):
            if not path.is_file():
                raise RuntimeError(f"Required input is missing: {path}")
        stage_manifest = read(stage_manifest_path)
        preparation = read(preparation_path)
        validation = read(validation_path)
        live = read(LIVE_MANIFEST)
        previous_manifest_sha = digest(LIVE_MANIFEST)
        if validation.get("status") != "pass":
            raise RuntimeError(f"Independent validation is not pass: {validation.get('status')!r}")
        if validation.get("mismatches"):
            raise RuntimeError("Independent validation reports mismatches")
        actual_stage_sha = digest(stage_manifest_path)
        if preparation.get("manifestSHA256") != actual_stage_sha:
            raise RuntimeError("source-preparation.json manifestSHA256 does not match stage manifest")
        validation_digests = validator_manifest_digests(validation)
        if validation_digests != {actual_stage_sha}:
            raise RuntimeError(f"Independent validation manifest SHA mismatch: {sorted(validation_digests)}")
        staged_patches = stage_manifest.get("patches")
        if not isinstance(staged_patches, list):
            raise RuntimeError("Stage manifest patches must be a list")
        staged_patch_count = len(staged_patches)
        preparation_owner_count = preparation.get("owners")
        validation_owner_count = validation.get("ownerCount")
        if not isinstance(preparation_owner_count, int) or preparation_owner_count < 0:
            raise RuntimeError("source-preparation.json owners must be a non-negative integer")
        if not isinstance(validation_owner_count, int) or validation_owner_count < 0:
            raise RuntimeError("independent-validation.json ownerCount must be a non-negative integer")
        if not (staged_patch_count == preparation_owner_count == validation_owner_count):
            raise RuntimeError(
                "Stage patch count does not match preparation owners and validation ownerCount: "
                f"{staged_patch_count}, {preparation_owner_count}, {validation_owner_count}"
            )
        live_patches = live.get("patches")
        if not isinstance(live_patches, list):
            raise RuntimeError("Live manifest patches must be a list")
        patches_before = len(live_patches)

        existing_patch_ids = {patch.get("id") for patch in live["patches"]}
        existing_owners = {patch.get("sourceAncestor") for patch in live["patches"] if patch.get("sourceAncestor")}
        existing_tiles = {
            tile.get("id")
            for patch in live["patches"]
            for level in (patch.get("levels") or {}).values()
            for tile in level.get("tiles", [])
            if tile.get("id")
        }
        stage_patch_ids = [patch.get("id") for patch in staged_patches]
        stage_owners = [patch.get("sourceAncestor") for patch in staged_patches]
        stage_tile_owners: dict[str, str] = {}
        stage_tiles = []
        for patch in staged_patches:
            for level in (patch.get("levels") or {}).values():
                for tile in level.get("tiles", []):
                    tile_id = tile.get("id")
                    if not tile_id:
                        continue
                    stage_tiles.append(tile_id)
                    prior_owner = stage_tile_owners.setdefault(tile_id, patch.get("id"))
                    if prior_owner != patch.get("id"):
                        raise RuntimeError(f"Tile occurs in multiple staged owners: {tile_id}")
        if len(stage_patch_ids) != len(set(stage_patch_ids)):
            raise RuntimeError("Duplicate staged patch id")
        if len(stage_owners) != len(set(stage_owners)):
            raise RuntimeError("Duplicate staged sourceAncestor")
        if existing_patch_ids & set(stage_patch_ids):
            raise RuntimeError(f"Patch id already exists: {sorted(existing_patch_ids & set(stage_patch_ids))}")
        if existing_owners & set(stage_owners):
            raise RuntimeError(f"sourceAncestor already exists: {sorted(existing_owners & set(stage_owners))}")
        if existing_tiles & set(stage_tiles):
            raise RuntimeError(f"Tile already exists: {sorted(existing_tiles & set(stage_tiles))[:5]}")

        # Optional row-level checks from the independent validator.  A validator
        # may use either the corridor-style rows schema or a patch/level map.
        validated_rows = {(row.get("id"), row.get("level")): row for row in validation.get("rows", []) if isinstance(row, dict)}
        for patch in staged_patches:
            if set((patch.get("levels") or {})) != {"high", "fine"}:
                raise RuntimeError(f"Patch lacks complete high/fine levels: {patch.get('id')}")
            for level_name, level in patch["levels"].items():
                mask = level.get("mask") or patch.get("mask")
                if not mask or not mask.get("sha256"):
                    raise RuntimeError(f"Missing mask digest: {patch.get('id')}/{level_name}")
                row = validated_rows.get((patch.get("id"), level_name))
                if row and row.get("maskSha256") and row["maskSha256"] != mask["sha256"]:
                    raise RuntimeError(f"Validator mask SHA mismatch: {patch.get('id')}/{level_name}")
                if level_name == "fine" and any(tile.get("originalError", tile.get("geometricError")) != 0 for tile in level.get("tiles", [])):
                    raise RuntimeError(f"Fine level is not terminal: {patch.get('id')}")

        source_dest = PROJECT / "public/models/hires/building-neighborhood/source"
        mask_dest = PROJECT / "public/models/hires/building-neighborhood/masks"
        descriptor_dest = PROJECT / "public/models/hires/building-neighborhood/descriptors"
        staged_tiles: dict[str, dict[str, Any]] = {}
        descriptors = []
        action_counts = {"sourcePlanned": 0, "sourceExisting": 0, "maskPlanned": 0, "maskExisting": 0, "descriptors": 0}
        rewritten_patches = []
        for original_patch in staged_patches:
            patch = copy.deepcopy(original_patch)
            for level_name, level in patch["levels"].items():
                mask = copy.deepcopy(level.get("mask") or patch.get("mask"))
                mask_file = source_for_mask(stage, mask)
                mask_target = mask_dest / f"{patch['id']}-{level_name}.png"
                action = checked_copy(mask_file, mask_target, mask["sha256"], args.dry_run)
                action_counts["maskExisting" if action == "existing" else "maskPlanned"] += 1
                mask["url"] = relative_public(mask_target)
                mask["localPath"] = str(mask_target)
                level["mask"] = mask
                for tile in level.get("tiles", []):
                    tile_id = tile["id"]
                    source = source_for_tile(stage, tile)
                    target = source_dest / f"{tile_id}.glb"
                    expected = tile["sha256"]
                    previous = staged_tiles.get(tile_id)
                    if previous and previous["sha256"] != expected:
                        raise RuntimeError(f"Same tile has different staged SHA: {tile_id}")
                    if not previous:
                        action = checked_copy(source, target, expected, args.dry_run)
                        action_counts["sourceExisting" if action == "existing" else "sourcePlanned"] += 1
                        staged_tiles[tile_id] = {
                            "sha256": expected,
                            "target": target,
                            "bytes": int(tile.get("sourceB3dmBytes", tile.get("bytes", 0))),
                        }
                    tile["url"] = relative_public(target)
                    tile["localPath"] = str(target)
                level["bytes"] = sum(int(tile.get("bytes", 0)) for tile in level.get("tiles", []))
                level["textureBytes"] = sum(int(tile.get("textureBytes", 0)) for tile in level.get("tiles", []))
                level["textureMipBytes"] = sum(int(tile.get("textureMipBytes", 0)) for tile in level.get("tiles", []))
                level["triangles"] = sum(int(tile.get("triangles", 0)) for tile in level.get("tiles", []))
            patch["mask"] = copy.deepcopy(patch["levels"]["high"]["mask"])
            descriptor = f"building-neighborhood/descriptors/{patch['id']}.json"
            patch["sourceManifest"] = descriptor
            rewritten_patches.append(patch)
            descriptors.append((descriptor_dest / f"{patch['id']}.json", patch))

        merged = copy.deepcopy(live)
        merged["patches"] = list(live["patches"]) + rewritten_patches
        patches_added = len(rewritten_patches)
        expected_patches_after = patches_before + patches_added
        if len(merged["patches"]) != expected_patches_after:
            raise RuntimeError(
                f"Merged manifest patch count is not before+added ({expected_patches_after}): "
                f"{len(merged['patches'])}"
            )
        merged["replacementPolicy"] = (live.get("replacementPolicy", "") + " Building-neighborhood source owners are complete L18 subtrees with validated high/fine frontiers; they are appended only when sourceAncestor and tile IDs are absent from the live manifest.").strip()
        merged["buildingNeighborhoodEvidence"] = str((EVIDENCE / "integration.json").relative_to(PROJECT))

        evidence_sources = [preparation_path, validation_path]
        if not args.dry_run:
            for path, descriptor in descriptors:
                write_json(path, descriptor)
                action_counts["descriptors"] += 1
            for source in evidence_sources:
                target = EVIDENCE / source.name
                checked_copy(source, target, digest(source), False)
            write_json(LIVE_MANIFEST, merged)
            integration = {
                "status": "source-assets-integrated; browser and visual acceptance pending",
                "stageManifestSha256": actual_stage_sha,
                "previousManifestSha256": previous_manifest_sha,
                "patchesBefore": patches_before,
                "patchesAdded": patches_added,
                "patchesAfter": len(merged["patches"]),
                "uniqueSourceTilesAdded": len(staged_tiles),
                "sourceFilesVerified": action_counts["sourcePlanned"] + action_counts["sourceExisting"],
                "maskFilesVerified": action_counts["maskPlanned"] + action_counts["maskExisting"],
                "descriptors": len(descriptors),
                "manifestPath": str(LIVE_MANIFEST.relative_to(PROJECT)),
                "evidence": [str((EVIDENCE / source.name).relative_to(PROJECT)) for source in evidence_sources],
            }
            integration["manifestSha256"] = digest(LIVE_MANIFEST)
            write_json(EVIDENCE / "integration.json", integration)
        summary = {
            "status": "dry-run-pass" if args.dry_run else "integrated",
            "stage": str(stage),
            "validator": validation.get("status"),
            "stageManifestSha256": actual_stage_sha,
            "patchesBefore": patches_before,
            "patchesAdded": patches_added,
            "patchesAfter": len(merged["patches"]),
            "uniqueSourceTiles": len(staged_tiles),
            "maskFiles": sum(len(p["levels"]) for p in rewritten_patches),
            "newCompressedBytes": sum(tile["bytes"] for tile in staged_tiles.values()),
            "writesSuppressed": args.dry_run,
        }
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, AssertionError) as error:
        print(json.dumps({"status": "blocked", "dryRun": args.dry_run, "reason": str(error)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
