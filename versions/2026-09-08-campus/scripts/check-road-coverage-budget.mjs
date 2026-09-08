// Current checkout classes + actual source metadata/cameras. No renderer or decoded GPU memory claim.
// Optional --staged reads the explicit source staging directory before root installs the atomic snapshot.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
const root=fileURLToPath(new URL('../',import.meta.url)),staged=process.argv.includes('--staged');
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
const {CampusScene}=load('scene'),{RoadCoveragePlanner,parseRoadProtection,visibleRoadClusters,roadCoverageRange}=load('road-coverage-plan');
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
const checks=[],observed={};
function check(name,run){const detail=run();checks.push({name,status:'pass',detail});}
function read(s){return {roads:s.roadCoverageState,exteriors:Array.from(s.acceptedExterior,b=>b.id),exteriorBytes:s.acceptedExterior.reduce((sum,b)=>sum+exteriorBundleBytes(b),0),mesh:Array.from(s.acceptedMesh,c=>({id:c.patch.id,key:c.key,tiles:c.level.tiles.length,bytes:c.bytes})),meshBytes:s.meshDetail.planBytes(s.acceptedMesh),pool:s.detailPool.stats(s.detailMemoryBytes())};}
check('source metadata resolves actual distinct stable partitions with complete error-zero fine',()=>{
 const byId=new Map(patches.map(p=>[p.id,p]));assert.equal(byId.size,patches.length);
 for(const cluster of protection.clusters)for(const id of cluster.partitionIds){const p=byId.get(id);assert.ok(p,id);assert.ok(p.levels.fine?.tiles.length,id);assert.ok(p.levels.fine.tiles.every(t=>(t.originalError??t.geometricError)===0),id);}
 assert.throws(()=>parseRoadProtection({...rawProtection,clusters:[{...rawProtection.clusters[0],verifiedCoverageFraction:.5}]}));
 return {clusters:protection.clusters.length,partitions:patches.length,referencedPartitions:new Set(protection.clusters.flatMap(c=>c.partitionIds)).size};
});
for(const [name,state]of Object.entries(records))for(const level of ['high','ultra'])check(name+'/'+level+' actual scene whole-road and exterior joint plan',()=>{
 const s=fixture(state,level);s.updateDetails(10000,true);s.updateDetails(11000);
 const result=read(s);assert.ok(result.roads,'scene road diagnostics missing');assert.ok(result.roads.primaryClusterId,'main source corridor must be visible');
 assert.ok(result.roads.acceptedFinePartitionIds.length>0,'primary whole fine must fit these High/Ultra views');
 assert.ok(result.pool.chargedBytes<=sharedDetailCaps[level]);assert.ok(result.exteriors.length<=8);
 for(const id of result.roads.acceptedFinePartitionIds){const choice=s.acceptedMesh.find(c=>c.patch.id===id);assert.equal(choice.level,choice.patch.levels.fine);assert.ok(choice.level.tiles.every(t=>(t.originalError??t.geometricError)===0));}
 assert.ok(result.roads.desiredFinePartitionIds.every(id=>result.roads.acceptedFinePartitionIds.includes(id)||result.roads.deferredFinePartitionIds.includes(id)));
 if(name.startsWith('fixed-'))for(const id of ['campus-01','campus-32','campus-33'])assert.ok(result.exteriors.includes(id),name+' lost '+id);
 observed[name+'/'+level]=result;return result;
});
check('flat all-near road protection counterexample is retained rather than hiding the old regression',()=>{
 const result={};for(const name of ['fixed-tsang-near-high','fixed-lam-near-high']){
  const s=fixture(records[name]),allowed=new Set(protection.clusters.flatMap(c=>c.partitionIds));
  const ids=new Set(visibleDetails(s.camera,patches,s.host.clientHeight,100).filter(c=>allowed.has(c.id)&&c.distance<=300).map(c=>c.id));
  const flat=s.meshDetail.previewCoveragePlan(s.camera,s.host.clientHeight,qualityProfiles.high,ids);
  s.updateDetails(10000,true);const planned=read(s);
  assert.ok(flat.bytes>planned.roads.reservedFineBytes);
  result[name]={flatIds:[...ids],flatFineBytes:flat.bytes,flatPlusPreservedExteriorBytes:flat.bytes+planned.exteriorBytes,cap:sharedDetailCaps.high,actualProtected:planned.roads};
 }return result;
});
check('clipped centreline rejects a behind-camera road even with a huge misleading bounds',()=>{
 const c=new THREE.PerspectiveCamera(42,16/9,.5,9000);c.position.set(0,10,0);c.lookAt(0,10,-100);c.updateMatrixWorld();
 const cluster={...protection.clusters[0],bounds:{min:[-100,-100,-100],max:[100,100,100]},sourceLineLocalXZ:[[-5,20],[5,20]]};
 assert.equal(visibleRoadClusters(c,[cluster],900,()=>10).length,0);
 cluster.sourceLineLocalXZ=[[-5,-20],[5,-20]];assert.ok(visibleRoadClusters(c,[cluster],900,()=>10).length>0);
 return {behindPixels:0,actualLineUsed:true};
});
check('source endpoint continuity prevents skipping an unaffordable middle segment',()=>{
 const clusters=[0,1,2].map(i=>({...protection.clusters[0],id:'fixture-'+i,partitionIds:['part-'+i],sourceLineLocalXZ:[[i*10,0],[(i+1)*10,0]]}));
 const visible=clusters.map((cluster,i)=>({id:cluster.id,cluster,score:100-i*10,pixels:100,distance:100,visibleSegments:[[cluster.sourceLineLocalXZ[0],cluster.sourceLineLocalXZ[1]]]}));
 const parts=clusters.map((c,i)=>({id:c.partitionIds[0],bounds:{min:[i*10,0,-1],max:[(i+1)*10,2,1]}}));
 const planner=new RoadCoveragePlanner({version:1,clusters});
 let plan=planner.plan(visible,parts,ids=>[...ids].reduce((sum,id)=>sum+(id==='part-1'?100:1),0),3);
 assert.equal(plan.acceptedPartitionIds.join('|'),'part-0');assert.ok(plan.deferredPartitionIds.includes('part-2'));
 plan=planner.plan(visible,parts,ids=>ids.size,3);assert.equal(plan.acceptedPartitionIds.length,3);
 return {wholeConnectedAcceptance:true,noSkipAcrossDeferredMiddle:true};
});
check('source range hysteresis, primary stability and leaving view release fine demand',()=>{
 const cluster=protection.clusters[0],partition={id:cluster.partitionIds[0],bounds:cluster.bounds};
 const item={id:cluster.id,cluster:{...cluster,partitionIds:[partition.id]},score:100,pixels:100,distance:300,visibleSegments:[[cluster.sourceLineLocalXZ[0],cluster.sourceLineLocalXZ.at(-1)]]};
 const planner=new RoadCoveragePlanner({version:1,clusters:[item.cluster]});
 assert.equal(planner.plan([{...item,distance:300.001}],[partition],ids=>ids.size,2).acceptedPartitionIds.length,0);
 assert.equal(planner.plan([item],[partition],ids=>ids.size,2).acceptedPartitionIds.length,1);
 assert.equal(planner.plan([{...item,distance:330}],[partition],ids=>ids.size,2).acceptedPartitionIds.length,1);
 assert.equal(planner.plan([{...item,distance:330.001}],[partition],ids=>ids.size,2).acceptedPartitionIds.length,0);
 planner.plan([item],[partition],ids=>ids.size,2);assert.equal(planner.plan([],[partition],ids=>ids.size,2).acceptedBytes,0);
 return {...roadCoverageRange};
});
check('actual same pose is selected-entity independent and small motion retains the same source corridor',()=>{
 const state=records['fixed-lam-near-high'],plans=[];
 for(const id of ['', 'building:catalog:campus-32','building:catalog:campus-33']){const s=fixture(state);s.selectedId=id;s.updateDetails(10000,true);plans.push(read(s));}
 assert.equal(JSON.stringify(plans[0].roads.acceptedFinePartitionIds),JSON.stringify(plans[1].roads.acceptedFinePartitionIds));assert.equal(JSON.stringify(plans[0].exteriors),JSON.stringify(plans[2].exteriors));
 const s=fixture(state);s.updateDetails(10000,true);const initial=read(s);
 for(let i=0;i<8;i++){const delta=Math.sin(i)*.02;s.camera.position.fromArray(state.camera.map(v=>v+delta));s.camera.lookAt(new THREE.Vector3(...state.target.map(v=>v+delta)));s.updateDetails(10400+i*400);assert.equal(JSON.stringify(s.roadCoverageState.acceptedFinePartitionIds),JSON.stringify(initial.roads.acceptedFinePartitionIds));}
 return {sourceIds:initial.roads.acceptedFinePartitionIds,samples:8};
});
check('Balanced reports every desired but unaccepted fine group and cannot silently call high protected',()=>{
 const s=fixture(records['fixed-lam-near-high'],'balanced');s.updateDetails(10000,true);const a=read(s);
 assert.ok(a.pool.chargedBytes<=sharedDetailCaps.balanced);
 for(const id of a.roads.acceptedFinePartitionIds)assert.equal(s.acceptedMesh.find(c=>c.patch.id===id).level,s.meshDetail.patches.find(p=>p.id===id).levels.fine);
 assert.ok(a.roads.desiredFinePartitionIds.every(id=>a.roads.acceptedFinePartitionIds.includes(id)||a.roads.deferredFinePartitionIds.includes(id)));
 return a;
});
check('pending old image reservations stay charged before fine coverage can use a larger lane grant',()=>{
 const cap=sharedDetailCaps.high,pool=new DetailResourcePool(cap),usage={exterior:0,mesh:0,original:0},lanes={};
 for(const lane of ['exterior','mesh','original'])lanes[lane]={memoryBytes:()=>usage[lane],setBudget:()=>{}};
 const target=observed['fixed-lam-near-high/high'].pool.demand;
 const old={exterior:target.exterior,mesh:Math.max(0,cap-target.exterior-192*1048576),original:192*1048576};
 const ceilings={exterior:cap,mesh:cap,original:cap};pool.reconcile(cap,old,ceilings,lanes);Object.assign(usage,old);
 let state=pool.reconcile(cap,target,ceilings,lanes);assert.ok(state.chargedBytes<=cap);assert.ok(state.waitingForDrain.length>0);assert.ok(pool.grants.mesh<=target.mesh);
 usage.original=Math.min(usage.original,target.original);usage.mesh=Math.min(usage.mesh,target.mesh);state=pool.reconcile(cap,target,ceilings,lanes);
 assert.equal(pool.grants.mesh,target.mesh);assert.equal(state.overCapBytes,0);return state;
});
const files=['app/road-coverage-plan.ts','app/campus-mesh-detail.ts','app/scene.ts','app/detail-resource-pool.ts',manifestPath,protectionPath];
const report={status:'pass',checkedAt:new Date().toISOString(),staged,checks:checks.length,results:checks,sourceSHA256:Object.fromEntries(files.map(path=>[path,createHash('sha256').update(fs.readFileSync(path.startsWith('/')?path:root+path)).digest('hex')])),limitations:['Actual source manifests, source centreline geometry, current Three projection and scene planning; loading boundaries and ledger counters are controlled. No browser or allocation acceptance.','UC pose is derived from its verified exterior bounds; other named poses are real captured camera/target/viewport states.','DTM height samples only rank road centreline visibility; they are not road-deck geometry or new surveyed elevations.','Deferred fine source regions may use complete high frontiers; they are not counted as protected fine.']};
fs.writeFileSync(root+'docs/source-evidence-v4/road-coverage-budget-tests.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,checks:report.checks,staged,views:Object.fromEntries(Object.entries(observed).map(([name,a])=>[name,{primary:a.roads.primaryClusterId,reservedMiB:a.roads.reservedFineBytes/1048576,accepted:a.roads.acceptedFinePartitionIds,deferred:a.roads.deferredFinePartitionIds,exteriors:a.exteriors,poolMiB:a.pool.chargedBytes/1048576}]))},null,2));
