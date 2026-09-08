#!/usr/bin/env python3
"""Join canonical buildings to actual native coverage and saved source frontiers.

No network calls. A projection percentage is not facade/image/era acceptance.
Source-node bounding boxes are used only for acquisition planning, never masks.
"""
import hashlib, itertools, json
from pathlib import Path
import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize
from shapely import contains_xy
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from hkust_source_geometry import geometry

P = Path(__file__).resolve().parents[1]
O = P/'docs/source-evidence-v4/building-quality'; O.mkdir(parents=True, exist_ok=True)
C = Path('/tmp/hkust-v6-building-native/coverage-cache'); C.mkdir(parents=True, exist_ok=True)
read = lambda p: json.loads(p.read_text())
registry = read(P/'public/data/entity-registry.json')
buildings = [e for e in registry['entities'] if e['type'] == 'building']
footprints = read(P/'public/data/building-footprints.json')['footprints']
extra = read(P/'public/data/picking/building-domains.json')['domains']
extra_file = P/'public/data/picking/building-domains-extra.json'
if extra_file.exists(): extra += read(extra_file)['domains']
baseline = read(P/'public/models/preview-manifest.json')['tiles']
main = read(P/'public/models/hires/manifest.json')['patches']
staged_file = P/'public/models/hires/partial-residential-ias/manifest.json'
staged = read(staged_file)['patches'] if staged_file.exists() else []
patches = [(p, 'published') for p in main]
patches += [(p, 'staged-independent-qa') for p in staged if p['id'] not in {a['id'] for a in main}]
exteriors = read(P/'public/models/exteriors/manifest.json')['bundles']

def shape(parts):
    return unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in parts])

rows = []
for e in buildings:
    sources = [f for f in footprints if f['officialBuildingId'] == e.get('externalIds', {}).get('pathAdvisorBuildingId')]
    additions = [d for d in extra if d['entityId'] == e['entityId']]
    parts = [p for f in sources for p in f['parts']] + [p for d in additions for p in d['parts']]
    domain = shape(parts) if parts else None
    point = next((r['position'] for r in e['representations'] if r['type'] == 'reference_point' and r.get('position')), None)
    if domain is not None:
        lo = np.floor(np.array(domain.bounds[:2])*2)/2; hi = np.ceil(np.array(domain.bounds[2:])*2)/2
        xx, zz = np.meshgrid(np.arange(lo[0]+.25, hi[0], .5), np.arange(lo[1]+.25, hi[1], .5))
        inside = contains_xy(domain, xx, zz); sample = np.c_[xx[inside], zz[inside]]
        selection = domain.buffer(10)
    else:
        sample = np.array([[point[0], point[2]]]) if point else np.empty((0, 2))
        selection = Point(*sample[0]) if len(sample) else None
    rows.append({'canonicalId': e['entityId'], 'name': e['name'], 'legacyIds': e.get('externalIds', {}).get('legacyCatalogIds', []),
        'domainSource': 'official-drawing-parts-and-holes' if sources else 'official-named-iB1000-closed-polygon' if additions else 'verified-reference-point-only' if point else 'not-georeferenced-in-existing-data',
        'domainAreaM2': domain.area if domain is not None else None,
        'domainGridSampleCount': len(sample) if domain is not None else None,
        'referencePosition': point, 'existingRepresentations': [r['type'] for r in e['representations']],
        'sourceFloorZRange': [min(f['minObservedFloorZ'] for f in sources), max(f['maxObservedFloorZ'] for f in sources)] if sources else None,
        'sourceIBaseRoofMetadata': [{'id': d['sourceBuildingId'], 'base': d['minY'], 'roof': d['maxY']} for d in additions],
        'nativeProjection': [], 'availableSourceRegions': [], 'individualBundle': next((b['id'] for b in exteriors if (b.get('entityId') or 'building:'+b.get('buildingId','')) == e['entityId']), e.get('externalIds', {}).get('exteriorBundleId')),
        'visualAcceptance': 'pending-multiple-views', '_domain': domain, '_sample': sample, '_selection': selection})

def read_mask(mm, root):
    return np.asarray(Image.open(root/mm['url']).convert('RGB'))[:, :, 0], mm

def sample_mask(array, mm, points):
    x = points[:, 0]; z = points[:, 1]
    within = (x >= mm['minX']) & (x < mm['maxX']) & (z >= mm['minZ']) & (z < mm['maxZ'])
    selected = np.zeros(len(points), bool)
    rows = np.minimum(array.shape[0]-1, ((z[within]-mm['minZ'])/(mm['maxZ']-mm['minZ'])*array.shape[0]).astype(int))
    cols = np.minimum(array.shape[1]-1, ((x[within]-mm['minX'])/(mm['maxX']-mm['minX'])*array.shape[1]).astype(int))
    selected[within] = array[rows, cols] > 127
    return selected

