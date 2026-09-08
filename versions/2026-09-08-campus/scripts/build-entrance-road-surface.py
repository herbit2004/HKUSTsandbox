#!/usr/bin/env python3
"""Clip actual finest available photographic ground triangles to proven entrance domains.

The plaza retains the previously verified DTM mesh. Road geometry retains original
photography Y; orthophoto UV is derived from EPSG2326. No projected roof is used.
"""
import argparse,json,struct,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import Polygon,GeometryCollection,polygons,intersection,area,constrained_delaunay_triangles
from shapely.ops import unary_union
from rasterio.features import rasterize
from affine import Affine
from hkust_source_geometry import geometry,Heights

ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--base-surface',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();P=args.project;B=args.base_surface;D=args.output;D.mkdir(parents=True,exist_ok=True)
m=json.loads((B/'manifest.json').read_text());sources=json.loads((B/'source-domains.json').read_text())
raw=(B/m['url']).read_bytes();jl=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+jl]);binary=raw[28+jl:]
def acc(i):
 a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];dtype={5126:'<f4',5125:'<u4'}[a['componentType']];k={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']]
 return np.frombuffer(binary,dtype=dtype,count=a['count']*k,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,k)
positions=acc(0).astype(float)
plaza_tri=positions[acc(g['meshes'][0]['primitives'][0]['indices']).reshape(-1,3)]
base_road=positions[acc(g['meshes'][1]['primitives'][0]['indices']).reshape(-1,3)]
# Exact already-filtered official road domain, not a buffer around a centreline.
road_domain=unary_union(polygons(base_road[:,:,[0,2]]))
dtm=Heights(list((P/'public/terrain/source-data').glob('*.tif')))
patches={p['id']:p for p in json.loads((P/'public/models/hires/manifest.json').read_text())['patches']}
for path in sorted([*(P/'public/models/hires').glob('partial-*/manifest.json'),*(P/'public/models/hires').glob('terminal/*/manifest.json')]):
 for patch in json.loads(path.read_text())['patches']:patches[patch['id']]=patch
tiles=[]
for patch in patches.values():
 level_name='fine' if 'fine' in patch['levels'] else 'high';level=patch['levels'][level_name]
 source_tree=P/'public/models/hires/sources'/patch['id']/'source-tileset.json';errors={}
 if source_tree.exists():
  def visit(node):
   uri=node.get('content',{}).get('uri')
   if uri:errors[uri.removesuffix('.b3dm')]=node.get('geometricError',0)
   for child in node.get('children',[]):visit(child)
  visit(json.load(open(source_tree))['root'])
 for t in level['tiles']:
  lo_x,lo_z,hi_x,hi_z=road_domain.bounds;bounds=t['bounds']
  if bounds['max'][0]<lo_x or bounds['min'][0]>hi_x or bounds['max'][2]<lo_z or bounds['min'][2]>hi_z:continue
  error=t.get('originalError',errors.get(t['id'].split('/')[-1]));assert error is not None
  tiles.append({**t,'selectedLevel':level_name,'sourceGeometricError':error,'patchId':patch['id']})
# Only one retained frontier per patch. Across their real projection overlap,
# lower original source error wins; stable source ID breaks equal-error ties.
tiles.sort(key=lambda t:(t['sourceGeometricError'],t['id']))
triangles=[];origins=[];used=[];minimum_normal=.6;band=1.5;claimed=GeometryCollection()
for tile in tiles:
 b=tile['bounds'];x0,z0,x1,z1=road_domain.bounds
 if b['max'][0]<x0 or b['min'][0]>x1 or b['max'][2]<z0 or b['min'][2]>z1:continue
 path=P/'public/models/hires'/tile['url'];tr,_=geometry(path,np.array(tile['matrix']).reshape(4,4,order='F'))
 cr=np.cross(tr[:,1]-tr[:,0],tr[:,2]-tr[:,0]);norm=np.linalg.norm(cr,axis=1)
 slope=(norm>1e-8)&(abs(cr[:,1])>=minimum_normal*norm)
 ix=np.flatnonzero(slope);candidate=tr[ix]
 q=candidate.reshape(-1,3);dh=dtm(np.c_[q[:,0]+844800,820500-q[:,2]]).reshape(-1,3)
 close=np.isfinite(dh).all(1)&(abs(candidate[:,:,1]-dh)<=band).all(1);ix=ix[close];candidate=candidate[close]
 if not len(ix):continue
 clipped=intersection(polygons(candidate[:,:,[0,2]]),road_domain.difference(claimed))
 keep=np.flatnonzero(area(clipped)>1e-8)
 if not len(keep):continue
 tid=len(used);start=len(triangles)
 for k in keep:
  source=candidate[k];n=np.cross(source[1]-source[0],source[2]-source[0]);pieces=constrained_delaunay_triangles(clipped[k])
  for polygon in pieces.geoms:
   xz=np.asarray(polygon.exterior.coords)[:3]
   y=source[0,1]-(n[0]*(xz[:,0]-source[0,0])+n[2]*(xz[:,1]-source[0,2]))/n[1]
   tri=np.c_[xz[:,0],y,xz[:,1]]
   if np.cross(tri[1]-tri[0],tri[2]-tri[0])[1]<0:tri=tri[[0,2,1]]
   triangles.append(tri);origins.append([tid,int(ix[k])])
 claimed=unary_union([claimed,unary_union(polygons(np.array(triangles[start:])[:,:,[0,2]]))])
 used.append({'id':tile['id'],'url':tile['url'],'matrix':tile['matrix'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'originalTriangleCount':len(tr),'generatedTriangles':len(triangles)-start,'selectedLevel':tile['selectedLevel'],'patchId':tile['patchId'],'sourceGeometricError':tile['sourceGeometricError']})
road_tri=np.array(triangles);assert len(road_tri)>1000
# Keep each clipped triangle's original plane; no height blending at source edges.
all_tri=np.concatenate([plaza_tri,road_tri]);pos,indices=np.unique(all_tri.reshape(-1,3).astype('<f4'),axis=0,return_inverse=True);indices=indices.reshape(-1,3).astype('<u4')
face_norm=np.cross(all_tri[:,1]-all_tri[:,0],all_tri[:,2]-all_tri[:,0]);norm=np.zeros_like(pos)
for corner in range(3):np.add.at(norm,indices[:,corner],face_norm)
norm/=np.maximum(np.linalg.norm(norm,axis=1,keepdims=True),1e-12)
e0,n0,e1,n1=m['texture']['boundsEN'];uv=np.c_[(pos[:,0].astype(float)+844800-e0)/(e1-e0),(n1-820500+pos[:,2].astype(float))/(n1-n0)].astype('<f4')
arrays=[pos,norm,uv,indices[:len(plaza_tri)].ravel(),indices[len(plaza_tri):].ravel()];out=bytearray();views=[];accessors=[]
for i,a in enumerate(arrays):
 out.extend(b'\0'*(-len(out)%4));views.append({'buffer':0,'byteOffset':len(out),'byteLength':a.nbytes,'target':34963 if i>=3 else 34962});out.extend(a.tobytes());accessors.append({'bufferView':i,'componentType':5125 if i>=3 else 5126,'count':len(a),'type':['VEC3','VEC3','VEC2','SCALAR','SCALAR'][i]})
accessors[0].update(min=pos.min(0).tolist(),max=pos.max(0).tolist())
g['accessors']=accessors;g['bufferViews']=views;g['buffers']=[{'byteLength':len(out)}]
g['nodes'][1]['extras']['geometry']='Actual source photography ground triangle planes clipped inside previously verified official entrance ground domains; no Y offset or generated profile.'
g['nodes'][1]['extras']['heightDatum']='Source photography local transform; not independently certified HKPD. Compared with original DTM within1.5m at all source triangle vertices.'
g['extras']['geometry']='Plaza: measured0.5m DTM. Approach: actual finest-available photographic source triangle planes.'
g['asset']['generator']='build-entrance-road-surface.py'
js=json.dumps(g,separators=(',',':')).encode();js+=b' '*(-len(js)%4);out.extend(b'\0'*(-len(out)%4));(D/m['url']).write_bytes(struct.pack('<4sII',b'glTF',2,28+len(js)+len(out))+struct.pack('<I4s',len(js),b'JSON')+js+struct.pack('<I4s',len(out),b'BIN\0')+out)
for name in [m['texture']['url'],'entrance-tdop-20250111.pgw','source-domains.json']:shutil.copy2(B/name,D/name)
h,w=m['texture']['height'],m['texture']['width'];res=m['mask']['pixelSizeMeters'];minx,minz=m['mask']['minX'],m['mask']['minZ']
mask=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in all_tri[:,:,[0,2]]),out_shape=(h,w),transform=Affine(res,0,minx,0,res,minz),dtype='uint8')
rr,cc=np.indices((h,w));en=np.c_[e0+(cc.ravel()+.5)*res,n1-(rr.ravel()+.5)*res];height=dtm(en).reshape(h,w);valid=(mask>0)&np.isfinite(height);enc=np.floor(np.where(valid,height,0)*256).astype('uint16');rgba=np.dstack([np.where(valid,255,0),enc//256,enc%256,np.full((h,w),255)]).astype('uint8');Image.fromarray(rgba).save(D/m['mask']['url'])
for i,tr in enumerate([plaza_tri,road_tri]):
 low=tr.min((0,1));high=tr.max((0,1));m['features'][i]['meshBounds']={'min':low.tolist(),'max':high.tolist()};m['features'][i]['center']=((low+high)/2).tolist();m['features'][i]['triangles']=len(tr);m['features'][i]['vertices']=len(np.unique(indices[:len(plaza_tri)] if i==0 else indices[len(plaza_tri):]))
m['features'][1].update(g['nodes'][1]['extras']);m['source']['geometry']='Entrance plaza: original CEDD0.5m DTM2019–2020 in HKPD. Approach: actual retained finest-frontier photography ground triangle planes, original local sourceY (not independently certified HKPD).';m['source']['roadGeometry']=g['nodes'][1]['extras']['geometry'];m['source']['roadHeightDatum']=g['nodes'][1]['extras']['heightDatum'];m['source']['groundDomainSupportSources']=m['source'].pop('photoSources',[]);m['source']['roadPhotoSources']=used;m['source']['roadSourcePriority']='One finest retained complete frontier per patch; never baselineL16. Smaller original geometricError has priority in overlapping source projections. Equal error uses stable sourceID. Lower-priority tile is clipped to the remaining actual ground projection, never to a bbox.';m['bytes']=(D/m['url']).stat().st_size
m['limitations'].append('Approach ground now retains actual clipped source photography Y; plaza retains DTM. Epoch/datum differences remain visible at their boundary and are not artificially blended.')
source_index=np.array(origins,dtype='<u4');source_index.tofile(D/'road-source-face-index.bin')
projection=unary_union(polygons(road_tri[:,:,[0,2]]));
def domain_parts(geom):
 return [{'rings':[list(map(list,ring.coords))for ring in [p.exterior,*p.interiors]]}for p in ([geom]if geom.geom_type=='Polygon'else geom.geoms)]
sources['groundInputDomainLocalXZ']=sources['generatedDomainLocalXZ'];sources['generatedRoadDomainLocalXZ']=domain_parts(projection);sources['generatedDomainLocalXZ']=domain_parts(unary_union([projection,unary_union(polygons(plaza_tri[:,:,[0,2]]))]));(D/'source-domains.json').write_text(json.dumps(sources,separators=(',',':')))
q=road_tri.reshape(-1,3);dy=q[:,1]-dtm(np.c_[q[:,0]+844800,820500-q[:,2]])
qa={'status':'generated-needs-independent-check','plazaTriangles':len(plaza_tri),'roadTriangles':len(road_tri),'originalGroundRoadAreaM2':road_domain.area,'newSourceGroundProjectionAreaM2':projection.area,'sourceCoveredRoadDomainPercent':projection.area/road_domain.area*100,'uncoveredSourceRoadDomainAreaM2':road_domain.difference(projection).area,'sourceFaceRecords':len(origins),'sourcePhotoMinusDTM':{'min':float(np.nanmin(dy)),'median':float(np.nanmedian(dy)),'max':float(np.nanmax(dy))},'roadSourceTriangleSlopeThreshold':minimum_normal,'sourceTriangleVertexBandMeters':band,'trueClippedSourceTriangles':True,'unboundRoadEntityId':True,'sourceYNotOffset':True}
(D/'road-source-clipping.json').write_text(json.dumps({'sourceTiles':used,'indexUrl':'road-source-face-index.bin','indexEncoding':'little-endian uint32 pairs: source tile index, original triangle index; one pair per road triangle','qa':qa},indent=2));m['qa']=qa;(D/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));(D/'qa.json').write_text(json.dumps(qa,indent=2));print(json.dumps(qa,indent=2))
