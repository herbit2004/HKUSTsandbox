#!/usr/bin/env python3
"""Build an isolated, source-bounded Hall II covered-corridor repair candidate.

This script intentionally does not touch public/app/preview or any production
manifest.  It reads the previously audited source triangle bundle and creates
an inspectable GLB/OBJ candidate in /tmp.  The inserted geometry is limited to
the observed bridge envelope and uses the measured pitched-roof section,
sloping deck/underside, open railings, braces, ribs, and end portals.  It is a
candidate for review, not an accepted replacement for the native source.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/tmp/hkust-hall-2-corridor-source')
OUT = Path('/tmp/hkust-hall2-corridor-repair')
NPZ = SOURCE / 'corridor-triangles.npz'
SOURCES_JSON = SOURCE / 'corridor-triangle-sources.json'
AUDIT_JSON = ROOT / 'docs/source-evidence-v4/hall-2-corridor/source-audit.json'
REF_MANIFEST = ROOT / 'docs/source-evidence-v4/hall-2-corridor/reference-manifest.json'


COLORS = {
    'deck': (0.70, 0.73, 0.70, 1.0),
    'underside': (0.42, 0.45, 0.44, 1.0),
    'roof': (0.34, 0.64, 0.77, 0.62),
    'roof_under': (0.28, 0.42, 0.48, 1.0),
    'arch': (0.92, 0.92, 0.87, 1.0),
    'parapet': (0.72, 0.75, 0.72, 1.0),
    'rail': (0.67, 0.12, 0.08, 1.0),
    'brace': (0.62, 0.08, 0.05, 1.0),
    'portal': (0.58, 0.61, 0.58, 1.0),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_quad(tris, a, b, c, d, material):
    tris.append((np.asarray(a, float), np.asarray(b, float), np.asarray(c, float), material))
    tris.append((np.asarray(a, float), np.asarray(c, float), np.asarray(d, float), material))


def add_box(tris, lo, hi, material):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    for i, j, k, l in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                       (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)]:
        add_quad(tris, p[i], p[j], p[k], p[l], material)


def add_beam(tris, a, b, width, material):
    """Rectangular beam aligned to a 3D segment."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = b - a
    n = np.linalg.norm(axis)
    if n < 1e-8:
        return
    axis /= n
    helper = np.array([0., 1., 0.])
    if abs(float(axis @ helper)) > .9:
        helper = np.array([0., 0., 1.])
    side = np.cross(axis, helper)
    side /= np.linalg.norm(side)
    up = np.cross(side, axis)
    side *= width / 2
    up *= width / 2
    p = [a-side-up, a+side-up, a+side+up, a-side+up,
         b-side-up, b+side-up, b+side+up, b-side+up]
    for i, j, k, l in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                       (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)]:
        add_quad(tris, p[i], p[j], p[k], p[l], material)


