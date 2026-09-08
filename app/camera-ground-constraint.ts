/** Campus camera ground guard. Dependency-free; compatible with Three Vector3.
 * Call once AFTER flight interpolation and OrbitControls.update(), BEFORE render.
 * This guards camera/target against sampled terrain and explicit current-floor
 * polygons. It is not a building-wall collision engine or a navigation graph.
 */
export type XYZ = { x: number; y: number; z: number };
export type HeightSampler = (x: number, z: number) => number | null;
export type AllowedFloorSampler = (x: number, z: number, referenceY: number) => number | null;
export type Ring = readonly (readonly number[])[];
export type PolygonPart = { rings: readonly Ring[] };
export type FloorRoom = PolygonPart & { heightSourceZ: number };
export type CameraLike = {
  position: XYZ;
  lookAt?: (x: number, y: number, z: number) => unknown;
  updateMatrixWorld?: (force?: boolean) => unknown;
};
export interface HeightGrid {
  rows: number; columns: number;
  first_easting: number; first_northing: number;
  easting_step: number; northing_step: number;
  heights: ArrayLike<number | null>;
  origin?: { easting?: number; northing?: number };
}
export interface GroundContext {
  sampleGround: HeightSampler;
  /** Optional exact sampler built once from already loaded 1m mesh vertices. */
  sampleDetail?: HeightSampler;
  /** MUST be restricted to verified open-building AND current-floor polygons. */
  allowedFloorAt?: AllowedFloorSampler;
  /** NoData alone does not prove water. Supply this only for known water. */
  isKnownWater?: (x: number, z: number) => boolean;
  waterHeight?: number;
  /** Change on opening/closing building or switching the active floor. */
  contextKey?: string;
  sweep?: boolean;
}
export interface GroundOptions {
  cameraClearance?: number;
  targetClearance?: number;
  cameraProbeRadius?: number;
  unknownInitialHeight?: number;
  sweepStepMeters?: number;
  maxSweepSamples?: number;
}
type Source = 'indoor' | 'detail' | 'terrain' | 'water' | 'unknown-held' | 'unknown-initial';
type Surface = { height: number; source: Source };
export interface GroundMetrics {
  corrected: boolean;
  cameraCorrectionY: number;
  targetCorrectionY: number;
  cameraSurfaceY: number;
  targetSurfaceY: number;
  cameraClearance: number;
  cameraSource: Source;
  targetSource: Source;
  sweepBlocked: boolean;
  acceptedMovementFraction: number;
  sweepSamples: number;
  sweepCoarsened: boolean;
  groundQueries: number;
}
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
const copy = (v: XYZ): XYZ => ({ x: v.x, y: v.y, z: v.z });
const assign = (to: XYZ, from: XYZ) => { to.x = from.x; to.y = from.y; to.z = from.z; };
const mix = (a: XYZ, b: XYZ, t: number): XYZ => ({ x: a.x + (b.x-a.x)*t, y: a.y + (b.y-a.y)*t, z: a.z + (b.z-a.z)*t });

/** Exact triangle interpolation used by build_terrain.py: NW/SW/NE, NE/SW/SE.
 * Null corners mean the whole cell was not rendered. Do not interpolate them.
 */
