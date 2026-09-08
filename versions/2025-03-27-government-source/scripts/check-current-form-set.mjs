// Real installed Three GLTFLoader + current production module, with controlled
// self-contained GLB fixtures and injectable HTTP/bitmap latency and failures.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import ts from 'typescript';
import sharp from 'sharp';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

const root = new URL('../', import.meta.url), modules = new Map(), reports = [];
function load(name) {
  if (modules.has(name)) return modules.get(name);
  const exports = {}; modules.set(name, exports);
  const code = ts.transpileModule(fs.readFileSync(new URL(`app/${name}.ts`, root), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code, {exports,console,performance,Map,Set,WeakMap,Promise,ArrayBuffer,Uint8Array,Uint8ClampedArray,DataView,TextDecoder,Blob,URL,DOMException,AbortController,setTimeout,clearTimeout,crypto:webcrypto,fetch,
    require(id) {if (id==='three') return THREE;if (id==='three/addons/loaders/GLTFLoader.js') return {GLTFLoader};if (id.startsWith('./')) return load(id.slice(2));throw new Error(id);}});
  return exports;
}
const {loadCurrentFormSet,parseCurrentFormSetManifest} = load('current-form-set');
const originalBitmap = globalThis.createImageBitmap, originalSelf = globalThis.self;
globalThis.self = globalThis;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function gate() {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
async function ticks() {await new Promise(resolve=>setImmediate(resolve));}
async function until(check) {for(let i=0;i<1000;i++){if(check())return;await new Promise(resolve=>setTimeout(resolve,1));}throw new Error('Test condition did not arrive');}
function bitmap(log, name='mask', width=1, height=1) {const value={width,height,closed:0,close(){this.closed++;}};log.push({name,value});return value;}
function glbFixture(mutate=()=>{}) {
  const position=Buffer.from(new Float32Array([-.5,0,0,.5,0,0,0,1,0]).buffer);
  const binary=Buffer.alloc(Math.ceil((position.length+png.length)/4)*4);position.copy(binary);png.copy(binary,position.length);
  const document={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0,1,2,3]}],nodes:Array.from({length:4},(_,i)=>({name:'member-'+i,mesh:0,translation:[i*3,0,0],extras:{entityId:'building:controlled-'+i,buildingId:'official-'+i,sourceEvidence:'controlled-shared-source'}})),buffers:[{byteLength:binary.length}],bufferViews:[{buffer:0,byteOffset:0,byteLength:position.length},{buffer:0,byteOffset:position.length,byteLength:png.length}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[-.5,0,0],max:[.5,1,0]}],meshes:[{primitives:[{attributes:{POSITION:0},material:0}]}],images:[{bufferView:1,mimeType:'image/png'}],samplers:[{wrapS:10497,wrapT:33071}],textures:[{source:0,sampler:0}],materials:[{pbrMetallicRoughness:{baseColorTexture:{index:0},metallicFactor:0,roughnessFactor:.75}}]};
  mutate(document);
  const json=Buffer.from(JSON.stringify(document)),jsonPad=Buffer.alloc(Math.ceil(json.length/4)*4,32);json.copy(jsonPad);
  const header=Buffer.alloc(20);header.writeUInt32LE(0x46546c67,0);header.writeUInt32LE(2,4);header.writeUInt32LE(20+jsonPad.length+8+binary.length,8);header.writeUInt32LE(jsonPad.length,12);header.writeUInt32LE(0x4e4f534a,16);
  const binHeader=Buffer.alloc(8);binHeader.writeUInt32LE(binary.length,0);binHeader.writeUInt32LE(0x004e4942,4);
  return Buffer.concat([header,jsonPad,binHeader,binary]);
}
function fixture({mutate,mask=true}={}) {
  const bytes=glbFixture(mutate),images=[],network=[],decoded=[],disposed=[],parsed=[];
  const manifest={version:1,asset:{url:'whole.glb',sha256:hash(bytes),bytes:bytes.length},members:Array.from({length:4},(_,i)=>({entityId:'building:controlled-'+i,buildingId:'official-'+i,nodeName:'member-'+i,bounds:{min:[i*3-.5,0,0],max:[i*3+.5,1,0]},...(mask?{mask:{url:`mask-${i}.png`,sha256:hash(png),bytes:png.length,boundsXZ:{min:[0,0],max:[.5,.5]},width:1,height:1,pixelSizeMeters:.5,replacementMinY:0,replacementMaxY:2}}:{})}))};
  globalThis.createImageBitmap=async()=>bitmap(images,'GLB');
  const options={baseURL:'https://current-form.invalid/stage/',
    fetch:async(url,init)=>{network.push({url,signal:init.signal});if(init.signal.aborted)throw new DOMException('cancelled','AbortError');return new Response(url.endsWith('.glb')?bytes:png);},
    decodeBitmap:async()=>bitmap(images,'mask-'+decoded.push(1)),
    createLoader:manager=>{const loader=new GLTFLoader(manager),parse=loader.parseAsync.bind(loader);loader.parseAsync=async(...args)=>{const value=await parse(...args);parsed.push(value);const seen=new Set();value.scene.traverse(o=>{for(const r of [o.geometry,...(o.material?Array.isArray(o.material)?o.material:[o.material]:[])])if(r&&!seen.has(r)){seen.add(r);r.addEventListener('dispose',()=>disposed.push(r));}if(o.material?.map&&!seen.has(o.material.map)){seen.add(o.material.map);o.material.map.addEventListener('dispose',()=>disposed.push(o.material.map));}});return value;};return loader;}};
  return {bytes,images,network,decoded,disposed,parsed,manifest,options};
}
async function check(name, run) {const began=performance.now();try{const detail=await run();reports.push({name,status:'pass',milliseconds:Math.round(performance.now()-began),detail});}catch(error){reports.push({name,status:'fail',error:error.stack});}}

