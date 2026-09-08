#!/usr/bin/env python3
"""Reproducible, offline-only assembly of complete source LOD patches."""
import datetime, hashlib, json, math, pathlib, shutil, struct

PROJECT = pathlib.Path(__file__).resolve().parents[3]
SOURCE = pathlib.Path('/tmp/hkust-hires-geodata')
OUT = pathlib.Path('/tmp/hkust-v2-hires')
BASE = json.loads((PROJECT/'public/models/render-manifest.json').read_text())
IDENTITY = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    temp.replace(path)
def multiply(a,b):
    return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]
def transform(m,p): return [sum(m[k*4+r]*p[k] for k in range(3))+m[12+r] for r in range(3)]
def union(bounds):
    return {'min':[min(b['min'][i] for b in bounds) for i in range(3)], 'max':[max(b['max'][i] for b in bounds) for i in range(3)]}
def center(bounds): return [(a+b)/2 for a,b in zip(bounds['min'],bounds['max'])]
def source_nodes(root):
    result={}
    def walk(n,parent):
        matrix=multiply(parent,n.get('transform',IDENTITY))
        name=pathlib.PurePosixPath(n.get('content',{}).get('uri','')).name
        if name: result[name]={'node':n,'matrix':matrix}
        for c in n.get('children',[]): walk(c,matrix)
    walk(root,IDENTITY)
    return result
def uncovered(root, selected):
    name=pathlib.PurePosixPath(root.get('content',{}).get('uri','')).name
    if name in selected: return []
    children=root.get('children',[])
    if children: return [v for c in children for v in uncovered(c,selected)]
    return [name] if name else []

def inspect_glb(data,matrix):
    magic,version,length=struct.unpack_from('<4sII',data)
    assert magic==b'glTF' and version==2 and length==len(data),'Invalid GLB header'
    cursor=12; doc=None; binary=None
    while cursor<len(data):
        size,typ=struct.unpack_from('<II',data,cursor); chunk=data[cursor+8:cursor+8+size];cursor+=8+size
        if typ==0x4E4F534A: doc=json.loads(chunk)
        elif typ==0x004E4942: binary=chunk
    assert doc and binary is not None
    assert not doc.get('extensionsRequired'), 'Unsupported GLTF extension; do not assume raw accessor layout'
    # Source assets currently have identity nodes. Reject instead of silently ignoring transforms.
    for n in doc.get('nodes',[]):
        assert n.get('matrix',IDENTITY)==IDENTITY
        assert n.get('translation',[0,0,0])==[0,0,0]
        assert n.get('rotation',[0,0,0,1])==[0,0,0,1]
        assert n.get('scale',[1,1,1])==[1,1,1]
    low=[math.inf]*3; high=[-math.inf]*3; triangles=vertices=0
    seen=set()
    for mesh in doc.get('meshes',[]):
        for primitive in mesh['primitives']:
            assert primitive.get('mode',4)==4
            idx=primitive['attributes']['POSITION']; accessor=doc['accessors'][idx]
            vertices+=accessor['count']
            triangles+=(doc['accessors'][primitive['indices']]['count'] if 'indices' in primitive else accessor['count'])//3
            if idx in seen: continue
            seen.add(idx)
            assert accessor['componentType']==5126 and accessor['type']=='VEC3' and not accessor.get('sparse')
            view=doc['bufferViews'][accessor['bufferView']]; assert view.get('buffer',0)==0
            start=view.get('byteOffset',0)+accessor.get('byteOffset',0); stride=view.get('byteStride',12)
            for i in range(accessor['count']):
                point=transform(matrix,struct.unpack_from('<fff',binary,start+i*stride))
                assert all(math.isfinite(p) for p in point)
                for axis in range(3):
                    low[axis]=min(low[axis],point[axis]); high[axis]=max(high[axis],point[axis])
    assert all(math.isfinite(v) for v in low+high)
    encoded=sum(doc['bufferViews'][img['bufferView']]['byteLength'] for img in doc.get('images',[]))
    return {'bounds':{'min':low,'max':high},'triangles':triangles,'vertices':vertices,'textureEncodedBytes':encoded}

