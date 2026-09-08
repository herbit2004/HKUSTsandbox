#!/usr/bin/env python3
"""Extract actual published building and named-space polygons plus evidence-backed POI patches.
Reads only the saved project evidence. Writes exclusively to this /tmp asset directory.
No remote requests, guessed coordinates, footprint simplification or invented heights.
"""
from pathlib import Path
import json,sys,collections,hashlib,shutil
import numpy as np
try:import pyproj
except ImportError:sys.path.insert(0,'/tmp/hkust-geometry-deps');import pyproj
R=Path(__file__).resolve().parents[2];S=R/'source-pathadvisor';O=Path(__file__).resolve().parent
C=json.loads((R/'public/data/catalog.json').read_text())['buildings'];CI={x['id']:x for x in C};E=json.loads((R/'public/data/poi-evidence.json').read_text());EI={x['sourceBuildingId']:x for x in E if x.get('sourceBuildingId')};BC=json.loads((S/'building-floor-catalog.json').read_text());BCI={x['building_id']:x for x in BC};B=json.loads((S/'all_base_map.geojson').read_text());T=pyproj.Transformer.from_crs(4326,2326,always_xy=True);SOURCE='https://navigate.ust.hk/path/api/app/assets/all-base-map';DATE='2026-09-05'

def local(coords):
 a=np.array(coords,float);e,n=T.transform(a[:,0],a[:,1]);return np.round(np.stack([np.asarray(e)-844800,820500-np.asarray(n)],axis=1),3).tolist()

def ring_stats(r):
 a=np.asarray(r);a=a-np.mean(a,axis=0);cross=a[:-1,0]*a[1:,1]-a[1:,0]*a[:-1,1];signed=cross.sum()/2
 if abs(signed)<1e-9:return 0,np.mean(r,axis=0)
 centroid=((a[:-1]+a[1:])*cross[:,None]).sum(axis=0)/(6*signed)+np.mean(r,axis=0)
 return abs(signed),centroid

def poly_stats(rings):
 areas=[ring_stats(r) for r in rings];net=areas[0][0]-sum(a[0] for a in areas[1:]);weighted=areas[0][0]*areas[0][1]-sum((a[0]*a[1] for a in areas[1:]),start=np.zeros(2));return net,weighted/net if net>1e-9 else areas[0][1]

def contains(point,rings):
 def inside(p,ring):
  x,z=p;yes=False
  for a,b in zip(ring,ring[1:]+ring[:1]):
   if (a[1]>z)!=(b[1]>z) and x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:yes=not yes
  return yes
 return inside(point,rings[0]) and not any(inside(point,r) for r in rings[1:])

cache={}
def floor_data(fid):
 if fid not in cache:
  p=S/'floors'/fid/'geojson-response.json';cache[fid]=json.loads(p.read_text())['data']['building_floor']
 return cache[fid]

def floor_summary(bid):
 rec=[];allz=set()
 for f in BCI[bid]['floors']:
  features=(floor_data(f['_id']).get('geojson') or {}).get('features',[]);zs=set()
  def walk(a):
   if not a:return
   if isinstance(a[0],(int,float)):
    if len(a)>2:zs.add(round(a[2],6))
   else:
    for p in a:walk(p)
  for ft in features:walk(ft['geometry']['coordinates'])
  allz.update(zs);rec.append({'id':f['_id'],'name':f['name'],'sourceZValues':sorted(zs),'source':f"https://navigate.ust.hk/path/api/app/building-floors/geojson?building_floor_id={f['_id']}"})
 return rec,sorted(allz)