await check('unknown manifest boundary rejects duplicate identities and nonfinite domains before IO',async()=>{
  const f=fixture();for(const key of ['entityId','buildingId','nodeName']){const m=structuredClone(f.manifest);m.members[1][key]=m.members[0][key];assert.throws(()=>parseCurrentFormSetManifest(m),/Duplicate/);}
  for(const value of [null,{version:2}, {...f.manifest,members:[]}])assert.throws(()=>parseCurrentFormSetManifest(value));
  const bad=structuredClone(f.manifest);bad.members[0].bounds.min[0]=NaN;assert.throws(()=>parseCurrentFormSetManifest(bad));assert.equal(f.network.length,0);return {duplicates:['entityId','buildingId','nodeName'],invalidValuesRejected:true};
});
await check('GLB SHA and exact byte length are checked before parse, no external dependency escapes asset integrity',async()=>{
  for(const change of [m=>m.asset.sha256='0'.repeat(64),m=>m.asset.bytes++]){const f=fixture();change(f.manifest);await assert.rejects(loadCurrentFormSet(f.manifest,f.options),/differs from manifest/);assert.equal(f.parsed.length,0);}
  const f=fixture({mutate:d=>{d.images=[{uri:'https://unverified.invalid/unhashed.png'}];}});await assert.rejects(loadCurrentFormSet(f.manifest,f.options),/embed every/);assert.equal(f.parsed.length,0);assert.equal(f.network.length,1);return {parserNotInvoked:true};
});
await check('all four members and delayed last mask become ready together; complete commit preserves shared native resources',async()=>{
  const f=fixture(),last=gate();let count=0;f.options.decodeBitmap=async()=>{count++;if(count===4)await last.promise;return bitmap(f.images,'mask-'+count);};
  const parent=new THREE.Group();let ready;const promise=loadCurrentFormSet(f.manifest,f.options).then(set=>{ready=set;return set;});await until(()=>count===4);assert.equal(ready,undefined);assert.equal(parent.children.length,0);assert.equal(f.images.every(i=>i.value.closed===0),true);
  last.resolve();const set=await promise;assert.equal(set.state,'ready');assert.equal(set.root.parent,null);assert.equal(set.members.length,4);
  const roots=set.members.map(m=>m.root);assert.equal(new Set(roots.map(r=>r.material)).size,1);assert.equal(new Set(roots.map(r=>r.geometry)).size,1);assert.equal(new Set(roots.map(r=>r.material.map)).size,1);
  for(let i=0;i<4;i++){assert.equal(roots[i].userData.entityId,f.manifest.members[i].entityId);assert.equal(roots[i].userData.sourceEvidence,'controlled-shared-source');assert.equal(roots[i].position.x,i*3);}
  let activate=0,deactivate=0;set.commit(parent,{activate:members=>{activate++;assert.equal(members.every(m=>!!m.mask),true);assert.equal(parent.children.length,0);},deactivate:()=>deactivate++});set.commit(parent);assert.equal(parent.children.length,4);assert.ok(parent.children.every((child,i)=>child===roots[i]));assert.equal(set.root.children.length,0);assert.equal(activate,1);assert.equal(f.images.every(i=>i.value.closed===0),true);
  set.dispose();set.dispose();assert.equal(parent.children.length,0);assert.equal(deactivate,1);assert.equal(set.state,'disposed');assert.equal(f.disposed.length,3);assert.equal(new Set(f.disposed).size,3);assert.equal(f.images.every(i=>i.value.closed===1),true);assert.throws(()=>set.commit(parent),/disposed/);return {atomicMembers:4,sharedResourcesDisposedExactlyOnce:3,bitmapsClosedOnce:f.images.length};
});
await check('missing, duplicate or mismatched GLB roots reject the entire set and release shared resources',async()=>{
  const changes=[d=>d.scenes[0].nodes.pop(),d=>d.nodes[3].name='member-2',d=>d.nodes[2].extras.entityId='wrong',d=>d.nodes[2].extras.buildingId='wrong'];
  for(const mutate of changes){const f=fixture({mutate});await assert.rejects(loadCurrentFormSet(f.manifest,f.options),/roots differ|duplicate root|identity/);assert.equal(f.decoded.length,0);assert.equal(f.images.every(i=>i.value.closed===1),true);assert.equal(f.disposed.length,3);}
  return {invalidRootCases:changes.length};
});
await check('actual transformed geometry and descendant ownership must fit the declared member',async()=>{
  const shifted=fixture({mutate:d=>d.nodes[2].translation[1]=5});await assert.rejects(loadCurrentFormSet(shifted.manifest,shifted.options),/outside its checked bounds/);assert.equal(shifted.images.every(i=>i.value.closed===1),true);
  const child=fixture({mutate:d=>{d.nodes.push({name:'conflicting-child',mesh:0,extras:{entityId:'other'}});d.nodes[0].children=[4];}});await assert.rejects(loadCurrentFormSet(child.manifest,child.options),/conflicting identity/);assert.equal(child.images.every(i=>i.value.closed===1),true);return {noWrongOwnerCommit:true};
});
await check('last mask HTTP failure or wrong dimensions releases complete parsed GLB and all earlier mask bitmaps',async()=>{
  for(const mode of ['http','dimensions']){const f=fixture(),get=f.options.fetch,decode=f.options.decodeBitmap;let count=0;f.options.fetch=async(...args)=>mode==='http'&&args[0].endsWith('mask-3.png')?new Response('',{status:503}):get(...args);f.options.decodeBitmap=async(...args)=>{count++;return mode==='dimensions'&&count===4?bitmap(f.images,'wrong-size',2,1):decode(...args);};await assert.rejects(loadCurrentFormSet(f.manifest,f.options),/HTTP 503|dimensions differ/);assert.equal(f.images.every(i=>i.value.closed===1),true);assert.equal(f.disposed.length,3);}return {wholeSetFailures:2};
});
await check('abort during unabortable mask decode waits for late bitmap and then releases everything',async()=>{
  const f=fixture(),pending=gate(),abort=new AbortController();let decoding=false,settled=false;f.options.signal=abort.signal;f.options.decodeBitmap=async()=>{decoding=true;await pending.promise;return bitmap(f.images,'late-mask');};const result=loadCurrentFormSet(f.manifest,f.options).then(()=>{throw new Error('unexpected ready');},error=>error).finally(()=>settled=true);await until(()=>decoding);abort.abort();await ticks();assert.equal(settled,false);assert.equal(f.network.every(n=>n.signal.aborted),true);pending.resolve();const error=await result;assert.equal(error.name,'AbortError');assert.equal(f.images.every(i=>i.value.closed===1),true);assert.equal(f.disposed.length,3);return {didNotResolveBeforeDecodeDrain:true};
});
await check('abort during real GLTF embedded-image decode drains parser and cleans late shared bitmap',async()=>{
  const f=fixture({mask:false}),pending=gate(),abort=new AbortController();let decoding=false,settled=false;globalThis.createImageBitmap=async()=>{decoding=true;await pending.promise;return bitmap(f.images,'late-GLB');};f.options.signal=abort.signal;const result=loadCurrentFormSet(f.manifest,f.options).then(()=>{throw new Error('unexpected ready');},e=>e).finally(()=>settled=true);await until(()=>decoding);abort.abort();await ticks();assert.equal(settled,false);pending.resolve();assert.equal((await result).name,'AbortError');assert.equal(f.images.length,1);assert.equal(f.images[0].value.closed,1);assert.equal(f.disposed.length,3);return {realGLTFParserLateBitmapClosedOnce:true};
});
await check('real GLTF swallowed texture error cannot produce ready null-map facades',async()=>{
  const f=fixture();globalThis.createImageBitmap=async()=>{throw new DOMException('controlled allocation failure','InvalidStateError');};await assert.rejects(loadCurrentFormSet(f.manifest,f.options),/dependency failed/);assert.equal(f.decoded.length,0);assert.equal(f.parsed.length,1);assert.equal(f.disposed.length,2);return {nullMapParseBlocked:true};
});
await check('shared mask URL decodes once, while every member hash remains enforced',async()=>{
  const f=fixture();for(const m of f.manifest.members)m.mask.url='shared.png';const set=await loadCurrentFormSet(f.manifest,f.options);assert.equal(f.decoded.length,1);assert.equal(new Set(set.members.map(m=>m.mask)).size,1);set.dispose();assert.equal(f.images.every(i=>i.value.closed===1),true);
  const bad=fixture();for(const m of bad.manifest.members)m.mask.url='shared.png';bad.manifest.members[1].mask.sha256='0'.repeat(64);await assert.rejects(loadCurrentFormSet(bad.manifest,bad.options),/Shared current form mask SHA/);assert.equal(bad.decoded.length,1);assert.equal(bad.images.every(i=>i.value.closed===1),true);return {sharedMaskTextureAndDecode:true,secondDescriptorStillVerified:true};
});
await check('commit coverage failure invokes rollback and never exposes a subset; rollback failure still releases GPU resources',async()=>{
  for(const throws of [false,true]){const f=fixture(),set=await loadCurrentFormSet(f.manifest,f.options),parent=new THREE.Group();let active=[];assert.throws(()=>set.commit(parent,{activate:members=>{active.push(members[0].descriptor.entityId);throw new Error('controlled coverage failure');},deactivate:()=>{active=[];if(throws)throw new Error('controlled rollback failure');}}),/controlled/);assert.equal(active.length,0);assert.equal(parent.children.length,0);assert.equal(set.state,'disposed');assert.equal(f.disposed.length,3);assert.equal(f.images.every(i=>i.value.closed===1),true);}return {failedCommitLeavesNoMembers:true};
});
await check('already-aborted request does not fetch, and timeout also waits for decode disposal',async()=>{
  const f=fixture(),abort=new AbortController();abort.abort();await assert.rejects(loadCurrentFormSet(f.manifest,{...f.options,signal:abort.signal}),e=>e.name==='AbortError');assert.equal(f.network.length,0);
  const slow=fixture(),pending=gate();let decoding=false,settled=false;slow.options.timeoutMs=100;slow.options.decodeBitmap=async()=>{decoding=true;await pending.promise;return bitmap(slow.images,'late-timeout');};const result=loadCurrentFormSet(slow.manifest,slow.options).catch(e=>e).finally(()=>settled=true);await until(()=>decoding);await until(()=>slow.network[0].signal.aborted);assert.equal(settled,false);pending.resolve();assert.equal((await result).name,'AbortError');assert.equal(slow.images.every(i=>i.value.closed===1),true);return {timeoutDrains:true};
});

