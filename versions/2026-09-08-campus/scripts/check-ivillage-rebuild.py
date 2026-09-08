#!/usr/bin/env python3
"""Independent asset, identity, topology and source-ground checks (not visual QA)."""
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union

P=Path(__file__).resolve().parents[1];O=P/'public/models/current-forms/ivillage-rebuild'
S=Path('/tmp/hkust-ivillage-rebuild-source')
m=json.loads((O/'manifest.json').read_text());e=json.loads((O/'evidence/geometry.json').read_text())
raw=(O/m['asset']['url']).read_bytes()
assert len(raw)==m['asset']['bytes'] and hashlib.sha256(raw).hexdigest()==m['asset']['sha256']
magic,version,size=struct.unpack_from('<4sII',raw);assert (magic,version,size)==(b'glTF',2,len(raw))
length,kind=struct.unpack_from('<I4s',raw,12);assert kind==b'JSON'
g=json.loads(raw[20:20+length]);binary=memoryview(raw)[28+length:]
assert len(g['scenes'][0]['nodes'])==len(m['members'])==4
assert len(g['images'])==len(g['textures'])==m['appearance']['embeddedTextures']
assert len(g['materials'])==m['appearance']['materials']
assert len(g['images'])==2 and len(g['materials'])==14
for index,relative in enumerate(['textures/official-facade-photo.jpg','textures/official-roof-paving.png']):
    image=g['images'][index];view=g['bufferViews'][image['bufferView']]
    embedded=bytes(binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']])
    assert embedded==(O/relative).read_bytes(),'actual embedded photo differs from registered source output'
assert all('KHR_materials_unlit' in mat.get('extensions',{}) for mat in g['materials'])
assert not any('uri' in v for k in ['images','buffers']for v in g[k])
floor=json.loads((P/'public/interiors/manifest.json').read_text())
total=0;draws=0;material_users={};envelopes=[]
for member,record,root_index in zip(m['members'],e['buildings'],g['scenes'][0]['nodes']):
    node=g['nodes'][root_index]
    assert node['name']==member['nodeName']==record['catalogId']
    assert node['extras']['entityId']==member['entityId']
    assert node['extras']['buildingId']==member['buildingId']
    actual=[]
    for child in node['children']:
        for primitive in g['meshes'][g['nodes'][child]['mesh']]['primitives']:
            a=g['accessors'][primitive['attributes']['POSITION']];view=g['bufferViews'][a['bufferView']]
            positions=np.frombuffer(binary,dtype='<f4',count=a['count']*3,offset=view.get('byteOffset',0)).reshape(-1,3)
            assert np.isfinite(positions).all() and len(positions)%3==0
            t=positions.reshape(-1,3,3);area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
            assert (area>1e-8).all(), 'float32 packing collapsed a real geometric feature'
            total+=len(t);draws+=1;actual.append(positions)
            material_users.setdefault(primitive['material'],set()).add(member['buildingId'])
    positions=np.concatenate(actual)
    assert np.max(abs(positions.min(0)-member['bounds']['min']))<.001
    assert np.max(abs(positions.max(0)-member['bounds']['max']))<.001
    preserved=[{'id':f['id'],'name':f['floorName'],'sourceZValues':f['sourceZValues']}for f in floor['floors']if f['buildingId']==member['buildingId']]
    assert record['publicFloors']==preserved
    envelope=unary_union([Polygon(p['rings'][0],p['rings'][1:])for p in record['envelopeParts']])
    assert envelope.is_valid and envelope.geom_type=='Polygon'
    envelopes.append(envelope)
    mask=member['mask'];payload=(O/mask['url']).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==mask['sha256'] and len(payload)==mask['bytes']
    assert Image.open(O/mask['url']).size==(mask['width'],mask['height'])
for i,a in enumerate(envelopes):
    for j,b in enumerate(envelopes):
        if i<j:assert a.intersection(b).area<1e-6,'duplicate building shell ownership'
for a,b in zip(envelopes,envelopes[1:]):assert a.distance(b)<.001,'broken neighbouring building junction'
assert len(material_users[0])==4 and len(material_users[1])==4 and len(material_users[7])==4

# Recompute every ground-protection witness from its actual source triangle,
# independent of the raster generation loop and encoded image channels.
witness=np.load(O/'evidence/ground-preservation-witnesses.npz')
source=np.load(S/'terminal-triangles.npz');T=source['positions']
lookup={(int(s),int(t)):i for i,(s,t) in enumerate(zip(source['sourceTileIndex'],source['triangleIndex']))}
guard=m['sourceProtection'];payload=(O/guard['url']).read_bytes()
assert len(payload)==guard['bytes']==guard['width']*guard['height']*4
assert hashlib.sha256(payload).hexdigest()==guard['sha256']
rgba=np.frombuffer(payload,np.uint8).reshape(guard['height'],guard['width'],4)
assert (rgba[:,:,2:]==255).all(),'old Hall X structure would survive complete replacement'
maximum=0
for row,col,height,s,t in zip(witness['row'],witness['col'],witness['height'],witness['sourceTileIndex'],witness['triangleIndex']):
    tri=T[lookup[int(s),int(t)]]
    normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);normal/=np.linalg.norm(normal)
    assert normal[1]>=.6-1e-10
    x,z=np.array(guard['boundsXZ']['min'])+(np.array([col,row])+.5)*guard['pixelSizeMeters']
    a,b=np.linalg.solve(np.column_stack([tri[1,[0,2]]-tri[0,[0,2]],tri[2,[0,2]]-tri[0,[0,2]]]),[x-tri[0,0],z-tri[0,2]])
    assert min(a,b,1-a-b)>-1e-7
    actual=tri[0,1]+a*(tri[1,1]-tri[0,1])+b*(tri[2,1]-tri[0,1])
    assert abs(actual-height)<1e-7
    decoded=float(rgba[row,col,0])+float(rgba[row,col,1])/256
    maximum=max(maximum,abs(decoded-actual))
    assert abs(decoded-actual)<=1/512+1e-8
report={'status':'pass','assetSHA256':m['asset']['sha256'],'buildings':len(m['members']),
    'triangles':total,'drawPrimitives':draws,'embeddedSharedTextures':len(g['images']),'materials':len(g['materials']),
    'groundWitnesses':len(witness['row']),'maximumGroundEncodingErrorMeters':maximum,
    'checks':['Four whole entity roots with stable identities and exact manifest bounds',
        'Every packed triangle finite and non-degenerate','One shared material and texture graph',
        'No duplicate physical shell domains; three adjacent XZ junctions touch (vertical closure is checked separately)',
        'All existing public floor records unchanged','Every model/mask/protection SHA and byte count',
        'Every protected ground texel recomputed from actual source triangle; no old X structure protection'],
    'limitations':'Geometry/source checks are not proof of current photo fidelity, visible source removal, all-angle live picking or runtime performance.'}
(P/'docs/source-evidence-v4/ivillage-rebuild/asset-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
