import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {CameraGroundConstraint,createGridGroundSampler,createAllowedFloorSampler,createRegularTerrainPatchSampler} from '../app/camera-ground-constraint.ts';
const project=fileURLToPath(new URL('../',import.meta.url));
const close=(a,b,epsilon=1e-4)=>assert.ok(Math.abs(a-b)<=epsilon,`${a} != ${b}`);
const camera=(x,y,z)=>({position:{x,y,z},lookAt(){},updateMatrixWorld(){}});
function parseGlb(path){const raw=fs.readFileSync(path),len=raw.readUInt32LE(12),doc=JSON.parse(raw.subarray(20,20+len).toString()),offset=28+len;return{doc,bin:raw.subarray(offset)}}
function array(g,b,i){const a=g.accessors[i],v=g.bufferViews[a.bufferView],n={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type],start=(v.byteOffset||0)+(a.byteOffset||0),size={5126:4,5125:4,5123:2}[a.componentType],stride=v.byteStride||n*size;return{count:a.count,n,get(row,col){const at=start+row*stride+col*size;return a.componentType===5126?b.readFloatLE(at):a.componentType===5125?b.readUInt32LE(at):b.readUInt16LE(at)}}}
const grid=JSON.parse(fs.readFileSync(project+'/public/terrain/height-grid-5m.json','utf8')),sample=createGridGroundSampler(grid);
// Independent comparison against actual exported triangle vertices, not another
// copy of the grid formula. Covers source origin, row direction, and diagonal.
const base=parseGlb(project+'/public/terrain/terrain.glb'),prim=base.doc.meshes[0].primitives[0],positions=array(base.doc,base.bin,prim.attributes.POSITION),indices=array(base.doc,base.bin,prim.indices);
let maxMeshError=0,comparisons=0;
for(let k=0;k<indices.count/3;k+=211){const xyz=[0,0,0],weights=[.19,.37,.44];for(let j=0;j<3;j++){const vi=indices.get(k*3+j,0);for(let c=0;c<3;c++)xyz[c]+=positions.get(vi,c)*weights[j]};const height=sample(xyz[0],xyz[2]);assert.notEqual(height,null);maxMeshError=Math.max(maxMeshError,Math.abs(height-xyz[1]));comparisons++}
assert.ok(maxMeshError<.001);
const noData=createGridGroundSampler({rows:2,columns:2,first_easting:844800,first_northing:820500,easting_step:5,northing_step:-5,heights:[0,10,null,40]});assert.equal(noData(1,1),null);assert.equal(sample(10000,10000),null);
const zero=createGridGroundSampler({rows:2,columns:2,first_easting:844800,first_northing:820500,easting_step:5,northing_step:-5,heights:[0,0,0,0]});assert.equal(zero(2,2),0);
const detailManifest=JSON.parse(fs.readFileSync(project+'/public/terrain/detail/manifest.json','utf8')),detail=parseGlb(project+'/public/terrain/detail/'+detailManifest.tiles[0].url),dp=detail.doc.meshes[0].primitives[0],pv=array(detail.doc,detail.bin,dp.attributes.POSITION),iv=array(detail.doc,detail.bin,dp.indices),detailSample=createRegularTerrainPatchSampler({count:pv.count,getX:i=>pv.get(i,0),getY:i=>pv.get(i,1),getZ:i=>pv.get(i,2)},1);
let maxDetailError=0;for(let k=0;k<iv.count/3;k+=101){const p=[0,0,0];for(let j=0;j<3;j++)for(let c=0;c<3;c++)p[c]+=pv.get(iv.get(k*3+j,0),c)/3;maxDetailError=Math.max(maxDetailError,Math.abs(detailSample(p[0],p[2])-p[1]))}assert.ok(maxDetailError<.001);

