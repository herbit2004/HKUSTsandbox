#!/usr/bin/env python3
"""Fetch only the37 previously audited UG10-intersecting source terminal leaves.
No missing sibling retries; immutable B3DM/GLB sources and per-tree transforms retained.
Requires numpy, Pillow, affine, rasterio; URLs come from saved official source manifests.
"""
import argparse,concurrent.futures,hashlib,io,json,math,shutil,struct,subprocess,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize
from hkust_source_geometry import geometry

parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args();P=args.project;D=args.output or P/'public/models/hires/partial-ug10';D.mkdir(parents=True,exist_ok=True);C=args.cache;C.mkdir(parents=True,exist_ok=True);audit=json.loads(args.audit.read_text());focus=audit['focusBoundsXZ'];items=[]
for tree in audit['subtrees']:
 portable=P/'source-geodata/mesh'/tree['sheet'];source=portable if (portable/'source-zip-index.json').exists() else Path(tree['sourceZipIndexPath']).parent;tree['sourceZipIndexPath']=str(source/'source-zip-index.json');tree['sourceTreePath']=str(source/tree['subtree']/'source-tileset.json');url=json.loads((source/'subset-manifest.json').read_text())['source'];index=json.loads(Path(tree['sourceZipIndexPath']).read_text());source_tree=json.loads(Path(tree['sourceTreePath']).read_text());assert not any('transform'in child for child in source_tree['root'].get('children',[]))
 for branch in tree['branches']:
  for a in branch['levels']['fine']['assets']:
   b=a['knownBounds']
   if not(b['min'][0]<=focus['max'][0]and b['max'][0]>=focus['min'][0]and b['min'][2]<=focus['max'][1]and b['max'][2]>=focus['min'][1]):continue
   assert a['original_geometric_error']==0 and a['source_name']in index;items.append((tree,a,index[a['source_name']],url))
assert len(items)==37 and len({a['id']for _,a,_,_ in items})==37

def mip_bytes(w,h):
 n=0
 while True:
  n+=w*h*4
  if w==h==1:return n
  w=max(1,w//2);h=max(1,h//2)

def fetch(item):
 tree,a,e,url=item;name=a['source_name'];cache=C/(a['id']+'.b3dm');cache.parent.mkdir(parents=True,exist_ok=True)
 legacy=C/name
 if not cache.exists() and legacy.exists():shutil.copy2(legacy,cache)
 if not cache.exists():
  start=e['offset'];part=cache.with_suffix('.zip-part');r=subprocess.run(['/usr/bin/curl','--fail','--silent','--show-error','--location','--range',f'{start}-{start+e["compressed"]+1024}','--max-filesize',str(e['compressed']+2048),'--max-time','45','--retry','2','--retry-all-errors','--retry-delay','1','--output',str(part),'--write-out','%{http_code}',url],capture_output=True)
  assert r.returncode==0,(name,r.stderr.decode());assert r.stdout==b'206',(name,r.stdout)
  raw=part.read_bytes();header=struct.unpack_from('<4s5H3L2H',raw);assert header[0]==b'PK\x03\x04';offset=30+header[-2]+header[-1];payload=raw[offset:offset+e['compressed']];payload=zlib.decompress(payload,-15)if e['compression']==8 else payload;assert len(payload)==e['size']and zlib.crc32(payload)==e['crc32'];cache.write_bytes(payload);part.unlink()
 payload=cache.read_bytes();assert len(payload)==e['size']and zlib.crc32(payload)==e['crc32'];head=struct.unpack_from('<4s6I',payload);offset=28+sum(head[3:]);raw=payload[offset:];assert raw[:4]==b'glTF'and struct.unpack_from('<I',raw,8)[0]==len(raw);dest=D/(Path(name).stem+'.glb');dest.write_bytes(raw)
 n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);binary=raw[28+n:];textures=[]
 for im in g.get('images',[]):
  bv=g['bufferViews'][im['bufferView']];bb=binary[bv.get('byteOffset',0):bv.get('byteOffset',0)+bv['byteLength']]
  with Image.open(io.BytesIO(bb))as pic:w,h=pic.size;pic.verify()
  textures.append({'width':w,'height':h,'encodedBytes':len(bb),'mipBytes':mip_bytes(w,h),'sha256':hashlib.sha256(bb).hexdigest()})
 matrix=tree['baselineSourceMatrix'];tri,_=geometry(dest,np.array(matrix).reshape(4,4,order='F'));low=tri.min((0,1));high=tri.max((0,1));assert np.isfinite(tri).all()
 tile={'id':a['id'],'url':'partial-ug10/'+dest.name,'matrix':matrix,'bounds':{'min':low.tolist(),'max':high.tolist()},'center':((low+high)/2).tolist(),'triangles':len(tri),'vertices':sum(g['accessors'][p['attributes']['POSITION']]['count']for m in g['meshes']for p in m['primitives']),'bytes':len(raw),'textureBytes':sum(t['width']*t['height']*4 for t in textures),'textureMipBytes':sum(t['mipBytes']for t in textures),'textureEncodedBytes':sum(t['encodedBytes']for t in textures),'textures':textures,'textureDimensions':[[t['width'],t['height']]for t in textures],'sha256':hashlib.sha256(raw).hexdigest(),'sourceB3dmSha256':hashlib.sha256(payload).hexdigest(),'sourceZipCRC32':e['crc32'],'sourceZipName':name,'sourceZipOffset':e['offset'],'sourceUrl':url,'sourceB3dmCachePath':str(cache),'originalError':0,'matrixSourceBaselineId':tree['baselineId']}
 print('SOURCE',name,len(tri),'tri',round(tile['textureMipBytes']/1048576,2),'mipMiB',flush=True);return tile,tri

