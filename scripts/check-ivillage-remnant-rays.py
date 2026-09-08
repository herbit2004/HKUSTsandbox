#!/usr/bin/env python3
"""Replay photographed source rays against the real current-form mask bytes.

This checks world-space occlusion, not a browser or exact screenshot match.
The screenshot and DOM camera were captured sequentially, so user movement can
invalidate the pixel correspondence. Stored source faces remain reproducible.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from hkust_source_geometry import geometry

P=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument('--masks',type=Path,default=P/'public/models/current-forms/ivillage-rebuild')
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--pose',type=Path,default=P/'docs/source-evidence-v4/ivillage-remnants/live-before.json')
ap.add_argument('--pixels',type=json.loads,default=[[400,530],[400,560],[400,590],[400,620],[400,640],[855,525],[855,555],[855,585],[855,615],[660,440],[666,460],[675,470]])
args=ap.parse_args()
pose=json.loads(args.pose.read_text())
source=np.load('/tmp/hkust-ivillage-rebuild-source/terminal-triangles.npz')
T=source['positions'];N=source['normals']
model,_=geometry(P/'public/models/current-forms/ivillage-rebuild/ivillage-x-xiii-v1.glb')
manifest=json.loads((args.masks/'manifest.json').read_text())
masks=[(m['mask'],np.asarray(Image.open(args.masks/m['mask']['url']).convert('RGBA'))) for m in manifest['members']]
pd=manifest['sourceProtection']
protection=np.frombuffer((args.masks/pd['url']).read_bytes(),np.uint8).reshape(pd['height'],pd['width'],4)

def sample(d,pixels,p):
    x,z=p[0],p[2];left,top=d['boundsXZ']['min'];right,bottom=d['boundsXZ']['max']
    if not left<=x<right or not top<=z<bottom:return None
    return pixels[int((z-top)/d['pixelSizeMeters']),int((x-left)/d['pixelSizeMeters'])]

def removed(point,normal):
    p=sample(pd,protection,point)
    if p is not None and p[0] and abs(point[1]-int(p[0])-int(p[1])/256)<=pd['groundBandMeters'] and abs(normal[1])>=.6:return False
    for d,pixels in masks:
        p=sample(d,pixels,point)
        if p is None or p[0]<128:continue
        lower=d['replacementMinY'] if p[3]==255 else max(d['replacementMinY'],int(p[3]))
        if lower<=point[1]<=d['replacementMaxY']:return True
    return False

def hits(triangles,origin,direction):
    edge1=triangles[:,1]-triangles[:,0];edge2=triangles[:,2]-triangles[:,0]
    q=np.cross(np.broadcast_to(direction,edge2.shape),edge2);det=np.einsum('ij,ij->i',edge1,q)
    inv=np.divide(1,det,out=np.zeros_like(det),where=abs(det)>1e-10)
    tvec=origin-triangles[:,0];u=np.einsum('ij,ij->i',tvec,q)*inv;r=np.cross(tvec,edge1)
    v=r@direction*inv;distance=np.einsum('ij,ij->i',edge2,r)*inv
    ids=np.flatnonzero((abs(det)>1e-10)&(u>=0)&(v>=0)&(u+v<=1)&(distance>0))
    return [(int(i),float(distance[i])) for i in ids[np.argsort(distance[ids])]]

origin=np.array(pose['camera']);target=np.array(pose['target']);forward=target-origin;forward/=np.linalg.norm(forward)
right=np.cross(forward,[0,1,0]);right/=np.linalg.norm(right);up=np.cross(right,forward)
cx,cy=pose['viewport']['targetPixel'];scale=2*np.tan(np.deg2rad(42/2))/pose['viewport']['height']
reports=[]
for x,y in args.pixels:
    direction=forward+right*((x-cx)*scale)+up*((cy-y)*scale);direction/=np.linalg.norm(direction)
    modelhits=hits(model,origin,direction);front=modelhits[0][1] if modelhits else float('inf')
    checked=[]
    for i,distance in hits(T,origin,direction):
        if distance>=front:break
        point=origin+direction*distance
        checked.append({'stagedTriangleIndex':i,'sourceTileIndex':int(source['sourceTileIndex'][i]),'triangleIndex':int(source['triangleIndex'][i]),'point':point.tolist(),'normal':N[i].tolist(),'distance':distance,'removed':removed(point,N[i])})
    reports.append({'pixel':[x,y],'modelDistance':None if not np.isfinite(front) else front,'sourceBeforeModel':checked,'remainingSourceBeforeModel':sum(not v['removed'] for v in checked)})
result={'masks':str(args.masks),'pose':pose,'rays':reports,'limitations':['Source terminal geometry rays, not proof of the actually loaded LOD at screenshot time.','Sequential camera and screenshot reads may differ if user moves; no screenshot identity assumed.','Other scene masks are not evaluated; original ground-reference is outside these tall-wall witnesses.']}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps([{'pixel':r['pixel'],'hits':len(r['sourceBeforeModel']),'remaining':r['remainingSourceBeforeModel']}for r in reports],indent=2))
