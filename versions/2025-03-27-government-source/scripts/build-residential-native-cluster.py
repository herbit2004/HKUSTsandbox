#!/usr/bin/env python3
"""Original error-zero source leaves for six complete named geographic domains.

The 10 m guard only selects complete original files; it is never the mask or new
geometry. Known missing source siblings stay on baseline. Existing verified
floating-fragment corrections are reused without changing their evidence.
"""
import argparse, concurrent.futures, hashlib, io, json, shutil, struct, subprocess, zlib
from pathlib import Path
import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from hkust_source_geometry import geometry

parser = argparse.ArgumentParser()
parser.add_argument('--plan-only', action='store_true')
args = parser.parse_args()
P = Path(__file__).resolve().parents[1]
O = P/'docs/source-evidence-v4/building-quality'
D = P/'public/models/hires/partial-residential-ias'
C = Path('/tmp/hkust-v6-building-native/source')
for folder in [O, D, C]: folder.mkdir(parents=True, exist_ok=True)
read = lambda p: json.loads(p.read_text())
audit = read(P/'public/models/hires/partial-ug10/branch-audit.json')
old = read(P/'public/models/hires/partial-ug10/manifest.json')['patches'][0]
existing = {t['id']: t for t in old['levels']['high']['tiles']}
named = {'ug-hall-10', 'ug-hall-11', 'ug-hall-12', 'ug-hall-13', 'campus-28'}
domains = {f['id']: unary_union([Polygon(p['rings'][0], p['rings'][1:]) for p in f['parts']])
    for f in read(P/'public/data/building-footprints.json')['footprints'] if f['id'] in named}
domains['campus-35'] = unary_union([Polygon(p['rings'][0], p['rings'][1:])
    for d in read(P/'public/data/picking/building-domains.json')['domains']
    if d['entityId'] == 'building:catalog:campus-35' for p in d['parts']])
acquisition_domain = unary_union(list(domains.values())).buffer(10)
items = []
for tree in audit['subtrees']:
    folder = P/'source-geodata/mesh'/tree['sheet']
    entries = read(folder/'source-zip-index.json')
    url = read(folder/'subset-manifest.json')['source']
    for branch in tree['branches']:
        for a in branch['levels']['fine']['assets']:
            b = a['knownBounds']
            selected = box(b['min'][0], b['min'][2], b['max'][0], b['max'][2]).intersects(acquisition_domain)
            if not selected and a['id'] not in existing: continue
            assert a['original_geometric_error'] == 0 and a['source_name'] in entries
            items.append((tree, a, entries[a['source_name']], url))
plan = {'id': 'residential-ias-terminal-cluster', 'canonicalIds': [e['entityId']
    for e in read(P/'public/data/entity-registry.json')['entities'] if e['type'] == 'building'
    and set(e.get('externalIds', {}).get('legacyCatalogIds', [])) & set(domains)],
    'domainLegacyIds': sorted(domains), 'selectionGuardMeters': 10,
    'selectionMeaning': 'Original leaf bounding boxes intersect the full named official domains plus a 10m source-acquisition guard; retain all previously delivered37 leaves as well. No mesh clipping, footprint extrusion, image resampling or invented geometry.',
    'selectedLeafCount': len(items), 'newLeafCount': sum(a['id'] not in existing for _, a, _, _ in items),
    'sourceEncodedBytes': sum(e['size'] for _, _, e, _ in items),
    'newSourceEncodedBytes': sum(e['size'] for _, a, e, _ in items if a['id'] not in existing),
    'sourceZipCompressedBytes': sum(e['compressed'] for _, _, e, _ in items),
    'missingSiblingRequests': 0, 'maximumOriginalError': 0,
    'knownMissingSiblings': [m for t in audit['subtrees'] for m in t['missingDirectSiblings']],
    'leaves': [{'id': a['id'], 'sourceName': a['source_name'], 'bytes': e['size'],
        'compressed': e['compressed'], 'existing': a['id'] in existing, 'knownBounds': a['knownBounds']}
        for _, a, e, _ in items]}
