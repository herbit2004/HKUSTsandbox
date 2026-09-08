#!/usr/bin/env python3
"""Acquire four bounded, indexed original objects and stage actual-source masks.

No live manifest/runtime edits. The original ZIP-entry bytes, CRC, source node
matrices, positions, UVs and images remain unchanged. Candidate accessor bounds
are only an acquisition filter; identity evidence below uses actual triangles.
"""
import argparse
import concurrent.futures
import hashlib
import json
import struct
import time
import urllib.request
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union
from hkust_source_geometry import geometry

P = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--plan', help='Optional bounded source-candidate/domain/staging plan JSON.')
parser.add_argument('--download-only', action='store_true', help='Validate original ZIP files without assigning any building or generating a mask.')
args = parser.parse_args()
plan = json.loads(Path(args.plan).read_text()) if args.plan else {}
INDEX = Path('/tmp/hkust-v6-building-native/individual-index')
D = Path(plan.get('stagingDirectory', '/tmp/hkust-v6-next-institutional-exteriors'))
REPORT = P / 'docs/source-evidence-v4/building-quality' / plan.get('report', 'next-individual-exteriors-staging.json')
read = lambda p: json.loads(p.read_text())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
TARGETS = {
    'B453382157301063A0': ('campus-24', 'Lee Shau Kee Business Building'),
    'B454812152101063A0': ('campus-28', 'IAS / Lo Ka Chung Building'),
    'B454972146001063A0': ('campus-30', 'Conference Lodge'),
    'B457762207601063A0': ('campus-53', 'Water Sports Centre'),
}
if plan:
    TARGETS = {oid: (target['id'], '') for oid, target in plan['targets'].items()}
candidate_file = Path(plan.get('candidatesFile', INDEX / 'target-building-candidates.json'))
if not candidate_file.exists():
    candidate_file = P / 'docs/source-evidence-v4/building-quality/next-individual-source-candidates.json'
candidates = [c for c in read(candidate_file)['candidates'] if c['id'] in TARGETS]
assert len(candidates) == len(TARGETS)

