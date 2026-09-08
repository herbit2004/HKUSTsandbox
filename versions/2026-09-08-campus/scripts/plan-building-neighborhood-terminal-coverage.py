#!/usr/bin/env python3
"""Plan source terminal leaves around existing building domains.

This is a read-only planner.  It only reads the checked-in footprints, picking
domains, hires manifest, source tilesets and ZIP indexes.  Source owner and
leaf selection uses the projected convex hull of each real 3D Tiles bounding
volume (the same conservative projected-volume method used by
``prepare-hall-2-corridor.py``), never a campus-sized rectangle.  It does not
download, stage or modify runtime assets.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT / "docs/source-evidence-v4/building-quality/targeted-terminal-coverage-plan-u68.json"
CORRIDOR_BOUNDS = (607.0, -1560.0, 679.0, -1538.0)

# Focus labels are deliberate canonical IDs.  Name/alias substring matching
# would conflate Tsang Chiu Sang Tower with Tsang Shiu Tim Sports Centre, and
# Lam Po Yu Tower with the unrelated UG Hall VII alias.  Hall II is separately
# joined with the corridor AOI below.
FOCUS_ENTITY_IDS = {
    "Tsang": ("building:catalog:campus-32",),
    "Lam": ("building:catalog:campus-33",),
    "University Center": (
        "building:b00000000000000000000005",
        "building:b00000000000000000000006",
    ),
    "Hall II corridor surroundings": ("building:68ec6b9632cc78a7ddf60beb",),
    "Innovation": ("building:69201b741c838d03d9fbe71b",),
}


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique
    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def on_segment(a, b, p, tolerance=1e-9) -> bool:
    return abs(cross(a, b, p)) <= tolerance and min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance and min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance


def segments_intersect(a, b, c, d) -> bool:
    ab1, ab2, cd1, cd2 = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    if (ab1 > 1e-9 and ab2 < -1e-9 or ab1 < -1e-9 and ab2 > 1e-9) and (cd1 > 1e-9 and cd2 < -1e-9 or cd1 < -1e-9 and cd2 > 1e-9):
        return True
    return on_segment(a, b, c) or on_segment(a, b, d) or on_segment(c, d, a) or on_segment(c, d, b)


def point_in_ring(point, ring) -> bool:
    inside = False
    for index, current in enumerate(ring):
        previous = ring[index - 1]
        if on_segment(previous, current, point):
            return True
        if (current[1] > point[1]) != (previous[1] > point[1]):
            x = (previous[0] - current[0]) * (point[1] - current[1]) / (previous[1] - current[1]) + current[0]
            if point[0] < x:
                inside = not inside
    return inside


def segment_distance(a, b, c, d) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    def point_segment(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length2 = dx * dx + dy * dy
        if not length2:
            return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2))
        q = (start[0] + t * dx, start[1] + t * dy)
        return ((point[0] - q[0]) ** 2 + (point[1] - q[1]) ** 2) ** 0.5
    return min(point_segment(a, c, d), point_segment(b, c, d), point_segment(c, a, b), point_segment(d, a, b))


def bounds_intersect(first, second) -> bool:
    return not (first[2] < second[0] or second[2] < first[0] or first[3] < second[1] or second[3] < first[1])


class SimpleGeometry:
    """Small dependency-free polygon/multipolygon intersection helper."""
    def __init__(self, polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]]):
        self.polygons = polygons
        points = [point for outer, holes in polygons for ring in [outer, *holes] for point in ring]
        self._bounds = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)) if points else (0, 0, 0, 0)
        self.area = sum(abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2 for ring, _ in polygons) - sum(abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(hole, hole[1:]))) / 2 for _, holes in polygons for hole in holes)

    @property
    def bounds(self):
        return self._bounds

    def intersects(self, other) -> bool:
        if isinstance(other, BufferedGeometry):
            return other.intersects(self)
        if not bounds_intersect(self.bounds, other.bounds):
            return False
        for outer_a, holes_a in self.polygons:
            for outer_b, holes_b in other.polygons:
                rings_a, rings_b = [outer_a, *holes_a], [outer_b, *holes_b]
                if any(segments_intersect(a, b, c, d) for ring_a in rings_a for a, b in zip(ring_a, ring_a[1:]) for ring_b in rings_b for c, d in zip(ring_b, ring_b[1:])):
                    return True
                if outer_a and point_in_ring(outer_a[0], outer_b) and not any(point_in_ring(outer_a[0], hole) for hole in holes_b):
                    return True
                if outer_b and point_in_ring(outer_b[0], outer_a) and not any(point_in_ring(outer_b[0], hole) for hole in holes_a):
                    return True
        return False

    def buffer(self, distance: float):
        return BufferedGeometry(self, distance)


class BufferedGeometry:
    def __init__(self, base: SimpleGeometry, distance: float):
        self.base, self.distance = base, distance
        self.area = base.area
        self._bounds = (base.bounds[0] - distance, base.bounds[1] - distance, base.bounds[2] + distance, base.bounds[3] + distance)

    @property
    def bounds(self):
        return self._bounds

    def intersects(self, other: SimpleGeometry) -> bool:
        if not bounds_intersect(self.bounds, other.bounds):
            return False
        if self.base.intersects(other):
            return True
        for outer_a, holes_a in self.base.polygons:
            for outer_b, holes_b in other.polygons:
                for ring_a in [outer_a, *holes_a]:
                    for ring_b in [outer_b, *holes_b]:
                        if any(segment_distance(a, b, c, d) <= self.distance for a, b in zip(ring_a, ring_a[1:]) for c, d in zip(ring_b, ring_b[1:])):
                            return True
        return False


def box(*bounds):
    x0, y0, x1, y1 = bounds
    return SimpleGeometry([([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], [])])


def polygon_from_parts(parts: list[dict[str, Any]]):
    polygons = []
    for part in parts:
        rings = part.get("rings") or []
        if not rings or len(rings[0]) < 4:
            continue
        outer = [tuple(map(float, point)) for point in rings[0]]
        holes = [[tuple(map(float, point)) for point in ring] for ring in rings[1:]]
        polygons.append((outer, holes))
    if not polygons:
        return None
    return SimpleGeometry(polygons)


def normalize_id(value: str) -> str:
    return value.removesuffix(".b3dm").removesuffix(".glb")


def projected_volume(node: dict[str, Any], matrix: list[float]):
    """Return a projected 2D hull for a source node's oriented box.

    Older saved source tilesets use the 12-value ``sphere`` field for an
    oriented box.  Supporting both names keeps this equivalent to the source
    preparation scripts while remaining conservative for acquisition.
    """
    volume = node.get("boundingVolume", {})
    values = volume.get("box", volume.get("sphere"))
    if not values:
        return None
    if len(values) == 12:
        center = values[:3]
        axes = [values[3:6], values[6:9], values[9:12]]
        corners = [
            [center[i] + sum(signs[j] * axes[j][i] for j in range(3)) for i in range(3)]
            for signs in itertools.product((-1, 1), repeat=3)
        ]
    elif len(values) == 4:
        center, radius = values[:3], values[3]
        corners = [
            [center[0] + sx * radius, center[1] + sy * radius, center[2] + sz * radius]
            for sx, sy, sz in itertools.product((-1, 1), repeat=3)
        ]
    else:
        return None
    # Three.js matrices in the checked-in manifests are column-major.
    world = []
    for point in corners:
        world.append([
            sum(point[j] * matrix[j * 4 + i] for j in range(3)) + matrix[12 + i]
            for i in range(3)
        ])
    hull = convex_hull([(point[0], point[2]) for point in world])
    return SimpleGeometry([(hull + [hull[0]], [])]) if len(hull) >= 3 else None


def matrix_for_subtile(render_tiles: list[dict[str, Any]], sheet: str, sub: str):
    candidates = [tile for tile in render_tiles if tile.get("id", "").startswith(f"{sheet}/{sub}/")]
    if not candidates:
        return None, None
    matrices = {tuple(tile["matrix"]) for tile in candidates if tile.get("matrix")}
    if len(matrices) != 1:
        raise ValueError(f"Expected one placement matrix for {sheet}/{sub}, got {len(matrices)}")
    tile = sorted(candidates, key=lambda value: value["id"])[0]
    return list(next(iter(matrices))), tile["id"]


def terminal_nodes(node: dict[str, Any], path: tuple[str, ...] = ()):
    uri = (node.get("content") or {}).get("uri") or (node.get("content") or {}).get("url")
    current = path + ((uri,) if uri else ())
    children = node.get("children") or []
    if children:
        for child in children:
            yield from terminal_nodes(child, current)
    elif uri:
        yield node, current


def source_owners(node: dict[str, Any], path: tuple[str, ...] = ()):
    uri = (node.get("content") or {}).get("uri") or (node.get("content") or {}).get("url")
    current = path + ((uri,) if uri else ())
    if uri and "_L18_" in Path(uri).stem:
        yield node, current
        return
    for child in node.get("children") or []:
        yield from source_owners(child, current)


def aliases(entity: dict[str, Any]) -> str:
    values = [entity.get("name", "")]
    values.extend(entity.get("aliases") or [])
    values.extend(entity.get("externalIds", {}).get("legacyCatalogIds") or [])
    return " ".join(str(value) for value in values).casefold()


def exterior_evidence(entity: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose the registered exterior object bounds beside canonical polygons."""
    evidence = []
    for representation in entity.get("representations", []):
        if representation.get("type") != "mesh_group" or representation.get("subtype") != "exterior_bundle":
            continue
        for obj in representation.get("objects", []):
            bounds = obj.get("bounds") or {}
            minimum, maximum = bounds.get("min"), bounds.get("max")
            if not (isinstance(minimum, list) and isinstance(maximum, list) and len(minimum) >= 3 and len(maximum) >= 3):
                continue
            evidence.append({
                "objectId": obj.get("id"),
                "bundleId": representation.get("featureId") or entity.get("externalIds", {}).get("exteriorBundleId"),
                "asset": obj.get("asset"),
                "boundsXZ": [round(float(minimum[0]), 3), round(float(minimum[2]), 3), round(float(maximum[0]), 3), round(float(maximum[2]), 3)],
                "source": representation.get("asset") or "/models/exteriors/manifest.json",
            })
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buffer-meters", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.buffer_meters < 0:
        raise SystemExit("--buffer-meters must be non-negative")

    # Only these checked-in inputs are read.  In particular, no URL is opened.
    paths = {
        "registry": PROJECT / "public/data/entity-registry.json",
        "footprints": PROJECT / "public/data/building-footprints.json",
        "domains": PROJECT / "public/data/picking/building-domains.json",
        "domainsExtra": PROJECT / "public/data/picking/building-domains-extra.json",
        "hiresManifest": PROJECT / "public/models/hires/manifest.json",
        "renderManifest": PROJECT / "public/models/render-manifest.json",
    }
    registry = read(paths["registry"])
    footprint_data = read(paths["footprints"])
    domain_data = read(paths["domains"])
    extra_data = read(paths["domainsExtra"])
    hires = read(paths["hiresManifest"])
    render = read(paths["renderManifest"])
    entities = {entity["entityId"]: entity for entity in registry["entities"]}
    building_entities = {key: value for key, value in entities.items() if value.get("type") == "building"}

    excluded = []
    for entity_id, entity in sorted(building_entities.items()):
        status = str(entity.get("status") or "existing").casefold()
        if status in {"construction", "planned", "demolished", "reference-only", "reference_only"}:
            excluded.append({"entityId": entity_id, "name": entity.get("name"), "reason": f"status:{status}"})

    # Resolve footprints by PathAdvisor id or legacy catalog id.  Non-building
    # footprints (for example the outdoor pool) are retained in exclusions.
    by_path_id = {
        entity.get("externalIds", {}).get("pathAdvisorBuildingId"): entity_id
        for entity_id, entity in building_entities.items()
        if entity.get("externalIds", {}).get("pathAdvisorBuildingId")
    }
    by_catalog_id = {
        legacy_id: entity_id
        for entity_id, entity in building_entities.items()
        for legacy_id in entity.get("externalIds", {}).get("legacyCatalogIds", [])
    }
    geometry_parts: dict[str, list[dict[str, Any]]] = {}
    geometry_refs: dict[str, list[dict[str, Any]]] = {}

    def add_geometry(entity_id: str, parts: list[dict[str, Any]], ref: dict[str, Any]) -> None:
        if entity_id not in building_entities:
            return
        status = str(building_entities[entity_id].get("status") or "existing").casefold()
        if status in {"construction", "planned", "demolished", "reference-only", "reference_only"}:
            return
        geometry_parts.setdefault(entity_id, []).extend(parts)
        geometry_refs.setdefault(entity_id, []).append(ref)

    for footprint in footprint_data.get("footprints", []):
        entity_id = by_path_id.get(footprint.get("officialBuildingId")) or by_catalog_id.get(footprint.get("catalogId"))
        if entity_id:
            add_geometry(entity_id, footprint.get("parts", []), {
                "kind": "footprint",
                "id": footprint.get("id"),
                "catalogId": footprint.get("catalogId"),
                "officialBuildingId": footprint.get("officialBuildingId"),
                "source": footprint.get("source"),
            })
        else:
            excluded.append({"id": footprint.get("id"), "catalogId": footprint.get("catalogId"), "reason": "footprint-not-a-canonical-building"})

    domain_records = list(domain_data.get("domains", []))
    domain_records.extend(extra_data.get("domains", []))
    for domain in domain_records:
        entity_id = domain.get("entityId")
        if entity_id in building_entities:
            add_geometry(entity_id, domain.get("parts", []), {
                "kind": "building-domain",
                "physicalDomainId": domain.get("physicalDomainId"),
                "sourceBuildingId": domain.get("sourceBuildingId"),
                "sourceBuildingIds": domain.get("sourceBuildingIds"),
                "sourceFragments": [
                    {"sheet": fragment.get("sheet"), "sourceFile": fragment.get("sourceFile"), "sourceFileSha256": fragment.get("sourceFileSha256")}
                    for fragment in domain.get("sourceFragments", [])
                ],
            })

    # Aggregate domains are explicitly shared zones.  They participate in the
    # plan and are not silently discarded as non-building geometry.
    shared_zone_ids = set()
    for domain in extra_data.get("auditOnlyAggregateDomains", []):
        entity_id = domain.get("entityId")
        if entity_id not in entities or entities[entity_id].get("type") != "zone":
            continue
        shared_zone_ids.add(entity_id)
        geometry_parts.setdefault(entity_id, []).extend(domain.get("parts", []))
        geometry_refs.setdefault(entity_id, []).append({
            "kind": "shared-zone-domain",
            "physicalDomainId": domain.get("physicalDomainId"),
            "sourceBuildingId": domain.get("sourceBuildingId"),
            "sourceBuildingIds": domain.get("sourceBuildingIds"),
            "sourceFragments": [
                {"sheet": fragment.get("sheet"), "sourceFile": fragment.get("sourceFile"), "sourceFileSha256": fragment.get("sourceFileSha256")}
                for fragment in domain.get("sourceFragments", [])
            ],
        })

    shapes = {entity_id: polygon_from_parts(parts) for entity_id, parts in geometry_parts.items()}
    shapes = {entity_id: shape for entity_id, shape in shapes.items() if shape is not None}
    for entity_id in sorted(building_entities):
        if entity_id not in shapes:
            status = str(building_entities[entity_id].get("status") or "existing").casefold()
            reason = "status-excluded" if status in {"construction", "planned", "demolished", "reference-only", "reference_only"} else "no-existing-domain-or-footprint"
            if not any(item.get("entityId") == entity_id and item.get("reason") == reason for item in excluded):
                excluded.append({"entityId": entity_id, "name": building_entities[entity_id].get("name"), "reason": reason})

    selections = {entity_id: shape.buffer(args.buffer_meters) for entity_id, shape in shapes.items()}
    corridor = box(*CORRIDOR_BOUNDS)
    building_rows = {}
    for entity_id, shape in sorted(shapes.items()):
        entity = entities[entity_id]
        building_rows[entity_id] = {
            "entityId": entity_id,
            "name": entity.get("name"),
            "scopeType": "shared-zone" if entity_id in shared_zone_ids else "building",
            "status": entity.get("status") or "existing",
            "geometryAreaM2": round(shape.area, 3),
            "geometryBoundsXZ": [round(value, 3) for value in shape.bounds],
            "exteriorEvidence": exterior_evidence(entity),
            "bufferMeters": args.buffer_meters,
            "geometrySources": geometry_refs[entity_id],
            "intersectingOwnerEvidence": [],
            "focusMembership": [],
            "plannedOwnerIds": [],
            "plannedLeafIds": [],
        }

    published_owner_ids = {patch.get("sourceAncestor") for patch in hires.get("patches", []) if patch.get("sourceAncestor")}
    published_leaf_ids = {
        normalize_id(tile.get("id", ""))
        for patch in hires.get("patches", [])
        for level in (patch.get("levels") or {}).values()
        for tile in level.get("tiles", [])
        if tile.get("id")
    }
    render_tiles = render.get("tiles", [])
    owner_candidates: dict[str, dict[str, Any]] = {}
    corridor_owner_ids = set()
    missing_source_index = []
    unavailable_geometry = []
    source_region_count = 0

    for index_path in sorted((PROJECT / "source-geodata/mesh").glob("*/source-zip-index.json")):
        sheet = index_path.parent.name
        index = read(index_path)
        for tree_path in sorted(index_path.parent.glob("*/source-tileset.json")):
            sub = tree_path.parent.name
            matrix, baseline_id = matrix_for_subtile(render_tiles, sheet, sub)
            if matrix is None:
                unavailable_geometry.append({"sheet": sheet, "sub": sub, "reason": "no-render-manifest-placement"})
                continue
            source_region_count += 1
            tree = read(tree_path)
            for owner_node, owner_path in source_owners(tree.get("root", {})):
                owner_uri = owner_path[-1]
                owner_id = f"{sheet}/{sub}/{normalize_id(owner_uri)}"
                owner_shape = projected_volume(owner_node, matrix)
                if owner_shape is None:
                    unavailable_geometry.append({"ownerId": owner_id, "sourceTree": str(tree_path.relative_to(PROJECT)), "reason": "owner-volume-unreadable"})
                    continue
                corridor_hit = owner_shape.intersects(corridor)
                if corridor_hit:
                    corridor_owner_ids.add(f"{sheet}/{sub}/{normalize_id(owner_uri)}")
                matched = [entity_id for entity_id, selection in selections.items() if owner_shape.intersects(selection)]
                targets = [selections[entity_id] for entity_id in matched]
                if corridor_hit:
                    targets.append(corridor)
                if not targets:
                    continue
                owner_key = (sheet, sub, owner_id)
                owner_record = owner_candidates.setdefault(owner_id, {
                    "ownerId": owner_id,
                    "sheet": sheet,
                    "sub": sub,
                    "sourceAncestor": owner_id,
                    "sourceTree": str(tree_path.relative_to(PROJECT)),
                    "sourceTreeSha256": sha256(tree_path),
                    "sourceZipIndex": str(index_path.relative_to(PROJECT)),
                    "sourceZipIndexSha256": sha256(index_path),
                    "sourceBaselineId": baseline_id,
                    "sourceNodePath": list(owner_path),
                    "ownerBoundsXZ": [round(value, 3) for value in owner_shape.bounds],
                    "ownerGeometrySource": "projected oriented bounding-volume convex hull",
                    "entityIds": set(),
                    "corridorIntersects": False,
                    "candidateLeafIds": set(),
                    "publishedLeafIds": set(),
                    "missingLeafKeys": [],
                    "leaves": {},
                })
                owner_record["entityIds"].update(matched)
                owner_record["corridorIntersects"] = owner_record["corridorIntersects"] or corridor_hit
                published_owner = owner_id in published_owner_ids
                if published_owner:
                    owner_record["publishedOwner"] = True
                for entity_id in matched:
                    building_rows[entity_id]["intersectingOwnerEvidence"].append({
                        "ownerId": owner_id,
                        "ownerBoundsXZ": [round(value, 3) for value in owner_shape.bounds],
                        "sourceTree": str(tree_path.relative_to(PROJECT)),
                        "sourceTreeSha256": sha256(tree_path),
                        "sourceZipIndex": str(index_path.relative_to(PROJECT)),
                        "sourceZipIndexSha256": sha256(index_path),
                        "sourceNodePath": list(owner_path),
                        "publishedOwner": published_owner,
                    })
                for leaf_node, leaf_path in terminal_nodes(owner_node):
                    leaf_uri = leaf_path[-1]
                    leaf_id = f"{sheet}/{sub}/{normalize_id(leaf_uri)}"
                    leaf_shape = projected_volume(leaf_node, matrix)
                    if leaf_shape is None:
                        unavailable_geometry.append({"ownerId": owner_id, "leafId": leaf_id, "sourceTree": str(tree_path.relative_to(PROJECT)), "reason": "leaf-volume-unreadable"})
                        continue
                    if not any(leaf_shape.intersects(target) for target in targets):
                        continue
                    owner_record["candidateLeafIds"].add(leaf_id)
                    if published_owner or leaf_id in published_leaf_ids:
                        owner_record["publishedLeafIds"].add(leaf_id)
                        continue
                    source_key = f"{sub}/{leaf_uri}"
                    entry = index.get(source_key)
                    if not entry:
                        owner_record["missingLeafKeys"].append(source_key)
                        missing_source_index.append({
                            "ownerId": owner_id,
                            "leafId": leaf_id,
                            "sourceZipIndex": str(index_path.relative_to(PROJECT)),
                            "sourceZipKey": source_key,
                            "entityIds": sorted(matched),
                        })
                        continue
                    # A source leaf can be hit by multiple domains; retain one
                    # leaf row and merge all canonical owners into it.
                    leaf_record = owner_record["leaves"].setdefault(leaf_id, {
                        "leafId": leaf_id,
                        "sourceZipIndex": str(index_path.relative_to(PROJECT)),
                        "sourceZipIndexSha256": sha256(index_path),
                        "sourceZipKey": source_key,
                        "sourceZipEntry": {
                            "size": entry.get("size"),
                            "compressed": entry.get("compressed"),
                            "offset": entry.get("offset"),
                            "crc32": entry.get("crc32"),
                        },
                        "newCompressedBytes": int(entry.get("size") or 0),
                        "entityIds": set(),
                    })
                    leaf_record["entityIds"].update(matched)

    # Convert sets, deduplicate leaves globally and attach focus membership.
    owners = []
    for owner_id in sorted(owner_candidates):
        owner = owner_candidates[owner_id]
        for leaf in owner["leaves"].values():
            leaf["entityIds"] = sorted(leaf["entityIds"])
            leaf["focusSets"] = []
            for entity_id in leaf["entityIds"]:
                building_rows[entity_id]["plannedLeafIds"].append(leaf["leafId"])
        owner["entityIds"] = sorted(owner["entityIds"])
        owner["candidateLeafIds"] = sorted(owner["candidateLeafIds"])
        owner["publishedLeafIds"] = sorted(owner["publishedLeafIds"])
        owner["missingLeafKeys"] = sorted(set(owner["missingLeafKeys"]))
        owner["leaves"] = sorted(owner["leaves"].values(), key=lambda leaf: leaf["leafId"])
        owner["newCompressedBytes"] = sum(leaf["newCompressedBytes"] for leaf in owner["leaves"])
        owner["newLeafCount"] = len(owner["leaves"])
        owner["candidateTerminalLeafCount"] = len(owner["candidateLeafIds"])
        owner["publishedOwner"] = bool(owner.get("publishedOwner"))
        if owner["newLeafCount"]:
            owners.append(owner)
            for entity_id in owner["entityIds"]:
                building_rows[entity_id]["plannedOwnerIds"].append(owner_id)

    # Focus sets are intentionally named and small enough to be used as an
    # optional review queue.  Membership is exact canonical ID membership;
    # Hall II additionally includes the fixed corridor AOI owners explicitly.
    focus = {}
    for label, requested_ids in FOCUS_ENTITY_IDS.items():
        entity_ids = [entity_id for entity_id in requested_ids if entity_id in building_rows]
        candidate_owner_ids = sorted({owner_id for owner_id, owner in owner_candidates.items() if set(owner["entityIds"]) & set(entity_ids)})
        entity_owner_ids = list(candidate_owner_ids)
        focus_corridor_owner_ids = []
        if label == "Hall II corridor surroundings":
            focus_corridor_owner_ids = sorted(corridor_owner_ids)
            candidate_owner_ids = sorted(set(candidate_owner_ids) | set(focus_corridor_owner_ids))
        owner_ids = sorted({owner["ownerId"] for owner in owners if set(owner["entityIds"]) & set(entity_ids)})
        published_owner_ids = sorted({owner_id for owner_id in candidate_owner_ids if owner_candidates[owner_id].get("publishedOwner")})
        leaves = sorted({leaf["leafId"] for owner in owners if owner["ownerId"] in owner_ids for leaf in owner["leaves"]})
        published_leaves = sorted({leaf_id for owner_id in candidate_owner_ids for leaf_id in owner_candidates[owner_id]["publishedLeafIds"]})
        bytes_total = sum(leaf["newCompressedBytes"] for owner in owners if owner["ownerId"] in owner_ids for leaf in owner["leaves"])
        focus[label] = {
            "entityIds": sorted(entity_ids),
            "entityEvidence": [
                {
                    "entityId": entity_id,
                    "name": building_rows[entity_id]["name"],
                    "geometryBoundsXZ": building_rows[entity_id]["geometryBoundsXZ"],
                    "exteriorEvidence": building_rows[entity_id]["exteriorEvidence"],
                    "geometrySources": building_rows[entity_id]["geometrySources"],
                    "intersectingOwnerEvidence": building_rows[entity_id]["intersectingOwnerEvidence"],
                }
                for entity_id in sorted(entity_ids)
            ],
            "entityOwnerIds": sorted(entity_owner_ids),
            "corridorOwnerIds": focus_corridor_owner_ids,
            "ownerEvidence": [
                {
                    "ownerId": owner_id,
                    "ownerBoundsXZ": owner_candidates[owner_id]["ownerBoundsXZ"],
                    "sourceTree": owner_candidates[owner_id]["sourceTree"],
                    "sourceTreeSha256": owner_candidates[owner_id]["sourceTreeSha256"],
                    "sourceZipIndex": owner_candidates[owner_id]["sourceZipIndex"],
                    "sourceZipIndexSha256": owner_candidates[owner_id]["sourceZipIndexSha256"],
                    "sourceNodePath": owner_candidates[owner_id]["sourceNodePath"],
                    "entityIds": sorted(owner_candidates[owner_id]["entityIds"]),
                    "corridorIntersects": owner_candidates[owner_id]["corridorIntersects"],
                    "publishedOwner": owner_candidates[owner_id].get("publishedOwner", False),
                }
                for owner_id in candidate_owner_ids
            ],
            "candidateOwnerIds": candidate_owner_ids,
            "ownerIds": owner_ids,
            "publishedOwnerIds": published_owner_ids,
            "candidateLeafCount": len(set(leaves) | set(published_leaves)),
            "publishedLeafIds": published_leaves,
            "publishedLeafCount": len(published_leaves),
            "leafIds": leaves,
            "newLeafCount": len(leaves),
            "newCompressedBytes": bytes_total,
        }
        for entity_id in entity_ids:
            building_rows[entity_id]["focusMembership"].append(label)

    for label, details in focus.items():
        selected_owner_ids = set(details["ownerIds"]) | set(details["candidateOwnerIds"])
        for owner in owners:
            if owner["ownerId"] not in selected_owner_ids:
                continue
            for leaf in owner["leaves"]:
                leaf["focusSets"].append(label)

    for row in building_rows.values():
        row["plannedOwnerIds"] = sorted(set(row["plannedOwnerIds"]))
        row["plannedLeafIds"] = sorted(set(row["plannedLeafIds"]))
        row["intersectingOwnerEvidence"] = sorted(row["intersectingOwnerEvidence"], key=lambda item: item["ownerId"])
        row["focusMembership"] = sorted(row["focusMembership"])

    planned_leaves = [leaf for owner in owners for leaf in owner["leaves"]]
    output = {
        "version": 1,
        "planId": "targeted-terminal-coverage-plan-u68",
        "status": "read-only-source-plan",
        "generatedAt": "2026-09-07",
        "scope": {
            "bufferMeters": args.buffer_meters,
            "sourceSelection": "canonical existing building domains/footprints plus 10m configurable acquisition buffer; construction/reference-only excluded; shared-zone aggregate domains retained",
            "canonicalGeometryRows": len(building_rows),
            "sharedZoneRows": sum(row["scopeType"] == "shared-zone" for row in building_rows.values()),
            "focusEntityResolution": {label: list(entity_ids) for label, entity_ids in FOCUS_ENTITY_IDS.items()},
            "excludedCanonicalOrFootprints": excluded,
            "hallIICorridorBoundsXZ": list(CORRIDOR_BOUNDS),
        },
        "method": {
            "intersection": "projected oriented 3D Tiles bounding-volume convex hull in XZ, intersected with the exact checked-in building polygon buffered in meters; no campus AABB selection",
            "focusMatching": "exact canonical entity IDs listed in scope.focusEntityResolution; no name or alias substring matching",
            "terminalDefinition": "content-bearing source-tree leaf (no children), normally L19/L20/L21 descendants under an L18 source owner",
            "publishedDeduplication": "published sourceAncestor owners suppress their candidate leaves; remaining published leaf IDs are suppressed individually; every new leaf appears once globally",
            "bytes": "source-zip-index size field, the compressed b3dm payload size; no network or decompression",
            "localTriangleValidation": "No planned new terminal leaf has a local GLB in this checkout, so actual triangle intersections are 0; exact triangle validation remains a post-download QA step. Existing published owners/leaves are deduplicated before this new-byte plan.",
            "limitations": [
                "Projected source volumes are conservative acquisition evidence; after download, exact triangle projection and visual acceptance remain separate QA.",
                "A source ZIP index entry is required for every new plan leaf; missing keys are listed separately and have no byte estimate.",
            ],
        },
        "inputs": {
            key: {"path": str(path.relative_to(PROJECT)), "sha256": sha256(path)}
            for key, path in paths.items()
        },
        "summary": {
            "sourceRegionsRead": source_region_count,
            "sourceOwnersWithBuildingOrCorridorIntersection": len(owner_candidates),
            "publishedOwnersSuppressed": sum(bool(owner.get("publishedOwner")) for owner in owner_candidates.values()),
            "plannedOwners": len(owners),
            "plannedTerminalLeaves": len(planned_leaves),
            "uniquePlannedTerminalLeaves": len({leaf["leafId"] for leaf in planned_leaves}),
            "newCompressedBytes": sum(leaf["newCompressedBytes"] for leaf in planned_leaves),
            "missingSourceIndexEntries": len(missing_source_index),
            "unavailableGeometryNodes": len(unavailable_geometry),
            "localPlannedTerminalGlbs": 0,
            "actualTriangleIntersectionChecks": 0,
        },
        "buildings": [building_rows[key] for key in sorted(building_rows)],
        "focusSets": focus,
        "owners": [
            {
                **{key: value for key, value in owner.items() if key != "leaves"},
                "leaves": owner["leaves"],
            }
            for owner in owners
        ],
        "missingSourceIndex": missing_source_index,
        "unavailableGeometry": unavailable_geometry,
    }
    output["summary"]["newCompressedMiB"] = round(output["summary"]["newCompressedBytes"] / 2**20, 3)
    for item in output["owners"]:
        item["entityIds"] = sorted(item["entityIds"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
    print(compact({
        "plan": str(args.output.relative_to(PROJECT) if args.output.is_relative_to(PROJECT) else args.output),
        "canonical": len(building_rows),
        "sharedZones": output["scope"]["sharedZoneRows"],
        "owners": len(owners),
        "leaves": len({leaf["leafId"] for leaf in planned_leaves}),
        "newCompressedBytes": output["summary"]["newCompressedBytes"],
        "newCompressedMiB": output["summary"]["newCompressedMiB"],
        "missingIndex": len(missing_source_index),
        "publishedOwnersSuppressed": output["summary"]["publishedOwnersSuppressed"],
    }))


if __name__ == "__main__":
    main()
