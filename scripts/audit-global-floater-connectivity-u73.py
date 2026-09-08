#!/usr/bin/env python3
"""Read-only global face-connectivity audit for the Hall X-XIII preview tiles."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "public/models"
FORMS = MODELS / "current-forms/ivillage-rebuild"
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants"
SCOPE = (571.0, -1171.5, 793.5, -1009.0)
Q = 1e-5

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read_glb(p):
    raw=p.read_bytes(); mark=raw.find(b"BIN\x00")
    j=json.JSONDecoder().raw_decode(raw[20:mark-4].decode('utf8').rstrip(' \0'))[0]
    return j,raw,mark+4
def accessor(doc,raw,start,i):
    a=doc['accessors'][i]; v=doc['bufferViews'][a['bufferView']]
    w={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    dt={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
    item=np.dtype(dt).itemsize; base=start+v.get('byteOffset',0)+a.get('byteOffset',0)
    stride=v.get('byteStride',item*w)
    return np.ndarray((a['count'],w),dtype=dt,buffer=raw,offset=base,strides=(stride,item)).copy()
def world(m,p):
    a=np.asarray(m,float).reshape(4,4,order='F'); return (np.c_[p,np.ones(len(p))]@a.T)[:,:3]
def pinpoly(x,z,poly):
    inside=False; j=len(poly)-1
    for i,(xi,zi) in enumerate(poly):
        xj,zj=poly[j]
        if ((zi>z)!=(zj>z)) and x < (xj-xi)*(z-zi)/((zj-zi) or 1e-30)+xi: inside=not inside
        j=i
    return inside
def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def cross(a,b,c,d):
    e=1e-9; o=(orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b))
    return ((o[0]*o[1]<=e*e) and (o[2]*o[3]<=e*e))
def bbox_poly(poly,lo,hi):
    if any(lo[0]<=x<=hi[0] and lo[1]<=z<=hi[1] for x,z in poly): return True
    if any(pinpoly(x,z,poly) for x,z in [(lo[0],lo[1]),(lo[0],hi[1]),(hi[0],lo[1]),(hi[0],hi[1])]): return True
    box=[(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])]
    return any(cross(tuple(a),tuple(b),c,d) for a,b in zip(poly,poly[1:]+poly[:1]) for c,d in zip(box,box[1:]+box[:1]))
def dtm(points,g):
    east=g['origin']['easting']+points[:,0]; north=g['origin']['northing']-points[:,2]
    col=(east-g['first_easting'])/g['easting_step']; row=(north-g['first_northing'])/g['northing_step']; out=np.full(len(points),np.nan)
    n=int(g['columns']); ok=(row>=0)&(row<g['rows']-1)&(col>=0)&(col<n-1)
    for i in np.where(ok)[0]:
        r=int(np.floor(row[i])); c=int(np.floor(col[i])); fr=row[i]-r; fc=col[i]-c
        a=np.array([g['heights'][r*n+c],g['heights'][r*n+c+1],g['heights'][(r+1)*n+c],g['heights'][(r+1)*n+c+1]])
        out[i]=a[0]*(1-fc)*(1-fr)+a[1]*fc*(1-fr)+a[2]*(1-fc)*fr+a[3]*fc*fr
    return out
def mask_hits(desc,pix,pts):
    x0,z0=desc['boundsXZ']['min']; s=float(desc['pixelSizeMeters']); c=np.floor((pts[:,0]-x0)/s).astype(int); r=np.floor((pts[:,2]-z0)/s).astype(int)
    out=np.zeros(len(pts),bool); ok=(r>=0)&(r<pix.shape[0])&(c>=0)&(c<pix.shape[1]); rgba=pix[r[ok],c[ok]]
    lower=np.where(rgba[:,3]==255,float(desc['replacementMinY']),np.maximum(float(desc['replacementMinY']),rgba[:,3])); out[ok]=(rgba[:,0]>=128)&(pts[ok,1]>=lower)&(pts[ok,1]<=float(desc['replacementMaxY'])); return out
def main():
    mp=MODELS/'preview-manifest.json'; manifest=json.loads(mp.read_text()); selected=[]
    for ti,t in enumerate(manifest['tiles']):
        b=t['bounds']
        if not (b['max'][0]<SCOPE[0] or b['min'][0]>SCOPE[2] or b['max'][2]<SCOPE[1] or b['min'][2]>SCOPE[3]): selected.append((ti,t))
    # Gather every face from all selected primitives into one global vertex table.
    faces=[]; tile_face_counts={}; loaded=[]
    for ti,t in selected:
        p=MODELS/t['url']; doc,raw,start=read_glb(p); n0=len(faces); local=0
        for mi,mesh in enumerate(doc['meshes']):
            for pi,pr in enumerate(mesh['primitives']):
                if pr.get('mode',4)!=4: continue
                pos=world(t['matrix'],accessor(doc,raw,start,pr['attributes']['POSITION'])); ix=accessor(doc,raw,start,pr['indices']).ravel().reshape(-1,3)
                for fi,tr in enumerate(ix):
                    tri=pos[tr]; faces.append({'tileIndex':ti,'sourceId':t['id'],'url':t['url'],'tileSha256':t.get('sha256'),'glbSha256':sha(p),'meshIndex':mi,'primitiveIndex':pi,'localFace':fi,'tri':tri})
                    local+=1
        tile_face_counts[str(ti)]=local; loaded.append({'tileIndex':ti,'id':t['id'],'url':t['url'],'sha256':sha(p),'manifestSha256':t.get('sha256')})
    # DSU faces through ANY shared quantized world vertex, across every primitive/tile.
    parent=list(range(len(faces))); buckets={}
    for fi,f in enumerate(faces):
        for v in np.rint(f['tri']/Q).astype(np.int64): buckets.setdefault(tuple(map(int,v)),[]).append(fi)
    def root(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    for ids in buckets.values():
        r=root(ids[0])
        for x in ids[1:]: parent[root(x)]=r
    comps={}
    for i in range(len(faces)): comps.setdefault(root(i),[]).append(i)
    form=json.loads((FORMS/'manifest.json').read_text()); geom=json.loads((FORMS/'evidence/geometry.json').read_text()); grid=json.loads((ROOT/'public/terrain/height-grid-5m.json').read_text());
    terrain=np.asarray(grid['heights'],float); members=[]
    for m in form['members']:
        members.append((m,np.asarray(Image.open(FORMS/m['mask']['url']).convert('RGBA'))))
    official=[(b['catalogId'],b['envelopeParts'][0]['rings'][0]) for b in geom['buildings']]
    prot_desc=form['sourceProtection']; prot=np.frombuffer((FORMS/prot_desc['url']).read_bytes(),np.uint8).reshape(prot_desc['height'],prot_desc['width'],4)
    records=[]
    for ci,ids in enumerate(comps.values()):
        tris=np.asarray([faces[i]['tri'] for i in ids]); lo=tris.min((0,1)); hi=tris.max((0,1));
        if hi[0]<SCOPE[0] or lo[0]>SCOPE[2] or hi[2]<SCOPE[1] or lo[2]>SCOPE[3]: continue
        centers=tris.mean(1); gaps=centers[:,1]-dtm(centers,grid); area=np.linalg.norm(np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0]),axis=1)/2
        normals=np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0]); norms=np.linalg.norm(normals,axis=1); normals[:,1]=np.divide(normals[:,1],norms,out=np.zeros(len(norms)),where=norms>0)
        probes=np.r_[centers,tris.reshape(-1,3)]; cur=[m['catalogId'] for m,pix in members if mask_hits(m['mask'],pix,probes).any()]
        pi=np.floor((centers[:,0]-prot_desc['boundsXZ']['min'][0])/prot_desc['pixelSizeMeters']).astype(int); ri=np.floor((centers[:,2]-prot_desc['boundsXZ']['min'][1])/prot_desc['pixelSizeMeters']).astype(int); ok=(ri>=0)&(ri<prot.shape[0])&(pi>=0)&(pi<prot.shape[1]); ph=int(np.count_nonzero(ok & (prot[np.clip(ri,0,prot.shape[0]-1),np.clip(pi,0,prot.shape[1]-1),0]>=1)))
        oi=[n for n,p in official if bbox_poly(p,lo[[0,2]],hi[[0,2]])]; oc=[n for n,p in official if pinpoly(float(centers.mean(0)[0]),float(centers.mean(0)[2]),p)]
        finite=gaps[np.isfinite(gaps)]; elevated=bool(len(finite) and np.nanpercentile(gaps,5)>2); small=bool(len(ids)<=120 and area.sum()<=50 and max(hi[0]-lo[0],hi[2]-lo[2])<=8 and hi[1]-lo[1]<=8)
        # No checked-in evidence proves that an unowned elevated patch is not
        # corridor, tree canopy, slope/retaining surface, roof fitting, or
        # another intentional source surface.  Therefore this audit never
        # grants deletion approval from numerical gates alone.
        semantic_exclusion='unproven-corridor-tree-canopy-slope-owner'
        safe=False
        records.append({'componentIndex':ci,'faceCount':len(ids),'faces':[{'tileIndex':faces[i]['tileIndex'],'sourceId':faces[i]['sourceId'],'meshIndex':faces[i]['meshIndex'],'primitiveIndex':faces[i]['primitiveIndex'],'localFace':faces[i]['localFace'],'worldFaceIndex':i} for i in ids],'bounds':{'min':lo.tolist(),'max':hi.tolist()},'areaSquareMeters':float(area.sum()),'dtmGapMeters':{'min':float(np.nanmin(finite)) if len(finite) else None,'p05':float(np.nanpercentile(finite,5)) if len(finite) else None,'median':float(np.nanmedian(finite)) if len(finite) else None,'max':float(np.nanmax(finite)) if len(finite) else None},'currentFormMaskHits':cur,'officialBuildingProtectionHits':oi,'officialBuildingCentroidHits':oc,'sourceProtectionFaceCount':ph,'areaWeightedAboveDtmFraction':float(np.average(gaps>2,weights=np.maximum(area,1e-12))),'areaWeightedGroundLikeFraction':float(np.average((np.abs(gaps)<=2)&(np.abs(normals[:,1])>=.6),weights=np.maximum(area,1e-12))),'smallIsolatedElevated':small and elevated,'semanticExclusion':semantic_exclusion,'safeToDelete':safe,'disposition':'retain-review'})
    candidates=[r for r in records if r['smallIsolatedElevated']]; safe=[r for r in candidates if r['safeToDelete']]
    out={'status':'audit-complete-no-runtime-write','task':'U73 global floater connectivity across actual Hall X-XIII preview tiles','algorithm':{'quantizationMeters':Q,'connectivity':'DSU over all triangle faces; faces union when any quantized world-coordinate vertex is shared, across primitives and tiles','triangleZeroGroupingReused':False},'scope':{'boundsXZ':list(SCOPE),'selectedTileIndices':[i for i,_ in selected]},'inputs':{'previewManifest':str(mp),'previewManifestSha256':sha(mp),'selectedTiles':loaded,'currentFormManifest':str(FORMS/'manifest.json'),'currentFormManifestSha256':sha(FORMS/'manifest.json'),'officialGeometry':str(FORMS/'evidence/geometry.json'),'officialGeometrySha256':sha(FORMS/'evidence/geometry.json'),'dtm':str(ROOT/'public/terrain/height-grid-5m.json'),'dtmSha256':sha(ROOT/'public/terrain/height-grid-5m.json'),'sourceProtectionMask':str(FORMS/prot_desc['url']),'sourceProtectionMaskSha256':sha(FORMS/prot_desc['url'])},'counts':{'selectedTiles':len(selected),'globalFaces':len(faces),'globalComponentsIntersectingScope':len(records),'smallIsolatedElevatedCandidates':len(candidates),'safeToDelete':len(safe)},'thresholds':{'maxFaces':120,'maxAreaSquareMeters':50,'maxHorizontalSpanMeters':8,'maxVerticalSpanMeters':8,'minP05DtmGapMeters':2,'protectionRule':'any current-form mask, official envelope, or source-protection hit blocks safe deletion'},'candidates':candidates,'safeToDeleteCandidates':safe,'allIntersectingComponents':records,'writes':{'runtimeManifestModified':False,'glbModified':False,'sourceTrianglesDeleted':0}}
    jp=OUT/'global-floater-connectivity-u73.json'; md=OUT/'global-floater-connectivity-u73.md'; jp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    lines=['# Hall X–XIII 全局浮空面连通性审计（U73）','','只读审计；未修改生产 GLB、preview manifest、current-form manifest 或运行时代码。','',f'- 当前 preview manifest 实际选中瓦片：{len(selected)}（{", ".join(str(i) for i,_ in selected)}）',f'- 全局面数：{len(faces)}；跨 primitive/tile 连通分量：{len(records)}；小型且整体高于 DTM 候选：{len(candidates)}；safeToDelete：{len(safe)}','- 连通算法：所有面统一到世界坐标，顶点按 1e-5 m 量化；共享任意顶点的面通过 DSU union，跨 primitive、跨 tile 生效。','', '|候选分量|面数|tile / primitive / face|bounds|面积 m²|DTM gap min/p05/med/max|保护域命中|safeToDelete|','|---|---:|---|---|---:|---|---|---|']
    for r in candidates:
        f='; '.join(f"t{a['tileIndex']}/p{a['primitiveIndex']}/f{a['localFace']}" for a in r['faces'][:12]);
        if len(r['faces'])>12:f+=f'; …（共{len(r["faces"])}面）'
        b=r['bounds'];g=r['dtmGapMeters']; hits=', '.join(r['currentFormMaskHits']+r['officialBuildingProtectionHits']) or ('source-protection:'+str(r['sourceProtectionFaceCount']) if r['sourceProtectionFaceCount'] else 'none')
        lines.append(f"| C{r['componentIndex']}|{r['faceCount']}|{f}|[{b['min'][0]:.3f},{b['min'][1]:.3f},{b['min'][2]:.3f}] → [{b['max'][0]:.3f},{b['max'][1]:.3f},{b['max'][2]:.3f}]|{r['areaSquareMeters']:.3f}|{g['min']:.3f}/{g['p05']:.3f}/{g['median']:.3f}/{g['max']:.3f}|{hits}|{'是' if r['safeToDelete'] else '否'}|")
    lines += ['', '## 结论', '', f'本次全局连通性审计筛出 {len(candidates)} 个同时满足“小型、整体高于 DTM、全局隔离”的几何候选，其中 {len(safe)} 个没有命中 current-form、官方建筑保护域或 source-protection 域。']
    if not safe: lines += ['没有可安全删除项。所有候选均应保留，直到有独立运行时 owner 证据排除走廊、树冠、坡面主体、屋面或其他保留语义。']
    else: lines += ['safeToDelete 仅表示数值与保护域门槛通过；仍需人工/运行时 owner 复核后才能执行删除。']
    lines += ['', '## 输入与边界', '', 'DTM 为当前仓库中的 5 m 高程网格；DTM gap 只说明相对地形的高度，不足以区分树冠、走廊、坡面或建筑构件。保护域命中采用 current-form replacement mask、官方 Hall X–XIII envelope 与 source-protection mask。']
    md.write_text('\n'.join(lines)+'\n'); print(json.dumps({'json':str(jp),'markdown':str(md),'selectedTiles':[i for i,_ in selected],'faces':len(faces),'components':len(records),'candidates':len(candidates),'safeToDelete':len(safe)}))
if __name__=='__main__': main()
