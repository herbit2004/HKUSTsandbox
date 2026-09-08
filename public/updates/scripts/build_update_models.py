#!/usr/bin/env python3
"""Derive open-topped, translucent display envelopes from official data only.
No roof or inferred storey height. Uses published base-map XY and actual room
coordinate Z extrema, never floor catalog ordinals. Python + numpy + pyproj.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from pyproj import Transformer

MATCHES={'UG Hall X':'ug-hall-10','UG Hall XI':'ug-hall-11','UG Hall XII':'ug-hall-12','UG Hall XIII':'ug-hall-13','Martin Ka Shing Lee Innovation Building':'campus-19'}
ORIGIN={'easting':844800,'northing':820500,'horizontalCRS':'EPSG:2326','axes':'x=E-844800; y=original sourceZ; z=820500-N','verticalDatum':'Source Z vertical datum not independently verified; no DTM snapping or vertical offset applied'}
PA_BASE='https://navigate.ust.hk/path/api/app/assets/all-base-map'
LIMITATIONS=[
 'This is an open-topped display envelope from base-map outlines and observed floor sourceZ. It is not a measured facade, full exterior, BIM, or complete building volume.',
 'The lowest observed floor is not necessarily the building base and the highest observed floor is not the roof. No top cap or roof height is generated.',
 'Published base-map outlines are repeated through the observed Z range; this does not prove that exterior walls are vertical or that every floor has the same plan.',
 'Line rings at observed floor Z repeat the base outline and are only height guides. They are not complete floor slabs or rooms.',
 'Missing floors, rooms, roof, facade materials, windows, balconies, structural details and building services remain absent.',
 'Source Z values are preserved numerically. Their vertical datum and agreement with the government HKPD terrain have not been independently established.',
 'The 2026-09-05 retrieval date does not establish the source geometry capture date, as-built completion date, access status, or actual roof elevation.'
]
def walk_coordinates(a):
 if isinstance(a,list):
  if a and isinstance(a[0],(int,float)):yield a
  else:
   for b in a:yield from walk_coordinates(b)

def write_glb(path,wall_positions,wall_normals,wall_indices,line_positions,line_indices,metadata):
 chunks=[];views=[];accessors=[];blob=bytearray()
 def acc(a,type,component,target):
  while len(blob)%4:blob.extend(b'\x00')
  vi=len(views);views.append({'buffer':0,'byteOffset':len(blob),'byteLength':a.nbytes,'target':target});blob.extend(a.tobytes())
  d={'bufferView':vi,'componentType':component,'count':len(a) if type!='SCALAR' else a.size,'type':type}
  if type=='VEC3':d.update({'min':a.min(axis=0).astype(float).tolist(),'max':a.max(axis=0).astype(float).tolist()})
  accessors.append(d);return len(accessors)-1
 primitives=[]
 if len(wall_positions):
  p=acc(wall_positions.astype('<f4'),'VEC3',5126,34962);n=acc(wall_normals.astype('<f4'),'VEC3',5126,34962);i=acc(wall_indices.astype('<u4'),'SCALAR',5125,34963)
  primitives.append({'attributes':{'POSITION':p,'NORMAL':n},'indices':i,'material':0,'mode':4})
 p=acc(line_positions.astype('<f4'),'VEC3',5126,34962);i=acc(line_indices.astype('<u4'),'SCALAR',5125,34963)
 primitives.append({'attributes':{'POSITION':p},'indices':i,'material':1,'mode':1})
 doc={'asset':{'version':'2.0','generator':'HKUST source-Z open-envelope builder','copyright':'Underlying published geographic map data: The Hong Kong University of Science and Technology'},'extensionsUsed':['KHR_materials_unlit'],'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':metadata['name']+' — approximate observed-Z envelope','mesh':0}],'meshes':[{'primitives':primitives}],'materials':[{'name':'Approximate open side envelope — translucent amber','pbrMetallicRoughness':{'baseColorFactor':[1,.58,.16,.16],'metallicFactor':0,'roughnessFactor':1},'alphaMode':'BLEND','doubleSided':True,'extensions':{'KHR_materials_unlit':{}}},{'name':'Published outline at observed Z — guide lines','pbrMetallicRoughness':{'baseColorFactor':[.12,.52,.95,.9],'metallicFactor':0,'roughnessFactor':1},'alphaMode':'BLEND','doubleSided':True,'extensions':{'KHR_materials_unlit':{}}}],'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors,'extras':metadata}
 raw=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode();raw+=b' '*(-len(raw)%4)
 while len(blob)%4:blob.extend(b'\x00')
 path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(blob))+struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(blob),b'BIN\x00')+blob)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 base=json.load(open(a.source/'all_base_map.geojson'));catalog=json.load(open(a.source/'manifest.json'))
 projection=Transformer.from_crs(4326,2326,always_xy=True)
 selected=[f for f in base['features']if f['properties']['name']in MATCHES]
 (a.output/'source-footprints.geojson').write_text(json.dumps({'type':'FeatureCollection','features':selected},separators=(',',':')))
 models=[]
 for feature in selected:
  name=feature['properties']['name'];id=MATCHES[name];bid=feature['properties']['building_id'];floors=[];z_values=[]
  for fl in catalog['floors']:
   if fl['building_id']!=bid:continue
   fp=a.source/'floors'/fl['_id']/'rooms.geojson';data=json.load(open(fp));zs=[float(c[2])for f in data['features']for c in walk_coordinates(f['geometry']['coordinates'])if len(c)>2 and np.isfinite(c[2])]
   source=next(s for s in fl['sources']if '/geojson?'in s['endpoint'])
   rec={'floor':fl['name'],'floorId':fl['_id'],'source':source['endpoint'],'sourceGeojsonResponseSHA256':source['sha256'],'roomGeojsonSHA256':hashlib.sha256(fp.read_bytes()).hexdigest(),'roomFeatures':len(data['features']),'coordinatesWithZ':len(zs),'sourceZValues':sorted(set(zs)),'catalogElevationIgnored':fl['elevation']}
   if zs:rec.update({'zmin':min(zs),'zmax':max(zs)});z_values.extend(zs)
   floors.append(rec)
  if not z_values:raise ValueError('No source Z; cannot invent elevation for '+name)
  zmin,zmax=min(z_values),max(z_values);levels=sorted(set(z_values));is_volume=zmax>zmin
  polys=feature['geometry']['coordinates'] if feature['geometry']['type']=='MultiPolygon'else[feature['geometry']['coordinates']]
  wall_pos=[];wall_norm=[];wall_ind=[];line_pos=[];line_ind=[];source_vertices=0
  for poly in polys:
   for ring in poly:
    xy=np.array([projection.transform(c[0],c[1])for c in ring]);xy-=np.array([844800,820500]);xy[:,1]*=-1;source_vertices+=len(xy)
    if not np.allclose(xy[0],xy[-1],atol=1e-9,rtol=0):raise ValueError('Unexpected unclosed source ring')
    for h in levels:
     start=len(line_pos);line_pos.extend([[float(x),h,float(z)]for x,z in xy]);line_ind.extend([[start+k,start+k+1]for k in range(len(xy)-1)])
    if is_volume:
     for p,q in zip(xy[:-1],xy[1:]):
      if np.linalg.norm(p-q)<1e-8:continue
      v=np.array([[p[0],zmin,p[1]],[q[0],zmin,q[1]],[p[0],zmax,p[1]],[q[0],zmax,q[1]]],dtype=np.float64)
      n=np.cross(v[1]-v[0],v[2]-v[0]);n/=np.linalg.norm(n)
      start=len(wall_pos);wall_pos.extend(v.tolist());wall_norm.extend([n.tolist()]*4);wall_ind.extend([[start,start+1,start+2],[start+1,start+3,start+2]])
      start=len(line_pos);line_pos.extend([v[0].tolist(),v[2].tolist()]);line_ind.append([start,start+1])
  metadata={'id':id,'buildingId':bid,'name':name,'file':id+'.glb','displayLabel':'2026 公开轮廓体量（近似）','method':'open-top-side-envelope-and-observed-Z-outline-guides' if is_volume else 'single-observed-Z-outline-only','origin':ORIGIN,'sourceZMin':zmin,'sourceZMax':zmax,'sourceZSpan':zmax-zmin,'observedZLevels':levels,'hasVolume':is_volume,'roofCapGenerated':False,'groundOrBottomCapGenerated':False,'footprintSource':PA_BASE,'footprintGeometryType':feature['geometry']['type'],'footprintPolygonParts':len(polys),'footprintSourceVertexCount':source_vertices,'sourceFloors':floors,'retrievedAt':'2026-09-05','sourceGeometryCaptureDate':None,'limitations':LIMITATIONS}
  wp=np.array(wall_pos,dtype=np.float32).reshape(-1,3);wn=np.array(wall_norm,dtype=np.float32).reshape(-1,3);wi=np.array(wall_ind,dtype=np.uint32).reshape(-1,3);lp=np.array(line_pos,dtype=np.float32).reshape(-1,3);li=np.array(line_ind,dtype=np.uint32).reshape(-1,2)
  assert np.isfinite(lp).all()and np.isfinite(wp).all()
  if len(wp):assert wi.max()<len(wp)
  assert li.max()<len(lp)
  assert set(np.unique(wp[:,1])).issubset(set(np.array([zmin,zmax],dtype=np.float32)))
  assert set(np.unique(lp[:,1])).issubset(set(np.array(levels,dtype=np.float32)))
  file=a.output/metadata['file'];write_glb(file,wp,wn,wi,lp,li,metadata)
  metadata.update({'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'qa':{'allCoordinatesFinite':True,'indicesWithinBounds':True,'sideVerticesOnlyAtObservedZExtrema':True,'lineLevelsOnlyAtObservedSourceZ':True,'triangleCount':len(wi),'lineSegmentCount':len(li),'sideVertexCount':len(wp)}})
  (a.output/(id+'.manifest.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2));models.append(metadata)
 manifest={'label':'2026 公开轮廓体量（近似）','checkedAt':'2026-09-05','origin':ORIGIN,'scope':'Five priority 2026 campus update buildings. This overlay is separate from the government 3D mesh; do not replace, hide or rewrite government evidence with this approximation.','models':models,'limitations':LIMITATIONS}
 (a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print(json.dumps([{'id':m['id'],'file':m['file'],'zmin':m['sourceZMin'],'zmax':m['sourceZMax'],'floors':[f['floor']for f in m['sourceFloors']],'bytes':m['bytes']}for m in models],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