footprints=[];patches=[];qa=[];unmatched=[];centroid_comparisons=[]
for index,feature in enumerate(B['features']):
 prop=feature['properties'];bid=prop['building_id'];name=prop['name'];old=EI.get(bid);cid=old['id'] if old else None;g=feature['geometry'];polygons=[g['coordinates']] if g['type']=='Polygon' else g['coordinates'];parts=[];stats=[]
 for k,poly in enumerate(polygons):
  rings=[local(r) for r in poly];assert all(len(r)>=4 and r[0]==r[-1] and np.isfinite(r).all() for r in rings);area,center=poly_stats(rings);assert area>=0,(name,k,area);parts.append({'partIndex':k,'rings':rings,'sourceZ':None,'areaSquareMeters':round(area,4)});stats.append((area,center))
 area=sum(x[0] for x in stats);center=sum((a*c for a,c in stats),start=np.zeros(2))/area;coords=np.array([v for p in parts for ring in p['rings'] for v in ring]);floors,z=floor_summary(bid);fid=cid or 'unmatched-'+bid
 rec={'id':fid,'catalogId':cid,'catalogName':CI[cid]['name'] if cid else None,'officialBuildingId':bid,'officialBuildingName':name,'geometryRole':'official-building-base-map-drawing','parts':parts,'sourceZ':None,'observedFloorZLevels':z,'minObservedFloorZ':min(z) if z else None,'maxObservedFloorZ':max(z) if z else None,'boundsXZ':{'min':coords.min(axis=0).tolist(),'max':coords.max(axis=0).tolist()},'drawingAreaSquareMeters':round(area,4),'computedAreaCentroidXZ':np.round(center,3).tolist(),'source':SOURCE,'sourceFeatureIndex':index,'sourceGeometryType':g['type'],'sourceFloorReferences':floors,'checkedAt':DATE,'evidence':'Exact official building_id linkage to existing poi-evidence record.' if cid else 'Official building polygon exists, but no exact catalog/evidence identity match was established.','limitations':['The source is the official base-map drawing, including detailed multipart shapes; it is not a certified cadastral footprint or BIM.','Base-map polygons are 2D: sourceZ is null. Floor Z range is only the minimum/maximum published floor coordinates, not building base or roof height.','Vertical datum and physical accuracy are not confirmed; do not silently snap to DTM or claim an as-built envelope.']}
 footprints.append(rec)
 if cid:
  previous=np.array([old['easting']-844800,820500-old['northing']]);delta=float(np.linalg.norm(previous-center));centroid_comparisons.append({'catalogId':cid,'distanceMeters':delta,'previousXZ':previous.tolist(),'newComputedXZ':center.tolist()});patches.append({'id':cid,'set':{'footprintId':fid,'positionEvidence':'官方 PathAdvisor 建筑多边形绘图面积中心；非测量入口、屋顶或竣工测绘。','positionSource':SOURCE},'unset':[],'reason':'Attach exact existing official building geometry; preserve current marker coordinates.','evidence':{'officialBuildingId':bid,'existingPoiEvidenceMethod':old['method'],'existingCentroidDifferenceMeters':round(delta,6)}})
 else:unmatched.append({'officialBuildingId':bid,'officialBuildingName':name,'footprintId':fid,'reason':'No exact catalog alias. Coastal Marine Lab is not automatically equated to Ocean Research Facility.'})
 qa.append({'footprintId':fid,'parts':len(parts),'allSourcePolygonPartsPreserved':len(parts)==len(polygons),'allRingsClosedAndFinite':True,'sourceZNeverInvented':True})

