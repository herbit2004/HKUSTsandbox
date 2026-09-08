from pathlib import Path
from PIL import Image
import json,struct,io,hashlib
root=Path(__file__).resolve().parents[1]/'public/models'
manifest=json.loads((root/'render-manifest.json').read_text())
out={'version':1,'source':'render-manifest.json','method':'Embedded original image bytes extracted unchanged. Geometry is not duplicated when textures switch. GPU bytes estimated as width*height*4 without mipmaps.','tiles':[]}
for tile in manifest['tiles']:
 b=(root/tile['url']).read_bytes();n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);raw=b[28+n:];images=[]
 for i,image in enumerate(d.get('images',[])):
  v=d['bufferViews'][image['bufferView']];data=raw[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];im=Image.open(io.BytesIO(data));extension='png' if image['mimeType']=='image/png' else 'jpg';sha=hashlib.sha256(data).hexdigest();url=f'original-textures/{sha}.{extension}';p=root/url;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
  images.append({'url':'/models/'+url,'width':im.width,'height':im.height,'bytes':len(data),'decodedBytes':im.width*im.height*4,'sha256':sha})
 maps={}
 for i,m in enumerate(d.get('materials',[])):
  index=m.get('pbrMetallicRoughness',{}).get('baseColorTexture',{}).get('index')
  if index is not None:maps[str(i)]=images[d['textures'][index]['source']]
 out['tiles'].append({'id':tile['id'],'center':tile['center'],'bounds':tile['bounds'],'materials':maps})
out['stats']={'tiles':len(out['tiles']),'images':sum(len(t['materials']) for t in out['tiles']),'uniqueFiles':len(list((root/'original-textures').iterdir())),'originalBytes':sum(p.stat().st_size for p in (root/'original-textures').iterdir()),'maxDimension':max(max(m['width'],m['height']) for t in out['tiles'] for m in t['materials'].values()),'allDecodedBytes':sum(m['decodedBytes'] for t in out['tiles'] for m in t['materials'].values())}
(root/'texture-detail-manifest.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
print(out['stats'])
