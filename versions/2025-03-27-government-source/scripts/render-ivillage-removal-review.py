#!/usr/bin/env python3
"""Show newly attributed original faces in red beside the actual four roots.

The diagnostic adds source faces only in an offline GLB, never the public model.
It shows source selection, not fragment clipping or a browser screenshot.
"""
import argparse
import io
import importlib.util
import json
import struct
from pathlib import Path
import numpy as np
from PIL import Image

P=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--source-colours',action='store_true')
ap.add_argument('--effective-only',action='store_true',help='show only source triangle centroids newly hidden by the final masks')
args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if args.output.resolve().is_relative_to((P/'public').resolve()):raise ValueError('Review output must remain outside public')
base=P/'public/models/current-forms/ivillage-rebuild'
raw=(base/'ivillage-x-xiii-v1.glb').read_bytes();n=struct.unpack_from('<I',raw,12)[0]
g=json.loads(raw[20:20+n]);b=bytearray(raw[28+n:])
source=np.load('/tmp/hkust-ivillage-rebuild-source/terminal-triangles.npz');T=source['positions']
added=[]
for hall in range(10,14):
    name=f'ug-hall-{hall}-replacement-witnesses.npz'
    old=np.load(base/'evidence'/name)['stagedTriangleIndex']
    new=np.load(args.candidate/'evidence'/name)['stagedTriangleIndex']
    added.extend(np.setdiff1d(new,old).tolist())
ids=np.unique(added)
if args.effective_only:
    def visible(folder, indices):
        manifest=json.loads((folder/'manifest.json').read_text());points=T[indices].mean(1);normals=source['normals'][indices]
        removed=np.zeros(len(indices),bool)
        for member in manifest['members']:
            d=member['mask'];pixels=np.asarray(Image.open(folder/d['url']).convert('RGBA'))
            col=np.floor((points[:,0]-d['boundsXZ']['min'][0])/d['pixelSizeMeters']).astype(int)
            row=np.floor((points[:,2]-d['boundsXZ']['min'][1])/d['pixelSizeMeters']).astype(int)
            inside=(row>=0)&(row<d['height'])&(col>=0)&(col<d['width'])
            q=np.zeros((len(indices),4),np.uint8);q[inside]=pixels[row[inside],col[inside]]
            lower=np.where(q[:,3]<255,np.maximum(d['replacementMinY'],q[:,3]),d['replacementMinY'])
            removed|=inside&(q[:,0]>127)&(points[:,1]>=lower)&(points[:,1]<=d['replacementMaxY'])
        p=manifest['sourceProtection'];payload=np.frombuffer((folder/p['url']).read_bytes(),np.uint8).reshape(p['height'],p['width'],4)
        col=np.floor((points[:,0]-p['boundsXZ']['min'][0])/p['pixelSizeMeters']).astype(int)
        row=np.floor((points[:,2]-p['boundsXZ']['min'][1])/p['pixelSizeMeters']).astype(int)
        inside=(row>=0)&(row<p['height'])&(col>=0)&(col<p['width']);q=np.zeros((len(indices),4),np.uint8);q[inside]=payload[row[inside],col[inside]]
        ground=q[:,0]+q[:,1]/256
        preserve=inside&(q[:,0]>0)&(abs(points[:,1]-ground)<=p['groundBandMeters'])&(abs(normals[:,1])>=.6)
        return ~(removed&~preserve)
    before=args.candidate/'evidence/before'
    keep=visible(before,ids)&~visible(args.candidate,ids)
    ids=ids[keep]
