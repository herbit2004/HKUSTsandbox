#!/usr/bin/env python3
"""Actual original source-face rays for five named Staff range envelopes."""
import hashlib
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from hkust_source_geometry import geometry, Heights

ROOT = Path(__file__).resolve().parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
dest = ROOT/'docs/source-evidence-v4/building-quality/staff-range-source-rays.json'
manifest = read(ROOT/'public/models/exteriors/manifest.json')
domains = read(ROOT/'public/data/picking/building-domains-extra.json')['auditOnlyAggregateDomains']
dtm = Heights(list((ROOT/'public/terrain/source-data').glob('*.tif')))
cases = []
for bundle in [b for b in manifest['bundles'] if b.get('entityId', '').startswith('zone:')]:
    record = next(d for d in domains if d['physicalDomainId'] == bundle['physicalDomainId'])
    domain = unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in record['parts']])
    obj = bundle['objects'][0]; path = ROOT/'public/models/exteriors'/obj['url']
    source = read(ROOT/'public/models/exteriors'/obj['sourceManifest'])
    for file in source['files']:
        assert sha(path.parent/file['filename']) == file['sha256']
    matrix = np.eye(4); matrix[:3, 3] = obj['offset']
    triangles, _ = geometry(path, matrix)
    centers = triangles.mean(1)
    normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    area = np.linalg.norm(normal, axis=1)/2
    normal /= np.maximum(1e-15, area[:, None]*2)
    ground = dtm(np.column_stack([centers[:, 0]+844800, 820500-centers[:, 2]]))
    for label in ['roof', 'wall', 'outside-domain']:
        candidates = []
        for i, point in enumerate(centers):
            xz = Point(point[0], point[2]); inside = domain.contains(xz)
            if area[i] < .01 or not np.isfinite(ground[i]):
                continue
            if label == 'outside-domain':
                valid = not inside and domain.distance(xz) > .2 and abs(normal[i, 1]) < .2
                score = domain.distance(xz)
            else:
                valid = inside and point[1]-ground[i] > 3 and (abs(normal[i, 1]) >= .8 if label == 'roof' else abs(normal[i, 1]) <= .2)
                score = domain.boundary.distance(xz)
            if valid:
                candidates.append((score, i))
        assert candidates, (bundle['id'], label)
        clearance, index = max(candidates)
        center = centers[index]
        cases.append({'bundleId': bundle['id'], 'entityId': bundle['entityId'],
                      'physicalDomainId': bundle['physicalDomainId'], 'faceClass': label,
                      'sourceId': obj['id'], 'asset': '/models/exteriors/'+obj['url'],
                      'sourceSha256': sha(path), 'sourceFiles': source['files'],
                      'placement': matrix.flatten(order='F').tolist(), 'triangleIndex': index,
                      'worldTriangle': triangles[index].tolist(), 'point': center.tolist(),
                      'normal': normal[index].tolist(), 'groundY': float(ground[index]),
                      'boundaryClearanceMeters': clearance,
                      'expectedEntityId': None if label == 'outside-domain' else bundle['entityId'],
                      'ray': {'origin': (center+normal[index]*.02).tolist(), 'direction': (-normal[index]).tolist()}})
dest.write_text(json.dumps({'cases': cases, 'method': 'Actual source face centroids; original nodes and outer placement applied once. Files retain original SHA. Heights are independent original 0.5 m DTM bilinear samples. Numerical fixtures are not browser visibility acceptance.'}, indent=2)+'\n')
print(json.dumps({'cases': len(cases), 'groups': len({c['bundleId'] for c in cases}), 'path': str(dest)}))
