import pathlib,json,urllib.request,urllib.parse,concurrent.futures,time,hashlib
ROOT=pathlib.Path('/tmp/hkust-pathadvisor-complete');manifest=json.load(open(ROOT/'manifest.json'));BASE='https://navigate.ust.hk/path/api';items=manifest['floors']
def run(f):
 path=ROOT/'floors'/f['_id'];u=BASE+'/app/panorama-nodes?building_floor_id='+f['_id'];raw=path/'panorama-nodes-response.json'
 if f['_id']=='bf0000000000000000000108':raw.write_bytes((ROOT/'academic-1-panorama-nodes-response.json').read_bytes())
 try:
  if raw.exists():b=raw.read_bytes();headers={}
  else:
   with urllib.request.urlopen(urllib.request.Request(u,headers={'Accept':'application/json'}),timeout=50) as r:b=r.read();headers=dict(r.headers)
   raw.write_bytes(b);time.sleep(.25)
  d=json.loads(b);nodes=d.get('data',{}).get('panorama_nodes',[]);public=[{k:v for k,v in n.items() if k not in ['created_by','updated_by']} for n in nodes if n.get('visibility')=='visible_to_public'];(path/'public-panorama-nodes.json').write_text(json.dumps(public,ensure_ascii=False,separators=(',',':')))
  f['panorama_source']={'endpoint':u,'meta':d.get('meta'),'headers':headers,'raw_file':str(raw.relative_to(ROOT)),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};f['public_panorama_count']=len(public);f['panorama_returned_count']=len(nodes);f['public_panorama_file']=str((path/'public-panorama-nodes.json').relative_to(ROOT));(path/'manifest.json').write_text(json.dumps(f,ensure_ascii=False,indent=2));print(f['building_name'],f['name'],len(public),'public panoramas',flush=True)
 except Exception as e:f['panorama_error']=str(e);print(f['_id'],str(e),flush=True)
 return f
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:manifest['floors']=list(pool.map(run,items))
manifest['public_panorama_count']=sum(f.get('public_panorama_count',0) for f in manifest['floors']);manifest['panorama_note']='Panorama metadata from the public app endpoint only. Derivative public-panorama-nodes.json keeps visibility=visible_to_public entries and omits creator/updater IDs. Panoramas were not downloaded by this script. Coordinates and pan/tilt/roll offsets are original provider fields; created_at/updated_at are metadata timestamps, not verified capture times.';(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('ALL PANORAMA METADATA DONE',manifest['public_panorama_count'],flush=True)
