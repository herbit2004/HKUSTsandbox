#!/usr/bin/env python3
"""Digitise named POI reference points from official maps; no building mesh.
Requires numpy, Pillow, pyproj. The source pixel selections are auditable below.
"""
import json, pathlib, hashlib, xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from pyproj import Transformer

ROOT=pathlib.Path('/tmp')
MAP_URL='https://publish.ust.hk/univ/maps/Campus_Map_Color.pdf'
SEN_URL='https://sen.hkust.edu.hk/access-map/data/setting.json'
VR_URL='https://campus-vr.hkust.edu.hk/tour.xml'
maps=ROOT/'hkust-wayfinding'
markers=json.load(open(maps/'access-map-data.json'))['markers']
entities={e['id']:e for e in json.load(open(ROOT/'hkust-buildings.json'))['buildings_and_named_facilities']}
transform=Transformer.from_crs(4326,2326,always_xy=True)

# Map pixels are manual observations on the 2024x1432 official Aug 2026 PNG.
# SEN positions identify facilities, while its legacy map does not expose the
# exact point on the printed map. Pixel matching is thus an approximate
# facility correspondence, NOT a surveyed ground-control observation.
control_specs=[
 (1,1053,463,'Library LG1 AV counter: library wing interior reference'),
 (2,967,778,'Outside LT-E: visible blue E and adjacent corridor'),
 (8,974,940,'Behind CYT lift 37: visible 35-37 lift group'),
 (3,1140,1170,'LSK building: middle of named building footprint'),
 (12,1316,1243,'IAS accessible facilities: named IAS building'),
 (13,1338,1330,'Conference Lodge: named southern lodge footprint'),
 (34,1155,842,'Near Tin Ka Ping Hall: marked northwest part of University Center'),
 (31,1290,590,'Hall I G/F ramp: Hall I bridge-side part of footprint'),
 (32,1390,551,'Near Hall VII: marked Hall VII southeast edge'),
 (35,850,1116,'Geotechnical centrifuge vicinity: facility approach by Wong Check She block'),
 (36,902,1198,'South bus station vicinity: bus approach beside south entrance')
]
A=np.array([[x,y,1]for i,x,y,note in control_specs],dtype=float)
B=np.array([transform.transform(markers[i]['longitude'],markers[i]['latitude'])for i,x,y,note in control_specs])
coef=np.linalg.lstsq(A,B,rcond=None)[0]
res=A@coef-B
norm=np.linalg.norm(res,axis=1)
loo=[]
for i in range(len(A)):
 keep=np.arange(len(A))!=i
 fit=np.linalg.lstsq(A[keep],B[keep],rcond=None)[0]
 loo.append(float(np.linalg.norm(A[i]@fit-B[i])))
controls=[]
for k,(i,x,y,note) in enumerate(control_specs):
 controls.append({'senMarkerIndex':i,'title':markers[i]['title'],'longitude':markers[i]['longitude'],'latitude':markers[i]['latitude'],'easting':float(B[k,0]),'northing':float(B[k,1]),'mapPixel':[x,y],'pixelSelectionEvidence':note,'residualMeters':float(norm[k]),'leaveOneOutResidualMeters':loo[k]})
