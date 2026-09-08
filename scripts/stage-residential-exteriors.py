#!/usr/bin/env python3
"""Prepare verified complete original residential objects without touching live assets.
Run without flags to write /tmp/hkust-v6-next-exteriors and audit evidence only.
"""
import hashlib, json, shutil
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
from hkust_source_geometry import geometry

P=Path(__file__).resolve().parents[1]
S=Path('/tmp/hkust-hires-geodata/individualised-source')
D=Path('/tmp/hkust-v6-next-exteriors');D.mkdir(parents=True,exist_ok=True)
O=P/'docs/source-evidence-v4/building-quality'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
domains=read(P/'public/data/picking/building-domains.json')['domains']
projection={o['id']:o for o in read(O/'identity-sources/source-object-projections.json')}
GROUPS=[('campus-35','Jockey Club Global Graduate Tower',['B454352166201063A0','B454362166402062A0']),
    ('ug-hall-4','UG Hall IV',['B455782197701063A0']),
    ('ug-hall-5','UG Hall V',['B453562211501063A0']),
    ('ug-hall-7','UG Hall VII',['B454662211901063A0','B454902208402063A0'])]

def mips(w,h):
    total=0
    while True:
        total+=w*h*4
        if w==h==1:return total
        w=max(1,w//2);h=max(1,h//2)

bundles=[];reports=[]
for cid,name,ids in GROUPS:
    ds=[d for d in domains if d['entityId']=='building:catalog:'+cid]
    domain=unary_union([Polygon(p['rings'][0],p['rings'][1:])for d in ds for p in d['parts']])
    projected=unary_union([shape(projection[oid]['sourceProjection'])for oid in ids])
    intersection=domain.intersection(projected).area
    assert intersection/domain.area>.97
    objects=[];triangles=[];files_checked=0
    for oid in ids:
        sm=read(S/'buildings'/oid/'manifest.json');source=S/'buildings'/oid;target=D/'objects'/oid;target.mkdir(parents=True,exist_ok=True)
        for item in sm['files']:
            assert sha(source/item['filename'])==item['sha256']
            shutil.copy2(source/item['filename'],target/item['filename'])
            assert sha(target/item['filename'])==item['sha256'];files_checked+=1
        shutil.copy2(source/'manifest.json',target/'source-manifest.json')
        matrix=np.eye(4);matrix[:3,3]=[-844800,0,820500]
        tri,_=geometry(target/(oid+'.gltf'),matrix);triangles.append(tri);lo=tri.min((0,1));hi=tri.max((0,1))
        textures=sm['geometry']['textures'];dimensions=[t['dimensions_pixels']for t in textures]
        objects.append({'id':oid,'url':f'objects/{oid}/{oid}.gltf','offset':[-844800,0,820500],
            'bounds':{'min':lo.tolist(),'max':hi.tolist()},'triangles':len(tri),
            'textureDecodedBytes':sum(w*h*4 for w,h in dimensions),'textureMipBytes':sum(mips(w,h)for w,h in dimensions),
            'textureDimensions':dimensions,'textureMaxDimension':max(max(d)for d in dimensions),
            'textureFiles':[{'url':f'objects/{oid}/{t["uri"]}','width':t['dimensions_pixels'][0],'height':t['dimensions_pixels'][1],
                'decodedBytes':t['dimensions_pixels'][0]*t['dimensions_pixels'][1]*4}for t in textures],
            'assetBytes':sm['file_bytes'],'sourceManifest':f'objects/{oid}/source-manifest.json',
            'sourceUrl':sm['source_archive_uri'],'gltfSha256':sha(target/(oid+'.gltf')),
            'sourceLevelCode':sm['level_code'],'partName':None,'partNameNote':'Original object ID retained; source-supported upper/lower or adjacent body role recorded in group QA only.'})
    tri=np.concatenate(triangles);lo=tri.min((0,1));hi=tri.max((0,1));x0,z0=np.floor(lo[[0,2]])-1;x1,z1=np.ceil(hi[[0,2]])+1
    width=int((x1-x0)*2);height=int((z1-z0)*2)
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);xz=tri[abs(cross[:,1])>1e-9][:,:,[0,2]]
    array=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in xz),
        out_shape=(height,width),transform=Affine(.5,0,x0,0,.5,z0),dtype='uint8',all_touched=False)
    (D/'masks').mkdir(exist_ok=True);exact=D/'masks'/(cid+'.exact.png');image=D/'masks'/(cid+'.png')
    Image.fromarray(array).save(exact);Image.fromarray(array).filter(ImageFilter.MaxFilter(3)).save(image)
    mask={'url':f'masks/{cid}.png','exactUrl':f'masks/{cid}.exact.png',
        'boundsXZ':{'min':[float(x0),float(z0)],'max':[float(x1),float(z1)]},'width':width,'height':height,
        'metersPerPixel':.5,'channel':'red','occupiedValue':255,'emptyValue':0,'rowDirection':'z-increasing','textureFlipY':False,
        'heightMin':float(lo[1]-.5),'heightMax':float(hi[1]+5),'dilationMeters':.5,
        'source':'Union of actual complete source object triangle projections. .5m rendering guard supplied separately from exact projection; not a footprint mask.',
        'sha256':sha(image)}
    parts=[]
    for obj in objects:
        geom=shape(projection[obj['id']]['sourceProjection']);inter=geom.intersection(domain).area
        parts.append({'sourceObjectId':obj['id'],'sourceLevelCode':obj['sourceLevelCode'],
            'bounds':obj['bounds'],'sourceInsideDomainRatio':inter/geom.area,'domainCoveredRatio':inter/domain.area})
    pair_overlap=[]
    for i,a in enumerate(objects):
        for b in objects[i+1:]:
            pair_overlap.append({'a':a['id'],'b':b['id'],'projectionIntersectionM2':shape(projection[a['id']]['sourceProjection']).intersection(shape(projection[b['id']]['sourceProjection'])).area,
                'verticalSpanOverlapMeters':max(0,min(a['bounds']['max'][1],b['bounds']['max'][1])-max(a['bounds']['min'][1],b['bounds']['min'][1]))})
    evidence={'officialSource':'public/data/picking/building-domains.json',
        'officialBuildingIds':[d['sourceBuildingId']for d in ds],
        'officialAnnotationNames':[d['annotation']['TextString']for d in ds],
        'sourceProjectionInsideOfficialRatio':intersection/projected.area,'officialDrawingCoveredRatio':intersection/domain.area,
        'componentPolicy':'Each complete original object retained, never a selection of triangles/textures. GGT components occupy complementary vertical spans; HallVII components are adjacent with0.622m2 projection overlap.',
        'sourceParts':parts,'pairOverlap':pair_overlap}
    bundle={'id':cid,'buildingId':'catalog:'+cid,'buildingName':name,'catalogIds':[cid],'objects':objects,
        'bounds':{'min':lo.tolist(),'max':hi.tolist()},'center':((lo+hi)/2).tolist(),'mask':mask,
        'textureDecodedBytes':sum(o['textureDecodedBytes']for o in objects),'textureMipBytes':sum(o['textureMipBytes']for o in objects),
        'triangles':len(tri),'assetBytes':sum(o['assetBytes']for o in objects),'matchEvidence':evidence,
        'sourceDates':{'tileRevision':'2026-04-24','captureDate':None,'checkedAt':'2026-09-06'},
        'replacement':{'atomic':True,'keepPreviousUntilAllObjectsAndTexturesReady':True,'fallback':'Entire source group falls back; no partial object or texture commit.'}}
    bundles.append(bundle)
    reports.append({'canonicalId':'building:catalog:'+cid,'name':name,'sourceObjects':ids,
        'originalFilesShaVerified':files_checked,'originalGeometryUVTexturesNodesUnchanged':True,
        'triangles':len(tri),'textureMipMiB':bundle['textureMipBytes']/2**20,
        'officialDrawingCoveredRatio':intersection/domain.area,'sourceInsideDomainRatio':intersection/projected.area,
        'sourceParts':parts,'pairOverlap':pair_overlap,'iB1000OriginalBaseRoof':[
            {'buildingId':d['sourceBuildingId'],'base':d['minY'],'roof':d['maxY']}for d in ds],
        'heightPolicy':'Keep native source heights unchanged. iB1000 source roofs and original3D model extrema differ; no claimed surveyed roof or forced vertical rescaling.',
        'browserAppearanceAcceptance':'pending'})
(D/'manifest.json').write_text(json.dumps({'version':1,'bundles':bundles},ensure_ascii=False,indent=2)+'\n')
(O/'residential-exteriors-staging.json').write_text(json.dumps({'status':'staged-not-live','stagingDirectory':str(D),'groups':reports,
    'geometrySource':'Original government individualised glTF files already downloaded; revision2026-04-24 is not capture date.',
    'sourceGroupBoundary':'These are complete available source objects associated by exact official named domains and actual projected geometry. No assumption of2026 measured facade completeness.'},ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{k:r[k]for k in ['name','sourceObjects','triangles','textureMipMiB','officialDrawingCoveredRatio']}for r in reports],ensure_ascii=False,indent=2))
