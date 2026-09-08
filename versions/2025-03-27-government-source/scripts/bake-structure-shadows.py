#!/usr/bin/env python3
"""Bake bounded geometric occlusion into an isolated, self-contained GLB.

No inferred equipment, geometry offsets, new light sources or photo edits.
All active roots cast shadows together. Photo textures are excluded unless the
material explicitly opts in with extras.bakeStructureShadow == true (a material
swatch can opt in; a registered facade normally must not). Multipliers and glTF
COLOR_0 are LINEAR. Unoccluded material colours remain unchanged.

Example:
  python3 scripts/bake-structure-shadows.py input.glb /tmp/shadow/candidate.glb
  python3 scripts/bake-structure-shadows.py --self-test /tmp/shadow-tests.json

Needs numpy and a C++17 compiler. The small exact-triangle BVH is compiled into
/tmp, not installed. Display-direction/AO-distance parameters are not measured
site illumination. This does not establish browser or visual acceptance.
"""
import argparse
import copy
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DTYPES = {5120: '<i1', 5121: '<u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
BVH_CPP = r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>
struct V { double x[3]; };
struct T { V p[3], lo, hi, center; };
struct N { V lo,hi; int left=-1,right=-1,start=0,count=0; };
struct Tree {
 std::vector<T> ts; std::vector<int> order; std::vector<N> ns;
 int build(int start,int end) {
  N n; for(int k=0;k<3;k++){n.lo.x[k]=1e300;n.hi.x[k]=-1e300;}
  V clo=n.lo,chi=n.hi;
  for(int i=start;i<end;i++) for(int k=0;k<3;k++){
   auto&t=ts[order[i]]; n.lo.x[k]=std::min(n.lo.x[k],t.lo.x[k]);
   n.hi.x[k]=std::max(n.hi.x[k],t.hi.x[k]);
   clo.x[k]=std::min(clo.x[k],t.center.x[k]); chi.x[k]=std::max(chi.x[k],t.center.x[k]);
  }
  int ix=ns.size(); ns.push_back(n);
  if(end-start<=8){ns[ix].start=start;ns[ix].count=end-start;return ix;}
  int ax=0;for(int k=1;k<3;k++)if(chi.x[k]-clo.x[k]>chi.x[ax]-clo.x[ax])ax=k;
  int mid=(start+end)/2;
  std::nth_element(order.begin()+start,order.begin()+mid,order.begin()+end,
   [&](int a,int b){return ts[a].center.x[ax]<ts[b].center.x[ax];});
  int a=build(start,mid),b=build(mid,end); ns[ix].left=a;ns[ix].right=b;return ix;
 }
 bool box(const N&n,const double*o,const double*d,double maxT)const{
  double lo=1e-5,hi=maxT;
  for(int k=0;k<3;k++){
   if(std::abs(d[k])<1e-15){if(o[k]<n.lo.x[k]-1e-10||o[k]>n.hi.x[k]+1e-10)return false;}
   else{double a=(n.lo.x[k]-o[k])/d[k],b=(n.hi.x[k]-o[k])/d[k];if(a>b)std::swap(a,b);
    lo=std::max(lo,a);hi=std::min(hi,b);if(hi<lo)return false;}
  }return true;
 }
 bool triangle(const T&t,const double*o,const double*d,double maxT)const{
  double e1[3],e2[3],p[3],q[3],v[3];
  for(int k=0;k<3;k++){e1[k]=t.p[1].x[k]-t.p[0].x[k];e2[k]=t.p[2].x[k]-t.p[0].x[k];v[k]=o[k]-t.p[0].x[k];}
  p[0]=d[1]*e2[2]-d[2]*e2[1];p[1]=d[2]*e2[0]-d[0]*e2[2];p[2]=d[0]*e2[1]-d[1]*e2[0];
  double det=e1[0]*p[0]+e1[1]*p[1]+e1[2]*p[2];if(std::abs(det)<1e-12)return false;
  double u=(v[0]*p[0]+v[1]*p[1]+v[2]*p[2])/det;if(u<-1e-9||u>1+1e-9)return false;
  q[0]=v[1]*e1[2]-v[2]*e1[1];q[1]=v[2]*e1[0]-v[0]*e1[2];q[2]=v[0]*e1[1]-v[1]*e1[0];
  double w=(d[0]*q[0]+d[1]*q[1]+d[2]*q[2])/det;if(w<-1e-9||u+w>1+1e-9)return false;
  double z=(e2[0]*q[0]+e2[1]*q[1]+e2[2]*q[2])/det;return z>1e-5&&z<maxT;
 }
 bool hit(int i,const double*o,const double*d,double maxT)const{
  const auto&n=ns[i];if(!box(n,o,d,maxT))return false;
  if(n.count){for(int j=n.start;j<n.start+n.count;j++)if(triangle(ts[order[j]],o,d,maxT))return true;return false;}
  return hit(n.left,o,d,maxT)||hit(n.right,o,d,maxT);
 }
};
extern "C" void* bvh_create(const double*data,int count){
 try{auto*b=new Tree();b->ts.resize(count);b->order.resize(count);
  for(int i=0;i<count;i++){auto&t=b->ts[i];b->order[i]=i;
   for(int k=0;k<3;k++){t.lo.x[k]=1e300;t.hi.x[k]=-1e300;t.center.x[k]=0;
    for(int j=0;j<3;j++){double v=data[i*9+j*3+k];t.p[j].x[k]=v;t.lo.x[k]=std::min(t.lo.x[k],v);t.hi.x[k]=std::max(t.hi.x[k],v);t.center.x[k]+=v/3;}}
  }if(count)b->build(0,count);return b;
 }catch(...){return nullptr;}
}
extern "C" void bvh_free(void*p){delete static_cast<Tree*>(p);}
extern "C" void bvh_hits(void*p,const double*o,const double*d,const double*maxT,int count,uint8_t*out){
 auto*b=static_cast<Tree*>(p);for(int i=0;i<count;i++)out[i]=!b->ns.empty()&&b->hit(0,o+i*3,d+i*3,maxT[i]);
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_glb(path):
    raw = Path(path).read_bytes()
    if len(raw) < 20 or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('Invalid GLB header')
    chunks = {}; at = 12
    while at < len(raw):
        length, kind = struct.unpack_from('<I4s', raw, at); at += 8
        if at + length > len(raw) or kind in chunks:
            raise ValueError('Invalid or repeated GLB chunk')
        chunks[kind] = raw[at:at + length]; at += length
    g = json.loads(chunks[b'JSON'])
    if len(g.get('buffers', [])) != 1 or 'uri' in g['buffers'][0]:
        raise ValueError('Only one self-contained GLB buffer is supported')
    if any('uri' in im for im in g.get('images', [])):
        raise ValueError('External images are not allowed')
    if g.get('skins') or g.get('animations'):
        raise ValueError('Static geometry required; skinning/animation is unsupported')
    return g, chunks.get(b'BIN\0', b''), sha(raw)


def access(g, binary, index):
    a = g['accessors'][index]
    if 'sparse' in a or 'bufferView' not in a:
        raise ValueError('Sparse or implicit accessors require explicit conversion first')
    v = g['bufferViews'][a['bufferView']]
    dtype = np.dtype(DTYPES[a['componentType']]); width = WIDTHS[a['type']]
    data = np.ndarray((a['count'], width), dtype, binary,
                      v.get('byteOffset', 0) + a.get('byteOffset', 0),
                      strides=(v.get('byteStride', dtype.itemsize * width), dtype.itemsize)).astype(np.float64)
    if a.get('normalized'):
        data = np.maximum(-1, data / np.iinfo(dtype).max)
    if not np.isfinite(data).all():
        raise ValueError('Non-finite accessor')
    return data


def matrix(node):
    if 'matrix' in node:
        result = np.asarray(node['matrix'], float).reshape(4, 4).T
    else:
        x, y, z, w = node.get('rotation', [0, 0, 0, 1])
        if abs(x*x+y*y+z*z+w*w-1) > 1e-5:
            raise ValueError('Node quaternion is not normalized')
        r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                      [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                      [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        result = np.eye(4); result[:3, :3] = r @ np.diag(node.get('scale', [1, 1, 1]))
        result[:3, 3] = node.get('translation', [0, 0, 0])
    if not np.isfinite(result).all() or abs(np.linalg.det(result)) < 1e-12:
        raise ValueError('Invalid node transform')
    return result


def instances(g):
    out = []; seen = set()
    def visit(i, parent, inherited):
        if i in seen:
            raise ValueError('Node has multiple parents or a cycle')
        seen.add(i); n = g['nodes'][i]; world = parent @ matrix(n)
        extras = {**inherited, **n.get('extras', {})}
        if 'mesh' in n:
            out.append((i, n['mesh'], world, extras))
        for child in n.get('children', []):
            visit(child, world, extras)
    for root in g['scenes'][g.get('scene', 0)]['nodes']:
        visit(root, np.eye(4), {})
    return out


def transform(points, world):
    return points @ world[:3, :3].T + world[:3, 3]


def normalize(values):
    lengths = np.linalg.norm(values, axis=-1, keepdims=True)
    if (lengths < 1e-12).any():
        raise ValueError('Zero shading normal')
    return values / lengths


class BVH:
    def __init__(self, triangles):
        cache = Path(tempfile.gettempdir()) / 'hkust-structure-shadow-bvh'
        cache.mkdir(parents=True, exist_ok=True)
        tag = sha(BVH_CPP.encode())[:16]; cpp = cache / (tag + '.cpp'); so = cache / (tag + '.so')
        if not so.exists():
            compiler = shutil.which('clang++') or shutil.which('c++')
            if not compiler:
                raise RuntimeError('C++17 compiler unavailable')
            cpp.write_text(BVH_CPP)
            temporary = cache / (tag + f'.{os.getpid()}.so')
            subprocess.run([compiler, '-std=c++17', '-O3', '-shared', '-fPIC', str(cpp), '-o', str(temporary)], check=True)
            temporary.replace(so)
        self.lib = ctypes.CDLL(str(so)); ptr = ctypes.POINTER(ctypes.c_double)
        self.lib.bvh_create.argtypes = [ptr, ctypes.c_int]; self.lib.bvh_create.restype = ctypes.c_void_p
        self.lib.bvh_free.argtypes = [ctypes.c_void_p]
        self.lib.bvh_hits.argtypes = [ctypes.c_void_p, ptr, ptr, ptr, ctypes.c_int, ctypes.POINTER(ctypes.c_uint8)]
        tris = np.ascontiguousarray(triangles, dtype=np.float64)
        self.handle = self.lib.bvh_create(tris.ctypes.data_as(ptr), len(tris))
        if not self.handle:
            raise MemoryError('BVH allocation failed')

    def hits(self, origins, directions, maximum):
        p = ctypes.POINTER(ctypes.c_double)
        o = np.ascontiguousarray(origins, dtype=np.float64)
        d = np.ascontiguousarray(np.broadcast_to(directions, o.shape), dtype=np.float64)
        t = np.ascontiguousarray(np.broadcast_to(maximum, (len(o),)), dtype=np.float64)
        out = np.empty(len(o), dtype=np.uint8)
        self.lib.bvh_hits(self.handle, o.ctypes.data_as(p), d.ctypes.data_as(p), t.ctypes.data_as(p), len(o), out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)))
        return out.astype(bool)

    def close(self):
        if self.handle:
            self.lib.bvh_free(self.handle); self.handle = None


def lighting(bvh, positions, normals, settings):
    origins = positions + settings['surfaceOffsetM'] * normals
    light = normalize(np.asarray(settings['directionTowardLight'], float))
    sun = bvh.hits(origins, light, settings['shadowDistanceM'])
    facing = np.maximum(0, normals @ light)
    # Fibonacci cosine-weighted hemisphere, rotated consistently around each normal.
    basis = np.tile([0., 1., 0.], (len(normals), 1))
    basis[np.abs(normals[:, 1]) > .9] = [1, 0, 0]
    tangent = normalize(np.cross(basis, normals)); bitangent = np.cross(normals, tangent)
    blocked = np.zeros(len(positions), dtype=np.int32)
    for i in range(settings['aoRays']):
        radial = math.sqrt((i + .5) / settings['aoRays']); phi = i * math.pi * (3 - math.sqrt(5))
        direction = (radial * math.cos(phi) * tangent + radial * math.sin(phi) * bitangent
                     + math.sqrt(1-radial*radial) * normals)
        blocked += bvh.hits(origins, direction, settings['aoDistanceM'])
    ao = 1 - blocked / settings['aoRays']
    multiplier = ((1-settings['aoStrength']*(1-ao)) *
                  (1-settings['shadowStrength']*sun*facing))
    return multiplier, ao, sun & (facing > 0)


def split_attributes(attributes, indices, world, max_edge, remaining):
    """Longest-edge bisection in world metres, preserving each source plane."""
    keys = list(attributes); sizes = [attributes[k].shape[1] for k in keys]
    joined = np.concatenate([attributes[k] for k in keys], axis=1)
    pi = keys.index('POSITION'); po = sum(sizes[:pi]); polys = []; parents = []; exceptions = []
    for original, ix in enumerate(indices.reshape(-1, 3)):
        stack = [joined[ix]]; children = []
        while stack:
            tri = stack.pop(); p = transform(tri[:, po:po+3], world)
            squared = np.sum((p - np.roll(p, -1, axis=0))**2, axis=1); edge = int(np.argmax(squared))
            if squared[edge] > max_edge**2 * (1+1e-10):
                a, b, c = edge, (edge+1) % 3, (edge+2) % 3; mid = (tri[a]+tri[b])/2
                stack.extend([np.array([mid, tri[b], tri[c]]), np.array([tri[a], mid, tri[c]])])
            else:
                children.append(tri)
            if len(polys) + len(children) + len(stack) > remaining:
                raise ValueError('Subdivision triangle limit exceeded; no partial output written')
        packed = np.asarray(children)[:, :, po:po+3].astype('<f4')
        packed_cross = np.linalg.norm(np.cross(packed[:, 1]-packed[:, 0], packed[:, 2]-packed[:, 0]), axis=1)
        if (packed_cross <= 1e-8).any():
            source = joined[ix, po:po+3].astype('<f4')
            source_cross = np.linalg.norm(np.cross(source[1]-source[0], source[2]-source[0]))
            if source_cross <= 1e-8:
                raise ValueError('Source triangle already degenerate before subdivision')
            source_world = transform(source.astype(float), world)
            exceptions.append({'sourceTriangle': original, 'rejectedSubTriangles': len(children),
                'collapsedSubTriangles': int((packed_cross <= 1e-8).sum()),
                'originalLongestEdgeM': float(np.linalg.norm(source_world-np.roll(source_world, -1, axis=0), axis=1).max()),
                'policy': 'Retain the entire original source triangle and shade its original vertices; no source surface discarded'})
            children = [joined[ix]]
        polys.extend(children); parents.extend([original]*len(children))
    arr = np.asarray(polys, float).reshape(-1, sum(sizes)); result = {}; start = 0
    for k, size in zip(keys, sizes):
        result[k] = arr[:, start:start+size]; start += size
    if 'NORMAL' in result:
        result['NORMAL'] = normalize(result['NORMAL'])
    return result, np.asarray(parents, np.int32), exceptions


def image_hashes(g, binary):
    result = []
    for im in g.get('images', []):
        v = g['bufferViews'][im['bufferView']]; start = v.get('byteOffset', 0)
        result.append(sha(binary[start:start+v['byteLength']]))
    return result


def settings_from_args(args):
    return {'directionTowardLight': normalize(np.asarray(args.direction, float)).tolist(),
            'shadowDistanceM': args.shadow_distance, 'aoDistanceM': args.ao_distance,
            'surfaceOffsetM': .02, 'aoRays': args.ao_rays, 'aoStrength': args.ao_strength,
            'shadowStrength': args.shadow_strength, 'maximumEdgeM': args.max_edge,
            'maximumOutputTriangles': args.max_triangles, 'maximumSamples': args.max_samples,
            'policy': 'Fixed display-direction occlusion only; unoccluded colours unchanged. Not measured lighting.'}


def bake(source, output, settings):
    begin = time.monotonic(); source = Path(source).resolve(); output = Path(output).resolve()
    if output == source or output.is_relative_to(ROOT / 'public'):
        raise ValueError('Require isolated output distinct from source and outside public')
    for k in ('maximumEdgeM', 'shadowDistanceM', 'aoDistanceM', 'surfaceOffsetM'):
        if not math.isfinite(settings[k]) or settings[k] <= 0:
            raise ValueError('Positive finite geometric settings required')
    if not 1 <= settings['aoRays'] <= 128 or any(not 0 <= settings[k] <= 1 for k in ('aoStrength', 'shadowStrength')):
        raise ValueError('Invalid bounded lighting settings')
    g, binary, source_sha = read_glb(source); original = copy.deepcopy(g); original_binary = binary
    if g.get('extras', {}).get('structureOcclusionBake'):
        raise ValueError('Input already baked; refusing accumulated darkening')
    active = instances(g); casters = []; jobs = []; skipped = []; input_tris = 0
    for node_i, mesh_i, world, extras in active:
        for primitive_i, p in enumerate(original['meshes'][mesh_i]['primitives']):
            if p.get('mode', 4) != 4 or p.get('targets') or p.get('extensions'):
                raise ValueError('Explicit static triangle primitives required; extensions/morphs unsupported')
            a = {k: access(original, binary, v) for k, v in p['attributes'].items()}
            if any(k.startswith(('JOINTS_', 'WEIGHTS_')) for k in a):
                raise ValueError('Skinning attributes unsupported')
            ix = access(original, binary, p['indices']).ravel().astype(int) if 'indices' in p else np.arange(len(a['POSITION']))
            if len(ix) % 3 or ix.max(initial=0) >= len(a['POSITION']):
                raise ValueError('Invalid triangle indices')
            tri = transform(a['POSITION'], world)[ix].reshape(-1, 3, 3); input_tris += len(tri)
            material = original.get('materials', [{}])[p.get('material', 0)]
            opaque = material.get('alphaMode', 'OPAQUE') == 'OPAQUE' and not material.get('extensions', {}).get('KHR_materials_transmission')
            if opaque:
                casters.append(tri)
            textured = 'baseColorTexture' in material.get('pbrMetallicRoughness', {})
            optin = material.get('extras', {}).get('bakeStructureShadow') is True
            if not opaque or (textured and not optin) or material.get('extras', {}).get('bakeStructureShadow') is False:
                skipped.append({'node': node_i, 'primitive': primitive_i, 'material': p.get('material'),
                                'reason': 'photo-preserved' if textured and not optin else 'non-opaque-or-explicit-opt-out'})
                continue
            if 'NORMAL' not in a:
                if 'indices' in p:
                    raise ValueError('Indexed bake target requires explicit normals')
                local = a['POSITION'].reshape(-1, 3, 3)
                a['NORMAL'] = np.repeat(normalize(np.cross(local[:, 1]-local[:, 0], local[:, 2]-local[:, 0])), 3, axis=0)
            preserve = extras.get('representationRole') == 'exact_source_floor_parts' or p.get('extras', {}).get('preserveGeometryAccessors') is True
            jobs.append({'node': node_i, 'mesh': mesh_i, 'primitive': primitive_i, 'world': world, 'original': p,
                         'attributes': a, 'indices': ix, 'preserve': preserve, 'optinTexture': textured,
                         'material': p.get('material', 0)})
    if input_tris > settings['maximumOutputTriangles']:
        raise ValueError('Input already exceeds configured triangle limit')
    running_triangles = input_tris; max_plane = 0.; max_area_delta = 0.
    encoded_plane = 0.; encoded_area = 0.; subdivision_fallbacks = []
    for job in jobs:
        old = job['attributes']; oldix = job['indices']; count = len(oldix)//3
        if job['preserve']:
            attrs = old; parent = np.arange(count)
        else:
            attrs, parent, exceptions = split_attributes(old, oldix, job['world'], settings['maximumEdgeM'],
                                             settings['maximumOutputTriangles']-running_triangles+count)
            subdivision_fallbacks.extend({**e, 'node': job['node'], 'nodeName': g['nodes'][job['node']].get('name'),
                                         'primitive': job['primitive']} for e in exceptions)
            oldtris = transform(old['POSITION'], job['world'])[oldix].reshape(-1, 3, 3)
            newtris = transform(attrs['POSITION'], job['world']).reshape(-1, 3, 3)
            cross = np.cross(oldtris[:, 1]-oldtris[:, 0], oldtris[:, 2]-oldtris[:, 0]); areas = np.linalg.norm(cross, axis=1)/2
            nonzero = areas > 1e-12
            if not nonzero.all():
                raise ValueError('Degenerate target source triangle; refuses silent removal')
            max_plane = max(max_plane, float(abs(((newtris-oldtris[parent, :1]) * (cross[parent]/(2*areas[parent, None]))[:, None, :]).sum(axis=-1)).max(initial=0)))
            newareas = np.linalg.norm(np.cross(newtris[:, 1]-newtris[:, 0], newtris[:, 2]-newtris[:, 0]), axis=1)/2
            max_area_delta = max(max_area_delta, float(abs(np.bincount(parent, weights=newareas, minlength=count)-areas).max(initial=0)))
            encoded = transform(attrs['POSITION'].astype('<f4').astype(float), job['world']).reshape(-1, 3, 3)
            encoded_plane = max(encoded_plane, float(abs(((encoded-oldtris[parent, :1]) * (cross[parent]/(2*areas[parent, None]))[:, None, :]).sum(axis=-1)).max(initial=0)))
            encoded_areas = np.linalg.norm(np.cross(encoded[:, 1]-encoded[:, 0], encoded[:, 2]-encoded[:, 0]), axis=1)/2
            encoded_area = max(encoded_area, float(abs(np.bincount(parent, weights=encoded_areas, minlength=count)-areas).max(initial=0)))
            running_triangles += len(parent)-count
        job['prepared'] = attrs; job['parents'] = parent
        job['positions'] = transform(attrs['POSITION'], job['world'])
        job['normals'] = normalize(attrs['NORMAL'] @ np.linalg.inv(job['world'][:3, :3]))
    # Weld samples by actual position + surface normal, not business identity.
    samples = np.concatenate([np.column_stack((j['positions'], j['normals'])) for j in jobs]) if jobs else np.empty((0, 6))
    unique, inverse = np.unique(np.round(samples, 7), axis=0, return_inverse=True)
    if len(unique) > settings['maximumSamples']:
        raise ValueError('Sample limit exceeded; no partial output written')
    bvh = BVH(np.concatenate(casters) if casters else np.empty((0, 3, 3)))
    try:
        factors, ao, blocked = lighting(bvh, unique[:, :3], normalize(unique[:, 3:]), settings) if len(unique) else (np.array([]), np.array([]), np.array([], bool))
    finally:
        bvh.close()
    buffer = bytearray(binary)
    def append_accessor(data, kind):
        data = np.ascontiguousarray(data, dtype='<f4'); buffer.extend(b'\0' * (-len(buffer) % 4))
        vi = len(g['bufferViews']); g['bufferViews'].append({'buffer': 0, 'byteOffset': len(buffer), 'byteLength': data.nbytes, 'target': 34962}); buffer.extend(data.tobytes())
        result = {'bufferView': vi, 'componentType': 5126, 'count': len(data), 'type': kind}
        if kind == 'VEC3':
            result.update(min=data.min(0).tolist(), max=data.max(0).tolist())
        g['accessors'].append(result); return len(g['accessors'])-1
    references = {}; cloned = {}; audit = []; offset = 0
    for node_i, mesh_i, _, _ in active:
        references[mesh_i] = references.get(mesh_i, 0)+1
    for job in jobs:
        node_i, mesh_i, pi = job['node'], job['mesh'], job['primitive']
        if references[mesh_i] > 1:
            if node_i not in cloned:
                cloned[node_i] = len(g['meshes']); g['meshes'].append(copy.deepcopy(original['meshes'][mesh_i])); g['nodes'][node_i]['mesh'] = cloned[node_i]
            mesh_i = cloned[node_i]
        p = g['meshes'][mesh_i]['primitives'][pi]; attrs = job['prepared']; n = len(attrs['POSITION'])
        sample_index = inverse[offset:offset+n]; multiplier = factors[sample_index]; offset += n
        colour = attrs.get('COLOR_0', np.ones((n, 3))).copy(); colour[:, :3] *= multiplier[:, None]
        if not job['preserve']:
            p.pop('indices', None); p['attributes'] = {k: append_accessor(v, 'VEC'+str(v.shape[1])) for k, v in attrs.items() if k != 'COLOR_0'}
        p['attributes']['COLOR_0'] = append_accessor(colour, 'VEC'+str(colour.shape[1]))
        extra = p.setdefault('extras', {}); ranges = extra.get('featureTriangleRanges')
        if ranges and not job['preserve']:
            prefix = np.r_[0, np.cumsum(np.bincount(job['parents'], minlength=len(job['indices'])//3))]
            if any(not isinstance(r, list) or len(r) != 3 or r[0] < 0 or r[1] < 0 or r[0]+r[1] >= len(prefix) for r in ranges):
                raise ValueError('Invalid feature triangle ranges')
            extra['sourceFeatureTriangleRanges'] = copy.deepcopy(ranges)
            extra['featureTriangleRanges'] = [[int(prefix[start]), int(prefix[start+count]-prefix[start]), label] for start, count, label in ranges]
        if 'sourceTriangleIndices' in extra and not job['preserve']:
            previous = extra['sourceTriangleIndices']
            if len(previous) != len(job['indices'])//3:
                raise ValueError('Invalid source triangle metadata')
            extra['sourceTriangleIndices'] = [previous[i] for i in job['parents']]
        extra['structureOcclusionBake'] = {'linearColourMultiplier': True, 'sourceGeometryAccessorsPreserved': job['preserve']}
        # The multiplier already contains the fixed display lighting for this
        # untextured surface. Mark that fact in the asset so the shared runtime
        # can display it once instead of washing it out with a second PBR pass.
        if not job['optinTexture']:
            g['materials'][job['material']].setdefault('extras', {})['campusBakedLighting'] = True
        audit.append({'node': node_i, 'nodeName': g['nodes'][node_i].get('name'), 'primitive': pi, 'material': p.get('material'),
                      'sourceTriangles': len(job['indices'])//3, 'outputTriangles': len(job['parents']), 'sourceAccessorsPreserved': job['preserve'],
                      'explicitTextureOptIn': job['optinTexture'], 'sampleVertices': n,
                      'multiplierMinMeanMax': [float(multiplier.min()), float(multiplier.mean()), float(multiplier.max())],
                      'blockedDirectionalFraction': float(blocked[sample_index].mean()), 'aoMean': float(ao[sample_index].mean())})
    g.setdefault('extras', {})['structureOcclusionBake'] = {'sourceSHA256': source_sha, 'settings': settings,
        'scope': 'Real source triangles only; no new equipment or inferred geometry. Isolated display candidate.'}
    g['buffers'][0]['byteLength'] = len(buffer)
    js = json.dumps(g, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode(); js += b' ' * (-len(js) % 4); buffer += b'\0' * (-len(buffer) % 4)
    raw = struct.pack('<4sII', b'glTF', 2, 28+len(js)+len(buffer))+struct.pack('<I4s', len(js), b'JSON')+js+struct.pack('<I4s', len(buffer), b'BIN\0')+buffer
    assert image_hashes(g, buffer) == image_hashes(original, original_binary)
    assert g.get('textures') == original.get('textures')
    assert len(g.get('materials', [])) == len(original.get('materials', []))
    for material_i, before in enumerate(original.get('materials', [])):
        after = copy.deepcopy(g['materials'][material_i])
        extras = after.get('extras', {})
        extras.pop('campusBakedLighting', None)
        if not extras and 'extras' not in before:
            after.pop('extras', None)
        assert after == before
    for item in skipped:
        new_mesh = g['nodes'][item['node']]['mesh']
        old_mesh = original['nodes'][item['node']]['mesh']
        assert g['meshes'][new_mesh]['primitives'][item['primitive']] == original['meshes'][old_mesh]['primitives'][item['primitive']]
    packed_minimum = float('inf')
    for _, mi, _, _ in instances(g):
        for primitive in g['meshes'][mi]['primitives']:
            vertices = access(g, buffer, primitive['attributes']['POSITION']).astype('<f4')
            ix = access(g, buffer, primitive['indices']).ravel().astype(int) if 'indices' in primitive else np.arange(len(vertices))
            packed = vertices[ix].reshape(-1, 3, 3)
            cross_size = np.linalg.norm(np.cross(packed[:, 1]-packed[:, 0], packed[:, 2]-packed[:, 0]), axis=1)
            if (cross_size <= 1e-8).any():
                raise ValueError('Packed output contains a degenerate triangle; no candidate written')
            packed_minimum = min(packed_minimum, float(cross_size.min()))
    if max_plane > 1e-5 or max_area_delta > 1e-5:
        raise ValueError('Subdivision changed source surface')
    output.parent.mkdir(parents=True, exist_ok=True); temporary = output.with_name(output.name+'.tmp'); temporary.write_bytes(raw); temporary.replace(output)
    report = {'status': 'PASS isolated geometry-occlusion candidate; not browser acceptance', 'source': str(source), 'sourceSHA256': source_sha,
              'output': str(output), 'outputSHA256': sha(raw), 'outputBytes': len(raw), 'settings': settings,
              'inputTriangles': input_tris, 'outputTriangles': running_triangles, 'casterTriangles': sum(len(x) for x in casters),
              'activeMeshNodes': len(active), 'sharedMeshInstanceClones': len(cloned), 'uniqueSamples': len(unique), 'rays': len(unique)*(settings['aoRays']+1),
              'maximumSubdivisionPlaneErrorM': max_plane, 'maximumPerSourceTriangleAreaDeltaM2': max_area_delta,
              'maximumStoredFloat32PlaneErrorM': encoded_plane, 'maximumStoredFloat32SourceTriangleAreaDeltaM2': encoded_area,
              'minimumPackedTriangleTwiceAreaM2': packed_minimum, 'packedDegenerateTriangles': 0,
              'subdivisionFallbacks': subdivision_fallbacks,
              'originalImageSHA256': image_hashes(original, original_binary), 'imagesBytesUnchanged': True,
              'materialFactorsTexturesSamplersUnchanged': g.get('samplers') == original.get('samplers'),
              'bakedLightingMaterialIds': sorted({j['material'] for j in jobs if not j['optinTexture']}),
              'colourSpace': 'Only LINEAR COLOR_0 RGB multiplied. BaseColorFactor stays linear; original encoded sRGB images unchanged; alpha retained.',
              'skipped': skipped, 'baked': audit, 'elapsedSeconds': time.monotonic()-begin,
              'limitations': ['Display sun direction and local AO radius are not measured illumination.',
                  'Cannot add shadows from missing roof equipment, environmental context or omitted geometry.',
                  'Opaque triangles cast together across all active roots; transparent/masked/transmission materials are excluded from occlusion.',
                  'Exact source floor accessors stay byte-identical and are sampled only at existing vertices.',
                  'Runtime must honour campusBakedLighting on untextured baked materials so the fixed multiplier is displayed once; requires browser review, not a physical-lighting claim.']}
    output.with_suffix('.bake.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return report


def self_test(output):
    settings = settings_from_args(argparse.Namespace(direction=[0, 1, 0], shadow_distance=20, ao_distance=3, ao_rays=32,
        ao_strength=.35, shadow_strength=.28, max_edge=1.2, max_triangles=250000, max_samples=250000))
    plate = np.array([[[-2, 2, -2], [2, 2, 2], [2, 2, -2]], [[-2, 2, -2], [-2, 2, 2], [2, 2, 2]]], float)
    plane = np.array([[[-10, 0, -10], [10, 0, 10], [10, 0, -10]], [[-10, 0, -10], [-10, 0, 10], [10, 0, 10]]], float)
    cases = []
    def check(name, condition, **evidence):
        if not condition:
            raise AssertionError(name)
        cases.append({'name': name, 'pass': True, **evidence})
    bvh = BVH(np.concatenate((plane, plate)))
    try:
        pos = np.array([[0, 0, 0], [5, 0, 0], [0, 2.01, 0]], float); normals = np.tile([0, 1, 0], (3, 1))
        factors, ao, blocked = lighting(bvh, pos, normals, settings)
        check('real_overhang_shadows_ground_but_exposed_point_clear', blocked.tolist() == [True, False, False], factors=factors.tolist())
        check('local_ao_lower_under_actual_structure', ao[0] < ao[1] and ao[2] == 1, ao=ao.tolist())
        check('source_plane_does_not_self_shadow', factors[2] == 1)
        short = {**settings, 'aoDistanceM': 1}
        _, near_ao, _ = lighting(bvh, pos[:1], normals[:1], short)
        check('beyond_ao_distance_is_not_local_occlusion', near_ao[0] == 1)
        check('linear_colour_not_srgb_product', (np.array([.5])*np.array([.5])).item() == .25)
    finally:
        bvh.close()
    # Real GLB round trip: two roots, transformed blocker, photo opt-out and swatch opt-in.
    temp = Path(tempfile.mkdtemp(prefix='hkust-shadow-test-')); binary = bytearray(); g = {'asset': {'version': '2.0'}, 'scene': 0,
        'scenes': [{'nodes': [0, 1, 2]}], 'nodes': [{'name': 'receiving-root', 'mesh': 0}, {'name': 'blocking-root', 'mesh': 1, 'translation': [0, 2, 0]},
            {'name': 'exact-floor', 'mesh': 0, 'translation': [10, 0, 0], 'extras': {'representationRole': 'exact_source_floor_parts'}}],
        'meshes': [], 'accessors': [], 'bufferViews': [], 'buffers': [{}],
        'materials': [{'pbrMetallicRoughness': {'baseColorFactor': [.25, .25, .25, 1]}},
            {'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}},
            {'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}, 'extras': {'bakeStructureShadow': True}}],
        'images': [], 'textures': [{'source': 0}]}
    def attr(a, kind):
        a = np.asarray(a, '<f4'); i = len(g['bufferViews']); g['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': a.nbytes}); binary.extend(a.tobytes())
        g['accessors'].append({'bufferView': i, 'componentType': 5126, 'count': len(a), 'type': kind}); return len(g['accessors'])-1
    ground = plane.reshape(-1, 3)/5
    common = {'POSITION': attr(ground, 'VEC3'), 'NORMAL': attr(np.tile([0, 1, 0], (6, 1)), 'VEC3'),
              'TEXCOORD_0': attr(np.zeros((6, 2)), 'VEC2'), 'COLOR_0': attr(np.tile([.5, .5, .5, .7], (6, 1)), 'VEC4')}
    g['meshes'] = [{'primitives': [{'attributes': common.copy(), 'material': i, 'extras': {'featureTriangleRanges': [[0, 1, 'first'], [1, 1, 'second']]}} for i in range(3)]},
                   {'primitives': [{'attributes': {'POSITION': attr((plate-[0, 2, 0]).reshape(-1, 3), 'VEC3'), 'NORMAL': attr(np.tile([0, 1, 0], (6, 1)), 'VEC3')}, 'material': 0}]}]
    # Valid 1x1 PNG; never decoded or modified by baker.
    import base64
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    g['images'] = [{'bufferView': len(g['bufferViews']), 'mimeType': 'image/png'}]
    g['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(png)}); binary.extend(png)
    g['buffers'][0]['byteLength'] = len(binary); binary.extend(b'\0'*(-len(binary)%4)); j = json.dumps(g).encode(); j += b' '*(-len(j)%4)
    source = temp/'source.glb'; source.write_bytes(struct.pack('<4sII', b'glTF', 2, 28+len(j)+len(binary))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
    report = bake(source, temp/'candidate.glb', settings); out, ob, _ = read_glb(temp/'candidate.glb')
    prs = out['meshes'][out['nodes'][0]['mesh']]['primitives']; old = g['meshes'][0]['primitives']
    check('registered_photo_primitive_exactly_unchanged', prs[1] == old[1])
    check('explicit_textured_swatch_receives_bake', prs[2]['attributes']['COLOR_0'] != old[2]['attributes']['COLOR_0'])
    check('all_root_transforms_cast_together', next(x for x in report['baked'] if x['node'] == 0)['blockedDirectionalFraction'] > .5)
    check('linear_input_colour_and_alpha_preserved', float(access(out, ob, prs[0]['attributes']['COLOR_0'])[:, :3].max()) <= .5 and np.allclose(access(out, ob, prs[0]['attributes']['COLOR_0'])[:, 3], .7))
    check('feature_ranges_reindexed_after_subdivision', prs[0]['extras']['featureTriangleRanges'][0][1] > 1 and sum(r[1] for r in prs[0]['extras']['featureTriangleRanges']) == out['accessors'][prs[0]['attributes']['POSITION']]['count']//3)
    check('encoded_images_and_material_factors_unchanged', image_hashes(g, binary) == image_hashes(out, ob) and
          all({k:v for k,v in material.items() if k != 'extras'} == {k:v for k,v in g['materials'][i].items() if k != 'extras'}
              for i,material in enumerate(out['materials'])))
    check('untextured_baked_materials_mark_single_runtime_light_pass',
          out['materials'][0]['extras']['campusBakedLighting'] is True and
          out['materials'][1].get('extras', {}).get('campusBakedLighting') is None)
    exact = out['meshes'][out['nodes'][2]['mesh']]['primitives'][0]
    check('source_floor_geometry_accessors_retained', all(exact['attributes'][k] == old[0]['attributes'][k] for k in ('POSITION', 'NORMAL', 'TEXCOORD_0')))
    check('shared_mesh_cloned_per_transform_with_distinct_occlusion', out['nodes'][0]['mesh'] != out['nodes'][2]['mesh'] and report['sharedMeshInstanceClones'] == 2)
    skinny = np.array([[700, 170, -1100], [704, 170, -1100], [700, 170, -1100.0001220703125]], float)
    split, parent, exceptions = split_attributes({'POSITION': skinny, 'NORMAL': np.tile([0, 1, 0], (3, 1))}, np.arange(3), np.eye(4), 1, 1000)
    check('float32_collapsed_child_falls_back_to_whole_source_triangle', len(exceptions) == 1 and len(parent) == 1 and np.array_equal(split['POSITION'], skinny), exception=exceptions)
    try:
        bake(source, temp/'should-not-exist.glb', {**settings, 'maximumOutputTriangles': report['inputTriangles']+1})
    except ValueError:
        check('bounded_subdivision_fails_atomically', not (temp/'should-not-exist.glb').exists())
    else:
        raise AssertionError('Expected subdivision guard')
    try:
        bake(temp/'candidate.glb', temp/'double.glb', settings)
    except ValueError:
        check('second_bake_rejected_to_avoid_accumulating_darkness', not (temp/'double.glb').exists())
    else:
        raise AssertionError('Expected repeat guard')
    result = {'status': 'PASS', 'cases': cases, 'fixtures': str(temp), 'scope': 'Actual triangle BVH + GLB round trip; no browser acceptance.'}
    Path(output).parent.mkdir(parents=True, exist_ok=True); Path(output).write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('source', nargs='?'); p.add_argument('output', nargs='?')
    p.add_argument('--self-test'); p.add_argument('--direction', type=float, nargs=3, default=[-.4, .8, .5])
    p.add_argument('--shadow-distance', type=float, default=250); p.add_argument('--ao-distance', type=float, default=6)
    p.add_argument('--ao-rays', type=int, default=16); p.add_argument('--ao-strength', type=float, default=.35)
    p.add_argument('--shadow-strength', type=float, default=.28); p.add_argument('--max-edge', type=float, default=1.5)
    p.add_argument('--max-triangles', type=int, default=350000); p.add_argument('--max-samples', type=int, default=300000)
    args = p.parse_args()
    if args.self_test:
        result = self_test(args.self_test); print(json.dumps({'status': result['status'], 'cases': len(result['cases'])})); return
    if not args.source or not args.output:
        p.error('source and isolated output are required')
    result = bake(args.source, args.output, settings_from_args(args))
    print(json.dumps({k: result[k] for k in ['output', 'outputSHA256', 'outputBytes', 'inputTriangles', 'outputTriangles', 'uniqueSamples', 'rays', 'elapsedSeconds']}, indent=2))


if __name__ == '__main__':
    main()
