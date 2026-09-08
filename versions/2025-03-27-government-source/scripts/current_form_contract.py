"""Shared registry/GLB contract for local complete-building representation sets.

This checks identity, original public sources and packed geometry. It cannot
establish that an approximate facade is an as-built exterior.
"""
import functools
import hashlib
import json
import math
import struct
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def image_dimensions(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return list(struct.unpack_from('>II', data, 16))
    require(data[:2] == b'\xff\xd8', 'unsupported original image encoding')
    i = 2
    while i + 4 <= len(data):
        if data[i] != 255:
            i += 1
            continue
        while data[i] == 255:
            i += 1
        marker = data[i]
        i += 1
        if marker in (0xd8, 0xd9, 1) or 0xd0 <= marker <= 0xd7:
            continue
        length = struct.unpack_from('>H', data, i)[0]
        if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
            height, width = struct.unpack_from('>HH', data, i + 3)
            return [width, height]
        require(length >= 2, 'invalid JPEG segment')
        i += length
    raise ValueError('image dimensions unavailable')


@functools.lru_cache(maxsize=8)
def inspect_asset(path, expected_sha, expected_bytes):
    data = Path(path).read_bytes()
    require(len(data) == expected_bytes and sha(data) == expected_sha, 'model SHA or length mismatch')
    require(struct.unpack_from('<4sII', data) == (b'glTF', 2, len(data)), 'invalid GLB header')
    length, kind = struct.unpack_from('<I4s', data, 12)
    require(kind == b'JSON', 'missing GLB JSON')
    g = json.loads(data[20:20 + length])
    size, kind = struct.unpack_from('<I4s', data, 20 + length)
    require(kind == b'BIN\0' and 28 + length + size == len(data), 'invalid self-contained GLB binary')
    binary = data[28 + length:]
    require(not any('uri' in ref for key in ('images', 'buffers') for ref in g.get(key, [])), 'external GLB dependency')

    def attribute(index):
        a = g['accessors'][index]
        v = g['bufferViews'][a['bufferView']]
        width = {'VEC3': 3, 'VEC2': 2, 'VEC4': 4, 'SCALAR': 1}[a['type']]
        fmt = {5126: 'f', 5125: 'I', 5123: 'H', 5121: 'B'}[a['componentType']]
        unpack = struct.Struct('<' + fmt * width)
        offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = v.get('byteStride', unpack.size)
        require(offset + max(0, a['count'] - 1) * stride + unpack.size <= v.get('byteOffset', 0) + v['byteLength'] <= len(binary), 'accessor exceeds buffer')
        return [unpack.unpack_from(binary, offset + i * stride) for i in range(a['count'])]

    roots = {}
    for root_index in g['scenes'][g.get('scene', 0)]['nodes']:
        root = g['nodes'][root_index]
        require(root['name'] not in roots, 'duplicate building root')
        points, triangles, meshes, seen = [], 0, 0, set()
        stack = [root_index]
        while stack:
            ni = stack.pop()
            require(ni not in seen, 'reused or cyclic node in physical root')
            seen.add(ni)
            node = g['nodes'][ni]
            require(not any(k in node for k in ('matrix', 'translation', 'rotation', 'scale')), 'unexpected extra transform on local geometry')
            for key in ('entityId', 'buildingId'):
                require(node.get('extras', {}).get(key, root['extras'][key]) == root['extras'][key], 'conflicting descendant identity')
            require(node.get('extras', {}).get('representationRole') != 'exact_source_floor_parts', 'public indoor floor masquerades as exterior closure')
            stack.extend(node.get('children', []))
            if 'mesh' not in node:
                continue
            meshes += 1
            for p in g['meshes'][node['mesh']]['primitives']:
                v = attribute(p['attributes']['POSITION'])
                require(all(math.isfinite(x) for pt in v for x in pt), 'nonfinite packed position')
                t = [v[i[0]] for i in attribute(p['indices'])] if 'indices' in p else v
                require(len(t) % 3 == 0 and p.get('mode', 4) == 4, 'nontriangle primitive')
                for a, b, c in zip(t[::3], t[1::3], t[2::3]):
                    ab = [b[i] - a[i] for i in range(3)]
                    ac = [c[i] - a[i] for i in range(3)]
                    cross = [ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0]]
                    require(sum(x*x for x in cross) > 1e-16, 'degenerate packed triangle')
                mat = g['materials'][p['material']]
                if 'baseColorTexture' in mat.get('pbrMetallicRoughness', {}):
                    uv = attribute(p['attributes']['TEXCOORD_0'])
                    require(len(uv) == len(v) and all(math.isfinite(x) for pt in uv for x in pt), 'invalid photographic UV')
                if 'COLOR_0' in p['attributes']:
                    color = attribute(p['attributes']['COLOR_0'])
                    require(len(color) == len(v) and all(math.isfinite(x) and 0 <= x <= 1 for pt in color for x in pt), 'invalid baked linear colour')
                triangles += len(t) // 3
                points.extend(v)
        require(points, 'empty physical root')
        roots[root['name']] = {'extras': root['extras'], 'triangles': triangles, 'meshes': meshes,
                              'bounds': {key: [fn(p[i] for p in points) for i in range(3)] for key, fn in [('min', min), ('max', max)]}}
    images = []
    for image in g.get('images', []):
        v = g['bufferViews'][image['bufferView']]
        raw = binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]
        images.append({'sha256': sha(raw), 'dimensions': image_dimensions(raw), 'bytes': len(raw)})
    return roots, images


