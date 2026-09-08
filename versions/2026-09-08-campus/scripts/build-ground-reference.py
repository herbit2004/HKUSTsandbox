#!/usr/bin/env python3
"""No image texture or generated ground: references actual triangles and original DTM.
Dependencies: numpy, Pillow, shapely2.
"""
import json,sys,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import polygons,points,STRtree
import argparse
from hkust_source_geometry import Heights, geometry
ap=argparse.ArgumentParser(description="Source-ground preservation inside building replacement masks.")
ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
ap.add_argument('--output',type=Path)
ap.add_argument('--qa-cache',type=Path,help='Optional diagnostic NPZ outside served assets')
args=ap.parse_args();P=args.project;D=args.output or P/'public/surfaces/ground-reference';D.mkdir(parents=True,exist_ok=True)
bundles=json.load(open(P/'public/models/exteriors/manifest.json'))['bundles'];bounds=np.array([[*b['mask']['boundsXZ']['min'],*b['mask']['boundsXZ']['max']]for b in bundles]);x0,z0=np.floor(bounds[:,:2].min(0));x1,z1=np.ceil(bounds[:,2:].max(0));step=.5;w,h=round((x1-x0)/step),round((z1-z0)/step);union=np.zeros((h,w),bool)
for b in bundles:
 m=b['mask'];a=np.asarray(Image.open(P/'public/models/exteriors'/m['url']));a=a[:,:,0]if a.ndim==3 else a;assert m['width']==a.shape[1]and m['height']==a.shape[0];x,z=m['boundsXZ']['min'];c=round((x-x0)/step);r=round((z-z0)/step);assert m.get('metersPerPixel',.5)==.5;union[r:r+a.shape[0],c:c+a.shape[1]]|=a>0
rr,cc=np.nonzero(union);xz=np.column_stack([x0+(cc+.5)*step,z0+(rr+.5)*step]);en=np.column_stack([xz[:,0]+844800,820500-xz[:,1]]);dtm=Heights(list((P/'public/terrain/source-data').glob('*.tif')))(en);covered=np.zeros(len(rr),bool);photo=np.full(len(rr),np.nan);used=[];normal_threshold=.6;band=1.0
for t in json.load(open(P/'public/models/render-manifest.json'))['tiles']:
 b=t['bounds'];lo=np.array(b['min'])[[0,2]];hi=np.array(b['max'])[[0,2]];ix=np.flatnonzero((~covered)&np.isfinite(dtm)&((xz>=lo)&(xz<=hi)).all(1))
 if not len(ix):continue
 path=P/'public/models'/t['url'];tri,_=geometry(path,np.array(t['matrix']).reshape(4,4,order='F'));cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norm=np.linalg.norm(cross,axis=1);good=abs(cross[:,1])>=normal_threshold*norm;good&=norm>1e-8;tri=tri[good];q=tri[:,:,[0,2]];pairs=STRtree(polygons(q)).query(points(xz[ix]),predicate='intersects');used.append({'id':t['id'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'groundSlopeCandidateTriangles':len(tri)})
 if not pairs.shape[1]:continue
 k=ix[pairs[0]];a=q[pairs[1]];p=xz[k];den=(a[:,1,1]-a[:,2,1])*(a[:,0,0]-a[:,2,0])+(a[:,2,0]-a[:,1,0])*(a[:,0,1]-a[:,2,1]);u=((a[:,1,1]-a[:,2,1])*(p[:,0]-a[:,2,0])+(a[:,2,0]-a[:,1,0])*(p[:,1]-a[:,2,1]))/den;v=((a[:,2,1]-a[:,0,1])*(p[:,0]-a[:,2,0])+(a[:,0,0]-a[:,2,0])*(p[:,1]-a[:,2,1]))/den;y=tri[pairs[1],:,1];py=u*y[:,0]+v*y[:,1]+(1-u-v)*y[:,2];ok=abs(py-dtm[k])<=band;covered[k[ok]]=True;photo[k[ok]]=py[ok]
encoded=np.floor(np.where(np.isfinite(dtm),dtm,0)*256).astype('uint16');image=np.zeros((h,w,4),dtype='uint8');image[:,:,3]=255;image[rr,cc,0]=covered*255;image[rr,cc,1]=encoded//256;image[rr,cc,2]=encoded%256;Image.fromarray(image).save(D/'ground-reference.png')
if args.qa_cache:np.savez_compressed(args.qa_cache,xz=xz,dtm=dtm,photo=photo,covered=covered)
report={'url':'ground-reference.png','minX':x0,'minZ':z0,'maxX':x1,'maxZ':z1,'width':w,'height':h,'pixelSizeMeters':step,'bandMeters':band,'minimumAbsoluteNormalY':normal_threshold,'groundPixels':int(covered.sum()),'groundAreaM2':float(covered.sum()*step*step),'replacementProjectedPixels':len(rr),'baseTextureBytes':w*h*4,'maskBytes':(D/'ground-reference.png').stat().st_size,'heightEncoding':'R=actual source mesh ground candidate coverage; G integer DTM meters; B fraction/256. NoColorSpace, Nearest, flipY=false.','source':'Original baseline 3D Visualisation Map triangles, actual vertical point intersections plus source CEDD0.5m DTM. No photograph pixels or generated surface.','method':'Inside current eight building replacement projections, accept actual nondegenerate source triangles with |normalY|>=0.6 and height within±1m of original DTM. Shader independently repeats slope/band check for rendered photo fragment. Do not preserve roofs or fake source ground where no accepted source triangle exists.','shaderPolicy':'Building replacement masks preserve compatible source ground fragments; terrain coverage remains active at these actual source ground pixels. Floor openings and new TDOP surface masks retain priority. meshPartial retains priority over its old baseline even at ground.','sources':used,'sourceTerrainHashes':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in(P/'public/terrain/source-data').glob('*.tif')],'heightDifference':{'min':float(np.nanmin(photo-dtm)),'max':float(np.nanmax(photo-dtm)),'median':float(np.nanmedian(photo-dtm))},'limitations':['This is an explicit renderer registration tolerance, not certified ground semantic classification. Source mesh vertical datum and epoch differ from DTM.','Cells without compatible source ground remain governed by existing replacement rules.','No height is changed and no roof orthophoto is projected onto ground.']}
(D/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k not in ['sources','sourceTerrainHashes']},indent=2))
