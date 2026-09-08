// Current checkout classes + actual source metadata/cameras. No renderer or decoded GPU memory claim.
// Optional --staged reads the explicit source staging directory before root installs the atomic snapshot.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
const root=fileURLToPath(new URL('../',import.meta.url)),staged=false;
const json=path=>JSON.parse(fs.readFileSync(path.startsWith('/')?path:root+path,'utf8'));
const manifestPath=staged?'/tmp/hkust-corridor-partitions/staged-partitions.json':'public/models/hires/manifest.json';
const protectionPath=staged?'/tmp/hkust-corridor-partitions/road-protection.json':'public/models/hires/road-protection.json';
const patches=json(manifestPath).patches,rawProtection=json(protectionPath),compiled=new Map();
function load(name){
 if(compiled.has(name))return compiled.get(name);
 const exports={};compiled.set(name,exports);
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(root+'app/'+name+'.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
  exports,performance,console,Map,Set,WeakMap,Uint8Array,ArrayBuffer,AbortController,DOMException,URL,setTimeout,clearTimeout,
  require(id){if(id==='three')return THREE;if(id.endsWith('/road-protection.json'))return rawProtection;if(id.endsWith('.json'))return json('app/'+id);if(id.startsWith('./'))return load(id.slice(2));return {};},
 });return exports;
}
const {CampusScene}=load('scene'),{RoadCoveragePlanner,parseRoadProtection}=load('road-coverage-plan');
const {CoherentExteriors,exteriorBundleBytes}=load('coherent-exteriors'),{CampusMeshDetail}=load('campus-mesh-detail');
const {SpatialMasks}=load('spatial-masks'),{AtomicTextures}=load('atomic-textures'),{EntityRegistry}=load('entity-registry');
const {ExteriorViewPlanner}=load('exterior-view-plan'),{StableDetailChoice,visibleDetails}=load('detail-priority');
const {DetailResourcePool,sharedDetailCaps}=load('detail-resource-pool'),{qualityProfiles}=load('quality');
const protection=parseRoadProtection(rawProtection),bundles=json('public/models/exteriors/manifest.json').bundles;
const tiles=json('public/models/texture-detail-manifest.json').tiles,regions=json('public/models/exteriors/baseline-texture-regions.json').regions;
const grid=json('public/terrain/height-grid-5m.json'),registry=new EntityRegistry(json('public/data/entity-registry.json'));
const records={};
for(const name of ['fixed-tsang-near-high','fixed-lam-near-high','entrance-green-fullbleed-fixed','entrance-green-fullbleed-nearer']){const capture=json('docs/source-evidence-v4/'+name+'.json');records[name]=capture.scene??capture;}
const uc=bundles.find(bundle=>bundle.id==='campus-36');
const ucCenter=uc.bounds.min.map((value,index)=>(value+uc.bounds.max[index])/2);
records['uc-source-derived-near']={camera:ucCenter.map((v,i)=>v+[110,100,135][i]),target:ucCenter,selectedId:'',viewport:{width:1149,height:1079,safeCenter:[735.5,570.5]}};
function fixture(state,level='high'){
 const s=Object.create(CampusScene.prototype),world=new THREE.Scene(),geometry=new THREE.Group(),masks=new SpatialMasks();
 const textures=new AtomicTextures(),exteriors=new CoherentExteriors(world,masks,()=>{}),mesh=new CampusMeshDetail(world,geometry,masks,()=>{});
 textures.catalog=new Map(tiles.map(tile=>[tile.id,tile]));
 textures.regions=regions.map(region=>{const source=region.baselineIds.map(id=>textures.catalog.get(id));return {...region,minX:Math.min(...source.map(t=>t.bounds.min[0])),minZ:Math.min(...source.map(t=>t.bounds.min[2])),maxX:Math.max(...source.map(t=>t.bounds.max[0])),maxZ:Math.max(...source.map(t=>t.bounds.max[2]))};});
 for(const tile of tiles){const g=new THREE.Group();g.name=tile.id;geometry.add(g);}
 exteriors.bundles=bundles;mesh.patches=patches;
 const w=state.viewport.width,h=state.viewport.height,camera=new THREE.PerspectiveCamera(42,w/h,.5,9000);
 camera.setViewOffset(w,h,w/2-state.viewport.safeCenter[0],h/2-state.viewport.safeCenter[1],w,h);
 camera.position.fromArray(state.camera);camera.lookAt(new THREE.Vector3(...state.target));camera.updateMatrixWorld();
 Object.assign(s,{camera,geometry,masks,textures,exteriors,meshDetail:mesh,qualityLevel:level,detailPool:new DetailResourcePool(sharedDetailCaps[level]),exteriorViewPlanner:new ExteriorViewPlanner(),roadCoveragePlanner:new RoadCoveragePlanner(protection),footprints:json('public/data/building-footprints.json').footprints,grid,host:{clientWidth:w,clientHeight:h},registry,opened:null,selectedId:state.selectedId,detailChoice:new StableDetailChoice(),detailSeen:new Map(),detailCandidates:[],lastDetailUpdate:0});
 exteriors.request=choices=>{s.acceptedExterior=choices;};mesh.request=choices=>{s.acceptedMesh=choices;};textures.request=(key,images)=>{s.acceptedOriginal={key,images};};
 s.prepareTextureGroups();return s;
}

