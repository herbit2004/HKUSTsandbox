#!/usr/bin/env python3
"""Bind source-photo-derived textures without moving any source-model vertex.
Python 3.12 + numpy + Pillow. No network or image generation is performed here.
Run: python scripts/texture-innovation.py --project PROJECT [--render]
"""
import argparse,copy,hashlib,json,math,struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def sha(b):return hashlib.sha256(b).hexdigest()
def chunks(raw):
 assert raw[:4]==b'glTF' and struct.unpack_from('<II',raw,4)==(2,len(raw))
 out={};i=12
 while i<len(raw):
  n,k=struct.unpack_from('<I4s',raw,i);out[k]=raw[i+8:i+8+n];i+=8+n
 assert i==len(raw)
 return json.loads(out[b'JSON']),bytearray(out[b'BIN\0'])
def accessor(g,b,i):
 a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];w={'VEC2':2,'VEC3':3,'SCALAR':1}[a['type']];dt={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];n=np.dtype(dt).itemsize
 return np.ndarray((a['count'],w),dt,b,v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',w*n),n)).copy()
def mip(w,h):
 n=0
 while True:
  n+=4*w*h
  if w==h==1:return n
  w=max(1,w//2);h=max(1,h//2)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--render',action='store_true');args=ap.parse_args()
 O=args.project/'public/models/current-forms/innovation';source=O/'source/untextured-v1.glb';raw=source.read_bytes();old,oldbin=chunks(raw);g=copy.deepcopy(old);binary=bytearray(oldbin);m=json.loads((O/'source/untextured-v1-manifest.json').read_text())
 assert sha(raw)=='518945726d20cd4b4147c09730807b4cc6a1db6c9638e9d919372b021b6999bf', 'locked original geometry'
 bmin=np.array(m['bounds']['min']);bmax=np.array(m['bounds']['max']);center=(bmin+bmax)/2
 def add_view(raw,target=None):
  binary.extend(b'\0'*((-len(binary))%4));i=len(g['bufferViews']);v={'buffer':0,'byteOffset':len(binary),'byteLength':len(raw)}
  if target:v['target']=target
  g['bufferViews'].append(v);binary.extend(raw);return i
 def add_access(a,kind):
  a=np.asarray(a,dtype='<f4');v=add_view(a.tobytes(),34962);i=len(g['accessors']);acc={'bufferView':v,'componentType':5126,'count':len(a),'type':kind}
  if kind=='VEC3':acc.update(min=a.min(0).tolist(),max=a.max(0).tolist())
  g['accessors'].append(acc);return i
 files=['facade-broad-photo-derived.png','facade-end-photo-derived.png'];images=[];texture_info=[]
 for name in files:
  path=O/'textures'/name;data=path.read_bytes();im=Image.open(path);im.verify();im=Image.open(path).convert('RGB');images.append(np.array(im));texture_info.append({'asset':'textures/'+name,'sha256':sha(data),'dimensions':list(im.size),'bytes':len(data),'baseRGBABytes':4*im.width*im.height,'rgbaWithMipBytes':mip(im.width,im.height),'generator':'built-in image_gen','meaning':'AI rectified/reconstructed facade material derived from the two official photos; not original photographic pixels or a measured orthographic elevation'})
 g['images']=[{'name':files[i],'mimeType':'image/png','bufferView':add_view((O/'textures'/files[i]).read_bytes())}for i in range(2)]
 g['samplers']=[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]
 g['textures']=[{'source':i,'sampler':0}for i in range(2)]
 material_start=len(g['materials'])
 for i,label in enumerate(['long-axis','end-axis']):
  g['materials'].append({'name':'official-photo-derived-'+label+'-facade','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'baseColorTexture':{'index':i,'texCoord':0},'metallicFactor':0,'roughnessFactor':.78},'doubleSided':True,'extras':{'appearanceMethod':'photo_reference_AI_rectified_texture','sourcePhotos':[x['url']for x in m['sources']['officialExteriorPhotos']],'measuredFacadeRegistration':False}})
 # Pixel intervals [module top, glazing top, glazing bottom, module bottom].
 # These are UV control points, not inferred architectural storeys or dimensions.
 wide=[[0,88,156,205],[205,241,308,337],[337,385,454,508],[508,544,614,686],[686,704,767,797],[797,849,914,960]]
 end=[[0,83,179,256],[256,272,359,436],[436,451,539,622],[622,636,720,805],[805,818,901,984],[984,997,1085,1165],[1165,1180,1283,1362],[1362,1378,1472,1536]]
 wide_by_floor=[5,4,3,2,1,0,1,0];end_by_floor=[7,6,5,4,3,2,1,0];zs=m['sourceFloorGeometry']['sourceZValues'];audit=[];render=[];floor_nodes=0
 for ni,node in enumerate(g['nodes']):
  if 'mesh' not in node:continue
  mesh=g['meshes'][node['mesh']];oldpr=old['meshes'][node['mesh']]['primitives'];role=node['extras']['representationRole'];assert len(oldpr)==1
  pr=oldpr[0];assert 'indices' not in pr
  positions=accessor(old,oldbin,pr['attributes']['POSITION']);normals=accessor(old,oldbin,pr['attributes']['NORMAL']);tri=positions.reshape(-1,3,3)
  if role!='approximate_exterior_band':
   render.append((tri,None,pr['material'],None))
   if role=='exact_source_floor_parts':floor_nodes+=1
   audit.append({'node':node['name'],'role':role,'triangles':len(tri),'positionsAndNormalsUnchanged':True,'sourceAccessorPreserved':True});continue
  lo=node['extras']['sourceBottomY'];hi=node['extras']['upperY'];fi=min(range(len(zs)),key=lambda i:abs(zs[i]-lo));uv=np.zeros((len(positions),2),np.float32);n=normals.reshape(-1,3,3)[:,0];is_end=np.abs(n[:,2])>np.abs(n[:,0]);material_faces=[];newprs=[]
  for tex in range(2):
   ids=np.flatnonzero(is_end==bool(tex));vi=(ids[:,None]*3+np.arange(3)).reshape(-1);p=positions[vi];norm=normals[vi];window_row=end[end_by_floor[fi]] if tex else wide[wide_by_floor[fi]];h,w=images[tex].shape[:2]
   if tex:
    rawu=(p[:,0]-bmin[0])/(bmax[0]-bmin[0]);u=np.where(p[:,2]<center[2],rawu,1-rawu)
   else:
    rawu=(p[:,2]-bmin[2])/(bmax[2]-bmin[2]);u=np.where(p[:,0]<center[0],1-rawu,rawu)
   ys=[lo,lo+1.2,lo+3.45,hi];pixelv=[window_row[3],window_row[2],window_row[1],window_row[0]];v=np.interp(p[:,1],ys,pixelv)/h
   # Clamp to texel centers: sampling never reaches an adjacent context image.
   coords=np.column_stack((np.clip(u,.5/w,1-.5/w),np.clip(v,.5/h,1-.5/h))).astype('<f4');uv[vi]=coords
   if len(ids):
    newprs.append({'attributes':{'POSITION':add_access(p,'VEC3'),'NORMAL':add_access(norm,'VEC3'),'TEXCOORD_0':add_access(coords,'VEC2')},'mode':4,'material':material_start+tex,'extras':{'sourcePrimitive':0,'sourceTriangleIndices':ids.tolist(),'textureAxis':'end'if tex else'long'}})
    render.append((p.reshape(-1,3,3),coords.reshape(-1,3,2),material_start+tex,tex));material_faces.append({'texture':files[tex],'faces':len(ids),'uvBounds':{'min':coords.min(0).tolist(),'max':coords.max(0).tolist()},'sourceTriangleIndices':ids.tolist()})
  mesh['primitives']=newprs
  # Validate exact source geometry, including normals, after grouping by texture.
  restored_p=np.empty_like(positions);restored_n=np.empty_like(normals);covered=[]
  for item in newprs:
   ids=np.asarray(item['extras']['sourceTriangleIndices']);vi=(ids[:,None]*3+np.arange(3)).reshape(-1);restored_p[vi]=accessor(g,binary,item['attributes']['POSITION']);restored_n[vi]=accessor(g,binary,item['attributes']['NORMAL']);covered.extend(ids.tolist())
  assert sorted(covered)==list(range(len(tri))) and np.array_equal(restored_p,positions) and np.array_equal(restored_n,normals)
  audit.append({'node':node['name'],'role':role,'triangles':len(tri),'positionsAndNormalsUnchanged':True,'materials':material_faces})
 assert floor_nodes==8
 g['buffers'][0]['byteLength']=len(binary);g['extras'].pop('noTextureImages',None);g['extras'].update({'appearance':'official-photo-derived textures; generated rectification, approximate UV side assignment','textureImages':2,'originalGeometrySha256':sha(raw),'sourcePositionsAndNormalsUnchanged':True});g['asset']['generator']='HKUST unchanged source-floor geometry + official-photo-derived facade UV/material binding'
 j=json.dumps(g,ensure_ascii=False,separators=(',',':')).encode();j+=b' '*((-len(j))%4);binary+=b'\0'*((-len(binary))%4);payload=struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\0')+binary
 (O/m['url']).write_bytes(payload)
 m.update(version=2,geometryBytes=len(payload),sha256=sha(payload),textures=2,appearance='Offline official-photo-derived facade textures bound through actual TEXCOORD_0 and material baseColorTexture. Built-in image_gen removes perspective/background and reconstructs occluded material; not untouched photo pixels or measured side elevations.')
 m['appearanceTextures']=texture_info;m['sourceGeometryAsset']={'asset':'source/untextured-v1.glb','sha256':sha(raw),'positionsAndNormalsUnchanged':True,'originalTriangles':m['triangles'],'originalMeshes':m['meshes']};m['textureRGBABytes']=sum(i['baseRGBABytes']for i in texture_info);m['textureRGBAWithMipBytes']=sum(i['rgbaWithMipBytes']for i in texture_info)
 m['uvRegistration']={'method':'per-source-floor piecewise vertical mapping; long facade along local Z, end facade along local X; facet normals determine texture family','measuredCameraPose':False,'absoluteFacadeSideRegistrationMeasured':False,'oppositeSideReuse':'opposite elevations reuse/mirror the observed material family; unphotographed elevation details are not independently established','sourceWorldPositionsChanged':False,'sourceFloorCount':8,'windowBandControlYAboveFloor':[0,1.2,3.45,5],'wideTexturePixelRows':wide,'wideRowForBottomToTopFloor':wide_by_floor,'endTexturePixelRows':end,'endRowForBottomToTopFloor':end_by_floor,'roofPolicy':'Original approximate roof cap and explicit unmeasured 5m extension unchanged; no new rooftop equipment or bridge geometry.'}
 m['sources']['textureGeneration']={'tool':'built-in image_gen','promptAsset':'imagegen-prompts.json','inputs':[x['localFile']for x in m['sources']['officialExteriorPhotos']],'outputs':[x['asset']for x in texture_info],'notOriginalPhotographicPixels':True}
 m['limitations']=[x for x in m['limitations'] if not x.startswith('Photos have no verified camera pose:')]+['Facade textures are AI rectified/reconstructed from official exterior photographs; they are approximate appearance, not new captured imagery or measured facade CAD.','No verified camera pose: opposite elevations reuse the observed material family; exact glazing bay count, mullion spacing, recess depth and cardinal side assignment remain approximate.','Roof cap geometry and unknown measured roof Z are unchanged. Unseen rooftop equipment, bridge and interior geometry are not invented.']
 m['validation']['sourcePositionsAndNormalsByteEqual']=True;m['validation']['allOriginalFacesPreserved']=True;m['validation']['facadeTexturedNodes']=32
 (O/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 report={'status':'pass','originalGeometrySha256':sha(raw),'outputSha256':sha(payload),'meshes':len(g['meshes']),'triangles':sum(len(x[0])for x in render),'sourceFloorNodes':floor_nodes,'facadeNodes':32,'textures':texture_info,'allPositionsAndNormalsByteEqual':True,'allOriginalTrianglesExactlyOnce':True,'boundsUnchanged':m['bounds'],'nodes':audit,'browserValidation':False};(O/'texture-geometry-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if args.render:render_views(render,g['materials'],images,bmin,bmax,O)
 print(json.dumps({k:m[k]for k in ['geometryBytes','triangles','meshes','textures','textureRGBABytes','textureRGBAWithMipBytes','bounds','sha256']},indent=2))

def render_views(meshes,materials,images,bmin,bmax,O,label='PHOTO-DERIVED FACADE UV / UNCHANGED SOURCE-FLOOR GEOMETRY / '):
 center=(bmin+bmax)/2;W,H=960,1040;scale=12.0;light=np.array([.4,.8,.45]);light/=np.linalg.norm(light)
 for name,eye_offset in [('north-west',[-100,48,-110]),('south-east',[100,48,110]),('south-west',[-105,42,90]),('north-east',[105,42,-90])]:
  eye=center+eye_offset;f=center-eye;f/=np.linalg.norm(f);right=np.cross(f,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,f);pixels=np.full((H,W,3),[225,235,240],np.uint8);zb=np.full((H,W),np.inf)
  for tris,uvs,mi,ti in meshes:
   color=np.array(materials[mi]['pbrMetallicRoughness']['baseColorFactor'][:3])*255
   for j,tri in enumerate(tris):
    project=np.column_stack(((tri-center)@right*scale+W/2,-(tri-center)@up*scale+H/2,(tri-eye)@f));x0=max(0,int(np.floor(project[:,0].min())));x1=min(W-1,int(np.ceil(project[:,0].max())));y0=max(0,int(np.floor(project[:,1].min())));y1=min(H-1,int(np.ceil(project[:,1].max())))
    if x1<x0 or y1<y0:continue
    a,b,c=project;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(den)<1e-8:continue
    yy,xx=np.mgrid[y0:y1+1,x0:x1+1];xx=xx+.5;yy=yy+.5;q0=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den;q1=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;q2=1-q0-q1;dep=q0*a[2]+q1*b[2]+q2*c[2];ok=(q0>=-1e-6)&(q1>=-1e-6)&(q2>=-1e-6)&(dep<zb[y0:y1+1,x0:x1+1]);normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);normal/=np.linalg.norm(normal);shade=.83+.17*abs(normal@light)
    if ti is not None:
     uv=uvs[j];sample=q0[...,None]*uv[0]+q1[...,None]*uv[1]+q2[...,None]*uv[2];im=images[ti];h,w=im.shape[:2];ix=np.clip((sample[:,:,0]*w).astype(int),0,w-1);iy=np.clip((sample[:,:,1]*h).astype(int),0,h-1);surface=im[iy,ix]*shade
    else:surface=np.broadcast_to(color*shade,(*q0.shape,3))
    zb[y0:y1+1,x0:x1+1][ok]=dep[ok];pixels[y0:y1+1,x0:x1+1][ok]=np.clip(surface[ok],0,255).astype(np.uint8)
  im=Image.fromarray(pixels);d=ImageDraw.Draw(im);d.text((20,18),label+name,fill=(30,50,60));im.save(O/'previews'/(name+'.png'))
if __name__=='__main__':main()