await check('final Hall X-XIII GLB and four checked PNG masks load through real parser and commit four independent roots in one coverage batch',async()=>{
  const base=new URL('public/models/current-forms/ivillage-rebuild/',root);
  const manifestBytes=fs.readFileSync(new URL('manifest.json',base)),manifest=JSON.parse(manifestBytes);
  assert.equal(manifest.members.length,4);
  assert.deepEqual(manifest.members.map(m=>m.nodeName),['ug-hall-10','ug-hall-11','ug-hall-12','ug-hall-13']);
  const images=[],requests=[];
  const decode=async(blob)=>{
    const {data,info}=await sharp(Buffer.from(await blob.arrayBuffer())).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const image=bitmap(images,'real-source',info.width,info.height);image.data=new Uint8ClampedArray(data);return image;
  };
  globalThis.createImageBitmap=decode;
  const set=await loadCurrentFormSet(manifest,{baseURL:'https://current-form.invalid/real/',
    fetch:async url=>{const name=new URL(url).pathname.replace('/real/','');assert.ok(!name.includes('..')&&!name.includes('/'));requests.push(name);return new Response(fs.readFileSync(new URL(name,base)));},decodeBitmap:decode});
  load('photographic-materials').preparePhotographicMaterials(set.root,4);
  assert.equal(requests.length,5);assert.equal(set.root.children.length,4);assert.equal(set.state,'ready');
  const {SpatialMasks}=load('spatial-masks'),{CurrentFormCoverage}=load('current-form-coverage');
  const masks=new SpatialMasks(),coverage=new CurrentFormCoverage(masks),parent=new THREE.Group();
  const resourceSet=new Set(),geometries=new Set(),materials=new Set(),textures=new Set();let materialUses=0,triangles=0;
  for(const member of set.members)member.root.traverse(o=>{
    assert.equal(o.userData.entityId,member.descriptor.entityId);assert.equal(o.userData.buildingId,member.descriptor.buildingId);
    if(!o.isMesh)return;geometries.add(o.geometry);triangles+=(o.geometry.index?.count??o.geometry.attributes.position.count)/3;
    for(const m of Array.isArray(o.material)?o.material:[o.material]){materials.add(m);materialUses++;if(m.map){assert.ok(m.isMeshBasicMaterial);assert.equal(m.map.anisotropy,4);if(o.geometry.attributes.color)assert.equal(m.vertexColors,true);}for(const value of Object.values(m))if(value?.isTexture)textures.add(value);}
  });
  assert.ok(materialUses>materials.size);assert.ok(triangles>50000);
  let disposed=0;for(const r of [...geometries,...materials,...textures,...set.members.map(m=>m.mask)]){resourceSet.add(r);r.addEventListener('dispose',()=>disposed++);}
  let batches=0;set.commit(parent,{activate:members=>{batches++;coverage.addPixelsBatch(members.map(m=>({id:m.descriptor.buildingId,descriptor:m.descriptor.mask,pixels:m.mask.image.data})));assert.equal(parent.children.length,0);},deactivate:()=>coverage.removeBatch(manifest.members.map(m=>m.buildingId))});
  assert.equal(parent.children.length,4);assert.equal(coverage.ready.size,4);assert.equal(batches,1);
  for(let i=0;i<4;i++)assert.equal(parent.children[i],set.members[i].root);
  parent.children[0].visible=false;assert.equal(parent.children.filter(c=>c.visible).length,3);parent.children[0].visible=true;
  const union=masks.slots.currentForms.texture.value.image;assert.equal(union.width,445);assert.equal(union.height,324);
  const occupied=union.data.reduce((n,value,index)=>n+(index%4===0&&value>127?1:0),0);assert.ok(occupied>10000);
  assert.equal(images.every(i=>i.value.closed===0),true);set.dispose();assert.equal(parent.children.length,0);assert.equal(coverage.ready.size,0);assert.equal(masks.slots.currentForms.enabled.value,0);assert.equal(disposed,resourceSet.size);assert.equal(images.every(i=>i.value.closed===1),true);masks.dispose();
  return {manifestSha256:hash(manifestBytes),assetSha256:manifest.asset.sha256,assetBytes:manifest.asset.bytes,rootNames:manifest.members.map(m=>m.nodeName),triangles,uniqueGeometries:geometries.size,materialUses,uniqueSharedMaterials:materials.size,uniqueGLTFTextures:textures.size,maskImages:4,coverageUnionOccupiedPixels:occupied,coverageBatches:batches,allOwnedResourcesDisposedOnce:resourceSet.size,decodedSourceImages:images.length,sourceImageSizes:images.map(i=>[i.value.width,i.value.height]),visualAcceptance:false};
});

