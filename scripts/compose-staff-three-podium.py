#!/usr/bin/env python3
"""Complete Staff3 with its original complementary low body, retained once.

The low object's whole original geometry/texture is preserved but has domain-only
picking ownership: the large terrace outside the named tower must not be assigned
to Staff3 or4 by source-object proximity. No live assets or registry are changed.
"""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import Point,Polygon,mapping
from shapely.ops import unary_union
from hkust_source_geometry import geometry

P=Path(__file__).resolve().parents[1]
D=Path('/tmp/hkust-v7-northern-exteriors/staff-3-4')
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(D/'manifest.json')
bundle=next(b for b in manifest['bundles']if b['id']=='staff-quarters-tower-3')
other=next(b for b in manifest['bundles']if b['id']=='staff-quarters-tower-4')
oid='B452822226202062A0';directory=D/'objects'/oid
candidate=next(c for c in read(P/'docs/source-evidence-v4/building-quality/northern-individual-source-candidates.json')['candidates']if c['id']==oid)
files=[f for f in read(D/'source-downloads.json')['files']if f['sourceObjectId']==oid]
assert len(files)==len(candidate['files'])
for item in files:assert sha(directory/item['filename'])==item['sha256']
gltf=read(directory/(oid+'.gltf'));dimensions=[]
for image in gltf['images']:
    with Image.open(directory/image['uri'])as decoded:dimensions.append(list(decoded.size));decoded.verify()