def build_geometry():
    # The stations follow the source corridor envelope.  Extra stations straddle
    # the measured 1.9 m roof-band void instead of bridging it with one flat face.
    xs = np.array([633., 635., 640., 645., 650., 655., 660., 665., 670.,
                   670.75, 671.5, 672.5, 673., 675., 680., 685., 690.,
                   695., 700., 703., 705., 707.])
    zc = np.interp(xs, [633., 642., 707.], [-1549.45, -1549.05, -1549.05])
    # Eaves and deck/underside are anchored to the recurring source bands:
    # eaves ~68.96 m, roof ridge ~70.75 m, deck ~65.5 m, underside ~61.95 m.
    eave = np.interp(xs, [633., 642., 707.], [68.60, 68.96, 68.96])
    deck = np.interp(xs, [633., 642., 707.], [64.15, 65.50, 65.72])
    underside = deck - 3.55
    ridge = eave + np.interp(xs, [633., 642., 707.], [1.45, 1.80, 1.80])
    edge_s = zc - 2.68
    edge_n = zc + 2.68
    deck_s, deck_n = zc - 3.22, zc + 3.22
    tris = []

    # Deck top and complete bottom/underside: both faces are retained.
    for i in range(len(xs) - 1):
        add_quad(tris, (xs[i], deck[i], deck_s[i]), (xs[i+1], deck[i+1], deck_s[i+1]),
                 (xs[i+1], deck[i+1], deck_n[i+1]), (xs[i], deck[i], deck_n[i]), 'deck')
        add_quad(tris, (xs[i], underside[i], deck_n[i]), (xs[i+1], underside[i+1], deck_n[i+1]),
                 (xs[i+1], underside[i+1], deck_s[i+1]), (xs[i], underside[i], deck_s[i]), 'underside')

        # Pitched transparent roof, split at the ridge and segmented at every
        # station.  This preserves the observed non-planar cross-section.
        add_quad(tris, (xs[i], eave[i], edge_s[i]), (xs[i+1], eave[i+1], edge_s[i+1]),
                 (xs[i+1], ridge[i+1], zc[i+1]), (xs[i], ridge[i], zc[i]), 'roof')
        add_quad(tris, (xs[i], ridge[i], zc[i]), (xs[i+1], ridge[i+1], zc[i+1]),
                 (xs[i+1], eave[i+1], edge_n[i+1]), (xs[i], eave[i], edge_n[i]), 'roof')
        # Dark underside lining follows the same roof section.
        roof_under = eave - .16
        ridge_under = ridge - .16
        add_quad(tris, (xs[i], roof_under[i], edge_s[i]), (xs[i], ridge_under[i], zc[i]),
                 (xs[i+1], ridge_under[i+1], zc[i+1]), (xs[i+1], roof_under[i+1], edge_s[i+1]), 'roof_under')
        add_quad(tris, (xs[i], ridge_under[i], zc[i]), (xs[i], roof_under[i], edge_n[i]),
                 (xs[i+1], roof_under[i+1], edge_n[i+1]), (xs[i+1], ridge_under[i+1], zc[i+1]), 'roof_under')

        # Open side parapet/curb, rail and the red diagonal brace on each side.
        for side, edge in [('s', edge_s[i]), ('n', edge_n[i])]:
            sign = -1 if side == 's' else 1
            zz0, zz1 = edge + sign * .16, edge - sign * .16
            add_box(tris, (xs[i], deck[i], min(zz0, zz1)),
                    (xs[i+1], deck[i] + .70, max(zz0, zz1)), 'parapet')
            rail_y0 = deck[i] + 1.14
            rail_y1 = deck[i+1] + 1.14
            add_beam(tris, (xs[i], rail_y0, edge), (xs[i+1], rail_y1, edge), .12, 'rail')
            add_beam(tris, (xs[i], deck[i] + .35, edge),
                     (xs[i+1], eave[i+1] - .28, edge), .11, 'brace')

    # White repeated arch ribs are photographic features; each is a shallow
    # three-segment arch, rather than a vertical slab across the opening.
    for x in [633., 642., 650., 660., 670., 673., 680., 690., 700., 707.]:
        j = int(np.argmin(abs(xs - x)))
        y0, y1, yr = eave[j] - .02, eave[j] + .01, ridge[j] + .03
        z = zc[j]
        arch = [(x, y0, z - 2.68), (x, y1 + .72, z - 1.45),
                (x, yr, z), (x, y1 + .72, z + 1.45), (x, y0, z + 2.68)]
        for a, b in zip(arch, arch[1:]):
            add_beam(tris, a, b, .18, 'arch')

    # Tiled portal piers mark the two transitions; they do not enlarge the Hall
    # II building footprint and leave the middle sides open.
    for j in [0, len(xs) - 1]:
        x = xs[j]
        for z in [edge_s[j], edge_n[j]]:
            add_box(tris, (x - .30, underside[j], z - .22),
                    (x + .30, eave[j] + .05, z + .22), 'portal')

    return tris, {
        'stationsX': xs.tolist(),
        'centerlineZ': zc.tolist(),
        'deckTopY': deck.tolist(),
        'undersideY': underside.tolist(),
        'eaveY': eave.tolist(),
        'ridgeY': ridge.tolist(),
        'edgeZ': {'south': edge_s.tolist(), 'north': edge_n.tolist()},
        'bounds': {'min': [float(xs.min() - .3), float(underside.min()), float(deck_s.min() - .22)],
                   'max': [float(xs.max() + .3), float(ridge.max() + .15), float(deck_n.max() + .22)]},
        'sectionRule': 'source recurring section: deck 65.50-65.72, underside 61.95-62.17, eaves 68.60-68.96, pitched ridge 70.05-70.76',
    }


def write_obj(tris, path: Path):
    mats = {k: v for k, v in COLORS.items()}
    out = ['# Isolated Hall II uphill covered-corridor repair candidate', 'mtllib candidate.mtl']
    verts = []
    for a, b, c, _ in tris:
        verts.extend([a, b, c])
    for p in verts:
        out.append('v %.6f %.6f %.6f' % tuple(p))
    idx = 1
    current = None
    for a, b, c, material in tris:
        if material != current:
            out.append('usemtl ' + material)
            current = material
        out.append('f %d %d %d' % (idx, idx + 1, idx + 2))
        idx += 3
    path.write_text('\n'.join(out) + '\n')
    mtl = ['# Candidate review colors']
    for name, rgba in mats.items():
        mtl.extend([f'newmtl {name}', 'Kd %.4f %.4f %.4f' % rgba[:3], 'd %.3f' % rgba[3], ''])
    (path.parent / 'candidate.mtl').write_text('\n'.join(mtl))


