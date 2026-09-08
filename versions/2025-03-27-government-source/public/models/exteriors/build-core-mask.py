"""Add Academic source-core coverage in G; preserve complete bundle coverage in R.
Run: python build-core-mask.py --project PROJECT. Requires NumPy and Pillow.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageChops,ImageFilter

STEP=.5; X0=240; Z0=-1740; W=1520; H=1640

def triangles(path,offset):
 g=json.loads(path.read_text());buffers=[(path.parent/b['uri']).read_bytes()for b in g['buffers']]
 def acc(i):
  a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];d=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]);w={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']]
  return np.ndarray((a['count'],w),d,buffers[v.get('buffer',0)],v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',w*d.itemsize),d.itemsize))
 out=[]
 def walk(i,parent):
  node=g['nodes'][i];assert not any(k in node for k in ['translation','rotation','scale']);local=np.array(node.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F');m=parent@local
  if 'mesh'in node:
   for pr in g['meshes'][node['mesh']]['primitives']:
    assert pr.get('mode',4)==4;points=acc(pr['attributes']['POSITION']).astype('f8');world=np.column_stack([points[:,0]*m[k,0]+points[:,1]*m[k,1]+points[:,2]*m[k,2]+m[k,3]+offset[k]for k in range(3)]);ix=acc(pr['indices']).reshape(-1,3)if'indices'in pr else np.arange(len(points)).reshape(-1,3);out.append(world[ix])
  for child in node.get('children',[]):walk(child,m)
 for root in g['scenes'][g.get('scene',0)]['nodes']:walk(root,np.eye(4))
 return np.concatenate(out)

def build(project):
 base=project/'public/models/exteriors';manifest_path=base/'manifest.json';manifest=json.loads(manifest_path.read_text());bundle=next(b for b in manifest['bundles']if b['id']=='campus-01');mask=bundle['mask'];objects=[o for o in bundle['objects']if not o['id'].startswith('academic-gap/')];assert len(objects)==9 and len(bundle['objects'])==37
 core=Image.new('1',(W,H));objects_report=[]
 for obj in objects:
  src=base/obj['url'];raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()==obj['gltfSha256'];tr=triangles(src,obj['offset']);assert np.isfinite(tr).all();xz=tr[:,:,[0,2]];area=np.abs((xz[:,1,0]-xz[:,0,0])*(xz[:,2,1]-xz[:,0,1])-(xz[:,1,1]-xz[:,0,1])*(xz[:,2,0]-xz[:,0,0]))*.5
  layer=Image.new('1',(W,H));draw=ImageDraw.Draw(layer)
  for tri in xz[area>.0025]:draw.polygon([((x-X0)/STEP,(z-Z0)/STEP)for x,z in tri],fill=1)
  old=Path('/tmp/hkust-v3-exteriors')/(obj['id']+'-projection.png');same=bool(np.array_equal(np.array(layer),np.array(Image.open(old))))if old.exists()else None
  difference=int(np.count_nonzero(np.array(layer)!=np.array(Image.open(old)))) if old.exists() else None
  boundaryOnly=None
  if same is False:
   previous=np.array(Image.open(old).convert('L'));current=np.array(layer.convert('L'));previousGuard=np.array(Image.fromarray(previous).filter(ImageFilter.MaxFilter(3)));currentGuard=np.array(Image.fromarray(current).filter(ImageFilter.MaxFilter(3)));boundaryOnly=bool(np.all(current<=previousGuard)and np.all(previous<=currentGuard));assert boundaryOnly,'Source projection mismatch exceeds one pixel raster boundary.'
  core=ImageChops.lighter(core,layer);objects_report.append({'id':obj['id'],'triangles':len(tr),'projectedTriangles':int((area>.0025).sum()),'sourceGltfSha256':obj['gltfSha256'],'retainedProjectionPixels':int(np.array(layer).sum()),'matchesPreviouslyPreservedProjection':same,'preservedRasterDifferencePixels':difference,'differencesWithinOnePixelBoundary':boundaryOnly})
 left=round((mask['boundsXZ']['min'][0]-X0)/STEP);top=round((mask['boundsXZ']['min'][1]-Z0)/STEP);box=(left,top,left+mask['width'],top+mask['height']);exact=core.crop(box).convert('L');guard=exact.filter(ImageFilter.MaxFilter(3));report={'pass':True,'objects':objects_report,'coreObjectCount':9,'bundleObjectCount':37,'maskSize':[mask['width'],mask['height']],'maskBoundsXZ':mask['boundsXZ'],'channels':{},'textureDecodedBytesUnchanged':bundle['textureDecodedBytes'],'trianglesUnchanged':bundle['triangles'],'maskDecodedBytesUnchanged':mask['width']*mask['height']*4,'projectionMethod':'Same original 0.5m source triangle raster, projected area >0.0025m2, source matrices once plus outer offset. G exact is nine source object union; G guard adds one pixel like existing R. No AABB/convex hull fill. R remains immutable; any regenerated G boundary pixel outside existing R is clipped to R. Preserved prior core rasters are independently compared, with any difference limited to one raster-boundary pixel.'}
 for role,url,green in [('guard',mask['url'],guard),('exact',mask['exactUrl'],exact)]:
  path=base/url;before=Image.open(path).convert('RGB');red=np.array(before)[:,:,0];g=np.array(green);assert red.shape==g.shape;clamped=int(np.count_nonzero(g>red));g=np.minimum(g,red);assert np.all(g<=red)
  rgba=np.stack([red,g,np.zeros_like(red),np.full_like(red,255)],axis=-1);Image.fromarray(rgba,'RGBA').save(path);after=np.array(Image.open(path));assert np.array_equal(after[:,:,0],red)
  report['channels'][role]={'redPixels':int((red>127).sum()),'greenPixels':int((g>127).sum()),'supplementOnlyPixels':int(((red>127)&(g<=127)).sum()),'redBytewiseUnchanged':True,'greenSubsetRed':True,'coreBoundaryPixelsClampedToUnchangedCompleteMask':clamped,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 mask.update(hasCoreMask=True,coreChannel='green',coreObjectIds=[o['id']for o in objects],channels={'red':'Complete bundle actual source coverage: nine individualised core objects plus28 photogrammetry gap surfaces.','green':'Only the nine original individualised source objects; same projection grid and guard.','blue':'unused (zero)','alpha':'opaque'},sha256=report['channels']['guard']['sha256'],exactSha256=report['channels']['exact']['sha256'],coreMaskEvidence='core-mask-validation.json')
 mask['source']='R retains complete original bundle source coverage. G is union of9 original individualised model projections only; actual triangle geometry, not bounding boxes. See core-mask-validation.json.'
 for obj in objects:obj['objectRole']='source-individualised-core'
 manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');(base/'core-mask-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[3]);args=parser.parse_args();r=build(args.project);print(json.dumps({k:v for k,v in r.items()if k!='objects'},indent=2))
