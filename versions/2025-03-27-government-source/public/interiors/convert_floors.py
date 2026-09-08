#!/usr/bin/env python3
"""Convert the public HKUST PathAdvisor floor geometry, following official renderer semantics.
All public polygons remain. hidden_from_map changes background color; background
names are omitted and interaction is disabled. Public CAD gets a reference plane.
No network. Requires NumPy and pyproj. Inputs remain untouched.
"""
from pathlib import Path
import sys,json,hashlib,collections,argparse
import numpy as np
try:import pyproj
except ImportError:sys.path.insert(0,'/tmp/hkust-geometry-deps');import pyproj
P=argparse.ArgumentParser();P.add_argument('--source',default='/tmp/hkust-pathadvisor-complete');P.add_argument('--output',default='/tmp/hkust-interior-geometry');a=P.parse_args();S=Path(a.source);R=Path(a.output);R.mkdir(parents=True,exist_ok=True)
T=pyproj.Transformer.from_crs(4326,2326,always_xy=True);DATE='2026-09-05'
catalog=json.loads((S/'building-floor-catalog.json').read_text());entries=[];failures=[];totals=collections.Counter();zvalues=set();tests=[]
def inside(p,ring):
 x,z=p;v=False
 for a,b in zip(ring,ring[1:]+ring[:1]):
  if (a[1]>z)!=(b[1]>z) and x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:v=not v
 return v

def centroid(rings):
 r=np.array(rings[0],float);u=r[:-1];v=r[1:];cross=u[:,0]*v[:,1]-v[:,0]*u[:,1];area=cross.sum();p=((u+v)*cross[:,None]).sum(axis=0)/(3*area) if abs(area)>1e-10 else r.mean(axis=0)
 valid=lambda p:inside(p,rings[0]) and not any(inside(p,h) for h in rings[1:])
 if not valid(p):
  lo=r.min(axis=0);hi=r.max(axis=0);cs=[np.array([x,z]) for x in np.linspace(lo[0],hi[0],19)[1:-1] for z in np.linspace(lo[1],hi[1],19)[1:-1]];cs=[q for q in cs if valid(q)]
  if cs:p=min(cs,key=lambda q:np.linalg.norm(q-p))
 return [round(float(v),3) for v in p]

def local2(ar):
 e,n=T.transform(ar[:,0],ar[:,1]);return np.round(np.stack([np.asarray(e)-844800,820500-np.asarray(n)],axis=1),3)

def cad_convert(bf,fid,refz):
 data=bf.get('cad_geojson') or {};features=data.get('features',[]) if isinstance(data,dict) else [];lines=[];unsupported=[]
 for f in features:
  g=f.get('geometry') or {};typ=g.get('type')
  if typ=='LineString':lines.append(g['coordinates'])
  elif typ=='MultiLineString':lines.extend(g['coordinates'])
  elif typ:unsupported.append(typ)
 lines=[np.asarray(line,dtype=float) for line in lines if len(line)>1]
 if not lines:return None
 assert refz is not None,(fid,'CAD without a known source room Z')
 assert all(ar.shape[1] in [2,3] and np.isfinite(ar).all() for ar in lines)
 segments=[];sourcepoints=sum(len(ar) for ar in lines);havesourcez=any(ar.shape[1]>2 for ar in lines);flat=np.concatenate([ar[:,:2] for ar in lines]);xz=local2(flat);offset=0
 for ar in lines:
  xy=xz[offset:offset+len(ar)];offset+=len(ar);ys=ar[:,2] if ar.shape[1]>2 else np.full(len(ar),refz);xyz=np.stack([xy[:,0],ys,xy[:,1]],axis=1).astype('<f4');segments.append(np.stack([xyz[:-1],xyz[1:]],axis=1))
 allseg=np.concatenate(segments);inputsegments=len(allseg)
 # Duplicate CAD segments (including reversed endpoints) render identically.
 # Canonicalize endpoint order and remove duplicates to reduce GPU memory.
 lo=allseg[:,0];hi=allseg[:,1];flip=(lo[:,0]>hi[:,0])|((lo[:,0]==hi[:,0])&(lo[:,2]>hi[:,2]))|((lo[:,0]==hi[:,0])&(lo[:,2]==hi[:,2])&(lo[:,1]>hi[:,1]));allseg[flip]=allseg[flip,::-1]
 flatseg=allseg.reshape(-1,6);flatseg=np.unique(flatseg,axis=0);zero=np.all(flatseg[:,:3]==flatseg[:,3:],axis=1);nzero=int(zero.sum());flatseg=flatseg[~zero];out=flatseg.astype('<f4').reshape(-1,3);path=R/f'{fid}.cad.bin';path.write_bytes(out.tobytes())
 return {'url':path.name,'format':'float32-le xyz LineSegments','vertexCount':len(out),'segmentCount':len(flatseg),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'referenceZ':refz,'heightMode':'source-z-when-present-otherwise-floor-reference-plane','sourceHadZ':havesourcez,'sourcePointCount':sourcepoints,'sourceSegmentCount':inputsegments,'duplicateSegmentsRemoved':inputsegments-len(flatseg)-nzero,'zeroLengthSegmentsRemovedAfterMillimeterRounding':nzero,'color':'#D3D3D3','opacity':0.8,'unsupportedGeometryTypes':sorted(set(unsupported)),'note':'CAD source has no Z in this dataset. This is a labeled reference plane, not measured vertical wall geometry; rooms keep their own source Z.'}