function sampleRect(heights: ArrayLike<number | null>, rows: number, columns: number, c: number, r: number): number | null {
  if (!finite(c) || !finite(r) || c < -1e-8 || r < -1e-8 || c > columns-1+1e-8 || r > rows-1+1e-8) return null;
  const col = Math.max(0, Math.min(columns-2, Math.floor(c)));
  const row = Math.max(0, Math.min(rows-2, Math.floor(r)));
  const u = Math.max(0, Math.min(1, c-col)), v = Math.max(0, Math.min(1, r-row));
  const a = heights[row*columns+col], b = heights[row*columns+col+1];
  const d = heights[(row+1)*columns+col], e = heights[(row+1)*columns+col+1];
  if (!finite(a) || !finite(b) || !finite(d) || !finite(e)) return null;
  return u+v <= 1 ? a+(b-a)*u+(d-a)*v : e+(d-e)*(1-u)+(b-e)*(1-v);
}
export function createGridGroundSampler(grid: HeightGrid): HeightSampler {
  if (grid.rows < 2 || grid.columns < 2 || !grid.easting_step || !grid.northing_step || grid.heights.length !== grid.rows*grid.columns) throw new Error('Invalid campus height grid');
  const e0 = grid.origin?.easting ?? 844800, n0 = grid.origin?.northing ?? 820500;
  return (x,z) => sampleRect(grid.heights, grid.rows, grid.columns,
    (x+e0-grid.first_easting)/grid.easting_step,
    (n0-z-grid.first_northing)/grid.northing_step);
}

/** Build ONCE per loaded regular 1m terrain BufferGeometry, then cache by geometry.
 * Uses the exported local positions, not a raycast through the full scene.
 * Pass the actual 1m position attribute; no transformed buildings or generic mesh.
 */
export function createRegularTerrainPatchSampler(position: { count: number; getX(i:number):number; getY(i:number):number; getZ(i:number):number }, spacing = 1): HeightSampler & { boundsXZ: [number,number,number,number]; storageBytes: number } {
  if (!(spacing > 0) || position.count < 4) throw new Error('Invalid regular terrain patch');
  let minX=Infinity, minZ=Infinity, maxX=-Infinity, maxZ=-Infinity;
  for (let i=0; i<position.count; i++) {
    const x=position.getX(i), z=position.getZ(i);
    if (!finite(x) || !finite(z) || !finite(position.getY(i))) throw new Error('Non-finite terrain vertex');
    minX=Math.min(minX,x); maxX=Math.max(maxX,x); minZ=Math.min(minZ,z); maxZ=Math.max(maxZ,z);
  }
  const columns=Math.round((maxX-minX)/spacing)+1, rows=Math.round((maxZ-minZ)/spacing)+1;
  if (rows<2 || columns<2 || rows*columns>2_000_000) throw new Error('Unexpected terrain patch extent');
  const heights=new Float64Array(rows*columns); heights.fill(NaN);
  for (let i=0; i<position.count; i++) {
    const c=(position.getX(i)-minX)/spacing, r=(position.getZ(i)-minZ)/spacing;
    if (Math.abs(c-Math.round(c))>1e-3 || Math.abs(r-Math.round(r))>1e-3) throw new Error('Terrain is not the declared regular local grid');
    heights[Math.round(r)*columns+Math.round(c)]=position.getY(i);
  }
  const sample=((x:number,z:number) => sampleRect(heights,rows,columns,(x-minX)/spacing,(z-minZ)/spacing)) as HeightSampler & { boundsXZ:[number,number,number,number]; storageBytes:number };
  sample.boundsXZ=[minX,minZ,maxX,maxZ]; sample.storageBytes=heights.byteLength;
  return sample;
}

function onSegment(x:number,z:number,a:readonly number[],b:readonly number[]) {
  const dx=b[0]-a[0], dz=b[1]-a[1], len2=dx*dx+dz*dz;
  if (len2<1e-16) return Math.hypot(x-a[0],z-a[1])<1e-7;
  const t=((x-a[0])*dx+(z-a[1])*dz)/len2;
  return t>=-1e-8 && t<=1+1e-8 && Math.abs((x-a[0])*dz-(z-a[1])*dx) <= 1e-7*Math.sqrt(len2);
}
function inRing(x:number,z:number,ring:Ring) {
  let result=false;
  for (let i=0,j=ring.length-1;i<ring.length;j=i++) {
    const a=ring[j], b=ring[i];
    if (onSegment(x,z,a,b)) return true;
    if ((a[1]>z)!==(b[1]>z) && x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]) result=!result;
  }
  return result;
}
function inPart(x:number,z:number,p:PolygonPart) { return p.rings.length>0 && inRing(x,z,p.rings[0]) && !p.rings.slice(1).some(r=>inRing(x,z,r)); }

