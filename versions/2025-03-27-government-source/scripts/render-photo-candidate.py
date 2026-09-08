#!/usr/bin/env python3
"""Read actual GLB bytes and rasterize candidate surfaces for offline review.

This is not browser acceptance: there is no original campus/terrain context.
Unlit photo pixels and packed vertex colours are used without a second light.
"""
import argparse
import hashlib
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image


def read_glb(path):
    raw=Path(path).read_bytes();length=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+length]),raw[28+length:],hashlib.sha256(raw).hexdigest()


def access(g,b,index):
    a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
    width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
    size=np.dtype(dtype).itemsize
    value=np.ndarray((a['count'],width),dtype,b,v.get('byteOffset',0)+a.get('byteOffset',0),
        strides=(v.get('byteStride',width*size),size)).astype(float)
    if a.get('normalized'):value/=np.iinfo(np.dtype(dtype)).max
    return value


def render(path,output,node_name=None,size=(1300,1000),view=(1,.6,1)):
    g,b,digest=read_glb(path);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    images=[]
    for item in g.get('images',[]):
        v=g['bufferViews'][item['bufferView']]
        im=Image.open(io.BytesIO(b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB')
        images.append(np.asarray(im)/255)
    included=set()
    def visit(i):
        included.add(i)
        for child in g['nodes'][i].get('children',[]):visit(child)
    roots=g['scenes'][g.get('scene',0)]['nodes']
    if node_name:
        roots=[i for i,n in enumerate(g['nodes']) if n.get('name')==node_name]
        if len(roots)!=1:raise ValueError('Need exactly one named root')
    for i in roots:visit(i)
    primitives=[]
    for i in sorted(included):
        node=g['nodes'][i]
        if 'mesh' not in node:continue
        if any(k in node for k in ('matrix','translation','rotation','scale')):
            raise ValueError('Renderer requires already-local source vertices; refuses silent transform omission')
        for p in g['meshes'][node['mesh']]['primitives']:
            a=p['attributes'];pos=access(g,b,a['POSITION'])
            ix=access(g,b,p['indices']).reshape(-1).astype(int) if 'indices' in p else np.arange(len(pos))
            uv=access(g,b,a['TEXCOORD_0'])[ix].reshape(-1,3,2) if 'TEXCOORD_0' in a else None
            colors=access(g,b,a['COLOR_0'])[ix,:3].reshape(-1,3,3) if 'COLOR_0' in a else None
            primitives.append((pos[ix].reshape(-1,3,3),uv,colors,p['material']))
    allp=np.concatenate([x[0].reshape(-1,3) for x in primitives]);center=(allp.min(0)+allp.max(0))/2
    forward=-np.array(view,dtype=float);forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,forward)
    W,H=size;projected=np.column_stack(((allp-center)@right,(allp-center)@up))
    scale=min((W-80)/np.ptp(projected[:,0]),(H-80)/np.ptp(projected[:,1]));project_center=(projected.min(0)+projected.max(0))/2
    pixels=np.full((H,W,3),[.84,.87,.88]);zb=np.full((H,W),np.inf)
    for tris,uvs,colors,mi in primitives:
        pbr=g['materials'][mi]['pbrMetallicRoughness'];factor=np.array(pbr.get('baseColorFactor',[1,1,1,1]),dtype=float)[:3]
        texture=pbr.get('baseColorTexture');tex=images[g['textures'][texture['index']]['source']] if texture else None
        repeat=texture and g.get('samplers',[{}])[g['textures'][texture['index']].get('sampler',0)].get('wrapS',10497)==10497
        for j,tri in enumerate(tris):
            projected=np.column_stack((((tri-center)@right-project_center[0])*scale+W/2,
                -((tri-center)@up-project_center[1])*scale+H/2,(tri-center)@forward))
            x0=max(0,int(np.floor(projected[:,0].min())));x1=min(W-1,int(np.ceil(projected[:,0].max())))
            y0=max(0,int(np.floor(projected[:,1].min())));y1=min(H-1,int(np.ceil(projected[:,1].max())))
            if x1<x0 or y1<y0:continue
            a,c,d=projected;den=(c[1]-d[1])*(a[0]-d[0])+(d[0]-c[0])*(a[1]-d[1])
            if abs(den)<1e-9:continue
            yy,xx=np.mgrid[y0:y1+1,x0:x1+1];xx=xx+.5;yy=yy+.5
            q0=((c[1]-d[1])*(xx-d[0])+(d[0]-c[0])*(yy-d[1]))/den
            q1=((d[1]-a[1])*(xx-d[0])+(a[0]-d[0])*(yy-d[1]))/den;q2=1-q0-q1
            depth=q0*a[2]+q1*c[2]+q2*d[2];old=zb[y0:y1+1,x0:x1+1]
            ok=(q0>=-1e-7)&(q1>=-1e-7)&(q2>=-1e-7)&(depth<old)
            if not ok.any():continue
            linear_surface=np.broadcast_to(factor,(*q0.shape,3)).copy()
            if tex is not None:
                if uvs is None:raise ValueError('Textured surface has no UV')
                uv=q0[...,None]*uvs[j,0]+q1[...,None]*uvs[j,1]+q2[...,None]*uvs[j,2]
                if repeat:uv%=1
                th,tw=tex.shape[:2];ix=np.clip((uv[:,:,0]*tw).astype(int),0,tw-1);iy=np.clip((uv[:,:,1]*th).astype(int),0,th-1)
                srgb=tex[iy,ix]
                linear_surface*=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
                calibration=g['materials'][mi].get('extras',{}).get('campusPhotoCalibration')
                if calibration:
                    luminance=np.sum(linear_surface*np.array([.2126,.7152,.0722]),axis=-1,keepdims=True)
                    linear_surface=(luminance*(1-calibration['saturation'])+linear_surface*calibration['saturation'])*calibration['exposure']*np.asarray(calibration['linearTint'])
            if colors is not None:
                linear=q0[...,None]*colors[j,0]+q1[...,None]*colors[j,1]+q2[...,None]*colors[j,2]
                linear_surface*=linear
            # GLTF vertex/base factors are linear; images and PNG output are sRGB.
            # Barycentrics outside the triangle can extrapolate below zero;
            # those pixels are discarded, but both np.where branches evaluate.
            linear_surface=np.maximum(linear_surface,0)
            surface=np.where(linear_surface<=.0031308,linear_surface*12.92,1.055*linear_surface**(1/2.4)-.055)
            old[ok]=depth[ok];pixels[y0:y1+1,x0:x1+1][ok]=surface[ok]
    Image.fromarray((np.clip(pixels,0,1)*255+.5).astype(np.uint8)).save(output)
    report={'glbSHA256':digest,'node':node_name,'view':view,'dimensions':[W,H],
            'triangles':sum(len(p[0])for p in primitives),'renderedPixels':int(np.isfinite(zb).sum()),
            'scope':'Offline actual-asset material/UV review; no live campus context, selection or loading acceptance.'}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('glb');p.add_argument('output');p.add_argument('--node');p.add_argument('--view',nargs=3,type=float,default=[1,.6,1])
    a=p.parse_args();print(json.dumps(render(a.glb,a.output,a.node,view=a.view),indent=2))
