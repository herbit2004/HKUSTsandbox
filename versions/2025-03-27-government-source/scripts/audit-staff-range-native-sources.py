#!/usr/bin/env python3
"""Stage five original range-envelope models; do not invent single-tower owners.

All inputs already exist locally. No live manifest or registry is modified.
"""
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from affine import Affine
from PIL import Image, ImageFilter
from rasterio.features import rasterize
from shapely.geometry import Point, Polygon, mapping
from shapely.ops import unary_union

from hkust_source_geometry import geometry

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/source-evidence-v4/building-quality'
DEST = Path('/tmp/hkust-v7-northern-exteriors/staff-range-five')
OLD = Path('/tmp/hkust-hires-geodata/individualised-source/buildings')
NEW = Path('/tmp/hkust-v7-northern-exteriors/staff-aggregate-5-7')
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
domains = read(ROOT / 'public/data/picking/building-domains-extra.json')['auditOnlyAggregateDomains']
targets = [
    (5, 7, '1101775236', 'B453782220901063A0'),
    (8, 11, '1101776570', 'B454912174801063A0'),
    (12, 14, '1101776670', 'B455062169901063A0'),
    (15, 17, '1101776664', 'B456202166401063A0'),
    (18, 19, '1101776842', 'B456282160501063A0'),
]
matrix = np.eye(4); matrix[:3, 3] = [-844800, 0, 820500]
for d in ['objects', 'masks']:
    (DEST / d).mkdir(parents=True, exist_ok=True)


def projection(tri):
    normal = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    return unary_union([Polygon(t[:, [0, 2]]) for t in tri[abs(normal[:, 1]) > 1e-9]])


