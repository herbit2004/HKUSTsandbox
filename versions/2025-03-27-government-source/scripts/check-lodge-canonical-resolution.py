#!/usr/bin/env python3
"""Stable negative-boundary checks for the two mapped lodge services."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str):
    return json.loads((ROOT / relative).read_text())


def main() -> None:
    registry = {e["entityId"]: e for e in read("public/data/entity-registry.json")["entities"]}
    expected = {
        "facility:catalog:campus-44": ("building:catalog:campus-43", "1101775164"),
        "facility:catalog:campus-45": ("building:catalog:staff-quarters-tower-1", "1101775183"),
    }
    for entity_id, (parent_id, source_id) in expected.items():
        entity = registry.get(entity_id)
        assert entity and entity["type"] == "facility", entity_id
        assert entity.get("parentId") == parent_id, (entity_id, entity.get("parentId"))
        assert entity.get("representations") == [], entity_id
        assert not entity.get("externalIds", {}).get("exteriorBundleId"), entity_id
        assert not entity.get("externalIds", {}).get("exteriorObjectIds"), entity_id
        evidence = entity.get("officialContainmentEvidence", {})
        assert source_id in evidence.get("parentPhysicalDomainId", ""), entity_id
        assert entity.get("relations") == [], entity_id
    domains = read("public/data/picking/building-domains-extra.json")["domains"]
    assert {d["physicalDomainId"] for d in domains if d["entityId"] in expected} == set()
    audit = read("docs/source-evidence-v4/building-quality/lodge-canonical-resolution-u70.json")
    assert audit["status"] == "resolved-contained-service-no-independent-shell"
    assert {r["catalogId"] for r in audit["resolutions"]} == {"campus-44", "campus-45"}
    print(json.dumps({"status": "pass", "checked": sorted(expected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
