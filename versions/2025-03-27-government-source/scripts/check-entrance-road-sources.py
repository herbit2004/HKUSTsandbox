#!/usr/bin/env python3
"""Read-only centreline/source alignment audit. No road width or paving is inferred."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import LineString, Polygon, points, polygons, STRtree
from shapely.ops import unary_union
from hkust_source_geometry import geometry, Heights

P=Path(__file__).resolve().parents[1]
outdoor=json.loads((P/'public/data/outdoor-entities.json').read_text())
road=next(r for r in outdoor['roads'] if r['entityId']=='path:streetcode:52360')
line=LineString(road['linesLocalXZ'][0])
distance=np.linspace(0,line.length,int(np.ceil(line.length/.5))+1)
xz=np.array([[p.x,p.y] for p in [line.interpolate(float(d)) for d in distance]])
heights=Heights(list((P/'public/terrain/source-data').glob('*.tif')))
dh=heights(np.c_[xz[:,0]+844800,820500-xz[:,1]])
manifest=json.loads((P/'public/models/hires/partial-entrance/manifest.json').read_text())
patch=manifest['patches'][0]
tr=np.concatenate([geometry(P/'public/models/hires'/t['url'],np.array(t['matrix']).reshape(4,4,order='F'))[0]
                   for t in patch['levels']['high']['tiles']])
cross=np.cross(tr[:,1]-tr[:,0],tr[:,2]-tr[:,0]);normal=np.linalg.norm(cross,axis=1)
ok=abs(cross[:,1])>1e-8;tr=tr[ok];cross=cross[ok];normal=normal[ok]
pair=STRtree(polygons(tr[:,:,[0,2]])).query(points(xz),predicate='intersects')
k=pair[0];tt=tr[pair[1]];n=cross[pair[1]]
y=tt[:,0,1]-(n[:,0]*(xz[k,0]-tt[:,0,0])+n[:,2]*(xz[k,1]-tt[:,0,2]))/n[:,1]
upper=np.full(len(xz),-np.inf);np.maximum.at(upper,k,y)
lower_compatible=np.zeros(len(xz),bool)
lower_compatible[k[(abs(y-dh[k])<=1.5)&(abs(n[:,1])/normal[pair[1]]>=.6)]]=True
upper[upper==-np.inf]=np.nan
sm=json.loads((P/'public/surfaces/entrance/manifest.json').read_text())['mask']
surface=np.asarray(Image.open(P/'public/surfaces/entrance'/sm['url']))
c=np.floor((xz[:,0]-sm['minX'])/sm['pixelSizeMeters']).astype(int)
r=np.floor((xz[:,1]-sm['minZ'])/sm['pixelSizeMeters']).astype(int)
surface_covered=surface[r,c,0]>0
domain=json.loads((P/'public/surfaces/entrance/source-domains.json').read_text())
official=unary_union([Polygon(p['rings'][0],p['rings'][1:]) for p in domain['sourceDomainLocalXZ']])
domain_covered=np.array([official.covers(p) for p in points(xz)])
pm=patch['mask'];a=np.asarray(Image.open(P/'public/models/hires'/pm['url']))
c=np.floor((xz[:,0]-pm['minX'])/pm['pixelSizeMeters']).astype(int)
r=np.floor((xz[:,1]-pm['minZ'])/pm['pixelSizeMeters']).astype(int)
partial_covered=a[r,c]>0
connection=next(r for r in outdoor['roads'] if r['entityId']=='path:universityroad')
endpoints=np.array([point for l in connection['linesLocalXZ'] for point in [l[0],l[-1]]])
endpoint_difference=float(np.min(np.linalg.norm(endpoints-xz[-1],axis=1)))
def ranges(sel):
    transitions=np.r_[0,np.flatnonzero(sel[1:]!=sel[:-1])+1,len(sel)]
    return [{'fromMeters':float(distance[a]),'toMeters':float(distance[b-1]),
             'startLocalXZ':xz[a].tolist(),'endLocalXZ':xz[b-1].tolist()}
            for a,b in zip(transitions[:-1],transitions[1:]) if sel[a]]
def stats(v):
    v=v[np.isfinite(v)]
    return {'count':len(v),'min':float(v.min()),'median':float(np.median(v)),
            'p95':float(np.quantile(v,.95)),'max':float(v.max())}
report={'entityId':road['entityId'],'sourceCentrelineId':road['segments'][0]['streetCentrelineId'],
        'registryFunction':road.get('function'),'lineLengthMeters':line.length,'pointChecks':len(xz),
        'maximumSampleSpacingMeters':float(np.max(np.diff(distance))),
        'universityRoadEndpointDistanceMeters':endpoint_difference,
        'partialProjectionCoverage':int(partial_covered.sum()),'actualRefinedSourceIntersections':int(np.isfinite(upper).sum()),
        'insideSelectedOfficialLineworkDomain':int(domain_covered.sum()),
        'existingTDOPGroundCoverage':int(surface_covered.sum()),
        'compatibleLowSlopeSourceGroundWithin1_5mOfDTM':int(lower_compatible.sum()),
        'upperSourceMinusDTMMeters':stats(upper-dh),'dtmHKPD':stats(dh),
        'sourceRaisedAboveDTMOver1_5mRanges':ranges(upper-dh>1.5),
        'existingTDOPMissingRanges':ranges(~surface_covered),
        'partialCoverageMissingRanges':ranges(~partial_covered),
        'interpretation':['The exact source centreline is connected at one identical University Road endpoint; no complete routing graph is inferred.',
         'Projection coverage proves alignment and a source surface above each checked point, not visible pavement or absence of crown occlusion.',
         'High source surfaces above DTM may be real overhanging crown, source reconstruction artifacts, or raised infrastructure; this audit does not classify them.',
         'TDOP currently follows official polygonized domains only where an actual source upper surface supports bare ground. No road width or hidden paving is invented.',
         'The 2025 orthophoto visibly contains real tree/shadow occlusion along this access road. A continuous synthetic road ribbon must not replace those observations.']}
assert endpoint_difference==0 and partial_covered.all() and np.isfinite(upper).all()
dest=P/'public/surfaces/entrance/road-52360-source-qa.json'
report['sourceCentrelineCurrentSurfaceConflict']={'diagnostic':'road-source-alignment-qa.png','sourceFaceChecks':'road-source-face-alignment.json','observation':'Most52360 centreline samples project over narrow roof-like covered structures in unchanged2025 TDOP, west of visible approach paving; do not derive a road-width polygon or flatten roof pixels from that line.','sampleCountOnFace115':192,'face115AreaM2':456.499690497282,'confidenceBoundary':'Observed aerial projection conflict does not determine historic or current infrastructure use.'}
dest.write_text(json.dumps(report,indent=2))
np.savetxt(P/'public/surfaces/entrance/road-52360-source-samples.csv',
           np.c_[distance,xz,dh,upper,upper-dh,partial_covered,surface_covered,domain_covered,lower_compatible],
           delimiter=',',header='distanceMeters,localX,localZ,dtmHKPD,upperPhotoY,photoMinusDTM,partialMask,tdopGround,officialDomain,compatibleSourceGround',comments='')
print(json.dumps({k:v for k,v in report.items() if not k.endswith('Ranges')},indent=2))
