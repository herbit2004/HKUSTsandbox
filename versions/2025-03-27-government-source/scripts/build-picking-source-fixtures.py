"""Bounded original-triangle fixtures for CPU picking; no geometry is published.
PYTHONPATH=/tmp/hkust-v3-deps python3 scripts/build-picking-source-fixtures.py
"""
from pathlib import Path
import json, hashlib
import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon
from shapely.ops import unary_union
from hkust_source_geometry import geometry, Heights

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/source-evidence-v4/entity-picking'
OUT.mkdir(parents=True, exist_ok=True)
read = lambda p: json.loads(p.read_text())
registry = read(ROOT/'public/data/entity-registry.json')
footprints = read(ROOT/'public/data/building-footprints.json')['footprints']
buildings = [e for e in registry['entities'] if e['type'] == 'building']
domains = {}
for building in buildings:
    source_id = building.get('externalIds', {}).get('pathAdvisorBuildingId')
    fps = [f for f in footprints if f['officialBuildingId'] == source_id]
    if fps:
        domains[building['entityId']] = (unary_union([Polygon(p['rings'][0],p['rings'][1:]) for f in fps for p in f['parts']]), min(f['minObservedFloorZ'] for f in fps))
named = read(ROOT/'public/data/picking/building-domains.json')['domains']
for entity_id in set(d['entityId'] for d in named):
    group = [d for d in named if d['entityId'] == entity_id]
    domains[entity_id] = (unary_union([Polygon(p['rings'][0],p['rings'][1:])for d in group for p in d['parts']]),min(d['minY']for d in group))
heights = Heights(sorted((ROOT/'public/terrain/source-data').glob('*.tif')))
cases = {}
baseline = read(ROOT/'public/models/preview-manifest.json')['tiles']
patches = read(ROOT/'public/models/hires/manifest.json')['patches']
tiles = [('baseline', t, ROOT/'public/models'/t['url']) for t in baseline]
for patch in patches:
    level = patch['levels'].get('fine') or patch['levels'].get('high')
    tiles.extend(('fine',t,ROOT/'public/models/hires'/t['url']) for t in level['tiles'])
for representation, tile, path in tiles:
    box = tile['bounds']; lo, hi = box['min'], box['max']
    candidates = [(entity_id, domain, zmin) for entity_id,(domain,zmin) in domains.items()
        if not (hi[0]<domain.bounds[0] or lo[0]>domain.bounds[2] or hi[2]<domain.bounds[1] or lo[2]>domain.bounds[3])
        and any((entity_id,representation,face) not in cases for face in ['roof','wall'])]
    if not candidates: continue
    tri,_ = geometry(path,np.asarray(tile['matrix']).reshape(4,4,order='F'))
    center = tri.mean(1); normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(normals,axis=1)
    vertical=np.abs(normals[:,1])/np.maximum(length,1e-12)
    ground=heights(np.column_stack([center[:,0]+844800,820500-center[:,2]]))
    for entity_id,domain,zmin in candidates:
        eligible=contains_xy(domain,center[:,0],center[:,2])&(center[:,1]>=zmin-.5)&np.isfinite(ground)&(length>.01)
        eligible &= (vertical<.6)|(np.abs(center[:,1]-ground)>1.25)
        # Overlapping different official buildings are deliberately ambiguous.
        for other_id,(other,other_min) in domains.items():
            if other_id != entity_id:
                eligible &= ~contains_xy(other,center[:,0],center[:,2])
        for face,condition in [('roof',vertical>=.85),('wall',vertical<=.25)]:
            key=(entity_id,representation,face)
            selected=np.flatnonzero(eligible&condition)
            if key in cases or not len(selected): continue
            # Largest eligible triangle makes a stable ray target; it is not an
            # independent semantic classifier for roofs versus vegetation.
            i=int(selected[np.argmax(length[selected])])
            cases[key]={'entityId':entity_id,'representation':representation,'faceClass':face,
                'asset':'/'+str(path.relative_to(ROOT/'public')),'tileId':tile['id'],'sourceTriangleIndex':i,
                'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'worldTriangle':tri[i].tolist(),
                'point':center[i].tolist(),'groundY':float(ground[i]),'absoluteNormalY':float(vertical[i])}
report={'purpose':'Replay actual original triangles against canonical footprint/height selection. FaceClass is slope only, not semantic source labeling.',
 'caseCount':len(cases),'cases':list(cases.values())}
(OUT/'source-triangle-fixtures.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(cases),'byRepresentation':{r:sum(k[1]==r for k in cases) for r in ['baseline','fine']},'buildings':len(set(k[0] for k in cases))}))
