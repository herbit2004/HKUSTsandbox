#!/usr/bin/env python3
"""Extract embedded GLB without mesh edits and prepare a local Three.js manifest.
Usage: PYTHONPATH=/tmp/hkust-geometry-deps python3 convert_mesh.py --source /tmp/hkust-geodata --output /tmp/hkust-model-assets
Dependencies: numpy, pyproj. No network access is used by this conversion.
The consumer applies tile.matrix to the loaded GLTF scene (column-major).
"""
from pathlib import Path
import argparse,json,struct,hashlib,datetime,math,sys
import numpy as np
try: import pyproj
except ImportError:
 sys.path.insert(0,'/tmp/hkust-geometry-deps');import pyproj

P=argparse.ArgumentParser();P.add_argument('--source',default='/tmp/hkust-geodata');P.add_argument('--output',default='/tmp/hkust-model-assets');P.add_argument('--height-offset',type=float,default=0.0)
args=P.parse_args();src=Path(args.source).resolve();dst=Path(args.output).resolve();dst.mkdir(parents=True,exist_ok=True)
ORIGIN_E=844800.;ORIGIN_N=820500.
ecef2geo=pyproj.Transformer.from_crs(4978,4979,always_xy=True)
geo2hk=pyproj.Transformer.from_crs(4326,2326,always_xy=True)
def local(ecef):
 lon,lat,h=ecef2geo.transform(*np.asarray(ecef).T);e,n=geo2hk.transform(lon,lat)
 return np.array([np.asarray(e)-ORIGIN_E,np.asarray(h)+args.height_offset,ORIGIN_N-np.asarray(n)]).T

def localmatrix(M):
 p=M[:3,3];J=np.stack([(local(p+np.eye(3)[a])-local(p-np.eye(3)[a]))/2 for a in range(3)],axis=1)
 out=np.eye(4);out[:3,:3]=J@M[:3,:3];out[:3,3]=local(p);return out

I=np.eye(4);allrecords=[];missing=[];sources={};max_error=0.;allglbbytes=0
for folder in sorted((src/'mesh').iterdir()):
 if not folder.is_dir() or not (folder/'tileset.json').exists():continue
 source_manifest=folder/'subset-manifest.json'
 if source_manifest.exists():sources[folder.name]=json.loads(source_manifest.read_text())
 def scan(path,parent=I):
  d=json.loads(path.read_text())
  def walk(t,M):
   nonlocal_placeholder=None
   if 'transform' in t:M=M@np.array(t['transform']).reshape(4,4).T
   u=t.get('content',{}).get('uri',t.get('content',{}).get('url'))
   if u:
    q=(path.parent/u).resolve()
    if not q.exists():missing.append(str(q.relative_to(src)));return
    if q.suffix=='.json':scan(q,M)
    else:allrecords.append((q,M.copy(),t.get('boundingVolume')))
   for ch in t.get('children',[]):walk(ch,M)
  walk(d['root'],parent)
 scan(folder/'tileset.json')

