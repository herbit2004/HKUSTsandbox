#!/usr/bin/env python3
"""Three actual source-face rays for domain-only Staff 3/4 ownership QA.

This creates evidence only. It does not alter source geometry or runtime picking.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from hkust_source_geometry import geometry, Heights

ROOT = Path(__file__).resolve().parents[1]
OID = 'B452822226202062A0'
SOURCE = ROOT / 'public/models/exteriors/objects' / OID
OUT = ROOT / 'docs/source-evidence-v4/building-quality/staff-domain-only-ray-fixtures.json'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = read(SOURCE / 'source-manifest.json')
for item in source['files']:
    assert sha(SOURCE / item['filename']) == item['sha256']

matrix = np.eye(4)
matrix[:3, 3] = [-844800, 0, 820500]
triangles, materials = geometry(SOURCE / (OID + '.gltf'), matrix)
assert len(triangles) == 208
centroids = triangles.mean(1)
normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
normals /= np.linalg.norm(normals, axis=1)[:, None]
domain_path = ROOT / 'public/data/picking/building-domains-extra.json'
records = [d for d in read(domain_path)['domains'] if d['entityId'] in [
    'building:catalog:staff-quarters-tower-3', 'building:catalog:staff-quarters-tower-4']]
domains = {d['entityId']: unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in d['parts']]) for d in records}
union = unary_union(list(domains.values()))
dtm_path = next((ROOT / 'public/terrain/source-data').glob('*6A*.tif'))
dtm = Heights([dtm_path])
grid_path = ROOT / 'public/terrain/height-grid-5m.json'
grid = read(grid_path)
heights = np.array([np.nan if z is None else z for z in grid['heights']]).reshape(grid['rows'], grid['columns'])


def sample_grid(x, z):
    c = (x + 844800 - grid['first_easting']) / grid['easting_step']
    r = (820500 - z - grid['first_northing']) / grid['northing_step']
    i, j = int(r), int(c)
    u, v = c-j, r-i
    h = heights[i:i+2, j:j+2]
    if h.shape != (2, 2) or not np.isfinite(h).all():
        return None
    return float(h[0, 0]*(1-u)*(1-v)+h[0, 1]*u*(1-v)+h[1, 0]*(1-u)*v+h[1, 1]*u*v)


def intersections(origin, direction):
    """Independent double-sided Moller-Trumbore check against all 208 faces."""
    a = triangles[:, 1] - triangles[:, 0]
    b = triangles[:, 2] - triangles[:, 0]
    p = np.cross(np.broadcast_to(direction, b.shape), b)
    det = np.einsum('ij,ij->i', a, p)
    valid = abs(det) > 1e-10
    inv = np.zeros(len(det)); inv[valid] = 1 / det[valid]
    delta = origin - triangles[:, 0]
    u = np.einsum('ij,ij->i', delta, p) * inv
    q = np.cross(delta, a)
    v = q @ direction * inv
    t = np.einsum('ij,ij->i', b, q) * inv
    valid &= (u >= -1e-9) & (v >= -1e-9) & (u+v <= 1+1e-9) & (t > 1e-8)
    return sorted([(float(t[i]), int(i)) for i in np.flatnonzero(valid)])


fixtures = []
for eid in [*domains, None]:
    candidates = []
    for i, center in enumerate(centroids):
        point = Point(center[0], center[2])
        belongs = domains[eid].contains(point) if eid else not union.covers(point)
        if belongs and abs(normals[i, 1]) < .1:
            clearance = domains[eid].boundary.distance(point) if eid else union.distance(point)
            candidates.append((clearance, i))
    assert candidates
    clearance, index = max(candidates)
    center = centroids[index]
    origin = center + .2 * normals[index]
    hits = intersections(origin, -normals[index])
    assert hits[0][1] == index and abs(hits[0][0]-.2) < 1e-8
    ground = float(dtm(np.array([[center[0]+844800, 820500-center[2]]]))[0])
    fixtures.append({
        'id': eid.rsplit(':', 1)[-1] if eid else 'outside-both-named-domains',
        'expectedDomainEntityId': eid,
        'expectedExplicitSourceOwner': None,
        'expectedDomainOnlyPicking': 'source-footprint-and-height' if eid else 'unassigned-visible-surface',
        'sourceObjectId': OID, 'sourceOwnership': 'domain-only',
        'triangleIndex': index, 'materialIndex': int(materials[index]),
        'triangleLocalXYZ': triangles[index].tolist(),
        'centroidLocalXYZ': center.tolist(), 'barycentric': [1/3, 1/3, 1/3],
        'normalLocalXYZ': normals[index].tolist(),
        'ray': {'origin': origin.tolist(), 'direction': (-normals[index]).tolist(), 'distance': hits[0][0]},
        'domainBoundaryClearanceMeters': clearance,
        'groundY': ground,
        'groundYMeaning': 'Bilinear sample of four original 0.5 m DTM pixel centres; HKPD, not source mesh height.',
        'runtimeGrid5mGroundY': sample_grid(center[0], center[2]),
        'sourceSurfaceMinusDtmMeters': float(center[1]-ground),
        'independentWholeSourceRayNearestFaceVerified': True,
    })

result = {
    'sourceObjectId': OID, 'sourceTriangles': len(triangles),
    'sourceLevelCode': '2A', 'sourceFiles': source['files'],
    'sourceArchiveUrl': source['source_archive_uri'],
    'sourceRevisionDate': source['source_revision_date'], 'captureDate': source['capture_date'],
    'gltfSha256': sha(SOURCE / (OID+'.gltf')),
    'binSha256': sha(SOURCE / (OID+'.bin')),
    'domainFile': str(domain_path.relative_to(ROOT)), 'domainFileSha256': sha(domain_path),
    'dtmFile': str(dtm_path.relative_to(ROOT)), 'dtmSha256': sha(dtm_path),
    'runtimeGridFile': str(grid_path.relative_to(ROOT)), 'runtimeGridSha256': sha(grid_path),
    'sourcePlacement': {'offset': [-844800, 0, 820500], 'originalNodeMatricesUnchanged': True},
    'method': 'Actual face centroids on vertical source faces, selected for largest clearance within each exact official domain or outside both. Ray starts 0.2 m along face normal and is verified against every original source triangle. No generated roof/footprint geometry.',
    'limitations': 'Isolated source-ownership regression, not proof that this low face is visually unobstructed in the full scene. In Staff 4 the original low object can lie below the DTM; source heights are retained. Vertical normals avoid accidentally testing ground-like rejection instead of ownership.',
    'fixtures': fixtures, 'runtimeModified': False,
}
OUT.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({'path': str(OUT), 'fixtures': fixtures}, indent=2))
