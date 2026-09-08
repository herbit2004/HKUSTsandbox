#!/usr/bin/env python3
"""Reproduce source geometry identity and planimetric coverage in the saved UG view.

Projection coverage is not facade completeness, present-day appearance, or an
image-quality acceptance result. Original geometric error zero is only a tree LOD.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from shapely import contains_xy
from hkust_source_geometry import geometry

P = Path(__file__).resolve().parents[1]
O = P / 'docs/source-evidence-v4/building-quality'
O.mkdir(parents=True, exist_ok=True)
read = lambda p: json.loads(p.read_text())
registry = read(P/'public/data/entity-registry.json')['entities']
footprints = read(P/'public/data/building-footprints.json')['footprints']
extra = read(P/'public/data/picking/building-domains.json')['domains']
entities = {e['entityId']: e for e in registry if e['type'] == 'building'}
domains = {}
for e in entities.values():
    fs = [f for f in footprints if f['officialBuildingId'] == e.get('externalIds', {}).get('pathAdvisorBuildingId')]
    parts = [p for f in fs for p in f['parts']]
    parts += [p for d in extra if d['entityId'] == e['entityId'] for p in d['parts']]
    if parts:
        domains[e['entityId']] = unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in parts])

manifest = read(P/'public/models/hires/manifest.json')
partial = read(P/'public/models/hires/partial-ug10/manifest.json')['patches'][0]
if not any(p['id'] == partial['id'] for p in manifest['patches']):
    manifest['patches'].append(partial)  # Replay the saved old browser state, not today's replacement.
m = partial['mask']
mask = np.asarray(Image.open(P/'public/models/hires'/m['url']).convert('RGB'))[:, :, 0]
coverage = []
for e in entities.values():
    legacy = e.get('externalIds', {}).get('legacyCatalogIds', [])
    if not set(legacy) & {'ug-hall-10', 'ug-hall-11', 'ug-hall-12', 'ug-hall-13', 'campus-35'}:
        continue
    domain = domains[e['entityId']]
    lo = np.floor(np.array(domain.bounds[:2])*2)/2
    hi = np.ceil(np.array(domain.bounds[2:])*2)/2
    x, z = np.meshgrid(np.arange(lo[0]+.25, hi[0], .5), np.arange(lo[1]+.25, hi[1], .5))
    inside = contains_xy(domain, x, z)
    within = (x >= m['minX']) & (x < m['maxX']) & (z >= m['minZ']) & (z < m['maxZ'])
    sampled = np.zeros(x.shape, bool)
    rows = ((z[within]-m['minZ'])/.5).astype(int)
    cols = ((x[within]-m['minX'])/.5).astype(int)
    sampled[within] = mask[rows, cols] > 127
    coverage.append({'canonicalId': e['entityId'], 'name': e['name'], 'legacyIds': legacy,
        'sourceDomainAreaM2': domain.area, 'sourceDomainBoundsXZ': list(domain.bounds),
        'gridInsideAreaM2': int(inside.sum())*.25,
        'current37LeafProjectionCoveredAreaM2': int((inside & sampled).sum())*.25,
        'current37LeafProjectionCoveragePercent': 100*int((inside & sampled).sum())/int(inside.sum())})

camera = np.array([744.195, 264.693, -942.341])
target = np.array([623.513, 144.011, -1089.841])
canvas = {'left': 310, 'top': 61.992, 'width': 1290, 'height': 837.998}
forward = (target-camera)/np.linalg.norm(target-camera)
right = np.cross(forward, [0, 1, 0]); right /= np.linalg.norm(right)
up = np.cross(right, forward)
pixels = [(990, 680), (946, 540), (1100, 720), (930, 350), (954, 401), (1222, 522), (1340, 595), (1460, 540)]
directions = []
for x, y in pixels:
    direction = forward + right*((x-canvas['left'])/canvas['width']*2-1)*np.tan(np.radians(21))*canvas['width']/canvas['height'] + up*(1-(y-canvas['top'])/canvas['height']*2)*np.tan(np.radians(21))
    directions.append(direction/np.linalg.norm(direction))

# Exact groups in the saved browser diagnostic, not the groups merely in manifest.
state = read(P/'docs/source-evidence-v4/ug10-terminal-near.json')
visible = {'12-NW-6C-7-partial-entrance': 'fine', '12-NW-6C-2': 'fine',
    'ug10-terminal-leaves-partial': 'high', '12-NW-6C-16': 'fine', '12-NW-6C-11': 'fine'}
hidden_ids = {bid for p in manifest['patches'] if p['id'] in visible and not p.get('mask') for bid in p['baselineIds']}
partial_masks = []
objects = []
for patch in manifest['patches']:
    if patch['id'] not in visible:
        continue
    level = patch['levels'][visible[patch['id']]]
    cm = level.get('mask', patch.get('mask'))
    if cm:
        partial_masks.append((np.asarray(Image.open(P/'public/models/hires'/cm['url']).convert('RGB'))[:, :, 0], cm))
    for tile in level['tiles']:
        objects.append((tile, P/'public/models/hires'/tile['url'], 'photogrammetry'))
for tile in read(P/'public/models/preview-manifest.json')['tiles']:
    if tile['id'] not in hidden_ids:
        objects.append((tile, P/'public/models'/tile['url'], 'baseline'))

def is_partial_masked(point):
    x, z = point[[0, 2]]
    for array, mm in partial_masks:
        if mm['minX'] <= x < mm['maxX'] and mm['minZ'] <= z < mm['maxZ']:
            col = min(array.shape[1]-1, int((x-mm['minX'])/(mm['maxX']-mm['minX'])*array.shape[1]))
            row = min(array.shape[0]-1, int((z-mm['minZ'])/(mm['maxZ']-mm['minZ'])*array.shape[0]))
            if array[row, col] > 127:
                return True
    return False

hits = [[] for _ in pixels]
for tile, path, role in objects:
    b = tile['bounds']
    if b['max'][0] < 450 or b['min'][0] > 900 or b['max'][2] < -1350 or b['min'][2] > -950:
        continue
    tri, materials = geometry(path, np.array(tile['matrix']).reshape(4, 4, order='F'))
    e1 = tri[:, 1]-tri[:, 0]; e2 = tri[:, 2]-tri[:, 0]; v = camera-tri[:, 0]
    for j, direction in enumerate(directions):
        h = np.cross(np.broadcast_to(direction, e2.shape), e2)
        a = np.einsum('ij,ij->i', e1, h); valid = abs(a) > 1e-8
        f = np.zeros(len(a)); f[valid] = 1/a[valid]
        u = f*np.einsum('ij,ij->i', v, h); q = np.cross(v, e1)
        w = f*(q@direction); distance = f*np.einsum('ij,ij->i', e2, q)
        ix = np.flatnonzero(valid & (u >= 0) & (w >= 0) & (u+w <= 1) & (distance > 0))
        for k in ix[np.argsort(distance[ix])][:4]:
            point = camera+direction*distance[k]
            owners = [eid for eid, domain in domains.items() if domain.covers(Point(*point[[0, 2]]))]
            hits[j].append({'tile': tile['id'], 'role': role, 'distance': float(distance[k]),
                'triangleIndex': int(k), 'worldXYZ': point.tolist(), 'canonicalDomains': owners,
                'names': [entities[eid]['name'] for eid in owners],
                'discardedByPartialProjection': role == 'baseline' and is_partial_masked(point),
                'originalError': tile.get('originalError'), 'sourceAsset': str(path.relative_to(P))})
records = []
for pixel, candidates in zip(pixels, hits):
    ordered = sorted(candidates, key=lambda x: x['distance'])[:10]
    records.append({'screen': list(pixel), 'firstRetainedNativeHit': next((h for h in ordered if not h['discardedByPartialProjection']), None), 'nativeHits': ordered})
report = {'checkedAt': '2026-09-06', 'screenshot': 'docs/screenshots/v4/ug10-terminal-near.png',
    'camera': camera.tolist(), 'target': target.tolist(), 'canvas': canvas, 'fovDegrees': 42,
    'coverage': coverage, 'actualSourceRayIdentity': records,
    'limitations': ['0.5m mask coverage measures horizontal projection only; it does not establish facade completeness or current completed appearance.',
        'Ray identity replays the exact saved camera and native partial masks. No independent exterior owner falls in these selected dorm points. This is source-based identity QA, not a new browser rendering test.',
        '2026 official photographs document blue/blue-grey ceramic cladding, curved corners and photovoltaic folded roofs. These real design features must be preserved; source geometry noise and capture-era differences need separate multi-angle comparison.']}
(O/'ug10-13-native-projection-and-identity.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'coverage': coverage, 'rayIdentity': [{'screen': r['screen'], 'hit': r['firstRetainedNativeHit']} for r in records]}, ensure_ascii=False, indent=2))
