#!/usr/bin/env python3
"""Copy only two verified public source models; independently validate their geometry."""
import json, hashlib, shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit
import numpy as np
from PIL import Image

SRC = Path('/tmp/hkust-hires-geodata/individualised-source').resolve()
OUT = Path(__file__).resolve().parent
OFFSET = np.array([-844800., 0., 820500.])
CHOSEN = [('B451872165201063A0', 'campus-22', '逸夫演艺中心 · Shaw Auditorium'),
          ('B451962174701063A0', 'campus-18', '郑裕彤楼 · Cheng Yu Tung Building')]
DTYPES = {5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
WIDTH = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT2':4,'MAT3':9,'MAT4':16}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def relative_ref(folder, uri):
    assert not urlsplit(uri).scheme and not uri.startswith('/'), uri
    result = (folder / unquote(uri)).resolve()
    assert result.is_relative_to(folder.resolve()) and result.is_file(), uri
    return result

def accessor(g, buffers, index):
    a = g['accessors'][index]
    assert 'sparse' not in a
    v = g['bufferViews'][a['bufferView']]
    dtype = np.dtype(DTYPES[a['componentType']]); width = WIDTH[a['type']]
    stride = v.get('byteStride', dtype.itemsize * width)
    offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    assert a.get('byteOffset', 0) + (a['count']-1)*stride + dtype.itemsize*width <= v['byteLength']
    return np.ndarray((a['count'],width), dtype, buffers[v['buffer']], offset,
                      strides=(stride,dtype.itemsize))

def prepare(model_id, catalog_id, label):
    folder = SRC/'buildings'/model_id
    source_manifest = json.loads((folder/'manifest.json').read_text())
    original = folder/(model_id+'.gltf')
    g = json.loads(original.read_text())
    assert g['asset']['version']=='2.0'
    assert not g.get('extensionsRequired')
    refs = [relative_ref(folder, obj['uri']) for key in ('buffers','images') for obj in g.get(key,[])]
    files = [original] + list(dict.fromkeys(refs))
    source_hashes = {f['filename']:f['sha256'] for f in source_manifest['files']}
    for f in files:
        assert sha(f)==source_hashes[f.name], f
    buffers = [relative_ref(folder,b['uri']).read_bytes() for b in g['buffers']]
    for b,data in zip(g['buffers'],buffers): assert b['byteLength']==len(data)
    for v in g['bufferViews']:
        assert v.get('byteOffset',0)+v['byteLength']<=len(buffers[v['buffer']])
    for i in range(len(g['accessors'])):
        assert np.isfinite(accessor(g,buffers,i)).all()

    points=[]; triangles=0; primitive_count=0
    def walk(i,parent):
        nonlocal triangles,primitive_count
        n=g['nodes'][i]
        assert not any(k in n for k in ('translation','rotation','scale'))
        m=parent@np.asarray(n.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F')
        if 'mesh' in n:
            for primitive in g['meshes'][n['mesh']]['primitives']:
                assert primitive.get('mode',4)==4
                pos=accessor(g,buffers,primitive['attributes']['POSITION']).astype(float)
                assert np.isfinite(pos).all()
                a=g['accessors'][primitive['attributes']['POSITION']]
                assert np.allclose(pos.min(0),a['min'],atol=1e-5)
                assert np.allclose(pos.max(0),a['max'],atol=1e-5)
                indices=accessor(g,buffers,primitive['indices']).ravel() if 'indices' in primitive else np.arange(len(pos))
                assert len(indices)%3==0 and indices.min()>=0 and indices.max()<len(pos)
                points.append((np.column_stack([pos,np.ones(len(pos))])@m.T)[:,:3])
                triangles+=len(indices)//3;primitive_count+=1
        for child in n.get('children',[]): walk(child,m)
    for root in g['scenes'][g.get('scene',0)]['nodes']: walk(root,np.eye(4))
    points=np.concatenate(points)
    world_min,world_max=points.min(0),points.max(0)
    claimed=np.array(source_manifest['geometry']['world_bbox_gltf_XYZ_m'])
    assert np.allclose(world_min,claimed[:,0],atol=1e-6)
    assert np.allclose(world_max,claimed[:,1],atol=1e-6)
    assert triangles==source_manifest['geometry']['triangle_count']

    destination=OUT/'buildings'/model_id;destination.mkdir(parents=True,exist_ok=True)
    checks=[]
    for f in files:
        target=destination/f.relative_to(folder)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(f,target)
        assert sha(target)==sha(f)
        checks.append({'url':target.relative_to(OUT).as_posix(),'bytes':target.stat().st_size,'sha256':sha(target)})
    shutil.copyfile(folder/'manifest.json',destination/'source-manifest.json')
    textures=[]
    for img in g['images']:
        f=relative_ref(destination,img['uri'])
        with Image.open(f) as im:
            size=list(im.size); im.verify()
        textures.append({'uri':img['uri'],'bytes':f.stat().st_size,'dimensions':size})
    local_min=(world_min+OFFSET).tolist();local_max=(world_max+OFFSET).tolist()
    return {
        'catalogId':catalog_id,'id':model_id,'label':label,
        'url':f'buildings/{model_id}/{model_id}.gltf','offset':OFFSET.tolist(),
        'bounds':{'min':local_min,'max':local_max},
        'boundsSpace':'local XYZ after applying offset; X=E-844800, Y=source elevation, Z=820500-N',
        'textureBytes':sum(t['bytes'] for t in textures),'triangles':int(triangles),
        'assetBytes':sum(f.stat().st_size for f in files),
        'source':source_manifest['source_archive_uri'],
        'sourceMetadata':f'buildings/{model_id}/source-manifest.json',
        'revisionDate':source_manifest['source_tile_revision_date'],
        'captureDate':None,'sourceTile':source_manifest['source_tile'],
        'levelCode':source_manifest['level_code'],'lod':source_manifest['lod'],
        'nameVerification':source_manifest['name_verification'],
        'notes':[
            'Original glTF node matrices and all source asset bytes preserved. GLTFLoader already applies source axis transformation to (E,H,-N); apply only the listed outer-group offset.',
            'Source vertical datum is not independently specified; source elevation is preserved with no inferred HKPD/ellipsoid correction.',
            '2026-04-24 is the source tile revision date, not photography, survey, completion or construction date.',
            'Model origin Y is not necessarily ground; bbox Y range is the actual model extent, not a floor-height measurement.',
            'Use as an isolated exterior viewer; no interior geometry is inferred.'
        ]
    }, {
        'id':model_id,'status':'pass','allReferencesPresent':True,
        'sourceAndCopySHA256Match':True,'originalMatricesUnchanged':True,
        'accessorsFiniteAndInBounds':True,'indicesWithinPositionCount':True,
        'worldBoundsAgreeWithSourceManifest':True,
        'worldBounds':{'min':world_min.tolist(),'max':world_max.tolist()},
        'localBounds':{'min':local_min,'max':local_max},
        'triangles':int(triangles),'primitiveCount':primitive_count,
        'positionCount':len(points),'textures':textures,'files':checks
    }

def main():
    source=json.loads((SRC/'buildings-manifest.json').read_text())
    result={'version':1,'checkedAt':'2026-09-05',
            'coordinateSystem':{'offset':OFFSET.tolist(),'axes':'x=E-844800; y=source elevation; z=820500-N','units':'metres'},
            'attribution':'3D Visualisation Map (Individualised Models), Lands Department, HKSAR Government. Source assets are publicly provided government model files; source usage terms continue to apply.',
            'sourceArchiveLastModified':source['source_archive_last_modified'],
            'buildings':[]}
    qa={'status':'pass','checkedAt':'2026-09-05','networkUsed':False,'sourceFilesModified':False,'buildings':[]}
    for item in CHOSEN:
        b,q=prepare(*item);result['buildings'].append(b);qa['buildings'].append(q)
    result['totals']={'buildings':2,'triangles':sum(x['triangles'] for x in result['buildings']),
                      'assetBytes':sum(x['assetBytes'] for x in result['buildings']),
                      'textureBytes':sum(x['textureBytes'] for x in result['buildings'])}
    for name,data in [('manifest.json',result),('validation.json',qa)]:
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'totals':result['totals'],'models':[{k:b[k] for k in ('catalogId','id','bounds','triangles','textureBytes')} for b in result['buildings']]},ensure_ascii=False))

if __name__=='__main__': main()
