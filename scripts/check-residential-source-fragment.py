#!/usr/bin/env python3
"""Prove the refined counterpart of the previously confirmed UG12 source floater.
Exact connected components only, never a general height/roof deletion rule.
"""
import json
from pathlib import Path
import numpy as np
from hkust_source_geometry import geometry
P = Path(__file__).resolve().parents[1]
D = P/'public/models/hires/partial-residential-ias'
m = json.loads((D/'manifest.json').read_text())['patches'][0]
ids = {'12-NW-11A/12-NW-11A-4/Tile_303_143_L20_00312',
       '12-NW-6C/12-NW-6C-19/Tile_303_144_L20_00203'}
focus_low = np.array([735.5, 186.5, -1100.5]); focus_high = np.array([743.0, 193.0, -1095.3])
components = []; suspect = []; other = []
for tile in m['levels']['high']['tiles']:
    # Reruns inspect original source, even after exact correction has been applied.
    correction = tile.get('sourceCorrection', {})
    url = correction.get('originalUrl', tile['url']) if tile['id'] in ids else tile['url']
    tri, _ = geometry(P/'public/models/hires'/url, np.array(tile['matrix']).reshape(4, 4, order='F'))
    chosen = []
    if tile['id'] in ids:
        parents = np.arange(len(tri)); vertices = {}
        def find(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]; i = parents[i]
            return int(i)
        for i, face in enumerate(tri):
            for point in face:
                key = tuple(np.round(point, 4)); old = vertices.get(key)
                if old is None: vertices[key] = i
                else: parents[find(i)] = find(old)
        groups = {}
        for i in range(len(tri)): groups.setdefault(find(i), []).append(i)
        intersection = np.all(tri.min(1) <= focus_high, axis=1) & np.all(tri.max(1) >= focus_low, axis=1)
        roots = set(find(i) for i in np.flatnonzero(intersection))
        assert 1 <= len(roots) <= 3, 'A changed source topology needs a new audit.'
        chosen = sorted(i for root in roots for i in groups[root])
        s = tri[chosen]; suspect.append(s)
        components.append({'id': tile['id'], 'sourceSha256': correction.get('originalSha256', tile['sha256']),
            'triangleIndices': chosen, 'triangles': len(chosen),
            'bounds': {'min': s.min((0, 1)).tolist(), 'max': s.max((0, 1)).tolist()}})
    other.append(np.delete(tri, chosen, axis=0))
suspect = np.concatenate(suspect); other = np.concatenate(other)
lo = suspect.min((0, 1)); hi = suspect.max((0, 1))
axis_distance = np.maximum(np.maximum(other.min(1)-hi, lo-other.max(1)), 0)
lower = float(np.linalg.norm(axis_distance, axis=1).min())
samples = []
e1 = other[:, 1]-other[:, 0]; e2 = other[:, 2]-other[:, 0]
direction = np.array([0, -1, 0]); h = np.cross(direction, e2)
a = np.einsum('ij,ij->i', e1, h); valid = abs(a) > 1e-9
f = np.zeros(len(a)); f[valid] = 1/a[valid]
for point in suspect.mean(1)[::max(1, len(suspect)//25)]:
    origin = point-[0, .01, 0]; v = origin-other[:, 0]
    u = f*np.einsum('ij,ij->i', v, h); q = np.cross(v, e1)
    w = f*(q@direction); t = f*np.einsum('ij,ij->i', e2, q)
    ix = np.flatnonzero(valid & (u >= 0) & (w >= 0) & (u+w <= 1) & (t > 0))
    k = ix[np.argmin(t[ix])] if len(ix) else None
    samples.append({'componentPoint': point.tolist(), 'verticalGapMeters': float(t[k]) if k is not None else None,
        'sourceSurfaceBelow': (origin+direction*t[k]).tolist() if k is not None else None})
assert 1219 <= len(suspect) <= 1300 and lower > 15
assert all(s['verticalGapMeters'] is not None and s['verticalGapMeters'] > 20 for s in samples)
report = {'status': 'confirmed-source-floater', 'combinedRemovedTriangleCount': len(suspect),
    'combinedBounds': {'min': lo.tolist(), 'max': hi.tolist()},
    'distanceLowerBoundToAnyOtherNewTriangleMeters': lower, 'components': components, 'verticalSamples': samples,
    'sourceReference': 'public/models/source-corrections/ug12-isolated-photogrammetry-fragment-8/manifest.json',
    'proof': 'Two exact connected refined components coincide with the independently confirmed old source floater. Conservative whole-component AABB to each other triangle AABB distance proves disconnection across all123 source leaves. Original low-LOD triangle indices are not reused.',
    'normalRoofsDeleted': False, 'originalSourceFilesRetained': True}
(D/'fine-fragment-correction-evidence.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({'triangles': len(suspect), 'distanceLowerBound': lower,
    'verticalGapRange': [min(s['verticalGapMeters'] for s in samples), max(s['verticalGapMeters'] for s in samples)]}))