await check('actual Innovation uses the same complete-set loader and photographic conversion, with partial indoor floor evidence outside the default exterior',async()=>{
  const base=new URL('public/models/current-forms/innovation/',root);
  const manifest=JSON.parse(fs.readFileSync(new URL('manifest.json',base))),images=[];
  const decode=async blob=>{
    const raw=Buffer.from(await blob.arrayBuffer());
    const {data,info}=await sharp(raw).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const reference=manifest.appearanceTextures.find(t=>t.sha256===hash(raw));assert.ok(reference);
    assert.deepEqual(reference.dimensions,[info.width,info.height]);
    const bitmapImage=bitmap(images,'original-JPEG',info.width,info.height);bitmapImage.data=data;return bitmapImage;
  };
  globalThis.createImageBitmap=decode;
  const set=await loadCurrentFormSet(manifest,{baseURL:'https://current-form.invalid/innovation/',
    fetch:async url=>new Response(fs.readFileSync(new URL(new URL(url).pathname.replace('/innovation/',''),base))),decodeBitmap:decode});
  assert.equal(set.members.length,1);assert.equal(set.members[0].root.name,'campus-19');
  const resources=new Set();let triangles=0,meshes=0,mapped=0;
  load('photographic-materials').preparePhotographicMaterials(set.root,4);
  set.root.traverse(o=>{
    assert.notEqual(o.userData.representationRole,'exact_source_floor_parts');
    if(!o.isMesh)return;meshes++;triangles+=(o.geometry.index?.count??o.geometry.attributes.position.count)/3;resources.add(o.geometry);
    for(const material of Array.isArray(o.material)?o.material:[o.material]){
      resources.add(material);if(material.map){mapped++;assert.ok(material.isMeshBasicMaterial);assert.equal(material.map.anisotropy,4);}
      for(const value of Object.values(material))if(value?.isTexture)resources.add(value);
    }
  });
  assert.equal(triangles,manifest.triangles);assert.equal(meshes,manifest.primitives);assert.equal(images.length,manifest.appearanceTextures.length);assert.equal(mapped,72);
  const disposals=new Map([...resources].map(r=>[r,0]));for(const r of resources)r.addEventListener('dispose',()=>disposals.set(r,disposals.get(r)+1));
  const parent=new THREE.Group();set.commit(parent);assert.equal(parent.children.length,1);assert.equal(parent.children[0],set.members[0].root);
  set.dispose();set.dispose();assert.equal(parent.children.length,0);assert.ok([...disposals.values()].every(n=>n===1));assert.ok(images.every(i=>i.value.closed===1));
  return {assetSHA256:manifest.asset.sha256,bytes:manifest.asset.bytes,triangles,meshes,mapped,activeSourceFloors:0,resourcesDisposedOnce:resources.size,embeddedOriginalImages:images.length,visualAcceptance:false};
});

globalThis.createImageBitmap=originalBitmap;globalThis.self=originalSelf;
const report={status:reports.every(r=>r.status==='pass')?'pass':'fail',passed:reports.filter(r=>r.status==='pass').length,total:reports.length,moduleSha256:hash(fs.readFileSync(new URL('app/current-form-set.ts',root))),checks:reports,limitations:['Lifecycle failures use real installed GLTFLoader with controlled four-root GLB geometry and injected bitmap completion. The final integration case also loads the actual Hall X-XIII GLB, decodes its embedded image and all four source PNG masks using sharp, and executes current coverage batch logic.','No renderer or browser is created; actual WebGL appearance, texture upload and interactive floor/pick behavior remain root browser QA.','Coverage hooks must implement a synchronous batch transaction and rollback; this module does not change CurrentFormCoverage.']};
fs.writeFileSync(new URL('docs/source-evidence-v4/current-form-set-tests.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));if(report.status!=='pass')process.exitCode=1;
