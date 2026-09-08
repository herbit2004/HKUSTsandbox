#!/usr/bin/env python3
"""Build an unenhanced 0.25 m TDOP entrance texture on measured 0.5 m DTM.
Inputs: downloaded official GML/TDOP and current checked-in original meshes/DTM.
No guessed heights, no ground texture under roofs/canopies, no sculpture geometry.
Run with numpy, Pillow, rasterio, shapely >=2.1.
"""
import argparse,json,math,struct,hashlib,sys,shutil
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw
import rasterio
from rasterio.windows import Window
from rasterio.features import rasterize,shapes
from affine import Affine
from shapely import Polygon,LineString,box,polygons,points,STRtree,intersection,constrained_delaunay_triangles,area
from shapely.geometry import shape
from shapely.ops import unary_union,polygonize
G='{http://www.opengis.net/gml}';ORIGIN=np.array([844800.,820500.]);CROP=(845040,821920,845205,822190);IDS=[11,12,13,21,88,100]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(a):
 a=np.asarray(a);a=a[np.isfinite(a)];return {'count':len(a),'min':float(a.min()),'max':float(a.max()),'median':float(np.median(a)),'p05':float(np.quantile(a,.05)),'p95':float(np.quantile(a,.95))}if len(a)else{'count':0}
def read_gml(path):
 for m in ET.parse(path).getroot().findall(G+'featureMember'):
  f=m[0];pr={n.tag.split('}')[-1]:n.text for n in f if not n.tag.startswith(G)}
  arrays=[np.array([float(v)for v in n.text.split()]).reshape(-1,3)[:,[1,0,2]] for n in f.iter(G+'posList')]
  yield pr,arrays
class Heights:
 def __init__(self,paths):
  self.tiles=[]
  for path in paths:
   with Image.open(path)as im:self.tiles.append((np.asarray(im).copy(),im.tag_v2[33922][3:5]))
 def __call__(self,en):
  out=np.full(len(en),np.nan)
  for a,(e,n)in self.tiles:
   c=(en[:,0]-e)*2-.5;r=(n-en[:,1])*2-.5;ix=np.flatnonzero((c>=0)&(r>=0)&(c<a.shape[1]-1)&(r<a.shape[0]-1))
   if not len(ix):continue
   ci=c[ix].astype(int);ri=r[ix].astype(int);u=c[ix]-ci;v=r[ix]-ri;q=np.array([a[ri,ci],a[ri,ci+1],a[ri+1,ci],a[ri+1,ci+1]])
   valid=np.isfinite(q).all(0)&(q!=-9999).all(0);z=q[0]*(1-u)*(1-v)+q[1]*u*(1-v)+q[2]*(1-u)*v+q[3]*u*v;out[ix[valid]]=z[valid]
  return out

