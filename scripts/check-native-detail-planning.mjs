// Pure selection/budget QA against current checkout, real manifests and cameras.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const cache=new Map();
function load(name){
  if(cache.has(name))return cache.get(name);
  const exports={};cache.set(name,exports);
  const code=ts.transpileModule(fs.readFileSync(path.join(root,'app',name+'.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,console,Map,Set,performance,AbortController,DOMException,setTimeout,clearTimeout,
    require(id){
      if(id==='three')return THREE;
      if(id==='./spatial-masks')return {partialSlots:Array.from({length:96},(_,i)=>i?'meshPartial'+(i+1):'meshPartial')};
      if(['./source-types','./detail-priority','./quality'].includes(id))return load(id.slice(2));
      return {};
    }});
  return exports;
}
const {nativeDetailChoice,fitNativeDetailChoices,CampusMeshDetail,nativePlanBytes}=load('campus-mesh-detail');
const {visibleDetails}=load('detail-priority');
const {qualityProfiles}=load('quality');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const patches=read('public/models/hires/manifest.json').patches;
const sourceSection=(patch,section)=>patch.baselineIds?.some(id=>id.includes('/'+section+'/'));
const entrance=patches.find(p=>sourceSection(p,'12-NW-6C-6'));
assert.ok(entrance,'Current manifest must retain a source-owned 12-NW-6C-6 partition');
const camera=new THREE.PerspectiveCamera(42,1290/837.998,.5,10000);
const checks=[];
function check(name,fn){fn();checks.push({name,status:'pass'});}
const high=qualityProfiles.high;
const candidate=(id,pixels,distance,score=100)=>({id,pixels,distance,score});
check('Every current source owner has a complete high frontier and reachable terminal frontier',()=>{
  assert.equal(new Set(patches.map(patch=>patch.id)).size,patches.length);
  assert.ok(patches.length>16,'The manifest must exercise more than the former staging-owner cap');
  for(const patch of patches){
    assert.ok(patch.levels.high?.tiles.length,patch.id+'/high');
    assert.ok(patch.levels.fine?.tiles.length,patch.id+'/fine');
    assert.equal(patch.levels.fine.geometricErrorMax,0,patch.id+'/terminal-error');
    const c=nativeDetailChoice(patch,candidate(patch.id,900,40),camera,838,high,high.meshMiB*2**20);
    assert.equal(c.level,patch.levels.fine,patch.id+'/reachable');
  }
});
check('Distant current owner keeps its high frontier instead of spending on terminal leaves',()=>{
  const c=nativeDetailChoice(entrance,candidate(entrance.id,200,1000),camera,838,high,1024*2**20);
  assert.equal(c.level,entrance.levels.high);
});
check('Near level has separate enter and exit thresholds',()=>{
  const distance=250;
  const c=candidate(entrance.id,320,distance);
  assert.equal(nativeDetailChoice(entrance,c,camera,838,high,1024*2**20,false).level,entrance.levels.high);
  assert.equal(nativeDetailChoice(entrance,c,camera,838,high,1024*2**20,true).level,entrance.levels.fine);
});
check('Ultra expanded terminal entry and retention use finite distance and residual thresholds',()=>{
  const profile=qualityProfiles.ultra;
  assert.equal(nativeDetailChoice(entrance,candidate(entrance.id,400,500),camera,900,profile,1792*2**20).level,entrance.levels.fine);
  assert.equal(nativeDetailChoice(entrance,candidate(entrance.id,400,630),camera,900,profile,1792*2**20,false).level,entrance.levels.high);
  assert.equal(nativeDetailChoice(entrance,candidate(entrance.id,400,630),camera,900,profile,1792*2**20,true).level,entrance.levels.fine);
  assert.equal(nativeDetailChoice(entrance,candidate(entrance.id,400,710),camera,900,profile,1792*2**20,true).level,entrance.levels.high);
});
check('Several current near owners reserve whole groups before distant owners',()=>{
  const owners=patches.filter(p=>sourceSection(p,'12-NW-6C-6')).slice(0,3);
  const entries=owners.map((patch,index)=>({choice:nativeDetailChoice(patch,candidate(patch.id,900-index*20,60+index),camera,838,high,1024*2**20),score:100-index}));
  const result=fitNativeDetailChoices(entries,1024*2**20);
  assert.deepEqual(new Set(result.map(choice=>choice.patch.id)),new Set(owners.map(patch=>patch.id)));
  assert.ok(result.every(choice=>choice.level.tiles.length>0));
  assert.ok(nativePlanBytes(result)<=1024*2**20);
});
check('A current owner exceeding a deliberately tiny budget is not partially truncated',()=>{
  const c=nativeDetailChoice(entrance,candidate(entrance.id,1000,20),camera,838,high,1024*2**20);
  assert.equal(fitNativeDetailChoices([{choice:c,score:100}],1).length,0);
});
check('Pool preview discovers fine demand independently of a previously reduced grant and starts no loads',()=>{
  const model=Object.create(CampusMeshDetail.prototype);
  Object.assign(model,{dead:false,patches,seen:new Map(),visible:new Map(),cache:new Map(),pending:null,budgetBytes:1,
    order:new (load('detail-priority').StableDetailOrder)(),masks:{partialCoverageStats:()=>({bytes:1})}});
  const c=new THREE.PerspectiveCamera(42,1600/900,.5,9000);
  c.position.set(429.712,216.457,-1435.886);c.lookAt(336.4,123.145,-1549.934);
  const plan=model.previewPlan(c,900,qualityProfiles.ultra,1792*2**20,10000);
  assert.ok(plan.some(choice=>choice.level===choice.patch.levels.fine));
  assert.equal(model.pending,null);assert.equal(model.visible.size,0);assert.equal(model.budgetBytes,1);
  assert.equal(model.planBytes(plan),nativePlanBytes(plan,1));
  assert.equal(model.memoryBytes(),1);
});
const cameraEvidence=[];
function realView(view,profile,budgetBytes,height=view.height??837.998){
  camera.position.fromArray(view.camera);camera.lookAt(new THREE.Vector3(...view.target));camera.updateMatrixWorld();
  const ranked=visibleDetails(camera,patches,height,profile.meshPixels);
  const preferences=ranked.map(c=>({choice:nativeDetailChoice(patches.find(p=>p.id===c.id),c,camera,height,profile,budgetBytes),score:c.score}));
  const selected=fitNativeDetailChoices(preferences,budgetBytes);
  check(view.id+' does not starve any current near owner when its complete high frontiers fit',()=>{
    assert.ok(nativePlanBytes(selected)<=budgetBytes);
    const missing=preferences.filter(entry=>entry.choice.near&&!selected.some(choice=>choice.patch.id===entry.choice.patch.id));
    assert.equal(missing.length,0,missing.map(entry=>entry.choice.patch.id).join(','));
  });
  cameraEvidence.push({...view,ranked,nearOwnerIds:preferences.filter(entry=>entry.choice.near).map(entry=>entry.choice.patch.id),selected:selected.map(c=>({key:c.key,bytes:c.bytes,projectedErrorPixels:c.projectedErrorPixels,reason:c.qualityReason}))});
  return selected;
}
realView({id:'saved-UG10-near',camera:[744.195,264.693,-942.341],target:[623.513,144.011,-1089.841]},high,1024*2**20);
realView({id:'saved-entrance-near',camera:[429.712,216.457,-1435.886],target:[336.4,123.145,-1549.934]},high,1024*2**20);
const hall=read('docs/source-evidence-v4/halls-current-first-stage.json').state;
camera.aspect=hall.viewport.width/hall.viewport.height;
camera.setViewOffset(hall.viewport.width,hall.viewport.height,hall.viewport.canvasCenter[0]-hall.viewport.safeCenter[0],hall.viewport.canvasCenter[1]-hall.viewport.safeCenter[1],hall.viewport.width,hall.viewport.height);
const ultra=qualityProfiles.ultra,ultraBytes=ultra.meshMiB*2**20;
realView({id:'saved-Hall-XIII-ultra',camera:hall.camera,target:hall.target,height:hall.viewport.height},ultra,ultraBytes,hall.viewport.height);
const entranceUltra=realView({id:'full-canvas-entrance-ultra',camera:[429.712,216.457,-1435.886],target:[336.4,123.145,-1549.934],height:900},ultra,ultraBytes,900);
check('Ultra entrance view reaches terminal detail for every selected 12-NW-6C-6 owner',()=>{
  const selected=entranceUltra.filter(choice=>sourceSection(choice.patch,'12-NW-6C-6'));
  assert.ok(selected.length>0);
  assert.ok(selected.every(choice=>choice.level===choice.patch.levels.fine));
});
const report={status:'pass',checks,currentOwners:patches.length,stagingOwnerCapacity:96,cameraEvidence,limits:'Selection and budgets only. Source appearance, actual network cancellation and browser multi-angle rendering have separate checks.'};
fs.writeFileSync(path.join(root,'docs/source-evidence-v4/building-quality/native-detail-planning-tests.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
