// Current typed source; real source PNG masks + controlled lifecycle boundaries.
import fs from 'node:fs';
import vm from 'node:vm';
import zlib from 'node:zlib';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import * as ts from 'typescript';
import * as THREE from 'three';
const root = fileURLToPath(new URL('../', import.meta.url));
function compile(name) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(root+'app/'+name+'.ts','utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,require(id){return id==='three'?THREE:compile('source-types');},
    Uint8Array,Map,Set,WeakMap,Math,Number,Error});
  return exports;
}
// Our source coverage PNGs are lossless 8-bit greyscale without interlacing.
function readMask(path) {
  const b=fs.readFileSync(path);let width,height,bytes=[];
  for(let at=8;at<b.length;){const n=b.readUInt32BE(at),type=b.toString('ascii',at+4,at+8),data=b.subarray(at+8,at+8+n);at+=12+n;
    if(type==='IHDR'){width=data.readUInt32BE(0);height=data.readUInt32BE(4);assert.equal(data[8],8);assert.equal(data[9],0);assert.equal(data[12],0);}
    if(type==='IDAT')bytes.push(data);
  }
  const packed=zlib.inflateSync(Buffer.concat(bytes)),data=new Uint8Array(width*height);let at=0;
  for(let y=0;y<height;y++){const filter=packed[at++];assert.ok(filter<=4);
    for(let x=0;x<width;x++){const i=y*width+x,a=x?data[i-1]:0,b=y?data[i-width]:0,c=x&&y?data[i-width-1]:0;
      const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);
      const predicted=filter===0?0:filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):pa<=pb&&pa<=pc?a:pb<=pc?b:c;
      data[i]=(packed[at++]+predicted)&255;
    }
  }
  assert.equal(at,packed.length);return {data,width,height};
}
const {SpatialMasks,partialSlots}=compile('spatial-masks');
const masks=new SpatialMasks();assert.equal(partialSlots.length,4);
const actual=[];
for(const folder of ['partial-entrance','partial-entrance-6c7']){
  const path=root+'public/models/hires/'+folder+'/manifest.json';if(!fs.existsSync(path))continue;
  const patch=JSON.parse(fs.readFileSync(path,'utf8')).patches[0],m=patch.mask;
  const pixels=readMask(root+'public/models/hires/'+m.url);
  assert.equal(pixels.width,m.width);assert.equal(pixels.height,m.height);
  const texture=new THREE.DataTexture(pixels.data,pixels.width,pixels.height,THREE.RedFormat);
  masks.set(partialSlots[actual.length],texture,[m.minX,m.minZ,m.maxX,m.maxZ]);actual.push({patch,pixels});
}
assert.ok(actual.length);
const combinedStats=masks.partialCoverageStats();
function expectedAt(x,z){return actual.some(({patch,pixels})=>{const m=patch.mask;
  const c=Math.floor((x-m.minX)/m.pixelSizeMeters),r=Math.floor((z-m.minZ)/m.pixelSizeMeters);
  return c>=0&&r>=0&&c<pixels.width&&r<pixels.height&&pixels.data[r*pixels.width+c]>127;});}
let comparisons=0;const union=masks.slots.partialCoverage,im=union.texture.value.image,bounds=union.bounds.value;
for(let r=0;r<im.height;r++)for(let c=0;c<im.width;c++){
  const x=bounds.x+(c+.5)*combinedStats.metersPerPixel,z=bounds.y+(r+.5)*combinedStats.metersPerPixel;
  assert.equal(im.data[r*im.width+c]>127,expectedAt(x,z));comparisons++;
}
assert.equal(combinedStats.bytes,im.data.byteLength);
const before=Buffer.from(im.data),beforeBounds=bounds.toArray();
masks.enable('meshPartial',false);masks.enable('meshPartial',true);
assert.deepEqual(Buffer.from(masks.slots.partialCoverage.texture.value.image.data),before);
assert.deepEqual(masks.slots.partialCoverage.bounds.value.toArray(),beforeBounds);
// A far-away entry must be rejected, preserving the committed union exactly.
assert.throws(()=>masks.set('meshPartial4',new THREE.DataTexture(new Uint8Array([255]),1,1,THREE.RedFormat),[9000,0,9000.5,.5]),/memory limit/);
assert.equal(masks.slots.meshPartial4.enabled.value,0);
assert.deepEqual(Buffer.from(masks.slots.partialCoverage.texture.value.image.data),before);
// A nonaligned source grid must not be rounded into an invented mask position.
assert.throws(()=>masks.set('meshPartial4',new THREE.DataTexture(new Uint8Array([255]),1,1,THREE.RedFormat),[200.1,-1600,200.6,-1599.5]),/exact pixel grid/);
assert.deepEqual(Buffer.from(masks.slots.partialCoverage.texture.value.image.data),before);
const shaderCounts={};
for(const role of ['baseline','photogrammetry','terrain','exterior','supplement']){
  const material=new THREE.MeshBasicMaterial(),mesh=new THREE.Mesh(new THREE.BufferGeometry(),material);
  masks.apply(mesh,role);const shader={uniforms:{},vertexShader:'#include <begin_vertex>',fragmentShader:'#include <clipping_planes_fragment>'};
  material.onBeforeCompile(shader,{});
  shaderCounts[role]=(shader.fragmentShader.match(/uniform sampler2D/g)||[]).length;
  assert.equal(shader.fragmentShader.includes('uniform sampler2D u_partialCoverage'),role==='baseline'||role==='supplement');
  if(role==='baseline'||role==='photogrammetry')assert.ok(shader.fragmentShader.includes('!campusPreserveSourceGround'));
  assert.equal(shader.fragmentShader.includes('mix(groundMask.r,groundMask.g,k_replacement)'),role==='photogrammetry');
  if(role==='supplement'){
    assert.ok(!shader.fragmentShader.includes('uniform sampler2D u_replacement'));
    assert.ok(!shader.fragmentShader.includes('campusPreserveSourceGround'));
    assert.ok(shader.fragmentShader.includes('u_opening')&&shader.fragmentShader.includes('u_surface2'));
  }
  material.dispose();mesh.geometry.dispose();
}
assert.ok(shaderCounts.baseline+2<=16); // Baseline source map plus sea blend.
masks.setPhotogrammetryCore('replacement',true);assert.equal(masks.slots.replacement.coreOnly.value,1);
masks.set('replacement',new THREE.DataTexture(new Uint8Array([255]),1,1,THREE.RedFormat),[0,0,1,1]);
assert.equal(masks.slots.replacement.coreOnly.value,0);
for(const name of partialSlots)masks.enable(name,false);
assert.equal(masks.slots.partialCoverage.enabled.value,0);assert.equal(masks.partialCoverageStats().bytes,1);
masks.dispose();
const report={status:'pass',actualSourceMasks:actual.map(a=>a.patch.id),pixelComparisons:comparisons,mismatches:0,
  combinedStats,shaderMaskSamplers:shaderCounts,baselineWithSourceAndSeaSamplers:shaderCounts.baseline+2,
  exactRestoreAfterDisable:true,oversizedAndMisalignedInputRejectedAtomically:true,emptyUnionReleased:true,
  coreChannelOnlyForNewPhotography:true,supplementHasNoBuildingReplacement:true,ordinarySetResetsCoreChannel:true,
  limitations:'CPU mask bytes and generated GLSL checked; final GPU compilation and visual acceptance are separate.'};
fs.writeFileSync(root+'public/models/hires/partial-entrance/mask-union-qa.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
