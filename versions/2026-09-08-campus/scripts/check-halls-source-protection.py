import json,sys,hashlib,argparse
from pathlib import Path
import numpy as np
from PIL import Image
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();P=args.project;O=args.cache;sys.path.insert(0,str(P/'scripts'));from hkust_source_geometry import geometry,Heights
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
D=json.load(open(P/'public/models/current-forms/halls-current/manifest.json'));m=D['sourceProtection'];a=np.frombuffer((P/'public/models/current-forms/halls-current'/m['url']).read_bytes(),np.uint8).reshape(m['height'],m['width'],4);c=np.load(O/'source-analysis.npz');T=c['triangles'];C=c['centroids'];N=c['normal'];S=json.load(open(O/'source-tiles.json'));W=json.load(open(P/'docs/source-evidence-v4/building-quality/hall-source-protection/source-protection-witnesses.json'));assert hashlib.sha256(a.tobytes()).hexdigest()==m['sha256'];assert hashlib.sha256((P/'public/surfaces/ground-reference/ground-reference.png').read_bytes()).hexdigest()==m['unchangedGroundReferenceSHA256']
for s in S:assert hashlib.sha256((P/'public/models/hires'/s['url']).read_bytes()).hexdigest()==s['sha256']
def sample(points,image,bounds):
 x=np.floor((points[:,0]-bounds[0])/.5).astype(int);z=np.floor((points[:,2]-bounds[1])/.5).astype(int);valid=(x>=0)&(z>=0)&(x<image.shape[1])&(z<image.shape[0]);p=np.zeros((len(points),4));p[:,3]=255;p[valid]=image[z[valid],x[valid]];return p
G=json.load(open(P/'public/surfaces/ground-reference/manifest.json'));ga=np.asarray(Image.open(P/'public/surfaces/ground-reference'/G['url']).convert('RGBA'))
def protection(points,normals):
 p=sample(points,a,m['boundsXZ']['min']);ground=(p[:,0]>0)&(abs(points[:,1]-p[:,0]-p[:,1]/256)<=1)&(abs(normals[:,1])>=.6);domain=unary_union([Polygon(part['rings'][0],part['rings'][1:])for part in m['structureParts']]);struct=(p[:,2]<255)&(p[:,3]<255)&(points[:,1]>=p[:,2])&(points[:,1]<=p[:,3])&shapely.covers(domain,shapely.points(points[:,[0,2]]));gp=sample(points,ga,[G['minX'],G['minZ']]);old=(gp[:,0]>127)&(abs(points[:,1]-gp[:,1]-gp[:,2]/256)<=G['bandMeters'])&(abs(normals[:,1])>=.6);return ground|struct|old
masks=[(b['mask'],np.asarray(Image.open(P/'public/models/current-forms/halls-current'/b['mask']['url']).convert('RGBA')))for b in D['buildings']]
def removed(points):
 lo=np.full(len(points),np.inf);hi=np.full(len(points),-np.inf)
 for mm,im in masks:
  p=sample(points,im,mm['boundsXZ']['min']);on=p[:,0]>127;l=np.where(p[:,3]==255,mm['replacementMinY'],np.maximum(mm['replacementMinY'],p[:,3]));lo[on]=np.minimum(lo[on],l[on]);hi[on]=np.maximum(hi[on],mm['replacementMaxY'])
 return (points[:,1]>=lo)&(points[:,1]<=hi)
env=unary_union([Polygon(part['rings'][0],part['rings'][1:])for b in D['buildings']for part in b['envelopeParts']]);dtm=Heights(sorted((P/'public/terrain/source-data').glob('*.tif')))(np.column_stack([C[:,0]+844800,820500-C[:,2]]));originalRemoved=removed(C);restored=originalRemoved&protection(C,N);groundgood=originalRemoved&~shapely.contains_xy(env,C[:,0],C[:,2])&(abs(N[:,1])>=.6)&(abs(C[:,1]-dtm)<=1)
# independent barycentric witness validation, rather than comparing generated RG only.
lookup={(s['id'],int(ix)):i for i,(ti,ix)in enumerate(zip(c['tileids'],c['triangleIndices']))for s in [S[int(ti)]]}
errors=[]
for r in W['records']:
 if r['kind']!='ground':continue
 ix=lookup[r['sourceId'],r['triangleIndex']];t=T[ix];q=t[:,[0,2]];x,z=r['sampleXZ'];v=np.cross(t[1]-t[0],t[2]-t[0]);y=t[0,1]-(v[0]*(x-t[0,0])+v[2]*(z-t[0,2]))/v[1];assert abs(y-r['sourceY'])<1e-8;assert abs(y-r['dtmY'])<=1;errors.append(abs(r['dtmY']-a[r['pixel'][1],r['pixel'][0],0]-a[r['pixel'][1],r['pixel'][0],1]/256))