# Exact published named-space matches. No geometric proximity or fuzzy alias is used.
space_specs=[('campus-10','b00000000000000000000001',[('bf0000000000000000000107','Tsang Shiu Tim Art Hall')]),('campus-12','b00000000000000000000001',[('bf0000000000000000000107','Alumni Commons')]),('campus-13','b00000000000000000000001',[('bf0000000000000000000107','Mr and Mrs Ho Ting Sik Visitor Information Center')]),('campus-25','b00000000000000000000004',[('bf0000000000000000000401','Karen Lee Student Mentoring Center (G/F)'),('bf0000000000000000000402','Karen Lee Student Mentoring Center (1/F)')])]
for cid,bid,specs in space_specs:
 parts=[];references=[];nodes=[];allz=set()
 for fid,match in specs:
  matches=[f for f in floor_data(fid)['geojson']['features'] if f['properties'].get('hidden_from_map') is False and f['properties'].get('location_name')==match];assert len(matches)==1,(cid,match,len(matches));ft=matches[0];loc=ft['properties']['location_id'];g=ft['geometry'];polys=[g['coordinates']] if g['type']=='Polygon' else g['coordinates'];roomz=set()
  for poly in polys:
   rings=[local(r) for r in poly];zs=set(round(v[2],6) for ring in poly for v in ring);assert len(zs)==1;z=next(iter(zs));allz.add(z);roomz.add(z);parts.append({'partIndex':len(parts),'rings':rings,'sourceZ':z,'sourceFloorId':fid,'sourceLocationId':loc,'sourceLocationName':match,'areaSquareMeters':round(poly_stats(rings)[0],4)})
  nav=json.loads((S/'floors'/fid/'nav-nodes.json').read_text());nm=[n for n in nav if n.get('location_id')==loc and n.get('name')==match];assert len(nm)==1,(cid,match,'matching navnode');n=nm[0];xz=local([[float(n['longitude']),float(n['latitude'])]])[0];inside=any(contains(xz,p['rings']) for p in parts if p['sourceLocationId']==loc);nodes.append({'id':n['_id'],'locationId':loc,'floorId':fid,'name':match,'longitude':float(n['longitude']),'latitude':float(n['latitude']),'localXZ':xz,'sourceZ':next(iter(roomz)),'insideMatchingRoomPolygon':inside,'source':f'https://navigate.ust.hk/path/api/app/building-floors/nav-nodes?building_floor_id={fid}'})
  references.append({'floorId':fid,'locationId':loc,'exactSourceName':match,'source':f'https://navigate.ust.hk/path/api/app/building-floors/geojson?building_floor_id={fid}'})
 coords=np.array([v for p in parts for r in p['rings'] for v in r]);fpid=cid+'-named-space';chosen=next(n for n in nodes if n['insideMatchingRoomPolygon']);xz=chosen['localXZ'];floorname=next(f['name'] for f in BCI[bid]['floors'] if f['_id']==chosen['floorId']);rec={'id':fpid,'catalogId':cid,'catalogName':CI[cid]['name'],'officialBuildingId':bid,'officialBuildingName':BCI[bid]['name'],'geometryRole':'published-named-space-room-boundary','parts':parts,'sourceZ':next(iter(allz)) if len(allz)==1 else None,'observedFloorZLevels':sorted(allz),'minObservedFloorZ':min(allz),'maxObservedFloorZ':max(allz),'boundsXZ':{'min':coords.min(axis=0).tolist(),'max':coords.max(axis=0).tolist()},'source':references[0]['source'],'sourceRoomReferences':references,'publicNavigationNodes':nodes,'selectionAnchorXZ':xz,'checkedAt':DATE,'evidence':'Exact public room location_name plus matching location_id navigation node; selected node lies inside that room polygon.','limitations':['Named interior space, not an independent exterior building.','Source floor Z is preserved, vertical datum unconfirmed.','Marker is an official navigation-node reference, not a surveyed entrance.']};footprints.append(rec)
 patches.append({'id':cid,'set':{'easting':round(xz[0]+844800,3),'northing':round(820500-xz[1],3),'footprintId':fpid,'positionMethod':'official-path-advisor-named-space-navigation-node','positionEvidence':f'官方明确命名空间 {chosen["name"]} 的导航节点，已验证落在同 location_id 房间多边形内；非测量入口。','positionSource':chosen['source'],'indoorBuilding':BCI[bid]['name'],'preferredIndoorFloorId':chosen['floorId'],'preferredIndoorFloor':floorname,'sourceLocationId':chosen['locationId'],'sourceZ':chosen['sourceZ']},'unset':['focusParent'],'reason':'Replace parent-building focus with an explicitly named public room and its official navigation node.','evidence':{'oldFocusParent':CI[cid].get('focusParent'),'sourceRooms':references,'chosenNode':chosen}});qa.append({'footprintId':fpid,'parts':len(parts),'exactNameAndLocationIdMatch':True,'chosenNodeWithinNamedRoomPolygon':True,'sourceZPreservedPerPart':True})

# Public Teaching Hub POI has a precise reference point, but no verified outline here.
fid='bf0000000000000000000102';pois=json.loads((S/'floors'/fid/'point-of-interests.json').read_text());p=[x for x in pois if x.get('name')=='Teaching Hub'];assert len(p)==1;p=p[0];nav=json.loads((S/'floors'/fid/'nav-nodes.json').read_text());ns=[n for n in nav if n.get('point_of_interest_id')==p['_id'] and n.get('name')==p['name']];assert len(ns)==1;assert ns[0]['longitude']==p['longitude'] and ns[0]['latitude']==p['latitude'];xz=local([[float(p['longitude']),float(p['latitude'])]])[0];source=f'https://navigate.ust.hk/path/api/app/building-floors/point-of-interests?building_floor_id={fid}'
patches.append({'id':'campus-09','set':{'easting':round(xz[0]+844800,3),'northing':round(820500-xz[1],3),'positionMethod':'official-path-advisor-explicit-public-poi','positionEvidence':'官方 Teaching Hub 公共 POI，与同 point_of_interest_id 的导航节点经纬度一致；仅点位，不证明竣工、入口位置或楼层覆盖。','positionSource':source},'unset':[],'reason':'Provide the explicit published Teaching Hub point for a previously unlocated inventory item. Preserve the existing construction/status evidence.','evidence':{'sourcePoiId':p['_id'],'sourceNavNodeId':ns[0]['_id'],'exactName':'Teaching Hub','longitude':float(p['longitude']),'latitude':float(p['latitude']),'source':source,'noVerticalCoordinateSupplied':True,'sourceCatalogFloorId':fid,'warning':'Do not infer that the whole Teaching Hub is only LG6 or derive its height from the catalog floor ordinal.'}})