with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:results=list(pool.map(fetch,items))
tiles=[r[0]for r in results];tri=np.concatenate([r[1]for r in results]);low=tri.min((0,1));high=tri.max((0,1));x0,z0=np.floor(low[[0,2]]);x1,z1=np.ceil(high[[0,2]]);res=.5;w=int(round((x1-x0)/res));h=int(round((z1-z0)/res));cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);xz=tri[:,:,[0,2]];ok=abs(cross[:,1])>1e-9
mask=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in xz[ok]),out_shape=(h,w),transform=Affine(res,0,x0,0,res,z0),dtype='uint8',all_touched=False);Image.fromarray(mask).save(D/'coverage.png')
mask_meta={'url':'partial-ug10/coverage.png','minX':float(x0),'minZ':float(z0),'maxX':float(x1),'maxZ':float(z1),'width':w,'height':h,'pixelSizeMeters':res,'coveredPixels':int((mask>0).sum()),'source':'Actual non-degenerate source triangle projection of the37 specifically selected terminal leaves across four source trees, pixel-centre rasterization. No bbox or hull replacement.','sha256':hashlib.sha256((D/'coverage.png').read_bytes()).hexdigest()}
level={'tiles':tiles,'triangles':sum(t['triangles']for t in tiles),'bytes':sum(t['bytes']for t in tiles),'textureBytes':sum(t['textureBytes']for t in tiles),'textureMipBytes':sum(t['textureMipBytes']for t in tiles),'vertices':sum(t['vertices']for t in tiles),'mask':mask_meta,'sourceFrontier':{'threshold':0,'maximumOriginalError':0,'complete':True,'terminalLeaves':True,'scope':'All37 selected terminal leaves are present. This is not the whole area of any of the four parent source trees.'}}
base=json.loads((P/'public/models/preview-manifest.json').read_text());byid={t['id']:t for t in base['tiles']};ids=[t['baselineId']for t in audit['subtrees']]
patch={'id':'ug10-terminal-leaves-partial','sheet':'12-NW-11A and12-NW-6C','partial':True,'baselineIds':ids,'baselineTriangles':sum(byid[i]['triangles']for i in ids),'baselineBytes':sum(byid[i]['bytes']for i in ids),'bounds':{'min':low.tolist(),'max':high.tolist()},'center':((low+high)/2).tolist(),'levels':{'high':level},'mask':mask_meta,'evidence':{'selection':'Only original error0 terminal leaves whose conservative source-node bounds intersect the fixed official UG Hall X drawing bounds. Selected leaves are not cropped or assigned as sole building ownership.','selectionBoundsXZ':focus,'sourceBranches':[{'subtree':t['subtree'],'baselineSourceMatrix':t['baselineSourceMatrix'],'sourceRootTransform':t['sourceRootTransform'],'missingDirectSiblings':t['missingDirectSiblings'],'sourceTreeSha256':hashlib.sha256(Path(t['sourceTreePath']).read_bytes()).hexdigest(),'sourceZipIndexSha256':hashlib.sha256(Path(t['sourceZipIndexPath']).read_bytes()).hexdigest()}for t in audit['subtrees']],'completeBranch':False,'notACompleteSubtree':'Only37 spatially selected source leaves are included. Retain baseline outside actual projected coverage, including all known missing sibling regions.','sourceAudit':'branch-audit.json','levelMeaning':'The high API slot itself contains only source error0 terminal leaves; ultra may reuse this same level without another copy.','sourceCRCAndPayloadRetained':True,'floaterCheckPending':True}}
(D/'manifest-pending-floater-qa.json').write_text(json.dumps({'version':1,'patches':[patch]},indent=2));shutil.copy2(args.audit,D/'branch-audit.json');np.savez_compressed(C/'qa-triangles.npz',triangles=tri);summary={'status':'source-extracted-pending-floater-check','patch':patch['id'],'tiles':len(tiles),'triangles':level['triangles'],'sourcePayloadBytes':sum(e['size']for _,_,e,_ in items),'textureBaseMiB':level['textureBytes']/1048576,'exactTextureMipMiB':level['textureMipBytes']/1048576,'maskMiB':w*h*4/1048576,'mask':mask_meta};(D/'extraction-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
