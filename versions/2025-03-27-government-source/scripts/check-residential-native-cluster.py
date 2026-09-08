#!/usr/bin/env python3
"""Independent local source/CRC, per-triangle attributes and mask validation.
No browser acceptance is implied. Requires numpy, Pillow, shapely.
"""
import argparse,hashlib,importlib.util,json,struct,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import STRtree,points,polygons
from hkust_source_geometry import geometry
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args();P=args.project;D=P/'public/models/hires/partial-residential-ias';patch=json.loads((D/'manifest.json').read_text())['patches'][0];tiles=patch['levels']['high']['tiles'];assert len(tiles)==123 and patch['partial']and not patch['evidence']['completeParentSubtrees'];base={t['id']:t for t in json.loads((P/'public/models/render-manifest.json').read_text())['tiles']};source_data=json.loads((P/'public/models/hires/partial-ug10/branch-audit.json').read_text());assert sum(len(t['missingDirectSiblings'])for t in source_data['subtrees'])==4
for source in source_data['subtrees']:
 folder=P/'source-geodata/mesh'/source['sheet'];original_tree=json.loads((folder/source['subtree']/'source-tileset.json').read_text());index=json.loads((folder/'source-zip-index.json').read_text());assert original_tree['root']['transform']==source['sourceRootTransform']
 def check_node(n,is_root=False):
  assert is_root or 'transform'not in n,'Unexpected descendant transform requires independent placement derivation.'
  for child in n.get('children',[]):check_node(child)
 check_node(original_tree['root'],True)
 assert all(missing['sourceName']not in index for missing in source['missingDirectSiblings'])
helper=P/'public/models/source-corrections/ug10-isolated-photogrammetry-fragment-9/validate_correction.py';spec=importlib.util.spec_from_file_location('attributes',helper);attrs=importlib.util.module_from_spec(spec);spec.loader.exec_module(attrs);tris=[];corrected=[]
for t in tiles:
 path=P/'public/models/hires'/t['url'];b3dm=(P/t['sourceB3dmRelativePath'] if t.get('sourceB3dmRelativePath') else Path(t['sourceB3dmCachePath'])).read_bytes();head=struct.unpack_from('<4s6I',b3dm);assert head[0]==b'b3dm'and head[2]==len(b3dm);raw=b3dm[28+sum(head[3:]):];assert zlib.crc32(b3dm)==t['sourceZipCRC32']and hashlib.sha256(b3dm).hexdigest()==t['sourceB3dmSha256'];assert hashlib.sha256(path.read_bytes()).hexdigest()==t['sha256'];assert t['originalError']==0 and t['matrix']==base[t['matrixSourceBaselineId']]['matrix']
 correction=t.get('sourceCorrection')
 if correction:
  original=P/'public/models/hires'/correction['originalUrl'];assert raw==original.read_bytes()and hashlib.sha256(raw).hexdigest()==correction['originalSha256'];g,aa,images=attrs.decode(original);ng,bb,nimages=attrs.decode(path);assert g['nodes']==ng['nodes']and g['materials']==ng['materials']and g['textures']==ng['textures']and images==nimages
  for name in ['POSITION','TEXCOORD_0']:
   a=np.concatenate([v[name]for v in aa]);b=np.concatenate([v[name]for v in bb]);assert np.array_equal(np.delete(a,correction['removedTriangleIndices'],axis=0),b)
  corrected.append({'id':t['id'],'removedTriangles':len(correction['removedTriangleIndices']),'retainedPositionUVExact':True,'imagesMaterialsAndNodesUnchanged':True})
 else:assert raw==path.read_bytes()
 tri,_=geometry(path,np.array(t['matrix']).reshape(4,4,order='F'));assert np.isfinite(tri).all()and len(tri)==t['triangles'];tris.append(tri)
tri=np.concatenate(tris);m=patch['mask'];image=np.asarray(Image.open(P/'public/models/hires'/m['url']));assert image.shape==(m['height'],m['width']);assert m['pixelSizeMeters']==.5 and all(float(m[k]*2).is_integer()for k in ['minX','minZ','maxX','maxZ']);assert hashlib.sha256((P/'public/models/hires'/m['url']).read_bytes()).hexdigest()==m['sha256']
rng=np.random.default_rng(20260906);flat=np.unique(np.r_[np.flatnonzero(image.ravel()==0),rng.choice(image.size,40000,replace=False)]);rr,cc=np.unravel_index(flat,image.shape);xz=np.c_[m['minX']+(cc+.5)*.5,m['minZ']+(rr+.5)*.5];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);tree=STRtree(polygons(tri[abs(cross[:,1])>1e-9][:,:,[0,2]]));pairs=tree.query(points(xz),predicate='intersects');expected=np.zeros(len(flat),bool);expected[pairs[0]]=True;assert np.array_equal(expected,image[rr,cc]>0)
# Independent direct fragment-volume rejection: check only, never a deletion predicate.
fragment_bounds=[([624.48,186.88,-1100.36],[628.96,193.81,-1097.07]),([736.72,186.55,-1100.36],[741.62,192.04,-1095.69])];tl=tri.min(1);th=tri.max(1);checks=[]
for lo,hi in fragment_bounds:
 hit=np.all(tl<=np.array(hi)+.001,axis=1)&np.all(th>=np.array(lo)-.001,axis=1);assert not hit.any();checks.append({'min':lo,'max':hi,'intersectingNewTriangles':0})
report={'status':'pass','tiles':len(tiles),'sourceTrianglesBeforeCorrection':len(tri)+sum(c['removedTriangles']for c in corrected),'retainedTriangles':len(tri),'correctedSourceComponents':corrected,'removedTriangles':sum(c['removedTriangles']for c in corrected),'sourcePayloadCRCAndEmbeddedOriginalGLBVerified':len(tiles),'sourceMatricesIdenticalToVerifiedBaseline':True,'allSelectedSourcesTerminalErrorZero':True,'wholeFourParentSubtreesComplete':False,'knownMissingSiblingRequests':0,'maskPixelCentreChecks':len(flat),'maskMismatches':0,'maskOccupiedPixels':int((image>0).sum()),'maskUncoveredPixelsRetained':int((image==0).sum()),'baseTextureMiB':sum(t['textureBytes']for t in tiles)/2**20,'exactTextureMipMiB':sum(t['textureMipBytes']for t in tiles)/2**20,'maskRgbaMiB':image.size*4/2**20,'knownFragmentsNotReintroduced':checks,'browserAcceptance':'Not part of this numerical source audit.'};(D/'independent-qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