# Retrace all source intersections along the exact previously recorded failure
# rays. Direction comes from recorded world source hit, never the new screenshot.
j=json.load(open(P/'docs/source-evidence-v4/building-quality/halls-stage-ray-audit.json'));eye=np.array(j['state']);e1=T[:,1]-T[:,0];e2=T[:,2]-T[:,0];q=eye-T[:,0];s=np.cross(q,e1);rayresults=[]
for r in j['rays']:
 if not r['oldSourceVisible']:continue
 d=np.array(r['oldSourceVisible']['position'])-eye;d/=np.linalg.norm(d);p=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,p);safe=np.where(abs(det)>1e-10,det,np.inf);u=np.einsum('ij,ij->i',q,p)/safe;v=s@d/safe;distance=np.einsum('ij,ij->i',e2,s)/safe;ix=np.flatnonzero((abs(det)>1e-10)&(u>=0)&(v>=0)&(u+v<=1)&(distance>0));points=eye+distance[ix,None]*d;visible=~removed(points)|protection(points,N[ix]);near=float(distance[ix[visible]].min())if visible.any()else None;front=near is not None and near<r['newModelDistance']-1e-5;assert not front,(r['pixel'],near,r['newModelDistance']);rayresults.append({'pixel':r['pixel'],'oldWallFailure':r['oldInFrontOfNew'],'sourceIntersections':len(ix),'firstVisibleSourceDistance':near,'newModelDistance':r['newModelDistance'],'oldWallInFrontAfterProtection':front})
# Baseline is an independent topology/LOD, not old triangle indices reused.
baseline=[];sampler=[]
for tile in json.load(open(P/'public/models/preview-manifest.json'))['tiles']:
 b=tile['bounds'];lo,hi=b['min'],b['max'];intersect=hi[0]>=m['boundsXZ']['min'][0]and lo[0]<=m['boundsXZ']['max'][0]and hi[2]>=m['boundsXZ']['min'][1]and lo[2]<=m['boundsXZ']['max'][1]and hi[1]>=1 and lo[1]<=254
 if not intersect:continue
 path=P/'public/models'/tile['url'];assert hashlib.sha256(path.read_bytes()).hexdigest()==tile['sha256'];tt,_=geometry(path,np.array(tile['matrix']).reshape(4,4,order='F'));cc=tt.mean(1);nn=np.cross(tt[:,1]-tt[:,0],tt[:,2]-tt[:,0]);nn/=np.maximum(1e-15,np.linalg.norm(nn,axis=1))[:,None];old=removed(cc);kept=old&protection(cc,nn);baseline.append({'id':tile['id'],'sha256':tile['sha256'],'restoredCentroidTriangles':int(kept.sum()),'formerlyRemovedCentroidTriangles':int(old.sum()),'trueBoundsY':[float(tt[:,:,1].min()),float(tt[:,:,1].max())]});assert tt[:,:,1].min()>3
report={'status':'pass with explicit incomplete coverage','sourceFilesVerified':len(S),'terminalTrianglesRead':len(T),'terminalRestoredCentroidTriangles':int(restored.sum()),'previousDtmCompatibleOutsideEnvelopeCentroids':int(groundgood.sum()),'restoredDtmCompatibleOutsideEnvelopeCentroids':int((groundgood&restored).sum()),'groundWitnessesIndependentlyChecked':len(errors),'maximumGroundEncodingErrorMeters':max(errors),'groundReferenceBytesUnchanged':True,'rawTextureHashVerified':True,'baseline':baseline,'rayRegressions':rayresults,'scope':m,'limits':['Counts classify triangle centroids, not removed triangle areas or screenshot pixels.','Only observed source-preservation bands are restored; all disconnected height ranges and unmatched cells remain explicitly partial.','13 previous failure-ray directions are reconstructed from recorded world hits; the new user screenshot pose is not used or inferred.','No source XYZ/UV, Hall current GLB, or existing replacement-mask pixel changes. Opening/partial/surface priority tested in TypeScript separately.']};args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in ['scope','rayRegressions','baseline']},indent=2))
