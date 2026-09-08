#!/usr/bin/env python3
"""Streaming two-pass all-campus global floater audit (read-only)."""
import importlib.util, json, hashlib, math
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]; MODELS=ROOT/'public/models'; OUT=ROOT/'docs/source-evidence-v4/ivillage-remnants'
Q=1e-5; MAXF=120; MAXA=50.; MAXH=8.; MINP05=2.
spec=importlib.util.spec_from_file_location('u73',ROOT/'scripts/audit-global-floater-connectivity-u73.py'); u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def domains():
    out=[]
    for p,label in [(MODELS/'current-forms/ivillage-rebuild/manifest.json','ivillage-current'),(MODELS/'current-forms/halls-current/manifest.json','halls-current'),(MODELS/'current-forms/innovation/manifest.json','innovation'),(MODELS/'current-forms/hall2-corridor/manifest.json','hall2-corridor')]:
        if not p.exists(): continue
        d=json.loads(p.read_text())
        vals=d.get('members',[])+d.get('buildings',[])
        for x in vals:
            if 'bounds' in x: out.append((f"{label}:{x.get('catalogId',x.get('entityId',x.get('id','member')))}",x['bounds']))
    ex=json.loads((MODELS/'exteriors/manifest.json').read_text())
    for b in ex.get('bundles',[]):
        for o in b.get('objects',[]):
            if 'bounds' in o:
                ids=b.get('catalogIds') or [b.get('id','unknown')]
                out.append((f"exterior:{ids[0]}",o['bounds']))
    return out
def overlap(a,b): return not (a['max'][0]<b['min'][0] or a['min'][0]>b['max'][0] or a['max'][1]<b['min'][1] or a['min'][1]>b['max'][1] or a['max'][2]<b['min'][2] or a['min'][2]>b['max'][2])
def load_tile(t):
    doc,raw,start=u.read_glb(MODELS/t['url']); tris=[]; metas=[]
    for mi,m in enumerate(doc['meshes']):
      for pi,p in enumerate(m['primitives']):
        if p.get('mode',4)!=4: continue
        pos=u.world(t['matrix'],u.accessor(doc,raw,start,p['attributes']['POSITION'])); ix=u.accessor(doc,raw,start,p['indices']).ravel().reshape(-1,3)
        for fi,tr in enumerate(ix): tris.append(pos[tr]); metas.append((mi,pi,fi))
    if not tris:return np.empty((0,3,3)),[]
    return np.asarray(tris),metas
def components(tris):
    n=len(tris); parent=np.arange(n); buckets={}
    for i,v in enumerate(np.rint(tris/u.Q).astype(np.int64)):
      for x in v:buckets.setdefault(tuple(map(int,x)),[]).append(i)
    def find(x):
      while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
      return int(x)
    for ids in buckets.values():
      r=find(ids[0])
      for x in ids[1:]: parent[find(x)]=r
    d={}
    for i in range(n):d.setdefault(find(i),[]).append(i)
    return list(d.values())
