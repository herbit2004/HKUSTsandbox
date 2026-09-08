// Read current source and reproduce the saved real browser Hall XIII projection.
// This is a planning / explicit allocation inventory, not a GPU-memory reading.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import * as THREE from 'three';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const cache=new Map();
function load(name){
  if(cache.has(name))return cache.get(name);
  const exports={};cache.set(name,exports);
  const code=ts.transpileModule(fs.readFileSync(path.join(root,'app',name+'.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,console,Map,Set,performance,AbortController,DOMException,setTimeout,clearTimeout,
    require(id){if(id==='three')return THREE;if(['./source-types','./detail-priority','./quality'].includes(id))return load(id.slice(2));return {};}});
  return exports;
}
const state=read('docs/source-evidence-v4/halls-current-first-stage.json').state;
const patches=read('public/models/hires/manifest.json').patches;
const exteriors=read('public/models/exteriors/manifest.json').bundles;
const {visibleDetails}=load('detail-priority');
const {nativeDetailChoice,fitNativeDetailChoices}=load('campus-mesh-detail');
const {qualityProfiles}=load('quality');
const {textureMipBytes}=load('source-types');
const viewport=state.viewport;
const camera=new THREE.PerspectiveCamera(42,viewport.width/viewport.height,.5,9000);
camera.position.fromArray(state.camera);camera.lookAt(new THREE.Vector3(...state.target));
camera.setViewOffset(viewport.width,viewport.height,viewport.canvasCenter[0]-viewport.safeCenter[0],viewport.canvasCenter[1]-viewport.safeCenter[1],viewport.width,viewport.height);
camera.updateMatrixWorld();
const preference=qualityProfiles[state.quality.level];
const ranked=visibleDetails(camera,patches,viewport.height,preference.meshPixels);
const entries=ranked.map(candidate=>({candidate,score:candidate.score,choice:nativeDetailChoice(patches.find(p=>p.id===candidate.id),candidate,camera,viewport.height,preference,state.meshDetail.budgetBytes)}));
const selected=fitNativeDetailChoices(entries,state.meshDetail.budgetBytes);
const maskOf=choice=>choice.level.mask??choice.patch.mask;
// Replay the specific previous policy behind the saved browser failure.
// The policy always upgraded visible Ultra entries before greedy whole-group fit.
const previousEntries=entries.map(({candidate,choice})=>{
 const level=choice.patch.levels.fine??choice.patch.levels.high;
 const mask=level.mask??choice.patch.mask;
 return {candidate,choice:{...choice,key:choice.patch.id+(choice.patch.levels.fine?'/fine':'/high'),level,
   bytes:level.tiles.reduce((n,t)=>n+t.textureDimensions.reduce((s,[w,h])=>s+textureMipBytes(w,h),0),mask?mask.width*mask.height*4:0)}};
});
let previousBytes=0;
const previousSelected=[];
for(const {choice}of previousEntries){
 let accepted=choice;
 if(previousBytes+accepted.bytes>state.meshDetail.budgetBytes&&choice.level===choice.patch.levels.fine){
  const level=choice.patch.levels.high,mask=level.mask??choice.patch.mask;
  accepted={...choice,key:choice.patch.id+'/high',level,
   bytes:level.tiles.reduce((n,t)=>n+t.textureDimensions.reduce((s,[w,h])=>s+textureMipBytes(w,h),0),mask?mask.width*mask.height*4:0)};
 }
 if(previousBytes+accepted.bytes>state.meshDetail.budgetBytes)continue;
 previousBytes+=accepted.bytes;previousSelected.push(accepted);
}
function memoryOf(choice){
 const mask=maskOf(choice);
 return {key:choice.key,gpuRgba8MipBytes:choice.level.tiles.reduce((s,t)=>s+t.textureDimensions.reduce((n,[w,h])=>n+textureMipBytes(w,h),0),0),
   sourceBitmapRgba8Bytes:choice.level.tiles.reduce((s,t)=>s+t.textureDimensions.reduce((n,[w,h])=>n+w*h*4,0),0),
   maskRgba8Bytes:mask?mask.width*mask.height*4:0};
}
const visible=state.meshDetail.visible.map(key=>{
 const index=key.lastIndexOf('/');const patch=patches.find(p=>p.id===key.slice(0,index));
 return {key,patch,level:patch.levels[key.slice(index+1)]};
});
const exteriorRows=exteriors.filter(bundle=>state.exterior.visibleIds.includes(bundle.id)).map(bundle=>({id:bundle.id,
 gpuRgba8MipBytes:bundle.objects.reduce((s,o)=>s+o.textureDimensions.reduce((n,[w,h])=>n+textureMipBytes(w,h),0),0),
 sourceBitmapRgba8Bytes:bundle.objects.reduce((s,o)=>s+o.textureDimensions.reduce((n,[w,h])=>n+w*h*4,0),0),
 maskRgba8Bytes:bundle.mask.width*bundle.mask.height*4}));
const original=read('public/models/texture-detail-manifest.json');
const sources=new Map(original.tiles.flatMap(tile=>Object.values(tile.materials).map(source=>[source.url,source])));
const originalUrls=state.textureDetail.ready.split('|').filter(Boolean);
const textureRows=originalUrls.map(url=>sources.get(url));
if(textureRows.some(source=>!source))throw new Error('Saved original atlas not in current source manifest');
const originals={gpuRgba8MipBytes:textureRows.reduce((n,t)=>n+textureMipBytes(t.width,t.height),0),sourceBitmapRgba8Bytes:textureRows.reduce((n,t)=>n+t.width*t.height*4,0)};
const visibleRows=visible.map(memoryOf);
const pendingEntry=previousEntries.find(entry=>state.meshDetail.failureKey.startsWith(entry.choice.patch.id+'/'));
const pending=memoryOf(pendingEntry.choice);
const completedTiles=Number(state.meshDetail.failureKey.match(/ @ (\d+)\//)[1]);
const decodedPartialBytes=pendingEntry.choice.level.tiles.slice(0,completedTiles).reduce((s,t)=>s+t.textureDimensions.reduce((n,[w,h])=>n+w*h*4,0),0);
const total=(rows,key)=>rows.reduce((n,row)=>n+row[key],0);
const steadyGpu=total(visibleRows,'gpuRgba8MipBytes')+total(exteriorRows,'gpuRgba8MipBytes')+originals.gpuRgba8MipBytes;
const steadyBitmap=total(visibleRows,'sourceBitmapRgba8Bytes')+total(exteriorRows,'sourceBitmapRgba8Bytes')+originals.sourceBitmapRgba8Bytes;
const report={status:'saved-browser-failure-and-current-policy-replay',replay:{camera:state.camera,target:state.target,viewport,mode:state.quality.mode,level:state.quality.level},
 previousUnboundedUltraPlan:previousSelected.map(choice=>({key:choice.key,groupMiB:choice.bytes/2**20})),
 previousPlanMiB:previousBytes/2**20,currentPlanMiB:selected.reduce((n,c)=>n+c.bytes,0)/2**20,
 candidatePlan:entries.map(({candidate,choice})=>({...candidate,key:choice.key,near:choice.near,reason:choice.qualityReason,projectedErrorPixels:choice.projectedErrorPixels,groupMiB:choice.bytes/2**20,selected:selected.some(c=>c.key===choice.key)})),
 selected:selected.map(choice=>({key:choice.key,groupMiB:choice.bytes/2**20})),
 savedVisibleMeshes:visibleRows,savedVisibleExteriors:exteriorRows,savedOriginalTextureAtlases:originals,
 failedTransaction:{...pending,completedTiles,completedSourceBitmapBytes:decodedPartialBytes},
 explicitAllocationInventory:{visibleTextureGpuRgba8MipBytes:steadyGpu,retainedSourceBitmapRgba8Bytes:steadyBitmap,
 retainedCpuAndGpuTextureBytes:steadyGpu+steadyBitmap,withFailedPartialDecodeBytes:steadyGpu+steadyBitmap+decodedPartialBytes,
 omission:'Excludes baseline low textures, geometry buffers, GLB/parser buffers, ImageBitmap decoder intermediates, renderer targets, masks, current-form and surface textures, browser overhead. RGBA8 size is an allocation model, not measured actual GPU/browser resident memory.'},
 diagnosis:[
 'The previous ultra meshFine=true policy upgraded every frustum-visible patch with a saved fine level, with no distance or projected-error ceiling. The saved Hall view therefore requested remote entrance fine groups.',
 'The frustum candidates are actually on-screen under this full canvas/safe-center projection; their distant fine request is not stale selection or pending cancellation.',
 'Mesh, coherent exterior and original-atlas budgets are separately bounded but additive. Mip byte accounting reserves GPU-format texture allocation and omits the retained source ImageBitmap allocation and upload/decode intermediates.',
 'A pending atomic mesh group keeps all decoded tile images until group readiness. Only after complete success does it enter the visible scene; source bitmaps are kept for live/cached textures afterwards.',
 'The saved ImageBitmap allocation failure is direct browser evidence. The explicit source-dimension inventory supports resource pressure as a cause; it does not establish a measured process limit.'
 ],
 implementedSelectionFix:[
 'Ultra terminal entry requires a normal large near view or distance<=600m and projected residual>=2px; retention uses660m/1.5px. All quality modes first reserve complete near high frontiers, then upgrade while all whole groups fit.'
 ],
 remainingCoordinatorWork:[
 'Root coordinator should reserve a shared texture working-set allowance across source bitmaps plus mip allocations, including pending transaction reservations. Keep per-building source groups atomic and original textures unchanged.',
 'Before a new decode, release hidden/replaced original atlases and lower-priority far groups by complete group. Preserve requested close buildings and report deferred whole groups rather than repeatedly retry the same allocation peak.'
 ]};
fs.writeFileSync(path.join(root,'docs/source-evidence-v4/building-quality/hall-detail-resource-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({candidatePlan:report.candidatePlan,previousPlanMiB:report.previousPlanMiB,currentPlanMiB:report.currentPlanMiB,selected:report.selected,explicitAllocationInventory:report.explicitAllocationInventory,failedTransaction:report.failedTransaction},null,2));
