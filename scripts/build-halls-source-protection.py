"""Bounded preservation of existing source triangles; never edits mesh geometry."""
import json,sys,hashlib,math,argparse
from pathlib import Path
import numpy as np
from PIL import Image
import shapely
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--cache',type=Path,default=Path('/tmp/hkust-hall-source-protection-cache'))
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();P=args.project.resolve();O=args.cache;O.mkdir(parents=True,exist_ok=True);out=args.output;out.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(P/'scripts'))
from hkust_source_geometry import Heights,geometry
cachepath=O/'source-analysis.npz';sourcepath=O/'source-tiles.json'
if not cachepath.exists() or not sourcepath.exists():
 ts=[];sis=[];indices=[];sources=[]
 patch=json.load(open(P/'public/models/hires/partial-residential-ias/manifest.json'))['patches'][0]
 for tile in patch['levels']['high']['tiles']:
  lo=tile['bounds']['min'];hi=tile['bounds']['max']
  if hi[0]<650 or lo[0]>790 or hi[2]<-1165 or lo[2]>-1010:continue
  path=P/'public/models/hires'/tile['url'];assert hashlib.sha256(path.read_bytes()).hexdigest()==tile['sha256'];t,_=geometry(path,np.array(tile['matrix']).reshape(4,4,order='F'));ts.append(t);sis.extend([len(sources)]*len(t));indices.extend(range(len(t)));sources.append(tile)
 T=np.concatenate(ts);N=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]);N/=np.maximum(1e-20,np.linalg.norm(N,axis=1))[:,None];np.savez_compressed(cachepath,triangles=T,normal=N,centroids=T.mean(1),tileids=np.array(sis),triangleIndices=np.array(indices));sourcepath.write_text(json.dumps(sources))
cache=np.load(cachepath);T=cache['triangles'];N=cache['normal'];C=cache['centroids'];sources=json.load(open(sourcepath));tileids=cache['tileids'];tix=cache['triangleIndices']
for source in sources:assert hashlib.sha256((P/'public/models/hires'/source['url']).read_bytes()).hexdigest()==source['sha256'], 'Stale source cache; remove cache and rebuild'
D=json.load(open(P/'public/models/current-forms/halls-current/manifest.json'));fp=next(f for f in json.load(open(P/'public/data/building-footprints.json'))['footprints']if f['catalogId']=='ug-hall-10');ug=unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in fp['parts']]);env=unary_union([Polygon(p['rings'][0],p['rings'][1:])for b in D['buildings']for p in b['envelopeParts']])
step=.5;minx=min(b['mask']['boundsXZ']['min'][0]for b in D['buildings']);minz=min(b['mask']['boundsXZ']['min'][1]for b in D['buildings']);maxx=max(b['mask']['boundsXZ']['max'][0]for b in D['buildings']);maxz=max(b['mask']['boundsXZ']['max'][1]for b in D['buildings']);w=round((maxx-minx)/step);h=round((maxz-minz)/step);occupied=np.zeros((h,w),bool)
for b in D['buildings']:
 m=b['mask'];a=np.asarray(Image.open(P/'public/models/current-forms/halls-current'/m['url']).convert('RGBA'));x=round((m['boundsXZ']['min'][0]-minx)/step);z=round((m['boundsXZ']['min'][1]-minz)/step);occupied[z:z+m['height'],x:x+m['width']]|=a[:,:,0]>127
rows,cols=np.nonzero(occupied);XZ=np.column_stack([minx+(cols+.5)*step,minz+(rows+.5)*step]);dtm=Heights(sorted((P/'public/terrain/source-data').glob('*.tif')))(np.column_stack([XZ[:,0]+844800,820500-XZ[:,1]]));eligible=~shapely.contains_xy(env,XZ[:,0],XZ[:,1]);best=np.full(len(XZ),np.inf);selected=np.full(len(XZ),-1);sourceY=np.zeros(len(XZ));ny=abs(N[:,1]);candidate=np.flatnonzero((ny>=.6)&(T[:,:,1].min(1)<=180)&(T[:,:,1].max(1)>=132));project=T[candidate][:,:,[0,2]];polys=shapely.polygons(project);valid=np.asarray(shapely.area(polys))>1e-8;candidate=candidate[valid];polys=polys[valid];pairs=shapely.STRtree(polys).query(shapely.points(XZ),predicate='intersects')
print('ground intersections',pairs.shape,flush=True)
for j,k in pairs.T:
 if not eligible[j]:continue
 ix=candidate[k];t=T[ix];q=t[:,[0,2]];u,v=np.linalg.solve(np.column_stack([q[1]-q[0],q[2]-q[0]]),XZ[j]-q[0]);y=t[0,1]+u*(t[1,1]-t[0,1])+v*(t[2,1]-t[0,1]);delta=abs(y-dtm[j])
 if delta<=1 and delta<best[j]:best[j]=delta;selected[j]=ix;sourceY[j]=y
