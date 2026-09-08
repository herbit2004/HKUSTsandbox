#!/usr/bin/env python3
"""Independent bounded source-support pixel/height and actual PV geometry checks."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
from shapely.strtree import STRtree
from hkust_source_geometry import geometry

ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path('.'));args=ap.parse_args();P=args.project.resolve();O=P/'public/models/current-forms/halls-current'
D=json.load(open(O/'manifest.json'));evidence=json.load(open(O/'evidence/replacement-support-audit.json'));sources={}
for source in evidence['verifiedSources']:
 path=P/'public/models/hires'/source['url'];assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'];sources[source['id']]=geometry(path,np.array(source['matrix']).reshape(4,4,order='F'))[0]
reports=[]
for b in D['buildings']:
 m=b['mask'];assert m['pixelMinYEncoding']=='int-meters-alpha-255-common';im=np.asarray(Image.open(O/m['url']).convert('RGBA'));assert im.shape==(m['height'],m['width'],4);assert hashlib.sha256((O/m['url']).read_bytes()).hexdigest()==m['sha256'];assert np.all((im[:,:,0]==0)|(im[:,:,0]==255));assert np.all(im[im[:,:,0]>0,3]>0)
 env=unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in b['envelopeParts']]);polys=[];lows=[]
 selections=json.load(open(O/m['sourceSupport']['sourceTriangleIndexAsset']))
 for group in selections:
  for t in sources[group['sourceId']][group['indices']]:
   verts=list(t)
   for y,sign in [(m['replacementMinY'],1),(m['replacementMaxY'],-1)]:
    clipped=[]
    for a,c in zip(verts,verts[1:]+verts[:1]):
     inside_a=sign*(a[1]-y)>=0;inside_c=sign*(c[1]-y)>=0
     if inside_a:clipped.append(a)
     if inside_a!=inside_c:clipped.append(a+(c-a)*(y-a[1])/(c[1]-a[1]))
    verts=clipped
   if len(verts)<3:continue
   q=np.array(verts);p=Polygon(q[:,[0,2]])
   p=p.convex_hull.buffer(.251)if p.area<1e-9 else p.buffer(.251,join_style=2)
   polys.append(p);lows.append(math.floor(q[:,1].min()))
 tree=STRtree(polys);rng=np.random.default_rng(417);samples=[]
 for condition in [(im[:,:,0]>0)&(im[:,:,3]<255),im[:,:,3]==255,im[:,:,0]==0]:
  points=np.argwhere(condition);ids=rng.choice(len(points),min(1024,len(points)),replace=False);samples.extend(points[ids])
 errors=[]
 for z,x in samples:
  x0=m['boundsXZ']['min'][0]+x*.5;z0=m['boundsXZ']['min'][1]+z*.5;cell=box(x0+1e-8,z0+1e-8,x0+.5-1e-8,z0+.5-1e-8)
  actual=im[z,x];core=env.intersects(cell);ids=tree.query(cell,predicate='intersects');expected=255 if core else min((lows[i]for i in ids),default=0)
  if int(actual[3])!=expected:errors.append({'x':int(x),'z':int(z),'actual':int(actual[3]),'expected':expected})
 assert not errors,(b['catalogId'],errors[:8])
 # Actual GLB photovoltaics must clear their assigned regularized roof; record
 # vertex proof separately from approximate source observation heights.
 tri,material=geometry(O/b['url']);pv=tri[material==4];clear=[]
 for p in pv.reshape(-1,3):
  fit=min(b['roofFits'],key=lambda f:unary_union([Polygon(q['rings'][0],q['rings'][1:])for q in f['domain']]).distance(Point(p[0],p[2])))
  roof=(p[[0,2]]-fit['origin'])@np.array(fit['coefficients'][:2])+fit['coefficients'][2];clear.append(float(p[1]-roof))
 assert min(clear)>.139,(b['catalogId'],min(clear))
 raychecks=m['checks']['cameraRays'];assert all(r['discardAfter']for r in raychecks if r['previousOldInFront'])
 reports.append({'catalogId':b['catalogId'],'independentPixelHeightSamples':len(samples),'pixelHeightMismatches':len(errors),'actualSourceTriangles':m['sourceSupport']['triangleCount'],'sourceSpecificPixels':m['checks']['sourceSpecificMinYPixels'],'verifiedOldFrontWallRays':sum(r['previousOldInFront']for r in raychecks),'allPreviouslyFrontWallRaysNowDiscarded':True,'pvTriangles':len(pv),'minimumPVVertexClearanceMeters':min(clear),'pvPositionMeasured':False})
report={'status':'pass','sourceFilesHashAndMatrixVerified':len(sources),'scope':'Independent geometric pixel-cell intersection samples (up to1024 each external/common/empty per hall), per-pixel minimum height, saved camera rays and GLB PV vertex clearance; not browser acceptance or surveyed ownership.','buildings':reports};(O/'source-support-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
