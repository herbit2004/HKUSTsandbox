// Current checkout planning and real captured cameras; no network/decode or browser claims.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
const root=fileURLToPath(new URL('../',import.meta.url));
const json=path=>JSON.parse(fs.readFileSync(root+path,'utf8'));
const compiled=new Map();
function load(name){
 if(compiled.has(name))return compiled.get(name);
 const exports={};compiled.set(name,exports);
 const source=fs.readFileSync(root+'app/'+name+'.ts','utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
  exports,performance,Map,Set,WeakMap,Uint8Array,ArrayBuffer,AbortController,DOMException,setTimeout,clearTimeout,console,
  require(id){if(id==='three')return THREE;if(id.startsWith('./'))return load(id.slice(2));if(id.endsWith('.json'))return json('app/'+id);return {};},
 });return exports;
}
const {CampusScene}=load('scene'),{CoherentExteriors,exteriorBundleBytes}=load('coherent-exteriors');
const {CampusMeshDetail}=load('campus-mesh-detail'),{AtomicTextures}=load('atomic-textures'),{SpatialMasks}=load('spatial-masks');
const {visibleDetails,StableDetailChoice}=load('detail-priority'),{ExteriorViewPlanner,exteriorNearRange}=load('exterior-view-plan');
const {DetailResourcePool,sharedDetailCaps}=load('detail-resource-pool'),{EntityRegistry}=load('entity-registry');
const {qualityProfiles}=load('quality'),{exteriorBuildingId}=load('source-types');
const bundles=json('public/models/exteriors/manifest.json').bundles,patches=json('public/models/hires/manifest.json').patches;
const tiles=json('public/models/texture-detail-manifest.json').tiles,regions=json('public/models/exteriors/baseline-texture-regions.json').regions;
const byId=id=>bundles.find(bundle=>bundle.id===id),MiB=1048576;
const records=['resumed-tsang-near-ultra','resumed-tsang-near-high','resumed-lam-near-high'];
const captured=Object.fromEntries(records.map(name=>[name,json('docs/source-evidence-v4/'+name+'.json').scene]));
const reports=[];
function check(name,fn){reports.push({name,status:'pass',detail:fn()});}
function fixture(state,level=state.quality.level){
 const scene=Object.create(CampusScene.prototype),world=new THREE.Scene(),geometry=new THREE.Group(),masks=new SpatialMasks();
 const textures=new AtomicTextures(),exteriors=new CoherentExteriors(world,masks,()=>{}),meshDetail=new CampusMeshDetail(world,geometry,masks,()=>{});
 textures.catalog=new Map(tiles.map(tile=>[tile.id,tile]));
 textures.regions=regions.map(region=>{const source=region.baselineIds.map(id=>textures.catalog.get(id));return {...region,minX:Math.min(...source.map(tile=>tile.bounds.min[0])),minZ:Math.min(...source.map(tile=>tile.bounds.min[2])),maxX:Math.max(...source.map(tile=>tile.bounds.max[0])),maxZ:Math.max(...source.map(tile=>tile.bounds.max[2]))};});
 for(const tile of tiles){const object=new THREE.Group();object.name=tile.id;geometry.add(object);}
 exteriors.bundles=bundles;meshDetail.patches=patches;
 const width=Math.round(state.viewport.width),height=Math.round(state.viewport.height),camera=new THREE.PerspectiveCamera(42,width/height,.5,9000);
 camera.setViewOffset(width,height,width/2-state.viewport.safeCenter[0],height/2-state.viewport.safeCenter[1],width,height);
 camera.position.fromArray(state.camera);camera.lookAt(new THREE.Vector3(...state.target));camera.updateMatrixWorld();
 Object.assign(scene,{camera,geometry,masks,textures,exteriors,meshDetail,qualityLevel:level,detailPool:new DetailResourcePool(sharedDetailCaps[level]),exteriorViewPlanner:new ExteriorViewPlanner(),roadCoveragePlanner:new (load('road-coverage-plan').RoadCoveragePlanner)(load('road-coverage-plan').parseRoadProtection(json('public/models/hires/road-protection.json'))),footprints:json('public/data/building-footprints.json').footprints,grid:json('public/terrain/height-grid-5m.json'),host:{clientWidth:width,clientHeight:height},registry:new EntityRegistry(json('public/data/entity-registry.json')),opened:null,selectedId:state.selectedId,detailChoice:new StableDetailChoice(),detailSeen:new Map(),detailCandidates:[],lastDetailUpdate:0});
 // Planning is real; stop only at the I/O request boundary.
 exteriors.request=choices=>{scene.acceptedExterior=choices;};
 meshDetail.request=choices=>{scene.acceptedMesh=choices;};
 textures.request=(key,images)=>{scene.acceptedOriginal={key,images};};
 scene.prepareTextureGroups();return scene;
}
function ranked(scene){return visibleDetails(scene.camera,bundles.map(bundle=>({id:bundle.id,bounds:scene.detailBounds(exteriorBuildingId(bundle),bundle.bounds)})),scene.host.clientHeight,qualityProfiles[scene.qualityLevel].detailPixels);}
function allocation(scene){return {exteriorIds:Array.from(scene.acceptedExterior,b=>b.id),exteriorMiB:scene.exteriors.previewPlan(scene.acceptedExterior,Infinity).bytes/MiB,mesh:Array.from(scene.acceptedMesh,c=>({key:c.key,MiB:c.bytes/MiB})),meshMiB:scene.meshDetail.planBytes(scene.acceptedMesh)/MiB,originalImages:scene.acceptedOriginal.images.length,pool:scene.detailPool.stats(scene.detailMemoryBytes())};}
const observed={};
for(const name of records)check('real camera '+name+' restores complete A/B and Academic within the unchanged shared cap',()=>{
 const state=captured[name],scene=fixture(state);scene.updateDetails(10000,true);scene.updateDetails(11000);
 assert.deepEqual(Array.from(scene.detailCandidates),state.detailCandidates);
 const actual=allocation(scene),budget=qualityProfiles[scene.qualityLevel].exteriorMiB*MiB;
 // The captured version also truncated candidate identities before its budget
 // loop. Keep that historical boundary explicit when reproducing its failure.
 const old=scene.exteriors.previewPlan(state.detailCandidates.slice(0,8).map(byId),budget);
 assert.deepEqual(Array.from(old.bundles,b=>b.id).sort((a,b)=>a.localeCompare(b)),state.exterior.visibleIds.slice().sort((a,b)=>a.localeCompare(b)));
 for(const id of ['campus-32','campus-33','campus-01'])assert.ok(actual.exteriorIds.includes(id),id);
 assert.ok(actual.exteriorIds.length<=8);assert.ok(actual.pool.chargedBytes<=sharedDetailCaps[scene.qualityLevel]);
 assert.ok(scene.acceptedExterior.every(bundle=>bundle===byId(bundle.id)));
 const academic=scene.acceptedExterior.find(b=>b.id==='campus-01');assert.equal(academic.objects.length,37);assert.equal(exteriorBundleBytes(academic),670763744);
 const expected=scene.exteriorViewPlanner.plan(state.detailCandidates.map(byId),ranked(scene),budget,sharedDetailCaps[scene.qualityLevel]);
 assert.equal(actual.pool.grants.exterior,expected.bytes);
 assert.ok(actual.exteriorMiB>old.bytes/MiB);
 observed[name]={recordedVisibleIds:state.exterior.visibleIds,oldExteriorMiB:old.bytes/MiB,sourceRanking:Array.from(ranked(scene),c=>({...c,costMiB:exteriorBundleBytes(byId(c.id))/MiB})),newPlan:actual};
 return observed[name];
});
check('same view is independent of clicked entity and High to Ultra never removes A/B neighbours',()=>{
 const state=captured['resumed-tsang-near-high'],plans=[];
 for(const level of ['high','ultra'])for(const selectedId of ['', 'building:catalog:campus-32','building:catalog:campus-33','building:b00000000000000000000001']){
  const scene=fixture(state,level);scene.selectedId=selectedId;scene.updateDetails(10000,true);plans.push({level,selectedId,ids:Array.from(scene.acceptedExterior,b=>b.id)});
 }
 for(const plan of plans)assert.deepEqual(plan.ids,plans[0].ids);return plans;
});
const visibility=(items,distance)=>items.map((bundle,i)=>({id:bundle.id,score:100-i,pixels:500,distance}));
check('300 m entry, 330 m exit and leaving the actual visible set release borrowed credit',()=>{
 const bundle=byId('campus-33'),cost=exteriorBundleBytes(bundle),cap=cost+MiB;
 const fresh=new ExteriorViewPlanner();assert.equal(fresh.plan([bundle],visibility([bundle],300.001),0,cap).bytes,0);
 const planner=new ExteriorViewPlanner();assert.equal(planner.plan([bundle],visibility([bundle],300),0,cap).bytes,cost);
 for(const distance of [300.001,299.9,301,330])assert.equal(planner.plan([bundle],visibility([bundle],distance),0,cap).bytes,cost);
 assert.equal(planner.plan([bundle],visibility([bundle],330.001),0,cap).budgetBytes,0);
 assert.equal(planner.plan([bundle],visibility([bundle],300),0,cap).bytes,cost);
 assert.equal(planner.plan([bundle],[],0,cap).budgetBytes,0);
 return {renderPolicy:{...exteriorNearRange},borrowedBytes:cost};
});
check('deduplication precedes eight-slot capacity and no ninth bundle is added',()=>{
 const items=captured['resumed-tsang-near-ultra'].detailCandidates.map(byId),planner=new ExteriorViewPlanner();
 const result=planner.plan([items[0],items[0],...items],visibility(items,200),0,4*1024*MiB);
 assert.equal(result.bundles.length,8);assert.equal(new Set(result.bundles.map(b=>b.id)).size,8);
 assert.deepEqual(Array.from(result.bundles,b=>b.id),items.slice(0,8).map(b=>b.id));return {ids:Array.from(result.bundles,b=>b.id)};
});
check('ordinary budget skips an expensive first group and can fill its eighth slot from candidate nine',()=>{
 const ids=['campus-01','campus-32','campus-33','campus-35','campus-18','campus-36','staff-quarters-tower-1','staff-quarters-tower-2','campus-24'];
 const items=ids.map(byId),budget=items.slice(1).reduce((sum,bundle)=>sum+exteriorBundleBytes(bundle),0);
 assert.ok(budget<exteriorBundleBytes(items[0]));
 const plan=new ExteriorViewPlanner().plan(items,visibility(items,900),budget,sharedDetailCaps.ultra);
 assert.deepEqual(Array.from(plan.bundles,b=>b.id),ids.slice(1));assert.equal(plan.bundles.length,8);assert.equal(plan.borrowedBytes,0);
 return {ids:Array.from(plan.bundles,b=>b.id),ordinaryBudgetBytes:budget};
});
check('one byte short of a real complete Academic group keeps baseline and never truncates source objects',()=>{
 const bundle=byId('campus-01'),cost=exteriorBundleBytes(bundle),snapshot=JSON.stringify(bundle),planner=new ExteriorViewPlanner();
 const short=planner.plan([bundle],visibility([bundle],100),0,cost-1);assert.equal(short.bundles.length,0);assert.equal(short.bytes,0);
 const exact=planner.plan([bundle],visibility([bundle],100),0,cost);assert.equal(exact.bundles.length,1);assert.equal(exact.bytes,cost);assert.equal(exact.bundles[0],bundle);assert.equal(JSON.stringify(bundle),snapshot);
 return {bytes:cost,objects:bundle.objects.length,shortRejectedWhole:true};
});
check('a distant group rejected at the ordinary ceiling cannot consume close-neighbour borrowing',()=>{
 const items=['campus-24','campus-35','campus-32','campus-33'].map(byId),v=visibility(items,200);v[0].distance=500;
 const plan=new ExteriorViewPlanner().plan(items,v,50*MiB,512*MiB);
 assert.deepEqual(Array.from(plan.bundles,b=>b.id),items.slice(1).map(b=>b.id));assert.ok(plan.budgetBytes>exteriorBundleBytes(items[0]));
 return {ids:Array.from(plan.bundles,b=>b.id),MiB:plan.bytes/MiB};
});
check('leaving close range restores the fixed base ceiling without accumulating old grants',()=>{
 const items=captured['resumed-lam-near-high'].detailCandidates.map(byId),planner=new ExteriorViewPlanner(),base=640*MiB,cap=sharedDetailCaps.high,cycles=[];
 for(let i=0;i<5;i++){
  const near=planner.plan(items,visibility(items,200),base,cap);assert.ok(near.budgetBytes>base);
  const away=planner.plan(items,visibility(items,331),base,cap);assert.equal(away.budgetBytes,base);assert.equal(away.borrowedBytes,0);
  cycles.push({near:near.budgetBytes,away:away.budgetBytes});
 }
 assert.ok(cycles.every(row=>row.near===cycles[0].near));return {cycles};
});
check('actual old reservations remain charged until mesh drain before the new complete exterior groups can start',()=>{
 const state=captured['resumed-tsang-near-ultra'],next=observed['resumed-tsang-near-ultra'].newPlan,cap=sharedDetailCaps.ultra;
 const usage={exterior:0,mesh:0,original:0},events=[],lanes={};
 for(const lane of ['exterior','mesh','original'])lanes[lane]={memoryBytes:()=>usage[lane],setBudget:value=>events.push({lane,value})};
 const pool=new DetailResourcePool(cap),old=state.detailPool;
 pool.reconcile(cap,old.demand,{exterior:800*MiB,mesh:1792*MiB,original:384*MiB},lanes);
 Object.assign(usage,old.actual);events.length=0;
 const target={...next.pool.demand},ceilings={exterior:next.pool.grants.exterior,mesh:1792*MiB,original:384*MiB};
 let result=pool.reconcile(cap,target,ceilings,lanes);
 assert.ok(result.waitingForDrain.includes('mesh'));assert.ok(pool.grants.exterior<target.exterior);assert.ok(result.chargedBytes<=cap);
 assert.equal(events[0].lane,'mesh');
 const before=new CoherentExteriors(new THREE.Scene(),new SpatialMasks(),()=>{}).previewPlan(next.exteriorIds.map(byId),pool.grants.exterior);
 assert.ok(!before.bundles.some(b=>b.id==='campus-33'));
 usage.mesh=Math.min(usage.mesh,target.mesh);usage.original=Math.min(usage.original,target.original);
 result=pool.reconcile(cap,target,ceilings,lanes);assert.equal(pool.grants.exterior,target.exterior);assert.ok(result.chargedBytes<=cap);assert.equal(result.overCapBytes,0);
 return {oldActual:old.actual,target,events,afterDrain:result};
});
const files=['app/exterior-view-plan.ts','app/coherent-exteriors.ts','app/scene.ts','app/detail-resource-pool.ts','app/quality.ts','app/campus-mesh-detail.ts','public/models/exteriors/manifest.json','public/models/hires/manifest.json',...records.map(name=>'docs/source-evidence-v4/'+name+'.json')];
const report={status:'pass',checks:reports.length,results:reports,sourceSha256:Object.fromEntries(files.map(path=>[path,createHash('sha256').update(fs.readFileSync(root+path)).digest('hex')])),limitations:['Uses current checkout methods and actual recorded camera/frustum/source assets. I/O boundaries and reservation counters are controlled; this is not browser visual or native allocation acceptance.','300m entry and330m retention are render policy, not identity evidence. Eight unique ranked slots, exact source dimensions, and shared caps are unchanged.','Mesh removal means returning a complete frontier to existing baseline. No source object, image, triangle, or stable entity is edited by this test.']};
fs.writeFileSync(root+'docs/source-evidence-v4/near-exterior-budget-tests.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,checks:report.checks,views:Object.fromEntries(Object.entries(observed).map(([name,row])=>[name,{oldMiB:row.oldExteriorMiB,newMiB:row.newPlan.exteriorMiB,ids:row.newPlan.exteriorIds,mesh:row.newPlan.mesh,chargedMiB:row.newPlan.pool.chargedBytes/MiB}]))},null,2));