for patch, publication in patches:
    level_name = 'fine' if 'fine' in patch['levels'] else 'high'; level = patch['levels'][level_name]
    mm = level.get('mask', patch.get('mask'))
    if mm:
        array, mm = read_mask(mm, P/'public/models/hires')
    else:
        key = hashlib.sha256(json.dumps([(t['url'], t.get('sha256'), t['matrix']) for t in level['tiles']]).encode()).hexdigest()[:16]
        meta = C/(key+'.json'); image = C/(key+'.png')
        if meta.exists() and image.exists():
            mm = read(meta); array = np.asarray(Image.open(image))
        else:
            triangles = [geometry(P/'public/models/hires'/t['url'], np.array(t['matrix']).reshape(4, 4, order='F'))[0] for t in level['tiles']]
            tri = np.concatenate(triangles); lo = np.floor(tri.min((0, 1))[[0, 2]]); hi = np.ceil(tri.max((0, 1))[[0, 2]])
            cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]); xz = tri[abs(cross[:, 1]) > 1e-9][:, :, [0, 2]]
            mm = {'minX': float(lo[0]), 'minZ': float(lo[1]), 'maxX': float(hi[0]), 'maxZ': float(hi[1])}
            array = rasterize((({'type': 'Polygon', 'coordinates': [[*t.tolist(), t[0].tolist()]]}, 255) for t in xz),
                out_shape=(int((hi[1]-lo[1])*2), int((hi[0]-lo[0])*2)), transform=Affine(.5, 0, lo[0], 0, .5, lo[1]), dtype='uint8', all_touched=False)
            Image.fromarray(array).save(image); meta.write_text(json.dumps(mm))
    print('PROJECTION', patch['id'], publication, flush=True)
    for row in rows:
        samples = row['_sample']
        if not len(samples): continue
        covered = sample_mask(array, mm, samples)
        if not covered.any(): continue
        row['nativeProjection'].append({'patchId': patch['id'], 'level': level_name, 'publication': publication,
            'coveredSamples': int(covered.sum()), 'projectionPercent': float(covered.mean()*100),
            'isDomainPercentage': row['_domain'] is not None,
            'textureMipMiBForAtomicGroup': sum(t.get('textureMipBytes', 0) for t in level['tiles'])/2**20,
            'autoLevelPolicy': 'normal-near projected-error selection, subject to complete neighbour/budget reservation' if level_name == 'fine' else 'complete high or terminal-only level', 'maskIsActualTriangles': True})

by_region = {}
for tile in baseline: by_region.setdefault('/'.join(tile['id'].split('/')[:2]), []).append(tile)
planned_leaves = {t['id'] for p, _ in patches for l in p['levels'].values() for t in l['tiles']}
all_regions = []
for region, base_tiles in by_region.items():
    sheet, sub = region.split('/')
    candidates = [row for row in rows if row['_selection'] is not None and any(box(t['bounds']['min'][0], t['bounds']['min'][2], t['bounds']['max'][0], t['bounds']['max'][2]).intersects(row['_selection']) for t in base_tiles)]
    if not candidates: continue
    source = P/'source-geodata/mesh'/sheet
    source_file = source/sub/'source-tileset.json'
    if not source_file.exists():
        for row in candidates: row['availableSourceRegions'].append({'id': region, 'sourceIndexAvailable': False})
        continue
    entries = read(source/'source-zip-index.json'); tree = read(source_file)
    matrices = {tuple(t['matrix']) for t in base_tiles}; assert len(matrices) == 1
    matrix = np.array(next(iter(matrices))).reshape(4, 4, order='F')
    leaves = []; unsupported_transform = []
    def visit(node, depth=0):
        if depth and 'transform' in node: unsupported_transform.append(depth)
        children = node.get('children', [])
        if children:
            for child in children: visit(child, depth+1)
            return
        uri = node.get('content', {}).get('uri', node.get('content', {}).get('url'))
        if not uri: return
        values = node['boundingVolume'].get('box', node['boundingVolume'].get('sphere'))
        if len(values) != 12: return
        center = np.array(values[:3]); axes = np.array(values[3:]).reshape(3, 3)
        points = np.array([center+np.array(sign)@axes for sign in itertools.product([-1, 1], repeat=3)])
        world = points@matrix[:3, :3].T+matrix[:3, 3]; lo = world.min(0); hi = world.max(0)
        name = sub+'/'+uri; entry = entries.get(name)
        leaves.append({'id': sheet+'/'+name.removesuffix('.b3dm'), 'sourceName': name,
            'originalError': node.get('geometricError'), 'available': bool(entry),
            'bytes': entry['size'] if entry else None, 'alreadyDownloaded': sheet+'/'+name.removesuffix('.b3dm') in planned_leaves,
            'bounds': {'min': lo.tolist(), 'max': hi.tolist()}, '_box': box(lo[0], lo[2], hi[0], hi[2])})
    visit(tree['root']); assert not unsupported_transform, (region, unsupported_transform)
    for row in candidates:
        selected = [leaf for leaf in leaves if leaf['_box'].intersects(row['_selection'])]
        present = [leaf for leaf in selected if leaf['available']]
        missing = [leaf for leaf in selected if not leaf['available']]
        row['availableSourceRegions'].append({'id': region, 'sourceIndexAvailable': True,
            'selectionBasis': 'full source domain +10m acquisition guard' if row['_domain'] is not None else 'reference point only, no building coverage claim',
            'availableTerminalLeaves': len(present), 'sourceEncodedMiB': sum(leaf['bytes'] for leaf in present)/2**20,
            'alreadyDownloadedTerminalLeaves': sum(leaf['alreadyDownloaded'] for leaf in present),
            'maximumAvailableLeafError': max((leaf['originalError'] for leaf in present), default=None),
            'missingTerminalNames': [leaf['sourceName'] for leaf in missing],
            'sourcePlanLeafIds': [leaf['id'] for leaf in present],
            'baselineTileIds': [t['id'] for t in base_tiles],
            'sourceTreeSha256': hashlib.sha256(source_file.read_bytes()).hexdigest()})
    all_regions.append({'id': region, 'leafCount': len(leaves), 'available': sum(l['available'] for l in leaves),
        'missing': [l['sourceName'] for l in leaves if not l['available']]})

