"""Download a finite, attributed campus subset of HK Government open geodata.
Uses HTTP byte ranges, retains original geometric content, prunes fine LOD.
"""
import urllib.request,json,struct,zlib,pathlib,concurrent.futures,time,zipfile,io,copy,hashlib
ROOT=pathlib.Path('/tmp/hkust-geodata');ROOT.mkdir(exist_ok=True)
TILES=['11-NE-10B','11-NE-10D','11-NE-15B','12-NW-6A','12-NW-6C','12-NW-11A']
THRESHOLD=7.0
metadata=json.load(open('/tmp/hkust-geodata-1.txt'))
index={f['properties']['SHEETNO']:f for f in metadata['features']}
dtmindex={f['properties']['TILE_NAME']:f for f in json.load(open('/tmp/hkust-dtm-index.geojson'))['features']}

def get(url,byte_range=None):
 for i in range(4):
  try:
   req=urllib.request.Request(url,headers={'Range':byte_range} if byte_range else {})
   with urllib.request.urlopen(req,timeout=60) as r:
    if byte_range and r.status!=206:raise RuntimeError('Range request was not honored')
    return r.read()
  except Exception:
   if i==3:raise
   time.sleep(0.5*(i+1))

class RangeZip:
 def __init__(self,u):
  self.url=u
  tail=get(u,'bytes=-65536');pos=tail.rfind(b'PK\x05\x06');e=struct.unpack_from('<4s4H2LH',tail,pos)
  cs,co=e[-3],e[-2];central=get(u,f'bytes={co}-{co+cs-1}');entries={};i=0
  while i<len(central):
   h=struct.unpack_from('<4s6H3L5H2L',central,i);assert h[0]==b'PK\x01\x02'
   name=central[i+46:i+46+h[10]].decode();entries[name]={'compressed':h[8],'size':h[9],'offset':h[-1],'compression':h[4],'crc32':h[7]};i+=46+h[10]+h[11]+h[12]
  self.entries=entries
 def read(self,name):
  e=self.entries[name];o=e['offset'];b=get(self.url,f"bytes={o}-{o+e['compressed']+1024}")
  h=struct.unpack_from('<4s5H3L2H',b);assert h[0]==b'PK\x03\x04'
  start=30+h[-2]+h[-1];v=b[start:start+e['compressed']]
  if e['compression']==8:v=zlib.decompress(v,-15)
  assert len(v)==e['size'] and zlib.crc32(v)==e['crc32'],name
  return v

def fix_volumes(node):
 for k in ['boundingVolume','viewerRequestVolume']:
  if k in node and len(node[k].get('sphere',[]))==12:node[k]['box']=node[k].pop('sphere')
 for c in node.get('children',[]):fix_volumes(c)

def prep_tile(tile):
 d=ROOT/'mesh'/tile;d.mkdir(parents=True,exist_ok=True)
 z=RangeZip(index[tile]['properties']['Format_3D_Tiles'])
 (d/'source-zip-index.json').write_text(json.dumps(z.entries))
 raw=z.read('tileset.json');r=json.loads(raw);(d/'source-tileset.json').write_bytes(raw)
 jobs=[];counts={};originals=[]
 for ch in r['root']['children']:
  path=ch['content'].get('uri',ch['content'].get('url')).removeprefix('./')
  original=z.read(path);sub=json.loads(original);(d/path).parent.mkdir(parents=True,exist_ok=True)
  (d/path.replace('tileset.json','source-tileset.json')).write_bytes(original)
  prefix=str(pathlib.PurePosixPath(path).parent)
  def prune(node):
   content=node.get('content',{});uri=content.get('uri',content.get('url'))
   name=prefix+'/'+uri.removeprefix('./') if uri else None
   available=name in z.entries if name else False
   children=node.get('children',[])
   if available and (node.get('geometricError',0)<=THRESHOLD or not children):
    node.pop('children',None);node['geometricError']=0
    return True,[name]
   selected=[];complete=True
   for c in children:
    ok,assets=prune(c);complete=complete and ok;selected.extend(assets)
   if not children or not complete:
    if available:
     node.pop('children',None);node['geometricError']=0
     return True,[name]
    return False,[]
   node.pop('content',None)
   return True,selected
  ok,assets=prune(sub['root']);assert ok,path;jobs.extend(assets);fix_volumes(sub['root']);(d/path).write_text(json.dumps(sub,separators=(',',':')))
 fix_volumes(r['root']);(d/'tileset.json').write_text(json.dumps(r,separators=(',',':')))
 total=sum(z.entries[n]['size'] for n in set(jobs)); print(tile,'frontier assets',len(jobs),'bytes',total,flush=True)
 for j,name in enumerate(jobs):
  p=d/name
  if p.exists() and p.stat().st_size==z.entries[name]['size']:continue
  v=z.read(name);assert v[:4] in [b'b3dm',b'glTF'];p.write_bytes(v)
  if j%40==0:print(tile,'download',j+1,'/',len(jobs),flush=True)
 result={'tile':tile,'model_uri':f'mesh/{tile}/tileset.json','assets':len(jobs),'bytes':total,'revision_ms':index[tile]['properties']['REVISIONDATE'],'source':index[tile]['properties']['Format_3D_Tiles'],'footprint_wgs84':index[tile]['geometry']}
 (d/'subset-manifest.json').write_text(json.dumps(result,indent=2));print(tile,'DONE',flush=True);return result

def prep_dtm(tile):
 f=dtmindex[tile.replace('-','')];u=f['properties']['URL'];d=ROOT/'dtm';d.mkdir(exist_ok=True);p=d/f['properties']['Filename'];b=p.read_bytes() if p.exists() else get(u)
 (d/f['properties']['Filename']).write_bytes(b)
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  for name in z.namelist():
   if pathlib.Path(name).name!=name:raise ValueError('Unexpected nested path')
   (d/name).write_bytes(z.read(name))
 return f

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 dtms=list(pool.map(prep_dtm,TILES))
(ROOT/'dtm-index.geojson').write_text(json.dumps({'type':'FeatureCollection','features':dtms},indent=2));print('DTM six tiles DONE',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(prep_tile,TILES))
manifest={'retrieved_at':'2026-09-05','sources':['https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1671677054006_62261/html','https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html'],'terms':'https://portal.csdi.gov.hk/csdi-webpage/doc/TNC','credit':'3D Visualisation Map from Lands Department; LiDAR DTM from Civil Engineering and Development Department, Hong Kong SAR Government. All original data intellectual property belongs to the Government.','mesh_lod_max_original_geometric_error':THRESHOLD,'mesh_changes':['Retain one complete geometric frontier per source child tree; finer LOD omitted for compact campus preview. Original mesh and texture bytes unmodified.','Correct source 12-component boundingVolume.sphere arrays to OGC boundingVolume.box; coordinate and extent values retained.','Set terminal subset tile geometricError to 0 because finer detail is not included.','Where source JSON refers to absent mesh assets, fall back to the closest available ancestor mesh to preserve coverage; these few subareas retain coarser detail than the target threshold.'],'dtm':'2019-12-20 to 2020-02-02 survey. GeoTIFF 0.5m Float32, EPSG:2326 HK1980 Grid, pixel-is-area, NoData=-9999. Do not equate metadata revision to capture date.','tiles':results}
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('ALL DONE',str(ROOT),sum(r['bytes'] for r in results),flush=True)
