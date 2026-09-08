"""Select actual source triangles for the additional official named domains.

No download or generated rendering geometry. Requires the project's source
geometry helper, numpy/Shapely/Pillow. Face categories are slope tests only.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon
from shapely.ops import unary_union
from hkust_source_geometry import geometry, Heights

ROOT = Path(__file__).resolve().parents[1]
read = lambda path: json.loads(path.read_text())
domains = read(ROOT / 'public/data/picking/building-domains-extra.json')['domains']
shapes = {d['physicalDomainId']: unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in d['parts']]) for d in domains}
heights = Heights(sorted((ROOT / 'public/terrain/source-data').glob('*.tif')))
baseline = read(ROOT / 'public/models/preview-manifest.json')['tiles']
patches = read(ROOT / 'public/models/hires/manifest.json')['patches']
bundles = read(ROOT / 'public/models/exteriors/manifest.json')['bundles']
source_owners = read(ROOT / 'public/data/picking/building-domains-extra.json')['sourceObjectOwners']
source_owners = {o['sourceObjectId']: o['entityId'] for o in source_owners}
tiles = [('baseline', t, ROOT / 'public/models' / t['url'], None) for t in baseline]
for patch in patches:
    # Highest currently available source frontier, not an artificial 'fine' role
    # applied to a preview mesh. High-only complete frontiers remain identified.
    level_name = 'fine' if 'fine' in patch['levels'] else 'high'
    for tile in patch['levels'][level_name]['tiles']:
        tiles.append((level_name, tile, ROOT / 'public/models/hires' / tile['url'], None))
for bundle in bundles:
    for obj in bundle['objects']:
        owner = source_owners.get(obj['id'], 'building:' + bundle['buildingId'])
        if owner not in {d['entityId'] for d in domains} or obj['url'].endswith('.glb'):
            continue
        matrix = np.eye(4)
        matrix[:3, 3] = obj['offset']
        tiles.append(('native-individual', {'id': obj['id'], 'bounds': obj['bounds'], 'matrix': matrix.flatten(order='F').tolist()}, ROOT / 'public/models/exteriors' / obj['url'], owner))
cases = {}
for representation, tile, path, native_owner in tiles:
    lo, hi = tile['bounds']['min'], tile['bounds']['max']
    eligible_domains = [d for d in domains if (not native_owner or d['entityId'] == native_owner)
                        and not (hi[0] < shapes[d['physicalDomainId']].bounds[0] or lo[0] > shapes[d['physicalDomainId']].bounds[2]
                                 or hi[2] < shapes[d['physicalDomainId']].bounds[1] or lo[2] > shapes[d['physicalDomainId']].bounds[3])
                        and any((d['physicalDomainId'], representation, face) not in cases for face in ['roof-like', 'wall-like'])]
    if not eligible_domains:
        continue
    triangles, _ = geometry(path, np.array(tile['matrix']).reshape(4, 4, order='F'))
    centers = triangles.mean(1)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    size = np.linalg.norm(normals, axis=1)
    normal_y = np.abs(normals[:, 1]) / np.maximum(size, 1e-12)
    ground = heights(np.column_stack([centers[:, 0] + 844800, 820500 - centers[:, 2]]))
    for domain in eligible_domains:
        polygon = shapes[domain['physicalDomainId']]
        eligible = contains_xy(polygon, centers[:, 0], centers[:, 2]) & (centers[:, 1] >= domain['minY'] - .5)
        eligible &= np.isfinite(ground) & (size > .01) & ((normal_y < .6) | (np.abs(centers[:, 1] - ground) > 1.25))
        for other in domains:
            if other['entityId'] != domain['entityId']:
                # Keep separate negative fixtures for genuine shared edges;
                # positive samples must clear the runtime's documented tolerance.
                eligible &= ~contains_xy(shapes[other['physicalDomainId']].buffer(other.get('boundaryToleranceMeters', 0)), centers[:, 0], centers[:, 2])
        for face, slope in [('roof-like', normal_y >= .85), ('wall-like', normal_y <= .25)]:
            key = (domain['physicalDomainId'], representation, face)
            indices = np.flatnonzero(eligible & slope)
            if key in cases or not len(indices):
                continue
            index = int(indices[np.argmax(size[indices])])
            cases[key] = {
                'entityId': domain['entityId'], 'physicalDomainId': domain['physicalDomainId'],
                'sourceComponentId': domain.get('componentId'), 'representation': representation,
                'faceClass': face, 'asset': '/' + str(path.relative_to(ROOT / 'public')),
                'sourceSha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sourceTriangleIndex': index,
                'sourceId': tile['id'], 'placement': tile['matrix'],
                'worldTriangle': triangles[index].tolist(), 'point': centers[index].tolist(),
                'groundY': float(ground[index]), 'absoluteNormalY': float(normal_y[index]),
                'nativeSourceOwner': native_owner,
            }
coverage = [{'entityId': d['entityId'], 'physicalDomainId': d['physicalDomainId'],
             'representationsWithActualTriangles': sorted({c['representation'] for c in cases.values() if c['physicalDomainId'] == d['physicalDomainId']}),
             'nativeIndividualSourceProven': any(c['physicalDomainId'] == d['physicalDomainId'] and c['representation'] == 'native-individual' for c in cases.values())}
            for d in domains]
report = {'purpose': 'Current actual asset triangle replay. Roof-like/wall-like indicates slope only, not independently verified roof/tree semantics or visual quality.',
          'cases': list(cases.values()), 'coverage': coverage,
          'inputSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT / 'public/data/picking/building-domains-extra.json', ROOT / 'public/models/hires/manifest.json']}}
out = ROOT / 'docs/source-evidence-v4/entity-picking/named-domain-source-fixtures.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'cases': len(cases), 'domains': len(coverage), 'nativeDomains': sum(r['nativeIndividualSourceProven'] for r in coverage),
                  'byRepresentation': {r: sum(c['representation'] == r for c in cases.values()) for r in ['baseline', 'high', 'fine', 'native-individual']}}))