patches=[]; evidence=[]; skipped=[]
for manifest_path in sorted((SOURCE/'mesh/12-NW-6C').glob('*/manifest.json')):
    # Snapshot each completed manifest; later arrivals are incorporated by rerunning this script.
    manifest=read(manifest_path); sheet=manifest['tile']; subtree=manifest['subtree']
    baseline=[t for t in BASE['tiles'] if t['id'].split('/')[:2]==[sheet,subtree]]
    if not baseline:
        skipped.append({'subtree':subtree,'reason':'No existing baseline sub-tree to replace'});continue
    matrix=baseline[0]['matrix']; assert all(t['matrix']==matrix for t in baseline)
    original_path=PROJECT/'source-geodata/mesh'/sheet/subtree/'source-tileset.json'
    fresh_path=manifest_path.parent/'source-tileset.json'
    old=read(original_path); fresh=read(fresh_path)
    assert old==fresh, f'{subtree}: source tree changed; matrix reuse requires conversion'
    assert old['asset'].get('gltfUpAxis')==fresh['asset'].get('gltfUpAxis')=='Z'
    nodes=source_nodes(fresh['root']); root_transform=fresh['root']['transform']
    assert root_transform==manifest['bounds']['root_transform_column_major']
    reference=nodes[pathlib.PurePosixPath(baseline[0]['sourceB3dm']).name]['matrix']
    for tile in baseline:
        node=nodes[pathlib.PurePosixPath(tile['sourceB3dm']).name]
        assert node['matrix']==reference
        raw=(PROJECT/'public/models'/tile['url']).read_bytes()
        assert sha(raw)==tile['sha256']
        source_raw=(PROJECT/'source-geodata'/tile['sourceB3dm']).read_bytes()
        assert sha(source_raw)==tile['sourceSha256']
    baseline_frontier=next(f for f in manifest['frontiers'] if f['key']=='baseline')
    assert not baseline_frontier['issues']
    assert {a['uri'] for a in baseline_frontier['assets']}=={b['sourceB3dm'] for b in baseline}
    for asset in baseline_frontier['assets']:
        b=next(b for b in baseline if b['sourceB3dm']==asset['uri'])
        assert asset['glb_sha256']==b['sha256'] and asset['sha256']==b['sourceSha256']
    patch={'id':subtree,'sheet':sheet,'baselineIds':[b['id'] for b in baseline],
           'baselineTriangles':sum(b['triangles'] for b in baseline),'baselineBytes':sum(b['bytes'] for b in baseline),
           'levels':{}, 'sourceRootTransform':root_transform,
           'matrixEvidence':'Existing baseline matrix reused exactly; original source hierarchy, transforms, baseline GLB and b3dm SHA-256 all match.',
           'sourceManifest':'sources/'+subtree+'/manifest.json'}
    accepted=[]
    for frontier in manifest['frontiers']:
        level=frontier['key']
        if level not in ('high','fine'):continue
        if frontier['issues']:
            skipped.append({'subtree':subtree,'level':level,'reason':'Source frontier has issues','issues':frontier['issues']});continue
        assets=frontier['assets']; names={pathlib.PurePosixPath(a['source_name']).name for a in assets}
        missing=uncovered(fresh['root'],names)
        assert not missing, f'{subtree}/{level}: uncovered source leaves {missing[:5]}'
        assert len(names)==len(assets)==frontier['summary']['assets']
        level_tiles=[]
        for asset in assets:
            name=pathlib.PurePosixPath(asset['source_name']).name
            assert name in nodes and nodes[name]['matrix']==reference, f'{subtree}/{name}: transform mismatch'
            assert not any(asset.get('feature_table',{}).get('RTC_CENTER',[0,0,0])), 'RTC_CENTER requires separate conversion'
            source=SOURCE/asset['glb_uri']
            assert source.is_file(), f'{subtree}/{level}: incomplete frontier {source}'
            raw=source.read_bytes(); digest=sha(raw)
            assert digest==asset['glb_sha256'] and len(raw)==asset['glb_bytes']
            b3dm=(SOURCE/asset['uri']).read_bytes()
            assert sha(b3dm)==asset['sha256']
            header=struct.unpack_from('<4s6I',b3dm)
            assert b3dm[28+sum(header[3:]):]==raw, 'GLB differs from embedded B3DM payload'
            stats=inspect_glb(raw,matrix)
            assert stats['triangles']==asset['triangles'] and stats['vertices']==asset['vertices']
            assert stats['textureEncodedBytes']==asset['texture_encoded_bytes']
            url=f'glb/{sheet}/{subtree}/{source.name}'
            dest=OUT/url;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,dest);assert sha(dest.read_bytes())==digest
            level_tiles.append({'id':f'{sheet}/{subtree}/{source.stem}','url':url,'matrix':matrix,
                                'bounds':stats['bounds'],'center':center(stats['bounds']),
                                'triangles':stats['triangles'],'vertices':stats['vertices'],'bytes':len(raw),
                                'textureBytes':asset['texture_pixels']*4,'textureEncodedBytes':stats['textureEncodedBytes'],
                                'texturePixels':asset['texture_pixels'],'textureDimensions':[[x['width'],x['height']] for x in asset['texture_images']],
                                'sha256':digest,'sourceB3dm':asset['uri'],'sourceSha256':asset['sha256'],
                                'geometricError':asset['original_geometric_error']})
        summary={'tiles':level_tiles,'triangles':sum(t['triangles'] for t in level_tiles),
                 'bytes':sum(t['bytes'] for t in level_tiles),'textureBytes':sum(t['textureBytes'] for t in level_tiles),
                 'textureEncodedBytes':sum(t['textureEncodedBytes'] for t in level_tiles),
                 'bounds':union([t['bounds'] for t in level_tiles]),'complete':True,
                 'geometricErrorMax':max(t['geometricError'] for t in level_tiles),
                 'sourceTargetGeometricError':frontier['target_original_geometric_error']}
        assert summary['triangles']==frontier['summary']['triangles'] and summary['bytes']==frontier['summary']['glb_bytes']
        patch['levels'][level]=summary;accepted.append(level)
    if not accepted:continue
    patch['bounds']=union([b['bounds'] for b in baseline]+[v['bounds'] for v in patch['levels'].values()]);patch['center']=center(patch['bounds'])
    patches.append(patch)
    source_out=OUT/'sources'/subtree;source_out.mkdir(parents=True,exist_ok=True)
    for path in [manifest_path,fresh_path]+list(manifest_path.parent.glob('tileset-*.json')):
        shutil.copyfile(path,source_out/path.name)
    evidence.append({'subtree':subtree,'baselineIds':patch['baselineIds'],'acceptedLevels':accepted,
                     'sourceTreesIdentical':True,'sourceRootTransformIdentical':True,'descendantEffectiveTransformsIdentical':True,
                     'baselinePayloadHashesIdentical':True,'allFrontiersCoverEverySourceLeaf':True,
                     'allGlbPayloadsCopiedWithoutModification':True,'boundsFromEveryPositionVertex':True,
                     'originalSourceTilesetSha256':sha(original_path.read_bytes()),'newSourceTilesetSha256':sha(fresh_path.read_bytes())})

