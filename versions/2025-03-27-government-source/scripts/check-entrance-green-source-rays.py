import sys,json
from pathlib import Path
import numpy as np
from PIL import Image
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'))
from hkust_source_geometry import geometry,Heights
cam=np.array([429.712,216.457,-1435.886]);tar=np.array([336.4,123.145,-1549.934]);fw=tar-cam;fw/=np.linalg.norm(fw);rt=np.cross(fw,[0,1,0]);rt/=np.linalg.norm(rt);up=np.cross(rt,fw)
pixels=[(1153,390),(1170,395),(1192,406),(1210,419),(1240,438),(1260,447),(1230,433),(1160,415),(1125,396),(1180,405),(1210,430),(1250,453)]
dirs=[]
for x,y in pixels:
 d=fw+rt*((x-310)/1290*2-1)*np.tan(np.radians(21))*1290/837.998+up*(1-(y-61.992)/837.998*2)*np.tan(np.radians(21));dirs.append(d/np.linalg.norm(d))
read=lambda p:json.loads(p.read_text());hm=Heights(sorted((P/'public/terrain/source-data').glob('*.tif')))
bundle=next(b for b in read(P/'public/models/exteriors/manifest.json')['bundles'] if b['id']=='campus-01');maskdir=P/'public/models/exteriors';b=bundle['mask']['boundsXZ'];am=(np.asarray(Image.open(maskdir/bundle['mask']['url']).convert('RGB')),[*b['min'],*b['max']])
gm=read(P/'public/surfaces/ground-reference/manifest.json');gr=(np.asarray(Image.open(P/'public/surfaces/ground-reference'/gm['url']).convert('RGB')),[gm[k] for k in ['minX','minZ','maxX','maxZ']])
em=read(P/'public/surfaces/entrance/manifest.json');s=em['mask'];sm=(np.asarray(Image.open(P/'public/surfaces/entrance'/s['url']).convert('RGB')),[s[k] for k in ['minX','minZ','maxX','maxZ']]);clearance=s['discardHeightClearanceMeters']
pm=[];patches=read(P/'public/models/hires/manifest.json')['patches'];wanted={'12-NW-6C-1-partial-entrance','12-NW-6C-7-partial-entrance','12-NW-6C-6','12-NW-6C-2'}
for p in patches:
 if p['id']not in wanted:continue
 m=p['levels']['fine'].get('mask',p.get('mask'))
 if m:pm.append((np.asarray(Image.open(P/'public/models/hires'/m['url']).convert('RGB')),[m[k] for k in ['minX','minZ','maxX','maxZ']]))
def sample(mask,p):
 a,b=mask; x,z=p[0],p[2]
 if x<b[0] or x>b[2] or z<b[1] or z>b[3]:return [0,0,0]
 r=min(a.shape[0]-1,int((z-b[1])/(b[3]-b[1])*a.shape[0]));c=min(a.shape[1]-1,int((x-b[0])/(b[2]-b[0])*a.shape[1]));return a[r,c].tolist()
def info(p,ny,role):
 a,g,s=sample(am,p),sample(gr,p),sample(sm,p);part=any(sample(m,p)[0]>127 for m in pm);ground=g[0]>127 and abs(p[1]-g[1]-g[2]/256)<=gm['bandMeters']and ny>=.6
 reasons=[]
 if role=='terrain' and g[0]>127:reasons.append('photography coverage with source ground reference')
 if role in ['baseline','photogrammetry'] and a[0 if role=='baseline'else 1]>127 and p[1]>=bundle['mask']['heightMin']-.15 and not ground: reasons.append('building R'if role=='baseline'else'building G')
 if role in ['baseline','supplement'] and part:reasons.append('partial projection')
 if role in ['baseline','photogrammetry','supplement','exterior','terrain']and ny>=.6 and s[0]>127 and p[1]<=s[1]+s[2]/256+clearance:reasons.append('surface2 height')
 return {'academicRG':a[:2],'groundReferenceRGB':g,'surfaceRGB':s,'partial':part,'groundProtected':ground,'discardReasons':reasons}
