#!/usr/bin/env python3
"""Prepare visibility-filtered HKUST official PathAdvisor room polygons.
No network. Requires NumPy and pyproj. CAD is deliberately omitted because it
has no per-location hidden_from_map flags. Polygon edges are not certified walls.
"""
from pathlib import Path
import sys,json,math,hashlib,collections,argparse
import numpy as np
try:import pyproj
except ImportError:sys.path.insert(0,'/tmp/hkust-geometry-deps');import pyproj
P=argparse.ArgumentParser();P.add_argument('--source',default='/tmp/hkust-pathadvisor-complete');P.add_argument('--output',default='/tmp/hkust-interior-geometry');a=P.parse_args();S=Path(a.source);R=Path(a.output);R.mkdir(parents=True,exist_ok=True)
T=pyproj.Transformer.from_crs(4326,2326,always_xy=True);DATE='2026-09-05'
catalog=json.loads((S/'building-floor-catalog.json').read_text());entries=[];failures=[];totals=collections.Counter();hidden_ids=set();visible_ids=set();zvalues=set();tests=[]
def point_inside(p,ring):
 x,z=p;inside=False
 for a,b in zip(ring,ring[1:]+ring[:1]):
  if (a[1]>z)!=(b[1]>z) and x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:inside=not inside
 return inside

def centroid(rings):
 r=np.array(rings[0],float);u=r[:-1];v=r[1:];cross=u[:,0]*v[:,1]-v[:,0]*u[:,1];area=cross.sum()
 if abs(area)>1e-10:p=((u+v)*cross[:,None]).sum(axis=0)/(3*area)
 else:p=r.mean(axis=0)
 valid=lambda p:point_inside(p,rings[0]) and not any(point_inside(p,h) for h in rings[1:])
 if not valid(p):
  lo=r.min(axis=0);hi=r.max(axis=0);candidates=[np.array([x,z]) for x in np.linspace(lo[0],hi[0],19)[1:-1] for z in np.linspace(lo[1],hi[1],19)[1:-1]];candidates=[q for q in candidates if valid(q)]
  if candidates:p=min(candidates,key=lambda q:np.linalg.norm(q-p))
 return [round(float(v),3) for v in p]

