#!/usr/bin/env python3
"""Install complete original LOD3A objects for source-verified Towers A and B.
Original glTF, nodes, geometry, UVs and image files are copied byte-for-byte.
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
D=P/'public/models/exteriors'
O=P/'docs/source-evidence-v4/building-quality'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
domains=read(P/'public/data/picking/building-domains.json')['domains']
projection=read(O/'identity-sources/source-object-projections.json')
original=read(D/'manifest.json')
report=[]
for cid,oid,name in [('campus-32','B453202172901063A0','Tsang Chiu Sang Tower'),('campus-33','B453352178701063A0','Lam Po Yu Tower')]:
    source=S/'buildings'/oid;sm=read(source/'manifest.json')
    assert sm['level_code']=='3A' and sm['all_references_present']
    target=D/'objects'/oid;target.mkdir(parents=True,exist_ok=True)
    for item in sm['files']:
        path=source/item['filename'];assert sha(path)==item['sha256']
        shutil.copy2(path,target/item['filename']);assert sha(target/item['filename'])==item['sha256']
    shutil.copy2(source/'manifest.json',target/'source-manifest.json')
    matrix=np.eye(4);matrix[:3,3]=[-844800,0,820500]
    tri,_=geometry(target/(oid+'.gltf'),matrix);lo=tri.min((0,1));hi=tri.max((0,1))
    assert len(tri)==sm['geometry']['triangle_count']
    ds=[d for d in domains if d['entityId']=='building:catalog:'+cid]
    domain=unary_union([Polygon(p['rings'][0],p['rings'][1:])for d in ds for p in d['parts']])
    source_projection=shape(next(q for q in projection if q['id']==oid)['sourceProjection'])
    intersection=source_projection.intersection(domain).area
    assert intersection/source_projection.area>.94 and intersection/domain.area>.88
    x0,z0=np.floor(lo[[0,2]])-1;x1,z1=np.ceil(hi[[0,2]])+1
    width=int((x1-x0)*2);height=int((z1-z0)*2)
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);xz=tri[abs(cross[:,1])>1e-9][:,:,[0,2]]
    array=rasterize((({'type':'Polygon','coordinates':[[*t.tolist(),t[0].tolist()]]},255)for t in xz),
        out_shape=(height,width),transform=Affine(.5,0,x0,0,.5,z0),dtype='uint8',all_touched=False)
    exact=D/'masks'/(cid+'.exact.png');mask_path=D/'masks'/(cid+'.png')
    Image.fromarray(array).save(exact);Image.fromarray(array).filter(ImageFilter.MaxFilter(3)).save(mask_path)
    textures=sm['geometry']['textures'];dimensions=[t['dimensions_pixels']for t in textures]
    base_bytes=sum(w*h*4 for w,h in dimensions)
    obj={'id':oid,'url':f'objects/{oid}/{oid}.gltf','offset':[-844800,0,820500],
        'bounds':{'min':lo.tolist(),'max':hi.tolist()},'triangles':len(tri),'textureDecodedBytes':base_bytes,
        'textureDimensions':dimensions,'textureMaxDimension':max(max(d)for d in dimensions),
        'textureFiles':[{'url':f'objects/{oid}/{t["uri"]}','width':t['dimensions_pixels'][0],'height':t['dimensions_pixels'][1],
            'decodedBytes':t['dimensions_pixels'][0]*t['dimensions_pixels'][1]*4}for t in textures],
        'assetBytes':sm['file_bytes'],'sourceManifest':f'objects/{oid}/source-manifest.json','sourceUrl':sm['source_archive_uri'],
        'gltfSha256':sha(target/(oid+'.gltf')),'sourceLevelCode':'3A','partName':name,
        'partNameNote':'Official named BuildingAnno anchor inside exact Building polygon, uniquely coincident with the full original government source object. Name is not inferred from .att family ID.'}
    mask={'url':f'masks/{cid}.png','exactUrl':f'masks/{cid}.exact.png','boundsXZ':{'min':[float(x0),float(z0)],'max':[float(x1),float(z1)]},
        'width':width,'height':height,'metersPerPixel':.5,'channel':'red','occupiedValue':255,'emptyValue':0,'rowDirection':'z-increasing','textureFlipY':False,
        'heightMin':float(lo[1]-.5),'heightMax':float(hi[1]+5),'dilationMeters':.5,
        'source':'Actual complete source triangle projection; .5m rendering guard retained separately from exact projection. No footprint/bbox replacement.',
        'sha256':sha(mask_path)}
    bundle={'id':cid,'buildingId':'catalog:'+cid,'buildingName':name,'catalogIds':[cid],'objects':[obj],
        'bounds':obj['bounds'],'center':((lo+hi)/2).tolist(),'mask':mask,'textureDecodedBytes':base_bytes,'triangles':len(tri),'assetBytes':sm['file_bytes'],
        'matchEvidence':{'officialSource':'public/data/picking/building-domains.json','officialBuildingIds':[d['sourceBuildingId']for d in ds],
            'officialAnnotationNames':[d['annotation']['TextString']for d in ds],
            'sourceProjectionInsideOfficialRatio':intersection/source_projection.area,'officialDrawingCoveredRatio':intersection/domain.area,
            'fullSourceObjectRetained':True,'uncoveredDomainPolicy':'Original source/baseline remains outside the actual projection; no invented annex or planar infill.',
            'nameEvidence':'Official 2025 naming evidence identifies Tower A as Tsang Chiu Sang Tower and Tower B as Lam Po Yu Tower; saved official BuildingAnno independently fixes each A/B geographic domain.'},
        'sourceDates':{'tileRevision':sm['source_tile_revision_date'],'captureDate':sm['capture_date'],'checkedAt':'2026-09-06'},
        'replacement':{'atomic':True,'keepPreviousUntilAllObjectsAndTexturesReady':True,'fallback':'Entire source group remains baseline if unsuccessful; no partial object or texture commit.'}}
    original['bundles']=[b for b in original['bundles']if b['id']!=cid]+[bundle]
    original['unassignedObjectIds']=[i for i in original.get('unassignedObjectIds',[])if i!=oid]
    report.append({'canonicalId':'building:catalog:'+cid,'name':name,'sourceObjectId':oid,'triangles':len(tri),
        'originalFilesHashVerified':len(sm['files']),'originalGeometryUVImagesAndNodesUnchanged':True,
        'sourceProjectionInsideOfficialRatio':intersection/source_projection.area,'officialDrawingCoveredRatio':intersection/domain.area,
        'textureDimensions':dimensions,'baseTextureMiB':base_bytes/2**20,'maskBoundsXZ':mask['boundsXZ'],
        'maskPixelSizeMeters':.5,'exactProjectionPixels':int((array>0).sum()),'independentBrowserAppearanceAcceptance':'pending'} )
temporary=D/'manifest.next.json';temporary.write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n');temporary.replace(D/'manifest.json')
(O/'tower-ab-source-exterior-stage.json').write_text(json.dumps({'status':'source-installed-for-browser-qa','buildings':report,
    'sourceEraLimit':'Original government single-object LOD3A models, revision2026-04-24; capture date unknown. Full-source byte preservation does not establish all2026 rooftop details.'},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
