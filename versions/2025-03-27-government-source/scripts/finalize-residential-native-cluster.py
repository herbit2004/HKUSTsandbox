#!/usr/bin/env python3
"""Apply fixed, newly audited source fragment indices; preserve original leaf GLBs.
Requires numpy, Pillow, affine, rasterio. Does not fetch or modify source payloads.
"""
import argparse,hashlib,importlib.util,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
from affine import Affine
from rasterio.features import rasterize
from hkust_source_geometry import geometry
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args();P=args.project;D=P/'public/models/hires/partial-residential-ias';m=json.loads((D/'manifest-before-fragment-correction.json').read_text());patch=m['patches'][0];evidence=json.loads((D/'fine-fragment-correction-evidence.json').read_text());assert evidence['status']=='confirmed-source-floater'and evidence['combinedRemovedTriangleCount']==1242 and evidence['distanceLowerBoundToAnyOtherNewTriangleMeters']>15
helper=P/'public/models/source-corrections/ug10-isolated-photogrammetry-fragment-9/build_correction.py';code=helper.read_text().replace('assert removed==9','assert removed==len(REMOVE_GLOBAL)').replace("'ug10-isolated-photogrammetry-fragment-9'","'ug12-refined-source-isolated-fragment'");namespace={'__name__':'source_correction_helper'};exec(compile(code,str(helper),'exec'),namespace)
validations=[]
for correction in evidence['components']:
 t=next(t for t in patch['levels']['high']['tiles']if t['id']==correction['id']);source=P/'public/models/hires'/t['url'];original=dict(t);dest=source.with_name(source.stem+'.corrected.glb');namespace.update(TILE=t['id'],SOURCE_SHA=correction['sourceSha256'],REMOVE_GLOBAL=correction['triangleIndices']);result=namespace['build'](source,dest)
 original_tri,_=geometry(source,np.array(t['matrix']).reshape(4,4,order='F'));new_tri,_=geometry(dest,np.array(t['matrix']).reshape(4,4,order='F'));expected=np.delete(original_tri,correction['triangleIndices'],axis=0);assert np.array_equal(expected,new_tri)
 t.update(url='partial-residential-ias/'+dest.name,bytes=result['bytes'],sha256=result['sha256'],triangles=result['triangles'],vertices=t['vertices']-result['verticesRemoved'],bounds={'min':new_tri.min((0,1)).tolist(),'max':new_tri.max((0,1)).tolist()});t['center']=((new_tri.min((0,1))+new_tri.max((0,1)))/2).tolist();t['sourceCorrection']={'id':'ug12-refined-source-isolated-fragment','originalUrl':original['url'],'originalSha256':original['sha256'],'originalTriangles':original['triangles'],'removedTriangleIndices':correction['triangleIndices'],'evidence':'partial-residential-ias/fine-fragment-correction-evidence.json'};validations.append({'id':t['id'],'removedTriangles':result['trianglesRemoved'],'removedVertices':result['verticesRemoved'],'retainedPositionsExact':True,'sourceSha256':original['sha256'],'derivedSha256':result['sha256']})
tris=[]
for t in patch['levels']['high']['tiles']:
 tr,_=geometry(P/'public/models/hires'/t['url'],np.array(t['matrix']).reshape(4,4,order='F'));tris.append(tr)
tri=np.concatenate(tris);low=tri.min((0,1));high=tri.max((0,1));mask=patch['mask'];x0,z0=mask['minX'],mask['minZ'];res=mask['pixelSizeMeters'];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);xz=tri[:,:,[0,2]];ok=abs(cross[:,1])>1e-9;image=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in xz[ok]),out_shape=(mask['height'],mask['width']),transform=Affine(res,0,x0,0,res,z0),dtype='uint8',all_touched=False);Image.fromarray(image).save(D/'coverage.png');mask['coveredPixels']=int((image>0).sum());mask['sha256']=hashlib.sha256((D/'coverage.png').read_bytes()).hexdigest();mask['source']='Actual projected retained source triangles from123 terminal leaves, excluding only two positively audited disconnected source components. No bbox/hull replacement.'
level=patch['levels']['high'];level['mask']=mask
for field in ['triangles','bytes','vertices','textureBytes','textureMipBytes']:level[field]=sum(t[field]for t in level['tiles'])
patch['bounds']={'min':low.tolist(),'max':high.tolist()};patch['center']=((low+high)/2).tolist();patch['evidence']['floaterCheckPending']=False;patch['evidence']['sourceTriangleCountBeforeCorrection']=908209;patch['evidence']['retainedTriangleCountAfterCorrection']=len(tri);patch['evidence']['sourceCorrection']='fine-fragment-correction-evidence.json';patch['evidence']['sourceCorrectionRemovedTriangleCount']=1242
(D/'manifest.json').write_text(json.dumps(m,indent=2));(D/'correction-validation.json').write_text(json.dumps({'pass':True,'corrections':validations,'removedTriangles':sum(v['removedTriangles']for v in validations),'retainedTriangles':len(tri),'matrixAndSourcePayloadUnchanged':True},indent=2));print(json.dumps({'tiles':len(level['tiles']),'triangles':len(tri),'exactTextureMipMiB':level['textureMipBytes']/1048576,'mask':mask},indent=2))
