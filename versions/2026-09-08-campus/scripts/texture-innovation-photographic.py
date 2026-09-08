#!/usr/bin/env python3
"""Isolated direct-official-photo UV candidate. Never modifies public resources.

Original floor/roof accessors and every source node/identity remain intact.
Facade triangles are only subdivided at UV controls. No image generation,
background removal, fake recess/roof geometry or measured camera claim.
"""
import argparse, copy, hashlib, importlib.util, json, struct
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from photo_materials import piecewise_photo_uv

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('innovation_io',ROOT/'scripts/texture-innovation.py')
io=importlib.util.module_from_spec(spec);spec.loader.exec_module(io)
REF=np.array([1824.,1368.])
# Each observed photo row: top masonry boundary, window head, window sill,
# bottom masonry boundary. Left/right pixels are in a 1824x1368 reference image.
# Row controls follow the photographed sloping bands, not a calibrated camera.
BROAD=[
 [[(285,299),(1457,110)],[(281,352),(1459,174)],[(275,399),(1461,250)],[(270,431),(1462,290)]],
 [[(263,434),(1465,299)],[(258,469),(1469,337)],[(249,518),(1472,429)],[(242,547),(1474,474)]],
 [[(231,551),(1481,484)],[(228,580),(1483,516)],[(220,625),(1486,574)],[(213,657),(1488,619)]],
 [[(208,662),(1490,635)],[(205,697),(1493,679)],[(201,740),(1496,752)],[(197,765),(1498,769)]],
 [[(217,806),(1460,846)],[(217,824),(1462,858)],[(213,888),(1464,925)],[(208,924),(1464,943)]]
]
END=[
 [[(764,223),(996,195)],[(758,248),(996,228)],[(749,286),(998,270)],[(742,320),(999,299)]],
 [[(741,328),(1000,307)],[(733,369),(1002,341)],[(720,411),(1004,383)],[(709,447),(1005,427)]]
]
ROW_FOR_FLOOR=[3,4,3,2,1,0,1,0]
U_BREAKS=np.unique(np.r_[np.linspace(0,1,17),[.30,.40,.48,.66,.72]])

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def digest(data):return hashlib.sha256(data).hexdigest()
def triangle_area(p):return np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)/2

def clip(poly,axis,value,greater):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  ia=a[axis]>=value-1e-10 if greater else a[axis]<=value+1e-10
  ib=b[axis]>=value-1e-10 if greater else b[axis]<=value+1e-10
  if ia:out.append(a)
  if ia!=ib:
   t=(value-a[axis])/(b[axis]-a[axis]);out.append(a+t*(b-a))
 return out

def split_triangle(p,axis,ubreaks,ybreaks):
 polys=[list(p)]
 for ax,breaks in [(axis,ubreaks),(1,ybreaks)]:
  for value in breaks:
   # Source GLB boundary positions are float32. A mathematically identical
   # decimal floor/window boundary must not create a sub-ULP sliver beside it.
   value=float(np.float32(value))
   next_polys=[]
   for poly in polys:
    lo=min(a[ax]for a in poly);hi=max(a[ax]for a in poly)
    if lo+1e-8<value<hi-1e-8:
     for greater in [False,True]:
      q=clip(poly,ax,value,greater)
      if len(q)>=3:next_polys.append(q)
    else:next_polys.append(poly)
   polys=next_polys
 result=[]
 for poly in polys:
  for i in range(1,len(poly)-1):
   tri=np.array([poly[0],poly[i],poly[i+1]])
   if triangle_area(tri[None])[0]>1e-10:result.append(tri)
 return result