records=[];validation=[];combinedmin=np.full(3,np.inf);combinedmax=np.full(3,-np.inf)
for path,M,source_volume in allrecords:
 b=path.read_bytes();source_hash=hashlib.sha256(b).hexdigest()
 if b[:4]==b'b3dm':
  h=struct.unpack_from('<4s6I',b);assert h[1]==1 and h[2]==len(b),str(path)
  start=28+sum(h[3:]);assert b[start:start+4]==b'glTF'
  glblen=struct.unpack_from('<I',b,start+8)[0];b=b[start:start+glblen]
 else:assert b[:4]==b'glTF'
 assert struct.unpack_from('<I',b,4)[0]==2 and struct.unpack_from('<I',b,8)[0]==len(b)
 jslen,tag=struct.unpack_from('<I4s',b,12);assert tag==b'JSON';d=json.loads(b[20:20+jslen]);binoffset=20+jslen+8
 assert b[20+jslen+4:20+jslen+8]==b'BIN\x00'
 for buf in d.get('buffers',[]):assert 'uri' not in buf
 for image in d.get('images',[]):assert 'uri' not in image
 # This source uses no glTF node transform. Refuse unsupported geometry instead of silently double-transforming.
 for node in d['nodes']:assert not any(k in node for k in ('translation','rotation','scale','matrix')),node
 L=localmatrix(M);vmin=np.full(3,np.inf);vmax=np.full(3,-np.inf);triangles=0;vertices=0;seen=set();errs=[]
 for mesh in d['meshes']:
  for pr in mesh['primitives']:
   assert pr.get('mode',4)==4
   triangles+=d['accessors'][pr['indices']]['count']//3 if 'indices' in pr else d['accessors'][pr['attributes']['POSITION']]['count']//3
   ai=pr['attributes']['POSITION']
   if ai in seen:continue
   seen.add(ai);a=d['accessors'][ai];v=d['bufferViews'][a['bufferView']];assert a['componentType']==5126 and a['type']=='VEC3'
   xyz=np.ndarray((a['count'],3),dtype='<f4',buffer=b,offset=binoffset+v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',12),4)).astype(float)
   transformed=xyz@L[:3,:3].T+L[:3,3]
   assert np.isfinite(transformed).all();vmin=np.minimum(vmin,transformed.min(axis=0));vmax=np.maximum(vmax,transformed.max(axis=0));vertices+=a['count']
   sample=xyz[::max(1,len(xyz)//32)];actual=local(sample@M[:3,:3].T+M[:3,3]);approx=sample@L[:3,:3].T+L[:3,3]
   errs.append(float(np.linalg.norm(actual-approx,axis=1).max()))
 max_error=max(max_error,max(errs,default=0.));combinedmin=np.minimum(combinedmin,vmin);combinedmax=np.maximum(combinedmax,vmax)
 relative=path.relative_to(src/'mesh').with_suffix('.glb');out=dst/'glb'/relative;out.parent.mkdir(parents=True,exist_ok=True)
 if not out.exists() or out.stat().st_size!=len(b):out.write_bytes(b)
 rec={'id':str(relative.with_suffix('')),'sheet':relative.parts[0],'url':str(Path('glb')/relative),'matrix':L.T.reshape(-1).tolist(),'bounds':{'min':vmin.tolist(),'max':vmax.tolist()},'center':((vmin+vmax)/2).tolist(),'triangles':triangles,'vertices':vertices,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'sourceB3dm':str(path.relative_to(src)),'sourceSha256':source_hash,'affineApproximationMaxErrorMeters':max(errs,default=0.)}
 records.append(rec);allglbbytes+=len(b)

manifest={'version':1,'generatedAt':'2026-09-05','coordinateSystem':{'horizontal':'Hong Kong 1980 Grid (EPSG:2326)','originE':ORIGIN_E,'originN':ORIGIN_N,'axes':'x=easting-originE; y=source geocentric height+heightOffsetMeters; z=originN-northing','heightOffsetMeters':args.height_offset,'heightDatum':'Source geocentric mesh height preserved. Absolute vertical datum of source mesh has not been confirmed. Do not describe these y coordinates as certified HKPD heights.','referenceTerrainDatum':'CEDD DTM uses Hong Kong Principal Datum (HKPD).','heightRegistrationEvidence':'Initial 582 coastal mesh samples at DTM 0-3 m: unshifted source height minus DTM median +0.110 m, 10th percentile -0.436 m. Mesh error, vegetation, surfaces and survey epoch differences remain. No unverified +2.371 m shift applied.','matrixConvention':'Column-major Three.js Matrix4; maps extracted raw GLTF scene into x-east, y-up, z-south. Do not additionally rotate glTF from Z-up or subtract the origin.','projection':'PROJ: WGS84 ECEF EPSG:4978 -> EPSG:4979; WGS84 longitude/latitude -> EPSG:2326 via inverse Hong Kong 1980 to WGS84 (1). First-order affine per source sub-tile, sampled against exact nonlinear conversion.'},'source':{'title':'Lands Department 3D Visualisation Map, Hong Kong SAR Government','metadata':'https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html','terms':'https://portal.csdi.gov.hk/csdi-webpage/doc/TNC','checkedAt':'2026-09-05','revisionDate':'2025-03-27','geometryCaptureDate':'Not established from the downloaded tiles; revision date is not a survey date.','credit':'3D Visualisation Map from Lands Department, Hong Kong SAR Government. Original data intellectual property belongs to the Government.','changes':'Selected source LOD frontier; extracted embedded GLB bytes without altering geometry or textures. Local affine placement is provided separately. Original 3D Tiles retains source ECEF transforms.'},'stats':{'tileCount':len(records),'glbBytes':allglbbytes,'triangles':sum(r['triangles'] for r in records),'vertices':sum(r['vertices'] for r in records),'bounds':{'min':combinedmin.tolist(),'max':combinedmax.tolist()},'maxAffineApproximationErrorMeters':max_error,'missingSourceAssets':len(missing)},'tiles':records,'sourceSheets':list(sources.values()),'missingSourceAssets':missing}
(dst/'render-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
report={'checkedAt':'2026-09-05','status':'complete' if not missing else 'partial-download','allB3dmHeadersValid':True,'allGlbHeadersValid':True,'allResourcesEmbedded':True,'allPositionsFinite':True,'allPrimitiveModesTriangles':True,'noUnsupportedNodeTransforms':True,'glbGeometryAndTextureBytesUnmodified':True,**manifest['stats'],'missing':missing}
(dst/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