/** Index ONLY the loaded current floor's source room polygons (including public
 * background floor surfaces). A courtyard hole never grants below-DTM access.
 * If multiple source Z planes overlap, choose the highest reachable plane at or
 * below referenceY; when below them all, choose the lowest plane and lift to it.
 */
export function createAllowedFloorSampler(verifiedBuildingParts: readonly PolygonPart[], currentFloorRooms: readonly FloorRoom[], cellSize=25): AllowedFloorSampler {
  const buckets=new Map<string,FloorRoom[]>();
  for (const room of currentFloorRooms) {
    if (!finite(room.heightSourceZ) || !room.rings[0]?.length) continue;
    let x0=Infinity,z0=Infinity,x1=-Infinity,z1=-Infinity;
    for (const p of room.rings[0]) { x0=Math.min(x0,p[0]);x1=Math.max(x1,p[0]);z0=Math.min(z0,p[1]);z1=Math.max(z1,p[1]); }
    for (let c=Math.floor(x0/cellSize); c<=Math.floor(x1/cellSize); c++) for (let r=Math.floor(z0/cellSize); r<=Math.floor(z1/cellSize); r++) {
      const key=c+','+r, list=buckets.get(key)||[]; list.push(room);buckets.set(key,list);
    }
  }
  return (x,z,referenceY) => {
    if (!verifiedBuildingParts.some(p=>inPart(x,z,p))) return null;
    let lowest=Infinity, below=-Infinity;
    for (const room of buckets.get(Math.floor(x/cellSize)+','+Math.floor(z/cellSize))||[]) if (inPart(x,z,room)) {
      lowest=Math.min(lowest,room.heightSourceZ);
      if (room.heightSourceZ<=referenceY+1e-4) below=Math.max(below,room.heightSourceZ);
    }
    return finite(below) ? below : finite(lowest) ? lowest : null;
  };
}

