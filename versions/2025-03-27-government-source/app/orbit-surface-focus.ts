import * as THREE from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { PanAnchor } from './anchored-pan';

export type OrbitSurfaceFocusContext = {
  /** Same active-floor/detail/DTM policy as the ground guard, including its
   * target clearance. Null means safety is unknown at this prospective pivot.
   * This samples a legal camera-control target, not a new source elevation. */
  minimumTargetY: (x: number, z: number, referenceY: number) => number | null;
  /** Render-policy tolerance for moving a surface pivot towards the eye to
   * satisfy target clearance. Never move through the first visible surface. */
  maxSurfaceOffsetMeters?: number;
};
export type OrbitSurfaceFocusMetrics = {
  active: boolean;
  gestureId: string;
  status: 'idle' | 'focused' | 'retained';
  reason: string;
  source: string;
  pickedPoint: number[] | null;
  target: number[];
  oldDistance: number;
  newDistance: number;
  surfaceOffsetMeters: number;
  pickMs: number;
  pickCount: number;
  cameraMovement: number;
  orientationChangeRadians: number;
};

/** A surface-centred orbit pivot, with no first-person mode. The caller owns
 * gesture lifetime: pointer rotation/pinch until release, or one wheel burst.
 * OrbitControls emits start/end for EACH wheel event, so those events alone
 * must not begin a new focus on every trackpad sample. PAN keeps its own anchor.
 */
export class OrbitSurfaceFocus {
  private gesture: string | null = null;
  private picks = 0;
  private metrics: OrbitSurfaceFocusMetrics = {
    active: false, gestureId: '', status: 'idle', reason: '', source: '',
    pickedPoint: null, target: [], oldDistance: 0, newDistance: 0,
    surfaceOffsetMeters: 0, pickMs: 0, pickCount: 0,
    cameraMovement: 0, orientationChangeRadians: 0,
  };

  begin(
    gestureId: string,
    camera: THREE.PerspectiveCamera,
    controls: OrbitControls,
    pick: (ray: THREE.Raycaster) => PanAnchor | null,
    context: OrbitSurfaceFocusContext,
  ): OrbitSurfaceFocusMetrics {
    if(this.gesture===gestureId)return this.stats();
    this.gesture=gestureId;
    const position=camera.position.clone(),orientation=camera.quaternion.clone(),oldTarget=controls.target.clone();
    const damping=controls.enableDamping;
    // Consume old spherical/pan/dolly deltas without exposing their camera
    // movement. The first update after the new target must use a clean gesture.
    try { controls.enableDamping=false;controls.update(); }
    finally {
      camera.position.copy(position);camera.quaternion.copy(orientation);
      controls.target.copy(oldTarget);controls.enableDamping=damping;
      camera.updateMatrixWorld(true);
    }
    const origin=camera.getWorldPosition(new THREE.Vector3());
    const direction=camera.getWorldDirection(new THREE.Vector3());
    const oldDistance=origin.distanceTo(oldTarget);
    let source='',pickedPoint:number[]|null=null,pickMs=0,surfaceOffsetMeters=0;
    const finish=(status:'focused'|'retained',reason:string)=>{
      this.metrics={active:true,gestureId,status,reason,source,pickedPoint,
        target:controls.target.toArray(),oldDistance,newDistance:origin.distanceTo(controls.target),
        surfaceOffsetMeters,pickMs,pickCount:this.picks,
        cameraMovement:camera.position.distanceTo(position),
        orientationChangeRadians:camera.quaternion.angleTo(orientation)};
      return this.stats();
    };
    // Camera forward is the principal ray even for an asymmetric projection.
    // NDC (0,0) would change direction when the sidebar offsets the principal point.
    const ray=new THREE.Raycaster(origin,direction,camera.near,camera.far);
    const start=performance.now();this.picks++;
    let hit:PanAnchor|null;
    try { hit=pick(ray); }
    catch { pickMs=performance.now()-start;return finish('retained','surface-pick-failed'); }
    pickMs=performance.now()-start;
    if(!hit)return finish('retained','no-visible-surface');
    source=hit.source;pickedPoint=hit.point.toArray();
    if(!pickedPoint.every(Number.isFinite))return finish('retained','nonfinite-surface');
    const offset=hit.point.clone().sub(origin),distance=offset.dot(direction);
    if(distance<=0)return finish('retained','surface-behind-camera');
    if(distance<camera.near||distance>camera.far)return finish('retained','surface-outside-camera-depth');
    if(offset.addScaledVector(direction,-distance).length()>Math.max(1e-5,distance*1e-7))
      return finish('retained','surface-off-principal-ray');
    const minimum=Math.max(camera.near,controls.minDistance),maximum=Math.min(camera.far,controls.maxDistance);
    // Reject the nearest too-close wall; do not skip it and choose an occluded
    // wall farther away. Clamping the orbit radius would move the camera now.
    if(distance<minimum||distance>maximum)return finish('retained','surface-outside-orbit-distance');
    const limit=context.maxSurfaceOffsetMeters??2;
    if(!Number.isFinite(limit)||limit<0)return finish('retained','invalid-surface-offset-limit');
    let adjusted=distance;
    const target=new THREE.Vector3();
    for(let attempt=0;attempt<8;attempt++){
      ray.ray.at(adjusted,target);
      const height=context.minimumTargetY(target.x,target.z,target.y);
      if(height===null||!Number.isFinite(height))return finish('retained','unknown-target-clearance');
      const deficit=height-target.y;
      if(deficit<=1e-6){
        const targetRadius=target.distanceTo(controls.cursor);
        if(targetRadius<controls.minTargetRadius||targetRadius>controls.maxTargetRadius)
          return finish('retained','surface-outside-target-limits');
        controls.target.copy(target);
        return finish('focused',surfaceOffsetMeters?'surface-with-target-clearance':'visible-surface');
      }
      if(direction.y>=-1e-7)return finish('retained','clearance-needs-occluded-or-horizontal-target');
      adjusted-=deficit/-direction.y+1e-7;
      surfaceOffsetMeters=distance-adjusted;
      if(adjusted<minimum||surfaceOffsetMeters>limit)
        return finish('retained','clearance-would-change-close-view');
    }
    return finish('retained','target-clearance-did-not-converge');
  }

  end(gestureId?: string) {
    if(gestureId!==undefined&&gestureId!==this.gesture)return;
    this.gesture=null;this.metrics.active=false;
  }
  stats(): OrbitSurfaceFocusMetrics {
    return {...this.metrics,target:[...this.metrics.target],pickedPoint:this.metrics.pickedPoint?[...this.metrics.pickedPoint]:null};
  }
}
