import * as THREE from 'three';
import type {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {OrbitSurfaceFocus} from './orbit-surface-focus';
import type {PanAnchor} from './anchored-pan';

export type NavigationMode = 'orbit' | 'fly';
export type FlightState = {captured:boolean;supported:boolean;error:boolean;speed:number;fallback:boolean;focused:boolean;dragging:boolean};
export type OrbitSnapshot = {position:THREE.Vector3;target:THREE.Vector3;quaternion:THREE.Quaternion};
const movementKeys = new Set(['KeyW','KeyA','KeyS','KeyD','Space','ShiftLeft','ShiftRight']);
const pitchLimit = Math.PI / 2 - .01;

export function isFlightTextInput(target:EventTarget|null):boolean {
  return !!target && typeof (target as Element).closest === 'function' &&
    !!(target as Element).closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]');
}

/** Movement is time based, capped after a stalled frame, and normalized across
 * all axes. W follows the view; Space/Shift use world up/down. */
export class FlightMotion {
  readonly keys = new Set<string>();
  speed = 30;
  private yaw = 0;
  private pitch = 0;
  private direction = new THREE.Vector3();
  private displacement = new THREE.Vector3();
  sync(camera:THREE.PerspectiveCamera) {
    const euler = new THREE.Euler().setFromQuaternion(camera.quaternion,'YXZ');
    this.pitch=euler.x;this.yaw=euler.y;this.clear();
  }
  clear(){this.keys.clear();}
  look(camera:THREE.PerspectiveCamera,target:THREE.Vector3,dx:number,dy:number){
    if(!Number.isFinite(dx)||!Number.isFinite(dy))return;
    this.yaw-=dx*.002;
    this.pitch=THREE.MathUtils.clamp(this.pitch-dy*.002,-pitchLimit,pitchLimit);
    camera.quaternion.setFromEuler(new THREE.Euler(this.pitch,this.yaw,0,'YXZ'));
    this.syncTarget(camera,target);
  }
  syncTarget(camera:THREE.PerspectiveCamera,target:THREE.Vector3){
    target.copy(camera.position).addScaledVector(camera.getWorldDirection(this.direction),100);
    camera.updateMatrixWorld(true);
  }
  step(camera:THREE.PerspectiveCamera,target:THREE.Vector3,deltaSeconds:number){
    const dt=Number.isFinite(deltaSeconds)?THREE.MathUtils.clamp(deltaSeconds,0,.1):0;
    const forward=Number(this.keys.has('KeyW'))-Number(this.keys.has('KeyS'));
    const right=Number(this.keys.has('KeyD'))-Number(this.keys.has('KeyA'));
    const up=Number(this.keys.has('Space'))-Number(this.keys.has('ShiftLeft')||this.keys.has('ShiftRight'));
    this.displacement.copy(camera.getWorldDirection(this.direction)).multiplyScalar(forward);
    this.displacement.addScaledVector(new THREE.Vector3(Math.cos(this.yaw),0,-Math.sin(this.yaw)),right);
    this.displacement.y+=up;
    if(this.displacement.lengthSq()<1e-12||!dt)return false;
    this.displacement.normalize().multiplyScalar(this.speed*dt);
    camera.position.add(this.displacement);target.add(this.displacement);camera.updateMatrixWorld(true);
    return true;
  }
}

/** Only the eye is constrained in flight. A sampled ground correction translates
 * eye AND forward target equally, so a hill can never rotate the user's view. */
export class FlightGroundGuard {
  private lastKnown = 0;
  reset(){this.lastKnown=0;}
  constrain(camera:THREE.PerspectiveCamera,target:THREE.Vector3,previous:THREE.Vector3,sample:(x:number,z:number,y:number)=>number|null){
    const distance=Math.hypot(camera.position.x-previous.x,camera.position.z-previous.z);
    const steps=Math.min(32,Math.max(1,Math.ceil(distance/.5)));
    let lift=0;
    for(let i=1;i<=steps;i++){
      const p=previous.clone().lerp(camera.position,i/steps);
      for(const [dx,dz] of [[0,0],[.35,0],[-.35,0],[0,.35],[0,-.35]]){
        const measured=sample(p.x+dx,p.z+dz,p.y);
        if(measured!==null&&Number.isFinite(measured))this.lastKnown=measured;
        lift=Math.max(lift,(measured!==null&&Number.isFinite(measured)?measured:this.lastKnown)+1.8-p.y);
      }
    }
    if(lift>0){camera.position.y+=lift;target.y+=lift;camera.updateMatrixWorld(true);}
    return lift;
  }
}