def uv_for(p,axis,side,fi,bmin,bmax,lo,hi):
 u=(p[:,axis]-bmin[axis])/(bmax[axis]-bmin[axis]);u=u if side>0 else 1-u
 end=axis==0;row=(fi%2)if end else ROW_FOR_FLOOR[fi]
 # Lower entry glazing is not a verified opposite-side elevation.
 # Reuse a clear upper material row on that side; name lettering is excluded.
 if not end and side<0 and row==4:row=3
 controls=np.array((END if end else BROAD)[row],float)[::-1]
 model_y=[lo,lo+1.2,lo+3.45,hi]
 left=piecewise_photo_uv(u,p[:,1],[0,1],model_y,[0,1],controls[:,0,1],REF)[:,1]*REF[1]
 right=piecewise_photo_uv(u,p[:,1],[0,1],model_y,[0,1],controls[:,1,1],REF)[:,1]*REF[1]
 lx=np.interp(p[:,1],model_y,controls[:,0,0]);rx=np.interp(p[:,1],model_y,controls[:,1,0])
 result=np.column_stack(((lx+(rx-lx)*u)/REF[0],(left+(right-left)*u)/REF[1]))
 assert np.isfinite(result).all() and(result>=0).all()and(result<=1).all()
 return result,row

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path('/tmp/hkust-innovation-photo'));ap.add_argument('--render',action='store_true');a=ap.parse_args();out=a.output.resolve()
 assert not out.is_relative_to(ROOT/'public'),'Isolated output required'
 out.mkdir(parents=True,exist_ok=True);(out/'photos').mkdir(exist_ok=True);(out/'previews').mkdir(exist_ok=True)
 source=ROOT/'public/models/current-forms/innovation';metadata=source/'source/legacy-manifest-v2.json';manifest=json.loads(metadata.read_text());raw=(source/'source/untextured-v1.glb').read_bytes();old,oldbin=io.chunks(raw)
 assert digest(raw)=='518945726d20cd4b4147c09730807b4cc6a1db6c9638e9d919372b021b6999bf'
 g=copy.deepcopy(old);binary=bytearray(oldbin);bmin=np.array(manifest['bounds']['min']);bmax=np.array(manifest['bounds']['max']);zs=manifest['sourceFloorGeometry']['sourceZValues'];render=[];audit=[];photos=[];images=[]
 def view(data,target=None):
  binary.extend(b'\0'*((-len(binary))%4));v={'buffer':0,'byteOffset':len(binary),'byteLength':len(data)}
  if target:v['target']=target
  g['bufferViews'].append(v);binary.extend(data);return len(g['bufferViews'])-1
 def access(arr,kind):
  arr=np.asarray(arr,dtype='<f4');v=view(arr.tobytes(),34962);g['accessors'].append({'bufferView':v,'componentType':5126,'count':len(arr),'type':kind,**({'min':arr.min(0).tolist(),'max':arr.max(0).tolist()}if kind=='VEC3'else{})});return len(g['accessors'])-1
 g['images']=[];g['textures']=[];g['samplers']=[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]
 for i,name in enumerate(['20260320_111131.jpg','20260421_160149.jpg']):
  data=(source/'references'/name).read_bytes();im=Image.open(source/'references'/name).convert('RGB');images.append(np.asarray(im));(out/'photos'/name).write_bytes(data)
  ref=next(p for p in manifest['sources']['officialExteriorPhotos']if p['localFile'].endswith(name));assert digest(data)==ref['sha256']
  g['images'].append({'name':'original-official-'+name,'mimeType':'image/jpeg','bufferView':view(data)});g['textures'].append({'source':i,'sampler':0});photos.append({**ref,'asset':'photos/'+name,'encodedBytes':len(data),'mipBytes':io.mip(*im.size),'pixelOperation':'None: original JPEG bytes embedded unchanged; no generation, recompression, masking or color edit.'})
 material_start=len(g['materials'])
 for label,i in [('broad-original-official-photograph',0),('end-original-official-photograph',1)]:
  g['materials'].append({'name':label,'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'baseColorTexture':{'index':i,'texCoord':0},'metallicFactor':0,'roughnessFactor':1},'doubleSided':True,'extras':{'sourcePhoto':photos[i]['url'],'sourceImageSHA256':photos[i]['sha256'],'sourcePhotoPixelsUnchanged':True,'registration':'manual observed window-band / facade-family correspondence; no measured camera pose'}})
 max_plane_error=0;max_area_error=0;unsupported=[];old_face_count=0;new_face_count=0;packing_fallbacks=[]
 for ni,node in enumerate(g['nodes']):
  if'mesh'not in node:continue
  mesh=g['meshes'][node['mesh']];pr=old['meshes'][node['mesh']]['primitives'][0];assert'indices'not in pr
  pos=io.accessor(old,oldbin,pr['attributes']['POSITION']);nor=io.accessor(old,oldbin,pr['attributes']['NORMAL']);tris=pos.reshape(-1,3,3);old_face_count+=len(tris)
  role=node['extras']['representationRole']
  if role!='approximate_exterior_band':
   render.append((tris,None,pr['material'],None));audit.append({'node':node['name'],'role':role,'originalAccessorPreserved':True,'triangles':len(tris)});new_face_count+=len(tris);continue
  lo=node['extras']['sourceBottomY'];hi=node['extras']['upperY'];fi=min(range(len(zs)),key=lambda i:abs(zs[i]-lo));parts={0:[],1:[]};sourceareas=[];afterareas=[];normal_out={0:[],1:[]};uv_out={0:[],1:[]};parentindices={0:[],1:[]};rowsused=set()
  for ti,tri in enumerate(tris):
   n=nor.reshape(-1,3,3)[ti,0];end=abs(n[2])>abs(n[0]);axis=0 if end else 2;family=int(end);side=float(n[2]if end else n[0]);breaks=bmin[axis]+U_BREAKS*(bmax[axis]-bmin[axis]);sub=split_triangle(tri.astype(float),axis,breaks,[lo,lo+1.2,lo+3.45,hi]);sub=np.array(sub)
   if not len(sub):continue
   packed=sub.astype('<f4');packed_area=np.linalg.norm(np.cross(packed[:,1]-packed[:,0],packed[:,2]-packed[:,0]),axis=1)
   if(packed_area<=1e-8).any():
    assert np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))>1e-8
    packing_fallbacks.append({'node':node['name'],'sourceTriangle':ti,'rejectedChildTriangles':len(sub),'collapsedChildTriangles':int((packed_area<=1e-8).sum()),'originalLongestEdgeM':float(np.linalg.norm(tri-np.roll(tri,-1,axis=0),axis=1).max()),'policy':'Whole original source triangle retained; each original source primitive already spans only one window/lower/upper band. No source face omitted.'})
    sub=tri.astype(float)[None]
   before=float(triangle_area(tri[None])[0]);after=float(triangle_area(sub).sum());max_area_error=max(max_area_error,abs(before-after));sourceareas.append(before);afterareas.append(after)
   geometric_n=np.cross(tri[1]-tri[0],tri[2]-tri[0]).astype(float);geometric_n/=np.linalg.norm(geometric_n);plane_error=float(abs((sub-tri[0])@geometric_n).max());max_plane_error=max(max_plane_error,plane_error)
   uv,row=uv_for(sub.reshape(-1,3),axis,side,fi,bmin,bmax,lo,hi);rowsused.add((family,row))
   parts[family].extend(sub);normal_out[family].extend(np.tile(n,(len(sub)*3,1)).reshape(-1,3,3));uv_out[family].extend(uv.reshape(-1,3,2));parentindices[family].extend([ti]*len(sub))
  newprs=[]
  for family in [0,1]:
   if not parts[family]:continue
   p=np.asarray(parts[family],dtype='<f4');uv=np.asarray(uv_out[family],dtype='<f4');n=np.asarray(normal_out[family],dtype='<f4');assert np.isfinite(p).all()and np.isfinite(uv).all()
   newprs.append({'attributes':{'POSITION':access(p.reshape(-1,3),'VEC3'),'NORMAL':access(n.reshape(-1,3),'VEC3'),'TEXCOORD_0':access(uv.reshape(-1,2),'VEC2')},'mode':4,'material':material_start+family,'extras':{'sourcePrimitive':0,'sourceTriangleIndices':parentindices[family],'subdivisionOnly':True,'photoFamily':'end'if family else'broad','originalEntityId':manifest['entityId']}})
   render.append((p,uv,material_start+family,family));new_face_count+=len(p)
  mesh['primitives']=newprs;node['extras']['photoRegistration']='appearance-only window-band correspondence; source pixels unchanged'
  audit.append({'node':node['name'],'role':role,'originalTriangles':len(tris),'subdividedTriangles':sum(len(p)for p in parts.values()),'originalAreaM2':sum(sourceareas),'subdividedAreaM2':sum(afterareas),'sourcePhotoRows':[{'photo':x,'row':y}for x,y in sorted(rowsused)],'allOriginalFacesCovered':len(set(parentindices[0]+parentindices[1]))==len(tris)})
 assert max_area_error<.0001 and max_plane_error<.0001
 assert sum(x['role']=='exact_source_floor_parts'for x in audit)==8
 assert all(n['extras']['entityId']==manifest['entityId']for n in g['nodes'])
 for m in g['meshes']:
  for p in m['primitives']:
   t=io.accessor(g,binary,p['attributes']['POSITION']).astype('<f4').reshape(-1,3,3)
   assert(np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)>1e-8).all(),'Float32 output triangle collapse'
 for n in g['nodes']:n['extras']['buildingId']=manifest['buildingId']
 child_roots=list(g['scenes'][g.get('scene',0)]['nodes']);root_index=len(g['nodes']);g['nodes'].append({'name':'campus-19','children':child_roots,'extras':{'entityId':manifest['entityId'],'buildingId':manifest['buildingId'],'representationRole':'complete_current_form_member'}});g['scenes'][g.get('scene',0)]['nodes']=[root_index]
 g['extras'].pop('noTextureImages',None);g['extras'].update({'appearance':'Original official photographic pixels; piecewise facade UV candidate','textureImages':2,'sourceGeometrySHA256':digest(raw),'subdivisionOnly':True,'measuredPhotographicPose':False,'sourceFloorAndRoofAccessorsUnchanged':True});g['asset']['generator']='Isolated direct-official-photo facade UV candidate; original source floors retained'
 g['buffers'][0]['byteLength']=len(binary);j=json.dumps(g,ensure_ascii=False,separators=(',',':')).encode();j+=b' '*((-len(j))%4);binary+=b'\0'*((-len(binary))%4);payload=struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\0')+binary
 glb=out/'innovation-original-photo-candidate.glb';glb.write_bytes(payload)
 report={'version':1,'members':[{'entityId':manifest['entityId'],'buildingId':manifest['buildingId'],'nodeName':'campus-19','bounds':manifest['bounds']}],'status':'isolated complete-building material candidate, not runtime-installed or visually accepted','asset':{'url':glb.name,'bytes':len(payload),'sha256':digest(payload)},'entityId':manifest['entityId'],'buildingId':manifest['buildingId'],'bounds':manifest['bounds'],'sourceGeometrySHA256':digest(raw),'originalRuntimeGLBSHA256':digest((source/'innovation-current-approx.glb').read_bytes()),'originalTriangles':old_face_count,'candidateTriangles':new_face_count,'nodes':len(g['nodes']),'originalChildNodes':len(old['nodes']),'sourceFloorNodes':8,'sourceFloorAndRoofAccessorsByteUnchanged':True,'maximumSubdivisionPlaneErrorM':max_plane_error,'maximumPerSourceTriangleAreaErrorM2':max_area_error,'sourcePhotos':photos,'textureMipBytes':sum(p['mipBytes']for p in photos),'registration':{'referenceImageDimensions':REF.tolist(),'broadRowsTopToBottom':BROAD,'endRowsTopToBottom':END,'broadSourceRowForFloorLGThrough6':ROW_FOR_FLOOR,'endRowForFloor':'alternate two clear observed rows; reuse is appearance-family only','modelWindowControlsAboveSourceFloor':[0,1.2,3.45,5],'horizontalSubdivisionU':U_BREAKS.tolist(),'noFourCornerSpanAcrossWindowBreak':True,'orientation':'Local X-normal surfaces use broad photo; local Z-normal surfaces use end photo. Opposite-facing UV orientation reversed. Cardinal side/photo camera correspondence is unmeasured.','namedBandPolicy':'Exclude the photographed name strip from reusable UV regions; exact sign placement is not measured and is not reconstructed.','occlusionPolicy':'Only inspected clear facade quadrilateral strips sampled. Sky, vegetation, cars, terrace foreground and cantilever void excluded. No black paint or image erasure.','pixelPolicy':'Exact original source JPEG bytes; existing photograph reflections, tile joints, mullion/shading shadows retained.'},'limitations':['Existing schematic eight-storey perimeter bands remain; source photos do not prove every side/bay or this full exterior geometry.','Photo 1 has five selected clear source window rows reused across eight source-storey intervals. Photo 2 contributes two clear end rows; its unmeasured cantilever and curved end silhouette are not rebuilt.','Opposite elevations and obscured low floors reuse clear photographed material families; not independently photographed restoration.','The approximate flat grey roof cap remains unchanged and unresolved. No source image depicts its full plan.','Offline orthographic renders use a simple lamp and do not establish Three/browser, realistic materials, seams at every perspective, or user acceptance.'],'audit':audit}
 report['float32SubdivisionFallbacks']=packing_fallbacks;report['packedDegenerateTriangles']=0
 report['sourceMetadata']={'asset':'/models/current-forms/innovation/source/legacy-manifest-v2.json','sha256':digest(metadata.read_bytes())}
 report['partitionControlPacking']='Split coordinates use the existing float32 GLB coordinate grid; source surfaces do not move. Any remaining collapsed child returns the whole original source triangle.'
 report['limitations'][-1]='Offline actual-GLB rendering has no live campus context, source shadows or dynamic PBR; it does not establish browser or user acceptance.'
 write(out/'manifest.json',report)
 for photo,rows in zip(photos,[BROAD,END]):
  im=Image.open(out/photo['asset']).convert('RGB').resize(tuple(REF.astype(int)));d=ImageDraw.Draw(im)
  for ri,row in enumerate(rows):
   for k,line in enumerate(row):d.line([tuple(line[0]),tuple(line[1])],fill=(255,30,30)if k in[0,3]else(20,255,80),width=3)
   d.text((row[0][0][0]+5,row[0][0][1]+3),str(ri),fill=(255,255,0))
  im.save(out/'previews'/('control-'+Path(photo['asset']).stem+'.png'))
 if a.render:io.render_views(render,g['materials'],images,bmin,bmax,out,label='ORIGINAL PHOTO UV CANDIDATE / OFFLINE, UNCALIBRATED / ')
 print(json.dumps({k:report[k]for k in['asset','originalTriangles','candidateTriangles','maximumSubdivisionPlaneErrorM','maximumPerSourceTriangleAreaErrorM2','textureMipBytes']},indent=2))

if __name__=='__main__':main()