registration={'source_map':MAP_URL,'source_map_title':'Campus_Map_ColorC&E_Aug2026_OL','source_map_pixels':[2024,1432],'source_map_sha256':hashlib.sha256((maps/'campus.png').read_bytes()).hexdigest(),'coordinate_points_source':SEN_URL,'checked_at':'2026-09-05','source_sen_revision':'not stated; legacy facility map','projection':'pyproj EPSG:4326 to EPSG:2326, always_xy=True','formula':'[easting,northing] = [pixelX,pixelY,1] @ affine_coefficients','affine_coefficients':coef.tolist(),'fit_rmse_m':float(np.sqrt(np.mean(norm**2))),'fit_max_residual_m':float(norm.max()),'leave_one_out_rmse_m':float(np.sqrt(np.mean(np.array(loo)**2))),'leave_one_out_max_residual_m':max(loo),'control_points':controls,'uncertainty_note':'These are manually matched facility correspondences, not surveyed ground control. Fit residual describes consistency with the schematic map only. Map-derived POIs use a 50m caution radius for orientation; it is not a statistical accuracy guarantee. They must not be used as entrance positions, building footprints, routes, or measured boundaries.','scope':'Main campus landmarks and residential buildings within/near the selected control point area. No fabricated coordinates for unmatched facilities.'}
(ROOT/'hkust-poi-registration.json').write_text(json.dumps(registration,ensure_ascii=False,indent=2))

pois=[]
def base(id):
 e=entities[id];return {'id':id,'name_en':e['name_en'],'name_zh':e.get('name_zh'),'source_map_name':e['name_en'],'crs':'EPSG:2326','checked_at':'2026-09-05','origin':{'easting':844800,'northing':820500}}
def add(id,e,n,**kw):
 p=base(id);p.update({'easting':round(float(e),3),'northing':round(float(n),3),'localX':round(float(e)-844800,3),'localZ':round(-(float(n)-820500),3),**kw});pois.append(p)
def sen(id,i,note):
 m=markers[i];e,n=transform.transform(m['longitude'],m['latitude'])
 add(id,e,n,longitude=m['longitude'],latitude=m['latitude'],source=SEN_URL,evidence=m['title'],method='official-access-map-reference-point',accuracyMeters=None,accuracyNote='Official map does not state positional accuracy. This is the named facility or nearby amenity reference point, not a surveyed entrance or building centre.',referencePointNote=note,sourceMarkerIndex=i,sourceRevision='not stated')
def pixel(id,x,y,note):
 e,n=np.array([x,y,1])@coef
 add(id,e,n,mapPixel=[x,y],source=MAP_URL,evidence=note,method='official-campus-map-manual-digitisation-affine-registration',accuracyMeters=50,accuracyNote='50m is an orientation caution radius, not a measured or statistical accuracy claim. Campus map is schematic; affine fit RMSE18.876m, leave-one-out errors in registration report.',referencePointNote='Visual footprint reference point; not an entrance, surveyed centroid, or shape reconstruction.',sourceRevision='2026-08',registrationFile='hkust-poi-registration.json')

# Published coordinate references are used directly whenever the named facility
# can be matched. Do not move these to a visually prettier apparent centroid.
sen('campus-01',0,'Computer Barn B reference inside the Academic Building')
sen('campus-04',1,'LG1 AV service counter reference inside the Library')
sen('campus-18',8,'Accessible washroom reference behind CYT lift 37')
sen('campus-24',3,'SEN station reference inside LSK Business Building')
sen('campus-28',12,'Accessible-facility reference in IAS building')
sen('campus-30',13,'G/F concierge-adjacent accessible washroom reference')
sen('campus-36',34,'Nearby Tin Ka Ping Hall ramp reference, within the University Center vicinity')
sen('ug-hall-1',31,'Ramp near Hall I G/F; not the elevated bridge entrance')
sen('ug-hall-7',32,'Ramp near Hall VII; nearby reference, not a dorm entrance')
sen('ug-hall-9',17,'Disabled parking near Hall IX; a nearby reference, not Hall IX centre')

vr={s.get('name'):s for s in ET.parse(ROOT/'hkust-campus-vr-tour.xml').getroot().iter('scene')}
for id,scene,note in [('campus-02','scene_Atrium','Official VR camera reference at Atrium'),('campus-61','scene_Piazza','Official VR camera reference at Piazza'),('campus-52','scene_Sports_Center','Official VR sports-centre outdoor camera reference near Fok Ying Tung Sports Center')]:
 s=vr[scene];lat,lon=float(s.get('lat')),float(s.get('lng'));e,n=transform.transform(lon,lat)
 add(id,e,n,longitude=lon,latitude=lat,source=VR_URL,evidence=scene,method='official-virtual-tour-geographic-scene-reference',accuracyMeters=None,accuracyNote='Official VR metadata does not state GPS accuracy or capture date. The position is a panorama camera reference, not an entrance or measured building centre.',referencePointNote=note,sourceScene=scene,sourceRevision='not stated')

