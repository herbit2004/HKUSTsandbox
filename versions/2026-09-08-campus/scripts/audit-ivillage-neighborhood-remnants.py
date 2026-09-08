#!/usr/bin/env python3
"""Audit remaining Hall X-XIII photographic source components.

This is deliberately an audit only.  It does not delete or rewrite source
triangles.  Components are exact-source connected closures (any shared
source vertex within one source tile), then tested against the checked-in
current-form masks, source-protection mask, official footprint domains and the
0.5 m source DTM grid.  A component is a correction candidate only when the
geometry is still visible, clearly above the DTM, outside all current-form
domains, and has no inherited protection/correction evidence.  This report
does not promote a candidate to a correction without a visual/ray witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/tmp/hkust-ivillage-rebuild-source")
FORMS = ROOT / "public/models/current-forms/ivillage-rebuild"
DEFAULT_REPORT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.json"
DEFAULT_PNG = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.png"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point_in_polygon(x: float, z: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, zi) in enumerate(polygon):
        xj, zj = polygon[j]
        if ((zi > z) != (zj > z)) and x < (xj - xi) * (z - zi) / ((zj - zi) or 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    # Inclusive intersection is appropriate for ownership boundary contact.
    o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    eps = 1e-9
    return ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps) or abs(o1) <= eps) and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps) or abs(o3) <= eps)


def polygon_bbox_intersects(polygon: list[list[float]], xmin: float, zmin: float, xmax: float, zmax: float) -> bool:
    if any(xmin <= x <= xmax and zmin <= z <= zmax for x, z in polygon):
        return True
    if any(point_in_polygon(x, z, polygon) for x, z in [(xmin, zmin), (xmin, zmax), (xmax, zmin), (xmax, zmax)]):
        return True
    corners = [(xmin, zmin), (xmax, zmin), (xmax, zmax), (xmin, zmax)]
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        for j, c in enumerate(corners):
            if segments_cross(tuple(a), tuple(b), c, corners[(j + 1) % 4]):
                return True
    return False


def dsu_components(tile_indices: np.ndarray, positions: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """Return exact same-source-vertex components; no cross-tile joins."""
    out: list[tuple[int, np.ndarray]] = []
    for tile in np.unique(tile_indices):
        ids = np.flatnonzero(tile_indices == tile)
        tri = positions[ids]
        n = len(ids)
        # The stage is float64 after exact source transforms.  1e-6 m only
        # absorbs serialization noise; this is not a spatial proximity join.
        q = np.rint(tri / 1e-6).astype(np.int64).reshape(-1, 3)
        owners = np.repeat(np.arange(n), 3)
        order = np.lexsort((q[:, 2], q[:, 1], q[:, 0]))
        q, owners = q[order], owners[order]
        parent = np.arange(n)

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = int(parent[a])
            return a

        start = 0
        while start < len(q):
            end = start + 1
            while end < len(q) and np.array_equal(q[end], q[start]):
                end += 1
            root = find(int(owners[start]))
            for owner in owners[start + 1 : end]:
                other = find(int(owner))
                if other != root:
                    parent[other] = root
            start = end
        roots = np.array([find(i) for i in range(n)], dtype=np.int32)
        _, labels = np.unique(roots, return_inverse=True)
        for component in range(int(labels.max()) + 1):
            out.append((int(tile), ids[labels == component]))
    return out


def sample_mask(descriptor: dict, pixels: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Return RGBA at points, with -1 for points outside the mask."""
    x0, z0 = descriptor["boundsXZ"]["min"]
    step = float(descriptor["pixelSizeMeters"])
    cols = np.floor((points[:, 0] - x0) / step).astype(int)
    rows = np.floor((points[:, 2] - z0) / step).astype(int)
    ok = (rows >= 0) & (rows < pixels.shape[0]) & (cols >= 0) & (cols < pixels.shape[1])
    result = np.full((len(points), 4), -1, dtype=np.int32)
    result[ok] = pixels[rows[ok], cols[ok]].astype(np.int32)
    return result


def replacement_hits(manifest: dict, masks: list[np.ndarray], points: np.ndarray) -> np.ndarray:
    hit = np.zeros(len(points), dtype=bool)
    for member, pixels in zip(manifest["members"], masks):
        d = member["mask"]
        rgba = sample_mask(d, pixels, points)
        active = rgba[:, 0] >= 128
        lower = np.where(rgba[:, 3] == 255, float(d["replacementMinY"]), np.maximum(float(d["replacementMinY"]), rgba[:, 3]))
        hit |= active & (points[:, 1] >= lower) & (points[:, 1] <= float(d["replacementMaxY"]))
    return hit


