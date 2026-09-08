#!/usr/bin/env python3
"""Independently decode every GLB and compare its vertices to source TIFFs."""
from pathlib import Path
import argparse,json,struct,hashlib
import numpy as np
from PIL import Image

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--baseline',type=Path,required=True);a=ap.parse_args();m=json.load(open(a.output/'manifest.json'));b=m['sourceGridBounds'];w=int((b['east']-b['west'])*2);h=int((b['north']-b['south'])*2);raster=np.full((h,w),-9999,dtype=np.float32)
 for s in m['sources']:
  p=a.source/s['file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256']
  with Image.open(p)as im:
   x,y=im.tag_v2[33922][3:5];r=int((b['north']-y)*2);c=int((x-b['west'])*2);arr=np.asarray(im);raster[r:r+arr.shape[0],c:c+arr.shape[1]]=arr
 valid=(raster!=-9999).reshape(h//2,2,w//2,2).all((1,3));cell=valid[:-1,:-1]&valid[:-1,1:]&valid[1:,:-1]&valid[1:,1:]
 seams={};compared=0;max_normal_delta=0.;max_height_delta=0.;vertex_count=0;triangle_count=0;details=[]
 for t in m['tiles']:
  p=a.output/t['url'];raw=p.read_bytes();magic,version,total=struct.unpack_from('<4sII',raw);assert(magic,version,total)==(b'glTF',2,len(raw));assert len(raw)==t['bytes'];assert hashlib.sha256(raw).hexdigest()==t['sha256']
  jl,jt=struct.unpack_from('<I4s',raw,12);assert jt==b'JSON';j=json.loads(raw[20:20+jl]);bl,bt=struct.unpack_from('<I4s',raw,20+jl);assert bt==b'BIN\x00';binary=raw[28+jl:];assert len(binary)==bl
  def accessor(i):
   ac=j['accessors'][i];v=j['bufferViews'][ac['bufferView']];dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[ac['componentType']];a=np.frombuffer(binary[v['byteOffset']:v['byteOffset']+v['byteLength']],dtype=dtype);return a.reshape(-1,3)if ac['type']=='VEC3'else a
  primitive=j['meshes'][0]['primitives'][0];xyz=accessor(primitive['attributes']['POSITION']);normal=accessor(primitive['attributes']['NORMAL']);ix=accessor(primitive['indices']).reshape(-1,3)
  assert len(xyz)==t['vertices']and len(ix)==t['triangles'];assert np.isfinite(xyz).all()and np.isfinite(normal).all();assert ix.max()<len(xyz)
  E=xyz[:,0].astype(float)+844800;N=820500-xyz[:,2].astype(float);c=np.rint((E-b['west'])*2-.5).astype(int);r=np.rint((b['north']-N)*2-.5).astype(int)
  assert((r%2==1)&(c%2==1)).all();assert np.array_equal(xyz[:,1],raster[r,c]);assert(valid[(r-1)//2,(c-1)//2]).all()
  fr=((r[ix].min(1)-1)//2);fc=((c[ix].min(1)-1)//2);assert cell[fr,fc].all()
  fn=np.cross(xyz[ix[:,1]]-xyz[ix[:,0]],xyz[ix[:,2]]-xyz[ix[:,0]]);assert(fn[:,1]>0).all()
  sb=t['sourceGridNodeBounds'];g=t['gridBBox'];actual=[b['west']+.75+sb['colStart'],b['west']+.75+sb['colEndInclusive'],b['north']-.75-sb['rowStart'],b['north']-.75-sb['rowEndInclusive']];assert actual==[g['west'],g['east'],g['north'],g['south']]
  assert t['bounds']['min'][0]==g['west']-844800 and t['bounds']['max'][0]==g['east']-844800 and t['bounds']['min'][2]==820500-g['north'] and t['bounds']['max'][2]==820500-g['south']
  edge=((r-1)//2==sb['rowStart'])|((r-1)//2==sb['rowEndInclusive'])|((c-1)//2==sb['colStart'])|((c-1)//2==sb['colEndInclusive'])
  for k in np.flatnonzero(edge):
   key=(int(r[k]),int(c[k]));val=(xyz[k].copy(),normal[k].copy())
   if key in seams:
    prev=seams[key];assert np.array_equal(val[0],prev[0]);delta=float(abs(val[1]-prev[1]).max());assert delta<1e-6;max_normal_delta=max(max_normal_delta,delta);compared+=1
   else:seams[key]=val
  vertex_count+=len(xyz);triangle_count+=len(ix);details.append({'tile':t['id'],'verticesComparedExactlyToSource':len(xyz),'sourceSupportedTriangles':len(ix),'gridBoundsVerified':True})
 old=json.load(open(a.baseline/'terrain-manifest.json'));baseline_sha=hashlib.sha256((a.baseline/'terrain.glb').read_bytes()).hexdigest();assert baseline_sha==old['assets']['terrain.glb']['sha256']
 out={'checkedAt':'2026-09-05','glbFilesDecoded':len(details),'allGlbHeadersChunksAndHashesValid':True,'verticesComparedExactlyToOriginalFloat32Source':vertex_count,'maxExportedVertexHeightErrorMeters':0,'allTrianglesUseFullySourceSupportedCells':True,'trianglesVerified':triangle_count,'allTriangleNormalsUpward':True,'allManifestBoundsUseActualFullGridRectangle':True,'sharedSeamVertexPairsCompared':compared,'maxSeamPositionDifferenceMeters':0,'maxSeamNormalComponentDifference':max_normal_delta,'original5mGlbMatchesRecordedSourceSHA256':True,'original5mGlbSHA256':baseline_sha,'tiles':details}
 (a.output/'independent-qa.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items()if k!='tiles'},indent=2))
if __name__=='__main__':main()
