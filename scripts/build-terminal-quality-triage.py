#!/usr/bin/env python3
"""Build a reproducible, offline terminal-source quality triage report.

This report deliberately measures source payloads and projection masks.  It does
not claim that a larger GLB or texture is visually better, and it never edits
runtime assets.  Run from the project root:

  python3 scripts/build-terminal-quality-triage.py

The default outputs are independent evidence files under docs/source-evidence-v4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - dependency is part of the workspace runtime
    raise SystemExit("Pillow is required to union the checked 0.5m masks") from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "public/models/hires/manifest.json"
DEFAULT_PLAN = ROOT / "docs/source-evidence-v4/building-quality/targeted-terminal-coverage-plan-u68.json"
DEFAULT_EXTERIORS = ROOT / "public/models/exteriors/manifest.json"
DEFAULT_REGISTRATION = ROOT / "docs/source-evidence-v4/current-form-registration.json"
DEFAULT_OUT = ROOT / "docs/source-evidence-v4/building-quality/terminal-quality-triage-u68.json"
DEFAULT_MD = ROOT / "docs/source-evidence-v4/building-quality/terminal-quality-triage-u68.md"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def mib(value: int | float) -> float:
    return round(float(value) / 1024 / 1024, 3)


def pct(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator * 100, 2) if denominator else None


def ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def normalize_building_id(entity_id: str) -> str:
    return entity_id.removeprefix("building:")


def source_stats(level: dict[str, Any]) -> dict[str, Any]:
    mask = level["mask"]
    return {
        "tiles": len(level["tiles"]),
        "triangles": level["triangles"],
        "vertices": sum(tile.get("vertices", 0) for tile in level["tiles"]),
        "glbBytes": level["bytes"],
        "glbMiB": mib(level["bytes"]),
        "textureRGBABytes": level["textureBytes"],
        "textureRGBAMiB": mib(level["textureBytes"]),
        "texturePixelsRGBA": level["textureBytes"] // 4,
        "textureMipBytes": level["textureMipBytes"],
        "textureMipMiB": mib(level["textureMipBytes"]),
        "maskPixels": mask["coveredPixels"],
        "maskAreaM2": round(mask["coveredPixels"] * mask["pixelSizeMeters"] ** 2, 3),
        "maskPixelSizeMeters": mask["pixelSizeMeters"],
        "maximumOriginalErrorMeters": level["maximumOriginalError"],
        "geometricErrorMaxMeters": level["geometricErrorMax"],
    }


def union_mask_area(root: Path, patches: list[dict[str, Any]], level_name: str) -> dict[str, Any]:
    """Union actual non-zero mask pixels in a local 0.5m integer grid."""
    if not patches:
        return {"pixels": 0, "areaM2": 0.0, "pixelSizeMeters": None, "boundsXZ": None}
    masks = [p["levels"][level_name]["mask"] for p in patches]
    pixel = masks[0]["pixelSizeMeters"]
    if any(abs(m["pixelSizeMeters"] - pixel) > 1e-9 for m in masks):
        raise ValueError(f"Mixed mask pixel sizes in {level_name}")
    min_x = min(m["minX"] for m in masks)
    min_z = min(m["minZ"] for m in masks)
    occupied: set[tuple[int, int]] = set()
    for patch in patches:
        m = patch["levels"][level_name]["mask"]
        mask_path = root / "public/models/hires" / m["url"]
        image = Image.open(mask_path).convert("L")
        if image.size != (m["width"], m["height"]):
            raise ValueError(f"Mask dimensions differ from manifest: {mask_path}")
        px = image.load()
        ox = round((m["minX"] - min_x) / pixel)
        oz = round((m["minZ"] - min_z) / pixel)
        for y in range(image.height):
            for x in range(image.width):
                if px[x, y] > 0:
                    occupied.add((ox + x, oz + y))
    max_x = max(m["maxX"] for m in masks)
    max_z = max(m["maxZ"] for m in masks)
    return {
        "pixels": len(occupied),
        "areaM2": round(len(occupied) * pixel * pixel, 3),
        "pixelSizeMeters": pixel,
        "boundsXZ": [min_x, min_z, max_x, max_z],
    }


def current_form_index() -> dict[str, dict[str, Any]]:
    """Read runtime registration plus the installed current-form manifests."""
    out: dict[str, dict[str, Any]] = {}
    manifests = [
        ROOT / "public/models/current-forms/ivillage-rebuild/manifest.json",
        ROOT / "public/models/current-forms/halls-current/manifest.json",
        ROOT / "public/models/current-forms/innovation/manifest.json",
        ROOT / "public/models/current-forms/hall2-corridor/manifest.json",
    ]
    for path in manifests:
        data = load(path)
        package = str(path.relative_to(ROOT))
        if "members" in data:
            for member in data["members"]:
                entity = member.get("entityId")
                if entity:
                    out.setdefault(entity, {"packages": []})["packages"].append({
                        "package": package,
                        "type": "current-form-set",
                        "status": data.get("status", "installed-set"),
                        "adoption": data.get("adoption"),
                        "asset": data.get("asset", {}).get("url"),
                        "assetBytes": data.get("asset", {}).get("bytes"),
                        "member": member.get("nodeName"),
                        "bounds": member.get("bounds"),
                    })
        for member in data.get("buildings", []):
            entity = member.get("entityId")
            if entity:
                out.setdefault(entity, {"packages": []})["packages"].append({
                    "package": package,
                    "type": "current-form-set",
                    "status": data.get("status", "installed-set"),
                    "adoption": data.get("adoption"),
                    "asset": data.get("asset", {}).get("url", member.get("url")),
                    "assetBytes": data.get("asset", {}).get("bytes", member.get("bytes")),
                    "member": member.get("nodeName", member.get("name")),
                    "bounds": member.get("bounds"),
                })
    # The corridor manifest is a space whose buildingId is Hall II.
    corridor = load(ROOT / "public/models/current-forms/hall2-corridor/manifest.json")
    for member in corridor.get("members", []):
        building = member.get("buildingId")
        if building:
            entity = f"building:{building}"
            out.setdefault(entity, {"packages": []})["packages"].append({
                "package": "public/models/current-forms/hall2-corridor/manifest.json",
                "type": "current-form-space",
                "status": corridor.get("status", "candidate"),
                "adoption": None,
                "asset": corridor.get("asset", {}).get("url"),
                "assetBytes": corridor.get("asset", {}).get("bytes"),
                "member": member.get("nodeName"),
                "bounds": member.get("bounds"),
            })
    return out


def exterior_index(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bundle in data.get("bundles", []):
        ids = []
        if bundle.get("buildingId"):
            ids.append(bundle["buildingId"])
        ids.extend(bundle.get("memberEntityIds", []))
        if bundle.get("entityId"):
            ids.append(bundle["entityId"])
        for ident in ids:
            normalized = ident.removeprefix("building:")
            out[normalized].append(bundle)
    return out


def classify_priority(row: dict[str, Any]) -> dict[str, Any]:
    """A transparent ranking heuristic, not a visual quality score."""
    score = 0
    reasons: list[str] = []
    current = row["currentForm"]
    delta = row["terminalVsHigh"]
    if current["present"]:
        score += 5
        reasons.append("current-form or bounded current-form space is present")
        if current["needsRuntimeVisualReview"]:
            score += 2
            reasons.append("current-form evidence is candidate/pending runtime review")
    if row["focusMembership"]:
        score += 3
        reasons.append("U68 named focus sample")
    if row["hires"]["missingOwnerCount"]:
        score += 2
        reasons.append("planned source owners are absent from current 167-owner manifest")
    if delta["textureRatio"] is not None and delta["textureRatio"] < 1.1:
        score += 2
        reasons.append("terminal texture pixel gain is below 10%; source may not improve visible sharpness")
    if delta["triangleRatio"] is not None and delta["triangleRatio"] < 1.1:
        score += 1
        reasons.append("terminal geometry triangle gain is below 10%")
    if score >= 8:
        level = "P0-current-form-or-coverage-review"
    elif score >= 5:
        level = "P1-visual-recheck"
    elif score >= 3:
        level = "P2-source-visual-sample"
    else:
        level = "P3-monitor"
    if current["needsPhotoRebuildReview"]:
        action = "photo-or-current-form-rebuild-review"
    elif delta["textureRatio"] is not None and delta["textureRatio"] < 1.1:
        action = "visual-recheck-plus-source-era-audit"
    else:
        action = "runtime-multi-angle-visual-recheck"
    return {"level": level, "score": score, "reasons": reasons, "requiredAction": action}


def make_report() -> dict[str, Any]:
    manifest = load(DEFAULT_MANIFEST)
    plan = load(DEFAULT_PLAN)
    exteriors = load(DEFAULT_EXTERIORS)
    registration = load(DEFAULT_REGISTRATION)
    registration_ids = {change.get("entityId") for change in registration.get("changes", [])}
    current_forms = current_form_index()
    exterior_by_id = exterior_index(exteriors)
    patches_by_id = {p["sourceAncestor"]: p for p in manifest["patches"]}

    rows: list[dict[str, Any]] = []
    referenced_owner_ids: set[str] = set()
    for item in plan["buildings"]:
        owner_ids = sorted({e["ownerId"] for e in item.get("intersectingOwnerEvidence", [])})
        referenced_owner_ids.update(owner_ids)
        patches = [patches_by_id[owner] for owner in owner_ids if owner in patches_by_id]
        missing = [owner for owner in owner_ids if owner not in patches_by_id]
        high = {k: sum(source_stats(p["levels"]["high"])[k] for p in patches) for k in [
            "tiles", "triangles", "vertices", "glbBytes", "textureRGBABytes", "texturePixelsRGBA",
            "textureMipBytes", "maskPixels", "maskAreaM2"]}
        fine = {k: sum(source_stats(p["levels"]["fine"])[k] for p in patches) for k in [
            "tiles", "triangles", "vertices", "glbBytes", "textureRGBABytes", "texturePixelsRGBA",
            "textureMipBytes", "maskPixels", "maskAreaM2"]}
        # Keep byte-derived MB next to the exact integer counters.
        for level in (high, fine):
            level["glbMiB"] = mib(level["glbBytes"])
            level["textureRGBAMiB"] = mib(level["textureRGBABytes"])
            level["textureMipMiB"] = mib(level["textureMipBytes"])
            level["maskAreaM2"] = round(level["maskAreaM2"], 3)
        high_union = union_mask_area(ROOT, patches, "high")
        fine_union = union_mask_area(ROOT, patches, "fine")
        domain_area = item.get("geometryAreaM2")
        bundles = []
        normalized = normalize_building_id(item["entityId"])
        for bundle in exterior_by_id.get(normalized, []):
            bundles.append({
                "id": bundle.get("id"),
                "name": bundle.get("buildingName", bundle.get("name")),
                "triangles": bundle.get("triangles"),
                "assetBytes": bundle.get("assetBytes"),
                "textureRGBABytes": bundle.get("textureDecodedBytes"),
                "textureMipBytes": bundle.get("textureMipBytes"),
                "sourceDates": bundle.get("sourceDates"),
                "matchRatios": {
                    "officialDrawingCoveredRatio": bundle.get("matchEvidence", {}).get("officialDrawingCoveredRatio"),
                    "sourceProjectionInsideOfficialRatio": bundle.get("matchEvidence", {}).get("sourceProjectionInsideOfficialRatio"),
                },
            })
        cf = current_forms.get(item["entityId"], {"packages": []})
        packages = cf.get("packages", [])
        needs_review = any(
            pkg.get("type") == "current-form-space"
            or pkg.get("status") not in (None, "installed-set")
            or (pkg.get("adoption") or {}).get("status", "").lower().find("pending") >= 0
            for pkg in packages
        )
        # The official-2026 i-Village references are current-state evidence but
        # dimensions/assignment remain approximations; keep that distinction.
        needs_photo_rebuild = any(
            "ivillage-rebuild" in pkg.get("package", "")
            or "innovation" in pkg.get("package", "")
            or pkg.get("type") == "current-form-space"
            for pkg in packages
        )
        row = {
            "canonicalId": item["entityId"],
            "name": item["name"],
            "scopeType": item.get("scopeType"),
            "status": item.get("status"),
            "focusMembership": item.get("focusMembership", []),
            "domainAreaM2": domain_area,
            "domainBoundsXZ": item.get("geometryBoundsXZ"),
            "hires": {
                "plannedOwnerCount": len(owner_ids),
                "mappedOwnerCount": len(patches),
                "missingOwnerCount": len(missing),
                "missingOwnerIds": missing,
                "ownerIds": owner_ids,
                "high": high,
                "fine": fine,
                "highUnionMask": high_union,
                "fineUnionMask": fine_union,
                "projectionToDomainInflationRatio": ratio(fine_union["areaM2"], domain_area or 0),
                "projectionToDomainPercent": pct(fine_union["areaM2"], domain_area or 0),
            },
            "terminalVsHigh": {
                "triangleRatio": ratio(fine["triangles"], high["triangles"]),
                "triangleGainPercent": pct(fine["triangles"] - high["triangles"], high["triangles"]),
                "glbByteRatio": ratio(fine["glbBytes"], high["glbBytes"]),
                "textureRatio": ratio(fine["textureRGBABytes"], high["textureRGBABytes"]),
                "texturePixelGainPercent": pct(fine["texturePixelsRGBA"] - high["texturePixelsRGBA"], high["texturePixelsRGBA"]),
                "textureMipRatio": ratio(fine["textureMipBytes"], high["textureMipBytes"]),
                "projectedUnionAreaGainPercent": pct(fine_union["areaM2"] - high_union["areaM2"], high_union["areaM2"]),
                "geometricErrorHighMeters": 1.75,
                "geometricErrorFineMeters": 0.0,
            },
            "exteriorBaseline": {
                "bundleCount": len(bundles),
                "bundles": bundles,
                "textureRGBABytes": sum(b.get("textureRGBABytes") or 0 for b in bundles),
                "texturePixelsRGBA": sum(b.get("textureRGBABytes") or 0 for b in bundles) // 4,
                "triangles": sum(b.get("triangles") or 0 for b in bundles),
            },
            "currentForm": {
                "present": bool(packages),
                "registrationEvidence": item["entityId"] in registration_ids,
                "needsRuntimeVisualReview": needs_review,
                "needsPhotoRebuildReview": needs_photo_rebuild,
                "packages": packages,
            },
            "sourceEra": {
                "terminalNative": {
                    "provider": manifest["source"]["title"],
                    "revisionDate": manifest["source"].get("revisionDate"),
                    "geometryCaptureDate": manifest["source"].get("geometryCaptureDate"),
                    "captureDateStatus": "unknown",
                },
                "individualExterior": [
                    b.get("sourceDates") for b in bundles if b.get("sourceDates")
                ],
            },
            "knownConstructionState": "see current-construction-status.json; this row has no row-specific construction assertion in that report",
        }
        row["triagePriority"] = classify_priority(row)
        rows.append(row)

    focus_names = {"曾超生楼", "林宝茹楼", "盧家驄大學中心", "本科生宿舍11座 · DJI Hall", "本科生宿舍12座", "本科生宿舍13座", "李家诚创科大楼"}
    for row in rows:
        if row["name"] in focus_names:
            row["focusSample"] = True
    all_manifest_owner_ids = set(patches_by_id)
    return {
        "version": 1,
        "status": "offline-source-quality-triage; visual-acceptance-not-claimed",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "canonicalRows": len(rows),
            "scopeTypes": {kind: sum(1 for r in rows if r["scopeType"] == kind) for kind in sorted({r["scopeType"] for r in rows})},
            "ownerManifestPatches": len(manifest["patches"]),
            "ownerManifestSha256": sha256(DEFAULT_MANIFEST),
            "planPath": str(DEFAULT_PLAN.relative_to(ROOT)),
            "planSha256": sha256(DEFAULT_PLAN),
            "currentFormRegistrationPath": str(DEFAULT_REGISTRATION.relative_to(ROOT)),
            "currentFormRegistrationSha256": sha256(DEFAULT_REGISTRATION),
            "planOwnerUnion": len(referenced_owner_ids),
            "manifestOwnersOutsideCanonicalPlan": len(all_manifest_owner_ids - referenced_owner_ids),
            "manifestOwnersOutsideCanonicalPlanIds": sorted(all_manifest_owner_ids - referenced_owner_ids),
        },
        "metricDefinitions": {
            "texturePixelsRGBA": "textureRGBABytes / 4; base-level uncompressed RGBA8 estimate, not compressed file bytes",
            "textureMipBytes": "manifest decoded texture base plus mip estimate; used as allocation proxy only",
            "projectedAreaM2": "non-zero pixels in the actual 0.5m mask union times 0.5m squared; no AABB/hull fill",
            "terminalVsHigh": "sum of fine owner payloads divided by corresponding high owner payloads; high=1.75m maximum source error, fine=0m",
            "visualBoundary": "metrics prove source payload/projection differences only; they do not prove facade sharpness, current form, topology, or correct owner identity",
            "priority": "transparent triage heuristic in classify_priority(); score is not a visual quality score. Projection/domain is reported as neighborhood projection inflation, never as building coverage.",
        },
        "sourceEpochs": {
            "nativeTerminal": {
                "provider": manifest["source"]["title"],
                "revisionDate": manifest["source"].get("revisionDate"),
                "geometryCaptureDate": manifest["source"].get("geometryCaptureDate"),
                "checkedAt": manifest["source"].get("checkedAt"),
            },
            "individualExteriors": {
                "dataset": exteriors.get("sourceDataset"),
                "checkedAt": exteriors.get("checkedAt"),
                "knownObjectTileRevision": "2026-04-24 where recorded; capture date unknown",
            },
            "currentForms": "See per-row package and adoption status. Official i-Village references are 2026-06/07 publication context; source geometry is explicitly approximate.",
        },
        "summary": {
            "rows": len(rows),
            "rowsWithMappedOwner": sum(1 for r in rows if r["hires"]["mappedOwnerCount"]),
            "rowsWithMissingOwner": sum(1 for r in rows if r["hires"]["missingOwnerCount"]),
            "rowsWithCurrentForm": sum(1 for r in rows if r["currentForm"]["present"]),
            "priorityCounts": {level: sum(1 for r in rows if r["triagePriority"]["level"] == level) for level in sorted({r["triagePriority"]["level"] for r in rows})},
        },
        "rows": rows,
        "limitations": [
            "An owner mask covers the source projection, which can include roads, trees, ground and neighboring buildings; it is not a building facade area or a coverage denominator.",
            "Summed owner payloads can overlap at source boundaries. Union mask area is reported separately and is the preferred projection-area metric.",
            "A larger terminal texture or triangle count does not establish clearer pixels, correct topology, or current construction state.",
            "Native Lands Department revision date is not a survey/acquisition date. Source era is reported as known/unknown rather than inferred.",
            "All rows require real multi-angle runtime inspection. Current-form or construction-state rows additionally require dated-photo/current-form visual review; metrics cannot decide whether a photo-based rebuild is faithful.",
            "This report does not modify app, public, GOAL, QA or preview assets.",
        ],
    }


def md(report: dict[str, Any]) -> str:
    rows = report["rows"]
    lines = [
        "# U68 terminal-source quality triage",
        "",
        f"Checked `{report['checkedAt']}` from the current offline workspace. This report joins {report['scope']['canonicalRows']} U68 canonical building/shared-zone rows to the current 167-owner hires manifest.",
        "",
        "The report measures exact manifest payloads and unions the actual non-zero 0.5m projection masks. `texturePixelsRGBA` is decoded base-level RGBA pixels (`textureBytes / 4`); it is not compressed file size. Fine/high ratios compare the terminal `originalError=0` frontier to the `maximumOriginalError=1.75m` high frontier. These are source-quality indicators, not visual sharpness scores.",
        "",
        "## Priority and evidence boundary",
        "",
        "Priority is a reproducible triage heuristic: current-form/candidate or mapped-owner gaps score highest, U68 named focus samples add weight, and <10% terminal texture/geometry gain adds a review flag. The reported projection/domain value is neighborhood projection inflation, not coverage. Every row still requires real runtime multi-angle inspection. Rows with current-form packages or known approximation/current-state sources need photo/current-form review before any rebuild decision.",
        "",
        "| Priority | Name | owners mapped/planned | fine projected union m² / domain m² | fine/high texture pixels | fine/high triangles | current-form | action |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (-x["triagePriority"]["score"], x["name"])):
        h, f = r["hires"]["high"], r["hires"]["fine"]
        c = r["currentForm"]
        current = "yes" if c["present"] else "no"
        if c["needsRuntimeVisualReview"]:
            current += " (review)"
        lines.append(
            f"| {r['triagePriority']['level']} ({r['triagePriority']['score']}) | {r['name']} | {r['hires']['mappedOwnerCount']}/{r['hires']['plannedOwnerCount']} | {r['hires']['fineUnionMask']['areaM2']:.1f} / {r['domainAreaM2']:.1f} | {f['texturePixelsRGBA']:,} / {h['texturePixelsRGBA']:,} ({r['terminalVsHigh']['texturePixelGainPercent']}%) | {f['triangles']:,} / {h['triangles']:,} ({r['terminalVsHigh']['triangleGainPercent']}%) | {current} | {r['triagePriority']['requiredAction']} |"
        )
    lines += [
        "",
        "## Focus samples",
        "",
    ]
    focus = [r for r in rows if r.get("focusSample")]
    for r in sorted(focus, key=lambda x: -x["triagePriority"]["score"]):
        lines.append(f"- **{r['name']}** — {r['triagePriority']['level']}; {', '.join(r['triagePriority']['reasons']) or 'no extra heuristic flag'}. Fine mask union is {r['hires']['fineUnionMask']['areaM2']:.1f}m² against official domain {r['domainAreaM2']:.1f}m²; terminal texture pixel gain is {r['terminalVsHigh']['texturePixelGainPercent']}%. {r['triagePriority']['requiredAction']}.")
    lines += [
        "",
        "## Source-era and current-state limits",
        "",
        f"- Native terminal source: `{report['sourceEpochs']['nativeTerminal']['revisionDate']}` revision; geometry capture date is explicitly unknown.",
        "- Individual exterior objects: manifest records a 2026-04-24 tile revision where available, with capture date generally unknown.",
        "- Hall XI–XIII current form: official i-Village completion references are 2026-06/07 publication context, while the current-form geometry states it is photograph-guided/approximate and awaits updated live review.",
        "- Innovation current form: 2026-03/04 official photo references are bound to an isolated candidate whose manifest says live browser acceptance is pending; this is a photo/current-form review item, not a proven replacement.",
        "- Hall II corridor: bounded current-form space candidate is tracked separately; its presence cannot prove the surrounding native source is clear.",
        "",
        "## Reproduction",
        "",
        "```sh",
        "python3 scripts/build-terminal-quality-triage.py",
        "```",
        "",
        "The JSON contains exact owner IDs, per-level triangle/GLB/texture/mask values, actual mask-union areas, current-form package/adoption states, source-era notes, and the heuristic reasons for every priority.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    report = make_report()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md.write_text(md(report), encoding="utf-8")
    print(json.dumps({"json": str(args.json), "md": str(args.md), "rows": len(report["rows"]), "owners": report["scope"]["ownerManifestPatches"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
