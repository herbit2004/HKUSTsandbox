// Installed OrbitControls, current helper/ground guard and real Three raycasts.
// Geometry below is explicit controlled test geometry, not campus/source QA.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const root=fileURLToPath(new URL('../',import.meta.url)),loaded=new Map();
function load(name){
 if(loaded.has(name))return loaded.get(name);
 const exports={};loaded.set(name,exports);
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(root+'app/'+name+'.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
  exports,performance,console,Map,Set,Float64Array,
  require(id){if(id==='three')return THREE;if(id.startsWith('./'))return load(id.slice(2));throw new Error('Unexpected dependency '+id);},
 });return exports;
}
const {OrbitSurfaceFocus}=load('orbit-surface-focus'),{pickVisiblePanAnchor}=load('anchored-pan');
const {CameraGroundConstraint,createAllowedFloorSampler}=load('camera-ground-constraint');
const results=[];
function check(name,run){results.push({name,status:'pass',detail:run()});}
function fixture(radius=8){
 const camera=new THREE.PerspectiveCamera(42,1600/900,.5,9000),target=new THREE.Vector3(500,151,-1400);
 camera.setViewOffset(1600,900,-161,-31,1600,900);
 camera.position.copy(target).add(new THREE.Vector3(0,radius/Math.sqrt(2),radius/Math.sqrt(2)));
 // No DOM listeners are installed for this numeric/component test.
 const controls=new OrbitControls(camera,null);controls.target.copy(target);
 controls.minDistance=8;controls.maxDistance=5100;controls.maxPolarAngle=Math.PI*.487;
 controls.enableDamping=true;controls.dampingFactor=.14;controls.update();camera.updateMatrixWorld(true);
 return {camera,controls,focus:new OrbitSurfaceFocus()};
}
function floor(y){
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(2000,2000),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));
 mesh.rotation.x=-Math.PI/2;mesh.position.set(500,y,-1400);mesh.name='controlled-floor-'+y;return mesh;
}
function wall(camera,distance){
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(500,500),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));
 mesh.position.copy(camera.position).addScaledVector(camera.getWorldDirection(new THREE.Vector3()),distance);
 mesh.quaternion.copy(camera.quaternion);mesh.name='controlled-wall-'+distance;return mesh;
}
const pick=objects=>ray=>pickVisiblePanAnchor(ray,objects);
function pose(camera){return {position:camera.position.toArray(),quaternion:camera.quaternion.toArray(),fov:camera.fov,zoom:camera.zoom,aspect:camera.aspect,projection:camera.projectionMatrix.toArray(),view:JSON.stringify(camera.view)};}
const release=meshes=>meshes.forEach(mesh=>{mesh.geometry.dispose();mesh.material.dispose();});

