#!/usr/bin/env python3
"""Independent source-file, image-header and all-pixel projection QA for staging.
Does not modify live source objects, scene or exterior manifest.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import STRtree, points, polygons
from hkust_source_geometry import geometry
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--directory',default='/tmp/hkust-v6-next-exteriors')
parser.add_argument('--report',default='residential-exteriors-independent-qa.json')
args=parser.parse_args()
D=Path(args.directory)
read=lambda p:json.loads(p.read_text())
reports=[]
for bundle in read(D/'manifest.json')['bundles']:
    all_tri=[];verified=0;dimensions=[];uv_report=[]
    for obj in bundle['objects']:
        directory=(D/obj['url']).parent;source=read(D/obj['sourceManifest'])
        for item in source['files']:
            path=directory/item['filename']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'];verified+=1
        gltf=read(D/obj['url'])
        assert gltf['nodes']==source['original_nodes']
        for reference in gltf['buffers']+gltf.get('images',[]):assert (directory/reference['uri']).exists()
        images=[]
        for image in gltf.get('images',[]):
            with Image.open(directory/image['uri'])as decoded:images.append(list(decoded.size));decoded.verify()
        assert images==obj['textureDimensions'];dimensions.extend(images)
        buffers=[(directory/buffer['uri']).read_bytes()for buffer in gltf['buffers']]
        def accessor(index):
            data=gltf['accessors'][index];view=gltf['bufferViews'][data['bufferView']]
            dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1',5122:'<i2',5120:'i1'}[data['componentType']])
            components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[data['type']]
            array=np.ndarray((data['count'],components),dtype=dtype,buffer=buffers[view.get('buffer',0)],
                offset=view.get('byteOffset',0)+data.get('byteOffset',0),strides=(view.get('byteStride',dtype.itemsize*components),dtype.itemsize))
            if data.get('normalized')and dtype.kind in 'iu':
                array=np.maximum(-1,array.astype(float)/np.iinfo(dtype).max)
            return array
        for mesh in gltf['meshes']:
            for primitive in mesh['primitives']:
                assert 'TEXCOORD_0'in primitive['attributes']
                material=gltf['materials'][primitive['material']]
                assert material.get('pbrMetallicRoughness',{}).get('baseColorTexture') is not None
                uv=accessor(primitive['attributes']['TEXCOORD_0'])
                assert uv.shape==(gltf['accessors'][primitive['attributes']['POSITION']]['count'],2)
                assert np.isfinite(uv).all()
                indices=accessor(primitive['indices']).ravel().astype(int)if'indices'in primitive else np.arange(len(uv))
                assert indices.min()>=0 and indices.max()<len(uv)
                uvtri=uv[indices.reshape(-1,3)].astype(float)
                a,b=uvtri[:,1]-uvtri[:,0],uvtri[:,2]-uvtri[:,0]
                area=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5
                texture=gltf['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]
                uv_report.append({'sourceObjectId':obj['id'],'material':primitive['material'],
                    'baseColorImage':gltf['images'][texture['source']]['uri'],
                    'triangles':len(uvtri),'finiteSourceUVs':True,'uvMin':uv.min(0).tolist(),'uvMax':uv.max(0).tolist(),
                    'nonCollapsedUVTriangles':int(np.count_nonzero(area>1e-12)),
                    'nonCollapsedUVFraction':float(np.mean(area>1e-12))})
        transform=np.eye(4);transform[:3,3]=obj['offset'];tri,_=geometry(D/obj['url'],transform)
        assert len(tri)==obj['triangles'] and np.isfinite(tri).all()
        assert np.max(abs(tri.min((0,1))-obj['bounds']['min']))<1e-9
        assert np.max(abs(tri.max((0,1))-obj['bounds']['max']))<1e-9
        all_tri.append(tri)
    tri=np.concatenate(all_tri);mask=bundle['mask'];exact=np.asarray(Image.open(D/mask['exactUrl']).convert('L'))
    actual=np.asarray(Image.open(D/mask['url']).convert('L'))
    assert exact.shape==(mask['height'],mask['width'])
    rows,cols=np.indices(exact.shape);low=mask['boundsXZ']['min'];high=mask['boundsXZ']['max']
    step=np.array(high)-low;step/=np.array([mask['width'],mask['height']]);assert np.array_equal(step,[.5,.5])
    grid=np.c_[low[0]+(cols.ravel()+.5)*.5,low[1]+(rows.ravel()+.5)*.5]
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);tree=STRtree(polygons(tri[abs(normal[:,1])>1e-9][:,:,[0,2]]))
    pairs=tree.query(points(grid),predicate='intersects');expected=np.zeros(len(grid),bool);expected[pairs[0]]=True
    assert np.array_equal(expected.reshape(exact.shape),exact>0)
    padded=np.pad(exact,1);guard=np.maximum.reduce([padded[dr:dr+len(exact),dc:dc+exact.shape[1]]for dr in range(3)for dc in range(3)])
    assert np.array_equal(actual,guard)
    reports.append({'canonicalId':bundle.get('entityId')or'building:'+bundle['buildingId'],'objects':len(bundle['objects']),
        'allOriginalFilesSha256Verified':verified,'triangles':len(tri),'everyPrimitiveHasSourceUVAndBaseColorTexture':True,
        'textureDimensions':dimensions,'sourceNodeMatricesAndOuterOffsetVerified':True,
        'originalUVAccessorValidation':uv_report,
        'allExactProjectionPixelChecks':len(grid),'projectionMismatches':0,
        'guardMatchesExactlyOneSourcePixel':True,'liveAssetsModified':False})
result={'status':'pass','groups':reports,'browserAppearanceAcceptance':'Not part of source/numerical checks; remains pending.'}
(P/'docs/source-evidence-v4/building-quality'/args.report).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