# Visible building centres / representative footprint points in the official
# Aug2026 campus drawing. These annotate names only; they never create geometry.
for id,x,y,note in [
 ('campus-07',940,465,'Named S H Ho Sports Hall footprint immediately north of atrium'),
 ('campus-19',1025,1014,'Named Martin Ka Shing Lee Innovation Building south-east of CYT'),
 ('campus-20',892,1000,'Dark construction/planning footprint labelled Medical Education and Research Complex'),
 ('campus-22',940,1074,'Distinct concentric oval Shaw Auditorium footprint'),
 ('campus-27',1210,1271,'Named Daniel & Mayce Yu Research Building construction footprint south of LSK'),
 ('campus-32',1114,1002,'Named Tsang Chiu Sang Tower (Tower A) residential footprint'),
 ('campus-33',1132,931,'Named Lam Po Yu Tower (Tower B) residential footprint'),
 ('campus-35',1300,1070,'Named Jockey Club Global Graduate Tower cruciform footprint'),
 ('campus-48',1480,552,'Named Tsang Shiu Tim Sports Center footprint west of the stadium'),
 ('ug-hall-2',1336,617,'Named UG Hall II short block east of Hall I'),
 ('ug-hall-3',1276,406,'Distinct curved Hall III footprint on the north-east residential slope'),
 ('ug-hall-4',1449,669,'Named UG Hall IV long curved residential footprint beside Courts 1-2'),
 ('ug-hall-5',1193,499,'Named UG Hall V (PG Hall II) footprint west of Hall III'),
 ('ug-hall-6',1330,655,'Named UG Hall VI footprint east of the bridge axis'),
 ('ug-hall-8',1510,751,'Western portion of southern seafront hall block labelled Hall VIII'),
 ('ug-hall-10',1260,1118,'Western i-Village ribbon labelled Hall X'),
 ('ug-hall-11',1352,1128,'Middle northern i-Village ribbon labelled DJI Hall (Hall XI)'),
 ('ug-hall-12',1373,1170,'Inner eastern i-Village residential arm labelled Hall XII'),
 ('ug-hall-13',1425,1167,'Outer eastern i-Village residential arm labelled Hall XIII')
]:pixel(id,x,y,note)

# Supersede matched points using subsequently available official Path Advisor
# geographic base-map outlines. Area-weighted centroid is computed in projected
# metres, with interior rings subtracted. This is a drawing centroid, not an
# assertion of public entrance, current as-built perimeter, or survey accuracy.
PA_URL='https://navigate.ust.hk/path/api/app/assets/all-base-map'
pa_matches={
 'Academic Building':'campus-01','Cheng Yu Tung Building':'campus-18',
 'HKUST Jockey Club Institute for Advanced Study/Lo Ka Chung Building':'campus-28',
 'Lee Shau Kee Business Building':'campus-24','Lo Ka Chung University Center':'campus-36',
 'Shaw Auditorium':'campus-22','Tsang Shiu Tim Sports Centre':'campus-48',
 'Li Dak Sum Yip Yio Chin Kenneth Li Conference Lodge':'campus-30',
 'Outdoor Swimming Pool':'campus-49','Martin Ka Shing Lee Innovation Building':'campus-19',
 'Water Sports Center':'campus-53',**{'UG Hall '+roman:'ug-hall-'+str(i)for i,roman in [(1,'I'),(2,'II'),(6,'VI'),(10,'X'),(11,'XI'),(12,'XII'),(13,'XIII')]}
}
def projected_centroid(geometry):
 polys=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
 weighted=np.zeros(2);area=0
 for poly in polys:
  for ri,ring in enumerate(poly):
   xy=np.array([transform.transform(p[0],p[1])for p in ring]);offset=xy[0].copy();xy-=offset
   x,y=xy[:,0],xy[:,1];cross=x[:-1]*y[1:]-x[1:]*y[:-1];signed_area=cross.sum()/2
   if abs(signed_area)<1e-10:continue
   center=np.array([((x[:-1]+x[1:])*cross).sum(),((y[:-1]+y[1:])*cross).sum()])/(6*signed_area)+offset
   weight=abs(signed_area)*(1 if ri==0 else -1);weighted+=center*weight;area+=weight
 if area<=0:raise ValueError('Invalid footprint area')
 return weighted/area,area