def mip_bytes(w, h):
    total = 0
    while True:
        total += w*h*4
        if w == h == 1:
            return total
        w, h = max(1, w//2), max(1, h//2)


def connectivity(tri):
    """Geometric vertex connectivity is diagnostic, never tower identity."""
    _, inverse = np.unique(np.round(tri.reshape(-1, 3)/.0001).astype(np.int64), axis=0, return_inverse=True)
    ids = inverse.reshape(-1, 3)
    parent = np.arange(len(tri)); seen = {}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    for i, vertices in enumerate(ids):
        for v in vertices:
            if int(v) in seen:
                parent[find(i)] = find(seen[int(v)])
            else:
                seen[int(v)] = i
    groups = {}
    for i in range(len(tri)):
        groups.setdefault(int(find(i)), []).append(i)
    items = sorted(groups.values(), key=len, reverse=True)
    return {'positionMergeToleranceMeters': .0001, 'componentCount': len(items),
            'largestComponentTriangles': [len(v) for v in items[:15]],
            'largestComponentShare': len(items[0])/len(tri),
            'identityMeaning': 'None. Disconnected windows, balcony pieces and source modelling seams can create components; no component is assigned a tower number.'}


def upper_support(tri):
    """Exact original faces clipped above height, then projected into XZ.

    Projection connectivity is not proof of a structural connection between
    overlapping surfaces at different heights. No tower identities are inferred.
    """
    low, high = tri[:, :, 1].min(), tri[:, :, 1].max()
    result = []
    for fraction in [.25, .5, .75]:
        level = low+(high-low)*fraction
        polygons = []
        for face in tri:
            vertices = []
            for i in range(3):
                p, q = face[i], face[(i+1) % 3]
                inside_p, inside_q = p[1] >= level, q[1] >= level
                if inside_p:
                    vertices.append(p)
                if inside_p != inside_q:
                    vertices.append(p+(q-p)*(level-p[1])/(q[1]-p[1]))
            if len(vertices) >= 3:
                polygon = Polygon(np.array(vertices)[:, [0, 2]])
                if polygon.area > 1e-9:
                    polygons.append(polygon)
        shape = unary_union(polygons)
        parts = list(shape.geoms) if shape.geom_type == 'MultiPolygon' else [shape]
        result.append({'fractionOfSourceHeightSpan': fraction, 'cutY': float(level),
                       'componentCountAll': len(parts),
                       'componentsLargerThan10M2': sorted([p.area for p in parts if p.area > 10], reverse=True),
                       'projection': mapping(shape)})
    return result


annotations = []
for path in sorted((EVIDENCE / 'identity-sources').glob('*/BuildingAnno.gml')):
    root = ET.parse(path).getroot()
    for feature in root.findall('.//{http://www.safe.com/gml/fme}BuildingAnno'):
        props = {c.tag.split('}')[-1]: c.text for c in feature if c.tag.startswith('{http://www.safe.com/gml/fme}')}
        raw = feature.find('.//{http://www.opengis.net/gml}pos')
        if raw is None:
            continue
        n, e = map(float, raw.text.split())
        annotations.append({'sourceFile': str(path.relative_to(ROOT)), 'sourceFileSha256': sha(path),
                            'localXZ': [e-844800, 820500-n], **props})

bundles = []; ranges = []; tower_rows = []
for start, end, building_id, oid in targets:
    record = next(d for d in domains if d['sourceBuildingId'] == building_id)
    domain = unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in record['parts']])
    origin = NEW/'objects'/oid if start == 5 else OLD/oid
    path = origin/(oid+'.gltf'); gltf = read(path)
    if start == 5:
        files = [f for f in read(NEW/'source-downloads.json')['files'] if f['sourceObjectId'] == oid]
        candidate = next(c for c in read(EVIDENCE/'northern-individual-source-candidates.json')['candidates'] if c['id'] == oid)
        source_url, revision = candidate['url'], '2025-03-27'
    else:
        original = read(origin/'manifest.json'); files = original['files']
        source_url, revision = original['source_archive_uri'], original['source_tile_revision_date']
    directory = DEST/'objects'/oid; directory.mkdir(exist_ok=True)
    for item in files:
        assert sha(origin/item['filename']) == item['sha256']
        shutil.copyfile(origin/item['filename'], directory/item['filename'])
    dims = []
    for image in gltf['images']:
        with Image.open(origin/image['uri']) as im:
            dims.append(list(im.size)); im.verify()
    tri, _ = geometry(path, matrix); shape = projection(tri)
    intersection = shape.intersection(domain).area
    assert intersection/domain.area > .98
    lo, hi = tri.min((0, 1)), tri.max((0, 1))
    source = {'id': oid, 'level_code': '3A', 'source_archive_uri': source_url,
              'source_revision_date': revision, 'capture_date': None, 'files': files,
              'file_bytes': sum(f['bytes'] for f in files), 'original_nodes': gltf['nodes'],
              'geometry': {'triangles': len(tri), 'textures': [
                  {'uri': image['uri'], 'dimensions_pixels': dims[i]} for i, image in enumerate(gltf['images'])]},
              'originalMetadataPath': str(origin/'manifest.json') if start != 5 else str(NEW/'source-downloads.json')}
    (directory/'source-manifest.json').write_text(json.dumps(source, indent=2)+'\n')
    obj = {'id': oid, 'url': f'objects/{oid}/{oid}.gltf', 'offset': [-844800, 0, 820500],
           'bounds': {'min': lo.tolist(), 'max': hi.tolist()}, 'triangles': len(tri),
           'textureDecodedBytes': sum(w*h*4 for w, h in dims),
           'textureMipBytes': sum(mip_bytes(w, h) for w, h in dims),
           'textureDimensions': dims, 'textureMaxDimension': max(max(d) for d in dims),
           'textureFiles': [{'url': f'objects/{oid}/{image["uri"]}', 'width': dims[i][0], 'height': dims[i][1],
                             'decodedBytes': dims[i][0]*dims[i][1]*4} for i, image in enumerate(gltf['images'])],
           'assetBytes': source['file_bytes'], 'sourceManifest': f'objects/{oid}/source-manifest.json',
           'sourceUrl': source_url, 'sourceLevelCode': '3A', 'gltfSha256': sha(path),
           'ownership': 'domain-only', 'subtype': 'original-individualised-staff-range-envelope'}
    key = f'staff-quarters-towers-{start}-{end}'
    x0, z0 = np.floor(lo[[0, 2]])-1; x1, z1 = np.ceil(hi[[0, 2]])+1
    width, height = int((x1-x0)*2), int((z1-z0)*2)
    pixels = rasterize([(mapping(shape), 255)], out_shape=(height, width),
                       transform=Affine(.5, 0, x0, 0, .5, z0), dtype='uint8', all_touched=False)
    exact = DEST/'masks'/f'{key}.exact.png'; guarded = DEST/'masks'/f'{key}.png'
    Image.fromarray(pixels).save(exact)
    Image.fromarray(pixels).filter(ImageFilter.MaxFilter(3)).save(guarded)
    mask = {'url': f'masks/{key}.png', 'exactUrl': f'masks/{key}.exact.png',
            'boundsXZ': {'min': [float(x0), float(z0)], 'max': [float(x1), float(z1)]},
            'width': width, 'height': height, 'heightMin': float(lo[1]-.5), 'heightMax': float(hi[1]+5),
            'pixelSizeMeters': .5, 'metersPerPixel': .5, 'textureFlipY': False,
            'rowDirection': 'increasing local Z', 'channel': 'red', 'occupiedValue': 255,
            'emptyValue': 0, 'sha256': sha(guarded)}
    evidence = {'sourceBuildingId': building_id, 'sourceProjectionAreaM2': shape.area,
                'officialDomainAreaM2': domain.area, 'intersectionM2': intersection,
                'officialDrawingCoveredRatio': intersection/domain.area,
                'sourceProjectionInsideOfficialRatio': intersection/shape.area}
    bundles.append({'id': key, 'entityId': record['entityId'], 'physicalDomainId': record['physicalDomainId'],
                    'integrationStatus': 'explicit existing range entity; no invented single-tower buildingId',
                    'catalogIds': [record['entityId'].removeprefix('zone:catalog:')],
                    'buildingName': f'Staff Quarters Towers {start}–{end}',
                    'sourceDates': {'revisionDate': revision, 'captureDate': None},
                    'name': f'Staff Quarters Towers {start}–{end}', 'objects': [obj], 'mask': mask,
                    'bounds': obj['bounds'], 'center': ((lo+hi)/2).tolist(), 'triangles': len(tri),
                    'textureDecodedBytes': obj['textureDecodedBytes'], 'textureMipBytes': obj['textureMipBytes'],
                    'assetBytes': obj['assetBytes'], 'matchEvidence': evidence})
    near_annotations = [a for a in annotations if domain.distance(Point(a['localXZ'])) < 30]
    inside_annotations = [a for a in near_annotations if domain.covers(Point(a['localXZ']))]
    names = [n.get('name') for n in gltf['nodes'] if n.get('name')]
    assert names == [oid]
    report = {'range': [start, end], 'entityId': record['entityId'], 'physicalDomainId': record['physicalDomainId'],
              'sourceBuildingId': building_id, 'officialSheetFragments': len(record['sourceFragments']),
              'unionPolygonComponents': len(domain.geoms) if domain.geom_type == 'MultiPolygon' else 1,
              'annotation': record['annotation'], 'allInsideAnnotations': inside_annotations,
              'allAnnotationsWithin30m': near_annotations, 'sourceObjectId': oid,
              'triangles': len(tri), 'textureDimensions': dims, 'textureMipMiB': obj['textureMipBytes']/2**20,
              'gltfSha256': sha(path), 'sourceRevisionDate': revision, 'captureDate': None,
              'originalNodeNames': names, 'meshCount': len(gltf['meshes']),
              'primitiveCount': sum(len(m['primitives']) for m in gltf['meshes']),
              'geometryConnectivity': connectivity(tri), 'sourceActualBounds': obj['bounds'],
              'upperSourceSupport': upper_support(tri),
              'upperSupportMeaning': 'All original triangles clipped exactly above each source-height fraction; XZ union only, without filling, snapping or buffering. Connected projection does not prove a common structural podium or resolve tower-number boundaries.',
              'sourceProjection': mapping(shape), 'domainOverlap': evidence,
              'singleTowerOrdinalBinding': False,
              'reason': 'The saved official annotation names a tower range and the closed Building ID is shared by that range. Original model nodes name only the source object ID; original primitives are materials, not tower owners. No existing individual-number control point or separate numbered closed domain establishes which body is Tower N.'}
    ranges.append(report)
    for number in range(start, end+1):
        tower_rows.append({'name': f'Staff Quarters Tower {number}', 'towerNumber': number,
                           'existingRangeEntityId': record['entityId'], 'physicalDomainId': record['physicalDomainId'],
                           'sourceObjectIds': [oid], 'individualCanonicalId': None,
                           'individuallyLocated': False, 'individualPhysicalDenominatorConfirmed': False,
                           'closedOfficialDomainScope': f'Towers {start}–{end}',
                           'sourceReadyAsWholeRange': True, 'splitDecision': 'do-not-split-with-current-evidence',
                           'reason': report['reason']})

