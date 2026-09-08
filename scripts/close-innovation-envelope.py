#!/usr/bin/env python3
"""Isolated closure of the existing Innovation floor-to-floor envelope steps.

Uses the actual original GLB wall boundary, not a new perimeter approximation.
Only adjacent-outline differences receive horizontal faces. Original facades,
UVs, images, floor elevations and top roof remain intact. Stored partial indoor
floor meshes remain evidence nodes, outside the default exterior scene.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Polygon, Point, mapping
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shadow_io', ROOT/'scripts/bake-structure-shadows.py')
io = importlib.util.module_from_spec(spec); spec.loader.exec_module(io)


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def components(shape):
    if shape.is_empty:
        return []
    return [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)


def active_triangles(g, binary):
    triangles = []; owners = []
    for ni, mi, world, _ in io.instances(g):
        for pi, p in enumerate(g['meshes'][mi]['primitives']):
            a = io.access(g, binary, p['attributes']['POSITION'])
            ix = io.access(g, binary, p['indices']).ravel().astype(int) if 'indices' in p else np.arange(len(a))
            t = io.transform(a, world)[ix].reshape(-1, 3, 3)
            triangles.extend(t); owners.extend([(ni, pi)]*len(t))
    return np.asarray(triangles), owners


def ray(tris, owners, origin, direction, maximum):
    direction = np.asarray(direction, float); direction /= np.linalg.norm(direction)
    e1 = tris[:, 1]-tris[:, 0]; e2 = tris[:, 2]-tris[:, 0]; p = np.cross(direction, e2)
    det = (e1*p).sum(1); valid = abs(det) > 1e-10; inv = np.divide(1, det, where=valid, out=np.zeros_like(det))
    rel = np.asarray(origin)-tris[:, 0]; u = (rel*p).sum(1)*inv; q = np.cross(rel, e1)
    v = (q*direction).sum(1)*inv; t = (q*e2).sum(1)*inv
    valid &= (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8) & (t > 1e-6) & (t < maximum)
    ids = np.flatnonzero(valid)
    if not len(ids):
        return None
    i = int(ids[np.argmin(t[ids])])
    return {'distance': float(t[i]), 'nodeIndex': owners[i][0], 'primitive': owners[i][1],
            'triangle': i, 'point': (np.asarray(origin)+direction*t[i]).tolist()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=Path('/tmp/hkust-innovation-photo'))
    p.add_argument('--output', type=Path, default=Path('/tmp/hkust-innovation-photo-closed'))
    args = p.parse_args(); out = args.output.resolve(); source_dir = args.input.resolve()
    if out == source_dir or out.is_relative_to(ROOT/'public'):
        raise ValueError('Isolated output required')
    out.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((source_dir/'manifest.json').read_text())
    source = source_dir/source_manifest['asset']['url']; g, binary, digest = io.read_glb(source)
    if digest != source_manifest['asset']['sha256']:
        raise ValueError('Candidate manifest SHA mismatch')
    original = copy.deepcopy(g); original_binary = binary
    perimeter_file = ROOT/'public/models/current-forms/innovation/source/untextured-v1.glb'
    pg, pb, perimeter_sha = io.read_glb(perimeter_file)
    if perimeter_sha != source_manifest['sourceGeometrySHA256']:
        raise ValueError('Photo source geometry identity mismatch')
    envelopes = []; floor_parts = {}; source_nodes = []
    for node_i, node in enumerate(pg['nodes']):
        if 'mesh' not in node:
            continue
        alltris = np.concatenate([io.access(pg, pb, p['attributes']['POSITION']).reshape(-1, 3, 3) for p in pg['meshes'][node['mesh']]['primitives']])
        extra = node.get('extras', {})
        if extra.get('representationRole') == 'exact_source_floor_parts':
            floor_parts[float(extra['sourceZValues'][0])] = unary_union([Polygon(t[:, [0, 2]]) for t in alltris])
        if not node.get('name', '').startswith('approx-band-lower-'):
            continue
        y = float(extra['sourceBottomY']); stored_y = float(np.float32(y)); lines = []
        for tri in alltris:
            for a, b in zip(tri, np.roll(tri, -1, axis=0)):
                if abs(a[1]-stored_y) < 1e-7 and abs(b[1]-stored_y) < 1e-7 and np.linalg.norm(a-b) > 1e-8:
                    lines.append(LineString([a[[0, 2]], b[[0, 2]]]))
        shape = unary_union(list(polygonize(unary_union(lines))))
        if shape.is_empty or not shape.is_valid:
            raise ValueError('Source wall boundary is not closed')
        envelopes.append({'y': y, 'shape': shape, 'sourceNode': node['name'], 'floorId': extra['sourceFloorId']})
    envelopes.sort(key=lambda x: x['y'])
    if len(envelopes) != 8 or len(floor_parts) != 8:
        raise ValueError('Expected the eight verified source layers')
    roots = g['scenes'][g.get('scene', 0)]['nodes']
    if len(roots) != 1 or g['nodes'][roots[0]]['name'] != 'campus-19':
        raise ValueError('Expected unified campus-19 exterior root')
    root = g['nodes'][roots[0]]; identity = {k: root['extras'][k] for k in ('entityId', 'buildingId')}
    for ni in list(root['children']):
        if g['nodes'][ni].get('extras', {}).get('representationRole') == 'exact_source_floor_parts':
            root['children'].remove(ni); source_nodes.append(ni)
    if len(source_nodes) != 8:
        raise ValueError('Expected exactly eight source-evidence floor nodes')
    buffer = bytearray(binary); added_nodes = []; interfaces = []; witnesses = []; slivers = []
    def accessor(array):
        array = np.ascontiguousarray(array, '<f4'); buffer.extend(b'\0'*(-len(buffer)%4)); vi = len(g['bufferViews'])
        g['bufferViews'].append({'buffer': 0, 'byteOffset': len(buffer), 'byteLength': array.nbytes, 'target': 34962}); buffer.extend(array.tobytes())
        g['accessors'].append({'bufferView': vi, 'componentType': 5126, 'count': len(array), 'type': 'VEC3', 'min': array.min(0).tolist(), 'max': array.max(0).tolist()})
        return len(g['accessors'])-1
    for lower, upper in zip(envelopes, envelopes[1:]):
        y = upper['y']; stored_y = float(np.float32(y))
        for label, sign, shape in [('terrace', 1, lower['shape'].difference(upper['shape'])),
                                   ('soffit', -1, upper['shape'].difference(lower['shape']))]:
            triangles = []; missing = shape.difference(floor_parts[y]); missing_sample = []
            for part in components(shape):
                if part.geom_type != 'Polygon':
                    raise ValueError('Unexpected non-polygon difference')
                for t in constrained_delaunay_triangles(part).geoms:
                    if not part.covers(t):
                        raise ValueError('Triangulation left source difference domain')
                    xz = np.asarray(t.exterior.coords)[:3]; tri = np.column_stack((xz[:, 0], np.full(3, stored_y), xz[:, 1])).astype('<f4')
                    n = np.cross(tri[1]-tri[0], tri[2]-tri[0])
                    if abs(n[1]) <= 1e-12:
                        slivers.append({'y': y, 'role': label, 'areaM2': t.area, 'polygon': mapping(t), 'reason': 'Unrepresentable zero-area float32 triangle; recorded, not silently discarded'})
                        continue
                    if n[1]*sign < 0:
                        tri = tri[[0, 2, 1]]
                    triangles.append(tri)
            if not triangles:
                continue
            tris = np.asarray(triangles); projected = unary_union([Polygon(t[:, [0, 2]]) for t in tris])
            # Interior witness for each sizeable actually missing component, avoiding edge ambiguity.
            for part in sorted(components(missing), key=lambda x: x.area, reverse=True):
                if part.area < .01:
                    continue
                point = part.representative_point(); clearance = point.distance(part.boundary)
                if clearance < .0001:
                    continue
                px, pz = point.x, point.y
                # Very short finite ray proves this interface, not some other floor several metres away.
                origin = [px, stored_y+sign*.08, pz]
                witnesses.append({'interfaceY': y, 'role': label, 'origin': origin, 'direction': [0, -sign, 0], 'maximum': .16})
                # Oblique ray still crosses inside the component, with offset bounded by actual clearance.
                horizontal = min(.04, clearance*.25)
                witnesses.append({'interfaceY': y, 'role': label, 'origin': [px+horizontal, stored_y+sign*.08, pz],
                                  'direction': [-horizontal, -sign*.08, 0], 'maximum': .18})
                missing_sample.append([px, stored_y, pz])
                if len(missing_sample) == 3:
                    break
            ni = len(g['nodes']); mi = len(g['meshes']); name = f'layer-transition-{y:.2f}-{label}'
            extra = {**identity, 'representationRole': 'approximate_layer_transition', 'surfaceRole': label,
                     'sourceLowerFloorId': lower['floorId'], 'sourceUpperFloorId': upper['floorId'], 'sourceY': y,
                     'derivation': 'Exact difference of existing source GLB exterior wall outlines; not a newly surveyed slab',
                     'noMeasuredSurfaceMaterial': True}
            pos = tris.reshape(-1, 3); normal = np.tile([0, sign, 0], (len(pos), 1))
            material = 4 if sign == 1 else 0  # Explicit existing schematic roof/pale-band materials, not photo claims.
            g['meshes'].append({'name': name, 'primitives': [{'attributes': {'POSITION': accessor(pos), 'NORMAL': accessor(normal)}, 'material': material, 'mode': 4}]})
            g['nodes'].append({'name': name, 'mesh': mi, 'extras': extra}); root['children'].append(ni); added_nodes.append(ni)
            interfaces.append({'y': y, 'role': label, 'lowerAreaM2': lower['shape'].area, 'upperAreaM2': upper['shape'].area,
                               'differenceAreaM2': shape.area, 'oldMissingHorizontalAreaM2': missing.area,
                               'storedNewTriangleAreaM2': float(abs(np.cross(tris[:, 1]-tris[:, 0], tris[:, 2]-tris[:, 0])[:, 1]).sum()/2),
                               'storedProjectionSymmetricDifferenceM2': shape.symmetric_difference(projected).area,
                               'triangles': len(tris), 'sourceDifference': mapping(shape), 'witnesses': missing_sample})
    g.setdefault('extras', {})['layerTransitionClosure'] = {'sourcePhotoCandidateSHA256': digest, 'sourcePerimeterGLBSHA256': perimeter_sha,
        'sourceFloorEvidenceNodes': source_nodes, 'defaultExteriorExcludesInteriorSourceFloorMeshes': True,
        'derivation': 'Only adjacent lower-minus-upper terraces and upper-minus-lower soffits at existing source floor Y; no full floor plates'}
    g['buffers'][0]['byteLength'] = len(buffer); j = json.dumps(g, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode(); j += b' '*(-len(j)%4); buffer.extend(b'\0'*(-len(buffer)%4))
    raw = struct.pack('<4sII', b'glTF', 2, 28+len(j)+len(buffer))+struct.pack('<I4s', len(j), b'JSON')+j+struct.pack('<I4s', len(buffer), b'BIN\0')+buffer
    output = out/'innovation-photo-closed.glb'; pending = out/'innovation-photo-closed.pending.glb'; pending.write_bytes(raw)
    # Validate the serialized output, not the intermediate geometry.
    encoded, eb, output_sha = io.read_glb(pending); before_tris, before_owners = active_triangles(original, original_binary)
    after_tris, after_owners = active_triangles(encoded, eb)
    assert io.image_hashes(encoded, eb) == io.image_hashes(original, original_binary)
    assert encoded['materials'] == original['materials'] and encoded.get('textures') == original.get('textures')
    for i in range(len(original['meshes'])):
        assert encoded['meshes'][i] == original['meshes'][i]
    assert all(encoded['nodes'][i] == original['nodes'][i] for i in source_nodes)
    for w in witnesses:
        w['before'] = ray(before_tris, before_owners, w['origin'], w['direction'], w['maximum'])
        w['after'] = ray(after_tris, after_owners, w['origin'], w['direction'], w['maximum'])
        if w['before'] is not None or w['after'] is None or w['after']['nodeIndex'] not in added_nodes:
            raise AssertionError(('Finite interface ray did not establish closure', w))
    # Horizontal probes through every exterior-ring segment at a true mid-storey Y.
    horizontal = []
    for envelope in envelopes:
        height = envelope['y']+2.5
        for part in components(envelope['shape']):
            coords = list(part.exterior.coords)
            for a, b in zip(coords, coords[1:]):
                a = np.asarray(a); b = np.asarray(b); edge = b-a; length = np.linalg.norm(edge)
                if length < .1:
                    continue
                mid = (a+b)/2; direction = np.array([-edge[1], 0, edge[0]])/length
                origin = np.array([mid[0], height, mid[1]])-direction*.05
                old = ray(before_tris, before_owners, origin, direction, .1); new = ray(after_tris, after_owners, origin, direction, .1)
                if old is None or new is None or abs(old['distance']-new['distance']) > 1e-9 or old['nodeIndex'] != new['nodeIndex']:
                    raise AssertionError('Horizontal source facade changed')
                horizontal.append({'floorY': envelope['y'], 'origin': origin.tolist(), 'direction': direction.tolist(), 'distance': new['distance'], 'nodeIndex': new['nodeIndex']})
    manifest = {'version': 1, 'asset': {'url': output.name, 'sha256': output_sha, 'bytes': len(raw)}, 'members': source_manifest['members'],
                'sourceCandidateManifest': str(source_dir/'manifest.json'), 'sourceCandidateSHA256': digest,
                'closure': {'report': 'closure-validation.json', 'sourceFloorNodesRetainedOutsideActiveScene': source_nodes,
                            'sourceFloorCountOpenedByWorldInterior': 8, 'newTransitionNodes': len(added_nodes), 'activeTriangles': len(after_tris)},
                'limitations': ['Existing exterior footprints, all-side photo reuse and grey top roof remain approximate; no as-built claim.',
                    'Only layer-step interfaces closed. This is not a claim of global watertightness at the ground/bottom or measured structural slabs.',
                    'Source floor evidence meshes stay outside default scene; production public interior JSON untouched.']}
    report = {'status': 'PASS isolated adjacent-outline closure', 'sourceSHA256': digest, 'sourcePerimeterSHA256': perimeter_sha,
              'outputSHA256': output_sha, 'activeTrianglesBefore': len(before_tris), 'activeTrianglesAfter': len(after_tris),
              'photoPrimitivesImagesMaterialsUnchanged': True, 'oldMeshesAccessorsUnchanged': True,
              'sourceFloorNodesRetainedOutsideDefaultScene': source_nodes, 'interfaces': interfaces,
              'totalAddedDifferenceAreaM2': sum(x['differenceAreaM2'] for x in interfaces),
              'totalPreviouslyMissingHorizontalAreaM2': sum(x['oldMissingHorizontalAreaM2'] for x in interfaces),
              'finiteMissingInterfaceRaysBeforeMissAfterNewCap': witnesses, 'horizontalUnchangedFacadeProbes': horizontal,
              'unrepresentableFloat32Slivers': slivers, 'limitation': 'Horizontal rays confirm unchanged walls; only crossing vertical/oblique rays can verify an added horizontal face. No browser acceptance.'}
    report['publicInteriorSourceFiles'] = [{'asset': original['nodes'][ni]['extras']['sourceAsset'],
        'sha256': hashlib.sha256((ROOT/'public'/original['nodes'][ni]['extras']['sourceAsset'].lstrip('/')).read_bytes()).hexdigest()}
        for ni in source_nodes]
    pending.replace(output)
    write(out/'manifest.json', manifest); write(out/'closure-validation.json', report)
    write(out/'envelopes.geojson', {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'y': x['y'], 'floorId': x['floorId']}, 'geometry': mapping(x['shape'])} for x in envelopes]})
    print(json.dumps({'output': str(output), 'sha256': output_sha, 'triangles': len(after_tris), 'interfaceRays': len(witnesses),
                      'horizontalProbes': len(horizontal), 'addedDifferenceAreaM2': report['totalAddedDifferenceAreaM2'],
                      'previouslyMissingHorizontalAreaM2': report['totalPreviouslyMissingHorizontalAreaM2']}, indent=2))


if __name__ == '__main__':
    main()
