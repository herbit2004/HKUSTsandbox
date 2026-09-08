import pathlib,json,urllib.request,concurrent.futures,time,hashlib
ROOT=pathlib.Path('/tmp/hkust-pathadvisor-complete');manifest=json.load(open(ROOT/'manifest.json'));items=manifest['floors']
def run(f):
 path=ROOT/'floors'/f['_id'];u='https://navigate.ust.hk/path/api/app/panorama-edges?building_floor_id='+f['_id'];raw=path/'panorama-edges-response.json'
 if f['_id']=='bf0000000000000000000108':raw.write_bytes((ROOT/'academic-1-panorama-edges-response.json').read_bytes())
 try:
  if raw.exists():b=raw.read_bytes();headers={}
  else:
   with urllib.request.urlopen(u,timeout=50) as r:b=r.read();headers=dict(r.headers)
   raw.write_bytes(b);time.sleep(.25)
  d=json.loads(b);edges=d.get('data',{}).get('panorama_edges',[]);clean=[{k:v for k,v in n.items() if k not in ['created_by','updated_by']} for n in edges];(path/'panorama-edges.json').write_text(json.dumps(clean,separators=(',',':')))
  result={'floor_id':f['_id'],'building':f['building_name'],'floor':f['name'],'endpoint':u,'meta':d.get('meta'),'count':len(edges),'raw_file':str(raw.relative_to(ROOT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};(path/'panorama-edges-manifest.json').write_text(json.dumps(result,indent=2));return result
 except Exception as e:return {'floor_id':f['_id'],'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(run,items))
(ROOT/'panorama-edges-index.json').write_text(json.dumps(r,indent=2));print('ALL PANORAMA EDGES DONE',len(r),'floors',sum(x.get('count',0) for x in r),'returned edges')