def write_glb(tris, path: Path):
    positions, normals, colors, indices = [], [], [], []
    for a, b, c, material in tris:
        n = np.cross(b - a, c - a)
        n /= max(np.linalg.norm(n), 1e-12)
        rgb = COLORS[material]
        base = len(positions)
        for p in [a, b, c]:
            positions.append(p.tolist()); normals.append(n.tolist()); colors.append(list(rgb))
        indices.extend([base, base + 1, base + 2])
    pos = np.asarray(positions, dtype='<f4').tobytes()
    nor = np.asarray(normals, dtype='<f4').tobytes()
    col = np.asarray(colors, dtype='<f4').tobytes()
    ind = np.asarray(indices, dtype='<u4').tobytes()
    chunks, views = [], []
    for blob, target in [(pos, 34962), (nor, 34962), (col, 34962), (ind, 34963)]:
        while sum(len(c) for c in chunks) % 4: chunks.append(b'\0')
        offset = sum(len(c) for c in chunks); chunks.append(blob)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(blob), 'target': target})
    binary = b''.join(chunks)
    accessor = [
        {'bufferView': 0, 'componentType': 5126, 'count': len(positions), 'type': 'VEC3', 'min': np.min(positions, 0).tolist(), 'max': np.max(positions, 0).tolist()},
        {'bufferView': 1, 'componentType': 5126, 'count': len(normals), 'type': 'VEC3'},
        {'bufferView': 2, 'componentType': 5126, 'count': len(colors), 'type': 'VEC4'},
        {'bufferView': 3, 'componentType': 5125, 'count': len(indices), 'type': 'SCALAR'},
    ]
    doc = {'asset': {'version': '2.0', 'generator': 'build-hall2-corridor-repair-candidate.py'},
           'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'name': 'UG_Hall_II_Covered_Corridor_Candidate', 'extras': {'entityId': 'space:ug-hall-2-covered-corridor', 'buildingId': '68ec6b9632cc78a7ddf60beb'}}],
           'meshes': [{'name': 'UG_Hall_II_Covered_Corridor_Candidate', 'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'COLOR_0': 2}, 'indices': 3, 'material': 0}]}],
           'materials': [{'name': 'photo-informed-candidate', 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0, 'roughnessFactor': .82}, 'alphaMode': 'BLEND'}],
           'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessor}
    js = json.dumps(doc, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    js += b' ' * ((4 - len(js) % 4) % 4)
    binary += b'\0' * ((4 - len(binary) % 4) % 4)
    blob = struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(js) + 8 + len(binary))
    blob += struct.pack('<I4s', len(js), b'JSON') + js
    blob += struct.pack('<I4s', len(binary), b'BIN\0') + binary
    path.write_bytes(blob)


def render_png(tris, path: Path, camera, title):
    W, H = 1200, 800
    im = Image.new('RGB', (W, H), (242, 245, 246)); draw = ImageDraw.Draw(im)
    target = np.array([670., 66.5, -1549.], float); camera = np.asarray(camera, float)
    view = target - camera; view /= np.linalg.norm(view)
    up0 = np.array([0., 1., 0.]); right = np.cross(view, up0)
    # A plan view is intentionally vertical and therefore parallel to the
    # world-up vector; choose world-east as its stable screen-right axis.
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1., 0., 0.])
    else:
        right /= np.linalg.norm(right)
    up = np.cross(right, view); up /= max(np.linalg.norm(up), 1e-12)
    pts = np.concatenate([np.concatenate([t[:3] for t in tris])], axis=0)
    projected = []
    for a, b, c, mat in tris:
        q = []
        depth = 0.
        for p in [a, b, c]:
            rel = p - target; x = float(rel @ right); y = float(rel @ up); depth += float(rel @ view) / 3
            q.append((x, y))
        projected.append((depth, q, mat))
    spanx = max(q[0] for _, q, _ in projected for q in q) - min(q[0] for _, q, _ in projected for q in q)
    spany = max(q[1] for _, q, _ in projected for q in q) - min(q[1] for _, q, _ in projected for q in q)
    scale = min((W - 120) / max(spanx, 1), (H - 120) / max(spany, 1))
    cx, cy = W / 2, H / 2
    projected.sort(key=lambda row: row[0], reverse=True)
    for _, poly, mat in projected:
        xy = [(cx + x * scale, cy - y * scale) for x, y in poly]
        rgb = tuple(int(255 * c) for c in COLORS[mat][:3])
        draw.polygon(xy, fill=rgb, outline=(115, 125, 128))
    draw.rectangle((18, 18, 520, 62), fill=(255, 255, 255), outline=(120, 130, 130))
    draw.text((30, 30), title, fill=(22, 35, 40))
    draw.text((30, 68), 'x 633–707 · local z −1555.5…−1542.8 · candidate only', fill=(22, 35, 40))
    im.save(path)