def fetch_entry(job):
    candidate, entry = job
    destination = D / 'objects' / candidate['id'] / Path(entry['name']).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        payload = destination.read_bytes()
        assert len(payload) == entry['size'] and zlib.crc32(payload) == entry['crc32']
    else:
        for attempt in range(3):
            try:
                offset = entry['offset']
                request = urllib.request.Request(candidate['url'], headers={'Range': f'bytes={offset}-{offset + entry["compressed"] + 1024}'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    assert response.status == 206
                    raw = response.read()
                header = struct.unpack_from('<4s5H3L2H', raw)
                assert header[0] == b'PK\x03\x04' and header[3] == entry['compression']
                length = 30 + header[-2] + header[-1]
                assert raw[30:30+header[-2]].decode('utf8') == entry['name']
                payload = raw[length:length + entry['compressed']]
                if entry['compression'] == 8:
                    payload = zlib.decompress(payload, -15)
                else:
                    assert entry['compression'] == 0
                assert len(payload) == entry['size'] and zlib.crc32(payload) == entry['crc32']
                destination.write_bytes(payload)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    return {'filename': destination.name, 'bytes': len(payload), 'sha256': sha(payload), 'zipEntry': entry}

def mip_bytes(width, height):
    total = 0
    while True:
        total += width * height * 4
        if width == height == 1:
            return total
        width, height = max(1, width // 2), max(1, height // 2)

jobs = [(candidate, entry) for candidate in candidates for entry in candidate['files']]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    fetched = list(pool.map(fetch_entry, jobs))
if args.download_only:
    (D / 'source-downloads.json').write_text(json.dumps({'status': 'original-files-only-no-owner-assignment',
        'files': [{'sourceObjectId': candidate['id'], **item} for (candidate, _), item in zip(jobs, fetched)]}, indent=2)+'\n')
    print(json.dumps({'objects': len(candidates), 'files': len(fetched), 'bytes': sum(item['bytes'] for item in fetched)}))
    raise SystemExit(0)
registry = read(P / 'public/data/entity-registry.json')
entities = {entity['entityId']: entity for entity in registry['entities']}
domain_path = plan.get('domainsFile', 'public/data/building-footprints.json')
domain_source = read(P / domain_path)
if 'footprints' in domain_source:
    domains = {f['id']: unary_union([Polygon(part['rings'][0], part['rings'][1:]) for part in f['parts']]) for f in domain_source['footprints']}
else:
    raw_domains = domain_source['domains']
    domains = {eid.removeprefix('building:').removeprefix('catalog:'): unary_union([
        Polygon(part['rings'][0], part['rings'][1:]) for domain in raw_domains if domain['entityId'] == eid for part in domain['parts']])
        for eid in {domain['entityId'] for domain in raw_domains}}
bundles, reports = [], []
for candidate in candidates:
    oid = candidate['id']
    cid, name = TARGETS[oid]
    canonical_id = plan['targets'][oid]['canonicalId'] if plan else registry['legacyMap'][cid]
    assert canonical_id.startswith('building:') and canonical_id in entities
    name = entities[canonical_id]['name']
    directory = D / 'objects' / oid
    source_files = [item for (c, _), item in zip(jobs, fetched) if c['id'] == oid]
    gltf = read(directory / (oid + '.gltf'))
    transform = np.eye(4)
    transform[:3, 3] = [-844800, 0, 820500]
    triangles, _ = geometry(directory / (oid + '.gltf'), transform)
    assert np.isfinite(triangles).all()
    normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    projected_triangles = triangles[abs(normal[:, 1]) > 1e-9][:, :, [0, 2]]
    projection = unary_union([Polygon(tri) for tri in projected_triangles])
    domain = domains[cid]
    matches = sorted([{'id': identity, 'intersectionM2': projection.intersection(other).area,
                       'domainCoveredRatio': projection.intersection(other).area / other.area}
                      for identity, other in domains.items() if projection.intersection(other).area > 1],
                     key=lambda match: -match['intersectionM2'])
    assert matches[0]['id'] == cid, (oid, matches)
    intersection = projection.intersection(domain).area
    assert intersection / domain.area > .85, (cid, intersection / domain.area)
    dimensions = []
    textures = []
    for image in gltf.get('images', []):
        with Image.open(directory / image['uri']) as decoded:
            size = list(decoded.size)
            decoded.verify()
        dimensions.append(size)
        textures.append({'uri': image['uri'], 'dimensions_pixels': size})
    for mesh in gltf['meshes']:
        for primitive in mesh['primitives']:
            assert 'TEXCOORD_0' in primitive['attributes']
            assert gltf['materials'][primitive['material']]['pbrMetallicRoughness'].get('baseColorTexture') is not None
    lo, hi = triangles.min((0, 1)), triangles.max((0, 1))
    x0, z0 = np.floor(lo[[0, 2]]) - 1
    x1, z1 = np.ceil(hi[[0, 2]]) + 1
    width, height = int((x1-x0)*2), int((z1-z0)*2)
    mask_array = rasterize(((mapping(Polygon(tri)), 255) for tri in projected_triangles),
                           out_shape=(height, width), transform=Affine(.5, 0, x0, 0, .5, z0),
                           dtype='uint8', all_touched=False)
    (D / 'masks').mkdir(exist_ok=True)
    Image.fromarray(mask_array).save(D / 'masks' / (cid + '.exact.png'))
    Image.fromarray(mask_array).filter(ImageFilter.MaxFilter(3)).save(D / 'masks' / (cid + '.png'))
    source_manifest = {'id': oid, 'level_code': candidate['sourceLevelCode'],
        'source_archive_uri': candidate['url'], 'source_sheet': candidate['sheet'],
        'source_revision_date': '2025-03-27', 'capture_date': None, 'files': source_files,
        'file_bytes': sum(item['bytes'] for item in source_files), 'original_nodes': gltf['nodes'],
        'geometry': {'textures': textures, 'triangles': len(triangles)},
        'bytePolicy': 'Original ZIP payloads unchanged; original CRC32 verified before writing.'}
    (directory / 'source-manifest.json').write_text(json.dumps(source_manifest, indent=2) + '\n')
    obj = {'id': oid, 'url': f'objects/{oid}/{oid}.gltf', 'offset': [-844800, 0, 820500],
        'bounds': {'min': lo.tolist(), 'max': hi.tolist()}, 'triangles': len(triangles),
        'textureDecodedBytes': sum(w*h*4 for w, h in dimensions),
        'textureMipBytes': sum(mip_bytes(w, h) for w, h in dimensions),
        'textureDimensions': dimensions, 'textureMaxDimension': max(max(d) for d in dimensions),
        'textureFiles': [{'url': f'objects/{oid}/{image["uri"]}', 'width': dimensions[i][0],
            'height': dimensions[i][1], 'decodedBytes': dimensions[i][0]*dimensions[i][1]*4}
            for i, image in enumerate(gltf['images'])],
        'assetBytes': source_manifest['file_bytes'], 'sourceManifest': f'objects/{oid}/source-manifest.json',
        'sourceUrl': candidate['url'], 'sourceLevelCode': candidate['sourceLevelCode'],
        'gltfSha256': sha((directory / (oid+'.gltf')).read_bytes())}
    mask = {'url': f'masks/{cid}.png', 'exactUrl': f'masks/{cid}.exact.png',
        'boundsXZ': {'min': [float(x0), float(z0)], 'max': [float(x1), float(z1)]},
        'width': width, 'height': height, 'metersPerPixel': .5, 'channel': 'red',
        'occupiedValue': 255, 'emptyValue': 0, 'rowDirection': 'z-increasing', 'textureFlipY': False,
        'heightMin': float(lo[1]-.5), 'heightMax': float(hi[1]+5), 'dilationMeters': .5,
        'source': 'Actual complete original object triangle projection, with separately retained exact mask; one source-pixel rendering guard.',
        'sha256': sha((D/'masks'/(cid+'.png')).read_bytes())}
    match = {'officialSource': domain_path, 'officialEntityId': canonical_id,
        'sourceProjectionAreaM2': projection.area, 'officialDomainAreaM2': domain.area,
        'intersectionM2': intersection, 'officialDrawingCoveredRatio': intersection / domain.area,
        'sourceProjectionInsideOfficialRatio': intersection / projection.area,
        'otherOfficialDomainIntersections': matches,
        'identityMethod': 'Unique dominant overlap of actual transformed source triangles with existing officially located building domain; never accessor bbox or source-family digits.'}
    if 'domains' in domain_source:
        match['officialNamedDomains'] = [{'sourceBuildingId': domain.get('sourceBuildingId'),
            'annotation': domain.get('annotation'), 'baseLevel': domain.get('minY'), 'roofLevel': domain.get('maxY')}
            for domain in domain_source['domains'] if domain['entityId'] == canonical_id]
    bundle = {'id': cid, 'buildingId': canonical_id.removeprefix('building:'), 'buildingName': name,
        'catalogIds': [cid] if registry.get('legacyMap', {}).get(cid) == canonical_id else [],
        'objects': [obj], 'bounds': obj['bounds'], 'center': ((lo+hi)/2).tolist(), 'mask': mask,
        'textureDecodedBytes': obj['textureDecodedBytes'], 'textureMipBytes': obj['textureMipBytes'],
        'triangles': len(triangles), 'assetBytes': obj['assetBytes'], 'matchEvidence': match,
        'sourceDates': {'tileRevision': '2025-03-27', 'captureDate': None, 'checkedAt': '2026-09-06'},
        'replacement': {'atomic': True, 'keepPreviousUntilAllObjectsAndTexturesReady': True,
            'fallback': 'Entire original source object; never partial textures or triangles.'}}
    bundles.append(bundle)
    reports.append({'canonicalId': canonical_id, 'name': name, 'sourceObjectId': oid,
        'originalFiles': len(source_files), 'originalEncodedBytes': obj['assetBytes'],
        'triangles': len(triangles), 'textureDimensions': dimensions,
        'textureMipMiB': obj['textureMipBytes']/2**20, 'actualBounds': obj['bounds'],
        'actualProjection': match, 'sourceProjectionGeometry': mapping(projection),
        'browserAppearanceAcceptance': 'pending: source projection and byte integrity do not establish facade/current-era quality'})
    print(cid, oid, len(triangles), 'triangles', round(obj['textureMipBytes']/2**20, 3), 'MiB', round(intersection/domain.area, 6), flush=True)
(D / 'manifest.json').write_text(json.dumps({'version': 1, 'bundles': bundles}, indent=2)+'\n')
REPORT.write_text(json.dumps({'status': 'staged-not-live', 'stagingDirectory': str(D), 'groups': reports,
    'captureDate': None, 'sourceRevisionIsNotCaptureDate': True,
    'limits': 'Complete available source objects, original source heights/UV/textures/nodes. No inferred missing annex or claimed2026 appearance; outside actual projection keeps existing baseline.'}, indent=2)+'\n')
