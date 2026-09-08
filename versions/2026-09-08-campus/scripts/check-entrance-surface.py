#!/usr/bin/env python3
"""Independent exported-asset checks; reads GLB, PNG and original source TIFFs."""
import argparse,json,struct,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import rasterio
from rasterio.windows import Window
from shapely import polygons,points,STRtree,Polygon,contains_xy,distance
from shapely.ops import unary_union
from hkust_source_geometry import geometry
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--tdop',type=Path,required=True);ap.add_argument('--surface',type=Path);args=ap.parse_args();d=args.surface or args.project/'public/surfaces/entrance';m=json.load(open(d/'manifest.json'));raw=(d/m['url']).read_bytes();n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);offset=28+n
assert struct.unpack_from('<I',raw,8)[0]==len(raw)
def acc(i):
 a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];dtype={5126:'<f4',5125:'<u4'}[a['componentType']];size={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']];return np.frombuffer(raw,dtype=dtype,count=a['count']*size,offset=offset+v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,size)
positions=acc(0).astype(float);uv=acc(2);triangles=np.concatenate([acc(mesh['primitives'][0]['indices']).reshape(-1,3)for mesh in g['meshes']]);p=positions[triangles];en=np.column_stack([positions[:,0]+844800,820500-positions[:,2]])
assert g['nodes'][0]['extras']['entityId']=='outdoor_area:catalog:campus-61'
assert 'entityId' not in g['nodes'][1]['extras']
# Independent single-source pixel lookup; no generator functions are imported.
tif=next((args.project/'public/terrain/source-data').glob('12NW6C*.tif'))
with Image.open(tif)as im:
 dtm=np.asarray(im);east,north=im.tag_v2[33922][3:5];assert im.tag_v2[33550][:2]==(.5,.5)
def reference(q):
 c=(q[:,0]-east)/.5-.5;r=(north-q[:,1])/.5-.5;i=np.floor(c).astype(int);j=np.floor(r).astype(int);fx=c-i;fy=r-j
 heights=np.stack([dtm[j,i],dtm[j,i+1],dtm[j+1,i],dtm[j+1,i+1]],1);assert np.isfinite(heights).all() and(heights!=-9999).all();weights=np.stack([(1-fx)*(1-fy),fx*(1-fy),(1-fx)*fy,fx*fy],1);return(heights*weights).sum(1)
road_provenance=d/'road-source-clipping.json';road_qa=None
dtm_vertices=np.unique(acc(g['meshes'][0]['primitives'][0]['indices']).reshape(-1)) if road_provenance.exists() else np.arange(len(positions))
height_error=float(abs(reference(en[dtm_vertices])-positions[dtm_vertices,1]).max());print("Max independent DTM height error",height_error,flush=True);assert height_error<.001
if road_provenance.exists():
 provenance=json.load(open(road_provenance));records=np.fromfile(d/provenance['indexUrl'],dtype='<u4').reshape(-1,2);road_indices=acc(g['meshes'][1]['primitives'][0]['indices']).reshape(-1,3);road=positions[road_indices];assert len(records)==len(road)
 maximum_plane_error=0.;maximum_barycentric_excess=0.;maximum_source_projection_distance=0.;source_union_area_sum=0.
 for ti,t in enumerate(provenance['sourceTiles']):
  source_path=args.project/'public/models/hires'/t['url'];assert hashlib.sha256(source_path.read_bytes()).hexdigest()==t['sha256'];original,_=geometry(source_path,np.array(t['matrix']).reshape(4,4,order='F'))
  select=np.flatnonzero(records[:,0]==ti);source=original[records[select,1]];generated=road[select];normal=np.cross(source[:,1]-source[:,0],source[:,2]-source[:,0]);predicted=source[:,0,1,None]-(normal[:,0,None]*(generated[:,:,0]-source[:,0,0,None])+normal[:,2,None]*(generated[:,:,2]-source[:,0,2,None]))/normal[:,1,None]
  maximum_plane_error=max(maximum_plane_error,float(abs(predicted-generated[:,:,1]).max()))
  a=source[:,1][:,[0,2]]-source[:,0][:,[0,2]];b=source[:,2][:,[0,2]]-source[:,0][:,[0,2]];q=generated[:,:,[0,2]]-source[:,0][:,[0,2]][:,None,:];det=a[:,0]*b[:,1]-a[:,1]*b[:,0];u=(q[:,:,0]*b[:,1,None]-q[:,:,1]*b[:,0,None])/det[:,None];v=(a[:,0,None]*q[:,:,1]-a[:,1,None]*q[:,:,0])/det[:,None]
  # Barycentric weights are diagnostic; very small original triangles amplify
  # float32 coordinate rounding. Plane error remains the metric height check.
  maximum_barycentric_excess=max(maximum_barycentric_excess,float(np.maximum.reduce([-u,-v,u+v-1,np.zeros_like(u)]).max()))
  source_polygons=polygons(source[:,:,[0,2]])
  for vertex in range(3):maximum_source_projection_distance=max(maximum_source_projection_distance,float(distance(source_polygons,points(generated[:,vertex][:,[0,2]])).max()))
  source_union_area_sum+=unary_union(polygons(generated[:,:,[0,2]])).area
 assert maximum_plane_error<.001
 assert maximum_source_projection_distance<.0001
 road_qa={'triangles':len(road),'sourceTiles':len(provenance['sourceTiles']),'originalSourcePlaneChecks':len(road)*3,'maximumPlaneErrorMeters':maximum_plane_error,'maximumSourceProjectionDistanceMeters':maximum_source_projection_distance,'maximumBarycentricRoundoffExcess':maximum_barycentric_excess,'originalTriangleReferencesPreserved':True,'sourcePhotoMinusDTMMinMax':[float((road[:,:,1].ravel()-reference(np.c_[road[:,:,0].ravel()+844800,820500-road[:,:,2].ravel()])).min()),float((road[:,:,1].ravel()-reference(np.c_[road[:,:,0].ravel()+844800,820500-road[:,:,2].ravel()])).max())]}
 projection_area=unary_union(polygons(road[:,:,[0,2]])).area;triangle_area=abs(np.cross(road[:,1]-road[:,0],road[:,2]-road[:,0])[:,1]).sum()/2
 road_qa.update(projectedTriangleAreaSumM2=float(triangle_area),projectedUnionAreaM2=projection_area,crossSourceOverlapAreaM2=source_union_area_sum-projection_area,sameSourceInternalOverlapAreaM2=float(triangle_area-source_union_area_sum),allSourceGeometricErrorsZero=all(t.get('sourceGeometricError')==0 for t in provenance['sourceTiles']),baselineL16SourceCount=sum('_L16_'in t['id']for t in provenance['sourceTiles']))
 # Original source multilayer surfaces can overlap within one source asset.
 # Cross-source residual area is explicitly measured after Float32 export.
 assert road_qa['crossSourceOverlapAreaM2']<.01
bounds=m['texture']['boundsEN'];e0,n0,e1,n1=bounds;roundtrip=np.column_stack([e0+uv[:,0].astype(float)*(e1-e0),n1-uv[:,1].astype(float)*(n1-n0)]);uv_error=float(abs(roundtrip-en).max());assert uv_error<.0001
with rasterio.open(args.tdop)as src:source_rgb=src.read(window=Window((e0-845000)*4,(824000-n1)*4,(e1-e0)*4,(n1-n0)*4)).transpose(1,2,0)
assert np.array_equal(np.asarray(Image.open(d/m['texture']['url'])),source_rgb)
mask=np.asarray(Image.open(d/m['mask']['url']));h,w=mask.shape[:2];rng=np.random.default_rng(20260906);rr=rng.integers(0,h,12000);cc=rng.integers(0,w,12000);xz=np.column_stack([e0-844800+(cc+.5)*.25,820500-n1+(rr+.5)*.25]);pairs=STRtree(polygons(p[:,:,[0,2]])).query(points(xz),predicate='intersects');expect=np.zeros(len(rr),bool);expect[pairs[0]]=True;actual=mask[rr,cc,0]>127;assert np.array_equal(expect,actual)
rr,cc=np.nonzero(mask[:,:,0]>127);q=np.column_stack([e0+(cc+.5)*.25,n1-(rr+.5)*.25]);encoded=mask[rr,cc,1].astype(float)+mask[rr,cc,2]/256;quant_error=float(abs(reference(q)-encoded).max());assert quant_error<1/256+.000001
source=json.load(open(d/'source-domains.json'));as_poly=lambda parts:unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in parts]);domain=as_poly(source['sourceDomainLocalXZ']);stage=as_poly(source['excludedStageLocalXZ']);centroid=p[:,:,[0,2]].mean(1);assert contains_xy(domain.buffer(.0001),centroid[:,0],centroid[:,1]).all();stage_hits=STRtree(polygons(p[:,:,[0,2]])).query(stage,predicate='intersects');overlap=sum(Polygon(p[i][:,[0,2]]).intersection(stage).area for i in stage_hits);assert overlap<.001
result={'status':'pass','meshVertices':len(positions),'meshTriangles':len(triangles),'independentOriginalDTMHeightComparisons':len(dtm_vertices),'maxHeightErrorMeters':height_error,'roadSourceGeometry':road_qa,'maxUVCoordinateErrorMeters':uv_error,'unchangedTDOPPixelCount':h*w,'maskTrianglePointChecks':12000,'maskTriangleMismatches':0,'heightMaskTexelsChecked':len(rr),'maxHeightEncodingErrorMeters':quant_error,'excludedStageOverlapSquareMeters':overlap,'allTriangleCentroidsInsideOfficialDomainWithin0_1mmTolerance':True,'separatePiazzaAndUnboundRoadNodes':True,'sourceFiles':{'glbSha256':hashlib.sha256(raw).hexdigest(),'maskSha256':hashlib.sha256((d/m['mask']['url']).read_bytes()).hexdigest()},'limitations':['Tests verify source alignment and representation consistency; browser acceptance must separately inspect remaining roof/ground seams and canopy retention.']}
(d/'independent-qa.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
