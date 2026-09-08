"""Validate source-specific correction without a browser: --project PATH."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np

def decode(path):
 raw=path.read_bytes();n,k=struct.unpack_from('<II',raw,12);assert k==0x4e4f534a;g=json.loads(raw[20:20+n]);p=20+n;n,k=struct.unpack_from('<II',raw,p);assert k==0x004e4942;buf=raw[p+8:p+8+n]
 def acc(ai):
  a=g['accessors'][ai];v=g['bufferViews'][a['bufferView']];d=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]);w={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']];return np.ndarray((a['count'],w),d,buf,v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',w*d.itemsize),d.itemsize))
 attrs=[]
 for mesh in g['meshes']:
  for pr in mesh['primitives']:
   ix=acc(pr['indices']).reshape(-1,3);assert int(ix.max())<g['accessors'][pr['attributes']['POSITION']]['count'];attrs.append({key:acc(ai)[ix]for key,ai in pr['attributes'].items()})
 images=[]
 for im in g['images']:
  v=g['bufferViews'][im['bufferView']];images.append(hashlib.sha256(buf[v['byteOffset']:v['byteOffset']+v['byteLength']]).hexdigest())
 return g,attrs,images

def validate(project):
 base=Path(__file__).resolve().parent;manifest=json.loads((base/'manifest.json').read_text());src=project/'public/models'/manifest['sourcePreview']['url'];dst=project/'public/models'/manifest['correctedPreview']['url'];a,aa,ai=decode(src);b,bb,bi=decode(dst)
 removed=list(range(6548,6557));checks={}
 for key in ['POSITION','TEXCOORD_0']:
  original=np.concatenate([x[key]for x in aa]);corrected=np.concatenate([x[key]for x in bb]);expected=np.delete(original,removed,axis=0);assert np.array_equal(expected,corrected);checks[key+'ExactRetainedTriangleEquality']=True
 assert a['nodes']==b['nodes']and a['scenes']==b['scenes'];assert a['materials']==b['materials']and a['textures']==b['textures'];assert ai==bi
 assert hashlib.sha256(src.read_bytes()).hexdigest()==manifest['sourcePreview']['sha256'];assert hashlib.sha256(dst.read_bytes()).hexdigest()==manifest['correctedPreview']['sha256']
 t=next(x for x in json.loads((project/'public/models/preview-manifest.json').read_text())['tiles']if x['id']==manifest['tileId']);assert t==manifest['correctedPreview']
 return {'pass':True,'trianglesBefore':sum(len(x['POSITION'])for x in aa),'trianglesAfter':sum(len(x['POSITION'])for x in bb),'removedTriangles':9,**checks,'imagesByteEquivalent':True,'materialsNodesTransformsUnchanged':True,'manifestHashAndTileBinding':True}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[4]);parser.add_argument('--output',type=Path);args=parser.parse_args();result=validate(args.project);out=json.dumps(result,indent=2)+'\n';print(out,end='')
 if args.output:args.output.write_text(out)