const reports=[];
async function check(name,run){reports.push({name,status:'pass',detail:await run()});}
function snapshot(s){return {exterior:s.acceptedExterior.map(b=>b.id).sort(),mesh:s.acceptedMesh.map(c=>c.key).sort(),original:s.acceptedOriginal.images.map(t=>t.url).sort(),pool:s.detailPool.stats(s.detailMemoryBytes())};}
function motion(s,state,index){
 const target=new THREE.Vector3(...state.target),offset=new THREE.Vector3(...state.camera).sub(target),spherical=new THREE.Spherical().setFromVector3(offset);
 const phase=Math.sin(index*Math.PI/8);spherical.theta+=phase*THREE.MathUtils.degToRad(.4);spherical.radius*=1+phase*.015;
 s.camera.position.copy(target).add(new THREE.Vector3().setFromSpherical(spherical));s.camera.lookAt(target);s.camera.updateMatrixWorld();
}
const observed={};
for(const name of ['fixed-tsang-near-high','fixed-lam-near-high','entrance-green-fullbleed-fixed'])for(const level of ['high','ultra'])await check(name+'/'+level+' repeated small rotate and scroll',()=>{
 const state=records[name],s=fixture(state,level),rows=[];s.updateDetails(10000,true);
 // Let retained-frustum membership and the first whole source set converge
 // before measuring motion stability. The assertion below still rejects any
 // subsequent high/fine or bundle oscillation across the full gesture trace.
 for(const warm of [10400,10800,11200])s.updateDetails(warm);
 for(let i=0;i<65;i++){motion(s,state,i);s.updateDetails(11600+i*400);const a=snapshot(s);assert.ok(a.pool.chargedBytes<=sharedDetailCaps[level]);rows.push(a);}
 const changes=Object.fromEntries(['exterior','mesh','original'].map(lane=>[lane,rows.reduce((sum,row,i)=>sum+Number(i>0&&JSON.stringify(row[lane])!==JSON.stringify(rows[i-1][lane])),0)]));
 assert.equal(changes.exterior,0,`${name}/${level} exterior ${JSON.stringify(changes)}`);assert.ok(changes.mesh<=1,`${name}/${level}: one retained-frustum frontier convergence is allowed, repeated mesh oscillation is not ${JSON.stringify(changes)}`);assert.ok(changes.original<=1,'a one-time atlas addition is allowed, repeated source-set oscillation is not');
 observed[name+'/'+level]={changes,initial:rows[0],last:rows.at(-1)};return observed[name+'/'+level];
});
const {StableDetailOrder}=load('detail-priority'),{nativeDetailChoice}=load('campus-mesh-detail'),{textureMipBytes}=load('source-types');
const sources=[...new Map(tiles.flatMap(tile=>Object.values(tile.materials)).map(source=>[source.url,source])).values()].slice(0,3);
const cost=source=>textureMipBytes(source.width,source.height);
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const fakeTexture=()=>{const image={closed:0,close(){this.closed++;}};return new THREE.Texture(image);};
function cached(a,source,texture=fakeTexture()){
 a.cache.set(source.url,{texture,source,bytes:cost(source),usedAt:performance.now()});a.cacheBytes+=cost(source);return texture;
}
await check('Atomic cache-only pressure never detaches an affordable completed original set',()=>{
 const a=new AtomicTextures(),first=cached(a,sources[0]),unused=cached(a,sources[1]);
 const low=new THREE.Texture(),material=new THREE.MeshBasicMaterial({map:low});
 a.bindings=[{material,low,source:sources[0]}];a.commit(new Map([[sources[0].url,first]]));
 const version=material.version;a.setBudget(cost(sources[0]));
 assert.equal(material.map,first);assert.equal(material.version,version);assert.equal(a.current.size,1);
 assert.equal(unused.image.closed,1);assert.equal(first.image.closed,0);assert.equal(a.cacheBytes,cost(sources[0]));
 a.dispose();return {realSource:sources[0].url,bytes:cost(sources[0]),unnecessaryMaterialChanges:0,unusedClosedOnce:true};
});
await check('Atomic overlapping group changes keep useful decode and commit the latest group only after complete',async()=>{
 const a=new AtomicTextures({cacheBudgetBytes:sources.reduce((n,s)=>n+cost(s),0)}),calls=[],gates=new Map(),images=[];
 a.fetchTexture=async source=>{calls.push(source.url);const gate=deferred();gates.set(source.url,gate);await gate.promise;const texture=fakeTexture();images.push(texture);return texture;};
 a.request('old-overlap',sources.slice(0,2));await tick();const transaction=a.pending;
 a.request('new-overlap',sources);assert.equal(a.pending,transaction);assert.equal(transaction.signal.aborted,false);
 gates.get(sources[0].url).resolve();gates.get(sources[1].url).resolve();await tick();await tick();
 assert.equal(a.current.size,0);assert.equal(a.pendingKey,'new-overlap');
 gates.get(sources[2].url).resolve();await tick();await tick();
 assert.equal(a.ready,'new-overlap');assert.equal(a.current.size,3);
 for(const source of sources)assert.equal(calls.filter(url=>url===source.url).length,1);
 assert.ok(a.cacheBytes+a.reservedBytes<=a.cacheBudgetBytes);a.dispose();assert.ok(images.every(texture=>texture.image.closed===1));
 return {downloadCalls:calls,wholeLatestCommit:true,obsoleteTransactionDidNotRestartSharedImages:true};
});
await check('Atomic budget reduction keeps affordable visible originals while cancelled native decode drains',async()=>{
 const a=new AtomicTextures(),first=cached(a,sources[0]),gate=deferred(),newTexture=fakeTexture();
 a.commit(new Map([[sources[0].url,first]]));a.fetchTexture=async()=>{await gate.promise;return newTexture;};
 a.setBudget(cost(sources[0])+cost(sources[1]));a.request('pair',sources.slice(0,2));await tick();
 const reserved=a.reservedBytes;a.setBudget(cost(sources[0]));assert.equal(a.pending.signal.aborted,true);
 assert.equal(a.current.get(sources[0].url),first);assert.equal(a.reservedBytes,reserved,'abort cannot spend native reservation early');
 a.request('single',sources.slice(0,1));gate.resolve();await tick();await tick();
 assert.equal(a.reservedBytes,0);assert.equal(newTexture.image.closed,1);assert.equal(a.current.get(sources[0].url),first);a.dispose();
 return {reservedBeforeDrain:reserved,affordableCurrentRemainedBound:true,staleBitmapClosedOnce:true};
});
await check('eight complete exterior slots exchange a ready group without prematurely removing the outgoing facade',()=>{
 const models=bundles.filter(bundle=>bundle.id!=='campus-01').slice(0,9),masks=new SpatialMasks();
 const exterior=new CoherentExteriors(new THREE.Scene(),masks,()=>{},{budgetBytes:models.reduce((sum,b)=>sum+exteriorBundleBytes(b),0),maxCachedGroups:3});
 const ready=bundle=>({bundle,bytes:exteriorBundleBytes(bundle),group:new THREE.Group(),mask:new THREE.DataTexture(new Uint8Array([255,0,0,255]),1,1)});
 exterior.desired=models.slice(0,8);for(const model of exterior.desired)exterior.commit(ready(model));
 const old=exterior.visible.get(models[7].id);let started='';exterior.start=bundle=>{started=bundle.id;};
 exterior.request([...models.slice(0,7),models[8]]);assert.equal(started,models[8].id);
 assert.equal(exterior.visible.get(models[7].id),old,'slot capacity alone cannot cause baseline before decode');assert.equal(exterior.visible.size,8);
 exterior.commit(ready(models[8]));assert.equal(exterior.visible.size,8);assert.equal(exterior.visible.has(models[7].id),false);assert.equal(exterior.visible.has(models[8].id),true);
 for(const model of models.slice(0,7))assert.ok(exterior.visible.has(model.id));assert.ok(exterior.memoryBytes()<=exterior.options.budgetBytes);
 exterior.dispose();masks.dispose();return {outgoing:models[7].id,incoming:models[8].id,unchangedFacades:7,maximumVisibleSlots:8};
});
await check('new whole-plan priorities guide budget release instead of stale load order',()=>{
 const a=bundles.find(b=>b.id==='campus-32'),b=bundles.find(b=>b.id==='campus-33'),masks=new SpatialMasks();
 const e=new CoherentExteriors(new THREE.Scene(),masks,()=>{},{budgetBytes:exteriorBundleBytes(a)+exteriorBundleBytes(b)});
 const ready=bundle=>({bundle,bytes:exteriorBundleBytes(bundle),group:new THREE.Group(),mask:new THREE.DataTexture(new Uint8Array([255,0,0,255]),1,1)});
 e.desired=[b,a];e.commit(ready(b));e.commit(ready(a));e.pump=()=>{};
 e.setBudget(exteriorBundleBytes(a),0,[a]);assert.ok(e.visible.has(a.id));assert.equal(e.visible.has(b.id),false);assert.ok(e.memoryBytes()<=exteriorBundleBytes(a));
 e.dispose();masks.dispose();return {retainedNewPlan:a.id,wholeReleased:b.id};
});
await check('score advantages and real-source near-level thresholds have spatial hysteresis without a timer',()=>{
 const order=new StableDetailOrder(),ids=bundles.slice(0,9).map(bundle=>bundle.id),rows=ids.map((id,index)=>({id,score:100-index,pixels:500,distance:150}));
 order.rank(rows);for(let i=0;i<20;i++){const next=rows.map(row=>({...row}));next[8].score=rows[7].score*(i%2?1.08:.98);next.sort((a,b)=>b.score-a.score);assert.equal(order.rank(next)[7].id,ids[7]);}
 const better=rows.map(row=>({...row}));better[8].score=rows[0].score*1.3;assert.equal(order.rank(better)[0].id,ids[8]);assert.equal(order.rank([]).length,0);
 const patch=patches.find(p=>p.levels.fine&&p.levels.high.geometricErrorMax>0),camera=new THREE.PerspectiveCamera(42,16/9,.5,9000);
 let previous=nativeDetailChoice(patch,{id:patch.id,pixels:700,score:100,distance:299.9},camera,900,qualityProfiles.high,sharedDetailCaps.high);
 assert.equal(previous.level,patch.levels.fine);
 for(let i=0;i<20;i++){const next=nativeDetailChoice(patch,{id:patch.id,pixels:700,score:100,distance:i%2?300.1:299.9},camera,900,qualityProfiles.high,sharedDetailCaps.high,previous.level===patch.levels.fine,previous.near);assert.equal(next.level,patch.levels.fine);previous=next;}
 const away=nativeDetailChoice(patch,{id:patch.id,pixels:700,score:100,distance:331},camera,900,qualityProfiles.high,sharedDetailCaps.high,true,true);assert.equal(away.level,patch.levels.high);
 return {sourcePatch:patch.id,smallAlternations:20,challengerAdvantage:1.3,nearExitMeters:330};
});
await check('real source box stays through a narrow viewport edge oscillation and exits when clearly offscreen',()=>{
 const bundle=bundles.find(b=>b.id==='campus-32'),center=new THREE.Vector3(...bundle.bounds.min).add(new THREE.Vector3(...bundle.bounds.max)).multiplyScalar(.5);
 const camera=new THREE.PerspectiveCamera(42,16/9,.5,9000),offset=new THREE.Vector3(150,150,220),candidate={id:bundle.id,bounds:bundle.bounds};
 camera.position.copy(center).add(offset);camera.lookAt(center);camera.updateMatrixWorld();
 assert.equal(visibleDetails(camera,[candidate],900,40).length,1);
 let edge=0;
 for(let angle=0;angle<80;angle+=.25){camera.lookAt(center);camera.rotateY(THREE.MathUtils.degToRad(angle));camera.updateMatrixWorld();if(!visibleDetails(camera,[candidate],900,40).length){edge=angle;break;}}
 assert.ok(edge>0);const retained=new Set([bundle.id]);
 for(const delta of [-.1,.1,-.1,.1]){camera.lookAt(center);camera.rotateY(THREE.MathUtils.degToRad(edge+delta));camera.updateMatrixWorld();assert.equal(visibleDetails(camera,[candidate],900,40,{ids:retained}).length,1);}
 camera.lookAt(center);camera.rotateY(THREE.MathUtils.degToRad(edge+20));camera.updateMatrixWorld();assert.equal(visibleDetails(camera,[candidate],900,40,{ids:retained}).length,0);
 return {realBundle:bundle.id,edgeAngleDegrees:edge,oscillationDegrees:.1,largeExitDegrees:20};
});
await check('actual native costs do not spend leftover credit on far fine while a near terminal frontier is deferred',()=>{
 const {fitNativeDetailChoices,nativePlanBytes}=load('campus-mesh-detail');
 const choice=(patch,fine,near)=>{const level=fine?patch.levels.fine:patch.levels.high,mask=level.mask??patch.mask;return {key:patch.id+(fine?'/fine':'/high'),patch,level,near,bytes:level.tiles.reduce((n,t)=>n+t.textureDimensions.reduce((sum,[w,h])=>sum+textureMipBytes(w,h),0),mask.width*mask.height*4)};};
 let sample;
 for(const p of patches){if(sample)break;for(const q of patches){
  if(p===q)continue;const near=choice(p,true,true),nearHigh=choice(p,false,true),far=choice(q,true,false),budget=nativePlanBytes([nearHigh,far]);
  if(Number.isFinite(budget)&&budget<nativePlanBytes([near])&&far.bytes>choice(q,false,false).bytes){sample={near,nearHigh,far,budget};break;}
 }}
 assert.ok(sample,'real complete-source cost counterexample must exist');
 const {near,nearHigh,far,budget}=sample,plan=fitNativeDetailChoices([{choice:near,score:100},{choice:far,score:10}],budget);
 assert.ok(plan.some(c=>c.key===nearHigh.key));assert.ok(!plan.some(c=>c.key===far.key));assert.ok(nativePlanBytes(plan)<=budget);
 return {near:near.patch.id,far:far.patch.id,budget,nearTerminalBytes:near.bytes,farTerminalBytes:far.bytes,accepted:plan.map(c=>({key:c.key,reason:c.qualityReason})),rankingBoundary:'Controlled near/far screen priority with real source dimensions and masks; not a browser view claim'};
});
await check('large region travel and rapid profile switching release old demand and converge within each effective cap',()=>{
 const state=records['fixed-lam-near-high'],s=fixture(state,'ultra');s.updateDetails(10000,true);const start=snapshot(s);
 s.camera.position.set(500,300,3000);s.camera.lookAt(500,300,5000);s.updateDetails(11000,true);const away=snapshot(s);
 assert.equal(away.exterior.length,0);assert.equal(away.mesh.length,0);assert.equal(away.original.length,0);
 s.camera.position.fromArray(state.camera);s.camera.lookAt(new THREE.Vector3(...state.target));const profiles=[];
 for(const [index,level]of ['smooth','ultra','high','balanced','high','ultra'].entries()){s.qualityLevel=level;s.updateDetails(12000+index*400,true);const a=snapshot(s);assert.ok(a.pool.chargedBytes<=sharedDetailCaps[level]);profiles.push({level,grants:a.pool.grants});}
 const end=snapshot(s);assert.deepEqual(end.exterior,start.exterior);assert.ok(end.mesh.length>0);
 return {awayAllReleased:true,returnedExteriors:end.exterior,profiles};
});
const sourceFiles=['app/detail-priority.ts','app/scene.ts','app/campus-mesh-detail.ts','app/atomic-textures.ts','app/coherent-exteriors.ts','app/detail-resource-pool.ts'];
const report={beforeReference:{path:'docs/source-evidence-v4/detail-stability-before.json',scope:'These same natural sequences were also stable before the fix; direct cache-pressure, threshold and decode-timing tests identify mechanisms. No browser flicker reproduction is claimed.'},sourceSha256:Object.fromEntries(sourceFiles.map(path=>[path,createHash('sha256').update(fs.readFileSync(root+path)).digest('hex')])),status:'pass',checkedAt:new Date().toISOString(),checks:reports.length,results:reports,limitations:['Current checkout classes and actual source camera/bounds; controlled request boundary. No browser visual or physical GPU allocation claim.']};
const output=root+'docs/source-evidence-v4/detail-stability-tests.json';
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(Object.fromEntries(Object.entries(observed).map(([name,a])=>[name,a.changes])),null,2));
