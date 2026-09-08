import sys,json,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import polygons,points,STRtree
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'));from hkust_source_geometry import geometry
out=Path('/tmp/hkust-v5-ground-protection/ground-reference-fine-extension');q=json.load(open(out/'fine-source-extension-qa.json'));records=q['records'];xz=np.asarray([r['worldXZ']for r in records]);reference=np.asarray([r['sourceY']for r in records]);matched=[None]*len(records);max_plane_error=0
for r in records:
 t=np.asarray(r['planeVertices']);x,z=r['worldXZ'];a,b,c=np.cross(t[1]-t[0],t[2]-t[0]);d=-np.dot([a,b,c],t[0]);y=-(a*x+c*z+d)/b;max_plane_error=max(max_plane_error,abs(y-r['sourceY']))
for t in json.load(open(P/'public/models/preview-manifest.json'))['tiles']:
 b=t['bounds']
 if b['max'][0]<340 or b['min'][0]>378 or b['max'][2]<-1605 or b['min'][2]>-1585:continue
 tri,_=geometry(P/'public/models'/t['url'],np.asarray(t['matrix']).reshape(4,4,order='F'));norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);ny=abs(norm[:,1])/np.maximum(np.linalg.norm(norm,axis=1),1e-12);ids=np.flatnonzero(ny>=.6);tt=tri[ids];pairs=STRtree(polygons(tt[:,:,[0,2]])).query(points(xz),predicate='intersects')
 for i,j in pairs.T:
  a,b,c=norm[ids[j]];d=-np.dot(norm[ids[j]],tt[j,0]);y=-(a*xz[i,0]+c*xz[i,1]+d)/b
  if abs(y-reference[i])<=1:matched[i]={'baselineId':t['id'],'triangle':int(ids[j]),'sourceY':float(y),'sourceReferenceDelta':float(y-reference[i])}
print('baseline compatible',sum(x is not None for x in matched),'/',len(records),'plane err',max_plane_error)
orig=np.asarray(Image.open(P/'public/surfaces/ground-reference/ground-reference-before-fine-extension.png').convert('RGB'));new=np.asarray(Image.open(out/'ground-reference.png').convert('RGB')).copy();mask=np.asarray(Image.open(out/'fine-source-extension.png')).copy();retained=[]
for r,match in zip(records,matched):
 x,z=r['pixel']
 if match is None:new[z,x]=orig[z,x];mask[z,x]=0
 else:retained.append({**r,'baselineFallback':match})
Image.fromarray(new).save(out/'ground-reference.png');Image.fromarray(mask).save(out/'fine-source-extension.png');q.update(records=retained,newPixels=len(retained),newAreaSquareMeters=len(retained)*.25,removedUnmatchedBaselinePixels=len(records)-len(retained),independentSourcePlaneEquationMaxError=max_plane_error,allExtensionPixelsHaveCompatibleOriginalBaseline=True);(out/'fine-source-extension-qa.json').write_text(json.dumps(q,indent=2)+'\n');m=json.load(open(out/'manifest.json'));m['fineSourceExtension']={k:v for k,v in q.items()if k!='records'};m['sha256']=hashlib.sha256((out/'ground-reference.png').read_bytes()).hexdigest();m['bytes']=(out/'ground-reference.png').stat().st_size;(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
for point in [[352.7809365099614,122.42785702111657,-1597.5110350007374],[351.6299172660472,121.02102149658919,-1599.9292197644024]]:
 col=int((point[0]-m['minX'])/.5);row=int((point[2]-m['minZ'])/.5);print('diagnostic point',point,'newRGB',new[row,col].tolist(),'newrefdelta',point[1]-new[row,col,1]-new[row,col,2]/256)