matrix=np.eye(4);matrix[:3,3]=[-844800,0,820500]
low,_=geometry(directory/(oid+'.gltf'),matrix)
upper,_=geometry(D/bundle['objects'][0]['url'],matrix)
adjacent,_=geometry(D/other['objects'][0]['url'],matrix)
def projection(triangles):
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    return unary_union([Polygon(t[:,[0,2]])for t in triangles[abs(normal[:,1])>1e-9]])
def mips(w,h):
    total=0
    while True:
        total+=w*h*4
        if w==h==1:return total
        w,h=max(1,w//2),max(1,h//2)
lo,hi=low.min((0,1)),low.max((0,1))
source={'id':oid,'level_code':'2A','source_archive_uri':candidate['url'],'source_sheet':candidate['sheet'],
    'source_revision_date':'2025-03-27','capture_date':None,'files':files,
    'file_bytes':sum(f['bytes']for f in files),'original_nodes':gltf['nodes'],
    'geometry':{'textures':[{'uri':img['uri'],'dimensions_pixels':dimensions[i]}for i,img in enumerate(gltf['images'])],'triangles':len(low)}}
(directory/'source-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
obj={'id':oid,'url':f'objects/{oid}/{oid}.gltf','offset':[-844800,0,820500],
    'bounds':{'min':lo.tolist(),'max':hi.tolist()},'triangles':len(low),
    'textureDecodedBytes':sum(w*h*4 for w,h in dimensions),'textureMipBytes':sum(mips(w,h)for w,h in dimensions),
    'textureDimensions':dimensions,'textureMaxDimension':max(max(d)for d in dimensions),
    'textureFiles':[{'url':f'objects/{oid}/{image["uri"]}','width':dimensions[i][0],'height':dimensions[i][1],
        'decodedBytes':dimensions[i][0]*dimensions[i][1]*4}for i,image in enumerate(gltf['images'])],
    'assetBytes':source['file_bytes'],'sourceManifest':f'objects/{oid}/source-manifest.json',
    'sourceUrl':candidate['url'],'sourceLevelCode':'2A','gltfSha256':sha(directory/(oid+'.gltf')),
    'ownership':'domain-only','subtype':'original-individualised-lower-building-body-and-terrace',
    'ownershipReason':'Only source intersections inside named closed building domains may resolve a building identity. The remaining source terrace is unassigned; do not assign the whole object toStaff3 orStaff4.'}
bundle['objects']=[o for o in bundle['objects']if o['id']!=oid]+[obj]
alltri=np.concatenate([upper,low]);full=projection(alltri);lowproj=projection(low);upperproj=projection(upper)
lo,hi=alltri.min((0,1)),alltri.max((0,1));x0,z0=np.floor(lo[[0,2]])-1;x1,z1=np.ceil(hi[[0,2]])+1
width,height=int((x1-x0)*2),int((z1-z0)*2)
exact=rasterize([(mapping(full),255)],out_shape=(height,width),transform=Affine(.5,0,x0,0,.5,z0),dtype='uint8',all_touched=False)
Image.fromarray(exact).save(D/bundle['mask']['exactUrl'])
Image.fromarray(exact).filter(ImageFilter.MaxFilter(3)).save(D/bundle['mask']['url'])
bundle['mask'].update({'boundsXZ':{'min':[float(x0),float(z0)],'max':[float(x1),float(z1)]},'width':width,'height':height,
    'heightMin':float(lo[1]-.5),'heightMax':float(hi[1]+5),'sha256':sha(D/bundle['mask']['url'])})
bundle.update({'bounds':{'min':lo.tolist(),'max':hi.tolist()},'center':((lo+hi)/2).tolist(),
    'triangles':len(alltri),'textureDecodedBytes':sum(o['textureDecodedBytes']for o in bundle['objects']),
    'textureMipBytes':sum(o['textureMipBytes']for o in bundle['objects']),'assetBytes':sum(o['assetBytes']for o in bundle['objects'])})
domains=read(P/'public/data/picking/building-domains-extra.json')['domains']
domains={eid:unary_union([Polygon(p['rings'][0],p['rings'][1:])for d in domains if d['entityId']==eid for p in d['parts']])for eid in ['building:catalog:staff-quarters-tower-3','building:catalog:staff-quarters-tower-4']}
target=domains['building:catalog:staff-quarters-tower-3'];intersection=full.intersection(target).area
bundle['matchEvidence'].update({'sourceProjectionAreaM2':full.area,'intersectionM2':intersection,
    'officialDrawingCoveredRatio':intersection/target.area,'sourceProjectionInsideOfficialRatio':intersection/full.area,
    'componentPolicy':'Staff3 upper3A and lower2A have matching vertical interface; one complete copy of each source. Lower2A has domain-only ownership. Staff4 retains its independent3A and no lower-body duplicate.'})
interface=float(upper[:,:,1].min());roof=low[np.all(abs(low[:,:,1]-interface)<1e-3,axis=1)]
base=upper[np.all(abs(upper[:,:,1]-interface)<1e-3,axis=1)]
contact=projection(roof).intersection(projection(base)).area if len(base)and len(roof)else None
interface_points=np.unique(upper.reshape(-1,3)[abs(upper.reshape(-1,3)[:,1]-interface)<1e-3][:,[0,2]],axis=0)
roof_projection=projection(roof)if len(roof)else None
distances=[roof_projection.distance(Point(point))for point in interface_points]if roof_projection is not None else []
report={'status':'staged-source-verified-runtime-domain-only-picking-required','stagingDirectory':str(D),
    'groups':[{'id':b['id'],'canonicalId':'building:'+b['buildingId'],'objects':[o['id']for o in b['objects']],
        'textureMipMiB':b['textureMipBytes']/2**20,'triangles':b['triangles'],'actualBounds':b['bounds'],
        'officialDomainCoveredRatio':b['matchEvidence']['officialDrawingCoveredRatio']}for b in manifest['bundles']],
    'lowerSourceObjectId':oid,'lowerSourceYRange':[float(low[:,:,1].min()),float(low[:,:,1].max())],
    'upperStaff3YRange':[float(upper[:,:,1].min()),float(upper[:,:,1].max())],
    'staff4YRange':[float(adjacent[:,:,1].min()),float(adjacent[:,:,1].max())],
    'sourceInterfaceYDifferenceMeters':float(low[:,:,1].max()-upper[:,:,1].min()),
    'horizontalSourceInterfaceContactM2':contact,
    'upperInterfaceVertices':len(interface_points),
    'upperInterfaceToLowerTopPlanDistanceMeters':dict(zip(['min','median','p95','max'],np.quantile(distances,[0,.5,.95,1]).tolist()))if distances else None,
    'interfaceNote':'No invented closing cap. The3A body has no horizontal bottom faces at its minimumY, so a2D bottom-face contact area is unavailable; original minimum-level boundary vertices are tested against actual2A top triangles instead.',
    'lowerProjectionM2':lowproj.area,'lowerUpperSourceProjectionIntersectionM2':lowproj.intersection(upperproj).area,
    'lowerStaff4SourceProjectionIntersectionM2':lowproj.intersection(projection(adjacent)).area,
    'lowerOfficialDomainIntersections':[{'canonicalId':eid,'intersectionM2':lowproj.intersection(domain).area,
        'fractionOfOfficialDomain':lowproj.intersection(domain).area/domain.area}for eid,domain in domains.items()],
    'lowerOutsideBothNamedDomainsM2':lowproj.difference(unary_union(list(domains.values()))).area,
    'ownership':'The lower2A object is owned once by theStaff3 source loading transaction, but ownership=domain-only for picking. Resource ownership does not assign its whole terrace to any building.',
    'originalTexturesGeometryUVNodesUnchanged':True,'physicalSourceCopies':1,
    'noRegistryOrRuntimeChanges':True,'browserAppearanceAcceptance':'pending'}
(D/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(P/'docs/source-evidence-v4/building-quality/northern-staff-3-4-composition.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