# RG independent 16-bit ground height. BA encode ONE true connected source
# structure interval. A stays nonzero for occupied texels to avoid Canvas
# premultiplication loss. For ground-only pixels A=255 and B=255 sentinel.
a=np.zeros((h,w,4),np.uint8);a[:,:,3]=255;records=[]
def witness(ix):
 s=sources[int(tileids[ix])];return {'sourceId':s['id'],'sourceUrl':s['url'],'sha256':s['sha256'],'triangleIndex':int(tix[ix]),'triangle':T[ix].tolist()}
for j in np.flatnonzero(selected>=0):
 ix=selected[j];enc=round(dtm[j]*256);a[rows[j],cols[j]]=[enc//256,enc%256,255,255];records.append({'pixel':[int(cols[j]),int(rows[j])],'kind':'ground','sampleXZ':XZ[j].tolist(),'sourceY':float(sourceY[j]),'dtmY':float(dtm[j]),'normalAbsY':float(ny[ix]),**witness(ix)})
# Edge cells retain actual source support; an exact source multipolygon test
# in both CPU and GLSL prevents preservation outside the original drawing.
ugCells={}
for j in range(len(XZ)):
 x,z=XZ[j];cell=box(x-.25,z-.25,x+.25,z+.25)
 if ug.intersects(cell):ugCells[(int(rows[j]),int(cols[j]))]=[]
def clip(t,axis,value,sign):
 result=[]
 for i,v in enumerate(t):
  p=t[i-1];a=sign*(p[axis]-value);b=sign*(v[axis]-value)
  if (a>=-1e-8)!=(b>=-1e-8):result.append(p+(v-p)*a/(a-b))
  if b>=-1e-8:result.append(v)
 return np.array(result)
mins=T.min(1);maxs=T.max(1);bounds=ug.bounds;ids=np.flatnonzero((maxs[:,0]>=bounds[0])&(mins[:,0]<=bounds[2])&(maxs[:,2]>=bounds[1])&(mins[:,2]<=bounds[3])&(maxs[:,1]>=133.75)&(mins[:,1]<=167.3))
print('UGX candidates',len(ids),'intersecting cells',len(ugCells),flush=True)
for ix in ids:
 if not ug.covers(shapely.Point(C[ix,0],C[ix,2])):continue
 left=max(0,math.floor((mins[ix,0]-minx)/step));right=min(w-1,math.floor((maxs[ix,0]-minx)/step));top=max(0,math.floor((mins[ix,2]-minz)/step));bottom=min(h-1,math.floor((maxs[ix,2]-minz)/step))
 for row in range(top,bottom+1):
  for col in range(left,right+1):
   if (row,col)not in ugCells:continue
   tt=T[ix];x=minx+col*step;z=minz+row*step
   for axis,val,sign in [(0,x,1),(0,x+step,-1),(2,z,1),(2,z+step,-1)]:
    tt=clip(tt,axis,val,sign)
    if len(tt)<2:break
   if len(tt)>=2:ugCells[row,col].append((float(tt[:,1].min()),float(tt[:,1].max()),int(ix)))
ambiguous=[];structure=0;overlap=0
for (row,col),intervals in ugCells.items():
 intervals.sort();merged=[]
 for lo,hi,ix in intervals:
  if merged and lo<=merged[-1][1]+.02:merged[-1][1]=max(merged[-1][1],hi);merged[-1][2].append(ix)
  else:merged.append([lo,hi,[ix]])
 if not merged:continue
 # Preserve only one connected interval; never join empty vertical gaps.
 # Widest actual continuous interval is explicit partial preservation.
 chosen=max(merged,key=lambda r:r[1]-r[0]);lo,hi,faces=chosen
 if len(merged)>1:ambiguous.append({'pixel':[col,row],'intervals':[[l,h]for l,h,_ in merged],'selected':[lo,hi]})
 if not(0<lo<=hi<254):continue
 a[row,col,2:]=[math.floor(lo),math.ceil(hi)];structure+=1;overlap+=int(a[row,col,0]>0)
 records.append({'pixel':[col,row],'kind':'structure','interval':[lo,hi],'encoded':[math.floor(lo),math.ceil(hi)],'sourceTriangles':[{'sourceId':sources[int(tileids[ix])]['id'],'triangleIndex':int(tix[ix])}for ix in sorted(set(faces))]})
Image.fromarray(a).save(out/'source-protection.png');raw=a.tobytes();(out/'source-protection.rgba').write_bytes(raw);groundOld=P/'public/surfaces/ground-reference/ground-reference.png'
clipped=ug.intersection(box(minx,minz,maxx,maxz));polygons=list(clipped.geoms)if hasattr(clipped,'geoms')else[clipped];parts=[{'rings':[[list(pt)for pt in poly.exterior.coords]]+[[list(pt)for pt in ring.coords]for ring in poly.interiors]}for poly in polygons if poly.area>0]
m={'structureParts':parts,'structureDomainStats':{'parts':len(parts),'rings':sum(len(p['rings'])for p in parts),'holes':sum(len(p['rings'])-1 for p in parts),'verticesIncludingRingClosures':sum(len(r)for p in parts for r in p['rings']),'sourceBuildingId':fp['officialBuildingId'],'sourceCatalogId':'ug-hall-10','operation':'Exact source multipolygon union intersected with current Hall mask bounds; no buffer, hull or simplification','boundaryToleranceMeters':.0001},'url':'source-protection.rgba','previewUrl':'source-protection.png','width':w,'height':h,'boundsXZ':{'min':[minx,minz],'max':[maxx,maxz]},'pixelSizeMeters':step,'encoding':'rg-ground-uint16-256-ba-structure-int-255-absent','groundBandMeters':1,'minimumAbsoluteGroundNormalY':.6,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'baseTextureBytes':a.nbytes,'groundPixels':int((selected>=0).sum()),'structurePixels':structure,'independentOverlapPixels':overlap,'multiIntervalPixels':len(ambiguous),'scope':'Only bypass currentForms deletion, preserving the already-rendered original triangle and UV. Opening/partial/exterior/surface rules keep precedence.','source':'Actual terminal source triangles and original per-tile verified transforms; official UG X public floor drawing; CEDD 0.5m DTM used only as a compatibility test, never rendered as replacement geometry.','unchangedGroundReferenceSHA256':hashlib.sha256(groundOld.read_bytes()).hexdigest(),'limits':['Ground requires real source intersection outside current form envelopes with abs(normalY)>=0.6 and source height within 1m of DTM. Unmatched areas remain unprotected.','UG X protection requires a projected original source triangle height interval AND an exact fragment-level source multipolygon test, with holes and boundary included. The 2D drawing alone does not invent a structure or height.','At cells with disjoint structure intervals only the widest real connected interval is encoded; other intervals stay subject to deletion. Ground has independent channels and is never overwritten or joined to the structure interval.','Structure bounds round outward to integer meters; this explicit raster tolerance is not measured ownership or building height.','This does not alter or resolve the 17.31m2 plan overlap of the approximate Hall XI envelope and UG X drawing.','No screenshot camera inferred; structural and source checks do not replace real WebGL visual acceptance.']}
m['sourceEvidence']={'buildingFootprints':{'asset':'/data/building-footprints.json','sha256':hashlib.sha256((P/'public/data/building-footprints.json').read_bytes()).hexdigest(),'catalogId':'ug-hall-10'},'terminalDescriptor':{'asset':'/models/hires/partial-residential-ias/manifest.json','sha256':hashlib.sha256((P/'public/models/hires/partial-residential-ias/manifest.json').read_bytes()).hexdigest()},'sourceTrianglesAndTransforms':'docs/source-evidence-v4/building-quality/hall-source-protection/source-protection-witnesses.json','dtm':[{'asset':'/terrain/source-data/'+p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in sorted((P/'public/terrain/source-data').glob('*.tif'))]}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(out/'witnesses.json').write_text(json.dumps({'sources':sources,'records':records,'disjointIntervals':ambiguous},separators=(',',':'))+'\n');print(json.dumps(m,indent=2))
