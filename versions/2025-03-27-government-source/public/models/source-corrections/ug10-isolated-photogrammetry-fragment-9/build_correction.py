"""Reproducible source-specific index correction. Never selects by height/AABB."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
TILE='12-NW-11A/12-NW-11A-3/Tile_302_143_L16_0'
SOURCE_SHA='eb0a2c37da99bfb3d8e788e3928552c6b295230dc60e9c6b4eba0bf335a60d9c'
REMOVE_GLOBAL=list(range(6548,6557))
DT={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'};W={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
def build(src,dest):
 raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'Source preview changed: re-audit indices.'
 length,kind=struct.unpack_from('<II',raw,12);assert kind==0x4e4f534a;g=json.loads(raw[20:20+length]);off=20+length;n,k=struct.unpack_from('<II',raw,off);assert k==0x004e4942;data=raw[off+8:off+8+n]
 views=[data[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]for v in g['bufferViews']]
 def arr(ai):
  a=g['accessors'][ai];v=g['bufferViews'][a['bufferView']];dt=np.dtype(DT[a['componentType']]);w=W[a['type']]
  return np.ndarray((a['count'],w),dt,views[a['bufferView']],a.get('byteOffset',0),strides=(v.get('byteStride',w*dt.itemsize),dt.itemsize)).copy()
 def replace(ai,x):
  a=g['accessors'][ai];v=g['bufferViews'][a['bufferView']];assert not a.get('byteOffset',0) and not v.get('byteStride');assert sum(z['bufferView']==a['bufferView']for z in g['accessors'])==1
  views[a['bufferView']]=x.tobytes();a['count']=len(x);a['min']=x.min(0).astype(float).tolist();a['max']=x.max(0).astype(float).tolist()
 start=0;removed=0;discardedvertices=0
 for mesh in g['meshes']:
  for pr in mesh['primitives']:
   ix=arr(pr['indices']).reshape(-1,3);local=[i-start for i in REMOVE_GLOBAL if start<=i<start+len(ix)];start+=len(ix)
   if not local:continue
   kept=np.delete(ix,local,axis=0);used=np.unique(kept);remap=np.zeros(int(ix.max())+1,dtype=ix.dtype);remap[used]=np.arange(len(used),dtype=ix.dtype);kept=remap[kept]
   for key,ai in pr['attributes'].items():
    old=arr(ai)
    if key=='POSITION':discardedvertices+=len(old)-len(used)
    replace(ai,old[used])
   replace(pr['indices'],kept.reshape(-1,1));removed+=len(local)
 assert removed==9
 newbin=bytearray()
 for v,b in zip(g['bufferViews'],views):
  newbin.extend(b'\0'*(-len(newbin)%4));v['byteOffset']=len(newbin);v['byteLength']=len(b);newbin.extend(b)
 g['buffers'][0]['byteLength']=len(newbin);newbin.extend(b'\0'*(-len(newbin)%4))
 g['asset'].setdefault('extras',{})['sourceCorrection']={'id':'ug10-isolated-photogrammetry-fragment-9','sourcePreviewSha256':SOURCE_SHA,'removedSourceGlobalTriangleIndices':REMOVE_GLOBAL,'scope':'Only positively identified disconnected source fragment. No roof/height-based blanket removal.'}
 js=json.dumps(g,separators=(',',':')).encode();js+=b' '*(-len(js)%4);out=struct.pack('<III',0x46546c67,2,12+8+len(js)+8+len(newbin))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(newbin),0x004e4942)+newbin
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(out)
 return {'tileId':TILE,'sourcePreviewSha256':SOURCE_SHA,'sha256':hashlib.sha256(out).hexdigest(),'bytes':len(out),'trianglesRemoved':removed,'verticesRemoved':discardedvertices,'triangles':start-removed}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('output',type=Path);a=p.parse_args();result=build(a.project/'public/models/preview-glb'/f'{TILE}.glb',a.output);print(json.dumps(result,indent=2))
