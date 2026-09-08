#!/usr/bin/env python3
"""Render original 3D geometry to a diagnostic orthographic image, without invented geometry.
Per-triangle texture centroid sampling is only a diagnostic simplification.
"""
from pathlib import Path
import numpy as np,json,struct,io,cv2
from PIL import Image,ImageDraw,ImageFont
R=Path(__file__).resolve().parent;manifest=json.loads((R/'preview-manifest.json').read_text());allvertices=[];allcolors=[]
def accessor(d,b,bo,i):
 a=d['accessors'][i];v=d['bufferViews'][a['bufferView']];typ={5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']];n={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']]
 return np.ndarray((a['count'],n),dtype=typ,buffer=b,offset=bo+v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',np.dtype(typ).itemsize*n),np.dtype(typ).itemsize))
for tile in manifest['tiles']:
 b=(R/tile['url']).read_bytes();n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);bo=20+n+8;M=np.array(tile['matrix']).reshape(4,4).T;textures=[]
 for im in d['images']:
  v=d['bufferViews'][im['bufferView']];o=bo+v.get('byteOffset',0);textures.append(np.array(Image.open(io.BytesIO(b[o:o+v['byteLength']])).convert('RGB')))
 for mesh in d['meshes']:
  for p in mesh['primitives']:
   xyz=accessor(d,b,bo,p['attributes']['POSITION']);pos=xyz@M[:3,:3].T+M[:3,3];indices=accessor(d,b,bo,p['indices']).reshape(-1,3);faces=pos[indices];uv=accessor(d,b,bo,p['attributes']['TEXCOORD_0'])[indices].mean(axis=1);t=d['materials'][p['material']]['pbrMetallicRoughness']['baseColorTexture']['index'];im=textures[d['textures'][t]['source']];uu=np.clip((uv[:,0]*im.shape[1]).astype(int),0,im.shape[1]-1);vv=np.clip((uv[:,1]*im.shape[0]).astype(int),0,im.shape[0]-1);color=im[vv,uu];allvertices.append(faces.astype('f4'));allcolors.append(color)
V=np.concatenate(allvertices);C=np.concatenate(allcolors);print('Loaded triangles',len(V),flush=True)
def render(name,mode):
 if mode=='top':
  coords=V[:,:,[0,2]];depth=V[:,:,1].mean(axis=1)
 else:
  cam=np.array([1500.,1500.,500.]);target=np.array([500.,70.,-1400.]);forward=(target-cam);forward/=np.linalg.norm(forward);right=np.cross(forward,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,forward);coords=np.stack([V@right,-V@up],axis=-1);depth=-(V@forward).mean(axis=1)
 lo=coords.min(axis=(0,1));hi=coords.max(axis=(0,1));wh=hi-lo;scale=min(2100/wh[0],1500/wh[1]);width=int(wh[0]*scale)+80;height=int(wh[1]*scale)+110;pix=np.rint((coords-lo)*scale+np.array([40,65])).astype('int32');canvas=np.full((height,width,3),[207,224,229],dtype='uint8')
 for i in np.argsort(depth):cv2.fillConvexPoly(canvas,pix[i],tuple(int(x) for x in C[i]))
 out=Image.fromarray(canvas);draw=ImageDraw.Draw(out);draw.text((24,15),'HKUST Clear Water Bay | Lands Department photogrammetric mesh | source revision 2025-03-27',fill=(25,37,47));draw.text((24,34),'Geometry diagnostic: triangle-centroid texture sampling. Buildings and terrain are from source mesh, not invented.',fill=(25,37,47));out.save(R/name);print(name,out.size,flush=True)
render('diagnostic-topdown.png','top');render('diagnostic-oblique.png','oblique')