changed_independent={p['id'] for p in patches if p['set'].get('positionMethod')};old_unlocated=[c['id'] for c in C if 'easting' not in c];remaining_estimated=[c['id'] for c in C if c.get('positionMethod')=='official-campus-map-manual-digitisation-affine-registration'];remain_parent=[c['id'] for c in C if c.get('focusParent') and c['id'] not in changed_independent]
metadata={'version':1,'checkedAt':DATE,'coordinateSystem':{'horizontalCRS':'EPSG:2326 Hong Kong 1980 Grid','originE':844800,'originN':820500,'axes':'x=easting-844800; z=820500-northing; y=source Z only where given','rings':'Within each part, rings[0] is the outer ring and subsequent rings are holes. A building can have many parts.','processing':'Exact source polygon coordinates transformed through PROJ inverse HK1980-to-WGS84(1), rounded to0.001m; no simplification, convex hull or synthetic footprint.'},'source':{'baseMap':SOURCE,'rawFile':'source-all-base-map.geojson','rawSha256':hashlib.sha256((S/'all_base_map.geojson').read_bytes()).hexdigest(),'licenseNote':'HKUST official public data; no open redistribution license verified, local educational use with attribution.','geometryCaptureOrUpdateDate':None},'footprints':footprints,'unmatchedSourceBuildings':unmatched}
(O/'building-footprints.json').write_text(json.dumps(metadata,ensure_ascii=False,separators=(',',':')));shutil.copy2(S/'all_base_map.geojson',O/'source-all-base-map.geojson')
patchset={'version':1,'checkedAt':DATE,'target':'public/data/catalog.json -> buildings[] matched by id','instructions':'For each patch, set listed fields and remove listed unset fields. Other fields, especially status/source/date evidence, remain unchanged. These are recommendations; source checkout was not edited.','patches':patches};(O/'catalog-patches.json').write_text(json.dumps(patchset,ensure_ascii=False,indent=2))
coverage={'officialBaseMapFeatures':len(B['features']),'matchedBuildingOutlines':len(EI),'unmatchedOfficialOutlines':len(unmatched),'namedSpaceOutlineEntries':len(space_specs),'allOutlineEntries':len(footprints),'sourceBuildingPolygonParts':sum(len(x['parts']) for x in footprints if x['geometryRole']=='official-building-base-map-drawing'),'namedSpacePolygonParts':sum(len(x['parts']) for x in footprints if x['geometryRole']=='published-named-space-room-boundary'),'parentFocusReplacedByNamedGeometry':4,'newlyLocatedExplicitPoi':1,'recommendedPatches':len(patches),'previousIndependentPositions':sum(bool(c.get('positionMethod')) for c in C),'afterRecommendedIndependentPositions':sum(bool(c.get('positionMethod')) for c in C)+len(changed_independent),'remainingParentFocusedCount':len(remain_parent),'remainingUnlocatedCount':len(set(old_unlocated)-changed_independent),'mapEstimatedCoordinatesUpgraded':0,'remainingMapEstimatedIds':remaining_estimated,'remainingParentFocusedIds':remain_parent,'remainingUnlocatedIds':sorted(set(old_unlocated)-changed_independent)}
(O/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2));report={'status':'pass','checkedAt':DATE,'coverage':coverage,'largestExistingCentroidDifferenceMeters':max(x['distanceMeters'] for x in centroid_comparisons),'existingCentroidComparisons':centroid_comparisons,'checks':qa,'sourceFilesModified':False};(O/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'pass','coverage':coverage,'maxExistingCentroidDifferenceMeters':report['largestExistingCentroidDifferenceMeters'],'outputBytes':(O/'building-footprints.json').stat().st_size},ensure_ascii=False,indent=2))
