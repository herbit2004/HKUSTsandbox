import pathlib,json,urllib.request,urllib.parse,concurrent.futures,time,collections,hashlib
ROOT=pathlib.Path('/tmp/hkust-pathadvisor-complete');CAT=json.load(open(ROOT/'building-floor-catalog.json'));BASE='https://navigate.ust.hk/path/api'
items=[{'building_id':b['building_id'],'building_name':b['name'],**f} for b in CAT for f in b['floors']]
# Prioritize academic building and then listed official buildings.
items.sort(key=lambda f:(f['building_id']!='b00000000000000000000001',f['building_name'],f.get('elevation','')))

def get(kind,f):
 path=ROOT/'floors'/f['_id'];path.mkdir(parents=True,exist_ok=True)
 filename=path/(kind+'-response.json');url=BASE+'/app/building-floors/'+kind+'?'+urllib.parse.urlencode({'building_floor_id':f['_id']})
 if f['_id']=='bf0000000000000000000108':
  known=ROOT/('academic-1-'+kind+'-response.json')
  if known.exists():filename.write_bytes(known.read_bytes())
 if filename.exists():b=filename.read_bytes();headers={};status=200
 else:
  for attempt in range(3):
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=50) as r:b=r.read();status=r.status;headers=dict(r.headers)
    filename.write_bytes(b);break
   except Exception:
    if attempt==2:raise
    time.sleep(1+attempt)
  time.sleep(.25)
 data=json.loads(b);return data,{'endpoint':url,'http_status':status,'meta':data.get('meta'),'headers':headers,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'raw_file':str(filename.relative_to(ROOT))}

def floor(f):
 path=ROOT/'floors'/f['_id'];path.mkdir(parents=True,exist_ok=True);summary={**f,'sources':[],'errors':[]}
 for kind in ['geojson','nav-nodes','point-of-interests']:
  try:
   data,source=get(kind,f);summary['sources'].append(source)
   if data.get('meta',{}).get('code')!=200:summary['errors'].append({'endpoint':kind,'meta':data.get('meta')});continue
   if kind=='geojson':
    obj=data.get('data',{}).get('building_floor',{})
    for key in ['geojson','cad_geojson']:
     g=obj.get(key)
     if isinstance(g,str):g=json.loads(g)
     if g:
      target=path/('rooms.geojson' if key=='geojson' else 'cad-lines.geojson');target.write_text(json.dumps(g,separators=(',',':'),ensure_ascii=False))
      features=g.get('features',[]);summary[key+'_file']=str(target.relative_to(ROOT));summary[key+'_feature_count']=len(features)
      summary[key+'_geometry_types']=dict(collections.Counter(x['geometry']['type'] for x in features))
      if key=='geojson':
       summary['room_type_counts']=dict(collections.Counter(x.get('properties',{}).get('type_name','') for x in features));summary['hidden_from_map_count']=sum(bool(x.get('properties',{}).get('hidden_from_map')) for x in features)
       zs=set()
       def collect(a):
        if isinstance(a,list) and a:
         if isinstance(a[0],(int,float)):
          if len(a)>2:zs.add(a[2])
         else:
          for b in a:collect(b)
       for x in features:collect(x['geometry'].get('coordinates',[]))
       summary['source_z_values']=sorted(zs)
   else:
    key='nav_nodes' if kind=='nav-nodes' else 'point_of_interests';a=data.get('data',{}).get(key,[]);(path/(kind+'.json')).write_text(json.dumps(a,separators=(',',':'),ensure_ascii=False));summary[kind+'_count']=len(a)
  except Exception as e:summary['errors'].append({'endpoint':kind,'error':str(e)})
 (path/'manifest.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print(f['building_name'],f['name'],summary.get('geojson_feature_count',0),'polygons',summary.get('nav-nodes_count',0),'nodes','errors',summary['errors'],flush=True);return summary

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:reports=list(pool.map(floor,items))
manifest={'retrieved_at':'2026-09-05','official_app':'https://navigate.ust.hk/path/app/','discovered_from_script':'https://navigate.ust.hk/path/app/static/js/main.c4c44c26.js','script_last_modified':'2026-08-22','method':'Public GET endpoints explicitly referenced by the official published app JavaScript, without cookies, Authorization header, login, or token. Building IDs from the app all-base-map GeoJSON; floor IDs from public per-building floor catalog. Limited to two workers and 0.25-second pause after new responses.','license_note':'HKUST official data. No open-data redistribution license was verified. Keep source attribution and scope of local campus-learning use; do not imply government CSDI terms cover university data.','crs_note':'Coordinates are in longitude/latitude as used by the official MapLibre app. Rooms include source Z values; Z vertical datum and building floor elevations require verification before combining with government mesh. The catalog elevation field is a floor ordinal, not a meter height. CAD linework may have no Z.','rendering_note':'Respect source hidden_from_map for labels/details, preserving original geometry and visibility flags. Polygon feature IDs and nav node positions are true published data, not inferred room layouts. Nav nodes do not by themselves provide complete edges or access restrictions.','building_count':len(CAT),'listed_floor_count':len(items),'floors':reports}
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('ALL FLOORS DONE',len(reports),sum(x.get('geojson_feature_count',0) for x in reports),'features',sum(x.get('nav-nodes_count',0) for x in reports),'nodes',flush=True)
