#!/usr/bin/env python3
"""Check that the two still-under-construction catalog rows stay unbound.

This is a read-only, deterministic boundary check.  A nearby whole-campus
photogrammetry tile is context only; it must not become a building owner until
an official footprint/source domain or an explicitly registered current-form
asset exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs/source-evidence-v4/building-quality/construction-owner-boundaries.json"
TARGETS = ("campus-20", "campus-27")


def read_json(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text())


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def all_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from all_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_dicts(child)


def contains_target(value: Any, target: str) -> bool:
    aliases = {target, f"building:catalog:{target}", f"building:{target}"}
    for row in all_dicts(value):
        for key in ("entityId", "canonicalId", "catalogId", "legacyCatalogId", "buildingId"):
            if row.get(key) in aliases:
                return True
        if target in row.get("id", "") if isinstance(row.get("id"), str) else False:
            return True
    return False


def fail(checks: list[dict[str, str]], target: str, message: str) -> None:
    checks.append({"target": target, "status": "fail", "message": message})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true", help="only set the exit status")
    args = parser.parse_args()

    evidence = json.loads(EVIDENCE_PATH.read_text())
    catalog = {row["id"]: row for row in read_json("public/data/catalog.json")["buildings"]}
    registry = {row["entityId"]: row for row in read_json("public/data/entity-registry.json")["entities"]}
    footprints = read_json("public/data/building-footprints.json")["footprints"]
    source_rows = {row["entityId"]: row for row in read_json("docs/source-evidence-v4/building-source-coverage.json")["buildings"]}
    native_rows = {row["canonicalId"]: row for row in read_json("docs/source-evidence-v4/building-quality/native-building-coverage.json")["rows"]}
    status_rows = {row["entityId"]: row for row in read_json("docs/source-evidence-v4/building-quality/current-construction-status.json")["rows"]}
    domains = []
    for relative in ("public/data/picking/building-domains.json", "public/data/picking/building-domains-extra.json"):
        domains.append(read_json(relative))
    exterior_manifest = read_json("public/models/exteriors/manifest.json")
    current_form_manifests = [
        read_json("public/models/current-forms/innovation/manifest.json"),
        read_json("public/models/current-forms/ivillage-rebuild/manifest.json"),
        read_json("public/models/current-forms/halls-current/manifest.json"),
    ]
    render_tiles = {row["id"]: row for row in read_json("public/models/render-manifest.json")["tiles"]}

    checks: list[dict[str, str]] = []
    evidence_entities = {row["canonicalId"]: row for row in evidence["entities"]}
    for target in TARGETS:
        canonical = f"building:catalog:{target}"
        c = catalog.get(target)
        e = registry.get(canonical)
        s = source_rows.get(canonical)
        n = native_rows.get(canonical)
        st = status_rows.get(canonical)
        ev = evidence_entities.get(canonical)
        if not all((c, e, s, n, st, ev)):
            fail(checks, target, "required catalog/registry/evidence row missing")
            continue

        if c.get("status") != "construction":
            fail(checks, target, f"catalog status is {c.get('status')!r}")
        if e.get("status") != "construction":
            fail(checks, target, f"registry status is {e.get('status')!r}")
        if e.get("identityStatus") != "catalog-name-only; exact physical footprint not resolved":
            fail(checks, target, "registry identity was promoted beyond catalog-name-only")
        representations = e.get("representations", [])
        if len(representations) != 1 or representations[0].get("type") != "reference_point":
            fail(checks, target, "registry has a non-reference representation")

        target_footprints = [row for row in footprints if row.get("catalogId") == target or row.get("officialBuildingId") == target]
        if target_footprints:
            fail(checks, target, f"{len(target_footprints)} footprint record(s) found")
        if any(contains_target(row, target) for row in domains):
            fail(checks, target, "picking source domain references target")
        if contains_target(exterior_manifest.get("bundles", []), target):
            fail(checks, target, "exterior manifest references target")
        if any(contains_target(row, target) for row in current_form_manifests):
            fail(checks, target, "current-form manifest references target")

        if s.get("pathAdvisorBuildingId") is not None or s.get("sourceFootprint") is not None:
            fail(checks, target, "source coverage contains a building owner/footprint")
        if s.get("exterior") is not None or s.get("sourceFloors"):
            fail(checks, target, "source coverage contains exterior/floor ownership")
        if s.get("classification") != "preview_only_without_building_attribution":
            fail(checks, target, "source classification is no longer point-only")
        if s.get("mappingStatus") != "point_context_only_not_verified_building_geometry":
            fail(checks, target, "source mapping status is no longer point-only")
        if n.get("domainSource") != "verified-reference-point-only" or n.get("individualBundle") is not None:
            fail(checks, target, "native coverage contains a domain or individual bundle")
        if n.get("existingRepresentations") != ["reference_point"]:
            fail(checks, target, "native coverage contains a non-reference representation")

        baseline = s.get("candidateBaselineAtFootprintOrPoint", {})
        tile_ids = baseline.get("tileIds", [])
        expected_tile = ev["baselineContext"]["tileId"]
        if baseline.get("association") != "reference_point_only" or tile_ids != [expected_tile]:
            fail(checks, target, "baseline source is not recorded as reference-point context")
        tile = render_tiles.get(expected_tile)
        if not tile:
            fail(checks, target, f"baseline tile {expected_tile} missing from render manifest")
        else:
            expected = ev["baselineContext"]
            if tile.get("triangles") != expected["triangles"] or tile.get("sha256") != expected["sha256"]:
                fail(checks, target, "baseline tile hash/triangle count differs from evidence")

        if st.get("status") != "construction" or st.get("completionConfirmed") is not False:
            fail(checks, target, "construction completion state changed")
        checks.append({"target": target, "status": "pass", "message": "construction/reference-point boundary intact; no owner promoted"})

    failed = [check for check in checks if check["status"] == "fail"]
    result = {
        "schemaVersion": 1,
        "status": "fail" if failed else "pass",
        "checkedAt": evidence.get("checkedAt"),
        "targets": list(TARGETS),
        "checks": checks,
        "sourceEvidence": str(EVIDENCE_PATH.relative_to(ROOT)),
        "readOnly": True,
        "productionFilesModified": False,
    }
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