check('stale eight-metre pivot refocuses a distant visible wall without moving camera or changing projection',()=>{
 const {camera,controls,focus}=fixture(),mesh=wall(camera,120),before=pose(camera);
 const result=focus.begin('rotate-1',camera,controls,pick([mesh]),{minimumTargetY:()=>-1000});
 assert.equal(result.status,'focused');assert.ok(Math.abs(result.newDistance-120)<1e-8);assert.deepEqual(pose(camera),before);
 const target=controls.target.clone();controls.update();
 assert.ok(camera.position.distanceTo(new THREE.Vector3(...before.position))<1e-10);
 assert.ok(camera.quaternion.angleTo(new THREE.Quaternion(...before.quaternion))<1e-7);
 assert.ok(controls.target.distanceTo(target)<1e-10);release([mesh]);return result;
});
check('off-axis centre uses camera forward, while naive canvas NDC zero would turn the view',()=>{
 const {camera,controls,focus}=fixture(),mesh=floor(122),before=pose(camera),ray=new THREE.Raycaster();
 const principal=controls.target.clone().project(camera);assert.ok(Math.abs(principal.x)>.1);
 ray.setFromCamera(new THREE.Vector2(),camera);const wrong=pick([mesh])(ray).point;
 const wrongDirection=wrong.clone().sub(camera.position).normalize(),turn=camera.getWorldDirection(new THREE.Vector3()).angleTo(wrongDirection);
 assert.ok(THREE.MathUtils.radToDeg(turn)>5);
 const result=focus.begin('wheel-1',camera,controls,pick([mesh]),{minimumTargetY:()=>122.1});
 assert.equal(result.status,'focused');assert.deepEqual(pose(camera),before);
 const projected=controls.target.clone().project(camera);assert.ok(Math.abs(projected.x-principal.x)<1e-9);assert.ok(Math.abs(projected.y-principal.y)<1e-9);
 release([mesh]);return {principalNDC:principal.toArray(),naiveTurnDegrees:THREE.MathUtils.radToDeg(turn),result};
});
check('ground target clearance is solved along the view ray and the real ground guard does not lift the camera',()=>{
 const {camera,controls,focus}=fixture(),mesh=floor(122),before=pose(camera),guard=new CameraGroundConstraint();
 const result=focus.begin('ground',camera,controls,pick([mesh]),{minimumTargetY:()=>122.1});
 assert.equal(result.status,'focused');assert.ok(result.surfaceOffsetMeters>0&&result.surfaceOffsetMeters<.2);
 const metrics=guard.constrain(camera,controls.target,{sampleGround:()=>122});
 assert.equal(metrics.cameraCorrectionY,0);assert.equal(metrics.targetCorrectionY,0);assert.equal(metrics.corrected,false);
 assert.ok(camera.position.distanceTo(new THREE.Vector3(...before.position))<1e-10);release([mesh]);return {result,metrics};
});
check('verified active lower-floor allowance permits LG focus rather than forcing the outdoor DTM height',()=>{
 const {camera,controls,focus}=fixture(),mesh=floor(100),rings=[[[400,-1550],[600,-1550],[600,-1250],[400,-1250],[400,-1550]]];
 const allowed=createAllowedFloorSampler([{rings}],[{rings,heightSourceZ:100}]);
 const minimum=(x,z,y)=>(allowed(x,z,y)??122)+.1;
 const before=pose(camera),result=focus.begin('indoor-LG',camera,controls,pick([mesh]),{minimumTargetY:minimum});
 assert.equal(result.status,'focused');assert.ok(controls.target.y<101);assert.deepEqual(pose(camera),before);
 const metrics=new CameraGroundConstraint().constrain(camera,controls.target,{sampleGround:()=>122,allowedFloorAt:allowed,contextKey:'verified-building/LG'});
 assert.equal(metrics.targetSource,'indoor');assert.equal(metrics.corrected,false);release([mesh]);return {result,metrics};
});
check('nearest too-close wall is rejected without moving five metres or selecting the occluded farther wall',()=>{
 const {camera,controls,focus}=fixture(),meshes=[wall(camera,3),wall(camera,120)],before=pose(camera),target=controls.target.clone();
 const result=focus.begin('near-wall',camera,controls,pick(meshes),{minimumTargetY:()=>-1000});
 assert.equal(result.status,'retained');assert.equal(result.reason,'surface-outside-orbit-distance');assert.equal(result.source,'controlled-wall-3');
 assert.deepEqual(pose(camera),before);assert.ok(controls.target.equals(target));controls.update();assert.ok(camera.position.distanceTo(new THREE.Vector3(...before.position))<1e-10);
 release(meshes);return result;
});
check('sky, behind, off-ray, unknown safety and excessive ground correction preserve the previous target',()=>{
 const cases=[
  {name:'sky',picker:()=>null,minimum:()=>0,reason:'no-visible-surface'},
  {name:'behind',distance:-10,minimum:()=>0,reason:'surface-behind-camera'},
  {name:'beyond-orbit',distance:5200,minimum:()=>-10000,reason:'surface-outside-orbit-distance'},
  {name:'unknown-height',distance:100,minimum:()=>null,reason:'unknown-target-clearance'},
  {name:'invalid-height',distance:100,minimum:()=>NaN,reason:'unknown-target-clearance'},
  {name:'too-large-adjustment',distance:100,minimum:()=>200,reason:'clearance-would-change-close-view'},
  {name:'off-ray',distance:100,lateral:10,minimum:()=>0,reason:'surface-off-principal-ray'},
 ];
 const outcomes=[];for(const row of cases){const {camera,controls,focus}=fixture(),before=pose(camera),target=controls.target.clone();
  const picker=row.picker??(ray=>({point:ray.ray.at(row.distance,new THREE.Vector3()).add(new THREE.Vector3(row.lateral??0,0,0)),source:row.name}));
  const result=focus.begin(row.name,camera,controls,picker,{minimumTargetY:row.minimum});
  assert.equal(result.status,'retained');assert.equal(result.reason,row.reason);assert.deepEqual(pose(camera),before);assert.ok(controls.target.equals(target));outcomes.push(result);
 }return outcomes;
});
check('existing Orbit damping and dolly increments are drained with no change at begin or the next update',()=>{
 const {camera,controls,focus}=fixture(),mesh=wall(camera,120),before=pose(camera);
 controls._sphericalDelta.theta=.08;controls._panOffset.set(1,0,0);controls._scale=.9;
 const result=focus.begin('new-rotation',camera,controls,pick([mesh]),{minimumTargetY:()=>-1000});
 assert.equal(result.status,'focused');assert.deepEqual(pose(camera),before);assert.equal(controls.enableDamping,true);
 const next=pose(camera);controls.update();assert.ok(camera.position.distanceTo(new THREE.Vector3(...next.position))<1e-9);assert.ok(camera.quaternion.angleTo(new THREE.Quaternion(...next.quaternion))<1e-7);
 release([mesh]);return result;
});
check('one gesture fixes its source anchor through motion and source swaps; end allows the next pick',()=>{
 const {camera,controls,focus}=fixture(),first=wall(camera,120),second=wall(camera,160);let calls=0;
 const picker=ray=>{calls++;return pick([calls===1?first:second])(ray);};
 focus.begin('wheel-burst',camera,controls,picker,{minimumTargetY:()=>-1000});const target=controls.target.clone();
 for(let i=0;i<12;i++){
  camera.position.lerp(target,.01);controls.update();const beforeRepeat=controls.target.clone();
  focus.begin('wheel-burst',camera,controls,picker,{minimumTargetY:()=>-1000});
  assert.ok(controls.target.equals(beforeRepeat),'repeated begin does not mutate target');
  assert.ok(controls.target.distanceTo(target)<1e-9,'OrbitControls normalization retains the same world anchor');
 }
 assert.equal(calls,1);focus.end('unrelated-pointer');assert.equal(focus.stats().active,true);focus.end('wheel-burst');
 focus.begin('next-wheel-burst',camera,controls,picker,{minimumTargetY:()=>-1000});assert.equal(calls,2);assert.ok(!controls.target.equals(target));release([first,second]);return {calls,heldSamples:12,stats:focus.stats()};
});
check('same visible-surface picker excludes hidden parents and caller-rejected masked surfaces',()=>{
 const {camera,controls,focus}=fixture(),hidden=wall(camera,20),masked=wall(camera,40),visible=wall(camera,120);hidden.visible=false;
 const result=focus.begin('masked-source',camera,controls,ray=>pickVisiblePanAnchor(ray,[hidden,masked,visible],hit=>hit.object!==masked),{minimumTargetY:()=>-1000});
 assert.equal(result.status,'focused');assert.equal(result.source,'controlled-wall-120');release([hidden,masked,visible]);return result;
});