(O/'residential-native-source-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({k: v for k, v in plan.items() if k not in ['leaves', 'knownMissingSiblings']}, ensure_ascii=False, indent=2), flush=True)
if args.plan_only: raise SystemExit()

def mip_bytes(w, h):
    total = 0
    while True:
        total += w*h*4
        if w == h == 1: return total
        w = max(1, w//2); h = max(1, h//2)

def fetch(item):
    tree, a, entry, url = item
    if a['id'] in existing:
        tile = existing[a['id']].copy()
        path = P/'public/models/hires'/tile['url']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == tile['sha256']
        tri, _ = geometry(path, np.array(tile['matrix']).reshape(4, 4, order='F'))
        return tile, tri
    cache = C/a['source_name']; cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        offset = entry['offset']; part = cache.with_suffix('.zip-part')
        result = subprocess.run(['/usr/bin/curl', '--fail', '--silent', '--show-error', '--location',
            '--range', f'{offset}-{offset+entry["compressed"]+1024}', '--max-filesize', str(entry['compressed']+2048),
            '--max-time', '45', '--retry', '2', '--retry-all-errors', '--retry-delay', '1',
            '--output', str(part), '--write-out', '%{http_code}', url], capture_output=True)
        assert result.returncode == 0, (a['source_name'], result.stderr.decode())
        assert result.stdout == b'206', (a['source_name'], result.stdout)
        raw = part.read_bytes(); header = struct.unpack_from('<4s5H3L2H', raw)
        assert header[0] == b'PK\x03\x04'
        start = 30+header[-2]+header[-1]
        payload = raw[start:start+entry['compressed']]
        if entry['compression'] == 8: payload = zlib.decompress(payload, -15)
        assert len(payload) == entry['size'] and zlib.crc32(payload) == entry['crc32']
        cache.write_bytes(payload); part.unlink()
    payload = cache.read_bytes()
    assert len(payload) == entry['size'] and zlib.crc32(payload) == entry['crc32']
    header = struct.unpack_from('<4s6I', payload); raw = payload[28+sum(header[3:]):]
    assert raw[:4] == b'glTF' and struct.unpack_from('<I', raw, 8)[0] == len(raw)
    dest = D/(Path(a['source_name']).stem+'.glb'); dest.write_bytes(raw)
    n = struct.unpack_from('<I', raw, 12)[0]; gltf = json.loads(raw[20:20+n]); binary = raw[28+n:]
    textures = []
    for image in gltf.get('images', []):
        view = gltf['bufferViews'][image['bufferView']]
        encoded = binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']]
        with Image.open(io.BytesIO(encoded)) as im: width, height = im.size; im.verify()
        textures.append({'width': width, 'height': height, 'encodedBytes': len(encoded),
            'mipBytes': mip_bytes(width, height), 'sha256': hashlib.sha256(encoded).hexdigest()})
    matrix = tree['baselineSourceMatrix']
    tri, _ = geometry(dest, np.array(matrix).reshape(4, 4, order='F'))
    lo = tri.min((0, 1)); hi = tri.max((0, 1))
    tile = {'id': a['id'], 'url': 'partial-residential-ias/'+dest.name, 'matrix': matrix,
        'bounds': {'min': lo.tolist(), 'max': hi.tolist()}, 'center': ((lo+hi)/2).tolist(),
        'triangles': len(tri), 'vertices': sum(gltf['accessors'][p['attributes']['POSITION']]['count']
            for mesh in gltf['meshes'] for p in mesh['primitives']), 'bytes': len(raw),
        'textureBytes': sum(t['width']*t['height']*4 for t in textures),
        'textureMipBytes': sum(t['mipBytes'] for t in textures),
        'textureEncodedBytes': sum(t['encodedBytes'] for t in textures), 'textures': textures,
        'textureDimensions': [[t['width'], t['height']] for t in textures],
        'sha256': hashlib.sha256(raw).hexdigest(), 'sourceB3dmSha256': hashlib.sha256(payload).hexdigest(),
        'sourceZipCRC32': entry['crc32'], 'sourceZipName': a['source_name'], 'sourceZipOffset': entry['offset'],
        'sourceUrl': url, 'sourceB3dmCachePath': str(cache), 'originalError': 0, 'terminalLeaf': True,
        'matrixSourceBaselineId': tree['baselineId']}
    print('SOURCE', a['id'], len(tri), 'tri', round(tile['textureMipBytes']/2**20, 2), 'mipMiB', flush=True)
    return tile, tri

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(fetch, items))
tiles = [t for t, _ in results]; tri = np.concatenate([t for _, t in results])
lo = tri.min((0, 1)); hi = tri.max((0, 1)); x0, z0 = np.floor(lo[[0, 2]]); x1, z1 = np.ceil(hi[[0, 2]])
resolution = .5; width = int((x1-x0)/resolution); height = int((z1-z0)/resolution)
cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]); xz = tri[abs(cross[:, 1]) > 1e-9][:, :, [0, 2]]
mask = rasterize((({'type': 'Polygon', 'coordinates': [[*t.tolist(), t[0].tolist()]]}, 255) for t in xz),
    out_shape=(height, width), transform=Affine(resolution, 0, x0, 0, resolution, z0), all_touched=False, dtype='uint8')
