#!/usr/bin/env python3
"""Bounded terminal frontiers for the four already-retained complete source regions.
Never edits the shared main manifest; emits mergeable per-region manifests.
"""
import argparse,concurrent.futures,hashlib,io,json,struct,subprocess,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from hkust_source_geometry import geometry,select

ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--existing-cache',type=Path,required=True);args=ap.parse_args();P=args.project;S=args.source;C=args.cache;C.mkdir(parents=True,exist_ok=True)
entries=json.load(open(S/'source-zip-index.json'));url=json.load(open(S/'subset-manifest.json'))['source'];main=json.load(open(P/'public/models/hires/manifest.json'))
def mip(w,h):
 total=0
 while True:
  total+=w*h*4
  if w==h==1:return total
  w=max(1,w//2);h=max(1,h//2)
reports=[]
for sub in ['12-NW-6C-6','12-NW-6C-2','12-NW-6C-11','12-NW-6C-16']:
 old=next(p for p in main['patches']if p['id']==sub);tree_path=P/'public/models/hires/sources'/sub/'source-tileset.json';tree=json.load(open(tree_path));_,assets,issues=select(tree['root'],sub,entries,0);assert not issues and all(a['original_geometric_error']==0 for a in assets)
 by_uri={}
 def walk(n):
  uri=n.get('content',{}).get('uri')
  if uri:by_uri[sub+'/'+uri]=n
  for c in n.get('children',[]):walk(c)
 walk(tree['root']);assert all(not by_uri[a['source_name']].get('children')for a in assets)
 folder='terminal/'+sub;D=P/'public/models/hires'/folder;D.mkdir(parents=True,exist_ok=True);matrix=old['levels']['high']['tiles'][0]['matrix'];M=np.array(matrix).reshape(4,4,order='F')
 existing={t['id']:t for level in old['levels'].values()for t in level['tiles']}
 if 'fine'in old and not(D/'previous-fine.json').exists():(D/'previous-fine.json').write_text(json.dumps(old['levels']['fine'],indent=2))
 def job(asset):
  name=asset['source_name'];entry=entries[name];path=C/name;path.parent.mkdir(parents=True,exist_ok=True)
  prior=args.existing_cache/name
  if not path.exists() and prior.exists():content=prior.read_bytes();assert len(content)==entry['size']and zlib.crc32(content)==entry['crc32'];path.write_bytes(content)
  if not path.exists():
   offset=entry['offset'];part=path.with_suffix('.zip-part');r=subprocess.run(['/usr/bin/curl','--fail','--silent','--show-error','--location','--range',f'{offset}-{offset+entry["compressed"]+1024}','--max-filesize',str(entry['compressed']+2048),'--max-time','45','--retry','2','--retry-all-errors','--retry-delay','1','--output',str(part),'--write-out','%{http_code}',url],capture_output=True);assert r.returncode==0,(name,r.stderr.decode());assert r.stdout==b'206';b=part.read_bytes();header=struct.unpack_from('<4s5H3L2H',b);assert header[0]==b'PK\x03\x04';start=30+header[-2]+header[-1];content=b[start:start+entry['compressed']];content=zlib.decompress(content,-15)if entry['compression']==8 else content;assert len(content)==entry['size']and zlib.crc32(content)==entry['crc32'];path.write_bytes(content);part.unlink()
  b=path.read_bytes();assert len(b)==entry['size']and zlib.crc32(b)==entry['crc32'];header=struct.unpack_from('<4s6I',b);raw=b[28+sum(header[3:]):];assert raw[:4]==b'glTF';identifier='12-NW-6C/'+name.removesuffix('.b3dm');old_tile=existing.get(identifier);target=D/(path.stem+'.glb');output_url=folder+'/'+target.name
  if old_tile and (P/'public/models/hires'/old_tile['url']).read_bytes()==raw:target=P/'public/models/hires'/old_tile['url'];output_url=old_tile['url']
  else:target.write_bytes(raw)
  n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);binary=raw[28+n:];images=[]
  for image in g.get('images',[]):
   view=g['bufferViews'][image['bufferView']];data=binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']];im=Image.open(io.BytesIO(data));images.append({'width':im.width,'height':im.height,'encodedBytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
  tr,_=geometry(target,M);lo=tr.min((0,1));hi=tr.max((0,1));return {'id':identifier,'url':output_url,'matrix':matrix,'bounds':{'min':lo.tolist(),'max':hi.tolist()},'center':((lo+hi)/2).tolist(),'triangles':len(tr),'vertices':sum(g['accessors'][p['attributes']['POSITION']]['count']for mesh in g['meshes']for p in mesh['primitives']),'bytes':len(raw),'textureBytes':sum(i['width']*i['height']*4 for i in images),'textureMipBytes':sum(mip(i['width'],i['height'])for i in images),'textureEncodedBytes':sum(i['encodedBytes']for i in images),'textureDimensions':[[i['width'],i['height']]for i in images],'textures':images,'originalError':0,'terminalLeaf':True,'sha256':hashlib.sha256(raw).hexdigest(),'sourceB3dmSha256':hashlib.sha256(b).hexdigest(),'sourceZipName':name,'sourceZipCRC32':entry['crc32']}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:tiles=list(pool.map(job,assets))
 lo=np.min([t['bounds']['min']for t in tiles],0);hi=np.max([t['bounds']['max']for t in tiles],0);level={key:sum(t[key]for t in tiles)for key in ['triangles','vertices','bytes','textureBytes','textureMipBytes','textureEncodedBytes']};level.update(tiles=tiles,bounds={'min':lo.tolist(),'max':hi.tolist()},complete=True,geometricErrorMax=0,sourceTargetGeometricError=0,sourceFrontier={'terminalLeaves':True,'threshold':0,'maximumOriginalError':0,'selectedFrontierIssues':[],'sourceTreeSha256':hashlib.sha256(tree_path.read_bytes()).hexdigest(),'sourceZipIndexSha256':hashlib.sha256((S/'source-zip-index.json').read_bytes()).hexdigest(),'sourceUrl':url})
 old['levels']['fine']=level;old['bounds']={'min':np.minimum(old['bounds']['min'],lo).tolist(),'max':np.maximum(old['bounds']['max'],hi).tolist()};old['center']=((np.array(old['bounds']['min'])+old['bounds']['max'])/2).tolist();(D/'manifest.json').write_text(json.dumps({'version':1,'patches':[old]},indent=2))
 report={k:v for k,v in level.items()if k!='tiles'};report.update(patch=sub,assets=len(tiles),exactTextureMipMiB=level['textureMipBytes']/1048576,sourceB3dmPayloadAndCRCVerified=len(tiles),sourceTreeTerminalErrorZeroVerified=len(tiles),matrixSource='Exact previously verified region high-level matrix; raw GLB nodes retained.');(D/'source-validation.json').write_text(json.dumps(report,indent=2));reports.append(report);print(json.dumps({k:report[k]for k in ['patch','assets','triangles','bytes','textureBytes','textureMipBytes','exactTextureMipMiB']},indent=2),flush=True)
(P/'public/models/hires/terminal/summary.json').write_text(json.dumps(reports,indent=2))
