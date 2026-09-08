# coding: utf-8
import pathlib,json,struct,hashlib,math
R=pathlib.Path(__file__).resolve().parents[1];P=R/'public';errors=[]
def check(v,msg):
 if not v:errors.append(msg)
m=json.loads((P/'models/preview-manifest.json').read_text());tri=0
for t in m['tiles']:
 p=P/'models'/t['url'];check(p.exists(),str(p));b=p.read_bytes();check(b[:4]==b'glTF' and struct.unpack_from('<I',b,8)[0]==len(b),'GLB header '+t['id']);check(hashlib.sha256(b).hexdigest()==t['sha256'],'GLB hash '+t['id']);check(len(t['matrix'])==16 and all(math.isfinite(x) for x in t['matrix']),'matrix '+t['id']);tri+=t['triangles']
i=json.loads((P/'interiors/manifest.json').read_text());parts=0;cad=0
for f in i['floors']:
 d=json.loads((P/'interiors'/f['url']).read_text());parts+=len(d['rooms'])
 for room in d['rooms']:
  check(math.isfinite(room['heightSourceZ']),'Room sourceZ');check(all(ring[0]==ring[-1] for ring in room['rings']),'Unclosed ring')
  if room.get('interactive') is False:check(not room['name'],'Background label')
 if d.get('cad'):
  c=d['cad'];p=P/'interiors'/c['url'];check(p.stat().st_size==c['vertexCount']*12,'CAD length '+f['id']);cad+=1
catalog=json.loads((P/'data/catalog.json').read_text());photos=set()
for f in catalog['floors']:check((P/f['image'].lstrip('/')).exists(),'Floor image '+f['id'])
for p in catalog['photos']:check((P/p['image'].lstrip('/')).exists(),'Photo '+p['id']);photos.add(p['image'])
pa=json.loads((P/'data/panoramas.json').read_text());ids={n['id'] for n in pa['nodes']}
for n in pa['nodes']:
 paths=n['faces'].values() if n['projection']=='cube' else [n['image']]
 for path in paths:check((P/path.lstrip('/')).exists(),'Panorama '+str(path))
for e in pa['edges']:check(e['from_panorama_node_id'] in ids and e['to_panorama_node_id'] in ids,'Panorama endpoint')
result={'checkedAt':'2026-09-05','status':'pass' if not errors else 'fail','errors':errors,'geometryTiles':len(m['tiles']),'triangles':tri,'floorCount':len(i['floors']),'polygonParts':parts,'cadFloors':cad,'photoAssets':len(photos),'cachedPanoramas':len(pa['nodes']),'verifiedCachedEdges':len(pa['edges']),'allRuntimeLocalAssetsExist':not errors}
(R/'docs/data-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
# Second-pass additions: exact dependency and byte integrity, not subjective accuracy.
v2={}
for folder,key in [('terrain/detail','tiles'),('models/hires','patches')]:
 d=json.loads((P/folder/'manifest.json').read_text())
 tiles=d[key] if key=='tiles' else [t for patch in d[key] for level in patch['levels'].values() for t in level['tiles']]
 for tile in tiles:
  b=(P/folder/tile['url']).read_bytes();check(hashlib.sha256(b).hexdigest()==tile['sha256'],'V2 asset hash '+tile['id']);check(b[:4]==b'glTF','V2 GLB '+tile['id'])
 v2[folder]={'entries':len(d[key]),'referencedGlbs':len(tiles),'trianglesAcrossLevels':sum(t['triangles'] for t in tiles)}
hi=json.loads((P/'models/hires/manifest.json').read_text());baseids={t['id'] for t in m['tiles']}
for patch in hi['patches']:check(set(patch['baselineIds'])<=baseids,'Missing baseline '+patch['id'])
tx=json.loads((P/'models/texture-detail-manifest.json').read_text());unique={v['url']:v for t in tx['tiles'] for v in t['materials'].values()}
for path,v in unique.items():check(hashlib.sha256((P/path.lstrip('/')).read_bytes()).hexdigest()==v['sha256'],'Original texture hash')
standalone=json.loads((P/'models/standalone/manifest.json').read_text())
for b in standalone['buildings']:
 gltf=P/'models/standalone'/b['url'];d=json.loads(gltf.read_text())
 for item in d.get('buffers',[])+d.get('images',[]):
  if item.get('uri') and not item['uri'].startswith('data:'):check((gltf.parent/item['uri']).exists(),'Standalone missing dependency')
index=json.loads((P/'interiors/room-index.json').read_text());check(len(index)==4301,'Complete interactive polygon-part search index')
result.update({'status':'pass' if not errors else 'fail','errors':errors,'v2':v2,'originalTextureFiles':len(unique),'standaloneBuildings':len(standalone['buildings']),'searchableRoomParts':len(index)})
(R/'docs/data-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('V2',json.dumps(result,ensure_ascii=False));raise SystemExit(bool(errors))
