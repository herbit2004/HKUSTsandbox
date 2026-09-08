// Real Three camera/movement/orbit logic with controlled DOM input dispatch.
// This is interaction-module regression coverage, not campus visual acceptance.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const root=fileURLToPath(new URL('../',import.meta.url)),cache=new Map();
function load(name){
  if(cache.has(name))return cache.get(name);
  const exports={};cache.set(name,exports);
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(root+'app/'+name+'.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
    exports,performance,console,Map,Set,Float64Array,
    require(id){if(id==='three')return THREE;if(id.startsWith('./'))return load(id.slice(2));throw Error(id);},
  });return exports;
}
const {FlightMotion,FlightGroundGuard,FirstPersonFlight,snapshotOrbit,returnToOrbit}=load('first-person-flight');
const {pickVisiblePanAnchor}=load('anchored-pan');
const results=[];
async function check(name,run){await run();results.push({name,status:'pass'});}
const near=(a,b,tolerance=1e-7)=>assert.ok(Math.abs(a-b)<=tolerance,`${a} != ${b}`);
function cameraAt(){const camera=new THREE.PerspectiveCamera(42,1,.5,9000);camera.position.set(0,50,100);camera.lookAt(0,50,0);return camera;}
class Surface extends EventTarget {
  listeners=new Map();
  addEventListener(type,fn,options){super.addEventListener(type,fn,options);const set=this.listeners.get(type)||new Set();set.add(fn);this.listeners.set(type,set);}
  removeEventListener(type,fn,options){super.removeEventListener(type,fn,options);this.listeners.get(type)?.delete(fn);}
  count(){return [...this.listeners.values()].reduce((n,s)=>n+s.size,0);}
}
function dispatch(target,type,properties={}){
  const event=new Event(type,{cancelable:true});
  for(const [key,value] of Object.entries(properties))Object.defineProperty(event,key,{value});
  target.dispatchEvent(event);return event;
}
function fixture(lock='supported'){
  const document=new Surface(),window=new Surface(),canvas=new Surface(),camera=cameraAt(),target=new THREE.Vector3(0,50,0);
  document.defaultView=window;document.activeElement=null;document.hidden=false;document.pointerLockElement=null;
  canvas.ownerDocument=document;canvas.closest=()=>null;
  canvas.focus=()=>{document.activeElement=canvas;dispatch(document,'focusin',{target:canvas});};
  canvas.blur=()=>{document.activeElement=null;};
  let requests=0,changes=0;
  if(lock!=='unsupported')canvas.requestPointerLock=()=>{requests++;if(lock==='rejected')return Promise.reject(new Error('Unsupported WebView'));document.pointerLockElement=canvas;dispatch(document,'pointerlockchange');return Promise.resolve();};
  document.exitPointerLock=()=>{document.pointerLockElement=null;dispatch(document,'pointerlockchange');};
  const controller=new FirstPersonFlight(camera,target,canvas,()=>changes++);
  return {document,window,canvas,camera,target,controller,requests:()=>requests,changes:()=>changes};
}
const key=(f,code,extra={})=>dispatch(f.document,'keydown',{code,key:code==='Space'?' ':code,...extra});

