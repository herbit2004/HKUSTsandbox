import json,sys,hashlib,math,argparse
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union
import shapely
from rasterio.features import rasterize
from affine import Affine
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path('.'));args=ap.parse_args();P=args.project.resolve();O=P/'public/models/current-forms/halls-current';D=json.load(open(O/'manifest.json'))
from hkust_source_geometry import geometry
patch=json.load(open(P/'public/models/hires/partial-residential-ias/manifest.json'))['patches'][0]
source=[];tileids=[];sourceix=[];sourcefacts=[]
for tile in patch['levels']['high']['tiles']:
 mn=tile['bounds']['min'];mx=tile['bounds']['max']
 if mx[0]<650 or mn[0]>790 or mx[2]<-1170 or mn[2]>-1010:continue
 path=P/'public/models/hires'/tile['url'];digest=hashlib.sha256(path.read_bytes()).hexdigest();assert digest==tile['sha256']
 tri,_=geometry(path,np.array(tile['matrix']).reshape(4,4,order='F'));source.append(tri);tileids.extend([tile['id']]*len(tri));sourceix.extend(range(len(tri)));sourcefacts.append({'id':tile['id'],'url':tile['url'],'sha256':digest,'matrix':tile['matrix']})
T=np.concatenate(source);tileids=np.array(tileids);sourceix=np.array(sourceix);C=T.mean(1);N=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]);N/=np.maximum(1e-20,np.linalg.norm(N,axis=1))[:,None]
envs=[unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in b['envelopeParts']])for b in D['buildings']]
points=shapely.points(C[:,0],C[:,2]);dist=np.array([shapely.distance(e,points)for e in envs]);nearest=dist.argmin(0)
ray=json.load(open(P/'docs/source-evidence-v4/building-quality/halls-stage-ray-audit.json'))['rays']
report=[]
for bi,b in enumerate(D['buildings']):
 e=envs[bi];m=b['mask'].get('actualModelProjection',b['mask']);upper=[167.3,173.2,179.1][bi];lo=133.75;d=dist[bi]
 # Six metres is only the finite acquisition screen beyond the exact drawing:
 # the largest checked source-wall point is 5.290m outside it. Output pixels
 # always require an actual connected source triangle, never a filled buffer.
 select=(nearest==bi)&(d<=6)&(T[:,:,1].max(1)>=lo)&(T[:,:,1].min(1)<=upper)&((abs(N[:,1])<.65)|(d<.75))
 ids=np.flatnonzero(select);tri=T[ids];v=np.round(tri.reshape(-1,3)/.03).astype(np.int64);_,inverse=np.unique(v,axis=0,return_inverse=True);faces=np.repeat(np.arange(len(ids)),3);nv=inverse.max()+1
 order=np.argsort(inverse);iv=inverse[order];fv=faces[order];shared=iv[1:]==iv[:-1];a=fv[:-1][shared];bb=fv[1:][shared];graph=coo_matrix((np.ones(len(a)*2),(np.r_[a,bb],np.r_[bb,a])),shape=(len(ids),len(ids))).tocsr();count,component=connected_components(graph,directed=False)
 seed=(d[ids]<=.6)
 for q in ray:
  if q['oldInFrontOfNew']:
   h=q['oldSourceVisible'];seed|=(tileids[ids]==h['sourceId'])&(sourceix[ids]==h['triangleIndex'])
 keep=np.isin(component,np.unique(component[seed]));ids=ids[keep];tri=T[ids]
 polys=[];bounds=[e.bounds]
 for i,t in zip(ids,tri):
  verts=list(t)
  for limit,sign in [(lo,1),(upper,-1)]:
   clipped=[]
   for start,end in zip(verts,verts[1:]+verts[:1]):
    a=(start[1]-limit)*sign>=0;c=(end[1]-limit)*sign>=0
    if a:clipped.append(start)
    if a!=c:clipped.append(start+(end-start)*((limit-start[1])/(end[1]-start[1])))
   verts=clipped
  if len(verts)<3:continue
  clipped=np.array(verts);q=Polygon(clipped[:,[0,2]])
  # Infinitesimal projected wall triangles retain their source edge plus the
  # half-pixel conservative guard; no source wall is discarded for zero area.
  if q.area<1e-9:q=shapely.convex_hull(q).buffer(.251)
  else:q=q.buffer(.251,join_style=2)
  polys.append((q,int(math.floor(clipped[:,1].min()))))
  bounds.append(q.bounds)
 mn=np.floor(np.array(bounds)[:,:2].min(0)*2)/2;mx=np.ceil(np.array(bounds)[:,2:].max(0)*2)/2;w,h=((mx-mn)*2).astype(int);A=Affine(.5,0,mn[0],0,.5,mn[1]);alpha=rasterize(sorted(polys,key=lambda p:p[1],reverse=True),out_shape=(h,w),transform=A,fill=0,dtype='uint8',all_touched=True)
 # Keep the existing exact final-model projection as an independently named
 # source. It alone gets common-minY, with only source pixel intersection.
 core=rasterize([(e,255)],out_shape=(h,w),transform=A,fill=0,dtype='uint8',all_touched=True)
 rgba=np.zeros((h,w,4),np.uint8);occupied=(alpha>0)|(core>0);rgba[occupied,:3]=255;rgba[alpha>0,3]=alpha[alpha>0];rgba[core>0,3]=255
 path=O/(b['catalogId']+'-replacement-support.png');Image.fromarray(rgba).save(path)
 sourcecount={str(t):int(np.count_nonzero(tileids[ids]==t))for t in np.unique(tileids[ids])}
 check=[]
 for q in ray:
  hit=q['oldSourceVisible']
  if not hit or min(hit['distanceToEnvelope'],key=hit['distanceToEnvelope'].get)!=b['catalogId']:continue
  p=hit['position'];x=int((p[0]-mn[0])*2);z=int((p[2]-mn[1])*2);pixel=rgba[z,x]if 0<=x<w and 0<=z<h else [0,0,0,0];lower=lo if pixel[3]==255 else max(lo,int(pixel[3]));check.append({'pixel':q['pixel'],'previousOldInFront':q['oldInFrontOfNew'],'discardAfter':bool(pixel[0]>127 and lower<=p[1]<=upper),'guardMinY':lower})
 item={'catalogId':b['catalogId'],'url':path.name,'boundsXZ':{'min':mn.tolist(),'max':mx.tolist()},'width':int(w),'height':int(h),'pixelSizeMeters':.5,'replacementMinY':lo,'replacementMaxY':upper,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pixelMinYEncoding':'int-meters-alpha-255-common','actualModelProjection':m,'sourceSupport':{'method':'Welded source-triangle components seeded by drawing-adjacent faces and independently checked camera-ray wall hits; exterior candidates are vertical-ish faces; original nodes/matrices retained. Half-pixel source projection guard and conservative all-touched rasterization.','maximumAcquisitionDistanceMeters':6,'distanceIsNotFinalMaskFill':True,'sourceMaximumCheckedWallDistanceMeters':5.289943838565689,'normalAbsYOutsideDrawingLimit':.65,'weldToleranceMeters':.03,'triangleCount':len(ids),'componentsConsidered':count,'retainedComponentCount':len(np.unique(component[keep])),'sourceTriangleCounts':sourcecount,'sourceTriangleIndexAsset':'evidence/'+b['catalogId']+'-replacement-source-triangles.json','baseSource':'actual final-model envelope projection','outsideSource':'actual terminal source triangles, alpha=min observed triangle Y rounded down; source geometry is an attribution approximation at facade joins, not a surveyed ownership boundary.'},'checks':{'occupiedPixels':int(occupied.sum()),'commonMinYPixels':int((core>0).sum()),'sourceSpecificMinYPixels':int(((alpha>0)&(core==0)).sum()),'cameraRays':check}}
 selected=[{'sourceId':str(t),'indices':sourceix[ids][tileids[ids]==t].tolist()}for t in np.unique(tileids[ids])];(O/'evidence'/(b['catalogId']+'-replacement-source-triangles.json')).write_text(json.dumps(selected,separators=(',',':')))
 report.append(item);b['mask']=item;print(b['catalogId'],len(ids),item['checks'],flush=True)
(O/'evidence/replacement-support-audit.json').write_text(json.dumps({'buildings':report,'verifiedSources':sourcefacts},indent=2));D['version']=2;D['parameters']['replacementSupport']='actual source facade components and separate current geometry, per-pixel source minimum Y; not a cadastral boundary';D['limitations'].append('Outside the public floor envelope, replacement support follows actual connected source facade triangles. The finite6m candidate screen is not filled; each added pixel has source-triangle support and a source-specific lower height. This is a visual correspondence approximation at facade joins, not new ownership geometry.');temp=O/'manifest.json.tmp';temp.write_text(json.dumps(D,ensure_ascii=False,indent=2)+'\n');temp.replace(O/'manifest.json')