def main():
    mp=MODELS/'preview-manifest.json'; manifest=json.loads(mp.read_text()); g=json.loads((ROOT/'public/terrain/height-grid-5m.json').read_text()); g['heights']=np.asarray(g['heights'],float)
    dom=domains(); candidates=[]; total_faces=0; total_components=0; tile_stats=[]
    # Pass 1: per-tile cross-primitive components and numerical gate.
    for ti,t in enumerate(manifest['tiles']):
      tris,meta=load_tile(t); total_faces+=len(tris); cs=components(tris); total_components+=len(cs); tile_stats.append({'tileIndex':ti,'id':t['id'],'url':t['url'],'glbSha256':sha(MODELS/t['url']),'manifestSha256':t.get('sha256'),'faces':len(tris),'components':len(cs)})
      for ci,ids in enumerate(cs):
        a=tris[ids]; lo=a.min((0,1)); hi=a.max((0,1)); centers=a.mean(1); gaps=centers[:,1]-u.dtm(centers,g); finite=gaps[np.isfinite(gaps)]
        if not len(finite): continue
        area=np.linalg.norm(np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]),axis=1)/2; p05=float(np.nanpercentile(finite,5));
        small=len(ids)<=MAXF and area.sum()<=MAXA and max(hi[0]-lo[0],hi[2]-lo[2])<=MAXH and hi[1]-lo[1]<=MAXH
        if not (small and p05>MINP05 and area.sum()>=0.01): continue
        bb={'min':lo.tolist(),'max':hi.tolist()}; hits=[n for n,b in dom if overlap(bb,b)]
        keys={tuple(map(int,x)) for x in np.rint(a.reshape(-1,3)/Q).astype(np.int64)}
        candidates.append({'candidateId':f'tile{ti}-component{ci}','tileIndex':ti,'tileId':t['id'],'url':t['url'],'tileSha256':sha(MODELS/t['url']),'faces':[{'meshIndex':meta[i][0],'primitiveIndex':meta[i][1],'localFace':meta[i][2]} for i in ids],'faceCount':len(ids),'bounds':bb,'areaSquareMeters':float(area.sum()),'dtmGapMeters':{'min':float(np.nanmin(finite)),'p05':p05,'median':float(np.nanmedian(finite)),'max':float(np.nanmax(finite))},'protectionDomainHits':sorted(set(hits)),'_keys':keys,'globalIsolation':None,'semanticStatus':'unknown-corridor-tree-canopy-slope-or-structure','safeToDelete':False})
    # Pass 2: candidate keys only; any appearance in another tile proves the
    # component was only tile-local. Same-tile cross-primitive links were
    # already unioned in pass 1.
    key_to_c=[(c,k) for c in candidates for k in c['_keys']]; bykey={}
    for c,k in key_to_c: bykey.setdefault(k,[]).append(c)
    for ti,t in enumerate(manifest['tiles']):
      wanted={k for k,cs in bykey.items() if any(c['tileIndex']!=ti for c in cs)}
      if not wanted: continue
      tris,_=load_tile(t)
      present={tuple(map(int,x)) for x in np.rint(tris.reshape(-1,3)/Q).astype(np.int64)} & wanted
      for c in candidates:
        if c['tileIndex']==ti: continue
        if c['_keys'] & present: c['globalIsolation']=False
    for c in candidates:
      if c['globalIsolation'] is None: c['globalIsolation']=True
      c.pop('_keys',None)
    isolated=[c for c in candidates if c['globalIsolation'] and not c['protectionDomainHits']]
    minimal=sorted(isolated,key=lambda c:(c['areaSquareMeters'],c['dtmGapMeters']['p05']))[:20]
    domain_paths=[MODELS/'current-forms/ivillage-rebuild/manifest.json',MODELS/'current-forms/halls-current/manifest.json',MODELS/'current-forms/innovation/manifest.json',MODELS/'current-forms/hall2-corridor/manifest.json',MODELS/'exteriors/manifest.json']
    domain_inputs=[{'path':str(p),'sha256':sha(p)} for p in domain_paths if p.exists()]
    out={'status':'audit-complete-no-runtime-write','task':'U73 campus-wide streaming global floater audit','algorithm':{'passes':2,'memoryModel':'one preview tile at a time; pass 2 hashes only first-pass candidate vertices','quantizationMeters':Q,'withinTileConnectivity':'all faces across all primitives union through any shared quantized world vertex','globalConnectivity':'pass 2 candidate-key lookup across every other tile'},'scope':{'previewManifestTileCount':len(manifest['tiles']),'allTilesProcessed':len(tile_stats)==len(manifest['tiles'])},'inputs':{'previewManifest':str(mp),'previewManifestSha256':sha(mp),'heightGrid':str(ROOT/'public/terrain/height-grid-5m.json'),'heightGridSha256':sha(ROOT/'public/terrain/height-grid-5m.json'),'domainInputs':domain_inputs},'counts':{'tiles':len(tile_stats),'faces':total_faces,'tileComponents':total_components,'numericCandidates':len(candidates),'globallyIsolatedCandidates':sum(c['globalIsolation'] for c in candidates),'isolatedOutsideProtectionDomains':len(isolated),'safeToDelete':0},'thresholds':{'maxFaces':MAXF,'maxAreaSquareMeters':MAXA,'minAreaSquareMeters':0.01,'maxHorizontalSpanMeters':MAXH,'maxVerticalSpanMeters':MAXH,'minP05DtmGapMeters':MINP05,'safeRule':'always false without independent owner evidence excluding corridor/tree canopy/slope/structure'},'candidates':candidates,'minimalCandidates':minimal,'writes':{'runtimeManifestModified':False,'glbModified':False,'sourceTrianglesDeleted':0}}
    jp=OUT/'campus-global-floater-audit-u73.json'; md=OUT/'campus-global-floater-audit-u73.md'; jp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    lines=['# 全校 Preview 全局浮空面审计（U73）','','只读；未修改生产 GLB、manifest 或代码。','',f"- 处理瓦片：{len(tile_stats)}；面数：{total_faces}；瓦片内跨 primitive 连通分量：{total_components}",f"- 数值候选：{len(candidates)}；二遍后真正跨瓦片全局隔离：{sum(c['globalIsolation'] for c in candidates)}；远离已加载楼体/保护域：{len(isolated)}；safeToDelete：0",'- 第一遍逐瓦片 union；第二遍只重扫候选顶点键，验证其他瓦片是否共享。','', '|候选|tile / primitive / local faces|bounds|area m²|DTM gap min/p05/med/max|楼体/保护域|全局隔离|safeToDelete|','|---|---|---|---:|---|---|---|---|']
    for c in minimal:
      fs='; '.join(f"p{x['primitiveIndex']}/f{x['localFace']}" for x in c['faces']); b=c['bounds'];g0=c['dtmGapMeters']; hits=', '.join(c['protectionDomainHits']) or 'none'
      lines.append(f"|{c['candidateId']}|t{c['tileIndex']} {fs}|[{b['min'][0]:.2f},{b['min'][1]:.2f},{b['min'][2]:.2f}] → [{b['max'][0]:.2f},{b['max'][1]:.2f},{b['max'][2]:.2f}]|{c['areaSquareMeters']:.3f}|{g0['min']:.2f}/{g0['p05']:.2f}/{g0['median']:.2f}/{g0['max']:.2f}|{hits}|{'是' if c['globalIsolation'] else '否'}|否|")
    lines += ['', '## 结论', '', '没有可安全删除项。即使候选通过面积、隔离与 DTM 门槛，当前仓库没有足够的语义 owner 证据排除走廊、树冠、坡面主体、屋面或其他保留表面，因此统一保留待复核。','', 'DTM gap 只表达相对 5 m 地形高度；楼体保护域使用当前仓库可用的 current-form、halls-current、innovation、hall2-corridor 与 exterior AABB。']
    md.write_text('\n'.join(lines)+'\n'); print(json.dumps({'json':str(jp),'markdown':str(md),'tiles':len(tile_stats),'faces':total_faces,'candidates':len(candidates),'isolated':len(isolated)}))
if __name__=='__main__': main()
