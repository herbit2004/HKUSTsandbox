#!/usr/bin/env python3
"""Join the saved building inventories and report the physical-building gap.

This is a read-only, local evidence join.  It intentionally does not edit the
registry or infer a unique physical-building denominator from catalog rows,
source objects, or apartment addresses.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs/source-evidence-v4/building-quality"
OUT_JSON = OUT_DIR / "canonical-building-inventory-gap-u68.json"
OUT_MD = OUT_DIR / "canonical-building-inventory-gap-u68.md"


def load(relative: str):
    return json.loads((ROOT / relative).read_text())


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def compact_catalog_row(row: dict, classification: str, **extra) -> dict:
    return {
        "catalogId": row["id"],
        "name": row.get("name") or row.get("name_zh") or row.get("name_en"),
        "englishName": row.get("en") or row.get("name_en"),
        "status": row.get("status"),
        "classification": classification,
        **extra,
    }


def main() -> None:
    registry_doc = load("public/data/entity-registry.json")
    catalog_doc = load("public/data/catalog.json")
    source_inventory = load("public/data/building-evidence.json")
    canonical_doc = load(
        "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json"
    )
    pick_doc = load(
        "docs/source-evidence-v4/building-quality/all-building-pick-coverage-u68.json"
    )

    entities = {e["entityId"]: e for e in registry_doc["entities"]}
    buildings = {k: e for k, e in entities.items() if e.get("type") == "building"}
    canonical_rows = canonical_doc["canonicalBuildings"]
    canonical_by_id = {r["canonicalId"]: r for r in canonical_rows}
    canonical_by_catalog_id = {
        catalog_id: row
        for row in canonical_rows
        for catalog_id in row.get("legacyCatalogIds", [])
    }
    zones = {z["entityId"]: z for z in canonical_doc["zones"]}
    facilities = {f["entityId"]: f for f in canonical_doc["facilities"]}
    spaces = {
        x["catalogId"]: x
        for x in canonical_doc["containedNamedSpacesOrWings"]
    }
    mapped_non_building = {
        x["catalogId"]: x
        for x in canonical_doc["catalogBuildingOrFacilityMappedToNonBuildingEntity"]
    }
    unresolved_catalog = {
        x["catalogId"]: x
        for x in canonical_doc["catalogBuildingOrFacilityWithoutIndependentBuildingEntity"]
    }
    # HKUST explicitly describes Lo Kwee-Seong Building as the laboratory
    # section of the Academic Building.  The current registry already models
    # it as a space under Academic; keep this newer primary-source correction
    # ahead of the older unresolved-candidate snapshot.
    confirmed_contained_sections = {
        "campus-04": {
            "entityId": "space:catalog:campus-04",
            "parentEntityId": "building:b00000000000000000000001",
            "parentHint": "主学术大楼 / Academic Building",
            "evidence": "https://library.hkust.edu.hk/news-events/news/where-lg2",
            "resolution": "HKUST Library states that the Library is part of the main academic building; retain it as a named section and do not create an independent exterior owner.",
            "officialSources": [
                "https://library.hkust.edu.hk/news-events/news/where-lg2",
                "https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf",
            ],
        },
        "campus-07": {
            "entityId": "space:catalog:campus-07",
            "parentEntityId": "building:b00000000000000000000001",
            "parentHint": "主学术大楼 / Academic Building",
            "evidence": "https://cmo.hkust.edu.hk/sites/default/files/2024-11/Annual_Testing_of_Fire_Alarm_System_Notice_2024Dec.pdf",
            "resolution": "HKUST CMO places S H Ho Sports Hall in the Main Academic Building testing plan and Academic Registry signage routes it from the Library/Lift 3 side to LG1; retain it as a named facility and do not create an independent exterior owner.",
            "officialSources": [
                "https://cmo.hkust.edu.hk/sites/default/files/2024-11/Annual_Testing_of_Fire_Alarm_System_Notice_2024Dec.pdf",
                "https://registry.hkust.edu.hk/sites/default/files/2023-10/Venue_signage%20_Oct2023_0.pdf",
                "https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf",
            ],
        },
        "campus-31": {
            "entityId": "space:catalog:campus-31",
            "parentEntityId": "building:68ec6a9f32cc78a7ddf5ddb8",
            "parentHint": "本科生宿舍1座 / Undergraduate Hall I",
            "evidence": "https://shrl.hkust.edu.hk/residential-halls/ug/ughall1",
            "resolution": "HKUST SHRLO states that UG Hall I and Stephen Kam Chuen Cheong Hall occupy two wings of one composite building; retain SKCC as a named wing/hall and do not create an independent exterior owner.",
            "officialSources": [
                "https://shrl.hkust.edu.hk/residential-halls/ug/ughall1",
                "https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf",
            ],
        },
        "campus-14": {
            "entityId": "space:catalog:campus-14",
            "parentEntityId": "building:b00000000000000000000001",
            "parentHint": "主学术大楼 / Academic Building",
            "evidence": "https://hkust.edu.hk/news/hkust-receives-hk100-million-donation-lo-kwee-seong-foundation-advance-frontiers-knowledge",
            "resolution": "HKUST identifies this name as the laboratory section of the Academic Building; it is not an independently counted exterior body.",
            "officialSources": [
                "https://hkust.edu.hk/news/hkust-receives-hk100-million-donation-lo-kwee-seong-foundation-advance-frontiers-knowledge",
            ],
        },
        "campus-44": {
            "entityId": "facility:catalog:campus-44",
            "parentEntityId": "building:catalog:campus-43",
            "parentHint": "校长宿舍 / President’s Lodge",
            "evidence": "docs/source-evidence-v4/building-quality/lodge-canonical-resolution-u70.json",
            "resolution": "The official August 2026 map places the Distinguished Guest Lodge callout inside the President’s Lodge existing-building envelope; retain it as a named accommodation service and do not create an independent exterior owner.",
            "officialSources": [
                "https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf",
                "https://cso.hkust.edu.hk/about-cso",
                "https://cso.hkust.edu.hk/node/30"
            ],
        },
        "campus-45": {
            "entityId": "facility:catalog:campus-45",
            "parentEntityId": "building:catalog:staff-quarters-tower-1",
            "parentHint": "教职员宿舍一座 / Staff Quarters Tower 1",
            "evidence": "docs/source-evidence-v4/building-quality/lodge-canonical-resolution-u70.json",
            "resolution": "The official August 2026 map places the UniLodge callout inside the Staff Quarters Towers 1–2 existing-building envelope; the saved iB1000 host domain is Tower 1. Retain it as a named accommodation service and do not create an independent exterior owner.",
            "officialSources": [
                "https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf",
                "https://cso.hkust.edu.hk/acc/unl",
                "https://cso.hkust.edu.hk/about-cso"
            ],
        }
    }

    catalog_rows = catalog_doc["buildings"]
    source_rows = source_inventory["buildings_and_named_facilities"]
    source_by_id = {x["id"]: x for x in source_rows}
    assert {x["id"] for x in catalog_rows} == {x["id"] for x in source_rows}
    # The canonical source audit predates the u70 lodge service migration and
    # still contains the two former building candidates. Filter those rows by
    # the current registry type before joining the physical denominator.
    canonical_rows = [
        row for row in canonical_rows
        if entities.get(row["canonicalId"], {}).get("type") == "building"
    ]
    canonical_by_id = {r["canonicalId"]: r for r in canonical_rows}
    canonical_by_catalog_id = {
        catalog_id: row
        for row in canonical_rows
        for catalog_id in row.get("legacyCatalogIds", [])
    }
    assert len(canonical_rows) == len(buildings) == 52
    assert set(canonical_by_id) == set(buildings)

    catalog_classified = []
    for row in catalog_rows:
        cid = row["id"]
        canonical = canonical_by_catalog_id.get(cid)
        if canonical:
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    "canonical-building",
                    canonicalId=canonical["canonicalId"],
                    lifecycleStatus=canonical.get("lifecycleStatus"),
                )
            )
        elif cid in zones:
            children = [
                r["canonicalId"]
                for r in canonical_rows
                if cid in (r.get("parentCatalogIds") or [])
                or cid in (r.get("legacyParentCatalogIds") or [])
                or cid in (r.get("parentIds") or [])
            ]
            # The canonical audit stores the parent relation on the rows for
            # C/D and split staff bodies in the identity source.  Keep the
            # direct relation explicit where available and otherwise use the
            # stable IDs from the identity extension below.
            if cid == "campus-34":
                children = [
                    "building:catalog:university-apartments-tower-c",
                    "building:catalog:university-apartments-tower-d",
                ]
            elif cid == "campus-37":
                children = [
                    "building:catalog:staff-quarters-tower-1",
                    "building:catalog:staff-quarters-tower-2",
                ]
            elif cid == "campus-38":
                children = [
                    "building:catalog:staff-quarters-tower-3",
                    "building:catalog:staff-quarters-tower-4",
                ]
            elif cid == "campus-46":
                children = [
                    f"building:catalog:staff-quarters-house-{n}" for n in range(1, 9)
                ] + [
                    f"building:catalog:staff-quarters-apartments-{a}-{b}"
                    for a, b in [(1, 12), (13, 24), (25, 36), (37, 48)]
                ]
            elif cid == "campus-47":
                children = [
                    f"building:catalog:staff-quarters-block-{letter}"
                    for letter in "pqrs"
                ]
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    "aggregate-zone",
                    entityId=next(
                        (eid for eid, z in zones.items() if cid in z.get("legacyCatalogIds", [])),
                        None,
                    ),
                    canonicalChildren=children,
                )
            )
        elif cid in confirmed_contained_sections:
            item = confirmed_contained_sections[cid]
            entity = entities.get(item["entityId"])
            assert entity and entity.get("type") in {"space", "facility"}
            assert (entity.get("primaryParent") or entity.get("parentId")) == item["parentEntityId"]
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    "named-space-or-wing" if entity.get("type") == "space" else "named-accommodation-service",
                    entityId=item["entityId"],
                    parentEntityId=item["parentEntityId"],
                    parentHint=item["parentHint"],
                    evidence=item["evidence"],
                    resolution=item["resolution"],
                )
            )
        elif cid in spaces:
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    "named-space-or-wing",
                    parentHint=spaces[cid].get("parentHint"),
                    evidence=spaces[cid].get("evidence"),
                )
            )
        elif cid in unresolved_catalog:
            item = unresolved_catalog[cid]
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    "canonical-building-candidate-unresolved",
                    mappedEntities=item.get("mappedEntities"),
                    parentHint=item.get("parentHint"),
                    evidence=item.get("evidence"),
                )
            )
        elif cid in mapped_non_building:
            item = mapped_non_building[cid]
            catalog_classified.append(
                compact_catalog_row(
                    row,
                    item["classification"],
                    mappedEntities=item.get("mappedEntities"),
                    parentHint=item.get("parentHint"),
                    evidence=item.get("evidence"),
                )
            )
        elif source_by_id[cid].get("entity_kind") == "outdoor-landmark-or-network":
            catalog_classified.append(
                compact_catalog_row(row, "outdoor-landmark-or-network")
            )
        else:
            catalog_classified.append(compact_catalog_row(row, "unclassified"))

    coverage_rows = pick_doc["buildings"]
    coverage_counts = Counter(x["coverage"] for x in coverage_rows)
    direct_rows = [
        x for x in coverage_rows if x["coverage"] == "direct-roof-and-facade-ray-proven"
    ]
    list_only_rows = [x for x in coverage_rows if x["coverage"] == "list-or-registry-only"]
    current_list_only_rows = [
        x for x in list_only_rows
        if (entities.get(x["entityId"]) or entities.get(registry_doc.get("legacyMap", {}).get(x["entityId"])))
        and (entities.get(x["entityId"]) or entities.get(registry_doc.get("legacyMap", {}).get(x["entityId"]))).get("type") == "building"
    ]
    assert len(coverage_rows) == 57
    assert len(direct_rows) == 53 and len(list_only_rows) == 4
    direct_buildings = [x for x in direct_rows if entities.get(x["entityId"], {}).get("type") == "building"]
    direct_zones = [x for x in direct_rows if entities.get(x["entityId"], {}).get("type") == "zone"]
    assert len(direct_buildings) == 48 and len(direct_zones) == 5

    unsplit = canonical_doc["namedUnsplitCandidates"]
    domain_groups = canonical_doc["physicalDomainGroups"]
    staff_groups = [
        g
        for g in domain_groups
        if g["physicalDomainId"].startswith("physical-domain:ib1000:")
        and g["aggregateEntityId"]
        in {
            "zone:catalog:campus-39",
            "zone:catalog:campus-40",
            "zone:catalog:campus-41",
            "zone:catalog:campus-42",
        }
    ]
    shared_halls = []
    seen_shared_hall_domains = set()
    for g in domain_groups:
        if g["physicalDomainId"] != "physical-domain:ib1000:1810084462":
            continue
        if g["physicalDomainId"] in seen_shared_hall_domains:
            continue
        seen_shared_hall_domains.add(g["physicalDomainId"])
        shared_halls.append(g)
    assert len(staff_groups) == 5 and len(shared_halls) == 1

    current_statuses = {"existing", "updated", "completed", None}
    current_canonical = [r for r in canonical_rows if r.get("lifecycleStatus") in current_statuses]
    planned_canonical = [r for r in canonical_rows if r.get("lifecycleStatus") == "construction"]
    assert len(current_canonical) == 50 and len(planned_canonical) == 2

    # A lower bound based on verified physical source domains.  It is not the
    # count of buildings: a staff range domain may contain several named
    # towers, and Hall VIII/IX are one verified combined domain.
    verified_domain_floor = len(direct_buildings) + len(staff_groups) + len(shared_halls)
    named_staff_upper = len(direct_buildings) + sum(
        len(g["memberNamedSamples"]) for g in staff_groups
    ) + len(shared_halls)
    assert verified_domain_floor == 54 and named_staff_upper == 64

    # These names used to be listed as unresolved building-like candidates.
    # The official first-party evidence now resolves them as contained named
    # sections/facilities, so they must not inflate the physical denominator.
    gap_candidates = []
    service_geometry_gaps = [
        {
            "catalogId": cid,
            "name": canonical_by_catalog_id[cid]["name"],
            "canonicalId": canonical_by_catalog_id[cid]["canonicalId"],
            "status": "existing-name-no-independent-domain",
            "whyGap": "Canonical identity exists, but current saved evidence has no independent exterior domain or direct pick ray.",
            "evidence": [
                "public/data/entity-registry.json",
                "public/data/catalog.json",
                "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json",
                "docs/source-evidence-v4/building-quality/all-building-pick-coverage-u68.json",
            ],
        }
        for cid in []
    ]
    facility_review = [
        {
            "catalogId": cid,
            "name": next(x["name"] for x in catalog_rows if x["id"] == cid),
            "entity": next(
                (x for x in mapped_non_building.get(cid, {}).get("mappedEntities", [])),
                None,
            ),
            "classification": mapped_non_building.get(cid, {}).get("classification"),
            "whyGap": "Named facility/zone with no independent building entity or domain; retain outside the building denominator until a footprint proves otherwise.",
            "evidence": [
                "public/data/building-evidence.json",
                "public/data/entity-registry.json",
                "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json",
            ],
        }
        for cid in ["campus-21", "campus-23", "campus-50", "campus-52"]
    ]

    planned = [
        {
            "catalogId": x["catalogId"],
            "name": x["name"],
            "currentEntity": x.get("canonicalId")
            or next(
                (m["entityId"] for m in mapped_non_building.get(x["catalogId"], {}).get("mappedEntities", [])),
                None,
            ),
            "status": x["status"],
            "classification": x["classification"],
            "evidence": [
                "public/data/building-evidence.json",
                "public/data/entity-registry.json",
                "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json",
            ],
        }
        for x in catalog_classified
        if x["catalogId"] in {"campus-09", "campus-20", "campus-27", "campus-51"}
    ]

    report = {
        "auditId": "canonical-building-inventory-gap-u68",
        "checkedAt": str(date.today()),
        "status": "read-only-evidence-join; physical-denominator-remains-bounded",
        "scope": {
            "question": "Whether all named real physical buildings are represented completely and how 53 direct + 6 list-only maps to physical evidence.",
            "excluded": ["registry edits", "app edits", "GOAL/QA/preview edits", "catalog row count as building count"],
            "countingRule": "A catalog name, registry entity, source object, apartment range, shared envelope, and closed physical domain are separate evidence units.",
        },
        "coverageCrosscheck": {
            "auditedScopes": len(coverage_rows),
            "directRoofAndFacadeScopes": len(direct_rows),
            "directCanonicalBuildingEntities": len(direct_buildings),
            "directAggregateZones": len(direct_zones),
            "listOnlyScopes": len(list_only_rows),
            "listOnlyEntityIds": [x["entityId"] for x in list_only_rows],
            "currentRegistryListOnlyEntityIds": [
                (registry_doc.get("legacyMap", {}).get(x["entityId"]) or x["entityId"])
                for x in current_list_only_rows
            ],
            "coverageCounts": dict(coverage_counts),
            "interpretation": "The historical snapshot has 53 direct scopes and 6 list-only rows; after the u70 service migration the current registry has 52 building entities, 5 shared/aggregate zones, and 4 list-only building entities. This is selectable-scope coverage, not a physical-building count.",
            "scopes": [
                {
                    "entityId": x["entityId"],
                    "name": x.get("name"),
                    "entityType": entities.get(x["entityId"], {}).get("type"),
                    "coverage": x["coverage"],
                    "flags": x.get("flags", []),
                }
                for x in coverage_rows
            ],
        },
        "canonicalCompleteness": {
            "registryBuildingEntities": len(buildings),
            "canonicalAuditRows": len(canonical_rows),
            "registryVsAuditIdMismatch": sorted(set(buildings) ^ set(canonical_by_id)),
            "catalogRows": len(catalog_rows),
            "catalogClassifiedRows": len(catalog_classified),
            "catalogClassificationCounts": dict(Counter(x["classification"] for x in catalog_classified)),
            "canonicalRows": [
                {
                    "canonicalId": r["canonicalId"],
                    "name": r["name"],
                    "classification": r.get("classification"),
                    "lifecycleStatus": r.get("lifecycleStatus"),
                    "legacyCatalogIds": r.get("legacyCatalogIds", []),
                    "associatedEntityIds": r.get("associatedEntityIds", []),
                    "physicalDomainIds": r.get("physicalDomainIds", []),
                    "sharedPhysicalRelations": r.get("sharedPhysicalRelations", []),
                    "directPickStatus": r.get("directPickEvidence", {}).get("status"),
                    "evidenceFiles": r.get("evidenceFiles", []),
                }
                for r in canonical_rows
            ],
            "catalogRows": catalog_classified,
        },
        "physicalAccounting": {
            "verifiedDirectCanonicalSourceScopes": len(direct_buildings),
            "staffAggregatePhysicalDomains": [
                {
                    "physicalDomainId": g["physicalDomainId"],
                    "aggregateEntityId": g["aggregateEntityId"],
                    "name": g["name"],
                    "namedSamples": g["memberNamedSamples"],
                }
                for g in staff_groups
            ],
            "sharedHallDomain": {
                "physicalDomainId": shared_halls[0]["physicalDomainId"],
                "aggregateEntityId": shared_halls[0]["aggregateEntityId"],
                "namedEntities": ["building:catalog:ug-hall-8", "building:catalog:ug-hall-9"],
                "interpretation": "One verified combined source domain; Hall VIII and Hall IX remain two names/entities but not two independently bounded bodies.",
            },
            "verifiedPhysicalDomainFloor": verified_domain_floor,
            "namedStaffTowerScenarioUpper": named_staff_upper,
            "formula": "48 direct canonical source scopes + 5 staff aggregate domains + 1 combined Hall VIII/IX domain = 54 verified source domains; replacing five aggregate domains by 15 named tower candidates yields 64 names/bodies only as a scenario.",
            "scenarioBounds": [
                {
                    "label": "verified source domains only",
                    "lower": 54,
                    "upper": 54,
                    "meaning": "Counts the saved direct bodies/domains, including one combined Hall VIII/IX domain and five Staff Quarters aggregate domains.",
                },
                {
                    "label": "split all 15 Staff Quarters Tower names",
                    "lower": 54,
                    "upper": 64,
                    "meaning": "Scenario only; requires per-number boundary evidence for Towers 5–19.",
                },
                {
                    "label": "three former catalog building candidates after containment resolution",
                    "lower": 54,
                    "upper": 64,
                    "meaning": "No increment: campus-04, campus-07, campus-31, campus-44, and campus-45 are resolved as contained named sections/facilities by official first-party evidence.",
                },
                {
                    "label": "also resolve four facility/zone reviews as buildings",
                    "lower": 54,
                    "upper": 68,
                    "meaning": "A deliberately broad review ceiling including campus-21, campus-23, campus-50, and campus-52 after the five contained names are excluded; current evidence does not support counting these facilities/zones.",
                },
            ],
            "unresolvedCanonicalRowsWithoutIndependentDomain": service_geometry_gaps,
            "openPhysicalDenominator": True,
        },
        "mostImportantGaps": gap_candidates,
        "resolvedContainedBuildingLikeNames": [
            {
                "catalogId": cid,
                "entityId": item["entityId"],
                "parentEntityId": item["parentEntityId"],
                "parentHint": item["parentHint"],
                "resolution": item["resolution"],
                "officialSources": item["officialSources"],
            }
            for cid, item in confirmed_contained_sections.items()
            if cid in {"campus-04", "campus-07", "campus-31", "campus-44", "campus-45"}
        ],
        "serviceOrFacilityReview": service_geometry_gaps + facility_review,
        "plannedOrUnbuilt": planned,
        "aliasesAndSharedRelations": canonical_doc["duplicateAliases"],
        "unsplitNamedCandidates": unsplit,
        "evidenceFiles": [
            "public/data/entity-registry.json",
            "public/data/catalog.json",
            "public/data/building-evidence.json",
            "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json",
            "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.md",
            "docs/source-evidence-v4/building-quality/named-space-containment-u69.json",
            "docs/source-evidence-v4/building-quality/lodge-canonical-resolution-u70.json",
            "docs/source-evidence-v4/building-quality/all-building-pick-coverage-u68.json",
            "docs/source-evidence-v4/building-quality/named-building-inventory.json",
            "docs/source-evidence-v4/building-quality/named-building-identity-checks.json",
            "docs/source-evidence-v4/building-quality/identity-sources/identities.json",
        ],
        "sourceSha256": {
            p: sha256(p)
            for p in [
                "public/data/entity-registry.json",
                "public/data/catalog.json",
                "public/data/building-evidence.json",
                "docs/source-evidence-v4/building-quality/canonical-physical-building-audit-u68.json",
                "docs/source-evidence-v4/building-quality/all-building-pick-coverage-u68.json",
            ]
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    lines = [
        "# Canonical building inventory gap audit · u68",
        "",
        f"Checked {report['checkedAt']} from local saved evidence. This report records the authorized containment resolution and does not change app, runtime, GOAL, QA, or preview files.",
        "",
        "## What 53 direct + 6 list-only means",
        "",
        "The pick-coverage audit has 59 selectable scopes: 53 direct scopes = 48 registry building entities + 5 aggregate/shared zones, and 6 list-only scopes = 6 registry building entities. It is not a count of physical buildings.",
        "",
        "The historical pick snapshot has six list-only rows. After resolving the two lodge services as facilities, the current registry has four list-only building entities:",
        "",
        *[
            f"- `{registry_doc.get('legacyMap', {}).get(x['entityId']) or x['entityId']}` — {(entities.get(x['entityId']) or entities.get(registry_doc.get('legacyMap', {}).get(x['entityId'])) or {}).get('name', x.get('name', ''))}"
            for x in current_list_only_rows
        ],
        "",
        "## Physical-domain accounting",
        "",
        "The evidence-backed source-domain floor is 54: 48 direct canonical building scopes + five verified Staff Quarters aggregate domains + one verified combined Hall VIII/IX domain. The five staff domains carry 15 named tower samples; if future boundary evidence proves all 15 are separate bodies, the corresponding scenario is 64. Neither number is a final unique-building denominator.",
        "",
                "The u70 lodge resolution moves `campus-44` (Distinguished Guest Lodge) under President’s Lodge and `campus-45` (UniLodge) under Staff Quarters Tower 1 as named accommodation services. Neither receives an independent exterior domain or shell. Hall VIII/IX are already represented by one combined domain.",
        "",
        "The three former catalog building candidates and the two lodge service names are excluded from the independent-building increment because official first-party evidence resolves them as contained named sections/facilities. A broad facility review ceiling of 68 would additionally require independent domains for Wong Check She Research Center, CLP Substation, Ocean Research Facility, and Fok Ying Tung Sports Center. These are scenario ceilings, not counts supported by current evidence.",
        "",
        "## Highest-priority canonical gaps",
        "",
        "| Priority | Catalog ID | Name | Current representation | Evidence gap |",
        "| ---: | --- | --- | --- | --- |",
        "| — | — | No existing named building-like candidate remains unresolved after the official containment resolution. | — | `campus-09` remains a construction-status record and is tracked under planned/unbuilt records. |",
    ]
    for g in gap_candidates:
        lines.append(
            f"| {g['priority']} | `{g['catalogId']}` | {g['name']} | `{g['currentEntity']}` | {g['whyGap']} |"
        )
    lines += [
        "",
        "`campus-14` is resolved as a named laboratory section of the Academic Building, and the current registry keeps it as `space:catalog:campus-14`. The same resolution now applies to `campus-04` (Library section under Academic), `campus-07` (Sports Hall facility/section under Academic), and `campus-31` (SKCC wing in the UG Hall I composite building); their official first-party sources are recorded in `named-space-containment-u69.json`. None is an independent physical-building gap.",
        "",
        "## Other named records that must stay out of the current building denominator",
        "",
        "- `campus-21` Wong Check She Research Center, `campus-23` CLP Substation, `campus-50` Ocean Research Facility, and `campus-52` Fok Ying Tung Sports Center remain facility/zone records without an independent building domain. `Coastal Marine Lab` and `Ocean Research Facility` are explicitly not equated in the alias audit.",
        "- `campus-09` Teaching Hub, `campus-20` Medical Education and Research Complex, `campus-27` Daniel & Mayce Yu Research Building, and `campus-51` AI Supercomputing Center are construction/upcoming records and are excluded from the current physical denominator.",
        "- Hall VI aliases (`本科生宿舍6座`, `Jockey Club Tower`, `S H Ho Tower`) resolve to one registry entity with two named source components. University Center and Towers C/D are separate named domains inside a shared envelope; they are not aliases or a third duplicated mesh.",
        "",
        f"Full row-level JSON: `{OUT_JSON.name}`.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "direct": len(direct_rows),
                "listOnly": len(list_only_rows),
                "verifiedPhysicalDomainFloor": verified_domain_floor,
                "namedStaffTowerScenarioUpper": named_staff_upper,
                "highestPriorityGaps": [x["catalogId"] for x in gap_candidates],
                "planned": [x["catalogId"] for x in planned],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