for building in catalog:
 for fl in building['floors']:
  fid=fl['_id'];p=S/'floors'/fid/'geojson-response.json';url=f'https://navigate.ust.hk/path/api/app/building-floors/geojson?building_floor_id={fid}'
  if fl.get('show_in_path_advisor') is not True:totals['catalogHiddenFloors']+=1;continue
  if not p.exists():failures.append({'id':fid,'reason':'source not downloaded'});continue
  try:d=json.loads(p.read_text());bf=d['data']['building_floor'];sourceFeatures=bf.get('geojson',{}).get('features',[])
  except Exception as e:failures.append({'id':fid,'reason':str(e)});continue
  rooms=[];skipped=0;unsupported=0;sourceHeights=set();floorVisibleFeatureCount=0;allxz=[];sourceVisibleIDs=set()
  for feature in sourceFeatures:
   props=feature.get('properties',{});location=props.get('location_id');
   # Fail closed: only explicitly visible source features enter the browser data.
   if props.get('hidden_from_map') is not False:
    skipped+=1
    if location:hidden_ids.add(location)
    continue
   g=feature.get('geometry') or {};polys=[g['coordinates']] if g.get('type')=='Polygon' else g['coordinates'] if g.get('type')=='MultiPolygon' else []
   if not polys:unsupported+=1;continue
   floorVisibleFeatureCount+=1
   if location:sourceVisibleIDs.add(location);visible_ids.add(location)
   for part,rings in enumerate(polys):
    out=[];ys=[]
    for ring in rings:
     ar=np.array(ring,float);assert ar.ndim==2 and ar.shape[1]>=3 and len(ar)>=4 and np.isfinite(ar).all(),(fid,location)
     e,n=T.transform(ar[:,0],ar[:,1]);xz=np.round(np.stack([np.asarray(e)-844800,820500-np.asarray(n)],axis=1),3);assert np.array_equal(xz[0],xz[-1]),(fid,location,'ring not closed');out.append(xz.tolist());ys.extend(ar[:,2].tolist());allxz.extend(xz.tolist())
    unique=sorted(set(round(float(y),6) for y in ys));sourceHeights.update(unique);zvalues.update(unique);assert len(unique)==1,(fid,location,'non-planar source room requires schema extension')
    rid=location or 'source-feature-'+str(feature.get('id'));rid+=f':part-{part}' if len(polys)>1 else '';color=props.get('type_color_hex') or 'DDE7F1';color=color.lstrip('#');color='#'+color if len(color)==6 and all(c in '0123456789abcdefABCDEF' for c in color) else '#DDE7F1'
    rooms.append({'id':rid,'sourceLocationId':location,'sourceFeatureId':feature.get('id'),'name':props.get('location_name') or '', 'type':props.get('type_name') or '', 'color':color,'rings':out,'heightSourceZ':unique[0],'center':centroid(out)})
  heights=sorted(sourceHeights);z=heights[0] if len(heights)==1 else None
  bounds=None
  if allxz:
   ar=np.array(allxz);bounds={'min':[round(float(ar[:,0].min()),3),min(heights),round(float(ar[:,1].min()),3)],'max':[round(float(ar[:,0].max()),3),max(heights),round(float(ar[:,1].max()),3)]}
  result={'version':1,'id':fid,'buildingId':building['building_id'],'buildingName':building['name'],'floorName':fl['name'],'catalogElevation':fl.get('elevation'),'catalogElevationMeaning':'Source catalog field; not used as geometric height. Values can be ordinal or other source conventions.','isDefault':bool(fl.get('is_default')),'z':z,'sourceZValues':heights,'sourceZMeaning':'Original room polygon Z, numerically preserved without datum correction; absolute vertical datum is unverified.','rooms':rooms,'cadLines':[],'cadPolicy':'Original CAD omitted because it has no hidden_from_map flags. Generate room perimeter lines from visible rooms.rings only; these are boundaries, not all physical walls.','bounds':bounds,'source':{'url':url,'officialApp':'https://navigate.ust.hk/path/app/','retrievedAt':DATE,'sourceGeometryUpdatedAt':None,'sourceSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'credit':'HKUST PathAdvisor official published app data','license':'No open redistribution license verified; local campus-learning use only. Do not apply government CSDI license to these university data.'},'stats':{'sourceFeatures':len(sourceFeatures),'visibleSourceFeatures':floorVisibleFeatureCount,'roomPolygonParts':len(rooms),'hiddenOrUnspecifiedFeaturesExcluded':skipped,'unsupportedVisibleFeatures':unsupported,'originalCadIncluded':False}}
  q=R/f'{fid}.json';q.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
  entries.append({'id':fid,'buildingId':building['building_id'],'buildingName':building['name'],'floorName':fl['name'],'url':q.name,'z':z,'sourceZValues':heights,'isDefault':bool(fl.get('is_default')),'bounds':bounds,'rooms':len(rooms),'visibleSourceFeatures':floorVisibleFeatureCount,'bytes':q.stat().st_size,'source':url})
  totals['sourceFeatures']+=len(sourceFeatures);totals['visibleSourceFeatures']+=floorVisibleFeatureCount;totals['roomPolygonParts']+=len(rooms);totals['hiddenOrUnspecifiedFeaturesExcluded']+=skipped;totals['unsupportedVisibleFeatures']+=unsupported;totals['emptyVisibleFloors']+=not bool(rooms);totals['jsonBytes']+=q.stat().st_size
  assert {r['sourceLocationId'] for r in rooms}<=sourceVisibleIDs
  tests.append({'id':fid,'explicitSourceVisibilityValidated':True,'allRingsClosed':True,'finiteCoordinates':True,'sourceZPreserved':True,'hiddenGeometryAndLabelsExcluded':True,'rooms':len(rooms)})
manifest={'version':1,'checkedAt':DATE,'coordinateSystem':{'horizontalCRS':'EPSG:2326 Hong Kong 1980 Grid','originE':844800,'originN':820500,'axes':'x=easting-844800; y=source polygon Z; z=820500-northing','rings':'Each ring is [[x,z],...], in meters. Outer ring first; remaining rings are holes. Do not drop holes.','horizontalProcessing':'WGS84 lon/lat to HK1980 Grid through PROJ inverse Hong Kong 1980 to WGS84 (1); rounded to nearest 0.001m.','verticalDatum':'Not confirmed. Preserve heightSourceZ per room; do not use catalogElevation or historical library levels as substitute.','wallHeight':'Not included. Any 0-3m boundary extrusion in UI is an explicitly diagrammatic display choice, not measured wall height.'},'visibilityPolicy':'Only features with properties.hidden_from_map === false; all other room geometry and labels excluded. Raw CAD is entirely omitted because it lacks visibility associations.','source':{'app':'https://navigate.ust.hk/path/app/','checkedAt':DATE,'geometryUpdatedAt':None,'credit':'HKUST PathAdvisor','license':'No open redistribution license verified. Keep local educational scope and source attribution.'},'stats':{'catalogBuildings':len(catalog),'catalogFloors':sum(len(b['floors']) for b in catalog),'convertedFloors':len(entries),'buildingsWithConvertedFloors':len(set(e['buildingId'] for e in entries)),**totals},'floors':entries,'failures':failures}
(R/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
report={'status':'pass' if not failures else 'incomplete-source','checkedAt':DATE,'stats':manifest['stats'],'allSourceRoomZPlanar':True,'sourceZRange':[min(zvalues),max(zvalues)] if zvalues else None,'hiddenGeometryNotCopiedToOutput':True,'cadGeometryNotCopiedToOutput':True,'tests':tests,'failures':failures};(R/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='tests'},ensure_ascii=False,indent=2))
