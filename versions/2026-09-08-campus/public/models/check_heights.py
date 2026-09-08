import sys,json,pathlib,struct
sys.path.insert(0,'/tmp/hkust-geometry-deps')
import pyproj,numpy as np
from PIL import Image
R=pathlib.Path('/tmp/hkust-geodata')
ec2geo=pyproj.Transformer.from_crs(4978,4979,always_xy=True)
geo2hk=pyproj.Transformer.from_crs(4326,2326,always_xy=True)
geo2ec=pyproj.Transformer.from_crs(4979,4978,always_xy=True)
print('OPERATION',geo2hk.description)
rasters=[]
for p in (R/'dtm').glob('*.tif'):
 im=Image.open(p);rasters.append((np.array(im),im.tag_v2[33922][3],im.tag_v2[33922][4],p.name))
print('RASTERS',[(r[1],r[2],r[3]) for r in rasters])
out=[];pts=[]
for p in R.rglob('*.b3dm'):
 sub=json.load(open(p.parent/'tileset.json'))['root'];M=np.array(sub['transform']).reshape(4,4).T
 b=p.read_bytes();hh=struct.unpack_from('<4s6I',b);o=28+sum(hh[3:]);l=struct.unpack_from('<I',b,o+12)[0];d=json.loads(b[o+20:o+20+l]);bo=o+20+l+8
 seen=set()
 for m in d['meshes']:
  for pr in m['primitives']:
   ai=pr['attributes']['POSITION']
   if ai in seen:continue
   seen.add(ai);a=d['accessors'][ai];v=d['bufferViews'][a['bufferView']];xyz=np.frombuffer(b,dtype='<f4',count=a['count']*3,offset=bo+v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,3)[::10].astype(float)
   ecef=xyz@M[:3,:3].T+M[:3,3];lon,lat,h=ec2geo.transform(*ecef.T);e,n=geo2hk.transform(lon,lat);e=np.array(e);n=np.array(n);h=np.array(h)
   for ar,x0,y0,name in rasters:
    cc=np.floor((e-x0)/.5).astype(int);rr=np.floor((y0-n)/.5).astype(int);ok=(cc>=0)&(cc<ar.shape[1])&(rr>=0)&(rr<ar.shape[0]);valid=np.where(ok)[0];tv=ar[rr[ok],cc[ok]];good=tv>-100
    if np.any(good):
     ii=valid[good];out.extend(np.stack([e[ii],n[ii],h[ii],tv[good]],axis=1).tolist())
 if len(out)>300000:break
arr=np.array(out);print('SAMPLES',arr.shape);np.save('/tmp/hkust-model-assets/height-samples.npy',arr)
delta=arr[:,2]-arr[:,3];print('RAW ELLIP-HKPD',np.percentile(delta,[0,1,5,10,20,30,50,80,95,99,100]))
low=arr[(arr[:,3]<3)&(arr[:,3]>0)];print('LOWGROUND',len(low),np.percentile(low[:,2]-low[:,3],[1,5,10,20,30,50,80,95,99]))
print('origin',geo2hk.transform(114.261638616,22.338847842))
print('ops',geo2hk.get_last_used_operation())
