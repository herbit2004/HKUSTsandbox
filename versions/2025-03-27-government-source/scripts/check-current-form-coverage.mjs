import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';
import sharp from 'sharp';
import * as THREE from 'three';
const root = new URL('../', import.meta.url);
const compiled = new Map();
function compile(name) {
  if (compiled.has(name)) return compiled.get(name);
  const exports = {}; compiled.set(name, exports);
  const code = ts.transpileModule(fs.readFileSync(new URL(`app/${name}.ts`, root), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code, {exports,require:id=>id==='three'?THREE:compile(id.replace('./','')),Uint8Array,Uint8ClampedArray,Map,Set,WeakMap,Math,Number,Error});
  return exports;
}
const {SpatialMasks, spatialMaskNames} = compile('spatial-masks');
const {CurrentFormCoverage} = compile('current-form-coverage');
const {isVisibleSurfaceHit} = compile('entity-picking');
const masks = new SpatialMasks(), coverage = new CurrentFormCoverage(masks);
const unified=process.argv.includes('--ivillage');
const base = new URL(`public/models/current-forms/${unified?'ivillage-rebuild':'halls-current'}/`,root);
const manifest = JSON.parse(fs.readFileSync(new URL('manifest.json',base),'utf8'));
const cases = [];
for (const building of manifest.members??manifest.buildings) {
  const {data,info} = await sharp(fs.readFileSync(new URL(building.mask.url,base))).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  assert.equal(info.width,building.mask.width); assert.equal(info.height,building.mask.height);
  cases.push({building, pixels:data});
}
let installations=0;const install=masks.set.bind(masks);masks.set=(...args)=>{if(args[0]==='currentForms')installations++;return install(...args);};
coverage.addPixelsBatch(cases.map(({building,pixels})=>({id:building.buildingId,descriptor:building.mask,pixels:new Uint8ClampedArray(pixels)})));
assert.equal(installations,1,'all sibling masks enter in one synchronous union');
assert.equal(coverage.ready.size,cases.length);
const commonMin=cases[0].building.mask.replacementMinY;
const slot = masks.slots.currentForms, image = slot.texture.value.image, b = slot.bounds.value;
const roles = ['baseline','photogrammetry','supplement','exterior'];
const meshes = Object.fromEntries(roles.map(role=>{
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial()); masks.apply(mesh,role); return [role,mesh];
}));
function visible(role,x,y,z,normal=[0,1,0]) {return isVisibleSurfaceHit({object:meshes[role],point:new THREE.Vector3(x,y,z),face:{normal:new THREE.Vector3(...normal),materialIndex:0},distance:1},masks);}
let pixelsChecked=0, occupied=0, maxEncodingError=0;
for(let row=0;row<image.height;row++) for(let col=0;col<image.width;col++){
  const x=b.x+(col+.5)*.5,z=b.y+(row+.5)*.5;
  const expected=cases.flatMap(({building:d,pixels:p})=>{
    const m=d.mask,c=Math.floor((x-m.boundsXZ.min[0])/.5),r=Math.floor((z-m.boundsXZ.min[1])/.5);
    if (!(c>=0&&r>=0&&c<m.width&&r<m.height&&p[(r*m.width+c)*4]>127)) return [];
    const alpha=p[(r*m.width+c)*4+3];
    return [{building:d,lower:m.pixelMinYEncoding&&alpha<255?Math.max(m.replacementMinY,alpha):m.replacementMinY}];
  });
  const at=(row*image.width+col)*4, on=expected.length>0, lower=on?Math.min(...expected.map(e=>e.lower)):Infinity;
  assert.equal(image.data[at]>127,on); pixelsChecked++;
  for(const role of ['baseline','photogrammetry','supplement']){
    assert.equal(visible(role,x,commonMin-.01,z),true);
    assert.equal(visible(role,x,150,z,[1,0,0]),!on||150<lower);
    assert.equal(visible(role,x,150,z),!on||150<lower);
  }
  assert.equal(visible('exterior',x,150,z),true,'new form/source interiors retain their own geometry');
  if(on){
    occupied++;
    assert.equal(visible('photogrammetry',x,lower-.01,z),true);
    assert.equal(visible('photogrammetry',x,lower+.01,z),false);
    const upper=Math.max(...expected.map(e=>e.building.mask.replacementMaxY));
    const decoded=image.data[at+1]+image.data[at+2]/256;
    maxEncodingError=Math.max(maxEncodingError,Math.abs(decoded-upper));
    assert.ok(Math.abs(decoded-upper)<=1/512);
    assert.equal(visible('photogrammetry',x,upper+.01,z),true);
    assert.equal(visible('photogrammetry',x,upper-.01,z),false);
  }
}
const oldTexture=slot.texture.value, oldReady=coverage.ready.size;
assert.throws(()=>coverage.addPixels('bad',{...cases[0].building.mask,pixelSizeMeters:1},new Uint8ClampedArray(cases[0].pixels)));
assert.equal(slot.texture.value,oldTexture); assert.equal(coverage.ready.size,oldReady);
assert.throws(()=>coverage.addPixelsBatch([
  {id:'otherwise-valid-sibling',descriptor:cases[0].building.mask,pixels:new Uint8ClampedArray(cases[0].pixels)},
  {id:'broken-last-sibling',descriptor:{...cases[1].building.mask,pixelSizeMeters:1},pixels:new Uint8ClampedArray(cases[1].pixels)},
]));
assert.equal(slot.texture.value,oldTexture);assert.equal(coverage.ready.size,oldReady);
assert.equal(coverage.ready.has('otherwise-valid-sibling'),false,'failed last sibling cannot install earlier siblings');
const alphaMasks=new SpatialMasks(),alphaCoverage=new CurrentFormCoverage(alphaMasks);
alphaCoverage.addPixels('source-support',{url:'fixture',boundsXZ:{min:[0,0],max:[.5,.5]},width:1,height:1,pixelSizeMeters:.5,replacementMinY:133.75,replacementMaxY:179.1,pixelMinYEncoding:'int-meters-alpha-255-common'},new Uint8ClampedArray([255,255,255,157]));
const alphaMesh=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial());alphaMasks.apply(alphaMesh,'photogrammetry');
for(const [y,expected] of [[133.8,true],[156.9,true],[157.1,false],[179.2,true]])assert.equal(isVisibleSurfaceHit({object:alphaMesh,point:new THREE.Vector3(.25,y,.25),face:{normal:new THREE.Vector3(1,0,0),materialIndex:0},distance:1},alphaMasks),expected);
const mixedMasks=new SpatialMasks(),mixedCoverage=new CurrentFormCoverage(mixedMasks);
mixedCoverage.addPixelsBatch([
  {id:'lower-terrace',descriptor:{url:'lower',boundsXZ:{min:[0,0],max:[.5,.5]},width:1,height:1,pixelSizeMeters:.5,replacementMinY:60,replacementMaxY:71.2},pixels:new Uint8ClampedArray([255,255,255,255])},
  {id:'upper-terrace',descriptor:{url:'upper',boundsXZ:{min:[.5,0],max:[1,.5]},width:1,height:1,pixelSizeMeters:.5,replacementMinY:129,replacementMaxY:179.1},pixels:new Uint8ClampedArray([255,255,255,255])},
]);
const mixedMesh=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial());mixedMasks.apply(mixedMesh,'photogrammetry');
for(const [x,y,expected] of [[.25,59,true],[.25,65,false],[.25,72,true],[.75,100,true],[.75,140,false],[.75,180,true]])
  assert.equal(isVisibleSurfaceHit({object:mixedMesh,point:new THREE.Vector3(x,y,.25),face:{normal:new THREE.Vector3(1,0,0),materialIndex:0},distance:1},mixedMasks),expected,`mixed terrace x=${x} y=${y}`);