def validate_current_form_set(project, entity, representation):
    public = Path(project) / 'public'
    manifest_url = representation['sourceManifest']
    manifest_path = public / manifest_url.lstrip('/')
    m = json.loads(manifest_path.read_text())
    require(m.get('version') == 1 and m.get('members'), 'expected complete-set version 1')
    for key in ('entityId', 'buildingId', 'nodeName'):
        require(len({v[key] for v in m['members']}) == len(m['members']), 'duplicate member ' + key)
    member = next(v for v in m['members'] if v['entityId'] == entity['entityId'])
    require(entity['type'] == 'building' and entity['externalIds']['pathAdvisorBuildingId'] == member['buildingId'] == representation['featureId'], 'physical member binding')
    require(representation['nodeName'] == member['nodeName'] and representation['bounds'] == member['bounds'], 'registry member/root bounds binding')
    require(representation['asset'] == str(Path(manifest_url).parent / m['asset']['url']), 'registry still references a different model')
    require(m['accuracy']['measuredExterior'] is False and m['accuracy']['measuredRoofHeight'] is False, 'approximate exterior promoted to survey')
    floors = json.loads((public / 'interiors/manifest.json').read_text())['floors']
    floors = [f for f in floors if f['buildingId'] == member['buildingId']]
    expected_z = sorted({z for f in floors for z in f['sourceZValues']})
    require(representation['sourceZValues'] == expected_z, 'registry public floor Z changed')
    records = member['sourceFloors']
    require({f['id'] for f in records} == {f['id'] for f in floors} and len(records) == len(floors), 'public source floor coverage')
    for f in floors:
        source = next(x for x in records if x['id'] == f['id'])
        require(source['asset'] == '/interiors/' + f['url'] and source['sourceZValues'] == f['sourceZValues'], 'source floor reference/Z changed')
        require(sha((public / source['asset'].lstrip('/')).read_bytes()) == source['sha256'], 'public source floor SHA changed')
    for source in m['sources']['savedGeometry']:
        require(sha((public / source['asset'].lstrip('/')).read_bytes()) == source['sha256'], 'geometric source SHA changed')
    roots, images = inspect_asset(str(manifest_path.parent / m['asset']['url']), m['asset']['sha256'], m['asset']['bytes'])
    require(set(roots) == {v['nodeName'] for v in m['members']}, 'manifest/default-scene root coverage')
    for v in m['members']:
        actual = roots[v['nodeName']]
        require(all(actual['extras'][k] == v[k] for k in ('entityId', 'buildingId')), 'GLB root identity differs')
        require(all(abs(actual['bounds'][k][i] - v['bounds'][k][i]) < .001 for k in ('min', 'max') for i in range(3)), 'actual root bounds differ')
    texture_records = m['appearanceTextures']
    require(len(images) == len(texture_records) == m.get('appearance', {}).get('embeddedTextures'), 'appearance texture graph incomplete')
    for image, record in zip(images, texture_records):
        raw = (manifest_path.parent / record['asset']).read_bytes()
        require(all(image[k] == record[k] for k in ('sha256', 'dimensions', 'bytes')), 'embedded photographic metadata mismatch')
        require(sha(raw) == image['sha256'], 'embedded image differs from saved photographic pixels')
    actual = roots[member['nodeName']]
    return {'status': 'pass', 'entityId': entity['entityId'], 'asset': representation['asset'],
            'sha256': m['asset']['sha256'], 'nodeName': member['nodeName'], **actual,
            'sourceFloorLayers': len(floors), 'embeddedImages': images, 'visualAcceptance': False}
