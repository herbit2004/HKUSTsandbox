#!/usr/bin/env python3
"""Generate 1m, 250m-cell terrain tiles from the preserved CEDD 0.5m TIFFs.
Reuses the original terrain GLB writer and exact-sample/NoData policy. No network.
"""
import argparse,hashlib,importlib.util,json,math,struct,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def load_builder(p):
 s=importlib.util.spec_from_file_location('base_terrain_builder',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def grid(mosaic,stride):
 offset=stride//2;h,w=mosaic.shape;z=mosaic[offset::stride,offset::stride].copy()
 ok=(mosaic!=-9999).reshape(h//stride,stride,w//stride,stride).all(axis=(1,3))
 cv=ok[:-1,:-1]&ok[1:,:-1]&ok[:-1,1:]&ok[1:,1:]
 return z,ok,cv,offset

def faces_for(cv,width):
 r,c=np.nonzero(cv);aa=r*width+c;bb=aa+1;dd=aa+width
 return np.stack([np.stack([aa,dd,bb],1),np.stack([bb,dd,dd+1],1)],1).reshape(-1,3)

def surface_at_source_pixels(z,cv,offset,stride,rr,cc):
 r=(rr-offset)/stride;c=(cc-offset)/stride;inside=(r>=0)&(c>=0)&(r<z.shape[0]-1)&(c<z.shape[1]-1)
 ri=np.clip(np.floor(r).astype(int),0,z.shape[0]-2);ci=np.clip(np.floor(c).astype(int),0,z.shape[1]-2)
 good=inside&cv[ri,ci];u=c-ci;v=r-ri
 h00=z[ri,ci].astype(float);h01=z[ri,ci+1].astype(float);h10=z[ri+1,ci].astype(float);h11=z[ri+1,ci+1].astype(float)
 h=np.where(u+v<=1,h00+(h01-h00)*u+(h10-h00)*v,h11+(h10-h11)*(1-u)+(h01-h11)*(1-v))
 return h,good

def stats(err):
 a=np.abs(err);return {'meanSignedMeters':float(err.mean()),'meanAbsoluteMeters':float(a.mean()),'rmseMeters':float(np.sqrt(np.mean(err**2))),'p50AbsoluteMeters':float(np.quantile(a,.5)),'p95AbsoluteMeters':float(np.quantile(a,.95)),'p99AbsoluteMeters':float(np.quantile(a,.99)),'maxAbsoluteMeters':float(a.max())}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--base-builder',type=Path,required=True);ap.add_argument('--baseline-manifest',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 a.output.mkdir(parents=True,exist_ok=True);(a.output/'tiles').mkdir(exist_ok=True)
 base=load_builder(a.base_builder);rasters=[];sources=[]
 for t in base.TILES:
  p=next(a.source.glob(t+'(*.tif'))
  with Image.open(p)as im:
   assert im.tag_v2[33550][:2]==(.5,.5) and float(im.tag_v2[42113])==-9999
   pix=np.asarray(im).copy();e,n=im.tag_v2[33922][3:5]
  rasters.append((e,n,pix));sources.append({'tile':t,'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':'https://bulkdata.csdi.gov.hk/cedd/lidar/2020dtm/'+p.with_suffix('.zip').name})
 west=min(r[0]for r in rasters);north=max(r[1]for r in rasters);east=max(e+p.shape[1]*.5 for e,n,p in rasters);south=min(n-p.shape[0]*.5 for e,n,p in rasters)
 mosaic=np.full((int((north-south)*2),int((east-west)*2)),-9999,dtype=np.float32)
 for e,n,p in rasters:
  c=int((e-west)*2);r=int((north-n)*2);mosaic[r:r+p.shape[0],c:c+p.shape[1]]=p
 del rasters
 z,ok,cv,offset=grid(mosaic,2);height,width=z.shape;es=west+(offset+.5)*.5+np.arange(width);ns=north-(offset+.5)*.5-np.arange(height)
 levels=np.array([0,8,30,100,230,380.]);palette=np.array([[.73,.72,.55],[.55,.63,.44],[.35,.50,.34],[.26,.41,.28],[.38,.45,.33],[.54,.54,.43]])
 tiles=[];skipped=[];cells=250
 for r0 in range(0,height-1,cells):
  r1=min(r0+cells,height-1)
  for c0 in range(0,width-1,cells):
   c1=min(c0+cells,width-1);name=f'terrain-1m-r{r0//cells:02d}-c{c0//cells:02d}';valid=cv[r0:r1,c0:c1]
   if not valid.any():skipped.append(name);continue
   # One-cell halo gives both tiles exactly the same area-weighted normals on
   # shared seams. It supplies shading only; no halo triangles are exported.
   hr0=max(0,r0-1);hr1=min(height-1,r1+1);hc0=max(0,c0-1);hc1=min(width-1,c1+1)
   he,hn=np.meshgrid(es[hc0:hc1+1],ns[hr0:hr1+1]);hp=np.stack([he-844800,z[hr0:hr1+1,hc0:hc1+1],820500-hn],-1).astype(np.float32)
   hfaces=faces_for(cv[hr0:hr1,hc0:hc1],hp.shape[1]);hpflat=hp.reshape(-1,3);h_norm=np.zeros_like(hpflat)
   fn=np.cross(hpflat[hfaces[:,1]]-hpflat[hfaces[:,0]],hpflat[hfaces[:,2]]-hpflat[hfaces[:,0]])
   for k in range(3):np.add.at(h_norm,hfaces[:,k],fn)
   h_norm/=np.maximum(np.linalg.norm(h_norm,axis=1,keepdims=True),1e-12)
   h_norm=h_norm.reshape(hp.shape)
   sl=(slice(r0-hr0,r1-hr0+1),slice(c0-hc0,c1-hc0+1));positions=hp[sl].reshape(-1,3);normals=h_norm[sl].reshape(-1,3)
   faces=faces_for(valid,c1-c0+1);used=np.unique(faces);remap=np.full(len(positions),-1,dtype=np.int32);remap[used]=np.arange(len(used));indices=remap[faces].astype(np.uint32)
   positions=positions[used];normals=normals[used];colors=np.stack([np.interp(positions[:,1],levels,palette[:,k])for k in range(3)],1).astype(np.float32)
   url='tiles/'+name+'.glb';f=a.output/url
   extra={'origin':{'easting':844800,'northing':820500,'horizontal_crs':'EPSG:2326','vertical_datum':'HKPD','threejs_axes':'x=E-844800; y=HKPD height; z=820500-N'},'survey_date':base.SURVEY,'retrieved_at':'2026-09-05','source_resolution_m':.5,'sample_spacing_m':1,'tile_nominal_cell_extent_m':250,'sourceGridNodeBounds':{'rowStart':r0,'rowEndInclusive':r1,'colStart':c0,'colEndInclusive':c1},'noDataPolicy':'Exact pixel-centre sample every 2 pixels. Withhold a node if any source pixel in its 1x1m block is NoData; triangles require all four cell corners. No filled terrain or synthetic shoreline.','normalPolicy':'Area-weighted geometric normals using one-cell halo to preserve identical seam shading.','colour_warning':'Illustrative elevation colours, not current landcover or photographs.'}
   base.write_glb(f,positions,normals,colors,indices,extra)
   # Reuse original writer without retaining its old, fixed 5m node label.
   raw=f.read_bytes();jl=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+jl]);doc['nodes'][0]['name']=name;doc['asset']['generator']='HKUST tiled terrain; original build_terrain.py GLB writer reused'
   # Each 250m tile has at most 251*251=63001 vertices. A lossless uint16
   # index conversion saves 2 bytes per index without changing the surface.
   assert len(positions)<=65535;indices16=indices.astype('<u2');view=doc['bufferViews'][3];binary=raw[28+jl:][:view['byteOffset']]+indices16.tobytes();view['byteLength']=indices16.nbytes;doc['accessors'][3]['componentType']=5123;doc['buffers'][0]['byteLength']=len(binary);binary+=b'\x00'*(-len(binary)%4)
   jb=json.dumps(doc,separators=(',',':')).encode();jb+=b' '*(-len(jb)%4);tail=struct.pack('<I4s',len(binary),b'BIN\x00')+binary;f.write_bytes(struct.pack('<4sII',b'glTF',2,20+len(jb)+len(tail))+struct.pack('<I4s',len(jb),b'JSON')+jb+tail)
   bmin=positions.min(0).astype(float).tolist();bmax=positions.max(0).astype(float).tolist()
   fullmin=[float(es[c0]-844800),bmin[1],float(820500-ns[r0])];fullmax=[float(es[c1]-844800),bmax[1],float(820500-ns[r1])];center=((np.array(fullmin)+np.array(fullmax))*.5).tolist()
   tile={'id':name,'url':url,'sourceSpacingMeters':.5,'samplingSpacingMeters':1,'vertices':len(positions),'triangles':len(indices),'indexType':'UNSIGNED_SHORT','bytes':f.stat().st_size,'geometryBufferBytes':int(positions.nbytes+normals.nbytes+colors.nbytes+indices16.nbytes),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bounds':{'min':fullmin,'max':fullmax},'validGeometryBounds':{'min':bmin,'max':bmax},'center':center,'gridBBox':{'west':float(es[c0]),'east':float(es[c1]),'north':float(ns[r0]),'south':float(ns[r1]),'heightMin':float(positions[:,1].min()),'heightMax':float(positions[:,1].max())},'sourceGridNodeBounds':extra['sourceGridNodeBounds']}
   tiles.append(tile)
  print(f'Completed tile row {r0//cells+1}/{math.ceil((height-1)/cells)}; {len(tiles)} non-empty tiles',flush=True)
 # Reference sampling uses identical original 0.5m pixel centres for both
 # surfaces, and exact triangle interpolation (not bilinear interpolation).
 rng=np.random.default_rng(20260905);available=np.flatnonzero(mosaic.ravel()!=-9999);take=rng.choice(available,size=min(250000,len(available)),replace=False);rr,cc=np.unravel_index(take,mosaic.shape);truth=mosaic[rr,cc].astype(float)
 coarse,coarse_ok,coarse_cv,coarse_off=grid(mosaic,10)
 hf,gf=surface_at_source_pixels(z,cv,offset,2,rr,cc);hc,gc=surface_at_source_pixels(coarse,coarse_cv,coarse_off,10,rr,cc);common=gf&gc
 ef=hf[common]-truth[common];ec=hc[common]-truth[common]
 worst_f=np.flatnonzero(common)[np.abs(ef).argmax()];worst_c=np.flatnonzero(common)[np.abs(ec).argmax()]
 def refpoint(i):return {'easting':float(west+(cc[i]+.5)*.5),'northing':float(north-(rr[i]+.5)*.5),'sourceHeight':float(truth[i]),'surface1m':float(hf[i]),'surface5m':float(hc[i])}
 error={'method':'250000 original valid 0.5m pixel centres sampled without replacement, fixed RNG seed20260905. Compare the exact piecewise-linear triangles used by each mesh, on identical points where both meshes have source-supported cells. This is display resampling error relative to the 2019-2020 DTM, not survey or present-day accuracy.','requestedReferenceSamples':len(take),'commonReferenceSamples':int(common.sum()),'noDataOrBoundaryExcluded':int((~common).sum()),'surface1m':stats(ef),'surface5m':stats(ec),'rmseReductionPercent':float((1-np.sqrt(np.mean(ef**2))/np.sqrt(np.mean(ec**2)))*100),'worst1mReference':refpoint(worst_f),'worst5mReference':refpoint(worst_c),'exactExportedVertexHeightErrorMeters':0,'vertexCaveat':'Both mesh vertex heights are copied exactly from source Float32 values. Off-vertex interpolation error is nonzero and is reported above.'}
 (a.output/'sampling-error.json').write_text(json.dumps(error,indent=2))
 old=json.load(open(a.baseline_manifest));baseline={'vertices':old['qa']['mesh_vertices'],'triangles':old['qa']['mesh_triangles'],'geometryBufferBytes':old['qa']['mesh_vertices']*36+old['qa']['mesh_triangles']*12,'glbBytes':old['assets']['terrain.glb']['bytes']}
 total={'tiles':len(tiles),'verticesWithSharedSeamDuplicates':sum(t['vertices']for t in tiles),'triangles':sum(t['triangles']for t in tiles),'glbBytes':sum(t['bytes']for t in tiles),'geometryBufferBytes':sum(t['geometryBufferBytes']for t in tiles),'largestTileBytes':max(t['bytes']for t in tiles),'largestTileGeometryBufferBytes':max(t['geometryBufferBytes']for t in tiles),'sourceValidPixels':int(len(available)),'retained1mGridNodes':int(ok.sum()),'memoryCaveat':'geometryBufferBytes is exact POSITION+NORMAL+COLOR_0+index array storage, not full browser RAM/VRAM. Parser copies, object overhead and GPU allocation add memory. Shared seams intentionally duplicate vertices across independent tiles.'}
 manifest={'version':1,'id':'hkust-cwt-cedd2020-terrain-1m-250m','label':'1米真实地形 · 按需细节','checkedAt':'2026-09-05','sourceSurveyDate':base.SURVEY,'sourceSpacingMeters':.5,'samplingSpacingMeters':1,'nominalTileCellExtentMeters':250,'origin':{'easting':844800,'northing':820500,'horizontalCRS':'EPSG:2326','verticalDatum':'HKPD','axes':'x=E-844800; y=HKPD height; z=820500-N'},'sourceGridBounds':{'west':west,'east':east,'south':south,'north':north},'samplingGrid':{'rows':height,'columns':width,'firstEasting':float(es[0]),'firstNorthing':float(ns[0]),'rowStepNorthing':-1,'columnStepEasting':1},'tiles':tiles,'skippedEmptyTiles':skipped,'totals':total,'baseline5m':baseline,'samplingError':error,'sources':sources,'integration':'Keep the existing 5m default untouched. Load only nearby/frustum-relevant tiles in detail mode and release distant tile geometries/materials. Do not raise them vertically to hide overlap; use explicit mode visibility or proper coarse-surface clipping beneath loaded tiles. No synthetic land, shoreline, bathymetry, buildings or new grades generated.'}
 manifest.update({'boundsNote':'bounds use the full rectangular grid cell coverage in x/z, from actual sampled pixel-centre boundaries; validGeometryBounds may be smaller along NoData. Do not clip the coarse surface to validGeometryBounds.','qaFile':'independent-qa.json','readme':'README.zh-CN.md','errorFile':'sampling-error.json','coverageImage':'tile-coverage.png'})
 (a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 # Evidence coverage raster; blue-gray only denotes NoData/withheld evidence.
 rgb=np.empty((*z.shape,3),dtype=np.uint8)
 for k in range(3):rgb[:,:,k]=np.where(ok,np.interp(z,levels,palette[:,k])*255,[174,190,203][k])
 im=Image.fromarray(rgb);d=ImageDraw.Draw(im)
 for t in tiles:
  b=t['sourceGridNodeBounds'];d.rectangle((b['colStart'],b['rowStart'],b['colEndInclusive'],b['rowEndInclusive']),outline='#eee8c7',width=1);d.text((b['colStart']+4,b['rowStart']+4),t['id'].replace('terrain-1m-',''),fill='white')
 im.resize((1125,900)).save(a.output/'tile-coverage.png')
 print(json.dumps({'totals':total,'baseline':baseline,'samplingError':error},indent=2))
if __name__=='__main__':main()