if not len(ids):raise ValueError('No diagnostic source faces selected')
pos=T[ids].reshape(-1,3).astype('<f4')
spec=importlib.util.spec_from_file_location('review_renderer',P/'scripts/render-photo-candidate.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
color_accessor=None
if args.source_colours:
    sources=json.loads(Path('/tmp/hkust-ivillage-rebuild-source/sources.json').read_text())['sources'];colors=np.ones((len(ids),3,3))
    for si in np.unique(source['sourceTileIndex'][ids]):
        meta=sources[int(si)];sg,sb,sha=module.read_glb(meta['localPath']);assert sha==meta['sha256']
        images=[]
        for item in sg.get('images',[]):
            view=sg['bufferViews'][item['bufferView']];offset=view.get('byteOffset',0)
            images.append(np.asarray(Image.open(io.BytesIO(sb[offset:offset+view['byteLength']])).convert('RGB'))/255)
        arrays=[]
        def visit(i):
            node=sg['nodes'][i]
            if 'mesh' in node:
                for pr in sg['meshes'][node['mesh']]['primitives']:
                    a=pr['attributes'];ix=module.access(sg,sb,pr['indices']).reshape(-1).astype(int) if 'indices' in pr else np.arange(sg['accessors'][a['POSITION']]['count'])
                    material=sg['materials'][pr.get('material',0)].get('pbrMetallicRoughness',{});factor=np.array(material.get('baseColorFactor',[1,1,1,1]))[:3]
                    c=np.broadcast_to(factor,(len(ix),3)).copy()
                    if 'baseColorTexture' in material:
                        texture=images[sg['textures'][material['baseColorTexture']['index']]['source']];uv=module.access(sg,sb,a['TEXCOORD_0'])[ix]
                        x=np.clip((uv[:,0]*texture.shape[1]).astype(int),0,texture.shape[1]-1);y=np.clip((uv[:,1]*texture.shape[0]).astype(int),0,texture.shape[0]-1)
                        srgb=texture[y,x];c*=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
                    arrays.append(c.reshape(-1,3,3))
            for child in node.get('children',[]):visit(child)
        for root in sg['scenes'][sg.get('scene',0)]['nodes']:visit(root)
        values=np.concatenate(arrays);where=np.flatnonzero(source['sourceTileIndex'][ids]==si)
        colors[where]=values[source['triangleIndex'][ids[where]]]
    c=colors.reshape(-1,3).astype('<f4');view=len(g['bufferViews']);g['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':c.nbytes,'target':34962});b+=c.tobytes()
    color_accessor=len(g['accessors']);g['accessors'].append({'bufferView':view,'componentType':5126,'count':len(c),'type':'VEC3'})
while len(b)%4:b+=b'\0'
vi=len(g['bufferViews']);g['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':pos.nbytes,'target':34962});b+=pos.tobytes()
ai=len(g['accessors']);g['accessors'].append({'bufferView':vi,'componentType':5126,'count':len(pos),'type':'VEC3','min':pos.min(0).tolist(),'max':pos.max(0).tolist()})
mi=len(g['materials']);g['materials'].append({'name':'DIAGNOSTIC newly attributed source faces','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1] if args.source_colours else [.65,.025,.015,1]},'doubleSided':True,'extensions':{'KHR_materials_unlit':{}}})
attributes={'POSITION':ai}
if color_accessor is not None:attributes['COLOR_0']=color_accessor
mesh=len(g['meshes']);g['meshes'].append({'primitives':[{'attributes':attributes,'material':mi}]})
node=len(g['nodes']);g['nodes'].append({'name':'DIAGNOSTIC source attribution only','mesh':mesh});g['scenes'][g.get('scene',0)]['nodes'].append(node)
g['buffers'][0]['byteLength']=len(b);j=json.dumps(g,separators=(',',':')).encode();j+=b' '*((-len(j))%4);b+=b'\0'*((-len(b))%4)
payload=struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\0')+b
path=args.output/'source-attribution-review.glb';path.write_bytes(payload)
for name,view in [('positive',(1,.6,1)),('negative',(-1,.6,-1)),('east',(1,.4,-.5))]:module.render(path,args.output/(name+'.png'),size=(1500,1050),view=view)
(args.output/'review.json').write_text(json.dumps({'displayedSourceTriangles':len(ids),'effectiveOnly':args.effective_only,'stagedTriangleIndices':ids.tolist(),'limitations':'Centroid sampling is an exact source reference but does not display partial triangle fragments, all LODs, or certify semantic ownership.'},indent=2)+'\n')
print(json.dumps({'newSourceTriangles':len(ids),'output':str(args.output)}))