objs=[]
for ob in bundle['objects']:
 M=np.eye(4)
 if'matrix'in ob:M=np.asarray(ob['matrix']).reshape(4,4,order='F')
 if'offset'in ob:M[:3,3]+=ob['offset']
 objs.append((ob['id'],P/'public/models/exteriors'/ob['url'],M,'supplement'if ob.get('objectRole')=='source-photogrammetry-gap-surface'else'exterior'))
for patch in patches:
 if patch['id']not in wanted:continue
 for t in patch['levels']['fine']['tiles']:objs.append((t['id'],P/'public/models/hires'/t['url'],np.asarray(t['matrix']).reshape(4,4,order='F'),'photogrammetry'))
for t in read(P/'public/models/preview-manifest.json')['tiles']:
 b=t['bounds']
 if b['max'][0]<200 or b['min'][0]>550 or b['max'][2]<-1750 or b['min'][2]>-1200:continue
 # complete loaded whole patches remove their baselineIds before render.
 hidden=any(t['id'] in patch.get('baselineIds',[]) for patch in patches if patch['id']in wanted and not patch.get('mask'))
 if not hidden:objs.append((t['id'],P/'public/models'/t['url'],np.asarray(t['matrix']).reshape(4,4,order='F'),'baseline'))
objs.extend([('entrance-ground',P/'public/surfaces/entrance'/em['url'],np.eye(4),'new-surface'),('terrain5m',P/'public/terrain/terrain.glb',np.eye(4),'terrain')])
hits=[[]for _ in pixels]
for name,path,M,role in objs:
 tri,mats=geometry(path,M);e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];v=cam-tri[:,0];normal=np.cross(e1,e2);ny=abs(normal[:,1])/np.maximum(np.linalg.norm(normal,axis=1),1e-12)
 for j,d in enumerate(dirs):
  h=np.cross(np.broadcast_to(d,e2.shape),e2);a=np.einsum('ij,ij->i',e1,h);valid=abs(a)>1e-8;f=np.zeros(len(a));f[valid]=1/a[valid];u=f*np.einsum('ij,ij->i',v,h);q=np.cross(v,e1);w=f*(q@d);tt=f*np.einsum('ij,ij->i',e2,q);ix=np.flatnonzero(valid&(u>=0)&(w>=0)&(u+w<=1)&(tt>0))
  for k in ix[np.argsort(tt[ix])][:6]:
   p=cam+d*tt[k];ii=info(p,float(ny[k]),role);hits[j].append({'object':name,'role':role,'distance':float(tt[k]),'position':p.tolist(),'triangle':int(k),'material':int(mats[k]),'normalY':float(ny[k]),'dtmY':float(hm(np.array([[p[0]+844800,820500-p[2]]]))[0]),**ii})
records=[{'screen':pixels[j],'hits':sorted(hits[j],key=lambda h:h['distance'])[:16]} for j in range(len(pixels))]
out={'camera':cam.tolist(),'target':tar.tolist(),'canvas':{'left':310,'top':61.992,'width':1290,'height':837.998},'rays':records,'note':'Current fine-extended ground reference and slope-limited surface2 predicate. Terrain photography coverage is inferred only at diagnosis points: core R plus groundReference R retains photography and suppresses DTM. Actual source ray order is recorded; not a browser render.'}
(P/'docs/source-evidence-v4/entrance-terminal-green-rays.json').write_text(json.dumps(out,indent=2,default=lambda x:x.item())+'\n')
for r in records:
 print(r['screen']);print('\n'.join(str((x['object'],x['role'],round(x['distance'],3),np.round(x['position'],3).tolist(),round(x['normalY'],3),x['discardReasons'],x['academicRG'],x['surfaceRGB']))for x in r['hits'][:6]))