/** Consume OrbitControls inertia without exposing a changed position or heading. */
export function snapshotOrbit(camera:THREE.PerspectiveCamera,controls:OrbitControls):OrbitSnapshot {
  const snapshot={position:camera.position.clone(),target:controls.target.clone(),quaternion:camera.quaternion.clone()};
  const damping=controls.enableDamping;
  controls.enableDamping=false;controls.update();controls.enableDamping=damping;
  camera.position.copy(snapshot.position);controls.target.copy(snapshot.target);camera.quaternion.copy(snapshot.quaternion);camera.updateMatrixWorld(true);
  return snapshot;
}

/** Reuse the rendered principal-ray surface when the normal orbit limits allow
 * it. Looking up, missing the campus, or standing too close restores the saved
 * orbit view; the UI reports this fallback explicitly. */
export function returnToOrbit(camera:THREE.PerspectiveCamera,controls:OrbitControls,saved:OrbitSnapshot,pick:(ray:THREE.Raycaster)=>PanAnchor|null,minimumTargetY:(x:number,z:number,y:number)=>number|null):'surface'|'saved' {
  snapshotOrbit(camera,controls);
  const polar=Math.acos(THREE.MathUtils.clamp(-camera.getWorldDirection(new THREE.Vector3()).y,-1,1));
  if(polar>=controls.minPolarAngle&&polar<=controls.maxPolarAngle){
    const focus=new OrbitSurfaceFocus();
    if(focus.begin('return-from-flight',camera,controls,pick,{minimumTargetY}).status==='focused'){
      controls.update();return 'surface';
    }
  }
  camera.position.copy(saved.position);controls.target.copy(saved.target);camera.quaternion.copy(saved.quaternion);
  camera.updateMatrixWorld(true);controls.update();return 'saved';
}

/** Listeners exist only while fly mode is enabled. Keyboard movement additionally
 * requires this canvas's pointer lock, or its focus in the WebView drag fallback.
 * UI focus and browser shortcuts never move the camera. Escape stops input while
 * leaving the chosen mode intact. */