for row in rows:
    row['sourceCoverageConclusion'] = ('No verified geographic domain; cannot infer whole-building coverage from a point.' if row['_domain'] is None else
        'Independent exterior source group exists; native-ground projection still needs separate facade/roof comparison.' if row['individualBundle'] else
        'Native projection available; whole-building multi-angle/current-era quality remains unaccepted.' if row['nativeProjection'] else
        'No published higher-detail projection on the verified building domain; currently native baseline unless a separate current-form representation exists.')
    row['missingAvailableSourceLeaves'] = sum(r.get('availableTerminalLeaves', 0)-r.get('alreadyDownloadedTerminalLeaves', 0) for r in row['availableSourceRegions'])
    for key in ['_domain', '_sample', '_selection']: del row[key]
report = {'checkedAt': '2026-09-06', 'scope': f'{len(buildings)} current canonical building audit rows; join canonicalId to the separate named-building inventory. This count is not a confirmed independent physical-building denominator.',
    'sampling': '0.5m pixel-centre sampling of actual transformed triangle projection within original parts and holes; no AABB is counted as completed building coverage.',
    'sourceEra': 'Lands Department 3DVM saved metadata revision2025-03-27; capture date not established. Official HallXI-XIII completion photos are2026-05-22. Revision/publication/capture dates are distinct.',
    'autoFinding': 'Former high.meshFine=false hard restriction has been removed from near selection. Current Auto/high uses projected source error with pixel/distance hysteresis, reserves complete high frontiers of visible near neighbours, then upgrades eligible groups within budget. Entrance four high groups consume about1013MiB, so1024MiB cannot also fund their1746MiB terminal frontiers. Terminal-only groups use one atomic reservation; far groups are ranked after near groups.',
    'limitations': ['Horizontal coverage includes roofs, vegetation or ground. It is not a facade completeness or visual sharpness score.',
        'Source acquisition lists use conservative node bounding boxes and a10m guard, never geometry masks; actual projection must be verified after download.',
        'Rows that have only a reference point cannot establish whole-building coverage. Missing known siblings are not requested.',
        'All visualAcceptance entries stay pending until real multi-angle browser and dated-photo comparison.'], 'rows': rows, 'sourceRegions': all_regions}
(O/'native-building-coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
lines = ['# 原生建筑细节覆盖审计', '', report['scope'], '', '投影覆盖不是完整立面、现状或清晰度验收。所有楼仍需同距离多角度运行检查。', '',
    '| 稳定ID／建筑 | 定位证据 | 已发布最高投影覆盖 | 另有待接入 | 可取未下末叶 | 当前判断 |', '|---|---|---|---|---:|---|']
for row in rows:
    pub = '; '.join(f"{p['patchId']} {p['projectionPercent']:.1f}%" for p in row['nativeProjection'] if p['publication'] == 'published') or '无'
    pending = '; '.join(f"{p['patchId']} {p['projectionPercent']:.1f}%" for p in row['nativeProjection'] if p['publication'] != 'published') or '—'
    lines.append(f"| {row['canonicalId']}<br>{row['name']} | {row['domainSource']} | {pub} | {pending} | {row['missingAvailableSourceLeaves']} | 待多角度验收；独立组：{row['individualBundle'] or '无'} |")
lines += ['', 'Auto 近景已允许按投影误差选择完整 fine；先保留邻近完整 high 覆盖，再按剩余预算升级。入口四片终级约1746MiB，1024MiB内不能全部驻留。终级仅置于 high 的新组仍按完整纹理组计预算；不能把预算限制称为源数据不足。', '', '完整机器证据：[native-building-coverage.json](native-building-coverage.json)。']
(O/'native-building-coverage.zh-CN.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'rows': len(rows), 'domainRows': sum(r['domainAreaM2'] is not None for r in rows), 'regions': len(all_regions)}, ensure_ascii=False))
