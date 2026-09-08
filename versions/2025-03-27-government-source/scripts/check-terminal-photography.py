#!/usr/bin/env python3
"""Re-read delivered terminal GLBs, original B3DMs, source tree and recorded metadata."""
import argparse,hashlib,io,json,struct,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from hkust_source_geometry import geometry
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--cache',type=Path,required=True);args=ap.parse_args();P=args.project
reports=[]
for folder in sorted((P/'public/models/hires/terminal').iterdir()):
 if not folder.is_dir() or not(folder/'manifest.json').exists():continue
 patch=json.load(open(folder/'manifest.json'))['patches'][0];level=patch['levels']['fine'];tree=json.load(open(P/'public/models/hires/sources'/patch['id']/'source-tileset.json'));nodes={}
 def walk(n):
  uri=n.get('content',{}).get('uri')
  if uri:nodes[patch['id']+'/'+uri]=n
  for c in n.get('children',[]):walk(c)
 walk(tree['root']);matrices={tuple(t['matrix'])for t in patch['levels']['high']['tiles']};assert len(matrices)==1;matrix=next(iter(matrices));triangles=0;images=0;max_bound_error=0.
 for t in level['tiles']:
  path=P/'public/models/hires'/t['url'];raw=path.read_bytes();source=(args.cache/t['sourceZipName']).read_bytes();head=struct.unpack_from('<4s6I',source);assert head[0]==b'b3dm' and head[2]==len(source);assert source[28+sum(head[3:]):]==raw
  assert hashlib.sha256(raw).hexdigest()==t['sha256'] and hashlib.sha256(source).hexdigest()==t['sourceB3dmSha256'];assert zlib.crc32(source)==t['sourceZipCRC32'];assert tuple(t['matrix'])==matrix
  n=nodes[t['sourceZipName']];assert n['geometricError']==0 and not n.get('children');tr,_=geometry(path,np.array(matrix).reshape(4,4,order='F'));assert len(tr)==t['triangles'];triangles+=len(tr);max_bound_error=max(max_bound_error,float(abs(tr.min((0,1))-t['bounds']['min']).max()),float(abs(tr.max((0,1))-t['bounds']['max']).max()))
  jl=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+jl]);binary=raw[28+jl:];dimensions=[]
  for image in g.get('images',[]):
   view=g['bufferViews'][image['bufferView']];data=binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']];im=Image.open(io.BytesIO(data));dimensions.append([im.width,im.height]);images+=1
  assert dimensions==t['textureDimensions']
 assert triangles==level['triangles'] and max_bound_error<1e-9
 report={'status':'pass','patch':patch['id'],'terminalSourceNodesVerified':len(level['tiles']),'sourceB3dmPayloadAndCRCChecks':len(level['tiles']),'triangles':triangles,'textureImageDimensionsChecked':images,'maximumWorldBoundsDifferenceMeters':max_bound_error,'allMatricesExactlyEqualVerifiedHighSourceMatrix':True,'allSelectedSourceErrorsZeroAndNoChildren':True,'sourceOriginalBytesRetained':True,'exactTextureMipBytes':level['textureMipBytes'],'limitations':'Source and derived-placement checks; browser loading and visual acceptance are separate.'};(folder/'independent-qa.json').write_text(json.dumps(report,indent=2));reports.append(report)
(P/'public/models/hires/terminal/independent-qa.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