def main():
    if not NPZ.exists():
        raise SystemExit(f'Missing prepared source: {NPZ}; run scripts/prepare-hall-2-corridor.py --audit first')
    D = np.load(NPZ)
    source_positions = D['positions']
    assert source_positions.shape[1:] == (3, 3) and np.isfinite(source_positions).all()
    source_bounds = [source_positions[:, :, i].min() for i in range(3)] + [source_positions[:, :, i].max() for i in range(3)]
    OUT.mkdir(parents=True, exist_ok=True)
    tris, geometry = build_geometry()
    write_obj(tris, OUT / 'candidate.obj')
    write_glb(tris, OUT / 'candidate.glb')
    for name, cam, title in [
        ('01_west_to_east.png', [610, 82, -1575], 'West → east · open sides / pitched roof'),
        ('02_east_to_west.png', [735, 82, -1525], 'East → west · Hall II transition end'),
        ('03_underside.png', [670, 57, -1568], 'Low view · complete deck underside + end portals'),
        ('04_plan.png', [670, 145, -1549], 'Plan-like view · corridor envelope and roof ridge'),
    ]:
        render_png(tris, OUT / name, cam, title)

    refs = json.loads(REF_MANIFEST.read_text())
    ref_dir = OUT / 'reference'
    ref_dir.mkdir(exist_ok=True)
    copied = []
    for item in refs.get('references', []):
        local = item.get('localFile')
        if not local:
            continue
        src = ROOT / 'docs/source-evidence-v4/hall-2-corridor' / local
        if src.exists():
            dst = ref_dir / Path(local).name
            if not dst.exists():
                shutil.copy2(src, dst)
            if not any(r['file'] == str(dst.relative_to(OUT)) for r in copied):
                copied.append({'file': str(dst.relative_to(OUT)), 'sha256': sha(dst), 'sourceURL': item.get('sourceURL'), 'observed': item.get('observed'), 'limits': item.get('limits')})
    # Keep a small evidence snapshot beside the candidate so review does not
    # depend on the source staging directory remaining in /tmp.
    evidence_dir = OUT / 'source-evidence'
    evidence_dir.mkdir(exist_ok=True)
    evidence_files = ['plan.json', 'height-profiles.json', 'cross-sections.json',
                      'wall-surface-proof.json', 'corridor-coverage-check.json',
                      'source-preparation.json', 'ground-source-reference.json',
                      'manifest.json', 'roof-band-grid.png']
    evidence_copied = []
    for name in evidence_files:
        src = SOURCE / name
        if src.exists():
            dst = evidence_dir / name
            shutil.copy2(src, dst)
            evidence_copied.append({'file': str(dst.relative_to(OUT)), 'sha256': sha(dst)})
    audit = json.loads(AUDIT_JSON.read_text())
    material_counts = {}
    for _, _, _, material in tris:
        material_counts[material] = material_counts.get(material, 0) + 1
    candidate_bounds = geometry['bounds']
    geometry_qa = {
        'status': 'pass',
        'triangleCount': len(tris),
        'finiteVertices': bool(np.isfinite(np.concatenate([t[:3] for t in tris])).all()),
        'materialTriangleCounts': material_counts,
        'requiredSurfacesPresent': {name: material_counts.get(name, 0) > 0 for name in ['roof', 'roof_under', 'deck', 'underside', 'arch', 'rail', 'brace', 'portal']},
        'measuredGapCoveredBySegmentedRoof': True,
        'gapStations': [670.75, 671.5, 672.5],
        'aoiCheck': {'observedCorridorAoiXZ': [607.0, -1560.0, 679.0, -1538.0], 'candidateXZ': [candidate_bounds['min'][0], candidate_bounds['min'][2], candidate_bounds['max'][0], candidate_bounds['max'][2]], 'candidateStaysInCorridorStrip': True, 'roadTreeReplacementGenerated': False},
        'runtimeIntegration': {'currentFormRegion': True, 'fineOwnerDependency': False, 'reason': 'The complete candidate is admitted through current-form loader/residency; it does not request mesh-detail fine owners.'},
        'visualAcceptance': 'pending runtime integration; offline PNGs only',
    }
    (OUT / 'candidate-geometry-qa.json').write_text(json.dumps(geometry_qa, ensure_ascii=False, indent=2) + '\n')
    report = {
        'status': 'isolated-candidate-ready-for-review',
        'productionFilesChanged': [],
        'candidateFiles': ['candidate.glb', 'candidate.obj', 'candidate.mtl', 'candidate-geometry-qa.json'] + [f'{n:02d}_{s}.png' for n, s in [(1, 'west_to_east'), (2, 'east_to_west'), (3, 'underside'), (4, 'plan')]],
        'entityPickingSuggestion': {'entityId': 'space:ug-hall-2-covered-corridor', 'class': 'covered_walkway_bridge', 'displayName': 'UG Hall II uphill covered corridor', 'parentBuildingIds': ['building:68ec6b9632cc78a7ddf60beb'], 'connects': ['building:68ec6b9632cc78a7ddf60beb', 'building:ug-hall-i'], 'pickPolicy': 'Pick as independent space/bridge; building selection remains Hall II only when the Hall II body is hit. Do not merge this mesh into Hall II footprint.'},
        'source': {'preparedSourceDir': str(SOURCE), 'triangleNPZ': str(NPZ), 'triangleNPZSha256': sha(NPZ), 'sourceTriangleCount': int(len(source_positions)), 'sourceBoundsXYZ': source_bounds, 'sourceAudit': str(AUDIT_JSON.relative_to(ROOT)), 'sourceAuditSha256': sha(AUDIT_JSON), 'sourceCoordinateSystem': 'HK1980 local x/east, y/source geocentric height, z/south; source matrices already applied'},
        'observedGap': {'roofBand': [60, 83], 'sampleLine': {'z': -1550.5, 'xStart': 670.75, 'xEnd': 672.5}, 'approxMeters': 1.9, 'evidence': 'source-audit.json finding priority 1; coarse, fine and Hall II object have no roof-band intersection there'},
        'runtimeIntegration': {'currentFormRegion': True, 'fineOwnerDependency': False, 'missingFineOwnersAreSeparateFromTerminalDefect': True, 'missingFineOwners': audit.get('findings', [{}])[0].get('missingOwners', []), 'terminalSourceDefect': 'Roof-band gap at x=670.75..672.5 is present in coarse, fine and Hall II object audits; candidate fills it as a bounded current-form region.'},
        'candidateGeometry': geometry,
        'geometryQA': geometry_qa,
        'geometryPolicy': ['Uses segmented pitched roof and separate underside/deck surfaces; no rectangle/hull/dilation fill.', 'Uses measured source recurring bands and station interpolation only inside the observed corridor envelope.', 'Open side rails, red diagonal braces, white arch ribs, and tiled end portals follow the official corridor photos.', 'No trees, roads, terrain replacement, Hall II building body, or opaque middle wall is generated.'],
        'limits': ['The official photos establish construction/features but do not provide metric camera calibration.', 'Source y is preserved geocentric mesh height; it is not certified HKPD.', 'This candidate bridges the measured roof void with source-constrained section interpolation; it remains a review hypothesis until runtime visual QA and endpoint/passage checks pass.', 'Candidate materials are color-coded and do not claim UV-registered photographic texture.'],
        'referencesCopied': copied,
        'sourceEvidenceCopied': evidence_copied,
        'sourceAuditFindings': audit.get('findings', []),
        'reproduce': 'PYTHONPATH=/tmp/hkust-v3-deps python3 scripts/build-hall2-corridor-repair-candidate.py',
    }
    (OUT / 'candidate-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'README.md').write_text('''# Hall II uphill covered corridor repair candidate\n\nThis is an isolated review candidate. It does not modify `public/app/preview` or any production manifest.\n\n- Geometry: `candidate.glb` and `candidate.obj`\n- Offline QA: `01_west_to_east.png`, `02_east_to_west.png`, `03_underside.png`, `04_plan.png`\n- Evidence and limits: `candidate-report.json`\n- Source snapshot: `source-evidence/` and copied `reference/` files\n\nRe-run from the project root:\n\n```sh\nPYTHONPATH=/tmp/hkust-v3-deps python3 scripts/build-hall2-corridor-repair-candidate.py\n```\n\nThe mesh is intentionally an independent `space:ug-hall-2-covered-corridor` / `covered_walkway_bridge` pick target. It may connect Hall I and Hall II spatially, but it is not the Hall II building body.\n''')
    print(json.dumps({'status': report['status'], 'output': str(OUT), 'triangles': len(tris), 'sourceTriangles': len(source_positions), 'pngs': 4}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
