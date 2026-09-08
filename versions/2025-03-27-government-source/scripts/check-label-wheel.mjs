import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

class TestWheelEvent extends Event {
  constructor(type, init = {}) {
    super(type, init);
    for (const field of ['deltaX','deltaY','deltaZ','deltaMode','clientX','clientY','screenX','screenY','buttons'])
      this[field] = init[field] ?? 0;
    for (const field of ['ctrlKey','shiftKey','altKey','metaKey']) this[field] = init[field] ?? false;
  }
}
class Canvas extends EventTarget {
  style = {};
  clientWidth = 1000;
  clientHeight = 800;
  ownerDocument = new EventTarget();
  getRootNode() { return this.ownerDocument; }
  getBoundingClientRect() { return {left:0,top:0,width:1000,height:800}; }
}
const root = new URL('../', import.meta.url);
const code = ts.transpileModule(fs.readFileSync(new URL('app/map-label-wheel.ts',root),'utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;
const exported = {};
vm.runInNewContext(code, {exports:exported,WheelEvent:TestWheelEvent});
const {connectMapLabelWheel} = exported;
function fixture(zoomToCursor=false) {
  const canvas=new Canvas(),labels=new EventTarget(),panel=new EventTarget();
  const camera=new THREE.PerspectiveCamera(42,1.25,.5,9000);
  camera.position.set(640,250,-1062);
  const controls=new OrbitControls(camera,canvas);
  controls.target.set(511,122,-1221);controls.zoomToCursor=zoomToCursor;controls.update();
  let starts=0,clicks=0;
  controls.addEventListener('start',()=>starts++);labels.addEventListener('click',()=>clicks++);
  const disconnect=connectMapLabelWheel(labels,canvas);
  return {canvas,labels,panel,camera,controls,disconnect,counts:()=>({starts,clicks})};
}
const result=[];
for(const zoomToCursor of [false,true])for(const deltaMode of [0,1,2])for(const ctrlKey of [false,true]) {
  const direct=fixture(zoomToCursor),crossing=fixture(zoomToCursor);
  const deltas=[-3,-2,-1,.5,2,1,-1,-.25];
  for(let i=0;i<deltas.length;i++) {
    const input={cancelable:true,bubbles:true,clientX:340+i*35,clientY:240+i*18,
      deltaX:1.25,deltaY:deltas[i],deltaZ:.1,deltaMode,ctrlKey,shiftKey:i%2===0};
    const a=new TestWheelEvent('wheel',input),b=new TestWheelEvent('wheel',input);
    direct.canvas.dispatchEvent(a);(i%3===1?crossing.canvas:crossing.labels).dispatchEvent(b);
    assert.equal(a.defaultPrevented,b.defaultPrevented);
    assert.ok(direct.camera.position.distanceTo(crossing.camera.position)<1e-9);
    assert.ok(direct.controls.target.distanceTo(crossing.controls.target)<1e-9);
  }
  assert.equal(crossing.counts().starts,deltas.length,'each input reaches controls once');
  assert.equal(crossing.counts().clicks,0,'wheel must not select a label');
  crossing.labels.dispatchEvent(new Event('click'));assert.equal(crossing.counts().clicks,1);
  const position=crossing.camera.position.clone(),panelWheel=new TestWheelEvent('wheel',{cancelable:true,deltaY:4});
  crossing.panel.dispatchEvent(panelWheel);assert.equal(panelWheel.defaultPrevented,false);
  assert.deepEqual(crossing.camera.position.toArray(),position.toArray());
  crossing.disconnect();crossing.labels.dispatchEvent(new TestWheelEvent('wheel',{cancelable:true,deltaY:-10}));
  assert.deepEqual(crossing.camera.position.toArray(),position.toArray(),'disposed label bridge stays inactive');
  direct.controls.dispose();crossing.controls.dispose();
  result.push({zoomToCursor,deltaMode,ctrlKey,events:deltas.length,status:'pass'});
}
const report={status:'pass',cases:result,scope:'Installed Three OrbitControls differential check: uninterrupted canvas wheel sequence versus the same sequence crossing map labels. Pixel/line/page units, pinch modifier, cursor coordinates, single dispatch, clicks, panel scrolling and disposal. Real browser hover/scroll verification remains required.'};
fs.writeFileSync(new URL('docs/source-evidence-v4/label-wheel-tests.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,cases:result.length}));