for(const role of roles){
  const material=meshes[role].material;
  const shader={uniforms:{},vertexShader:'#include <begin_vertex>',fragmentShader:'#include <clipping_planes_fragment>'};
  material.onBeforeCompile(shader,{});
  assert.equal(spatialMaskNames(role).includes('currentForms'),role!=='exterior');
  if(role!=='exterior')assert.ok(shader.fragmentShader.includes('d_currentForms>1.5||'));
}
const report={status:'pass',readyBuildings:[...coverage.ready.keys()],sourceMaskPixels:cases.reduce((s,e)=>s+e.building.mask.width*e.building.mask.height,0),unionPixels:pixelsChecked,occupiedUnionPixels:occupied,unionBytes:image.data.length,maxEncodingError,maskSamplersAdded:1,checks:['source pixel union including empty courtyard pixels','horizontal and vertical old-source removal','below-ground and above-guard preservation','per-pixel source-support lower guard preserves underlying hillside','new form and unmasked source interior preservation','invalid source grid retains previous complete mask','all siblings commit in one union; invalid last sibling rolls back entire batch','CPU and shader height mode branches'],limitation:'Checks real source PNG pixels and current code. Actual WebGL composition and browser floor transitions require separate runtime acceptance.'};
fs.writeFileSync(new URL(`docs/source-evidence-v4/${unified?'ivillage-rebuild/current-form-coverage':'current-form-coverage'}.json`,root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
