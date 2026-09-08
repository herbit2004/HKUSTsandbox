#!/usr/bin/env python3
"""Stage complete authoritative subtrees for the Hall II uphill covered walk.

No runtime files are modified. Selection starts with the observed entire walk
and both connections, then retains every leaf of each intersecting L18 owner.
Original ZIP bytes, GLB payload, node transforms, UVs and image bytes are kept.
"""
import argparse
import concurrent.futures
import hashlib
import io
import itertools
import json
from pathlib import Path
import struct
import sys
import time
import urllib.request
import zlib

import numpy as np
from PIL import Image
from shapely.geometry import Polygon, box
from hkust_source_geometry import geometry


SUBTILES = ['12-NW-6C-3', '12-NW-6C-4', '12-NW-6C-8', '12-NW-6C-9']
# A source-selection AOI, NOT a new cadastral domain or road-width measurement.
CORRIDOR_BOUNDS = [607., -1560., 679., -1538.]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def read(path):
    return json.loads(path.read_text())


def descendants(node, threshold):
    if 'content' in node and (node.get('geometricError', 0) <= threshold or not node.get('children')):
        return [node]
    return [leaf for child in node.get('children', []) for leaf in descendants(child, threshold)]


def projected_bounds(node, matrix):
    volume = node['boundingVolume']
    b = np.array(volume.get('box', volume.get('sphere')), float)
    assert len(b) == 12, 'Expected preserved source box (legacy sphere field contains 12 values)'
    corners = np.array([b[:3]+np.array(s)@b[3:].reshape(3,3) for s in itertools.product([-1,1], repeat=3)])
    world = corners@matrix[:3,:3].T+matrix[:3,3]
    return Polygon(world[:, [0,2]]).convex_hull


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/hkust-hall-2-corridor-source'))
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--audit', action='store_true', help='Also save actual source vertical intersections and corridor triangles; never fills source holes')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    assert not out.is_relative_to(project/'public')
    out.mkdir(parents=True, exist_ok=True)
    source = project/'source-geodata/mesh/12-NW-6C'
    index = read(source/'source-zip-index.json')
    source_url = read(source/'subset-manifest.json')['source']
    baselines = read(project/'public/models/render-manifest.json')['tiles']
    live_path = project/'public/models/hires/manifest.json'
    live = read(live_path)
    live_tiles = {t['id']:t for p in live['patches'] for level in p['levels'].values() for t in level['tiles']}
    aoi = box(*CORRIDOR_BOUNDS)
    owners, jobs = [], {}
    for sub in SUBTILES:
        baseline = next(t for t in baselines if '/'+sub+'/' in t['id'])
        matrix = np.array(baseline['matrix']).reshape(4,4,order='F')
        tree_path = source/sub/'source-tileset.json'
        tree = read(tree_path)
        def walk(node, ancestors):
            uri = node.get('content',{}).get('uri')
            chain = ancestors+([Path(uri).stem] if uri else [])
            if uri and '_L18_' in uri:
                if not projected_bounds(node,matrix).intersects(aoi):
                    return
                owner_id = 'native-12-NW-6C_'+sub+'_'+Path(uri).stem
                levels = {}
                for level, threshold in [('high',1.75),('fine',0)]:
                    frontier = descendants(node,threshold)
                    assert frontier, owner_id
                    if level == 'fine':
                        assert all(not n.get('children') and n.get('geometricError',0)==0 for n in frontier)
                    names = [n['content']['uri'] for n in frontier]
                    assert len(names) == len(set(names))
                    for n in frontier:
                        name = n['content']['uri'];key = sub+'/'+name
                        assert key in index, f'Missing original ZIP sibling: {key}'
                        if key not in jobs:
                            jobs[key] = {'sub':sub,'name':name,'node':n,'matrix':baseline['matrix'],'baselineId':baseline['id']}
                    levels[level] = names
                owners.append({'id':owner_id,'sub':sub,'node':node,'sourceAncestor':'12-NW-6C/'+sub+'/'+Path(uri).stem,'levels':levels,'baseline':baseline,'sourceTree':str(tree_path.relative_to(project)),'sourceTreeSha256':sha(tree_path.read_bytes()),'sourceAncestors':chain[:-1]})
                return
            for child in node.get('children',[]):
                walk(child,chain)
        walk(tree['root'],[])
    total = sum(index[k]['size'] for k in jobs)
    assert total < 80*1024**2, 'Bounded preparation exceeds 80MiB source payload review guard'
    plan = {'status':'bounded-source-plan','sourceURL':source_url,'selectionBoundsXZ':CORRIDOR_BOUNDS,'sourcePayloadBytes':total,'uniquePayloads':len(jobs),'owners':[{'id':o['id'],'alreadyRuntime':any(p['id']==o['id'] for p in live['patches']),'highFiles':len(o['levels']['high']),'fineFiles':len(o['levels']['fine'])}for o in owners],'sourceIndexSHA256':sha((source/'source-zip-index.json').read_bytes()),'runtimeManifestSHA256':sha(live_path.read_bytes()),'guard':'No missing source siblings accepted; complete original subtree for each selected owner; 80MiB compressed/source payload bound, no all-campus download.'}
    write_json(out/'plan.json',plan)
    print(json.dumps(plan,indent=2),flush=True)
    if args.plan_only:
        return

    def acquire(key):
        job = jobs[key];en = index[key]
        raw_path = out/'source-b3dm'/job['sub']/job['name'];raw_path.parent.mkdir(parents=True,exist_ok=True)
        existing = live_tiles.get('12-NW-6C/'+job['sub']+'/'+Path(job['name']).stem)
        candidates = [raw_path, source/job['sub']/job['name']]
        if existing:
            for field in ['sourceB3dmPath','sourceB3dmCachePath','sourceB3dmRelativePath']:
                if existing.get(field):
                    p = Path(existing[field]);candidates.append(p if p.is_absolute() else project/p)
        data = None
        reused = None
        for candidate in candidates:
            if candidate.exists():
                value = candidate.read_bytes()
                if len(value)==en['size'] and zlib.crc32(value)==en['crc32']:
                    data,reused = value,str(candidate);break
        if data is None:
            for attempt in range(4):
                try:
                    request = urllib.request.Request(source_url, headers={'Range':f"bytes={en['offset']}-{en['offset']+en['compressed']+1024}"})
                    with urllib.request.urlopen(request,timeout=35) as response:
                        assert response.status==206, 'Server ignored bounded ZIP range'
                        compressed=response.read()
                    head=struct.unpack_from('<4s5H3L2H',compressed)
                    assert head[0]==b'PK\x03\x04'
                    offset=30+head[-1]+head[-2]
                    payload=compressed[offset:offset+en['compressed']]
                    data=zlib.decompress(payload,-15) if en['compression']==8 else payload
                    assert len(data)==en['size'] and zlib.crc32(data)==en['crc32']
                    break
                except Exception:
                    if attempt==3:raise
                    time.sleep(attempt+1)
        raw_path.write_bytes(data)
        head=struct.unpack_from('<4s6I',data)
        assert head[0]==b'b3dm' and head[2]==len(data)
        glb=data[28+sum(head[3:]):]
        assert glb[:4]==b'glTF' and struct.unpack_from('<I',glb,8)[0]==len(glb)
        path=out/'source'/'12-NW-6C'/job['sub']/Path(job['name']).with_suffix('.glb')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(glb)
        n=struct.unpack_from('<I',glb,12)[0];g=json.loads(glb[20:20+n]);binary=glb[28+n:]
        textures=[]
        for im in g.get('images',[]):
            v=g['bufferViews'][im['bufferView']];encoded=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
            with Image.open(io.BytesIO(encoded)) as picture:
                width,height=picture.size;picture.load()
            w,h=width,height;mips=0
            while True:
                mips+=w*h*4
                if w==h==1:break
                w,h=max(1,w//2),max(1,h//2)
            textures.append({'width':width,'height':height,'encodedBytes':len(encoded),'mipBytes':mips,'sha256':sha(encoded)})
        assert all('TEXCOORD_0' in p['attributes'] for m in g['meshes'] for p in m['primitives'])
        T,_=geometry(path,np.array(job['matrix']).reshape(4,4,order='F'))
        assert np.isfinite(T).all()
        lo,hi=T.min(axis=(0,1)),T.max(axis=(0,1))
        record={'id':'12-NW-6C/'+job['sub']+'/'+path.stem,'url':str(path.relative_to(out)),'localPath':str(path),'sourceB3dmPath':str(raw_path),'sourceUrl':source_url,'sourceZipName':key,'sourceZipCRC32':en['crc32'],'sourceZipOffset':en['offset'],'sourceB3dmSha256':sha(data),'sha256':sha(glb),'matrix':job['matrix'],'matrixSourceBaselineId':job['baselineId'],'originalError':job['node'].get('geometricError',0),'terminalLeaf':not bool(job['node'].get('children')),'bounds':{'min':lo.tolist(),'max':hi.tolist()},'center':((lo+hi)/2).tolist(),'triangles':len(T),'vertices':sum(g['accessors'][p['attributes']['POSITION']]['count']for m in g['meshes']for p in m['primitives']),'bytes':len(glb),'sourceB3dmBytes':len(data),'textureMipBytes':sum(t['mipBytes']for t in textures),'textureBytes':sum(t['width']*t['height']*4 for t in textures),'textureEncodedBytes':sum(t['encodedBytes']for t in textures),'textureDimensions':[[t['width'],t['height']]for t in textures],'textures':textures,'allUvPresent':True,'reusedVerifiedB3dm':reused,'sourcePreservation':'GLB byte-for-byte extracted from ZIP-CRC-verified original b3dm; all original XYZ, index, node matrix, UV and encoded image payloads retained.'}
        return key,record,T

    tiles,triangles = {},{}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for done,(key,record,T) in enumerate(pool.map(acquire,jobs),1):
            tiles[key]=record;triangles[key]=T
            if done%10==0:print('verified source payloads',done,'/',len(jobs),flush=True)

    def mask_for(id,level,T):
        lo=T.min(axis=(0,1));hi=T.max(axis=(0,1));x0,z0=np.floor(lo[[0,2]]*2)/2;x1,z1=np.ceil(hi[[0,2]]*2)/2
        w,h=int(round((x1-x0)*2)),int(round((z1-z0)*2));mask=np.zeros((h,w),np.uint8)
        for t in T:
            a,b,c=t[:,[0,2]];den=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(den)<1e-12:continue
            lower=np.ceil((t[:,[0,2]].min(0)-[x0,z0])*2-.5-1e-9).astype(int);upper=np.floor((t[:,[0,2]].max(0)-[x0,z0])*2-.5+1e-9).astype(int)
            c0,r0=max(0,lower[0]),max(0,lower[1]);c1,r1=min(w-1,upper[0]),min(h-1,upper[1])
            if c0>c1 or r0>r1:continue
            xx,zz=np.meshgrid(x0+(np.arange(c0,c1+1)+.5)/2,z0+(np.arange(r0,r1+1)+.5)/2)
            dx,dz=xx-a[0],zz-a[1];u=(dx*(c[1]-a[1])-dz*(c[0]-a[0]))/den;v=((b[0]-a[0])*dz-(b[1]-a[1])*dx)/den
            mask[r0:r1+1,c0:c1+1][(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)]=255
        path=out/'masks'/f'{id}-{level}.png';path.parent.mkdir(exist_ok=True);Image.fromarray(mask).save(path)
        return {'url':str(path.relative_to(out)),'minX':x0,'minZ':z0,'maxX':x1,'maxZ':z1,'width':w,'height':h,'pixelSizeMeters':.5,'coveredPixels':int((mask>0).sum()),'sha256':sha(path.read_bytes()),'rowDirection':'increasing local Z','projection':'Actual complete-frontier source triangle pixel-centre projection; no rectangle/hull/dilation fill.'}

    patches=[]
    for owner in owners:
        levels={}
        for name in ['high','fine']:
            keys=[owner['sub']+'/'+u for u in owner['levels'][name]]
            selected=[tiles[k] for k in keys];T=np.concatenate([triangles[k]for k in keys]);lo,hi=T.min(axis=(0,1)),T.max(axis=(0,1))
            levels[name]={'maximumOriginalError':max(t['originalError']for t in selected),'completeSelectedSubtree':True,'tiles':selected,'bounds':{'min':lo.tolist(),'max':hi.tolist()},'triangles':len(T),'bytes':sum(t['bytes']for t in selected),'textureBytes':sum(t['textureBytes']for t in selected),'textureMipBytes':sum(t['textureMipBytes']for t in selected),'mask':mask_for(owner['id'],name,T),'geometricErrorMax':max(t['originalError']for t in selected),'frontier':'Complete original subtree: '+('all terminal error0 leaves'if name=='fine'else'first source frontier at error <=1.75m')}
        lo=np.minimum(levels['high']['bounds']['min'],levels['fine']['bounds']['min']);hi=np.maximum(levels['high']['bounds']['max'],levels['fine']['bounds']['max'])
        patches.append({'id':owner['id'],'sourceAncestor':owner['sourceAncestor'],'sourceOriginalTree':owner['sourceTree'],'sourceOriginalTreeSha256':owner['sourceTreeSha256'],'baselineIds':[owner['baseline']['id']],'partial':True,'bounds':{'min':lo.tolist(),'max':hi.tolist()},'center':((lo+hi)/2).tolist(),'levels':levels,'mask':levels['high']['mask'],'sourceFrontier':{'completeSelectedSubtree':True,'fineMaximumOriginalError':0,'fineTerminalCount':len(levels['fine']['tiles']),'highMaximumOriginalError':levels['high']['maximumOriginalError']}})
    metadata={'version':1,'status':'isolated source preparation, not installed or visually accepted','coordinateSystem':live['coordinateSystem'],'source':live['source'],'selection':plan,'patches':patches,'changesToSource':'None. Only lossless b3dm embedded GLB extraction and separate exact matrix descriptors. No bridge, terrain plane, texture resize or gap geometry generated.'}
    write_json(out/'manifest.json',metadata)
    costs={name:{'triangles':sum(p['levels'][name]['triangles']for p in patches),'glbBytes':sum(p['levels'][name]['bytes']for p in patches),'textureMipBytes':sum(p['levels'][name]['textureMipBytes']for p in patches),'maskBytesR8':sum(p['levels'][name]['mask']['width']*p['levels'][name]['mask']['height']for p in patches)}for name in ['high','fine']}
    write_json(out/'source-preparation.json',{'status':'stage-ready','owners':len(patches),'uniqueSourcePayloads':len(tiles),'sourceBytes':total,'newlyFetchedPayloads':sum(t['reusedVerifiedB3dm']is None for t in tiles.values()),'frontierCosts':costs,'perOwnerCosts':[{'id':p['id'],'alreadyRuntime':any(q['id']==p['id']for q in live['patches']),'highTextureMipBytes':p['levels']['high']['textureMipBytes'],'fineTextureMipBytes':p['levels']['fine']['textureMipBytes']}for p in patches],'boundsXZ':CORRIDOR_BOUNDS,'manifestSHA256':sha((out/'manifest.json').read_bytes()),'limitations':['Selected source volumes conservatively cover the entire observed covered walk and both endpoints; source surface/roof continuity must be checked independently before installation.','No runtime owner changes or scene/planner changes are made. Existing source-owner IDs must be reused rather than double-installed.','Source revision date is not a capture date, and XZ coverage alone does not establish navigability or continuous roof height.']})
    print('READY',str(out/'manifest.json'),json.dumps(costs),flush=True)
    if args.audit:
        audit_corridor(project,out,patches)


def audit_corridor(project,out,patches):
    """Intersections are source evidence, not inferred roof/deck surfaces."""
    tiles=list({t['id']:t for p in patches for t in p['levels']['fine']['tiles']}.values())
    all_triangles=[];source_ids=[];triangle_ids=[]
    for i,tile in enumerate(tiles):
        T,_=geometry(out/tile['url'],np.array(tile['matrix']).reshape(4,4,order='F'))
        lo,hi=T.min(1),T.max(1)
        selected=np.flatnonzero((hi[:,0]>=605)&(lo[:,0]<=708)&(hi[:,2]>=-1564)&(lo[:,2]<=-1535))
        all_triangles.append(T[selected]);source_ids.extend([i]*len(selected));triangle_ids.extend(selected.tolist())
    T=np.concatenate(all_triangles);source_ids=np.array(source_ids,np.uint32);triangle_ids=np.array(triangle_ids,np.uint32)
    normals=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]);length=np.linalg.norm(normals,axis=1);normals/=np.maximum(length[:,None],1e-30)
    np.savez_compressed(out/'corridor-triangles.npz',positions=T,normals=normals,sourceTileIndex=source_ids,triangleIndex=triangle_ids)
    write_json(out/'corridor-triangle-sources.json',tiles)
    lo,hi=T.min(1),T.max(1)
    def hits(x,z):
        ix=np.flatnonzero((lo[:,0]<=x)&(hi[:,0]>=x)&(lo[:,2]<=z)&(hi[:,2]>=z))
        a,b,c=T[ix,0],T[ix,1],T[ix,2]
        den=(b[:,0]-a[:,0])*(c[:,2]-a[:,2])-(b[:,2]-a[:,2])*(c[:,0]-a[:,0])
        inv=np.zeros(len(ix));valid=abs(den)>1e-12;inv[valid]=1/den[valid]
        u=((x-a[:,0])*(c[:,2]-a[:,2])-(z-a[:,2])*(c[:,0]-a[:,0]))*inv
        v=((b[:,0]-a[:,0])*(z-a[:,2])-(b[:,2]-a[:,2])*(x-a[:,0]))*inv
        y=a[:,1]+u*(b[:,1]-a[:,1])+v*(c[:,1]-a[:,1])
        valid &= (u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)
        result=[]
        for j in np.flatnonzero(valid)[np.argsort(y[valid])]:
            at=ix[j]
            if result and abs(result[-1]['y']-float(y[j]))<.005:continue
            result.append({'y':float(y[j]),'normalY':float(normals[at,1]),'sourceTileIndex':int(source_ids[at]),'triangleIndex':int(triangle_ids[at])})
        return result
    grid=read(project/'public/terrain/height-grid-5m.json')
    write_json(out/'ground-source-reference.json',{'path':'public/terrain/height-grid-5m.json','sha256':sha((project/'public/terrain/height-grid-5m.json').read_bytes()),'schemaKeys':list(grid),'use':'Separate bare-earth reference; not a bridge-deck height or generated ground plane.'})
    profiles=[]
    for z in [-1552.,-1550.5,-1549.,-1547.,-1545.]:
        profiles.append({'z':z,'samples':[{'x':float(x),'hits':hits(x,z)}for x in np.arange(610,706.01,.5)]})
    write_json(out/'height-profiles.json',{'coordinateMeaning':'x/z exact original local world placement; y original native source datum. Every hit is an actual triangle intersection. Multiple hits are kept; neither a top hit nor an upward face is automatically a walkable deck.','profiles':profiles,'sourceFile':'corridor-triangle-sources.json','triangleNPZ':'corridor-triangles.npz','sourceTriangleCount':len(T)})
    sections=[]
    for x in [630.,635.,645.,655.,665.,670.,671.,672.,673.,685.,700.]:
        segments=[]
        for i in np.flatnonzero((lo[:,0]<=x)&(hi[:,0]>=x)&(hi[:,1]>=60)&(lo[:,1]<=83)):
            points=[]
            for j,k in [(0,1),(1,2),(2,0)]:
                a,b=T[i,j],T[i,k]
                if abs(b[0]-a[0])<1e-10:continue
                u=(x-a[0])/(b[0]-a[0])
                if -1e-9<=u<=1+1e-9:
                    q=a+u*(b-a)
                    if not any(np.linalg.norm(q-p)<1e-7 for p in points):points.append(q)
            if len(points)==2 and max(p[1] for p in points)>=60 and min(p[1]for p in points)<=83:
                segments.append({'points':[p.tolist()for p in points],'sourceTileIndex':int(source_ids[i]),'triangleIndex':int(triangle_ids[i])})
        sections.append({'x':x,'segments':segments})
    write_json(out/'cross-sections.json',{'method':'Exact source-triangle intersection with fixed local X planes; only segments intersecting the 60..83m vertical band are retained. No section lines joined or gap-closing segments invented.','sections':sections})
    floor_manifest=read(project/'public/interiors/manifest.json')
    floors=[f for f in floor_manifest['floors']if f['buildingName']in['UG Hall I','UG Hall II']]
    write_json(out/'floor-source-references.json',{'floors':[{**f,'localPath':'public/interiors/'+f['url'],'sha256':sha((project/'public/interiors'/f['url']).read_bytes())}for f in floors],'limits':'Hall I G source Z=65.0 and Hall II 11 source Z=65.2 are drawing floor datums, not measured camera heights or permission to interpolate a bridge deck. Published room outlines do not themselves survey the entire bridge.'})
    # Half-metre roof-band preview: raw hit colours only, no interpolated hole fill.
    x0,z0,step=605.,-1564.,.5;w,h=206,58;top=np.full((h,w),np.nan)
    for row in range(h):
        for col in range(w):
            heights=[p['y']for p in hits(x0+(col+.5)*step,z0+(row+.5)*step)if 60<=p['y']<=83]
            if heights:top[row,col]=max(heights)
    np.savez_compressed(out/'roof-band-grid.npz',top=top,x0=x0,z0=z0,step=step)
    rgb=np.full((h,w,3),235,np.uint8);ok=np.isfinite(top);q=np.clip((top[ok]-64)/8,0,1);rgb[ok]=np.stack([50+180*q,170-90*q,220-160*q],axis=1).astype(np.uint8)
    Image.fromarray(rgb).resize((w*6,h*6),Image.Resampling.NEAREST).save(out/'roof-band-grid.png')
    write_json(out/'audit-contract.json',{'status':'raw-source-evidence-not-a-repair','triangles':len(T),'trianglesSHA256':sha((out/'corridor-triangles.npz').read_bytes()),'profilesSHA256':sha((out/'height-profiles.json').read_bytes()),'heightBandPreview':[60,83],'grid':{'x0':x0,'z0':z0,'step':step,'width':w,'height':h},'limitations':['Empty roof-band cells remain empty; high/fine completeness does not repair absent geometry.','No inferred bridge profile, floor slab, side openings, posts or transition plane generated.','See the independent source-audit report for the existing cuboid and Hall II endpoint void.']})


if __name__=='__main__':main()