await check('entry preserves actual eye and orientation; no implicit mouse capture',()=>{
  const f=fixture(),controls=new OrbitControls(f.camera,null);controls.target.copy(f.target);controls.update();
  const before=snapshotOrbit(f.camera,controls);f.controller.setEnabled(true);
  near(f.camera.position.distanceTo(before.position),0);near(f.camera.quaternion.angleTo(before.quaternion),0);assert.equal(f.requests(),0);
  key(f,'KeyW');f.controller.step(.1);near(f.camera.position.distanceTo(before.position),0);f.controller.dispose();
});
await check('time integration, three-axis normalization, shift descent and yaw-relative movement',()=>{
  function move(fps,keys){const camera=cameraAt(),start=camera.position.clone(),target=new THREE.Vector3(0,50,0),motion=new FlightMotion();motion.sync(camera);keys.forEach(k=>motion.keys.add(k));for(let i=0;i<fps;i++)motion.step(camera,target,1/fps);return {distance:start.distanceTo(camera.position),camera};}
  near(move(30,['KeyW']).distance,30);near(move(120,['KeyW']).distance,30);near(move(60,['KeyW','KeyD','Space']).distance,30);
  near(move(60,['ShiftLeft','ShiftRight']).camera.position.y,20);near(move(60,['Space','ShiftLeft']).distance,0);
  const camera=cameraAt(),target=new THREE.Vector3(),motion=new FlightMotion();motion.sync(camera);motion.look(camera,target,Math.PI/2/.002,0);motion.keys.add('KeyW');motion.step(camera,target,.1);near(camera.position.x,3);near(camera.position.z,100);
  motion.step(camera,target,20);near(camera.position.x,6);motion.step(camera,target,NaN);near(camera.position.x,6);
});
await check('pitch is bounded, cannot flip; translational ground protection retains heading',()=>{
  const camera=cameraAt(),target=new THREE.Vector3(),motion=new FlightMotion();motion.sync(camera);motion.look(camera,target,0,-1e8);
  const direction=camera.getWorldDirection(new THREE.Vector3());assert.ok(direction.y>.99&&direction.y<1);assert.ok(direction.z<0);
  motion.look(camera,target,0,1e8);assert.ok(camera.getWorldDirection(new THREE.Vector3()).y<-.99);
  const before=camera.position.clone(),heading=camera.quaternion.clone(),offset=target.clone().sub(camera.position);camera.position.set(3,1,100);target.copy(camera.position).add(offset);
  const lift=new FlightGroundGuard().constrain(camera,target,before,()=>10);assert.ok(lift>0);assert.ok(camera.position.y>=11.8);near(camera.quaternion.angleTo(heading),0);near(target.clone().sub(camera.position).distanceTo(offset),0);
});
await check('pointer lock input filtering, Escape, blur, suspension and listener cleanup',()=>{
  const f=fixture();f.controller.setEnabled(true);f.controller.requestCapture();assert.equal(f.controller.captured,true);
  const start=f.camera.position.clone();key(f,'KeyW');f.controller.step(.1);near(start.distanceTo(f.camera.position),3);
  for(const forbidden of [{ctrlKey:true},{metaKey:true},{altKey:true},{isComposing:true},{target:{closest:()=>({})}}]){key(f,'KeyW',forbidden);assert.equal(f.controller.motion.keys.size,0);}
  key(f,'Space');dispatch(f.window,'blur');assert.equal(f.controller.motion.keys.size,0);assert.equal(f.controller.captured,false);
  f.controller.requestCapture();key(f,'KeyD');const escape=dispatch(f.document,'keydown',{key:'Escape',code:'Escape'});assert.equal(escape.defaultPrevented,true);assert.equal(f.controller.enabled,true);assert.equal(f.controller.captured,false);assert.equal(f.controller.motion.keys.size,0);
  f.controller.requestCapture();key(f,'KeyW');f.controller.setSuspended(true);assert.equal(f.controller.captured,false);assert.equal(f.controller.motion.keys.size,0);
  f.controller.setEnabled(false);assert.equal(f.canvas.count()+f.document.count()+f.window.count(),0);
  f.controller.setEnabled(true);f.controller.setSuspended(false);f.controller.requestCapture();f.controller.dispose();assert.equal(f.canvas.count()+f.document.count()+f.window.count(),0);assert.equal(f.controller.captured,false);
});
await check('unsupported WebView supports focused keyboard flight and mouse-look without dragging; UI focus stops it',()=>{
  const f=fixture('unsupported');f.controller.setEnabled(true);assert.equal(f.controller.stats().fallback,true);f.controller.requestCapture();
  const start=f.camera.position.clone();key(f,'KeyW');f.controller.step(.1);near(start.distanceTo(f.camera.position),3);
  const before=f.camera.quaternion.clone();dispatch(f.document,'mousemove',{target:f.canvas,clientX:300,clientY:100,movementX:100,movementY:0,buttons:0});assert.ok(before.angleTo(f.camera.quaternion)>.1);
  const stopped=f.camera.quaternion.clone();dispatch(f.document,'mousemove',{target:{},clientX:400,clientY:100,movementX:100,movementY:0,buttons:0});near(stopped.angleTo(f.camera.quaternion),0);
  const input={closest:()=>({})};f.document.activeElement=input;dispatch(f.document,'focusin',{target:input});assert.equal(f.controller.motion.keys.size,0);const eye=f.camera.position.clone();key(f,'KeyW',{target:input});f.controller.step(.1);near(eye.distanceTo(f.camera.position),0);
  f.controller.requestCapture();key(f,'KeyW');dispatch(f.document,'keydown',{key:'Escape',code:'Escape'});assert.equal(f.controller.focused,false);assert.equal(f.controller.motion.keys.size,0);assert.equal(f.controller.enabled,true);f.controller.dispose();
});
await check('rejected Pointer Lock falls back once without repeated failed requests',async()=>{
  const f=fixture('rejected');f.controller.setEnabled(true);f.controller.requestCapture();await Promise.resolve();assert.equal(f.controller.stats().fallback,true);
  f.controller.requestCapture();f.controller.requestCapture();assert.equal(f.requests(),1);key(f,'KeyW');const start=f.camera.position.clone();f.controller.step(.1);near(start.distanceTo(f.camera.position),3);f.controller.dispose();
});
await check('a late pointer lock success after leaving fly mode is released',async()=>{
  const f=fixture();let finish;
  f.canvas.requestPointerLock=()=>new Promise(resolve=>{finish=()=>{f.document.pointerLockElement=f.canvas;resolve();};});
  f.controller.setEnabled(true);f.controller.requestCapture();f.controller.setEnabled(false);finish();await Promise.resolve();
  assert.equal(f.controller.captured,false);assert.equal(f.canvas.count()+f.document.count()+f.window.count(),0);f.controller.dispose();
});
await check('return to orbit uses first rendered surface without moving eye; upward view restores saved orbit',()=>{
  const camera=cameraAt(),controls=new OrbitControls(camera,null);controls.target.set(0,0,0);controls.maxPolarAngle=Math.PI*.487;controls.minDistance=8;controls.maxDistance=5100;controls.update();
  const saved=snapshotOrbit(camera,controls),floor=new THREE.Mesh(new THREE.PlaneGeometry(2000,2000),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));floor.rotation.x=-Math.PI/2;floor.updateMatrixWorld(true);
  camera.position.set(200,50,200);camera.lookAt(200,0,100);const eye=camera.position.clone(),orientation=camera.quaternion.clone();controls.target.copy(eye).addScaledVector(camera.getWorldDirection(new THREE.Vector3()),100);
  assert.equal(returnToOrbit(camera,controls,saved,ray=>pickVisiblePanAnchor(ray,[floor]),()=>.1),'surface');near(camera.position.distanceTo(eye),0);near(camera.quaternion.angleTo(orientation),0);assert.ok(controls.target.y>=.1-1e-6);
  camera.lookAt(camera.position.clone().add(new THREE.Vector3(0,20,-10)));assert.equal(returnToOrbit(camera,controls,saved,ray=>pickVisiblePanAnchor(ray,[floor]),()=>.1),'saved');near(camera.position.distanceTo(saved.position),0);near(controls.target.distanceTo(saved.target),0);
  floor.geometry.dispose();floor.material.dispose();
});
console.log(JSON.stringify({status:'pass',checks:results.length,results},null,2));