assert patches
output={'version':1,'generatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'coordinateSystem':BASE['coordinateSystem'],'source':BASE['source'],
        'textureBytesDefinition':'Uncompressed RGBA8 base-level texture estimate: width*height*4. Excludes mipmaps, driver overhead and transient decoded bitmap copies. textureEncodedBytes is compressed GLB image storage.',
        'urlBase':'All tile.url paths are relative to the directory containing this manifest.',
        'replacementPolicy':'Keep all baselineIds visible until every tile of the requested patch level has loaded and is ready. Swap the whole patch atomically; cancel or fail back to its complete baseline. high and fine are alternative full frontiers, never additive layers.',
        'patches':patches}
write(OUT/'manifest.json',output)
write(OUT/'validation.json',{'pass':True,'generatedAt':output['generatedAt'],'patchCount':len(patches),'evidence':evidence,'skipped':skipped,
    'totals':{level:{'patches':sum(level in p['levels'] for p in patches),'tiles':sum(len(p['levels'][level]['tiles']) for p in patches if level in p['levels']),
                     'triangles':sum(p['levels'][level]['triangles'] for p in patches if level in p['levels']),
                     'bytes':sum(p['levels'][level]['bytes'] for p in patches if level in p['levels']),
                     'textureBytes':sum(p['levels'][level]['textureBytes'] for p in patches if level in p['levels'])} for level in ('high','fine')}})
print(json.dumps(read(OUT/'validation.json')['totals'],ensure_ascii=False,indent=2))
print('Completed', len(patches), 'patches in', OUT)