adjacent_path = NEW/'objects/B453692221102063A0/B453692221102063A0.gltf'
adjacent, _ = geometry(adjacent_path, matrix)
adjacent_projection = projection(adjacent)
record57 = next(d for d in domains if d['sourceBuildingId'] == '1101775236')
domain57 = unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in record57['parts']])
rejected = {'sourceObjectId': adjacent_path.stem, 'gltfSha256': sha(adjacent_path), 'triangles': len(adjacent),
            'actualProjectionAreaM2': adjacent_projection.area,
            'staff5to7DomainIntersectionM2': adjacent_projection.intersection(domain57).area,
            'actualBounds': {'min': adjacent.min((0, 1)).tolist(), 'max': adjacent.max((0, 1)).tolist()},
            'decision': 'Original raw files retained; excluded from Staff 5–7 model. Almost zero actual domain intersection does not establish a complementary tower body or shared podium owner.'}
summary = {'status': 'staged-source-verified; visual acceptance and range-entity integration pending',
           'stagingDirectory': str(DEST), 'namedOrdinalsAudited': len(tower_rows),
           'newIndividuallyConfirmedTowers': 0, 'officialConnectedRangeEnvelopes': len(ranges),
           'physicalBuildingCountMeaning': 'Five connected official range polygons and five original model groups are verified. Neither establishes the count or per-number positions of physical towers. The 15 ordinal names remain unresolved for individual picking.',
           'ranges': ranges, 'towerRows': tower_rows, 'excludedAdjacentObject': rejected,
           'assetMiB': sum(b['assetBytes'] for b in bundles)/2**20,
           'textureMipMiB': sum(b['textureMipBytes'] for b in bundles)/2**20,
           'originalGeometryTextureUVNodesUnchanged': True, 'liveAssetsModified': False,
           'browserAppearanceAcceptance': 'pending; source-only numerical checks cannot certify current appearance'}
