from pathlib import Path
import sys,json,hashlib,shutil
import numpy as np
from PIL import Image
from shapely import polygons,points,STRtree
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'));from hkust_source_geometry import geometry,Heights
src=P/'public/surfaces/ground-reference';out=Path('/tmp/hkust-v5-ground-protection/ground-reference-fine-extension');out.mkdir(exist_ok=True)
for f in src.iterdir():
 if f.is_file():shutil.copy2(f,out/f.name)
m=json.load(open(src/'manifest-before-fine-extension.json'));old=np.asarray(Image.open(src/'ground-reference-before-fine-extension.png').convert('RGB'));a=old.copy();h,w=a.shape[:2];step=(m['maxX']-m['minX'])/w
# Bounded diagnosis window only; every accepted texel also needs actual fine
# near-ground triangle projection, core overlap and source slope/height evidence.
xx=m['minX']+(np.arange(w)+.5)*step;zz=m['minZ']+(np.arange(h)+.5)*step;cols=np.flatnonzero((xx>=340)&(xx<=378));rows=np.flatnonzero((zz>=-1605)&(zz<=-1585));rr,cc=np.meshgrid(rows,cols,indexing='ij');rr=rr.ravel();cc=cc.ravel();xz=np.column_stack([xx[cc],zz[rr]]);ys=Heights(sorted((P/'public/terrain/source-data').glob('*.tif')))(np.column_stack([xz[:,0]+844800,820500-xz[:,1]]))
bu=next(b for b in json.load(open(P/'public/models/exteriors/manifest.json'))['bundles']if b['id']=='campus-01');am=np.asarray(Image.open(P/'public/models/exteriors'/bu['mask']['url']).convert('RGB'));ab=bu['mask']['boundsXZ'];ac=np.clip(((xz[:,0]-ab['min'][0])/(ab['max'][0]-ab['min'][0])*am.shape[1]).astype(int),0,am.shape[1]-1);ar=np.clip(((xz[:,1]-ab['min'][1])/(ab['max'][1]-ab['min'][1])*am.shape[0]).astype(int),0,am.shape[0]-1);eligible=(old[rr,cc,0]==0)&(am[ar,ac,1]>127)&np.isfinite(ys)
best=np.full(len(xz),np.inf);chosen=[None]*len(xz);records=[];sources=[]
for patch in json.load(open(P/'public/models/hires/manifest.json'))['patches']:
 if patch['id'] not in ['12-NW-6C-1-partial-entrance','12-NW-6C-2']:continue
 for t in patch['levels']['fine']['tiles']:
  b=t['bounds']
  if b['max'][0]<340 or b['min'][0]>378 or b['max'][2]<-1605 or b['min'][2]>-1585:continue
  path=P/'public/models/hires'/t['url'];tri,_=geometry(path,np.asarray(t['matrix']).reshape(4,4,order='F'));norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);ny=abs(norm[:,1])/np.maximum(np.linalg.norm(norm,axis=1),1e-12);ids=np.flatnonzero(ny>=.85);tt=tri[ids];project=tt[:,:,[0,2]];ps=polygons(project);valid=ids[np.array([p.area>1e-8 for p in ps])];tt=tri[valid];project=tt[:,:,[0,2]];pairs=STRtree(polygons(project)).query(points(xz),predicate='intersects');used=False
  for pointindex,face in pairs.T:
   if not eligible[pointindex]:continue
   tr=tt[face];q=project[face];u,v=np.linalg.solve(np.column_stack([q[1]-q[0],q[2]-q[0]]),xz[pointindex]-q[0]);y=tr[0,1]*(1-u-v)+tr[1,1]*u+tr[2,1]*v;delta=abs(y-ys[pointindex])
   if delta>2 or delta>=best[pointindex]:continue
   best[pointindex]=delta;chosen[pointindex]={'tileId':t['id'],'url':t['url'],'triangle':int(valid[face]),'sourceY':float(y),'dtmY':float(ys[pointindex]),'normalY':float(ny[valid[face]]),'planeVertices':tr.tolist()};used=True
  if used:sources.append({'id':t['id'],'url':t['url'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'terminalLeaf':t.get('terminalLeaf'),'originalGeometricError':t.get('originalGeometricError',t.get('originalError'))})
mask=np.zeros((h,w),dtype=np.uint8)
for i,c in enumerate(chosen):
 if c is None:continue
 y=c['sourceY'];encoded=int(round(y*256));a[rr[i],cc[i]]=[255,encoded//256,encoded%256];mask[rr[i],cc[i]]=255;records.append({'pixel':[int(cc[i]),int(rr[i])],'worldXZ':xz[i].tolist(),**c})
Image.fromarray(a).save(out/m['url']);Image.fromarray(mask).save(out/'fine-source-extension.png')
assert np.array_equal(a[old[:,:,0]>127],old[old[:,:,0]>127])
# New source reference is exact from the contributing original plane; old DTM
# reference pixels stay byte-identical. No source position or surface changed.
qa={'newPixels':len(records),'newAreaSquareMeters':len(records)*step*step,'existingProtectedPixelsByteIdentical':True,'sourceHeightVsDTMAbsRange':[float(min(best[np.isfinite(best)])),float(max(best[np.isfinite(best)]))],'maxHeightEncodingError':max(abs(a[r['pixel'][1],r['pixel'][0],1]+a[r['pixel'][1],r['pixel'][0],2]/256-r['sourceY'])for r in records),'sourceFiles':sources,'records':records,'limits':'Only actual error0 fine triangle projection within the diagnosed arc-front window, original core G, old unprotected pixels, abs(normalY)>=.85 and <=2m from original DTM. No rectangle coverage, no geometry/texturing changes. Existing RGB unchanged at all previously protected pixels.'}
(out/'fine-source-extension-qa.json').write_text(json.dumps(qa,indent=2)+'\n');m['fineSourceExtension']={k:v for k,v in qa.items()if k!='records'};m['heightReference']='G/B encode original DTM for prior pixels; diagnosed extension pixels encode original fine photographic ground-plane Y. 1m rendering band unchanged; extension mask/provenance separately saved.';m['sha256']=hashlib.sha256((out/m['url']).read_bytes()).hexdigest();m['bytes']=(out/m['url']).stat().st_size;(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in qa.items()if k not in ['records','sourceFiles']},indent=2))