for f in json.load(open(ROOT/'hkust-pathadvisor-complete/all_base_map.geojson'))['features']:
 name=f['properties']['name'];id=pa_matches.get(name)
 if not id:continue
 c,area=projected_centroid(f['geometry'])
 old=next((p for p in pois if p['id']==id),None)
 pois=[p for p in pois if p['id']!=id]
 add(id,c[0],c[1],source=PA_URL,evidence=name,method='official-path-advisor-geographic-outline-centroid',accuracyMeters=None,accuracyNote='Official Path Advisor does not state survey accuracy. This point is the area-weighted centroid of its published geographic base-map drawing, with holes removed, and may lie in a courtyard for concave or multipart outlines.',referencePointNote='Plan-outline centroid for label placement only; not an entrance or measured as-built centroid.',sourceRevision='not stated; endpoint retrieved 2026-09-05',sourceBuildingId=f['properties']['building_id'],sourceGeometryType=f['geometry']['type'],sourceDrawingAreaSqMeters=round(float(area),3),supersededReference=old)

assert len({p['id']for p in pois})==len(pois)
(ROOT/'hkust-pois.json').write_text(json.dumps(pois,ensure_ascii=False,indent=2))
coverage={'checked_at':'2026-09-05','poi_count':len(pois),'direct_official_coordinate_references':sum(p['accuracyMeters']is None for p in pois),'map_registered_reference_points':sum(p['accuracyMeters']is not None for p in pois),'unplaced':[{'id':e['id'],'name_en':e['name_en']}for e in entities.values() if e['id']not in {p['id']for p in pois}],'warning':'Named nested facilities, far-west/north residences and uncalibrated edge facilities are left unplaced. 75 source entity records include nested spaces and grouped multiple buildings, so they are not 75 independent buildings.'}
(ROOT/'hkust-poi-coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))

# Audit graphic: blue circles are selected source pixels; orange numbered
# crosses are registration controls. Label IDs match the JSON entities.
im=Image.open(maps/'campus.png').convert('RGB');d=ImageDraw.Draw(im)
for c in controls:
 x,y=c['mapPixel'];d.line([(x-7,y),(x+7,y)],fill='#c34d00',width=3);d.line([(x,y-7),(x,y+7)],fill='#c34d00',width=3);d.text((x+8,y-10),f"S{c['senMarkerIndex']}",fill='#a34200')
for p in pois:
 if 'mapPixel'in p:
  x,y=p['mapPixel'];d.ellipse((x-5,y-5,x+5,y+5),outline='#174fd0',width=3);d.text((x+7,y+5),p['id'],fill='#174fd0')
im.save(ROOT/'hkust-poi-map-audit.png')
print(json.dumps({'count':len(pois),'fit_rmse_m':registration['fit_rmse_m'],'leave_one_out_rmse_m':registration['leave_one_out_rmse_m'],'leave_one_out_max_m':registration['leave_one_out_max_residual_m'],'direct':coverage['direct_official_coordinate_references'],'map':coverage['map_registered_reference_points']},indent=2))