export class FirstPersonFlight {
  readonly motion = new FlightMotion();
  enabled=false;
  suspended=false;
  private error=false;
  private disposed=false;
  private dragging=false;
  private fallbackPoint:[number,number]|null=null;
  private captureGeneration=0;
  private document:Document;
  private window:Window;
  private bindings:Array<[EventTarget,string,EventListener]> = [];
  constructor(private camera:THREE.PerspectiveCamera,private target:THREE.Vector3,private canvas:HTMLCanvasElement,private change:()=>void){
    this.document=canvas.ownerDocument;this.window=this.document.defaultView!;
  }
  get captured(){return this.document.pointerLockElement===this.canvas;}
  get fallback(){return this.error||typeof this.canvas.requestPointerLock!=='function';}
  get focused(){return this.document.activeElement===this.canvas;}
  stats():FlightState{return {captured:this.captured,supported:typeof this.canvas.requestPointerLock==='function',error:this.error,speed:this.motion.speed,fallback:this.fallback,focused:this.focused,dragging:this.dragging};}
  private bind(target:EventTarget,type:string,handler:EventListener){target.addEventListener(type,handler,true);this.bindings.push([target,type,handler]);}
  setEnabled(enabled:boolean){
    if(this.disposed||this.enabled===enabled)return;
    this.enabled=enabled;this.motion.clear();
    if(enabled){
      this.motion.sync(this.camera);
      this.motion.syncTarget(this.camera,this.target);
      this.bind(this.canvas,'click',this.click as EventListener);
      this.bind(this.document,'keydown',this.keydown as EventListener);
      this.bind(this.document,'keyup',this.keyup as EventListener);
      this.bind(this.document,'mousemove',this.mousemove as EventListener);
      this.bind(this.document,'pointerlockchange',this.lockchange);
      this.bind(this.document,'pointerlockerror',this.lockerror);
      this.bind(this.window,'blur',this.release);
      this.bind(this.document,'visibilitychange',this.visibility);
      this.bind(this.document,'focusin',this.focusin as EventListener);
    }else{
      this.release();
      for(const [target,type,handler] of this.bindings)target.removeEventListener(type,handler,true);
      this.bindings=[];
    }
    this.change();
  }
  setSuspended(suspended:boolean){this.suspended=suspended;if(suspended)this.release();}
  requestCapture(){
    if(!this.enabled||this.suspended||this.disposed||this.captured)return;
    this.motion.clear();
    this.canvas.focus({preventScroll:true});
    // A denied/unimplemented API becomes usable drag mode for this session.
    // Clicking the map again does not retry a failed pointer lock request.
    if(this.fallback){this.change();return;}
    const generation=++this.captureGeneration;
    try{
      const pending=this.canvas.requestPointerLock();
      if(pending&&typeof pending.then==='function')void pending.then(()=>{
        if(generation!==this.captureGeneration||!this.enabled||this.suspended||this.disposed){if(this.captured)this.document.exitPointerLock();}
      },()=>{if(generation===this.captureGeneration)this.lockerror();});
    }catch{this.lockerror();}
  }
  release=()=>{this.captureGeneration++;this.motion.clear();this.dragging=false;this.fallbackPoint=null;if(this.captured)this.document.exitPointerLock();if(this.focused)this.canvas.blur();if(!this.disposed)this.change();};
  private click=(event:MouseEvent)=>{if(event.button===0){event.preventDefault();event.stopImmediatePropagation();this.requestCapture();}};
  private accepts(event:KeyboardEvent){return this.enabled&&!this.suspended&&(this.captured||this.fallback&&this.focused)&&!isFlightTextInput(event.target)&&!event.isComposing&&!event.metaKey&&!event.ctrlKey&&!event.altKey;}
  private keydown=(event:KeyboardEvent)=>{
    if(event.key==='Escape'&&(this.captured||this.focused)){event.preventDefault();event.stopImmediatePropagation();this.release();return;}
    if(!this.accepts(event)){this.motion.clear();return;}
    if(movementKeys.has(event.code)){event.preventDefault();event.stopImmediatePropagation();this.motion.keys.add(event.code);}
  };
  private keyup=(event:KeyboardEvent)=>{this.motion.keys.delete(event.code);};
  private mousemove=(event:MouseEvent)=>{
    if(!this.enabled||this.suspended)return;
    if(this.captured)this.motion.look(this.camera,this.target,event.movementX,event.movementY);
    else if(this.fallback&&this.focused&&event.target===this.canvas){
      const point:[number,number]=[event.clientX,event.clientY];
      const dx=Number.isFinite(event.movementX)&&Math.abs(event.movementX)<=120?event.movementX:(this.fallbackPoint?point[0]-this.fallbackPoint[0]:0);
      const dy=Number.isFinite(event.movementY)&&Math.abs(event.movementY)<=120?event.movementY:(this.fallbackPoint?point[1]-this.fallbackPoint[1]:0);
      this.fallbackPoint=point;
      if(dx||dy)this.motion.look(this.camera,this.target,dx,dy);
    }else if(this.fallback){
      this.fallbackPoint=null;
    }
  };
  private lockchange=()=>{this.motion.clear();if(this.captured&&(!this.enabled||this.suspended||this.disposed)){this.release();return;}this.change();};
  private lockerror=()=>{if(this.disposed||!this.enabled)return;this.error=true;this.motion.clear();this.change();};
  private visibility=()=>{if(this.document.hidden)this.release();};
  private focusin=(event:FocusEvent)=>{if(event.target!==this.canvas)this.release();};
  step(deltaSeconds:number){return this.enabled&&!this.suspended&&(this.captured||this.fallback&&this.focused)&&this.motion.step(this.camera,this.target,deltaSeconds);}
  dispose(){this.setEnabled(false);this.disposed=true;}
}