// Downward pan moves camera and target together to preserve the orbit; endpoint
// near-surface checks remain true through repeated damping-sized requests.
const guard=new CameraGroundConstraint({cameraProbeRadius:0});let cam=camera(20,80,0),target={x:0,y:50,z:0};let r=guard.constrain(cam,target,{sampleGround:x=>100+x*.5});close(target.y,100.1);close(cam.position.y,130.1);assert.ok(r.cameraClearance>=1.8);
guard.reset();cam=camera(0,125,0);target={x:0,y:123.1,z:0};guard.constrain(cam,target,{sampleGround:()=>123});let dampingMaxError=0;for(let i=0;i<300;i++){cam.position.y-=.08;target.y-=.08;r=guard.constrain(cam,target,{sampleGround:()=>123});dampingMaxError=Math.max(dampingMaxError,Math.abs(cam.position.y-125));assert.ok(r.cameraClearance>=1.8-1e-6)}assert.ok(dampingMaxError<1e-6);

// Both endpoints are above low ground, yet a fast pan crosses a high ridge.
const sweep=new CameraGroundConstraint({cameraProbeRadius:0,sweepStepMeters:.5});cam=camera(0,12,0);target={x:0,y:2,z:0};const ridge={sampleGround:x=>x>=4&&x<=6?50:0};sweep.constrain(cam,target,ridge);cam.position.x=10;target.x=10;r=sweep.constrain(cam,target,ridge);assert.equal(r.sweepBlocked,true);assert.ok(cam.position.x<4);assert.ok(r.acceptedMovementFraction<.4);assert.ok(r.sweepSamples<=128+8);

// Indoor permission requires BOTH verified building and current-floor polygons.
// The room floor is below outdoor terrain; holes and outside points stay guarded.
const square=(x0,z0,x1,z1)=>[[x0,z0],[x1,z0],[x1,z1],[x0,z1],[x0,z0]];
const footprint=[{rings:[square(0,0,20,20),square(8,8,12,12)]}];
const floor=createAllowedFloorSampler(footprint,[{rings:[square(0,0,20,20)],heightSourceZ:97},{rings:[square(15,0,20,20)],heightSourceZ:117}]);
assert.equal(floor(5,5,100),97);assert.equal(floor(17,5,100),97);assert.equal(floor(17,5,119),117);assert.equal(floor(10,10,100),null);assert.equal(floor(21,5,100),null);
for(const [x,z,expected,source]of[[5,5,98.8,'indoor'],[10,10,141.8,'terrain'],[21,5,141.8,'terrain']]){const g=new CameraGroundConstraint({cameraProbeRadius:0});cam=camera(x,96,z);target={x,y:97,z};r=g.constrain(cam,target,{sampleGround:()=>140,allowedFloorAt:floor,contextKey:'academic/LG5'});close(cam.position.y,expected);assert.equal(r.cameraSource,source)}

// NoData is never silently interpolated or declared sea. Hold the last trusted
// outdoor lower bound; explicit known water can independently permit lower views.
const unknown=new CameraGroundConstraint({cameraProbeRadius:0});cam=camera(0,100,0);target={x:0,y:98.1,z:0};unknown.constrain(cam,target,{sampleGround:()=>98});cam.position.x=1;cam.position.y=20;target.x=1;r=unknown.constrain(cam,target,{sampleGround:()=>null});assert.equal(r.cameraSource,'unknown-held');assert.ok(cam.position.y>=99.8-1e-6);
unknown.reset();cam=camera(0,-5,0);target={x:0,y:0,z:0};r=unknown.constrain(cam,target,{sampleGround:()=>null,isKnownWater:()=>true});close(cam.position.y,1.8);assert.equal(r.cameraSource,'water');
const higherDetail=new CameraGroundConstraint({cameraProbeRadius:0});cam=camera(0,154,0);target={x:0,y:155,z:0};r=higherDetail.constrain(cam,target,{sampleGround:()=>130,sampleDetail:()=>155});assert.equal(r.cameraSource,'detail');assert.ok(cam.position.y>=156.8-1e-6);
console.log(JSON.stringify({status:'pass',actual5mTriangleComparisons:comparisons,max5mInterpolationErrorMeters:maxMeshError,max1mInterpolationErrorMeters:maxDetailError,regular1mSamplerStorageBytes:detailSample.storageBytes,dampingFrames:300,dampingMaxHeightDriftMeters:dampingMaxError,verified:['grid origin and triangle diagonal','NoData and zero-valued source cells','downward pan preserves orbit','300 damping corrections without drift','ridge swept collision','LG below DTM only within verified floor polygons','holes and outside footprint remain protected','multiple source Z preserved','held NoData boundary','explicit water','loaded1m override']},null,2));
