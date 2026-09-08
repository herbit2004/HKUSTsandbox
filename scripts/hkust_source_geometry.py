"""Read unmodified source GLB transforms, complete 3D Tiles frontiers and 0.5m DTM.
Used by bounded entrance derivation/QA scripts. No rendering geometry is invented.
"""
import json, struct, copy
import numpy as np
from PIL import Image

def geometry(path,placement=None):
 raw=path.read_bytes()
 if path.suffix=='.gltf':g=json.loads(raw);buffers=[(path.parent/b['uri']).read_bytes()for b in g['buffers']]
 else:
  n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);buffers=[raw[28+n:]]
 def accessor(i):
  a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]);k={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];return np.ndarray((a['count'],k),dtype=dtype,buffer=buffers[v.get('buffer',0)],offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dtype.itemsize*k),dtype.itemsize))
 out=[];mat=[]
 def walk(i,M):
  n=g['nodes'][i];assert not any(k in n for k in ['translation','rotation','scale']);m=M@np.array(n.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F')
  if'mesh'in n:
   for pr in g['meshes'][n['mesh']]['primitives']:
    pos=accessor(pr['attributes']['POSITION']).astype(float);world=pos@m[:3,:3].T+m[:3,3];idx=accessor(pr['indices']).ravel().astype(int)if'indices'in pr else np.arange(len(pos));out.append(world[idx.reshape(-1,3)]);mat.extend([pr.get('material',0)]*(len(idx)//3))
  for c in n.get('children',[]):walk(c,m)
 for i in g['scenes'][g.get('scene',0)]['nodes']:walk(i,np.eye(4)if placement is None else placement)
 return np.concatenate(out),np.array(mat)

def fix(n):
 if len(n.get('boundingVolume',{}).get('sphere',[]))==12:n['boundingVolume']['box']=n['boundingVolume'].pop('sphere')
 for c in n.get('children',[]):fix(c)

def select(root,sub,entries,threshold):
 issues=[]
 def walk(n):
  uri=n.get('content',{}).get('uri');name=sub+'/'+uri if uri else None;have=name in entries;ch=n.get('children',[])
  if have and (n.get('geometricError',0)<=threshold or not ch):
   n.pop('children',None);original_error=n.get('geometricError',0);n['geometricError']=0;return True,[{'source_name':name,'original_geometric_error':original_error}]
  out=[];complete=True
  for c in ch:
   ok,a=walk(c);complete &= ok;out+=a
  if not ch or not complete:
   if have:
    issues.append({'fallback':name,'original_geometric_error':n.get('geometricError',0)});n.pop('children',None);original_error=n.get('geometricError',0);n['geometricError']=0;return True,[{'source_name':name,'original_geometric_error':original_error}]
   issues.append({'missing':name});return False,[]
  n.pop('content',None);return True,out
 r=copy.deepcopy(root);ok,assets=walk(r);assert ok;fix(r);return r,assets,issues


class Heights:
 def __init__(self,paths):
  self.tiles=[]
  for path in paths:
   with Image.open(path)as im:self.tiles.append((np.asarray(im).copy(),im.tag_v2[33922][3:5]))
 def __call__(self,en):
  out=np.full(len(en),np.nan)
  for a,(e,n)in self.tiles:
   c=(en[:,0]-e)*2-.5;r=(n-en[:,1])*2-.5;ix=np.flatnonzero((c>=0)&(r>=0)&(c<a.shape[1]-1)&(r<a.shape[0]-1))
   if not len(ix):continue
   ci=c[ix].astype(int);ri=r[ix].astype(int);u=c[ix]-ci;v=r[ix]-ri;q=np.array([a[ri,ci],a[ri,ci+1],a[ri+1,ci],a[ri+1,ci+1]])
   valid=np.isfinite(q).all(0)&(q!=-9999).all(0);z=q[0]*(1-u)*(1-v)+q[1]*u*(1-v)+q[2]*(1-u)*v+q[3]*u*v;out[ix[valid]]=z[valid]
  return out
