#!/usr/bin/env python3
"""Bounded official source branch extraction; preserves source GLB bytes and placement.
Dependencies: numpy, Pillow, rasterio. curl is used only for exact missing ZIP entries.
"""
import sys,json,struct,zlib,subprocess,concurrent.futures,hashlib,io,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize
import argparse
from hkust_source_geometry import select, geometry
ap=argparse.ArgumentParser(description="Extract one complete L17_00 frontier, never claim all6C1 complete.")
ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
ap.add_argument('--source',type=Path,required=True,help='Downloaded12-NW-6C source directory with ZIP index and source tileset')
ap.add_argument('--cache',type=Path,required=True,help='Retain original B3DM assets; downloads only missing exact ZIP entries')
ap.add_argument('--output',type=Path)
ap.add_argument('--level',choices=['high','fine'],default='high')
ap.add_argument('--subtree',choices=['12-NW-6C-1','12-NW-6C-7'],default='12-NW-6C-1')
args=ap.parse_args();level_name=args.level;threshold=.9 if level_name=='high' else 0.;sub=args.subtree; stem='Tile_300_147' if sub.endswith('-1') else 'Tile_301_146'; folder='partial-entrance' if sub.endswith('-1') else 'partial-entrance-6c7';P=args.project;S=args.source;D=args.output or P/'public/models/hires'/folder;D.mkdir(parents=True,exist_ok=True);T=args.cache;T.mkdir(parents=True,exist_ok=True)
src=json.load(open(S/sub/'source-tileset.json'));es=json.load(open(S/'source-zip-index.json'));url=json.load(open(S/'subset-manifest.json'))['source'];branch=src['root']['children'][0]['children'][0]['children'][0];selected,assets,issues=select(branch,sub,es,threshold);assert len(assets)==({'high':60,'fine':91}[level_name] if sub.endswith('-1') else {'high':56,'fine':68}[level_name]) and not issues
base=next(t for t in json.load(open(P/'public/models/render-manifest.json'))['tiles'] if t['id']=='12-NW-6C/'+sub+'/'+stem+'_L16_0');M=np.array(base['matrix']).reshape(4,4,order='F')
def job(a):
 name=a['source_name'];entry=es[name];path=T/Path(name).name
 if not path.exists():
  o=entry['offset'];part=path.with_suffix('.zip-part');r=subprocess.run(['/usr/bin/curl','--fail','--silent','--show-error','--location','--range',f'{o}-{o+entry["compressed"]+1024}','--max-filesize',str(entry['compressed']+2048),'--max-time','45','--retry','2','--retry-all-errors','--retry-delay','1','--output',str(part),'--write-out','%{http_code}',url],capture_output=True);assert r.returncode==0,(name,r.stderr.decode());assert r.stdout==b'206',(name,r.stdout)
  b=part.read_bytes();header=struct.unpack_from('<4s5H3L2H',b);assert header[0]==b'PK\x03\x04';start=30+header[-2]+header[-1];content=b[start:start+entry['compressed']];content=zlib.decompress(content,-15)if entry['compression']==8 else content;assert len(content)==entry['size'] and zlib.crc32(content)==entry['crc32'];path.write_bytes(content);part.unlink()
 b=path.read_bytes();assert len(b)==entry['size']and zlib.crc32(b)==entry['crc32'];head=struct.unpack_from('<4s6I',b);off=28+sum(head[3:]);raw=b[off:];assert raw[:4]==b'glTF';dest=D/(path.stem+'.glb');dest.write_bytes(raw);n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);binary=raw[28+n:];tx=[]
 for im in g.get('images',[]):
  v=g['bufferViews'][im['bufferView']];bb=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];pic=Image.open(io.BytesIO(bb));tx.append({'width':pic.width,'height':pic.height,'encodedBytes':len(bb)})
 tri,_=geometry(dest,M);low=tri.min((0,1));high=tri.max((0,1));decoded=sum(t['width']*t['height']*4 for t in tx)
 return {'id':'12-NW-6C/'+name.removesuffix('.b3dm'),'url':folder+'/'+dest.name,'matrix':base['matrix'],'bounds':{'min':low.tolist(),'max':high.tolist()},'center':((low+high)/2).tolist(),'triangles':len(tri),'vertices':sum(g['accessors'][p['attributes']['POSITION']]['count']for m in g['meshes']for p in m['primitives']),'bytes':len(raw),'textureBytes':decoded,'textureEncodedBytes':sum(t['encodedBytes']for t in tx),'textures':tx,'textureDimensions':[[t['width'],t['height']]for t in tx],'sha256':hashlib.sha256(raw).hexdigest(),'sourceB3dmSha256':hashlib.sha256(b).hexdigest(),'sourceZipCRC32':entry['crc32'],'sourceZipName':name,'originalError':a['original_geometric_error']},tri
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:items=list(pool.map(job,assets))
tiles=[x[0]for x in items];tri=np.concatenate([x[1]for x in items]);low=tri.min((0,1));high=tri.max((0,1));x0,z0=np.floor(low[[0,2]]);x1,z1=np.ceil(high[[0,2]]);res=.5;w=round((x1-x0)/res);h=round((z1-z0)/res);xz=tri[:,:,[0,2]];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);ok=abs(cross[:,1])>1e-9
mask=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in xz[ok]),out_shape=(h,w),transform=Affine(res,0,x0,0,res,z0),dtype='uint8',all_touched=False);mask_name='coverage.png' if level_name=='high' else 'coverage-fine.png';Image.fromarray(mask).save(D/mask_name)
level={'tiles':tiles,'triangles':sum(t['triangles']for t in tiles),'bytes':sum(t['bytes']for t in tiles),'textureBytes':sum(t['textureBytes']for t in tiles),'vertices':sum(t['vertices']for t in tiles)}
patch={'id':sub+'-partial-entrance','sheet':'12-NW-6C','partial':True,'baselineIds':[base['id']],'baselineTriangles':base['triangles'],'baselineBytes':base['bytes'],'bounds':{'min':low.tolist(),'max':high.tolist()},'center':((low+high)/2).tolist(),'levels':{level_name:level},'mask':{'url':folder+'/'+mask_name,'minX':x0,'minZ':z0,'maxX':x1,'maxZ':z1,'width':w,'height':h,'pixelSizeMeters':res,'coveredPixels':int((mask>0).sum()),'source':'Actual transformed non-degenerate triangles of all retained original source assets, pixel-centre rasterization. No bbox/hull fill.'},'evidence':{'completeBranch':stem+'_L17_00.b3dm and all selected descendants','threshold':threshold,'selectedFrontierIssues':issues,'missingSibling':sub+'/'+stem+'_L17_00_1.b3dm','missingSiblingInSourceZipIndex':False,'notACompleteSubtree':'This branch is complete; the whole parent subtree is not. Keep its baseline outside this true source triangle projection.','sourceUrl':url,'sourceTilesetSha256':hashlib.sha256((S/sub/'source-tileset.json').read_bytes()).hexdigest(),'sourceZipIndexSha256':hashlib.sha256((S/'source-zip-index.json').read_bytes()).hexdigest(),'matrixSource':'Exact verified baseline root localXYZ matrix reused; source descendants have no additional node transforms.'}}
level['mask']=patch['mask'];level['sourceFrontier']={'threshold':threshold,'maximumOriginalError':max(t['originalError']for t in tiles),'complete':True,'terminalLeaves':all(t['originalError']==0 for t in tiles)}
if (D/'manifest.json').exists():
 old=json.load(open(D/'manifest.json'))['patches'][0]
 old['levels'][level_name]=level
 if level_name=='high':old['mask']=patch['mask']
 old['bounds']={'min':np.minimum(old['bounds']['min'],low).tolist(),'max':np.maximum(old['bounds']['max'],high).tolist()};old['center']=((np.array(old['bounds']['min'])+old['bounds']['max'])/2).tolist()
 old['evidence']['levelMeaning']='high is complete0.9-error frontier; fine is complete terminal error0 leaves. Neither completes missing sibling.'
 patch=old
(D/'manifest.json').write_text(json.dumps({'version':1,'patches':[patch]},indent=2));np.savez_compressed(T/('qa-triangles-'+level_name+'.npz'),triangles=tri);print(json.dumps({'patch':patch['id'],'tiles':len(tiles),'triangles':level['triangles'],'textureMiB':level['textureBytes']/1048576,'bytes':level['bytes'],'bounds':patch['bounds'],'mask':patch['mask']},indent=2))