def dtm_at(points: np.ndarray, grid: dict) -> np.ndarray:
    x0, z0, step = float(grid["x0"]), float(grid["z0"]), float(grid["step"])
    col = np.clip(np.rint((points[:, 0] - x0) / step).astype(int), 0, grid["ground"].shape[1] - 1)
    row = np.clip(np.rint((points[:, 2] - z0) / step).astype(int), 0, grid["ground"].shape[0] - 1)
    return grid["ground"][row, col]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--png", type=Path, default=DEFAULT_PNG)
    args = ap.parse_args()

    source = np.load(STAGE / "terminal-triangles.npz")
    positions = source["positions"]
    normals = source["normals"]
    tile_indices = source["sourceTileIndex"]
    triangle_indices = source["triangleIndex"]
    grid = dict(np.load(STAGE / "roof-grid.npz"))
    x0, z0 = float(grid["x0"]), float(grid["z0"])
    step = float(grid["step"])
    scope = (x0, z0, x0 + grid["ground"].shape[1] * step, z0 + grid["ground"].shape[0] * step)

    manifest = json.loads((FORMS / "manifest.json").read_text())
    masks = [np.asarray(Image.open(FORMS / m["mask"]["url"]).convert("RGBA")) for m in manifest["members"]]
    protection_desc = manifest["sourceProtection"]
    protection = np.frombuffer((FORMS / protection_desc["url"]).read_bytes(), np.uint8).reshape(protection_desc["height"], protection_desc["width"], 4)
    geometry = json.loads((FORMS / "evidence/geometry.json").read_text())
    envelopes: list[tuple[str, list[list[float]]]] = []
    for building in geometry["buildings"]:
        # Current evidence contains one simple outer ring per Hall.  Keep the
        # representation as source coordinates so this audit has no geometry
        # library or polygon simplification dependency.
        envelopes.append((building["catalogId"], building["envelopeParts"][0]["rings"][0]))

    # Existing positive reviews and already registered source corrections are
    # evidence to retain/revisit, not fresh deletion candidates.
    known_guard = set()
    review = json.loads((FORMS / "evidence/nonbuilding-source-review.json").read_text())
    for component in review.get("components", []):
        known_guard.update(int(i) for i in component.get("stagedTriangleIndices", []))
    protected = json.loads((FORMS / "evidence/protected-unattributed-volumes.json").read_text())
    known_guard.update(int(face["stagedTriangleIndex"]) for face in protected.get("faces", []))
    already_corrected = set()
    correction_dir = ROOT / "public/models/hires/source-corrections"
    for evidence in correction_dir.glob("*/evidence.json"):
        data = json.loads(evidence.read_text())
        for tile in data.get("sourceTiles", []):
            t = tile.get("sourceTileIndex")
            if t is None:
                continue
            already_corrected.update((int(t), int(i)) for i in tile.get("removedSourceTriangleIndices", []))

    components = dsu_components(tile_indices, positions)
    records = []
    for tile, ids in components:
        tri = positions[ids]
        centers = tri.mean(axis=1)
        # Four witnesses per triangle catches a boundary crossing that a
        # centroid-only test could miss while staying source-triangle based.
        witness_points = np.concatenate([centers, tri.reshape(-1, 3)], axis=0)
        visible_witness = ~replacement_hits(manifest, masks, witness_points)
        visible = visible_witness[: len(ids)]
        hidden = ~visible
        dtm = dtm_at(centers, grid)
        gaps = centers[:, 1] - dtm
        areas = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2.0
        area = np.maximum(areas, 1e-12)
        n = normals[ids]
        protection_rgba = sample_mask(protection_desc, protection, centers)
        protected_ground = (protection_rgba[:, 0] >= 1) & (np.abs(n[:, 1]) >= 0.60)
        lo, hi = tri.min(axis=(0, 1)), tri.max(axis=(0, 1))
        centroid = centers.mean(axis=0)
        env_intersects = [name for name, env in envelopes if polygon_bbox_intersects(env, float(lo[0]), float(lo[2]), float(hi[0]), float(hi[2]))]
        env_contains_centroid = [name for name, env in envelopes if point_in_polygon(float(centroid[0]), float(centroid[2]), env)]
        scoped = np.array([not (ti[:, 0].max() < scope[0] or ti[:, 0].min() > scope[2] or ti[:, 2].max() < scope[1] or ti[:, 2].min() > scope[3]) for ti in tri])
        if not np.any(scoped):
            continue
        scoped_ids = ids[scoped]
        known = int(np.count_nonzero(np.isin(scoped_ids, list(known_guard))))
        corrected = int(sum((tile, int(i)) in already_corrected for i in triangle_indices[scoped_ids]))
        ground_like = float(np.average((np.abs(gaps) <= 2.0) & (np.abs(n[:, 1]) >= 0.60), weights=area))
        above = float(np.average(gaps > 2.0, weights=area))
        hidden_fraction = float(np.average(hidden, weights=area))
        vertical_span = float(hi[1] - lo[1])
        horizontal_span = float(max(hi[0] - lo[0], hi[2] - lo[2]))
        # A conservative reason chain.  No visual colour classification is
        # used to approve a component; known terrain/canopy/retaining-wall
        # evidence and current-form ownership win over numerical suspicion.
        reasons = []
        if hidden_fraction >= 0.995:
            reasons.append("current-form-mask-covers-component")
        if env_contains_centroid:
            reasons.append("centroid-inside-official-current-form-envelope")
        elif env_intersects:
            reasons.append("component-bbox-intersects-official-current-form-envelope")
        if known:
            reasons.append("overlaps-existing-positive-nonbuilding-or-protected-review")
        if corrected:
            reasons.append("source-faces-already-removed-by-registered-correction")
        if int(np.count_nonzero(protected_ground)):
            reasons.append("source-protection-mask-witnesses-ground-compatible-surface")
        if ground_like >= 0.50 and float(np.nanpercentile(np.abs(gaps), 50)) <= 2.0:
            reasons.append("terrain-or-slope-compatible-with-source-dtm")
        if vertical_span >= 4.0 and above < 0.75:
            reasons.append("mixed-height-structure-or-canopy-needs-owner-proof")
        # Strict candidate gate.  A correction candidate is deliberately not
        # emitted here: without a stored live ray/visual witness ownership is
        # unresolved even when the numerical geometry looks suspicious.
        candidate_gate = (
            hidden_fraction < 0.995
            and not env_intersects
            and known == 0
            and corrected == 0
            and not np.any(protected_ground)
            and above >= 0.90
            and float(np.nanpercentile(gaps, 5)) > 2.0
            and vertical_span <= 8.0
            and n.shape[0] <= 1200
        )
        status = "review-candidate-no-correction" if candidate_gate else "rejected-or-retained"
        if not reasons:
            reasons.append("connected-source-structure-or-insufficient-positive-remnant-proof")
        source_info = json.loads((STAGE / "sources.json").read_text())["sources"][tile]
        records.append({
            "id": f"tile{tile}-component{len(records)}",
            "sourceTileIndex": tile,
            "sourceId": source_info["id"],
            "sourceUrl": source_info["url"],
            "triangleCount": int(len(ids)),
            "scopedTriangleCount": int(np.count_nonzero(scoped)),
            "scopedTriangleIndices": [int(i) for i in triangle_indices[scoped_ids]],
            "bounds": {"min": lo.tolist(), "max": hi.tolist()},
            "centroid": centroid.tolist(),
            "areaSquareMeters": float(areas.sum()),
            "verticalSpanMeters": vertical_span,
            "horizontalSpanMeters": horizontal_span,
            "dtmGapMeters": {"min": float(np.nanmin(gaps)), "p05": float(np.nanpercentile(gaps, 5)), "median": float(np.nanmedian(gaps)), "p95": float(np.nanpercentile(gaps, 95)), "max": float(np.nanmax(gaps))},
            "areaWeightedAbsNormalY": float(np.average(np.abs(n[:, 1]), weights=area)),
            "areaWeightedAboveDtmFraction": above,
            "areaWeightedDtmCompatibleFraction": ground_like,
            "sourceProtectionGroundWitnessCount": int(np.count_nonzero(protected_ground)),
            "currentFormVisibleTriangleCount": int(np.count_nonzero(visible)),
            "currentFormHiddenTriangleCount": int(np.count_nonzero(hidden)),
            "currentFormHiddenAreaFraction": hidden_fraction,
            "currentFormMaskedVertexWitnessCount": int(np.count_nonzero(~visible_witness[len(ids):])),
            "officialEnvelopeIntersections": env_intersects,
            "officialEnvelopeCentroidContainment": env_contains_centroid,
            "knownGuardTriangleCount": known,
            "alreadyCorrectedTriangleCount": corrected,
            "status": status,
            "reasons": reasons,
            "correctionCandidate": False,
            "correctionCandidateBlockers": ["no independent live multi-angle ray/visual owner witness recorded in this audit"],
        })

    candidates = [r for r in records if r["status"] == "review-candidate-no-correction"]
    summary = {
        "status": "audit-complete-no-runtime-write",
        "task": "G39 Hall X-XIII full-neighborhood remaining floating photographic source audit",
        "scope": {"boundsXZ": [x0, z0, x0 + grid["ground"].shape[1] * step, z0 + grid["ground"].shape[0] * step], "marginMeters": 10, "catalogIds": [x[0] for x in envelopes]},
        "inputs": {
            "terminalTriangles": str(STAGE / "terminal-triangles.npz"),
            "terminalTrianglesSha256": sha(STAGE / "terminal-triangles.npz"),
            "sourcePreparation": str(STAGE / "source-preparation.json"),
            "sources": str(STAGE / "sources.json"),
            "currentFormManifest": str(FORMS / "manifest.json"),
            "currentFormManifestSha256": sha(FORMS / "manifest.json"),
            "currentFormMasks": [m["mask"]["url"] for m in manifest["members"]],
            "dtm": str(STAGE / "roof-grid.npz"),
            "dtmMethod": "0.5m source-stage roof-grid ground sampled at exact source-triangle centroids",
            "topologyMethod": "Per-source-tile connected closure through any shared transformed source vertex at 1e-6m quantization; no cross-tile/proximity joins",
        },
        "counts": {"sourceTiles": int(len(np.unique(tile_indices))), "terminalTriangles": int(len(positions)), "topologyComponents": int(len(records)), "reviewCandidates": len(candidates), "correctionCandidates": 0, "knownGuardTriangles": len(known_guard), "registeredCorrectionFaces": len(already_corrected)},
        "policy": ["Use exact source triangles and DTM; no colour-only, rectangle, height-only or tile-wide deletion.", "Current-form envelope intersection, terrain compatibility, canopy/structure ambiguity and prior positive guards are rejection/retain signals.", "A component remains a manual review candidate until independent multi-angle runtime rays identify the same owner; no source correction is generated by this audit."],
        "commands": [
            "python3 scripts/audit-ivillage-neighborhood-remnants.py",
            "python3 -m py_compile scripts/audit-ivillage-neighborhood-remnants.py",
            "sha256sum docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.json docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.png",
        ],
        "writes": {"goalModified": False, "runtimePublished": False, "sourceTrianglesDeleted": 0, "newSourceCorrections": 0, "artifactsOnly": True},
        "components": records,
        "reviewCandidateIds": [r["id"] for r in candidates],
        "correctionCandidateIds": [],
        "limitations": ["Terminal source triangles represent the selected high/fine source frontier, not proof of whichever LOD a browser happened to load.", "DTM is 2019-2020 reference terrain; proximity does not identify roads, slopes, retaining walls or tree canopy by itself.", "No visual colour classifier or browser screenshot is used to approve deletion; current-form masks are sampled at centroid and all three vertex witnesses, so a mask sliver that misses those four samples still needs visual review.", "Source components can contain terrain, canopy, retaining walls, roofs and construction-era surfaces; unknown ownership is retained.", "Scope is the padded Hall X-XIII region in the existing source stage; components from intersecting triangles are reported with full closure bounds."],
        "artifacts": {"visualization": str(args.png), "report": str(args.report)},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    # Compact plan-view visualization: DTM as the context, official domains,
    # all audited components, and strict review candidates in red.
    # Pillow visualization avoids introducing a plotting/runtime dependency.
    from PIL import ImageDraw
    image = Image.fromarray(np.uint8(np.clip((grid["ground"] - np.nanmin(grid["ground"])) / (np.nanmax(grid["ground"]) - np.nanmin(grid["ground"]) or 1) * 180 + 45, 0, 255)), "L").convert("RGB")
    image = image.resize((image.width * 4, image.height * 4), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    scale = 4.0
    def px(x: float, z: float) -> tuple[int, int]:
        return (int((x - x0) / step * scale), int((z - z0) / step * scale))
    for name, env in envelopes:
        pts = [px(x, z) for x, z in env]
        draw.line(pts + [pts[0]], fill=(25, 90, 220), width=3, joint="curve")
    for r in records:
        x, y = px(r["centroid"][0], r["centroid"][2]); radius = max(2, min(16, int((r["areaSquareMeters"] ** 0.5) * 1.4)))
        color = (220, 38, 38) if r["status"] == "review-candidate-no-correction" else (100, 116, 139)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    image.save(args.png)
    print(json.dumps({"report": str(args.report), "visualization": str(args.png), "components": len(records), "reviewCandidates": len(candidates), "correctionCandidates": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