for building in catalog:
 for fl in building['floors']:
  fid=fl['_id'];p=S/'floors'/fid/'geojson-response.json';url=f'https://navigate.ust.hk/path/api/app/building-floors/geojson?building_floor_id={fid}'
  if fl.get('show_in_path_advisor') is not True:totals['catalogHiddenFloors']+=1;continue
  if not p.exists():failures.append({'id':fid,'reason':'source not downloaded'});continue
  try:d=json.loads(p.read_text());bf=d['data']['building_floor'];features=(bf.get('geojson') or {}).get('features',[])
  except Exception as e:failures.append({'id':fid,'reason':str(e)});continue
  rooms=[];background=0;interactive=0;named=0;unsupported=0;heightsCount=collections.Counter();allxz=[];sourceIDs=set()
  for feature in features:
   props=feature.get('properties',{});location=props.get('location_id');hidden=props.get('hidden_from_map') is not False;g=feature.get('geometry') or {};polys=[g['coordinates']] if g.get('type')=='Polygon' else g['coordinates'] if g.get('type')=='MultiPolygon' else []
   if not polys:unsupported+=1;continue
   if hidden:background+=1
   else:interactive+=1;named+=bool(props.get('location_name'))
   for part,rings in enumerate(polys):
    out=[];ys=[]
    for ring in rings:
     ar=np.asarray(ring,float);assert ar.ndim==2 and ar.shape[1]>=3 and len(ar)>=4 and np.isfinite(ar).all(),(fid,location);xz=local2(ar);assert np.array_equal(xz[0],xz[-1]),(fid,location,'ring not closed');out.append(xz.tolist());ys.extend(ar[:,2].tolist());allxz.extend(xz.tolist())
    unique=sorted(set(round(float(y),6) for y in ys));zvalues.update(unique);assert len(unique)==1,(fid,location,'non-planar source room needs schema extension');heightsCount[unique[0]]+=1;rid=location or 'source-feature-'+str(feature.get('id'));rid+=f':part-{part}' if len(polys)>1 else ''
    if hidden:color='#F9FCFF'
    else:
     color=(props.get('type_color_hex') or 'CCCCCC').lstrip('#');color='#'+color if len(color)==6 and all(c in '0123456789abcdefABCDEF' for c in color) else '#CCCCCC'
    rooms.append({'id':rid,'sourceLocationId':location,'sourceFeatureId':feature.get('id'),'name':'' if hidden else props.get('location_name') or '', 'type':'公开底图轮廓' if hidden else props.get('type_name') or '', 'color':color,'interactive':not hidden,'hiddenFromMap':hidden,'rings':out,'heightSourceZ':unique[0],'center':None if hidden else centroid(out)})
  heights=sorted(heightsCount);z=heights[0] if len(heights)==1 else None;refz=heightsCount.most_common(1)[0][0] if heightsCount else None;bounds=None
  if allxz:
   ar=np.array(allxz);bounds={'min':[round(float(ar[:,0].min()),3),min(heights),round(float(ar[:,1].min()),3)],'max':[round(float(ar[:,0].max()),3),max(heights),round(float(ar[:,1].max()),3)]}
  cad=cad_convert(bf,fid,refz)
  st={'sourceFeatures':len(features),'publicPolygonParts':len(rooms),'labeledSourceFeatures':interactive,'namedSourceFeatures':named,'backgroundSourceFeatures':background,'unsupportedFeatures':unsupported,'cadSegments':cad['segmentCount'] if cad else 0}
  result={'version':2,'id':fid,'buildingId':building['building_id'],'buildingName':building['name'],'floorName':fl['name'],'catalogElevation':fl.get('elevation'),'catalogElevationMeaning':'Source catalog field; not used as geometric height. Values may be ordinal or other source conventions.','isDefault':bool(fl.get('is_default')),'z':z,'sourceZValues':heights,'sourceZMeaning':'Original room polygon Z, preserved per room without datum correction; absolute vertical datum unverified. A floor can have several source Z values.','rooms':rooms,'cadLines':[],'cad':cad,'cadPolicy':'Public CAD is included as binary LineSegments matching official app rendering. No-Z CAD uses the floor modal room Z as a reference plane; do not flatten room Z to this CAD plane.','bounds':bounds,'source':{'url':url,'officialApp':'https://navigate.ust.hk/path/app/','retrievedAt':DATE,'sourceGeometryUpdatedAt':None,'sourceSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'credit':'HKUST PathAdvisor official published app data','license':'No open redistribution license verified; local campus-learning use only. Do not apply government CSDI license to university data.'},'stats':st}
  q=R/f'{fid}.json';q.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
  entries.append({'id':fid,'buildingId':building['building_id'],'buildingName':building['name'],'floorName':fl['name'],'url':q.name,'z':z,'sourceZValues':heights,'isDefault':bool(fl.get('is_default')),'bounds':bounds,'rooms':len(rooms),'publicPolygonParts':len(rooms),'labeledFeatures':interactive,'namedFeatures':named,'backgroundFeatures':background,'cadSegments':st['cadSegments'],'cadBytes':cad['bytes'] if cad else 0,'bytes':q.stat().st_size,'source':url})
  for k,v in st.items():totals[k]+=v
  totals['floorsWithoutLabeledFeatures']+=interactive==0;totals['jsonBytes']+=q.stat().st_size;totals['cadBytes']+=cad['bytes'] if cad else 0;totals['floorsWithCad']+=cad is not None;totals['floorsWithMultipleSourceZ']+=len(heights)>1
  assert all(not r['name'] and r['type']=='公开底图轮廓' and not r['interactive'] and r['center'] is None for r in rooms if r['hiddenFromMap']);assert len(rooms)>=len(features)-unsupported
  tests.append({'id':fid,'allPublicPolygonsRetained':True,'backgroundNamesOmittedAndInteractionDisabled':True,'allRingsClosed':True,'finiteCoordinates':True,'sourceZPreservedPerRoom':True,'publicPolygonParts':len(rooms),'cadSegments':st['cadSegments'],'sourceZValues':heights})
script=S/'main.js';js=script.read_text();evidence={'source':'https://navigate.ust.hk/path/app/static/js/main.c4c44c26.js','localSourceSha256':hashlib.sha256(script.read_bytes()).hexdigest(),'checkedAt':DATE,'hiddenFromMapOccurrences':js.count('hidden_from_map'),'confirmedBehavior':{'layer_geojson':'No feature filter. hidden_from_map === true gets fill #F9FCFF; otherwise source type color or #CCCCCC.','layer_geojson_outline':'No hidden feature filter. Color #CCCCCC.','layer_cad_geojson':'Public CAD source drawn without a hidden feature filter; color #D3D3D3 opacity 0.8.'},'outputChoice':'Retain background geometry but omit its names and disable interaction. Render public CAD independently.'};(R/'official-rendering-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
manifest={'version':2,'checkedAt':DATE,'coordinateSystem':{'horizontalCRS':'EPSG:2326 Hong Kong 1980 Grid','originE':844800,'originN':820500,'axes':'x=easting-844800; y=room source Z; z=820500-northing','rings':'Each ring is [[x,z],...], meters. Outer ring first; following rings are holes. Preserve holes.','horizontalProcessing':'WGS84 lon/lat to HK1980 through PROJ inverse Hong Kong 1980 to WGS84 (1); nearest 0.001m.','verticalDatum':'Unconfirmed. Preserve heightSourceZ per room. LSK Business Building 6 has multiple Z levels; never replace all with floor.z or CAD referenceZ.','wallHeight':'Not supplied. Boundary extrusion, if shown, must be explicitly diagrammatic.'},'visibilityPolicy':'Official renderer uses hidden_from_map for background fill, not geometry suppression. All public polygons included; background is color #F9FCFF, name empty, generic type, interactive false.','cadFormat':{'format':'float32-le xyz LineSegments','layout':'cad.url is a local binary file; each consecutive pair of vertices forms one segment. BufferAttribute itemSize=3.','coordinates':'Already local Three xyz, including source/reference-plane y; no extra rotation or origin shift.','heightPolicy':'Source CAD has no Z. Use modal room Z as an explicitly labeled reference plane; preserve each room source Z independently.','changes':'Rounded horizontal coords to nearest millimeter; exact repeated/reversed segments and zero-length rounded segments removed.'},'source':{'app':'https://navigate.ust.hk/path/app/','checkedAt':DATE,'geometryUpdatedAt':None,'credit':'HKUST PathAdvisor','license':'No open redistribution license verified. Keep local educational scope and attribution.'},'stats':{'catalogBuildings':len(catalog),'catalogFloors':sum(len(b['floors']) for b in catalog),'convertedFloors':len(entries),'buildingsWithConvertedFloors':len(set(e['buildingId'] for e in entries)),**totals},'floors':entries,'failures':failures}
(R/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')));report={'status':'pass' if not failures else 'incomplete-source','version':2,'checkedAt':DATE,'stats':manifest['stats'],'sourceZRange':[min(zvalues),max(zvalues)] if zvalues else None,'allPublicPolygonsRetained':True,'backgroundNamesOmittedAndInteractionDisabled':True,'cadIncludedAsOfficialPublicLayer':True,'sourceRoomZNeverFlattened':True,'tests':tests,'failures':failures};(R/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='tests'},ensure_ascii=False,indent=2))
