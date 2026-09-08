#!/usr/bin/env python3
"""Actual source and production CPU-mask regression for the U57 staging candidate.

Never writes public assets. Live source-hit witnesses come from the independently
captured fixed browser pose; raw GLB triangles and source SHA are rechecked here.
This is not browser acceptance or a universal vegetation/ownership classifier.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from hkust_source_geometry import geometry

P=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--candidate',type=Path,default=Path('/tmp/hkust-ivillage-replacement-u57'))
ap.add_argument('--source',type=Path,default=Path('/tmp/hkust-ivillage-rebuild-source'))
args=ap.parse_args();O=args.candidate;S=args.source
before=O/'evidence/before';E=O/'evidence';E.mkdir(parents=True,exist_ok=True)
historical_before=Path('/tmp/hkust-ivillage-replacement-u57b/evidence/before')
if not historical_before.exists():historical_before=before
old=json.loads((before/'manifest.json').read_text());new=json.loads((O/'manifest.json').read_text())
source=np.load(S/'terminal-triangles.npz');T=source['positions'];N=source['normals'];C=T.mean(1)
source_tile_indices=source['sourceTileIndex'];source_triangle_indices=source['triangleIndex']
sources=json.loads((S/'sources.json').read_text())['sources']
reports=[]


def check(name,condition,**evidence):
    reports.append({'name':name,'pass':bool(condition),**evidence})


def point(index,position=None,**extra):
    return {'stagedTriangleIndex':int(index),'sourceTileIndex':int(source_tile_indices[index]),
        'triangleIndex':int(source_triangle_indices[index]),
        'point':T[index].mean(0).tolist() if position is None else position,
        'normal':N[index].tolist(),**extra}


# This executes the current application classes. It does not mirror their union,
# alpha-floor or source-protection logic in Python.
runtime=r"""
import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';
import sharp from 'sharp';import * as THREE from 'three';
const payload=JSON.parse(fs.readFileSync(0,'utf8')),compiled=new Map();
function compile(name){
 if(compiled.has(name))return compiled.get(name);
 const exports={};compiled.set(name,exports);
 const code=ts.transpileModule(fs.readFileSync(`app/${name}.ts`,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require:id=>id==='three'?THREE:compile(id.replace('./','')),Uint8Array,Uint8ClampedArray,Map,Set,WeakMap,Math,Number,Error});return exports;
}
const {SpatialMasks}=compile('spatial-masks'),{CurrentFormCoverage}=compile('current-form-coverage'),{isVisibleSurfaceHit}=compile('entity-picking');
async function load(base){
 const manifest=JSON.parse(fs.readFileSync(base+'/manifest.json')),p=manifest.sourceProtection,masks=new SpatialMasks();
 masks.configureSourceProtection([...p.boundsXZ.min,...p.boundsXZ.max],16);
 const entries=[];for(const m of manifest.members){const pixels=await sharp(base+'/'+m.mask.url).ensureAlpha().raw().toBuffer();entries.push({id:m.buildingId,descriptor:m.mask,pixels:new Uint8ClampedArray(pixels)});}
 new CurrentFormCoverage(masks).addPixelsBatch(entries);
 masks.setSourceProtection(new THREE.DataTexture(new Uint8Array(fs.readFileSync(base+'/'+p.url)),p.width,p.height),[...p.boundsXZ.min,...p.boundsXZ.max],p.groundBandMeters);
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(300,100,300),new THREE.MeshBasicMaterial());mesh.position.set(700,150,-1100);masks.apply(mesh,'photogrammetry');
 function visible(v){return isVisibleSurfaceHit({object:mesh,point:new THREE.Vector3(...v.point),face:{normal:new THREE.Vector3(...v.normal),materialIndex:0},distance:1},masks);}
 return visible;
}
const a=await load(payload.before),b=await load(payload.after);
process.stdout.write(JSON.stringify(payload.points.map(p=>({before:a(p),after:b(p)}))));
"""


def states(points,before_folder=before):
    result=subprocess.run(['node','--input-type=module','-e',runtime],cwd=P,
        input=json.dumps({'before':str(before_folder),'after':str(O),'points':points}),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


live=json.loads((P/'docs/source-evidence-v4/ivillage-remnants/stable-rays-before.json').read_text())
for filename,pixels in [('real-rays-after.json',[r['pixel']for r in live['rays']]),
        ('environment-rays-after.json',[[900,630],[738,640],[938,508]])]:
    subprocess.run([sys.executable,str(P/'scripts/check-ivillage-remnant-rays.py'),
        '--masks',str(O),'--pose',str(P/'docs/source-evidence-v4/ivillage-remnants/stable-before.json'),
        '--pixels',json.dumps(pixels),'--output',str(E/filename)],cwd=P,check=True,capture_output=True,text=True)
live_points=[point(h['stagedTriangleIndex'],h['point'],pixel=r['pixel']) for r in live['rays']
    for h in r['sourceBeforeModel'] if not h['removed']]
actual_files=[]
for si in sorted({p['sourceTileIndex'] for p in live_points}|{28,51,89,90}):
    d=sources[si];path=Path(d['localPath']);raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==d['sha256']
    triangles,_=geometry(path,np.array(d['matrix']).reshape(4,4,order='F'))
    ids=np.flatnonzero(source_tile_indices==si)
    error=float(np.max(np.abs(triangles[source_triangle_indices[ids]]-T[ids])))
    assert error<=1e-9
    actual_files.append({'sourceTileIndex':si,'id':d['id'],'path':str(path),'sha256':d['sha256'],'maximumMatrixPositionErrorMeters':error})
check('live-witnesses-come-from-unchanged-source-glb-and-exact-matrix',True,sources=actual_files)

probes=[point(j)for j in [557285,564138,317450]]
probe_states=states(probes,historical_before)
check('above-ground-orientation-filter-real-counterexamples',all(s['before'] and not s['after'] for s in probe_states),
    witnesses=[{**p,**s}for p,s in zip(probes,probe_states)])
live_states=states(live_points,historical_before)
check('eight-high-wall-rays-removed-and-low-ground-contact-kept',len(live['rays'])==9 and bool(live_points) and
    all(s['before'] and s['after']==(p['pixel']==[865,440])for p,s in zip(live_points,live_states)),
    clearHighRays=8,groundAdjacentPendingRay=[865,440],intersections=len(live_points),
    witnesses=[{**p,**s}for p,s in zip(live_points,live_states)])

# Independent fixed spatial query over original source geometry, not the new
# selector's output IDs. It covers the photographed narrow strip's full height.
strip=(C[:,0]>=769.389)&(C[:,0]<=772.795)&(C[:,2]>=-1067.408)&(C[:,2]<=-1063.730)&(C[:,1]>=142)&(C[:,1]<=174.2)&(abs(N[:,1])<.6)
strip_ids=np.flatnonzero(strip);strip_states=states([point(i)for i in strip_ids],historical_before)
check('xiii-connected-strip-entire-sampled-height',len(strip_ids)>1000 and not any(s['after']for s in strip_states),
    triangles=len(strip_ids),yRange=[float(C[strip,1].min()),float(C[strip,1].max())],
    remainingBefore=sum(s['before']for s in strip_states),remainingAfter=sum(s['after']for s in strip_states))

ground=np.load(P/'public/models/current-forms/ivillage-rebuild/evidence/ground-preservation-witnesses.npz')
pd=old['sourceProtection'];ground_points=[]
source_keys=source_tile_indices.astype(np.int64)*2**32+source_triangle_indices.astype(np.int64)
source_order=np.argsort(source_keys)
sorted_source_keys=source_keys[source_order]
for row,col,height,si,ti in zip(ground['row'],ground['col'],ground['height'],ground['sourceTileIndex'],ground['triangleIndex']):
    key=int(si)*2**32+int(ti);j=int(source_order[np.searchsorted(sorted_source_keys,key)])
    assert source_keys[j]==key
    ground_points.append({'point':[pd['boundsXZ']['min'][0]+(int(col)+.5)*.5,float(height),
        pd['boundsXZ']['min'][1]+(int(row)+.5)*.5],'normal':N[j].tolist(),
        'sourceTileIndex':int(si),'triangleIndex':int(ti)})
ground_states=states(ground_points)
check('every-previously-witnessed-source-ground-stays-visible',len(ground_points)>=1032 and
    all(s['before'] and s['after']for s in ground_states),samples=len(ground_points))

# Visually selected negatives from stable-before.png: tree canopy (900,630),
# sport court (738,640), outside access road (938,508). The ray script verifies
# actual source intersections; these are not synthetic points at guessed height.
environment=json.loads((E/'environment-rays-after.json').read_text())
labels={(900,630):'visible tree canopy',(738,640):'visible sport court',(938,508):'visible outside access road'}
environment_points=[point(h['stagedTriangleIndex'],h['point'],pixel=r['pixel'],visualReference=labels[tuple(r['pixel'])])
    for r in environment['rays']if tuple(r['pixel'])in labels for h in r['sourceBeforeModel']]
environment_states=states(environment_points)
check('actual-tree-court-road-source-negative-rays-stay-visible',len(environment_points)>=5 and
    all(s['before'] and s['after']for s in environment_states),
    witnesses=[{**p,**s}for p,s in zip(environment_points,environment_states)])
unanchored=point(293761);unanchored_state=states([unanchored])[0]
check('unanchored-near-ground-source-not-forced-into-wall',unanchored_state['before'] and unanchored_state['after'],
    witness={**unanchored,**unanchored_state},reason='It passes radial alignment but has no shared-edge connection to accepted wall; no building identity claimed.')
buried=point(157656);buried_state=states([buried])[0]
check('below-dtm-alpha-probe-is-retained-not-mislabelled-as-proven-wall',buried_state['before'] and buried_state['after'],
    witness={**buried,**buried_state},sourceY=142.91701673002203,dtm=146.86640000000006)

check('four-member-identity-and-glb-unchanged',old['asset']==new['asset'] and
    [(m['entityId'],m['buildingId'],m['nodeName'])for m in old['members']]==[(m['entityId'],m['buildingId'],m['nodeName'])for m in new['members']] and
    hashlib.sha256((O/new['asset']['url']).read_bytes()).hexdigest()==new['asset']['sha256'])

# Quantify projection ambiguity instead of silently claiming every source face
# sharing a mask column has a proven semantic owner.
unattributed=np.unique(np.concatenate([np.load(E/f"{m['catalogId']}-unattributed-candidates.npz")['stagedTriangleIndex']for m in new['members']]))
unknown_states=states([point(i)for i in unattributed])
collateral=unattributed[np.array([s['before'] and not s['after']for s in unknown_states])]
np.savez_compressed(E/'unattributed-projection-overlap.npz',stagedTriangleIndex=collateral,
    sourceTileIndex=source_tile_indices[collateral],triangleIndex=source_triangle_indices[collateral],positions=T[collateral],normals=N[collateral])
grid=np.load(S/'roof-grid.npz');rows=np.floor((C[collateral,2]-grid['z0'])/grid['step']).astype(int).clip(0,grid['ground'].shape[0]-1)
cols=np.floor((C[collateral,0]-grid['x0'])/grid['step']).astype(int).clip(0,grid['ground'].shape[1]-1)
dtm=grid['ground'][rows,cols]
(E/'unattributed-projection-overlap.json').write_text(json.dumps({'status':'no-new-loss' if not len(collateral)else'requires-review-not-protected-by-candidate',
    'count':len(collateral),'faces':[{**point(j),'minY':float(T[j,:,1].min()),'maxY':float(T[j,:,1].max()),
        'dtm':float(dtm[k]),'centroidMinusDTM':float(C[j,1]-dtm[k]),'protected':False}
        for k,j in enumerate(collateral)]},indent=2)+'\n')
check('unattributed-projection-overlap-is-protected',not len(collateral),unattributedSourceFaces=len(unattributed),
    newlyHiddenUnattributedCentroids=len(collateral),evidence='unattributed-projection-overlap.npz',
    alreadyHiddenByOldMasks=sum(not s['before']for s in unknown_states),
    revivedOldHiddenFaces=sum(not s['before'] and s['after']for s in unknown_states),
    interpretation='Unknown source faces remain visible wherever they were previously visible. Already hidden old-mask faces are not revived.')

examined=np.load(E/'unattributed-volumes-examined.npz')['stagedTriangleIndex']
volume_points=[]
for weights in [[1/3,1/3,1/3],[.7,.2,.1],[.1,.7,.2],[.2,.1,.7]]:
    positions=np.einsum('ijk,j->ik',T[examined],weights)
    volume_points.extend(point(i,p.tolist())for i,p in zip(examined,positions))
volume_states=states(volume_points)
check('all-examined-unknown-source-faces-interior-samples-preserved',bool(examined.size) and
    not any(s['before'] and not s['after']for s in volume_states),sourceTriangles=len(examined),
    samples=len(volume_points),newlyHiddenSamples=sum(s['before'] and not s['after']for s in volume_states))
guard=np.load(E/'column-guards.npz');conflict=guard['conflict']
exact_rollback=True
for member in new['members']:
    a=np.asarray(Image.open(before/member['mask']['url']).convert('RGBA'))
    b=np.asarray(Image.open(O/member['mask']['url']).convert('RGBA'))
    exact_rollback&=np.array_equal(a[conflict],b[conflict])
check('conflicting-columns-restore-exact-old-rgba-at-all-heights',exact_rollback,rejectedNewColumns=int(conflict.sum()))
old_on=np.isfinite(guard['oldMinY'])
check('old-deletion-intervals-never-shrink',np.all(guard['finalMinY'][old_on]<=guard['oldMinY'][old_on]) and
    np.all(guard['finalMaxY'][old_on]>=guard['oldMaxY'][old_on]),oldColumns=int(old_on.sum()))

attributed=np.unique(np.concatenate([np.load(E/f"{m['catalogId']}-added-wall-witnesses.npz")['stagedTriangleIndex']for m in new['members']]))
attributed_states=states([point(i)for i in attributed])
# Audit every actual source centroid in changed mask columns, including copied
# source faces later proved equivalent to an attributed wall. A candidate-only
# list would miss those six small copies in U60's newly unblocked columns.
changed_columns=(guard['oldMinY']!=guard['finalMinY'])|(guard['oldMaxY']!=guard['finalMaxY'])
all_rows=np.floor((C[:,2]-float(grid['z0']))/float(grid['step'])).astype(int)
all_cols=np.floor((C[:,0]-float(grid['x0']))/float(grid['step'])).astype(int)
inside=(all_rows>=0)&(all_rows<changed_columns.shape[0])&(all_cols>=0)&(all_cols<changed_columns.shape[1])
query_ids=np.flatnonzero(inside);query_ids=query_ids[changed_columns[all_rows[query_ids],all_cols[query_ids]]]
query_states=states([point(i)for i in query_ids])
effective=query_ids[np.array([s['before']and not s['after']for s in query_states])]
np.savez_compressed(E/'effective-added-wall-centroids.npz',stagedTriangleIndex=effective,sourceTileIndex=source_tile_indices[effective],
    triangleIndex=source_triangle_indices[effective],positions=T[effective],normals=N[effective])
check('effective-removal-separated-from-attribution-candidates',True,attributedCandidates=len(attributed),
    queriedSourceCentroidsInChangedColumns=len(query_ids),newlyHiddenCentroids=len(effective),evidence='effective-added-wall-centroids.npz',
    interpretation='For offline review only: triangles are selected by actual runtime centroid visibility; GPU mask may retain other portions.')

old_union=np.zeros((pd['height'],pd['width']),bool);new_union=old_union.copy()
for m in old['members']:old_union|=np.asarray(Image.open(before/m['mask']['url']))[:,:,0]>127
for m in new['members']:new_union|=np.asarray(Image.open(O/m['mask']['url']))[:,:,0]>127
image=np.zeros((*old_union.shape,3),np.uint8);image[old_union]=[80,160,180];image[new_union&~old_union]=[230,70,40]
Image.fromarray(image).resize((pd['width']*3,pd['height']*3),Image.Resampling.NEAREST).save(E/'coverage-delta.png')
check('coverage-remains-source-projected-not-bbox-filled',not np.any(old_union&~new_union) and float(new_union.mean())<.35,
    oldOccupiedPixels=int(old_union.sum()),newOccupiedPixels=int(new_union.sum()),newOutsidePixels=int((new_union&~old_union).sum()))

# Fixed source-space regions from the rejected candidate's independently rendered
# effective-source overlays. These are regression witnesses, never selector IDs.
# Check actual previously deleted triangles, not just the classifier's seed set.
previous_candidate=Path('/tmp/hkust-ivillage-replacement-u57')
previous_effective=np.load(previous_candidate/'evidence/effective-added-wall-centroids.npz')['stagedTriangleIndex']
negative_regions=[
    ('hall-xii-rear-two-dark-canopy-lobes',[710.9,146.7,-1064.6],[725.5,156.5,-1054.4]),
    ('east-low-squat-canopy',[781.8,142,-1034.4],[790.1,146.9,-1025.2]),
    ('hall-x-oblique-floating-dark-fragment',[619.9,160.5,-1049.5],[626.2,166.1,-1044.4]),
]
negative_results=[]
for name,low,high in negative_regions:
    centers=C[previous_effective]
    selected=previous_effective[((centers>=low)&(centers<=high)).all(1)]
    rows=[]
    for weights in [[1/3,1/3,1/3],[.6,.2,.2],[.2,.6,.2],[.2,.2,.6]]:
        positions=np.einsum('ijk,j->ik',T[selected],weights)
        rows.extend(point(i,p.tolist())for i,p in zip(selected,positions))
    values=states(rows,previous_candidate)
    original_values=states(rows,historical_before)
    # Some interior samples of a triangle whose CENTROID was newly deleted
    # already lay under the old public mask. U57b must not revive that old mask.
    previous_removed=sum(o['before'] and not s['before']for o,s in zip(original_values,values))
    retained=sum(o['before'] and not s['before'] and s['after']for o,s in zip(original_values,values))
    check(name+'-new-deletion-rejected',len(selected)>20 and previous_removed>0 and retained==previous_removed,
        sourceTriangles=len(selected),sourceBounds={'min':low,'max':high},samples=len(rows),
        removedByRejectedU57=previous_removed,preservedByU57b=retained,
        alreadyHiddenByOriginalMask=sum(not o['before']for o in original_values),
        previousManifestSHA256=hashlib.sha256((previous_candidate/'manifest.json').read_bytes()).hexdigest())
    negative_results.append({'name':name,'stagedTriangleIndices':selected.tolist(),
        'samples':[{**p,**s,'originalPublicVisible':o['before']}for p,s,o in zip(rows,values,original_values)]})
(E/'foliage-negative-source-samples.json').write_text(json.dumps(negative_results,indent=2)+'\n')

guard_review=json.loads((E/'nonbuilding-source-review.json').read_text())
guard_ids=np.load(E/'nonbuilding-source-witnesses.npz')['stagedTriangleIndex']
guard_values=states([point(i)for i in guard_ids])
check('all-withheld-nonbuilding-source-centroids-keep-original-visibility',len(guard_ids)>500 and
    not any(s['before'] and not s['after']for s in guard_values),sourceTriangles=len(guard_ids),
    newlyHidden=sum(s['before'] and not s['after']for s in guard_values),evidence='nonbuilding-source-witnesses.npz')
# The real shadowed XIII component is dark enough to trigger the appearance
# predicate. Its tall connected structure must nevertheless remain a wall.
shadow=[c for c in guard_review['components']if 317450 in c['stagedTriangleIndices']]
if not shadow:
    prior_guard=json.loads(Path('/tmp/hkust-ivillage-replacement-u57b/evidence/nonbuilding-source-review.json').read_text())
    shadow=[c for c in prior_guard['components']if 317450 in c['stagedTriangleIndices']]
check('dark-real-facade-is-not-reclassified-by-colour-alone',len(shadow)==1 and
    not shadow[0]['withheldFromWallAttribution'] and shadow[0]['bounds']['max'][1]-shadow[0]['bounds']['min'][1]>25,
    component={k:v for k,v in shadow[0].items()if k!='stagedTriangleIndices'}if shadow else None)

set_bytes=effective.astype('<u8').tobytes()
(E/'effective-removal-set.json').write_text(json.dumps({'triangles':len(effective),
    'stagedTriangleIdsSHA256':hashlib.sha256(set_bytes).hexdigest(),'hashEncoding':'sorted little-endian unsigned 64-bit stagedTriangleIndex',
    'npzSHA256':hashlib.sha256((E/'effective-added-wall-centroids.npz').read_bytes()).hexdigest(),
    'comparison':'Newly hidden actual source centroids relative to evidence/before, never total deletion including old masks.',
    'baselineManifestSHA256':hashlib.sha256((before/'manifest.json').read_bytes()).hexdigest(),
    'historicalRejectedU57Centroids':len(previous_effective),
    'historicalRejectedU57Overlap':len(np.intersect1d(effective,previous_effective))},indent=2)+'\n')

u60_path=P/'docs/source-evidence-v4/ivillage-remnants/u60-close-rays-before.json'
if (E/'overlapping-source-wall-witnesses.json').exists() and u60_path.exists():
    u60=json.loads(u60_path.read_text())
    u60_source_checks=[]
    for si in sorted({h['sourceTileIndex']for ray in u60['rays']for h in ray['sourceBeforeModel']}):
        descriptor=sources[si];path=Path(descriptor['localPath'])
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        triangles,_=geometry(path,np.array(descriptor['matrix']).reshape(4,4,order='F'))
        ids=np.flatnonzero(source_tile_indices==si)
        error=float(np.max(np.abs(triangles[source_triangle_indices[ids]]-T[ids])))
        u60_source_checks.append({'sourceTileIndex':si,'id':descriptor['id'],'sha256':sha,
            'maximumMatrixPositionErrorMeters':error,'pass':sha==descriptor['sha256']and error<=1e-9})
    check('u60-actual-source-files-and-exact-matrices',bool(u60_source_checks)and all(x['pass']for x in u60_source_checks),sources=u60_source_checks)
    subprocess.run([sys.executable,str(P/'scripts/check-ivillage-remnant-rays.py'),
        '--masks',str(O),'--pose',str(P/'docs/source-evidence-v4/ivillage-remnants/u60-close-pose.json'),
        '--pixels',json.dumps([r['pixel']for r in u60['rays']]),'--output',str(E/'u60-close-rays-after.json')],cwd=P,check=True,capture_output=True,text=True)
    # These are the recorded narrow wall points; the same rays can also hit
    # independently preserved ground behind it (not every hit is a wall).
    wall_points=[point(h['stagedTriangleIndex'],h['point'],pixel=r['pixel'])for r in u60['rays']
        if r['pixel'][0]==958 for h in r['sourceBeforeModel']if h['point'][0]>771 and h['point'][2]>-1064]
    wall_values=states(wall_points)
    check('u60-second-wall-recorded-full-height-rays-cleared',len(wall_points)>=14 and
        not any(s['after']for s in wall_values),intersections=len(wall_points),
        yRange=[min(p['point'][1]for p in wall_points),max(p['point'][1]for p in wall_points)],
        witnesses=[{**p,**s}for p,s in zip(wall_points,wall_values)])
    floating=[point(h['stagedTriangleIndex'],h['point'],pixel=r['pixel'])for r in u60['rays']
        if r['pixel']in[[385,340],[390,370]]for h in r['sourceBeforeModel']]
    floating_values=states(floating)
    floating_evidence=[]
    for p,s in zip(floating,floating_values):
        xyz=p['point'];col=int((xyz[0]-float(grid['x0']))/float(grid['step']));row=int((xyz[2]-float(grid['z0']))/float(grid['step']))
        dtm=float(grid['ground'][row,col]);floating_evidence.append({**p,**s,'dtm':dtm,'sourceYMinusDTM':xyz[1]-dtm})
    check('u60-apparent-air-hits-are-real-dtm-ground-and-kept',len(floating)==2 and
        all(s['before']and s['after']for s in floating_values) and all(abs(x['sourceYMinusDTM'])<=1 and x['normal'][1]>=.6 for x in floating_evidence),
        witnesses=floating_evidence,
        interpretation='No current-model hit does not prove a suspended building remnant. These upward source faces agree with true DTM within 1m and sit >22m from every rebuilt envelope.')
    overlap=json.loads((E/'overlapping-source-wall-witnesses.json').read_text())
    from shapely.geometry import Polygon
    source_pairs=[]
    for row in overlap['faces']:
        j,k=row['stagedTriangleIndex'],row['witnessTriangleIndex']
        # Independently recompute the full source triangle containment, including
        # all edge interiors (convex triangle), rather than trusting saved flags.
        u=T[k,1]-T[k,0];u=u/np.linalg.norm(u);v=np.cross(N[k],u);basis=np.column_stack([u,v])
        outer=Polygon((T[k]-T[k,0])@basis);inner=Polygon((T[j]-T[k,0])@basis)
        ok=outer.buffer(.003).covers(inner) and abs((T[j]-T[k,0])@N[k]).max()<=.001 and abs(N[j]@N[k])>=.999
        source_pairs.append(ok)
    documented={316018,316019,316022,316023,316060,316067}
    check('u60-retriangulated-wall-copies-have-complete-millimetre-source-overlap',bool(source_pairs)and all(source_pairs)and
        documented.issubset({r['stagedTriangleIndex']for r in overlap['faces']}),pairs=len(source_pairs),
        documentedFalseUnknownTriangles=sorted(documented),evidence='overlapping-source-wall-witnesses.json')
    previous_guard=np.load('/tmp/hkust-ivillage-replacement-u57b/evidence/nonbuilding-source-witnesses.npz')['stagedTriangleIndex']
    inherited_values=states([point(i)for i in previous_guard])
    check('u60-all-3867-previous-nonbuilding-source-volumes-retained',len(previous_guard)==3867 and
        not any(s['before'] and not s['after']for s in inherited_values),sourceFaces=len(previous_guard),
        newlyHidden=sum(s['before'] and not s['after']for s in inherited_values))

result={'status':'pass-staging-awaiting-visual-acceptance' if all(r['pass']for r in reports) else 'fail',
    'checks':reports,'passed':sum(r['pass']for r in reports),'total':len(reports),
    'limitations':['This is a staging candidate, not runtime/browser acceptance.',
        'The source-ray negatives cover observed tree/court/road samples, not every environment surface.',
        'Ambiguous source columns are left at their original masks; small ground-adjacent old traces intentionally remain.',
        'No cadastral ownership, all-tree classifier, or complete exterior watertightness is claimed.']}
(E/'regression.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'passed':result['passed'],'total':result['total'],
    'newlyHiddenUnattributedCentroids':len(collateral),'report':str(E/'regression.json')}))
raise SystemExit(0 if all(r['pass']for r in reports)else 1)