const files=['app/orbit-surface-focus.ts','app/anchored-pan.ts','app/camera-ground-constraint.ts','node_modules/three/examples/jsm/controls/OrbitControls.js'];
const report={status:'pass',checkedAt:new Date().toISOString(),checks:results.length,results,sourceSHA256:Object.fromEntries(files.map(path=>[path,createHash('sha256').update(fs.readFileSync(root+path)).digest('hex')])),integration:{begin:'focus.begin(gestureId,camera,controls,pickVisiblePanAnchorDelegate,{minimumTargetY})',end:'focus.end(gestureId?)',wheel:'One gesture ID per wheel burst; OrbitControls start/end fires for each wheel sample.',pan:'Keep the existing fixed PAN anchor. End/clear focus when switching to PAN or a programmatic entity/floor flight.',safety:'minimumTargetY must use the active-floor/detail/DTM policy plus target clearance. Unknown safety returns null.'},limitations:['Actual installed Three math and raycasts on explicitly controlled walls/floors, not campus geometry or browser acceptance.','The helper preserves the eye and orientation, so it cannot move an already-inside-wall camera out of a building; it is not a collision engine.','No scene wiring or production controller event handlers were modified.']};
fs.writeFileSync(root+'docs/source-evidence-v4/orbit-surface-focus-tests.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,checks:report.checks},null,2));
