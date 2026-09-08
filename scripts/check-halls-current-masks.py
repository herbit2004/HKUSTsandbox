#!/usr/bin/env python3
"""Independent final GLB triangle/pixel-center proof of three current-form masks."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely import contains_xy
from hkust_source_geometry import geometry

ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path('.'));args=ap.parse_args()
O=args.project/'public/models/current-forms/halls-current';m=json.loads((O/'manifest.json').read_text());reports=[]
for b in m['buildings']:
 t,_=geometry(O/b['url']);mask=b['mask'].get('actualModelProjection',b['mask']);a=np.array(Image.open(O/mask['url']));h,w=a.shape;yy,xx=np.mgrid[:h,:w];x=mask['boundsXZ']['min'][0]+(xx+.5)*.5;z=mask['boundsXZ']['min'][1]+(yy+.5)*.5;truth=np.zeros((h,w),bool)
 for v in t:
  p=Polygon(v[:,[0,2]])
  if p.area>1e-8:truth|=contains_xy(p,x,z)
 mismatch=int(np.count_nonzero(truth!=(a>0)));assert mismatch==0,(b['catalogId'],mismatch)
 reports.append({'catalogId':b['catalogId'],'pixels':w*h,'coveredPixels':int(truth.sum()),'mismatches':mismatch,'maskSha256':hashlib.sha256((O/mask['url']).read_bytes()).hexdigest()})
report={'status':'pass','method':'independent actual GLB triangles / pixel-center polygon containment versus saved raster','buildings':reports};(O/'mask-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