export class CameraGroundConstraint {
  readonly options: Required<GroundOptions>;
  private previous: { camera:XYZ; target:XYZ; key:string } | null=null;
  private lastOutdoorCamera: number | null=null;
  private lastOutdoorTarget: number | null=null;
  constructor(options:GroundOptions={}) {
    this.options={cameraClearance:1.8,targetClearance:.1,cameraProbeRadius:.35,unknownInitialHeight:0,sweepStepMeters:2.5,maxSweepSamples:128,...options};
    if (this.options.cameraClearance<=0 || this.options.targetClearance<0 || this.options.cameraProbeRadius<0 || this.options.sweepStepMeters<=0 || this.options.maxSweepSamples<1) throw new Error('Invalid ground constraint options');
  }
  /** Use after a non-animated teleport or replacing the coordinate frame. */
  reset() { this.previous=null;this.lastOutdoorCamera=null;this.lastOutdoorTarget=null; }
  constrain(camera:CameraLike,target:XYZ,context:GroundContext):GroundMetrics {
    if (![camera.position.x,camera.position.y,camera.position.z,target.x,target.y,target.z].every(finite)) throw new Error('Non-finite camera/target');
    const o=this.options, initialCamera=copy(camera.position), initialTarget=copy(target);
    let queries=0, sweepSamples=0, sweepBlocked=false, acceptedMovementFraction=1, sweepCoarsened=false;
    const key=context.contextKey||'';
    const surfaceAt=(x:number,z:number,referenceY:number,held:number|null):Surface=>{
      queries++;
      const floor=context.allowedFloorAt?.(x,z,referenceY);
      if (finite(floor)) return {height:floor,source:'indoor'};
      const detail=context.sampleDetail?.(x,z);
      if (finite(detail)) return {height:detail,source:'detail'};
      const ground=context.sampleGround(x,z);
      if (finite(ground)) return {height:ground,source:'terrain'};
      if (context.isKnownWater?.(x,z)) return {height:context.waterHeight??0,source:'water'};
      return {height:held??o.unknownInitialHeight,source:held===null?'unknown-initial':'unknown-held'};
    };
    const cameraSurface=(p:XYZ):Surface=>{
      let found=surfaceAt(p.x,p.z,p.y,this.lastOutdoorCamera);
      if (o.cameraProbeRadius) for (const [dx,dz] of [[o.cameraProbeRadius,0],[-o.cameraProbeRadius,0],[0,o.cameraProbeRadius],[0,-o.cameraProbeRadius]]) {
        const sample=surfaceAt(p.x+dx,p.z+dz,p.y,this.lastOutdoorCamera);
        if (sample.height>found.height) found=sample;
      }
      return found;
    };
    const liftTargetAndCamera=()=>{
      const ground=surfaceAt(target.x,target.z,target.y,this.lastOutdoorTarget);
      const dy=Math.max(0,ground.height+o.targetClearance-target.y);
      if (dy>1e-7) { target.y+=dy;camera.position.y+=dy; }
      return ground;
    };
    let targetSurface=liftTargetAndCamera();
    let camSurface=cameraSurface(camera.position);
    camera.position.y=Math.max(camera.position.y,camSurface.height+o.cameraClearance);

    // A bounded swept segment prevents fast pan/zoom/fly stepping through a hill
    // between safe endpoints. Stop at the last safe point instead of launching
    // the camera skyward. Floor-context changes deliberately reset this segment.
    if (context.sweep!==false && this.previous && this.previous.key===key) {
      const prev=this.previous, requested=copy(camera.position), requestedTarget=copy(target);
      const distance=Math.hypot(requested.x-prev.camera.x,requested.z-prev.camera.z);
      const needed=Math.max(1,Math.ceil(distance/o.sweepStepMeters));
      const steps=Math.min(needed,o.maxSweepSamples);sweepCoarsened=needed>steps;
      let safeT=0;
      const isSafe=(t:number)=>{const p=mix(prev.camera,requested,t);sweepSamples++;return p.y+1e-5>=cameraSurface(p).height+o.cameraClearance;};
      if (distance>1e-5) for (let i=1;i<=steps;i++) {
        const t=i/steps;
        if (!isSafe(t)) {
          let low=safeT,high=t;
          for (let j=0;j<8;j++) { const mid=(low+high)/2;if(isSafe(mid))low=mid;else high=mid; }
          assign(camera.position,mix(prev.camera,requested,low));assign(target,mix(prev.target,requestedTarget,low));
          sweepBlocked=true;acceptedMovementFraction=low;break;
        }
        safeT=t;
      }
      targetSurface=liftTargetAndCamera();camSurface=cameraSurface(camera.position);
      camera.position.y=Math.max(camera.position.y,camSurface.height+o.cameraClearance);
    }
    // Record only measured outdoor/water references, never let an indoor LG
    // allowance lower the protective NoData fallback after leaving the building.
    const known=(s:Surface)=>s.source==='terrain'||s.source==='detail'||s.source==='water';
    if (known(camSurface)) this.lastOutdoorCamera=camSurface.height;
    if (known(targetSurface)) this.lastOutdoorTarget=targetSurface.height;
    this.previous={camera:copy(camera.position),target:copy(target),key};
    camera.lookAt?.(target.x,target.y,target.z);camera.updateMatrixWorld?.(true);
    const deltaY=camera.position.y-initialCamera.y, targetDeltaY=target.y-initialTarget.y;
    return {corrected:sweepBlocked||Math.abs(deltaY)>1e-7||Math.abs(targetDeltaY)>1e-7,
      cameraCorrectionY:deltaY,targetCorrectionY:targetDeltaY,cameraSurfaceY:camSurface.height,targetSurfaceY:targetSurface.height,
      cameraClearance:camera.position.y-camSurface.height,cameraSource:camSurface.source,targetSource:targetSurface.source,
      sweepBlocked,acceptedMovementFraction,sweepSamples,sweepCoarsened,groundQueries:queries};
  }
}
