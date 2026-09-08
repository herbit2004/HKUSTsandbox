#!/usr/bin/env python3
"""Make a texture-only browser preview; preserve all source geometry bytes.
Original extracted GLBs remain in glb/.  Requires Pillow; no network.
"""
from pathlib import Path
from PIL import Image
import json,struct,io,copy,hashlib,time
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'render-manifest.json').read_text());manifest=copy.deepcopy(manifest)
original_gpu=0;preview_gpu=0;resized=0;max_dimension=512
for tile in manifest['tiles']:
 p=ROOT/tile['url'];b=p.read_bytes();n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);bo=20+n+8;raw=b[bo:]
 image_views={im['bufferView']:im for im in d.get('images',[])};newbin=bytearray();expected_geometry=[]
 for i,v in enumerate(d['bufferViews']):
  a=v.get('byteOffset',0);data=raw[a:a+v['byteLength']]
  if i in image_views:
   im=Image.open(io.BytesIO(data));original_gpu+=im.width*im.height*4
   if max(im.size)>max_dimension:
    im.thumbnail((max_dimension,max_dimension),Image.Resampling.LANCZOS);dest=io.BytesIO();im.convert('RGB').save(dest,format='JPEG',quality=85,optimize=True);data=dest.getvalue();image_views[i]['mimeType']='image/jpeg';resized+=1
   preview_gpu+=im.width*im.height*4
  else:expected_geometry.append((i,data))
  while len(newbin)%4:newbin.append(0)
  v['byteOffset']=len(newbin);v['byteLength']=len(data);newbin+=data
 for i,expected in expected_geometry:
  v=d['bufferViews'][i];assert bytes(newbin[v['byteOffset']:v['byteOffset']+v['byteLength']])==expected
 d['buffers'][0]['byteLength']=len(newbin)
 d['asset']['extras']={'previewProcessing':'Embedded textures over 512 px reduced to maximum 512 px with Lanczos resampling and JPEG quality 85. Geometry buffer views are byte-for-byte unchanged.','sourceGlbSha256':tile['sha256'],'processedAt':'2026-09-05'}
 jb=json.dumps(d,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);newbin+=b'\x00'*((-len(newbin))%4)
 glb=struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(newbin))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(newbin),b'BIN\x00')+newbin
 target=Path(tile['url']);target=Path('preview-glb')/Path(*target.parts[1:]);q=ROOT/target;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(glb)
 tile['originalUrl']=tile['url'];tile['url']=str(target);tile['originalBytes']=tile['bytes'];tile['bytes']=len(glb);tile['originalSha256']=tile['sha256'];tile['sha256']=hashlib.sha256(glb).hexdigest()
manifest['source']['changes']+=' Browser preview texture processing: textures above 512 pixels reduced to longest side 512, JPEG quality 85; all geometry buffer views retain original bytes. Original GLB and original 3D Tiles separately retained.'
manifest['stats']['glbBytes']=sum(t['bytes'] for t in manifest['tiles']);manifest['stats']['textureMemoryBytesWithoutMipmaps']=preview_gpu
manifest['previewProcessing']={'maximumTextureDimension':512,'jpegQuality':85,'resampledImages':resized,'originalTextureBytesDecoded':original_gpu,'previewTextureBytesDecoded':preview_gpu,'geometryByteEqualityValidated':True,'originalManifest':'render-manifest.json'}
(ROOT/'preview-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
(ROOT/'preview-validation.json').write_text(json.dumps({'status':'complete',**manifest['stats'],**manifest['previewProcessing']},indent=2))
print(json.dumps({'status':'complete',**manifest['stats'],**manifest['previewProcessing']},indent=2))
