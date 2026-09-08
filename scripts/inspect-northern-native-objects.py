#!/usr/bin/env python3
"""Read original6A individual-object metadata against already named official domains.
Only12 indexed JSON entries are acquired; bounds are candidates, not owner masks.
"""
import argparse, concurrent.futures, hashlib, itertools, json, re, struct, urllib.parse, urllib.request, zlib
from pathlib import Path
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

P=Path(__file__).resolve().parents[1]
I=Path('/tmp/hkust-v6-building-native/individual-index')
D=Path('/tmp/hkust-v7-northern-exteriors');D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
parser=argparse.ArgumentParser()
parser.add_argument('--sheet',default='12-NW-6A')
args=parser.parse_args()
sheet=args.sheet
metadata=read(I/'sheet-index.json')
source=next((f['attributes']for f in metadata['features']if f['attributes']['SHEETNO']==sheet),None)
def request_bytes(url,range_=None):
    request=urllib.request.Request(url,headers={'Range':range_}if range_ else {})
    with urllib.request.urlopen(request,timeout=60)as response:
        if range_:assert response.status==206
        return response.read()
if source is None:
    cached=I/(sheet+'-sheet-index.json')
    if cached.exists():page=read(cached)
    else:
        endpoint='https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1671676915450_88604/FeatureServer/0/query'
        query=urllib.parse.urlencode({'where':f"SHEETNO='{sheet}'",'outFields':'*','returnGeometry':'false','f':'json'})
        raw=request_bytes(endpoint+'?'+query);cached.write_bytes(raw);page=json.loads(raw)
    assert len(page['features'])==1
    source=page['features'][0]['attributes']
url=source['Format_glTF'];index_path=I/(sheet+'-zip-index.json')
if not index_path.exists():
    tail=request_bytes(url,'bytes=-65536');position=tail.rfind(b'PK\x05\x06')
    end=struct.unpack_from('<4s4H2LH',tail,position);size,offset=end[-3],end[-2]
    central=request_bytes(url,f'bytes={offset}-{offset+size-1}')
    (I/(sheet+'-zip-central.bin')).write_bytes(central);entries={};index=0
    while index<len(central):
        header=struct.unpack_from('<4s6H3L5H2L',central,index);assert header[0]==b'PK\x01\x02'
        name=central[index+46:index+46+header[10]].decode()
        entries[name]={'compressed':header[8],'size':header[9],'offset':header[-1],'compression':header[4],'crc32':header[7]}
        index+=46+header[10]+header[11]+header[12]
    index_path.write_text(json.dumps(entries,indent=2)+'\n')
entries=read(index_path)
raw_domains=read(P/'public/data/picking/building-domains-extra.json')['domains']
domains={eid:unary_union([Polygon(p['rings'][0],p['rings'][1:])for d in raw_domains if d['entityId']==eid for p in d['parts']])
    for eid in {d['entityId']for d in raw_domains}}

def job(item):
    name,entry=item;oid=name.split('/')[1];destination=D/'metadata'/sheet/name
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raw=destination.read_bytes()
    else:
        offset=entry['offset'];request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{offset+entry["compressed"]+1024}'})
        with urllib.request.urlopen(request,timeout=60)as response:
            assert response.status==206;packed=response.read()
        header=struct.unpack_from('<4s5H3L2H',packed);assert header[0]==b'PK\x03\x04'
        start=30+header[-2]+header[-1];raw=packed[start:start+entry['compressed']]
        assert entry['compression']==8;raw=zlib.decompress(raw,-15)
        destination.write_bytes(raw)
    assert len(raw)==entry['size']and zlib.crc32(raw)==entry['crc32']
    gltf=json.loads(raw);corners=[]
    def walk(index,parent):
        node=gltf['nodes'][index];assert not any(key in node for key in ['translation','rotation','scale'])
        matrix=parent@np.array(node.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F')
        if'mesh'in node:
            for primitive in gltf['meshes'][node['mesh']]['primitives']:
                accessor=gltf['accessors'][primitive['attributes']['POSITION']]
                points=np.array(list(itertools.product(*zip(accessor['min'],accessor['max']))))
                corners.extend((points@matrix[:3,:3].T+matrix[:3,3]).tolist())
        for child in node.get('children',[]):walk(child,matrix)
    outer=np.eye(4);outer[:3,3]=[-844800,0,820500]
    for index in gltf['scenes'][gltf.get('scene',0)]['nodes']:walk(index,outer)
    lo=np.min(corners,0);hi=np.max(corners,0);rectangle=box(lo[0],lo[2],hi[0],hi[2])
    matches=[{'canonicalId':eid,'bboxDomainRatio':rectangle.intersection(domain).area/domain.area}for eid,domain in domains.items()if rectangle.intersection(domain).area>1]
    prefix=name.rsplit('/',1)[0]+'/'
    files=[{'name':n,**e}for n,e in entries.items()if n.startswith(prefix)and not n.endswith('/')]
    result={'id':oid,'sheet':sheet,'url':url,'sourceLevelCode':oid[-3:-1],
        'sourceJsonSha256':hashlib.sha256(raw).hexdigest(),'metadata':str(destination),
        'boundsFromAccessorExtrema':{'min':lo.tolist(),'max':hi.tolist()},'candidateMatches':matches,
        'files':files,'sourceEncodedBytes':sum(f['size']for f in files),'sourceCompressedBytes':sum(f['compressed']for f in files)}
    print(oid,[(m['canonicalId'],round(m['bboxDomainRatio'],3))for m in matches],result['sourceEncodedBytes'],flush=True)
    return result

items=[(name,e)for name,e in entries.items()if name.startswith('BUILDING/')and name.endswith('.gltf')]
count=len(items)
if count>40:
    # This published source-family coordinate encoding only bounds metadata
    # acquisition near existing named domains. Actual node+triangles still decide
    # location and ownership. Never manufacture a building from these digits.
    nearby=[]
    for name,entry in items:
        match=re.match(r'B(\d{5})(\d{5})',name.split('/')[1])
        if match:
            point=Point(800000+int(match[1])-844800,820500-(800000+int(match[2])))
            if any(domain.distance(point)<120 for domain in domains.values()):nearby.append((name,entry))
    items=nearby
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
    results=list(pool.map(job,items))
report={'status':'metadata-candidate-only','sourceSheetMetadata':source,'candidates':results,
    'sheetBuildingObjects':count,'retrievedMetadataObjects':len(results),
    'limits':'OriginalPOSITION accessor extrema through original nodes only bound candidate retrieval. Complete originalBIN/UV/images and actual triangles must establish source coverage before any building binding.'}
suffix=''if sheet=='12-NW-6A'else'-'+sheet
(D/('metadata-candidates'+suffix+'.json')).write_text(json.dumps(report,indent=2)+'\n')
(P/('docs/source-evidence-v4/building-quality/northern-individual-source-candidates'+suffix+'.json')).write_text(json.dumps(report,indent=2)+'\n')
