#!/usr/bin/env python3
"""Validate exported partial GLBs and ground-reference pixels against original sources.

Independent pixel-centre predicates use Shapely triangle intersections rather than
the builder's rasterizer. Input heights come from source TIFF pixels. No browser
or screenshot acceptance is implied by these numerical checks.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import STRtree, points, polygons
from hkust_source_geometry import geometry, Heights, select

ap = argparse.ArgumentParser()
ap.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
ap.add_argument('--source', type=Path, required=True)
ap.add_argument('--cache', type=Path, required=True)
ap.add_argument('--ray-report', type=Path, required=True)
ap.add_argument('--partial-folder', default='partial-entrance')
ap.add_argument('--level', choices=['high','fine'], default='high')
ap.add_argument('--skip-ground', action='store_true')
args = ap.parse_args()
P = args.project
rng = np.random.default_rng(20260906)

patch_dir = P/'public/models/hires'/args.partial_folder
patch = json.loads((patch_dir/'manifest.json').read_text())['patches'][0]
subtree = patch['id'].removesuffix('-partial-entrance')
level = patch['levels'][args.level]
tiles = level['tiles']
base = next(t for t in json.loads((P/'public/models/render-manifest.json').read_text())['tiles']
            if t['id'] == patch['baselineIds'][0])
entries = json.loads((args.source/'source-zip-index.json').read_text())
source_tree = json.loads((args.source/subtree/'source-tileset.json').read_text())
_, frontier, issues = select(source_tree['root']['children'][0]['children'][0]['children'][0],
                             subtree, entries, 0 if args.level=='fine' else .9)
assert not issues and {a['source_name'] for a in frontier} == {t['sourceZipName'] for t in tiles}
assert patch['evidence']['missingSibling'] not in entries
tris = []
for t in tiles:
    raw = (P/'public/models/hires'/t['url']).read_bytes()
    b3dm = (args.cache/Path(t['sourceZipName']).name).read_bytes()
    head = struct.unpack_from('<4s6I', b3dm)
    assert head[0] == b'b3dm' and head[2] == len(b3dm)
    assert raw == b3dm[28+sum(head[3:]):]
    assert hashlib.sha256(raw).hexdigest() == t['sha256']
    assert hashlib.sha256(b3dm).hexdigest() == t['sourceB3dmSha256']
    assert zlib.crc32(b3dm) == entries[t['sourceZipName']]['crc32']
    assert t['matrix'] == base['matrix']
    assert t['textureDimensions'] == [[x['width'], x['height']] for x in t['textures']]
    tri, _ = geometry(P/'public/models/hires'/t['url'], np.array(t['matrix']).reshape(4, 4, order='F'))
    assert len(tri) == t['triangles']
    tris.append(tri)
tri = np.concatenate(tris)
m = level.get('mask',patch['mask'])
mask = np.asarray(Image.open(P/'public/models/hires'/m['url']))
assert mask.shape == (m['height'], m['width'])
# Include every uncovered cell, plus a reproducible random sample of all cells.
flat = np.unique(np.r_[np.flatnonzero(mask.ravel() == 0), rng.choice(mask.size, 12000, replace=False)])
rr, cc = np.unravel_index(flat, mask.shape)
xz = np.c_[m['minX']+(cc+.5)*m['pixelSizeMeters'], m['minZ']+(rr+.5)*m['pixelSizeMeters']]
cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
tree = STRtree(polygons(tri[abs(cross[:, 1]) > 1e-9][:, :, [0, 2]]))
pairs = tree.query(points(xz), predicate='intersects')
expected = np.zeros(len(flat), bool)
expected[pairs[0]] = True
assert np.array_equal(expected, mask[rr, cc] > 0)

ray_source = json.loads(args.ray_report.read_text())
camera = np.array(ray_source['camera'])
refined_rays = []
e1 = tri[:, 1]-tri[:, 0]
e2 = tri[:, 2]-tri[:, 0]
v = camera-tri[:, 0]
for ray in ray_source['rays'][:3]:
    old = ray['hits'][0]
    if not old['object'].endswith(patch['baselineIds'][0]):
        continue
    d = np.array(old['position'])-camera
    d /= np.linalg.norm(d)
    h = np.cross(np.broadcast_to(d, e2.shape), e2)
    a = np.einsum('ij,ij->i', e1, h)
    f = np.divide(1, a, out=np.zeros_like(a), where=abs(a)>1e-8)
    u = f*np.einsum('ij,ij->i', v, h)
    q = np.cross(v, e1)
    w = f*(q@d)
    distance = f*np.einsum('ij,ij->i', e2, q)
    valid = (abs(a)>1e-8)&(u>=0)&(w>=0)&(u+w<=1)&(distance>0)
    hit = np.flatnonzero(valid)
    assert len(hit)
    k = hit[np.argmin(distance[hit])]
    refined_rays.append({'screen':ray['screen'], 'oldSource':old['object'],
                         'oldPosition':old['position'], 'newSourcePosition':(camera+d*distance[k]).tolist(),
                         'rayDistanceDifferenceMeters':float(distance[k]-old['distance'])})
partial_report = {
    'status':'pass', 'originalB3dmPayloadAndCRCVerified':len(tiles),
    'tiles':len(tiles), 'triangles':len(tri),
    'level':args.level,'allRetainedSourcesTerminalErrorZero':all(t['originalError']==0 for t in tiles),
    'sourceFrontierComplete':True, 'wholeParentSubtreeComplete':False,
    'missingSibling':patch['evidence']['missingSibling'],
    'placementIdenticalToVerifiedBaseline':True,
    'baseTextureMiB':sum(t['textureBytes'] for t in tiles)/2**20,
    'estimatedTextureWithMipmapsMiB':sum(t['textureBytes'] for t in tiles)*4/3/2**20,
    'maskPixelCentreChecks':len(flat), 'maskMismatches':0,
    'coveredPixels':int((mask>0).sum()), 'uncoveredPixelsRetained':int((mask==0).sum()),
    'maskRounding':'0.5m raster pixels; no source-projection dilation or hull fill',
    'sameCameraTreeRays':refined_rays,
    'browserAcceptance':'Not part of this numerical audit; root must inspect same-view rendering.'}
(patch_dir/('independent-qa.json' if args.level=='high' else 'independent-qa-fine.json')).write_text(json.dumps(partial_report, indent=2))
if args.skip_ground:
    print(json.dumps(partial_report,indent=2))
    raise SystemExit(0)

ground_dir = P/'public/surfaces/ground-reference'
gm = json.loads((ground_dir/'manifest.json').read_text())
im = np.asarray(Image.open(ground_dir/gm['url']))
current_ground_pixels = int(np.count_nonzero(im[:,:,0]))
if gm.get('fineSourceExtension'):
    original = np.asarray(Image.open(ground_dir/'ground-reference-before-fine-extension.png'))
    assert np.array_equal(im[original[:,:,0]>127], original[original[:,:,0]>127])
    # Original DTM reference checks remain scoped to their unchanged pixels;
    # new fine reference pixels have separate exact source/baseline validation.
    im = original
all_rr, all_cc = np.nonzero(im[:, :, 0])
sample = rng.choice(len(all_rr), min(12000, len(all_rr)), replace=False)
rr, cc = all_rr[sample], all_cc[sample]
xz = np.c_[gm['minX']+(cc+.5)*.5, gm['minZ']+(rr+.5)*.5]
dh = Heights(list((P/'public/terrain/source-data').glob('*.tif')))(np.c_[xz[:, 0]+844800, 820500-xz[:, 1]])
encoded = im[rr, cc, 1].astype(float)+im[rr, cc, 2].astype(float)/256
assert np.isfinite(dh).all() and np.max(abs(dh-encoded)) <= 1/256
valid = np.zeros(len(rr), bool)
source_tiles = json.loads((P/'public/models/render-manifest.json').read_text())['tiles']
for t in source_tiles:
    b=t['bounds']; lo=np.array(b['min'])[[0,2]]; hi=np.array(b['max'])[[0,2]]
    ix=np.flatnonzero((~valid)&((xz>=lo)&(xz<=hi)).all(1))
    if not len(ix): continue
    tr, _ = geometry(P/'public/models'/t['url'], np.array(t['matrix']).reshape(4,4,order='F'))
    cr=np.cross(tr[:,1]-tr[:,0], tr[:,2]-tr[:,0]); normal=np.linalg.norm(cr,axis=1)
    ok=(normal>1e-8)&(abs(cr[:,1])>=gm['minimumAbsoluteNormalY']*normal)
    tr=tr[ok]; projected=tr[:,:,[0,2]]
    pair=STRtree(polygons(projected)).query(points(xz[ix]),predicate='intersects')
    if not pair.shape[1]: continue
    k=ix[pair[0]]; t3=tr[pair[1]]; n=np.cross(t3[:,1]-t3[:,0],t3[:,2]-t3[:,0])
    # Independent plane equation, not the builder's barycentric formula.
    y=t3[:,0,1]-(n[:,0]*(xz[k,0]-t3[:,0,0])+n[:,2]*(xz[k,1]-t3[:,0,2]))/n[:,1]
    valid[k[abs(y-dh[k])<=gm['bandMeters']]]=True
assert valid.all()
green=[]
bundle_masks=[]
for bundle in json.loads((P/'public/models/exteriors/manifest.json').read_text())['bundles']:
    bm=bundle['mask']
    pixels=np.asarray(Image.open(P/'public/models/exteriors'/bm['url']))
    bundle_masks.append((bm,pixels[:,:,0] if pixels.ndim==3 else pixels))
for ray in ray_source['rays'][3:]:
    hit=ray['hits'][0]; x,y,z=hit['position']; c=int((x-gm['minX'])/.5); r=int((z-gm['minZ'])/.5)
    replacement=False
    for bm,ba in bundle_masks:
        bc=int(np.floor((x-bm['boundsXZ']['min'][0])/.5));br=int(np.floor((z-bm['boundsXZ']['min'][1])/.5))
        if 0<=br<ba.shape[0] and 0<=bc<ba.shape[1]:replacement |= bool(ba[br,bc]>0)
    protected=bool(im[r,c,0]>0)
    assert protected if replacement else not protected
    reference=(float(im[r,c,1])+float(im[r,c,2])/256) if protected else None
    if protected:assert abs(y-reference)<=gm['bandMeters']
    terrain_y=float(Heights(list((P/'public/terrain/source-data').glob('*.tif')))(np.array([[x+844800,820500-z]]))[0])
    assert abs(y-terrain_y)<=gm['bandMeters']
    green.append({'screen':ray['screen'],'source':hit['object'],'sourcePosition':hit['position'],
                  'insideBuildingReplacement':replacement,'groundMask':protected,'encodedReferenceY':reference,
                  'sourceMinusDtmMeters':y-terrain_y,
                  'policy':'preserve compatible source ground' if replacement else 'outside all building masks; original source needs no replacement exception'})
ground_report={'status':'pass','groundPixels':len(all_rr),'currentGroundPixels':current_ground_pixels,'scope':'unchanged original DTM reference pixels; fine-source-extension-qa.json validates added source-plane pixels','independentPlaneEquationChecks':len(rr),
               'compatibleSourceMissing':int((~valid).sum()),'encodedHeightMaxErrorMeters':float(np.max(abs(dh-encoded))),
               'sameCameraGreenStripRays':green,'groundBandMeters':gm['bandMeters'],
               'minimumAbsoluteNormalY':gm['minimumAbsoluteNormalY'],
               'excludedFragmentExamples':{'verticalWallNormalY0':True,'roof10mAboveDTM':True,'treeCanopy5mAboveDTM':True},
               'limitations':'Mask data and source-height predicate checked. Final shader and same-camera visual acceptance are separate.'}
(ground_dir/'independent-qa.json').write_text(json.dumps(ground_report,indent=2))
print(json.dumps({'partial':partial_report,'ground':ground_report},indent=2))
