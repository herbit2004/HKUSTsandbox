#!/usr/bin/env python3
"""Build a reproducible HKUST terrain subset from eight public CEDD GeoTIFFs.

Requires Python 3, numpy and Pillow. No GDAL, network or GIS service required.
Examples:
  python3 scripts/build_terrain.py --source /tmp/hkust-geodata/dtm --output .

This is a bare-earth survey surface. It is not current construction, building
geometry, a measured water surface, or an independently traced shoreline.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, struct
import numpy as np
from PIL import Image, ImageDraw

ORIGIN = (844800.0, 820500.0)
RETRIEVED = '2026-09-05'
NODATA = -9999.0
SURVEY = {'from':'2019-12-20', 'to':'2020-02-02'}
TILES = ['11NE10B','11NE10D','11NE15B','12NW6A','12NW6C','12NW11A','12NW6D','12NW11B']

def write_glb(path, positions, normals, colors, indices, extras):
    arrays=[positions.astype('<f4'),normals.astype('<f4'),colors.astype('<f4'),indices.astype('<u4')]
    offsets=[]; binary=b''
    for a in arrays:
        binary += b'\x00' * (-len(binary) % 4)
        offsets.append(len(binary)); binary += a.tobytes()
    views=[{'buffer':0,'byteOffset':o,'byteLength':a.nbytes,'target':34963 if i==3 else 34962} for i,(o,a) in enumerate(zip(offsets,arrays))]
    accessors=[{'bufferView':i,'componentType':5125 if i==3 else 5126,'count':len(a) if i<3 else a.size,'type':'SCALAR' if i==3 else 'VEC3'} for i,a in enumerate(arrays)]
    accessors[0].update({'min':positions.min(axis=0).astype(float).tolist(),'max':positions.max(axis=0).astype(float).tolist()})
    doc={'asset':{'version':'2.0','generator':'HKUST public-evidence terrain build_terrain.py','copyright':'Terrain source: Civil Engineering and Development Department, Hong Kong SAR Government'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'CEDD_2020_DTM_5m_subset','mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'COLOR_0':2},'indices':3,'material':0}]}],'materials':[{'name':'Elevation-tinted DTM (illustrative colour)','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1},'doubleSided':False}],'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors,'extras':extras}
    j=json.dumps(doc,separators=(',',':')).encode();j+=b' '*(-len(j)%4)
    binary+=b'\x00'*(-len(binary)%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(j)+8+len(binary))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\x00')+binary)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,default=Path('.'));a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);sources=[];rasters=[]
    for tile in TILES:
        p=next(a.source.glob(tile+'(*.tif'))
        with Image.open(p) as im:
            assert im.tag_v2[33550][:2]==(0.5,0.5)
            assert float(im.tag_v2[42113])==NODATA
            pixels=np.asarray(im).copy();tie=im.tag_v2[33922]
        e,n=float(tie[3]),float(tie[4]);h,w=pixels.shape
        rasters.append((e,n,pixels));valid=pixels[pixels!=NODATA]
        src={'tile':tile,'file':p.name,'url':'https://bulkdata.csdi.gov.hk/cedd/lidar/2020dtm/'+p.with_suffix('.zip').name,'sha256_tif':hashlib.sha256(p.read_bytes()).hexdigest(),'size':{'width':w,'height':h},'top_left_grid_m':[e,n],'pixel_size_m':0.5,'valid_cells':int(valid.size),'nodata_cells':int(pixels.size-valid.size),'min_m_hkpd':float(valid.min()),'max_m_hkpd':float(valid.max())}
        sources.append(src)
    xmin=min(r[0] for r in rasters);ymax=max(r[1] for r in rasters)
    xmax=max(e+r.shape[1]*0.5 for e,n,r in rasters);ymin=min(n-r.shape[0]*0.5 for e,n,r in rasters)
    width=int((xmax-xmin)/0.5);height=int((ymax-ymin)/0.5)
    mosaic=np.full((height,width),NODATA,dtype=np.float32)
    for e,n,r in rasters:
        col=int((e-xmin)/0.5);row=int((ymax-n)/0.5)
        mosaic[row:row+r.shape[0],col:col+r.shape[1]]=r
    valid_full=mosaic!=NODATA
    imin=np.unravel_index(np.where(valid_full,mosaic,np.inf).argmin(),mosaic.shape)
    imax=np.unravel_index(np.where(valid_full,mosaic,-np.inf).argmax(),mosaic.shape)
    def extrema(idx):
        row,col=map(int,idx);return {'height_m_hkpd':float(mosaic[row,col]),'easting':xmin+(col+0.5)*0.5,'northing':ymax-(row+0.5)*0.5,'source_mosaic_row_col':[row,col]}
    # Exact source-centre samples at five-metre spacing; never extrapolate.
    stride=10;sy=sx=5
    z=mosaic[sy::stride,sx::stride].copy();rows,cols=z.shape
    # A sample near NoData is withheld if its enclosing 5x5m block contains
    # missing source pixels. This conservatively avoids joining sea gaps.
    block_all_valid=valid_full.reshape(rows,stride,cols,stride).all(axis=(1,3))
    sample_valid=(z!=NODATA)&block_all_valid
    es=xmin+(sx+0.5)*0.5+np.arange(cols)*5
    ns=ymax-(sy+0.5)*0.5-np.arange(rows)*5
    ee,nn=np.meshgrid(es,ns)
    all_positions=np.stack([ee-ORIGIN[0],z,-(nn-ORIGIN[1])],axis=-1)
    cell_valid=sample_valid[:-1,:-1]&sample_valid[1:,:-1]&sample_valid[:-1,1:]&sample_valid[1:,1:]
    rr,cc=np.nonzero(cell_valid)
    aa=rr*cols+cc;bb=aa+1;dd=aa+cols;eei=dd+1
    # z points south; counterclockwise winding has upward y normal.
    faces=np.stack([np.stack([aa,dd,bb],axis=1),np.stack([bb,dd,eei],axis=1)],axis=1).reshape(-1,3)
    used=np.unique(faces);remap=np.full(rows*cols,-1,dtype=np.int32);remap[used]=np.arange(len(used))
    positions=all_positions.reshape(-1,3)[used].astype(np.float32);indices=remap[faces].astype(np.uint32)
    normals=np.zeros_like(positions)
    fn=np.cross(positions[indices[:,1]]-positions[indices[:,0]],positions[indices[:,2]]-positions[indices[:,0]])
    for k in range(3):np.add.at(normals,indices[:,k],fn)
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    # Colours are explicitly illustrative, not a remotely sensed landcover map.
    levels=np.array([0,8,30,100,230,380.]);palette=np.array([[.73,.72,.55],[.55,.63,.44],[.35,.50,.34],[.26,.41,.28],[.38,.45,.33],[.54,.54,.43]])
    colors=np.stack([np.interp(positions[:,1],levels,palette[:,i]) for i in range(3)],axis=1).astype(np.float32)
    origin={'easting':ORIGIN[0],'northing':ORIGIN[1],'horizontal_crs':'EPSG:2326 / Hong Kong 1980 Grid','vertical_datum':'Hong Kong Principal Datum (HKPD)','threejs_axes':'x=easting-origin.easting; y=height_m_hkpd; z=-(northing-origin.northing)'}
    extras={'origin':origin,'survey_date':SURVEY,'retrieved_at':RETRIEVED,'source_resolution_m':0.5,'sample_spacing_m':5,'sample_method':'Exact source pixel-centre sample every 10 pixels; no interpolation. Samples with NoData anywhere in enclosing 5m block omitted. Only full four-valid-corner cells receive triangles.','colour_warning':'Elevation tint is illustrative, not landcover or current aerial photography.','shoreline_warning':'NoData is a source coverage mask; it is not a surveyed shoreline. No synthetic land or bathymetry was filled.'}
    write_glb(a.output/'terrain.glb',positions,normals,colors,indices,extras)
    grid={'version':1,**extras,'rows':rows,'columns':cols,'first_easting':float(es[0]),'first_northing':float(ns[0]),'easting_step':5,'northing_step':-5,'ordering':'row-major, north to south; null = missing/withheld source evidence','height_unit':'m HKPD','heights':[round(float(v),3) if ok else None for v,ok in zip(z.flat,sample_valid.flat)]}
    (a.output/'height-grid-5m.json').write_text(json.dumps(grid,separators=(',',':')))
    # Binary forms are optional for engines that do not consume glTF.
    positions.astype('<f4').tofile(a.output/'terrain.positions.f32');normals.astype('<f4').tofile(a.output/'terrain.normals.f32');colors.astype('<f4').tofile(a.output/'terrain.colors.f32');indices.astype('<u4').tofile(a.output/'terrain.indices.u32')
    # Visual QA raster: gray = source NoData, black outline = withheld boundary.
    preview=np.zeros((rows,cols,3),dtype=np.uint8);preview[:]=[174,190,203]
    for k in range(3):preview[:,:,k]=np.where(sample_valid,np.interp(z,levels,palette[:,k])*255,preview[:,:,k])
    Image.fromarray(preview).resize((cols*3,rows*3),Image.Resampling.NEAREST).save(a.output/'terrain-elevation-preview.png')
    # Edge segments classify the model boundary; they do not assert coastline.
    ec=np.sort(np.concatenate([indices[:,[0,1]],indices[:,[1,2]],indices[:,[2,0]]]),axis=1)
    edges,count=np.unique(ec,axis=0,return_counts=True);edges=edges[count==1]
    boundary_positions=positions[edges].reshape(-1,3)
    boundary_positions.astype('<f4').tofile(a.output/'terrain-boundary.positions.f32')
    qa={'source_raster_dimensions':[width,height],'source_pixels_total':int(mosaic.size),'source_valid_pixels':int(valid_full.sum()),'source_nodata_pixels':int((~valid_full).sum()),'minimum':extrema(imin),'maximum':extrema(imax),'mesh_vertices':len(positions),'mesh_triangles':len(indices),'grid_dimensions':[cols,rows],'retained_grid_samples':int(sample_valid.sum()),'grid_missing_or_withheld':int((~sample_valid).sum()),'mesh_min_max_y':[float(positions[:,1].min()),float(positions[:,1].max())],'surface_normals_upward':bool((fn[:,1]>0).all()),'indices_in_range':bool(int(indices.max())<len(positions)),'finite_mesh_values':bool(np.isfinite(positions).all() and np.isfinite(normals).all()),'no_faces_touch_invalid_samples':bool(sample_valid.flat[used].all()),'bounds_grid_m':{'west':xmin,'east':xmax,'south':ymin,'north':ymax},'notes':['Six central sheets plus east-adjacent 12NW6D and 12NW11B preserve campus coastal ground coverage. The missing northeast sheet is left NoData. A rectangular crop boundary must not be displayed as a surveyed sea coast.','2020 bare-earth heights predate recent campus projects. Do not use this surface to infer finished grades for construction completed after survey.','Maximum source height is from the western hillside, not a building or campus roof.']}
    manifest={'name':'HKUST Clear Water Bay CEDD 2020 DTM subset','origin':origin,'survey_date':SURVEY,'retrieved_at':RETRIEVED,'source_metadata':'https://portal.csdi.gov.hk/csdi-webpage/metadata/cedd_rcd_1629267205233_87895/html','terms':'https://portal.csdi.gov.hk/csdi-webpage/doc/TNC','credit':'Civil Engineering and Development Department, Hong Kong SAR Government. Derived display mesh from public 0.5m Digital Terrain Model.','processing':extras,'qa':qa,'sources':sources,'assets':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in a.output.glob('*') if p.is_file() and p.name not in ['terrain-manifest.json','README.zh-CN.md']}}
    (a.output/'terrain-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(qa,indent=2))

if __name__=='__main__':main()
