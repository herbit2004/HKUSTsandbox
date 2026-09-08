#!/usr/bin/env python3
"""Register the reviewed Hall II covered-corridor candidate.

The candidate is an independent ``space`` entity. This script copies the
offline evidence bundle, writes the v1 current-form manifest, and updates the
entity/resource registries deterministically. Its replacement mask is the
actual XZ projection of the candidate's continuous roof/deck triangles with a
vertical lower guard above the source hillside, rather than a buffered bridge
box or a source-owner guess.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


ENTITY_ID = "space:ug-hall-2-covered-corridor"
HALL_I = "building:68ec6a9f32cc78a7ddf5ddb8"
HALL_II_ENTITY = "building:68ec6b9632cc78a7ddf60beb"
HALL_II_SOURCE = "68ec6b9632cc78a7ddf60beb"
ASSET_SHA = "244fe21742422c19ab07d55d89c783388139521929e0bdbf25d6845652418943"
ASSET_BYTES = 303844
BOUNDS = {"min": [632.7, 60.6, -1552.89], "max": [707.3, 70.91, -1545.61]}
MASK_BOUNDS = {"min": [632.5, -1553.0], "max": [707.5, -1545.5]}
MASK_STEP = 0.5
MASK_MIN_Y = 60.0
MASK_MAX_Y = 71.2


def build_projection_mask(candidate: Path, destination: Path) -> dict:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[np.ndarray] = []
    material = ""
    for line in candidate.read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v":
            vertices.append(tuple(map(float, fields[1:4])))
        elif fields[0] == "usemtl":
            material = fields[1]
        elif fields[0] == "f" and material in {"deck", "underside", "roof", "roof_under"}:
            indices = [int(value.split("/")[0]) - 1 for value in fields[1:4]]
            triangles.append(np.asarray([vertices[index] for index in indices], dtype=float))
    min_x, min_z = MASK_BOUNDS["min"]
    max_x, max_z = MASK_BOUNDS["max"]
    width = round((max_x - min_x) / MASK_STEP)
    height = round((max_z - min_z) / MASK_STEP)
    coverage = np.zeros((height, width), dtype=np.uint8)
    centers_x = min_x + (np.arange(width) + .5) * MASK_STEP
    centers_z = min_z + (np.arange(height) + .5) * MASK_STEP
    for triangle in triangles:
        projected = triangle[:, [0, 2]]
        c0 = max(0, int(np.floor((projected[:, 0].min() - min_x) / MASK_STEP)))
        c1 = min(width, int(np.floor((projected[:, 0].max() - min_x) / MASK_STEP)) + 1)
        r0 = max(0, int(np.floor((projected[:, 1].min() - min_z) / MASK_STEP)))
        r1 = min(height, int(np.floor((projected[:, 1].max() - min_z) / MASK_STEP)) + 1)
        a, b, c = projected
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-10:
            continue
        for row in range(r0, r1):
            for column in range(c0, c1):
                p = np.array([centers_x[column], centers_z[row]])
                u = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / denominator
                v = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / denominator
                if u >= -1e-9 and v >= -1e-9 and u + v <= 1 + 1e-9:
                    coverage[row, column] = 255
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = coverage
    rgba[:, :, 1:3] = coverage[:, :, None]
    rgba[:, :, 3] = 255
    Image.fromarray(rgba).save(destination)
    return {
        "url": destination.name,
        "boundsXZ": MASK_BOUNDS,
        "width": width,
        "height": height,
        "pixelSizeMeters": MASK_STEP,
        "replacementMinY": MASK_MIN_Y,
        "replacementMaxY": MASK_MAX_Y,
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
        "projection": "Pixel-centre raster of actual candidate deck, underside and pitched-roof triangles; no bbox, hull, buffer or dilation.",
        "verticalGuard": "Removes competing source only from y=60.0 through 71.2; audited hillside around y=48 remains visible.",
        "occupiedPixels": int((coverage > 127).sum()),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            copy_tree(item, destination)
        else:
            shutil.copy2(item, destination)


def manifest(mask: dict) -> dict:
    return {
        "version": 1,
        "asset": {"url": "candidate.glb", "sha256": ASSET_SHA, "bytes": ASSET_BYTES},
        "members": [{
            "entityId": ENTITY_ID,
            "buildingId": HALL_II_SOURCE,
            "nodeName": "UG_Hall_II_Covered_Corridor_Candidate",
            "bounds": BOUNDS,
            "mask": {key: value for key, value in mask.items() if key not in {"projection", "verticalGuard", "occupiedPixels"}},
        }],
        "entityType": "space",
        "subtype": "covered_walkway_bridge_current_form_candidate",
        "coordinateSystem": {
            "crs": "EPSG:2326",
            "alreadyLocal": True,
            "originEN": [844800, 820500],
            "applyAdditionalTransform": False,
            "axes": "x=east; y=sourceZ; z=south",
        },
        "runtime": {
            "selectionEntityId": ENTITY_ID,
            "currentFormRegion": True,
            "pickAsIndependentEntity": True,
            "hideEntireGroupWhenOpenedBuildingId": HALL_II_SOURCE,
            "sourceReplacement": {
                "status": "active",
                "method": mask["projection"],
                "verticalGuard": mask["verticalGuard"],
                "occupiedPixels": mask["occupiedPixels"],
            },
            "fineOwnerDependency": False,
            "fineOwnerResolution": "Complete current-form region; does not request or depend on missing fine owners.",
        },
        "geometry": {
            "triangleCount": 2292,
            "surfaces": ["roof", "roof_under", "deck", "underside", "arch", "rail", "brace", "portal"],
            "sourceConstrained": True,
            "roadTreeReplacementGenerated": False,
        },
        "appearanceTextures": [],
        "evidence": {
            "userReport": "evidence/user-reported-corridor-gap.png",
            "officialReferences": [
                "reference/bridge-mid-2029.jpg",
                "reference/bridge-west-2028.jpg",
                "reference/Hall2-flags.jpg",
                "reference/Venue_signage_Oct2023.pdf",
            ],
            "sourceAudit": "source-evidence/corridor-coverage-check.json",
        },
        "status": "candidate",
        "limitations": [
            "Official photos establish bridge construction/features but are not metrically camera calibrated.",
            "Source y is retained geocentric mesh height; it is not certified HKPD.",
            "Endpoint passage and runtime visual acceptance remain pending.",
        ],
    }


def entity() -> dict:
    return {
        "entityId": ENTITY_ID,
        "type": "space",
        "name": "本科生宿舍2座上坡有盖连廊",
        "aliases": ["UG Hall II uphill covered corridor", "Hall II covered corridor", "Bridge Link"],
        "externalIds": {},
        "parentId": HALL_II_ENTITY,
        "primaryParent": HALL_II_ENTITY,
        "function": "covered walkway / bridge link",
        "bounds": BOUNDS,
        "sourceId": "hall2-corridor-candidate",
        "sourceTypes": ["official-panorama", "official-photo", "source-triangle-audit", "user-report"],
        "status": "candidate",
        "identityStatus": "mapped-candidate",
        "identityEvidence": "Official Hall II-labelled bridge photo and route document identify the independent bridge link; it remains a space entity rather than a Hall II building-body extension.",
        "containmentEvidence": "Spatially associated with Hall II and the west transition; no Hall II footprint enlargement is introduced.",
        "representations": [{
            "id": "rep:hall2-covered-corridor-current-form",
            "type": "mesh",
            "subtype": "covered_walkway_bridge_current_form_candidate",
            "asset": "/models/current-forms/hall2-corridor/candidate.glb",
            "sourceManifest": "/models/current-forms/hall2-corridor/manifest.json",
            "nodeName": "UG_Hall_II_Covered_Corridor_Candidate",
            "featureId": ENTITY_ID,
            "bounds": BOUNDS,
            "sourceId": "hall2-corridor-candidate",
            "evidence": "Segmented source-constrained roof/deck/side/end geometry assembled from the prepared Hall II corridor triangles and official bridge references.",
            "registration": "Independent selectable current-form facility; does not replace terrain, trees, roads, or the Hall II body.",
        }],
        "relations": [
            {"type": "connects", "targetId": HALL_I, "evidence": "Official west transition panorama; exact accessible route is not certified."},
            {"type": "connects", "targetId": HALL_II_ENTITY, "evidence": "Official Hall II panorama/route and east portal; exact accessible route is not certified."},
        ],
        "notes": [
            "Old source is hidden only under the candidate roof/deck projection and only above y=60.0; the lower hillside remains.",
            "Candidate does not certify navigability, as-built dimensions, or vertical datum.",
        ],
    }


def resources() -> list[dict]:
    base = "/models/current-forms/hall2-corridor/"
    return [
        {"resourceId": "photo:user-reported-hall2-corridor-gap", "type": "photo", "asset": base + "evidence/user-reported-corridor-gap.png", "name": "用户报告：Hall II有盖连廊中段断开", "sourceId": "user-report", "bindings": [{"relation": "depicts", "entityId": ENTITY_ID, "evidence": "User screenshot supplied with the repair request; location/orientation is interpreted with the source audit."}]},
        {"resourceId": "photo:hall2-corridor-bridge-mid", "type": "photo", "asset": base + "reference/bridge-mid-2029.jpg", "name": "Official PathAdvisor bridge panorama reference", "source": "https://navigate.ust.hk/path/api/app/assets/panorama/id?id=6a82af453d5b4a959cd859ff", "sourcePage": "https://navigate.ust.hk/path/app/", "sourceId": "pa-pano", "bindings": [{"relation": "depicts", "entityId": ENTITY_ID, "evidence": "Open sides, red braces/rails, white arch ribs, blue pitched roof and tiled parapets."}]},
        {"resourceId": "photo:hall2-corridor-bridge-west", "type": "photo", "asset": base + "reference/bridge-west-2028.jpg", "name": "Official west bridge transition panorama reference", "source": "https://navigate.ust.hk/path/api/app/assets/panorama/id?id=6a82af22dbe4ef95904c3682", "sourcePage": "https://navigate.ust.hk/path/app/", "sourceId": "pa-pano", "bindings": [{"relation": "depicts", "entityId": ENTITY_ID, "evidence": "Curved west transition, circular supports and tiled portal establish the endpoint form."}]},
        {"resourceId": "photo:hall2-corridor-flags", "type": "photo", "asset": base + "reference/Hall2-flags.jpg", "name": "Hall II official bridge photo", "source": "https://cmo.hkust.edu.hk/files/Hall2-flags.jpg", "sourceId": "photos", "bindings": [{"relation": "depicts", "entityId": ENTITY_ID, "evidence": "Hall II label and the same open-sided red-braced bridge vocabulary."}]},
        {"resourceId": "document:hall2-corridor-route", "type": "document", "asset": base + "reference/Venue_signage_Oct2023.pdf", "name": "Official Bridge Link route reference", "source": "https://registry.hkust.edu.hk/sites/default/files/2023-10/Venue_signage%20_Oct2023_0.pdf", "sourceId": "official-route", "bindings": [{"relation": "supportsIdentity", "entityId": ENTITY_ID, "evidence": "Route document labels the Bridge Link between the west lift and Hall II entrance."}]},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=Path("/tmp/hkust-hall2-corridor-repair"))
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    public = project / "public"
    target = public / "models/current-forms/hall2-corridor"
    if not (args.candidate / "candidate.glb").is_file():
        raise SystemExit(f"Missing candidate output: {args.candidate / 'candidate.glb'}")
    if sha256(args.candidate / "candidate.glb") != ASSET_SHA or (args.candidate / "candidate.glb").stat().st_size != ASSET_BYTES:
        raise SystemExit("Candidate GLB SHA/byte count differs from the reviewed output")
    copy_tree(args.candidate / "reference", target / "reference")
    copy_tree(args.candidate / "source-evidence", target / "source-evidence")
    for name in ["candidate.glb", "candidate-geometry-qa.json", "candidate-report.json", "01_west_to_east.png", "02_east_to_west.png", "03_underside.png", "04_plan.png"]:
        source = args.candidate / name
        if source.is_file():
            destination = target / (Path("evidence") / name if name.endswith(".png") or name.endswith(".json") and name != "candidate.glb" else name)
            # Preserve the production layout already used by the candidate bundle.
            if name == "candidate.glb": destination = target / name
            elif name in {"candidate-geometry-qa.json", "candidate-report.json"}: destination = target / "evidence" / name
            destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, destination)
    mask = build_projection_mask(args.candidate / "candidate.obj", target / "replacement.png")
    m = manifest(mask); (target / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
    registry_path = public / "data/entity-registry.json"; registry = json.loads(registry_path.read_text())
    entities = registry["entities"]; prior = next((e for e in entities if e["entityId"] == ENTITY_ID), None)
    if prior: entities[entities.index(prior)] = entity()
    else: entities.append(entity())
    # The legacy map is an exact catalog-row mapping; this independent space
    # has no catalog row and must never be added to that map.
    registry.setdefault("legacyMap", {}).pop("hall2-covered-corridor", None)
    counts = registry.setdefault("counts", {}); counts["entities"] = len(entities); counts.setdefault("byType", {})["space"] = sum(e["type"] == "space" for e in entities); counts["representations"] = sum(len(e.get("representations", [])) for e in entities); counts["hall2CorridorCandidates"] = 1
    # The global validator counts only the established complete-building
    # current-form subtypes. Keep this independent candidate out of that
    # denominator until its own review contract is promoted.
    counts["currentFormModels"] = sum(r.get("subtype") in {"unified_current_form_approximation", "public_floor_based_current_form_approximation", "photo_roof_based_current_form_approximation"} for e in entities for r in e.get("representations", []))
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    resource_path = public / "data/entity-resources.json"; resource_data = json.loads(resource_path.read_text()); resource_list = resource_data["resources"]
    additions = resources(); ids = {r["resourceId"] for r in resource_list}; resource_list[:] = [r for r in resource_list if r["resourceId"] not in {a["resourceId"] for a in additions}]; resource_list.extend(additions)
    resource_path.write_text(json.dumps(resource_data, ensure_ascii=False, indent=2) + "\n")
    registry["counts"]["photoResources"] = sum(r.get("type") == "photo" for r in resource_list)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"entityId": ENTITY_ID, "manifest": str(target / "manifest.json"), "resourcesAdded": len(additions), "replacedExistingEntity": prior is not None, "sourceReplacement": "active", "occupiedPixels": mask["occupiedPixels"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