def source_geometry(root,t):
 raw=(root/t['url']).read_bytes();jl=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+jl]);bo=28+jl;M=np.array(t['matrix']).reshape(4,4).T
 def acc(i):
  a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']];k={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
  return np.ndarray((a['count'],k),dtype=dtype,buffer=raw,offset=bo+v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',np.dtype(dtype).itemsize*k),np.dtype(dtype).itemsize))
 for node in doc['nodes']:assert not any(k in node for k in ['matrix','translation','rotation','scale'])
 return np.concatenate([(acc(pr['attributes']['POSITION']).astype(float)@M[:3,:3].T+M[:3,3])[acc(pr['indices']).reshape(-1,3)]for mesh in doc['meshes']for pr in mesh['primitives']])
def photo_height(en,tiles,root):
 xz=np.stack([en[:,0]-ORIGIN[0],ORIGIN[1]-en[:,1]],1);out=np.full(len(en),-np.inf);used=[]
 for t in tiles:
  b=t['bounds'];lo=np.array(b['min'])[[0,2]];hi=np.array(b['max'])[[0,2]];ix=np.flatnonzero(((xz>=lo)&(xz<=hi)).all(1))
  if not len(ix):continue
  xyz=source_geometry(root,t);tri=xyz[:,:,[0,2]];d=(tri[:,1,1]-tri[:,2,1])*(tri[:,0,0]-tri[:,2,0])+(tri[:,2,0]-tri[:,1,0])*(tri[:,0,1]-tri[:,2,1]);valid=abs(d)>1e-8;xyz=xyz[valid];tri=tri[valid];d=d[valid]
  pairs=STRtree(polygons(tri)).query(points(xz[ix]),predicate='intersects');used.append({'id':t['id'],'sha256':sha(root/t['url']),'triangles':len(xyz)})
  if not pairs.shape[1]:continue
  k=ix[pairs[0]];q=tri[pairs[1]];p=xz[k];dd=d[pairs[1]];u=((q[:,1,1]-q[:,2,1])*(p[:,0]-q[:,2,0])+(q[:,2,0]-q[:,1,0])*(p[:,1]-q[:,2,1]))/dd;v=((q[:,2,1]-q[:,0,1])*(p[:,0]-q[:,2,0])+(q[:,0,0]-q[:,2,0])*(p[:,1]-q[:,2,1]))/dd;y=xyz[pairs[1],:,1];np.maximum.at(out,k,u*y[:,0]+v*y[:,1]+(1-u-v)*y[:,2])
 out[out==-np.inf]=np.nan;return out,used

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--gml',type=Path,required=True);ap.add_argument('--tdop',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();dest=args.output;dest.mkdir(parents=True,exist_ok=True);e0,n0,e1,n1=CROP
 # Polygonize only actual source lines and source building rings. The 250x320m
 # local clipping box is an explicit analysis boundary, never a land/road claim.
 region=box(845000,821880,845250,822200);lines=[region.boundary];provenance=[];buildings=[]
 for name in ['Transportation/CartoPedLine','Transportation/CartoTransLine','Buildings/Building']:
  path=args.gml/(name+'.gml')
  for pr,arrays in read_gml(path):
   if not any(LineString(a[:,:2]).intersects(region)for a in arrays):continue
   provenance.append({'layer':name,'properties':pr,'coordinatesEN':[a.tolist()for a in arrays]})
   for a in arrays:
    if name.startswith('Transportation'):lines.append(LineString(a[:,:2]))
    elif len(a)>3 and np.array_equal(a[0],a[-1]):buildings.append(Polygon(a[:,:2]));lines.append(LineString(a[:,:2]))
 candidates=list(polygonize(unary_union(lines)));domain=unary_union([candidates[i]for i in IDS]).intersection(box(*CROP));stage=unary_union([candidates[i]for i in [33,38,55]])
 assert domain.intersection(stage).area<1e-5
 assert domain.intersection(unary_union(buildings)).area<1e-4
 # Domain IDs are deterministic geometry derivations; these area checks guard
 # against input order/source revision silently selecting different faces.
 expected={11:5771.476,12:2418.340,13:477.918,21:4239.582,88:4232.271,100:93.056}
 assert all(abs(candidates[i].area-a)<.002 for i,a in expected.items())
 source_tifs=list((args.project/'public/terrain/source-data').glob('*.tif'));dtm=Heights(source_tifs)
 with rasterio.open(args.tdop)as r:
  window=Window((e0-845000)*4,(824000-n1)*4,(e1-e0)*4,(n1-n0)*4);rgb=r.read(window=window).transpose(1,2,0)
 texture='entrance-tdop-20250111.png';Image.fromarray(rgb).save(dest/texture)
 # No image filtering: crop PNG round-trips to the original GeoTIFF pixels.
 assert np.array_equal(np.asarray(Image.open(dest/texture)),rgb)
 (dest/'entrance-tdop-20250111.pgw').write_text(f'0.25\n0\n0\n-0.25\n{e0+.125}\n{n1-.125}\n')
 # Exclude source roofs/canopies/raised objects before triangulating ground.
 # Each 0.5m cell is accepted only when the uppermost source photography surface
 # is within -1..+1.5m of measured DTM at its centre; this is a conservative
 # ground-display filter, not a vegetation classification or measured boundary.
 xs=np.arange(e0+.25,e1,.5);ns=np.arange(n1-.25,n0,-.5);ee,nn=np.meshgrid(xs,ns);en=np.column_stack([ee.ravel(),nn.ravel()]);dh=dtm(en)
 baseline=json.load(open(args.project/'public/models/render-manifest.json'))['tiles'];bm,bused=photo_height(en,baseline,args.project/'public/models')
 hires={p['id']:p for p in json.load(open(args.project/'public/models/hires/manifest.json'))['patches']}
 for extra in sorted([*(args.project/'public/models/hires').glob('partial-*/manifest.json'),*(args.project/'public/models/hires').glob('terminal/*/manifest.json')]):
  for patch in json.load(open(extra))['patches']:hires[patch['id']]=patch
 tiles=[t for p in hires.values() for t in p['levels'].get('fine',p['levels']['high'])['tiles']];hm,hused=photo_height(en,tiles,args.project/'public/models/hires');ph=np.where(np.isfinite(hm),hm,bm);delta=ph-dh
 ground=np.isfinite(delta)&(delta>=-1)&(delta<=1.5);ground=ground.reshape(len(ns),len(xs));transform=Affine(.5,0,e0,0,-.5,n1)
 source_domain=domain
 cover=unary_union([shape(g)for g,v in shapes(ground.astype('uint8'),mask=ground,transform=transform)if v]);domain=domain.intersection(cover)
 print('Ground accepted',domain.area,'of official domains',source_domain.area,flush=True)
 # Source grid spacing 0.5m, exact original DTM centre-aligned internal vertices.
 loe,lon,hie,hin=domain.bounds;es=np.arange(math.floor(loe)-.75,math.ceil(hie)+.5,.5);ns=np.arange(math.floor(lon)-.75,math.ceil(hin)+.5,.5);ee,nn=np.meshgrid(es[:-1],ns[:-1]);p=np.stack([ee.ravel(),nn.ravel()],1);quads=np.stack([p,p+[.5,0],p+[.5,.5],p+[0,.5]],1);quad_polys=polygons(quads);parts=[domain.intersection(candidates[88]),domain.difference(candidates[88])];triangles=[];face_groups=[]
 for gi,part in enumerate(parts):
  clipped=intersection(quad_polys,part);clipped=clipped[area(clipped)>1e-10];triangulated=constrained_delaunay_triangles(clipped);group_tri=[np.asarray(t.exterior.coords)[:3]for cell in triangulated for t in cell.geoms];triangles.extend(group_tri);face_groups.extend([gi]*len(group_tri))
 tri=np.array(triangles);face_groups=np.array(face_groups);en,ix=np.unique(np.round(tri.reshape(-1,2),8),axis=0,return_inverse=True);ix=ix.reshape(-1,3);y=dtm(en);valid=np.isfinite(y);good_tri=valid[ix].all(1);ix=ix[good_tri];face_groups=face_groups[good_tri];used=np.unique(ix);remap=np.full(len(en),-1);remap[used]=np.arange(len(used));ix=remap[ix];en=en[used];y=y[used]
 pos=np.column_stack([en[:,0]-ORIGIN[0],y,ORIGIN[1]-en[:,1]]).astype('<f4');cross=np.cross(pos[ix[:,1]]-pos[ix[:,0]],pos[ix[:,2]]-pos[ix[:,0]]);flip=cross[:,1]<0;ix[flip]=ix[flip][:,[0,2,1]];cross=np.cross(pos[ix[:,1]]-pos[ix[:,0]],pos[ix[:,2]]-pos[ix[:,0]]);normals=np.zeros_like(pos)
 for k in range(3):np.add.at(normals,ix[:,k],cross)
 normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12);uv=np.column_stack([(en[:,0]-e0)/(e1-e0),(n1-en[:,1])/(n1-n0)]).astype('<f4')
 arrays=[pos,normals.astype('<f4'),uv,*[ix[face_groups==i].astype('<u4').reshape(-1)for i in range(2)]];binary=bytearray();views=[];acs=[]
 for i,a in enumerate(arrays):
  binary.extend(b'\0'*(-len(binary)%4));views.append({'buffer':0,'byteOffset':len(binary),'byteLength':a.nbytes,'target':34963 if i>=3 else 34962});binary.extend(a.tobytes());acs.append({'bufferView':i,'componentType':5125 if i>=3 else 5126,'count':len(a),'type':['VEC3','VEC3','VEC2','SCALAR','SCALAR'][i]})
 acs[0].update(min=pos.min(0).tolist(),max=pos.max(0).tolist())
 extras={'geometry':'0.5m CEDD bare-earth DTM, no vertical offset','texture':'unchanged Lands Department TDOP 2025-01-11 crop','sculptureAndStageExcluded':True}
 node_extras=[{**extras,'entityId':'outdoor_area:catalog:campus-61','surfaceNodeId':'entrance-piazza-ground','sourceDomainIds':[88]},{**extras,'surfaceNodeId':'entrance-approach-ground','sourceDomainIds':[i for i in IDS if i!=88],'binding':'No entityId; resolve road/path from actual hit point against existing official road geometry.'}]
 features=[]
 for i in range(2):
  pts=pos[np.unique(ix[face_groups==i])];bmin=pts.min(0).tolist();bmax=pts.max(0).tolist();features.append({**node_extras[i],'meshBounds':{'min':bmin,'max':bmax},'center':((np.array(bmin)+bmax)/2).tolist(),'triangles':int((face_groups==i).sum()),'vertices':len(pts)})
 doc={'asset':{'version':'2.0','generator':'build_entrance_surface.py','copyright':'Lands Department and CEDD, Hong Kong SAR Government'},'scene':0,'scenes':[{'nodes':[0,1]}],'nodes':[{'name':node_extras[i]['surfaceNodeId'],'mesh':i,'extras':node_extras[i]}for i in range(2)],'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3+i,'material':0}]}for i in range(2)],'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':acs,'materials':[{'name':'Unaltered TDOP pavement on measured DTM','pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':1},'extensions':{'KHR_materials_unlit':{}}}],'extensionsUsed':['KHR_materials_unlit'],'textures':[{'sampler':0,'source':0}],'samplers':[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}],'images':[{'uri':texture}],'extras':extras}
 js=json.dumps(doc,separators=(',',':')).encode();js+=b' '*(-len(js)%4);binary.extend(b'\0'*(-len(binary)%4));(dest/'entrance-ground.glb').write_bytes(struct.pack('<4sII',b'glTF',2,28+len(js)+len(binary))+struct.pack('<I4s',len(js),b'JSON')+js+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
 h,w=rgb.shape[:2];projected=pos[ix][:,:,[0,2]];shapes_tri=[({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in projected];mask=rasterize(shapes_tri,out_shape=(h,w),transform=Affine(.25,0,e0-ORIGIN[0],0,.25,ORIGIN[1]-n1),dtype='uint8',all_touched=False)
 rr,cc=np.indices((h,w));men=np.column_stack([e0+(cc.ravel()+.5)*.25,n1-(rr.ravel()+.5)*.25]);my=dtm(men).reshape(h,w);valid=(mask>0)&np.isfinite(my);encoded=np.floor(np.where(valid,my,0)*256).astype(np.uint16);rgba=np.dstack([np.where(valid,mask,0),encoded//256,encoded%256,np.full((h,w),255)]).astype('uint8');Image.fromarray(rgba).save(dest/'entrance-surface-mask.png')
 all_parts=lambda g:[{'rings':[[[x-ORIGIN[0],ORIGIN[1]-n]for x,n in ring.coords]for ring in[p.exterior,*p.interiors]]}for p in([g]if g.geom_type=='Polygon'else g.geoms)]
 (dest/'source-domains.json').write_text(json.dumps({'selectedPolygonizedFaces':IDS,'sourceDomainLocalXZ':all_parts(source_domain),'generatedDomainLocalXZ':all_parts(domain),'excludedStageLocalXZ':all_parts(stage),'sourceFeatures':provenance},ensure_ascii=False,separators=(',',':')))
 bmin=pos.min(0).tolist();bmax=pos.max(0).tolist();inside_source=rasterize([(source_domain,1)],out_shape=ground.shape,transform=transform,dtype='uint8')>0;good=(ground&inside_source).ravel();guard=json.load(open(args.project/'public/models/exteriors/manifest.json'))['bundles'][0]['mask'];maskroot=args.project/'public/models/exteriors';expanded=np.asarray(Image.open(maskroot/guard['url']))[...,0]if np.asarray(Image.open(maskroot/guard['url'])).ndim==3 else np.asarray(Image.open(maskroot/guard['url']));exact=np.asarray(Image.open(maskroot/guard['exactUrl']));exact=exact[...,0]if exact.ndim==3 else exact
 qa={'sourceDomainAreaSquareMeters':source_domain.area,'acceptedGroundAreaSquareMeters':domain.area,'rejectedRaisedCanopyOrMissingSourceAreaSquareMeters':source_domain.area-domain.area,'vertices':len(pos),'triangles':len(ix),'maxHeightRoundoffMeters':float(np.max(np.abs(pos[:,1]-y))),'meshYRangeHKPD':stats(y),'acceptedPhotoMinusDTM':stats(delta[good]),'allMeshVerticesHaveSourceDTM':bool(np.isfinite(y).all()),'meshAreaInsideDomainErrorSquareMeters':float(abs(domain.area-abs(cross[:,1]).sum()/2)),'allOriginalTDOPPixelsUnchanged':True,'textureSize':[w,h],'heightMaskQuantizationMaxMeters':float(np.max(np.abs(my[valid]-encoded[valid]/256))),'coveredMaskPixels':int(valid.sum()),'mainBuildingRenderingGuardExtraSquareMeters':float(((expanded>0)&(exact==0)).sum()*.25),'mainBuildingMaskHeightMin':guard['heightMin'],'sourcePhotoHeightDatumCaveat':'Original mesh datum not certified HKPD; DTM is HKPD. Delta only checks local registration and raised-object exclusion.'}
 manifest={'version':1,'url':'entrance-ground.glb','bytes':(dest/'entrance-ground.glb').stat().st_size,'originEN':ORIGIN.tolist(),'features':features,'texture':{'url':texture,'captureDate':'2025-01-11','pixelSizeMeters':.25,'boundsEN':list(CROP),'width':w,'height':h,'sha256':sha(dest/texture),'decodedBytes':w*h*4,'sourceURL':'https://open.hkmapservice.gov.hk/OpenData/directDownload?productName=TDOP&sheetName=T12-NW-A&productFormat=TIFF','sourceTiffSHA256':sha(args.tdop)},'mask':{'url':'entrance-surface-mask.png','slot':'surface2','minX':e0-ORIGIN[0],'maxX':e1-ORIGIN[0],'minZ':ORIGIN[1]-n1,'maxZ':ORIGIN[1]-n0,'width':w,'height':h,'pixelSizeMeters':.25,'heightEncoding':'R coverage; G whole meters, B fraction/256; RGB channels sampled in NoColorSpace','discardHeightClearanceMeters':1.75,'onlyEnableWithLoadedSurface':True,'flipY':False},'source':{'geometry':'CEDD original 0.5m DTM 2019-12-20 to 2020-02-02, HKPD','officialLinework':'iB1000 CartoPedLine, CartoTransLine and Building, sheet12-NW-6C','manualSelection':'Source polygonized faces verified against unchanged 2025 TDOP and official SENG/Marketing Piazza photos; no manually invented line or image pixels.','sourceTifs':[{'name':p.name,'sha256':sha(p)}for p in source_tifs],'photoSources':bused+hused},'limitations':['Source image is a 0.25m orthophoto, not 0.25m positional-accuracy certification.','DTM measures bare earth; paving texture is 2025, source DTM survey is 2019–2020.','Central sculpture and stepped platform, official building polygons and mapped planting-island holes are excluded.','Additional 0.5m display coverage filter rejects canopy, raised-object or missing-source cells; it is not a measured landcover boundary.','Underlying source trees/roofs remain above a per-pixel height-limited replacement mask.','No synthetic greenery, height correction, generated texture, sharpening or recolouring.'],'qa':qa}
 (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));(dest/'qa.json').write_text(json.dumps(qa,indent=2))
 overlay=Image.fromarray(rgb);color=np.zeros_like(rgb);color[:]=[245,50,40];arr=np.asarray(overlay).copy();sel=valid;arr[sel]=(arr[sel]*.7+color[sel]*.3).astype('uint8');Image.fromarray(arr).save(dest/'coverage-qa.png')
 print(json.dumps(qa,indent=2),flush=True)
if __name__=='__main__':main()
