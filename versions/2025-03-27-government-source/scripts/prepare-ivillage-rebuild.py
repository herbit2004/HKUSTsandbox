#!/usr/bin/env python3
"""Bounded, offline Hall X–XIII source preparation. Never writes runtime assets.

PYTHONPATH=/tmp/hkust-v3-deps python3 scripts/prepare-ivillage-rebuild.py
Coordinates are local x-east/y-up/z-south, not GeoJSON longitude/latitude.
Requires numpy, Pillow and shapely, plus the checked-in source geometry reader.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw
from shapely import contains_xy
from shapely.geometry import Polygon, MultiPolygon, mapping, box
from shapely.ops import unary_union

from hkust_source_geometry import geometry


CATALOG_IDS = [f"ug-hall-{n}" for n in range(10, 14)]
STEP = 0.5
MARGIN = 10.0
INVALID_INDEX = np.iinfo(np.uint32).max


def read_json(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def polygons(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for part in g.geoms for p in polygons(part)]


def feature(g, properties):
    return {"type": "Feature", "properties": properties, "geometry": mapping(g)}


def collection(features):
    return {"type": "FeatureCollection", "coordinateSystem": "Local x,z in metres; EPSG:2326 e=x+844800, n=820500-z. NOT WGS84.", "features": features}


def normalize_footprint(fp):
    changes = []
    raw_parts = []
    for part in fp["parts"]:
        p = Polygon(part["rings"][0], part["rings"][1:])
        assert np.isfinite(np.asarray([v for ring in part["rings"] for v in ring])).all()
        if not p.is_valid:
            repaired = p.buffer(0)
            changes.append(feature(p, {"catalogId": fp["catalogId"], "operation": "invalid-source-part-repaired-buffer0", "partIndex": part["partIndex"], "beforeArea": p.area, "afterArea": repaired.area}))
            p = repaired
        raw_parts.append(p)
    raw = unary_union(raw_parts)
    closed = raw.buffer(.4, join_style=2).buffer(-.4, join_style=2)
    for label, area in [("closing-added-area", closed.difference(raw)), ("closing-removed-area", raw.difference(closed))]:
        if not area.is_empty:
            changes.append(feature(area, {"catalogId": fp["catalogId"], "operation": label, "areaSquareMeters": area.area}))
    retained = []
    for component_index, p in enumerate(polygons(closed)):
        if p.area <= 5:
            changes.append(feature(p, {"catalogId": fp["catalogId"], "operation": "removed-component-at-most-5m2", "componentIndex": component_index, "areaSquareMeters": p.area}))
            continue
        holes = []
        for hole_index, ring in enumerate(p.interiors):
            h = Polygon(ring)
            if h.area > 9:
                holes.append(ring.coords)
            else:
                changes.append(feature(h, {"catalogId": fp["catalogId"], "operation": "filled-hole-at-most-9m2", "componentIndex": component_index, "holeIndex": hole_index, "areaSquareMeters": h.area}))
        kept = Polygon(p.exterior.coords, holes)
        simple = kept.simplify(.18, preserve_topology=True)
        # Simplification must not silently delete a retained hole or component.
        assert len(simple.interiors) == len(holes) and not simple.is_empty and simple.is_valid
        retained.append(simple)
        changes.append(feature(kept.symmetric_difference(simple), {"catalogId": fp["catalogId"], "operation": "simplify-0.18m-symmetric-difference", "componentIndex": component_index, "areaSquareMeters": kept.symmetric_difference(simple).area}))
    normalized = MultiPolygon(retained)
    assert normalized.is_valid and retained
    info = {"catalogId": fp["catalogId"], "officialBuildingId": fp["officialBuildingId"], "officialBuildingName": fp["officialBuildingName"], "source": fp["source"], "sourceFeatureIndex": fp["sourceFeatureIndex"], "sourceRole": fp["geometryRole"], "rawParts": len(raw_parts), "rawArea": raw.area, "normalizedArea": normalized.area, "components": len(retained), "retainedHoles": sum(len(p.interiors) for p in retained), "boundsXZ": list(normalized.bounds), "normalization": {"closingMeters": .4, "simplifyMeters": .18, "retainComponentAreaGreaterThan": 5, "retainHoleAreaGreaterThan": 9}, "adjustmentsRecorded": len(changes)}
    return raw, normalized, info, changes


def tree_frontier(project, patch, cache):
    path = project / patch["sourceOriginalTree"]
    if path not in cache:
        tree = read_json(path)
        nodes = {}
        def visit(n):
            uri = n.get("content", {}).get("uri", n.get("content", {}).get("url"))
            if uri:
                nodes[Path(uri).stem] = n
            for child in n.get("children", []):
                visit(child)
        visit(tree["root"])
        cache[path] = (nodes, sha(path))
    nodes, digest = cache[path]
    root = nodes[patch["sourceAncestor"].split("/")[-1]]
    leaves = []
    def terminal(n):
        children = n.get("children", [])
        if children:
            for child in children:
                terminal(child)
        else:
            uri = n.get("content", {}).get("uri", n.get("content", {}).get("url"))
            assert uri and n.get("geometricError", 0) == 0
            leaves.append(Path(uri).stem)
    terminal(root)
    actual = [t["id"].split("/")[-1] for t in patch["levels"]["fine"]["tiles"]]
    assert len(leaves) == len(set(leaves)) and sorted(leaves) == sorted(actual), patch["id"]
    return {"patchId": patch["id"], "sourceAncestor": patch["sourceAncestor"], "sourceTree": str(path.relative_to(project)), "sourceTreeSha256": digest, "fineTerminalCount": len(leaves), "matchesAllActualSourceTreeLeaves": True}


def sample_ground(grid, xx, zz):
    a = np.asarray(grid["heights"], dtype=np.float64).reshape(grid["rows"], grid["columns"])
    c = (xx + grid["origin"]["easting"] - grid["first_easting"]) / grid["easting_step"]
    r = (grid["origin"]["northing"] - zz - grid["first_northing"]) / grid["northing_step"]
    inside = (c >= 0) & (r >= 0) & (c <= a.shape[1]-1) & (r <= a.shape[0]-1)
    ci = np.clip(np.floor(c).astype(int), 0, a.shape[1]-2)
    ri = np.clip(np.floor(r).astype(int), 0, a.shape[0]-2)
    u, v = c-ci, r-ri
    nw, ne, sw, se = a[ri, ci], a[ri, ci+1], a[ri+1, ci], a[ri+1, ci+1]
    valid = inside & np.isfinite([nw, ne, sw, se]).all(axis=0)
    out = np.where(u+v <= 1, nw+(ne-nw)*u+(sw-nw)*v, se+(sw-se)*(1-u)+(ne-se)*(1-v))
    out[~valid] = np.nan
    return out


def rasterize(tris, normals, tile_indices, triangle_indices, xx, zz, ground, x0, z0):
    shape = xx.shape
    top = np.full(shape, np.nan)
    matched = np.full(shape, np.nan)
    hit_count = np.zeros(shape, np.uint32)
    top_src = np.full(shape, INVALID_INDEX, np.uint32)
    top_tri = top_src.copy()
    ground_src, ground_tri = top_src.copy(), top_src.copy()
    chosen = np.flatnonzero(normals[:, 1] >= .6)
    for counter, i in enumerate(chosen):
        t = tris[i]
        lo = np.ceil((t[:, [0, 2]].min(axis=0)-[x0, z0])/STEP-.5-1e-9).astype(int)
        hi = np.floor((t[:, [0, 2]].max(axis=0)-[x0, z0])/STEP-.5+1e-9).astype(int)
        c0, r0 = max(0, lo[0]), max(0, lo[1])
        c1, r1 = min(shape[1]-1, hi[0]), min(shape[0]-1, hi[1])
        if c0 > c1 or r0 > r1:
            continue
        s = np.s_[r0:r1+1, c0:c1+1]
        a, b, c = t
        den = (b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0])
        if abs(den) < 1e-14:
            continue
        dx, dz = xx[s]-a[0], zz[s]-a[2]
        u = (dx*(c[2]-a[2])-dz*(c[0]-a[0]))/den
        v = ((b[0]-a[0])*dz-(b[2]-a[2])*dx)/den
        valid = (u >= -1e-9) & (v >= -1e-9) & (u+v <= 1+1e-9)
        y = a[1]+u*(b[1]-a[1])+v*(c[1]-a[1])
        better = valid & (~np.isfinite(top[s]) | (y > top[s]))
        top[s][better], top_src[s][better], top_tri[s][better] = y[better], tile_indices[i], triangle_indices[i]
        hit_count[s] += valid
        delta = np.abs(y-ground[s])
        match = valid & (delta <= 1) & (~np.isfinite(matched[s]) | (delta < np.abs(matched[s]-ground[s])))
        matched[s][match], ground_src[s][match], ground_tri[s][match] = y[match], tile_indices[i], triangle_indices[i]
        if counter and counter % 100000 == 0:
            print(f"rasterized {counter}/{len(chosen)} upward source triangles", flush=True)
    return {"top": top, "ground": ground, "groundMatched": matched, "sourceTileIndex": top_src, "triangleIndex": top_tri, "groundSourceTileIndex": ground_src, "groundTriangleIndex": ground_tri, "upwardHitCount": hit_count, "x0": np.float64(x0), "z0": np.float64(z0), "step": np.float64(STEP)}


def stats(a):
    q = a[np.isfinite(a)]
    if not len(q):
        return {"finiteSamples": 0}
    bins = np.arange(math.floor(q.min()), math.ceil(q.max())+1.001)
    count, edges = np.histogram(q, bins=bins)
    return {"finiteSamples": len(q), "min": float(q.min()), "max": float(q.max()), "percentiles": {str(p): float(np.percentile(q, p)) for p in [1, 5, 25, 50, 75, 95, 99]}, "oneMeterHistogram": [{"min": float(a), "max": float(b), "count": int(n)} for a, b, n in zip(edges[:-1], edges[1:], count) if n]}


def validate_hits(positions, normals, source_indices, triangle_indices, grid, xx, zz):
    keys = source_indices.astype(np.uint64)*2**32 + triangle_indices
    assert len(np.unique(keys)) == len(keys)
    order = np.argsort(keys)
    result = {"uniqueOriginalTriangleReferences": len(keys)}
    for name, source_key, triangle_key in [("top", "sourceTileIndex", "triangleIndex"), ("groundMatched", "groundSourceTileIndex", "groundTriangleIndex")]:
        valid = np.isfinite(grid[name])
        assert not np.isinf(grid[name]).any()
        assert np.all(grid[source_key][~valid] == INVALID_INDEX)
        assert np.all(grid[triangle_key][~valid] == INVALID_INDEX)
        lookup = grid[source_key][valid].astype(np.uint64)*2**32 + grid[triangle_key][valid]
        found = order[np.searchsorted(keys[order], lookup)]
        assert np.array_equal(keys[found], lookup)
        a, b, c = positions[found, 0], positions[found, 1], positions[found, 2]
        dx, dz = xx[valid]-a[:, 0], zz[valid]-a[:, 2]
        den = (b[:, 0]-a[:, 0])*(c[:, 2]-a[:, 2])-(b[:, 2]-a[:, 2])*(c[:, 0]-a[:, 0])
        u = (dx*(c[:, 2]-a[:, 2])-dz*(c[:, 0]-a[:, 0]))/den
        v = ((b[:, 0]-a[:, 0])*dz-(b[:, 2]-a[:, 2])*dx)/den
        y = a[:, 1]+u*(b[:, 1]-a[:, 1])+v*(c[:, 1]-a[:, 1])
        max_error = float(np.max(np.abs(y-grid[name][valid]), initial=0))
        assert max_error < 1e-9 and (u >= -1e-8).all() and (v >= -1e-8).all() and (u+v <= 1+1e-8).all()
        assert (normals[found, 1] >= .6).all()
        result[name] = {"allFiniteHitsReconstructed": len(found), "maximumYReconstructionErrorMeters": max_error, "allHitsInsideOriginalTriangle": True, "allNormalsMeetSignedThreshold": True, "missingIndicesUseExplicitSentinel": True}
    matched = np.isfinite(grid["groundMatched"])
    assert (np.abs(grid["groundMatched"][matched]-grid["ground"][matched]) <= 1).all()
    return result


def preview(path, data, normalized, x0, z0, title):
    valid = np.isfinite(data)
    q = data[valid]
    lo, hi = (float(q.min()), float(q.max())) if len(q) else (0., 1.)
    f = np.clip(np.nan_to_num((data-lo)/max(1e-9, hi-lo)), 0, 1)
    palette = np.array([[27, 39, 90], [37, 125, 169], [82, 193, 177], [224, 217, 79], [243, 121, 58]], float)
    ix = np.minimum((f*4).astype(int), 3)
    mix = (f*4-ix)[..., None]
    colors = (palette[ix]*(1-mix)+palette[ix+1]*mix).astype(np.uint8)
    colors[~valid] = [232, 232, 236]
    scale = 3
    panel = Image.fromarray(colors).resize((data.shape[1]*scale, data.shape[0]*scale), Image.Resampling.NEAREST)
    im = Image.new("RGB", (panel.width+80, panel.height+100), "white")
    im.paste(panel, (40, 55))
    d = ImageDraw.Draw(im)
    d.text((16, 10), title, fill="black")
    d.text((16, 28), f"Actual source intersections; grey=no hit; height {lo:.2f}..{hi:.2f}m (source datum).", fill="black")
    for catalog_id, g in normalized.items():
        for p in polygons(g):
            for ring in [p.exterior, *p.interiors]:
                points = [(40+(x-x0)/STEP*scale, 55+(z-z0)/STEP*scale) for x, z in ring.coords]
                d.line(points, fill="black", width=2)
        p = g.representative_point()
        xy = (40+(p.x-x0)/STEP*scale, 55+(p.y-z0)/STEP*scale)
        d.rectangle([xy[0]-2, xy[1]-2, xy[0]+53, xy[1]+13], fill="white")
        d.text(xy, catalog_id.replace("ug-hall-", "Hall "), fill="black")
    d.text((16, im.height-30), f"x {x0:.1f}..{x0+data.shape[1]*STEP:.1f}; z {z0:.1f}..{z0+data.shape[0]*STEP:.1f}; 0.5m cell centres, z increases down.", fill="black")
    im.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("/tmp/hkust-ivillage-rebuild-source"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    project, out = args.project.resolve(), args.output.resolve()
    report_path = args.report or project / "docs/source-evidence-v4/ivillage-rebuild/source-preparation.json"
    assert not out.is_relative_to(project / "public"), "Evidence output must not overwrite runtime assets"
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    footprint_path = project / "public/data/building-footprints.json"
    interior_path = project / "public/interiors/manifest.json"
    manifest_path = project / "public/models/hires/manifest.json"
    ground_path = project / "public/terrain/height-grid-5m.json"
    manifest = read_json(manifest_path)
    all_fps = read_json(footprint_path)["footprints"]
    fps = [next(f for f in all_fps if f.get("catalogId") == i) for i in CATALOG_IDS]
    raw, normalized, mappings, changes, envelope_features = {}, {}, [], [], []
    floors = read_json(interior_path)["floors"]
    for fp in fps:
        i = fp["catalogId"]
        raw[i], normalized[i], info, adjusted = normalize_footprint(fp)
        changes.extend(adjusted)
        envelope_features.append(feature(normalized[i], info))
        floor_records = []
        for f in floors:
            if f["buildingId"] != fp["officialBuildingId"]:
                continue
            path = project / "public/interiors" / f["url"]
            source = read_json(path)
            assert source["buildingId"] == fp["officialBuildingId"]
            floor_records.append({"manifestEntry": f, "localPath": str(path), "sha256": sha(path), "source": source["source"], "sourceZMeaning": source["sourceZMeaning"], "rooms": [{k: room.get(k) for k in ["id", "sourceLocationId", "sourceFeatureId", "name", "interactive", "hiddenFromMap", "rings", "heightSourceZ"]} for room in source["rooms"]]})
        assert {f["manifestEntry"]["id"] for f in floor_records} == {f["id"] for f in fp["sourceFloorReferences"]}
        mappings.append({**info, "rawFootprint": fp, "floors": floor_records, "publishedFloorZValues": fp["observedFloorZLevels"], "ownershipPolicy": "Exact official building_id for footprint and floors only. Spatial source mesh/height samples do not establish building identity or roof storey count."})
    coords = np.asarray([p for f in fps for part in f["parts"] for ring in part["rings"] for p in ring])
    x0, z0 = np.floor((coords.min(axis=0)-MARGIN)/STEP)*STEP
    x1, z1 = np.ceil((coords.max(axis=0)+MARGIN)/STEP)*STEP
    width, height = int(round((x1-x0)/STEP)), int(round((z1-z0)/STEP))
    xx, zz = np.meshgrid(x0+(np.arange(width)+.5)*STEP, z0+(np.arange(height)+.5)*STEP)
    bbox = box(x0, z0, x1, z1)
    all_sources, tree_cache, frontier = {}, {}, []
    duplicates = []
    for patch in manifest["patches"]:
        level = patch["levels"]["fine"]
        assert level["completeSelectedSubtree"] and level["maximumOriginalError"] == 0
        frontier.append(tree_frontier(project, patch, tree_cache))
        for tile in level["tiles"]:
            # Legacy byte-preserved descriptors omit terminalLeaf; actual leaf
            # identity is independently proven against the original tree above.
            assert tile.get("terminalLeaf", True) and tile["originalError"] == 0
            assert len(tile["matrix"]) == 16 and np.isfinite(tile["matrix"]).all()
            path = manifest_path.parent / tile["url"]
            digest = sha(path)
            assert digest == tile["sha256"] and path.stat().st_size == tile["bytes"], str(path)
            if tile["id"] in all_sources:
                old = all_sources[tile["id"]]
                assert (tile["sha256"], tile["matrix"]) == (old["tile"]["sha256"], old["tile"]["matrix"])
                old["patchIds"].append(patch["id"])
                duplicates.append({"id": tile["id"], "additionalPatchId": patch["id"]})
            else:
                all_sources[tile["id"]] = {"tile": tile, "path": path, "patchIds": [patch["id"]]}
    selected = [r for _, r in sorted(all_sources.items()) if bbox.intersects(box(r["tile"]["bounds"]["min"][0], r["tile"]["bounds"]["min"][2], r["tile"]["bounds"]["max"][0], r["tile"]["bounds"]["max"][2]))]
    sources, batches, normal_batches, source_batches, triangle_batches, material_batches = [], [], [], [], [], []
    for index, record in enumerate(selected):
        tile, path = record["tile"], record["path"]
        triangles, materials = geometry(path, np.asarray(tile["matrix"], dtype=np.float64).reshape(4, 4, order="F"))
        assert len(triangles) == tile["triangles"] and np.isfinite(triangles).all()
        tri_min, tri_max = triangles.min(axis=1), triangles.max(axis=1)
        # Conservative AABB intersection retains complete crossing triangles, not centroid clipping.
        keep = (tri_max[:, 0] >= x0) & (tri_min[:, 0] <= x1) & (tri_max[:, 2] >= z0) & (tri_min[:, 2] <= z1)
        indices = np.flatnonzero(keep).astype(np.uint32)
        retained = triangles[keep]
        n = np.cross(retained[:, 1]-retained[:, 0], retained[:, 2]-retained[:, 0])
        length = np.linalg.norm(n, axis=1)
        n = np.divide(n, length[:, None], out=np.zeros_like(n), where=length[:, None] > 0)
        sources.append({"sourceTileIndex": index, **tile, "localPath": str(path), "patchIds": record["patchIds"], "retainedTriangleCount": len(retained), "retainedDegenerateTriangles": int((length == 0).sum()), "allTransformedBounds": {"min": triangles.min(axis=(0, 1)).tolist(), "max": triangles.max(axis=(0, 1)).tolist()}, "matrixPolicy": "Exact manifest column-major affine applied before all original glTF node transforms; no decomposition or additional axis/datum changes."})
        batches.append(retained)
        normal_batches.append(n)
        source_batches.append(np.full(len(retained), index, np.uint32))
        triangle_batches.append(indices)
        material_batches.append(materials[keep].astype(np.int32))
    positions, normals = np.concatenate(batches), np.concatenate(normal_batches)
    source_indices, triangle_indices, material_indices = np.concatenate(source_batches), np.concatenate(triangle_batches), np.concatenate(material_batches)
    print(f"validated {len(frontier)} complete owners / {len(all_sources)} unique fine files; extracted {len(positions)} triangles from {len(sources)} intersecting files", flush=True)
    np.savez_compressed(out / "terminal-triangles.npz", positions=positions, normals=normals, sourceTileIndex=source_indices, triangleIndex=triangle_indices, materialIndex=material_indices)
    ground_data = read_json(ground_path)
    ground = sample_ground(ground_data, xx, zz)
    grid = rasterize(positions, normals, source_indices, triangle_indices, xx, zz, ground, x0, z0)
    validation = validate_hits(positions, normals, source_indices, triangle_indices, grid, xx, zz)
    np.savez_compressed(out / "roof-grid.npz", **grid)
    regional_stats = []
    for f in fps:
        i = f["catalogId"]
        mask = contains_xy(normalized[i], xx, zz)
        near = contains_xy(normalized[i].buffer(MARGIN), xx, zz)
        np.save(out / f"{i}-envelope-grid-mask.npy", mask)
        counts = []
        for source_index, n in zip(*np.unique(grid["sourceTileIndex"][mask & np.isfinite(grid["top"])], return_counts=True)):
            counts.append({"sourceTileIndex": int(source_index), "topGridSamples": int(n)})
        regional_stats.append({"catalogId": i, "envelopeGridCells": int(mask.sum()), "topCoverageFraction": float(np.isfinite(grid["top"][mask]).mean()), "topSourceHeight": stats(grid["top"][mask]), "DTMGround": stats(ground[mask]), "topMinusDTM_UnconfirmedDatumCompatibility": stats((grid["top"]-ground)[mask]), "near10mTop": stats(grid["top"][near]), "groundMatchedWithin1m": stats(grid["groundMatched"][near]), "sourceContributions": counts})
    write_json(out / "normalized-envelopes.geojson", collection(envelope_features))
    write_json(out / "envelope-adjustments.geojson", collection(changes))
    write_json(out / "floor-footprint-mapping.json", {"version": 1, "buildings": mappings})
    write_json(out / "sources.json", {"version": 1, "coordinateSystem": manifest["coordinateSystem"], "source": manifest["source"], "sources": sources, "allRuntimeFineFrontiers": frontier, "duplicateSourceRecordsRemoved": duplicates})
    preview(out / "roof-grid.png", grid["top"], normalized, x0, z0, "Hall X-XIII / terminal source upward top surface (not classified roofs)")
    preview(out / "ground-grid.png", ground, normalized, x0, z0, "Hall X-XIII / CEDD 5m DTM triangulation sampled at 0.5m (HKPD)")
    preview(out / "ground-matched-grid.png", grid["groundMatched"], normalized, x0, z0, "Hall X-XIII / actual upward source face within 1m of DTM (not a fabricated plane)")
    artifacts = {p.name: {"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file() and p.name != "source-preparation.json"}
    report = {"version": 1, "status": "offline-source-stage-ready-not-a-runtime-or-visual-acceptance", "script": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__)), "geometryReaderSha256": sha(project / "scripts/hkust_source_geometry.py")}, "inputs": [{"path": str(p), "sha256": sha(p)} for p in [footprint_path, interior_path, manifest_path, ground_path]], "region": {"catalogIds": CATALOG_IDS, "rawFootprintBoundsXZ": [*coords.min(axis=0), *coords.max(axis=0)], "paddedAlignedBoundsXZ": [x0, z0, x1, z1], "marginMeters": MARGIN, "width": width, "height": height, "stepMeters": STEP, "cellCoordinate": "x=x0+(column+.5)*step; z=z0+(row+.5)*step; row increases z", "includesHallXWest581": bool(x0 < coords[:, 0].min() < 582)}, "geometry": {"retainedTriangles": len(positions), "sources": len(sources), "bytesOriginalSelectedFiles": sum(s["bytes"] for s in sources), "positionsDtype": str(positions.dtype), "normals": "Unit signed geometric normals from exact transformed source winding. Degenerate faces retained with zero normals. Roof/ground intersections require normal.y >= 0.6; downward faces never reoriented.", "upwardEligibleTriangles": int((normals[:, 1] >= .6).sum()), "downwardNearHorizontalTriangles": int((normals[:, 1] <= -.6).sum()), "finitePositionsAndNormals": bool(np.isfinite(positions).all() and np.isfinite(normals).all()), "triangleIndexMeaning": "Zero-based triangle in hkust_source_geometry.geometry concatenation for the unmodified source GLB. Entire intersecting triangle retained, even outside region bbox.", "deduplication": "Repeated source tile IDs require identical SHA and exact matrix and are read once. No fuzzy geometric merge or removal of cross-source coincident geometry."}, "frontierValidation": {"runtimeOwners": len(frontier), "actualUniqueFineSources": len(all_sources), "allSourceFilesShaAndBytesMatch": True, "all83OrCurrentOwnersComparedToOriginalTreeLeaves": True, "treeCount": len(tree_cache), "duplicateRecordsRemoved": len(duplicates), "scope": "Completeness against all installed runtime owners and their original source trees; not a claim that unavailable areas or later buildings exist in this source epoch."}, "grid": {"top": stats(grid["top"]), "ground": stats(ground), "groundMatched": stats(grid["groundMatched"]), "noData": "NaN heights and uint32 max source/triangle indices. No interpolation, inpainting or roof storey inference for top/groundMatched.", "groundSampler": {"source": str(ground_path), "sha256": sha(ground_path), "surveyDate": ground_data["survey_date"], "retrievedAt": ground_data["retrieved_at"], "sampleSpacingMeters": 5, "sourceResolutionMeters": .5, "method": "Same piecewise planar NW/SW/NE and NE/SW/SE triangle interpolation as createGridGroundSampler and runtime 5m DTM; all four source corners required; no extrapolation or NoData fill.", "verticalDatum": ground_data["origin"]["vertical_datum"]}, "groundMatchedPolicy": "Nearest actual upward-face vertical hit to the local DTM, with absolute source Y minus DTM <=1m. Raw surfaces may have another datum/epoch; this numerical match is not a classification or alignment correction."}, "regions": regional_stats, "normalizedEnvelopes": [f["properties"] for f in envelope_features], "artifacts": artifacts, "elapsedSeconds": round(time.monotonic()-started, 3), "limitations": ["Top is the highest actual upward photogrammetric triangle at each cell centre; vegetation, bridge/deck and old structures may be present. It is not a semantic roof mask.", "Government mesh revision date is not acquisition date. PathAdvisor 2D drawing and published floors are not a surveyed as-built shell.", "No textures, source geometry, production model, scene, stable entity IDs or runtime replacement masks changed.", "A source-domain intersection does not prove ownership of any particular face. No roof floor counts or fabricated floor Z values are inferred.", "Normalized drawing changes and omitted small components/holes are explicitly recorded in envelope-adjustments.geojson. Raw drawing and all published room polygons remain in floor-footprint-mapping.json.", "Ground is evidence for later wall-to-ground safety only; no ground rendering plane is generated."]}
    report["numericValidation"] = validation
    report["crossBuildingDrawingOverlap"] = [{"catalogIds": [a, b], "rawDrawingIntersectionAreaSquareMeters": raw[a].intersection(raw[b]).area, "normalizedIntersectionAreaSquareMeters": normalized[a].intersection(normalized[b]).area, "policy": "Overlap is retained as source evidence; it does not create a shared room, infer ownership or merge the two building IDs."} for index, a in enumerate(CATALOG_IDS) for b in CATALOG_IDS[index+1:] if raw[a].intersection(raw[b]).area > .01 or normalized[a].intersection(normalized[b]).area > .01]
    write_json(out / "source-preparation.json", report)
    write_json(report_path, report)
    print(json.dumps({"output": str(out), "report": str(report_path), "triangles": len(positions), "sourceFiles": len(sources), "gridShape": list(grid["top"].shape), "topCells": int(np.isfinite(grid["top"]).sum()), "elapsedSeconds": report["elapsedSeconds"]}), flush=True)


if __name__ == "__main__":
    main()