(DEST/'manifest.json').write_text(json.dumps({'version': 1, 'bundles': bundles,
    'integrationNote': 'Staging descriptors intentionally have entityId (existing zone) instead of fabricated buildingId. Keep range identity until independent numbered tower evidence is available.'}, indent=2)+'\n')
(EVIDENCE/'staff-range-native-audit.json').write_text(json.dumps(summary, indent=2)+'\n')
lines = ['# Staff 5–19 原生源与实体边界核验', '',
         '只使用已保存原始资料。5 个官方连通范围域可对应 5 个完整原生 3A 对象，但无法由这些资料把范围内 15 个编号分别定位；这不是确认只有 5 栋物理楼。', '',
         '| 官方范围 | 原生对象 | 原始三角 | 原纹理 mip MiB | 实际三角投影覆盖官方域 |',
         '|---|---|---:|---:|---:|']
for r in ranges:
    lines.append(f'| Tower {r["range"][0]}–{r["range"][1]} | {r["sourceObjectId"]} | {r["triangles"]:,} | {r["textureMipMiB"]:.3f} | {r["domainOverlap"]["officialDrawingCoveredRatio"]*100:.3f}% |')
lines += ['', '每个原 glTF 都只有来源编号作为根节点名称。材质 primitive 和几何连通件没有塔号语义，不能借组件数量强拆。原 iB1000 的单个 BUILDINGID 覆盖对应范围；跨图幅相同 ID 的片段先合并，不把图幅切口算作楼体分界。', '',
          'Tower 5–19 的逐名审计见 JSON 中 towerRows：每个编号均保留所属官方范围与原生对象，individualCanonicalId 为空。现有 range zone 仍保留；这批暂存描述使用 entityId + physicalDomainId，不制造 buildingId。', '',
          'Staff 5–7 邻近低对象 B453692221102063A0 虽然矩形范围相邻，真实投影与 Staff 5–7 域只相交约 0.004 m²，因此未拼入该楼群。原下载仍保留。', '',
          '原源高度跨度的 50% 以上三角经精确裁切后，五组均保留一个主要连通平面投影；75% 处出现不同的阶梯高部件，数量与塔号数量不一致。这支持原生模型是连续／阶梯排楼式表示，不能据此证明法定物理分栋、共裙房结构或塔号边界。投影重叠不等于不同高度之间真实连接。', '',
          '原图像、UV、节点矩阵及几何原样保留。遮罩来自全部实际三角投影的 0.5 m 像元中心判定，另存 exact 与一像元接缝 guard，不用矩形或凸包填域。来源修订日不等于摄影日期；数值覆盖与原文件检查不代替实际浏览验收。']
(EVIDENCE/'staff-range-native-audit.zh.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k: v for k, v in summary.items() if k not in ['ranges', 'towerRows']}, indent=2))