Image.fromarray(mask).save(D/'coverage.png')
mask_meta = {'url': 'partial-residential-ias/coverage.png', 'minX': float(x0), 'minZ': float(z0),
    'maxX': float(x1), 'maxZ': float(z1), 'width': width, 'height': height, 'pixelSizeMeters': .5,
    'coveredPixels': int((mask > 0).sum()), 'sha256': hashlib.sha256((D/'coverage.png').read_bytes()).hexdigest(),
    'source': 'Actual retained source triangle projection, 0.5m pixel-centre rasterization. No acquisition guard, AABB, hull or filled holes in the replacement mask.'}
level = {k: sum(t.get(k, 0) for t in tiles) for k in ['triangles', 'vertices', 'bytes', 'textureBytes', 'textureMipBytes', 'textureEncodedBytes']}
level.update(tiles=tiles, mask=mask_meta, sourceFrontier={'terminalLeaves': True, 'threshold': 0,
    'maximumOriginalError': 0, 'scope': 'All available terminal files selected from full six-building geographic domains; four unavailable direct siblings remain baseline outside actual projection.'})
patch = {'id': plan['id'], 'partial': True, 'sheet': '12-NW-6C and 12-NW-11A',
    'baselineIds': old['baselineIds'], 'bounds': {'min': lo.tolist(), 'max': hi.tolist()},
    'center': ((lo+hi)/2).tolist(), 'levels': {'high': level}, 'mask': mask_meta,
    'canonicalBuildingIds': plan['canonicalIds'], 'evidence': {'selection': plan['selectionMeaning'],
        'selectionGuardMeters': 10, 'domainLegacyIds': sorted(domains), 'completeParentSubtrees': False,
        'highestAvailableSelectedLeaves': True, 'knownMissingSiblings': plan['knownMissingSiblings'],
        'allPrevious37LeavesRetained': True, 'verifiedSourceCorrectionsRetained': [t['id'] for t in tiles if t.get('sourceCorrection')],
        'appearanceAcceptance': 'Pending real multi-angle source and browser comparison. Error0 does not establish completed-era appearance or absence of photogrammetric warping.'}}
(D/'manifest.json').write_text(json.dumps({'version': 1, 'patches': [patch]}, ensure_ascii=False, indent=2)+'\n')
summary = {'status': 'extracted-pending-independent-qa', 'patch': plan['id'], 'leaves': len(tiles),
    'triangles': level['triangles'], 'textureMipMiB': level['textureMipBytes']/2**20,
    'maskRgbaMiB': mask.size*4/2**20, 'sourceEncodedMiB': plan['sourceEncodedBytes']/2**20, 'mask': mask_meta}
(D/'extraction-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
