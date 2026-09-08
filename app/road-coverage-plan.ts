import * as THREE from 'three';
import type { VisibleDetail } from './detail-priority';
import type { Bounds3 } from './source-types';
import { partialSlots } from './spatial-masks';

export type VerifiedRoadCluster = {
  id: string;
  roadEntityIds: string[];
  streetCentrelineIds: Array<string | number>;
  partitionIds: string[];
  sourceLineLocalXZ: Array<[number, number]>;
  bounds: Bounds3;
  evidence: Record<string, unknown>;
};
export type RoadProtectionManifest = { version: 1; clusters: VerifiedRoadCluster[] };
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(item => typeof item === 'string' && item.length > 0);
const point = (value: unknown): value is [number, number, number] =>
  Array.isArray(value) && value.length === 3 && value.every(item => typeof item === 'number' && Number.isFinite(item));

/** This is a checked source cross-reference, not a name-based road classifier. */
export function parseRoadProtection(value: unknown): RoadProtectionManifest {
  if (!record(value) || value.version !== 1 || !Array.isArray(value.clusters))
    throw new Error('Invalid road source protection manifest');
  const ids = new Set<string>();
  const clusters = value.clusters.map((entry: unknown): VerifiedRoadCluster => {
    if (!record(entry) || typeof entry.id !== 'string' || !entry.id || ids.has(entry.id) ||
      !strings(entry.roadEntityIds) || !entry.roadEntityIds.length ||
      !Array.isArray(entry.streetCentrelineIds) || !entry.streetCentrelineIds.every(id =>
        typeof id === 'string' && id.length > 0 || typeof id === 'number' && Number.isFinite(id)) ||
      !strings(entry.partitionIds) || !entry.partitionIds.length ||
      entry.verifiedCoverageFraction !== 1 ||
      !Array.isArray(entry.sourceLineLocalXZ) || entry.sourceLineLocalXZ.length < 2 ||
      !entry.sourceLineLocalXZ.every(p => Array.isArray(p) && p.length === 2 && p.every(n => typeof n === 'number' && Number.isFinite(n))) ||
      !record(entry.bounds) || !point(entry.bounds.min) || !point(entry.bounds.max) ||
      entry.bounds.min.some((coordinate, axis) => coordinate > (entry.bounds as Bounds3).max[axis]) ||
      !record(entry.evidence))
      throw new Error('Invalid or duplicate road source cluster');
    ids.add(entry.id);
    return {
      id: entry.id,
      roadEntityIds: [...entry.roadEntityIds],
      streetCentrelineIds: [...entry.streetCentrelineIds],
      partitionIds: [...new Set(entry.partitionIds)],
      sourceLineLocalXZ: entry.sourceLineLocalXZ.map(p => [p[0], p[1]]),
      bounds: { min: [...entry.bounds.min], max: [...entry.bounds.max] },
      evidence: entry.evidence,
    };
  });
  return { version: 1, clusters };
}

/** Render policy only: reserve audited source partitions in the near image.
 * The exit margin prevents cancellation from small motion around 300 metres.
 * Distance and visibility are computed for each actual partition, not a long
 * road's overall bounds. Metadata never reserves the entire campus at once.
 */
export const roadCoverageRange = { enterMeters: 300, exitMeters: 330 } as const;

export type VisibleRoadCluster = {
  id: string;
  score: number;
  pixels: number;
  distance: number;
  cluster: VerifiedRoadCluster;
  visibleSegments: Array<[[number, number], [number, number]]>;
};

/** Clip actual line segments in homogeneous space, including the near plane. */
function clippedLine(a: THREE.Vector4, b: THREE.Vector4) {
  let enter=0,exit=1;
  const planes=(p:THREE.Vector4)=>[p.w+p.x,p.w-p.x,p.w+p.y,p.w-p.y,p.w+p.z,p.w-p.z];
  const from=planes(a),to=planes(b);
  for(let index=0;index<6;index++){
    if(from[index]<0&&to[index]<0)return null;
    if((from[index]<0)!==(to[index]<0)){
      const at=from[index]/(from[index]-to[index]);
      if(from[index]<0)enter=Math.max(enter,at);else exit=Math.min(exit,at);
    }
  }
  if(enter>exit)return null;
  const start=a.clone().lerp(b,enter),end=a.clone().lerp(b,exit);
  return start.w>0&&end.w>0?{points:[start.multiplyScalar(1/start.w),end.multiplyScalar(1/end.w)],enter,exit}:null;
}

/** Real source centreline XZ, sampled on the existing ground reference only for
 * view ranking. These Y values are not road-deck measurements or new geometry.
 * Unlike a large source bbox, a road behind the camera contributes zero pixels.
 */
export function visibleRoadClusters(
  camera:THREE.PerspectiveCamera,clusters:readonly VerifiedRoadCluster[],height:number,
  sampleGround:(x:number,z:number)=>number|null,
):VisibleRoadCluster[]{
  camera.updateMatrixWorld();
  const transform=new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);
  const width=height*camera.aspect,focusX=-camera.projectionMatrix.elements[8],focusY=-camera.projectionMatrix.elements[9];
  const result:VisibleRoadCluster[]=[];
  for(const cluster of clusters){
    let score=0,pixels=0,distance=Infinity;
    const visibleSegments:VisibleRoadCluster['visibleSegments']=[];
    for(let segment=1;segment<cluster.sourceLineLocalXZ.length;segment++){
      const a=cluster.sourceLineLocalXZ[segment-1],b=cluster.sourceLineLocalXZ[segment];
      const samples=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/5));
      let previous:THREE.Vector3|null=null;
      for(let index=0;index<=samples;index++){
        const fraction=index/samples,x=a[0]+(b[0]-a[0])*fraction,z=a[1]+(b[1]-a[1])*fraction,y=sampleGround(x,z);
        const point=y!==null&&Number.isFinite(y)?new THREE.Vector3(x,y,z):null;
        if(point&&previous){
          const clipped=clippedLine(new THREE.Vector4(previous.x,previous.y,previous.z,1).applyMatrix4(transform),new THREE.Vector4(point.x,point.y,point.z,1).applyMatrix4(transform));
          if(clipped){
            const [start,end]=clipped.points,length=Math.hypot((end.x-start.x)*width/2,(end.y-start.y)*height/2);
            const cx=(start.x+end.x)/2-focusX,cy=(start.y+end.y)/2-focusY;
            const centrality=.12+.88*Math.exp(-3.5*(cx*cx+cy*cy));
            const nearby=new THREE.Line3(previous,point).closestPointToPoint(camera.position,true,new THREE.Vector3()).distanceTo(camera.position);
            distance=Math.min(distance,nearby);pixels+=length;score+=length*centrality/(1+nearby/800);
            const first=previous.clone().lerp(point,clipped.enter),last=previous.clone().lerp(point,clipped.exit);
            visibleSegments.push([[first.x,first.z],[last.x,last.z]]);
          }
        }
        previous=point;
      }
    }
    if(pixels>=24&&Number.isFinite(distance))result.push({id:cluster.id,score,pixels,distance,cluster,visibleSegments});
  }
  return result.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
}

export function selectRoadCoveragePartitions(
  visible: readonly VisibleDetail[],
  allowed: ReadonlySet<string>,
  retained: ReadonlySet<string> = new Set(),
  capacity = partialSlots.length,
): string[] {
  const result: string[] = [];
  const unique = new Set<string>();
  for (const candidate of visible) {
    if (result.length >= capacity) break;
    if (unique.has(candidate.id) || !allowed.has(candidate.id) ||
      !Number.isFinite(candidate.distance) || candidate.distance < 0) continue;
    unique.add(candidate.id);
    const limit = retained.has(candidate.id) ? roadCoverageRange.exitMeters : roadCoverageRange.enterMeters;
    if (candidate.distance <= limit) result.push(candidate.id);
  }
  return result;
}

export class RoadCoveragePlanner {
  readonly partitionIds: ReadonlySet<string>;
  private retained = new Set<string>();
  private primary = '';
  constructor(readonly manifest: RoadProtectionManifest = { version: 1, clusters: [] }) {
    this.partitionIds = new Set(manifest.clusters.flatMap(cluster => cluster.partitionIds));
  }
  plan(
    visible: readonly VisibleRoadCluster[],
    partitions: readonly {id:string;bounds:Bounds3}[],
    bytesFor:(ids:ReadonlySet<string>)=>number,
    budgetBytes:number,
  ) {
    const byId=new Map(partitions.map(partition=>[partition.id,partition]));
    const near=visible.filter(candidate=>candidate.distance<=(this.retained.has(candidate.id)?roadCoverageRange.exitMeters:roadCoverageRange.enterMeters));
    this.retained=new Set(near.map(candidate=>candidate.id));
    const previous=near.find(candidate=>candidate.id===this.primary);
    const first=previous&&previous.score*1.2>=(near[0]?.score??0)?previous:near[0];
    this.primary=first?.id??'';
    const overlaps=(segment:VisibleRoadCluster['visibleSegments'][number],bounds:Bounds3)=>{
      let from=0,to=1;
      for(const [axis,index]of [[0,0],[1,2]] as const){
        const start=segment[0][axis],delta=segment[1][axis]-start,min=bounds.min[index],max=bounds.max[index];
        if(Math.abs(delta)<1e-10){if(start<min||start>max)return false;continue;}
        const a=(min-start)/delta,b=(max-start)/delta;
        from=Math.max(from,Math.min(a,b));to=Math.min(to,Math.max(a,b));
        if(from>to)return false;
      }
      return true;
    };
    const visibleIds=(candidate:VisibleRoadCluster)=>candidate.cluster.partitionIds.filter(id=>{
      const partition=byId.get(id);
      return partition&&candidate.visibleSegments.some(segment=>overlaps(segment,partition.bounds));
    });
    const connected=(a:VisibleRoadCluster,b:VisibleRoadCluster)=>{
      const ends=(candidate:VisibleRoadCluster)=>[candidate.cluster.sourceLineLocalXZ[0],candidate.cluster.sourceLineLocalXZ.at(-1)!];
      return ends(a).some(p=>ends(b).some(q=>Math.hypot(p[0]-q[0],p[1]-q[1])<=.75));
    };
    // Expand through source-connected near segments. Never jump past a deferred
    // middle segment to spend its reservation on a disconnected farther piece.
    const component:VisibleRoadCluster[]=first?[first]:[];
    const remaining=near.filter(candidate=>candidate!==first);
    for(let changed=true;changed;){
      changed=false;
      for(const candidate of remaining){
        if(component.includes(candidate)||!component.some(kept=>connected(candidate,kept)))continue;
        component.push(candidate);changed=true;
      }
    }
    const accepted:VisibleRoadCluster[]=[],ids=new Set<string>(),attempted=new Set<string>();
    const desiredIds=new Set(component.flatMap(visibleIds));
    for(let changed=true;changed;){
      changed=false;
      for(const candidate of component){
        if(attempted.has(candidate.id)||candidate!==first&&!accepted.some(kept=>connected(candidate,kept)))continue;
        attempted.add(candidate.id);
        const additions=visibleIds(candidate),next=new Set([...ids,...additions]);
        if(!additions.length||next.size>partialSlots.length||bytesFor(next)>budgetBytes)continue;
        accepted.push(candidate);for(const id of additions)ids.add(id);changed=true;
      }
    }
    return {
      primaryClusterId:this.primary,
      desiredClusterIds:component.map(candidate=>candidate.id),
      acceptedClusterIds:accepted.map(candidate=>candidate.id),
      deferredClusterIds:component.filter(candidate=>!accepted.includes(candidate)).map(candidate=>candidate.id),
      desiredPartitionIds:[...desiredIds],
      acceptedPartitionIds:[...ids],
      deferredPartitionIds:[...desiredIds].filter(id=>!ids.has(id)),
      desiredBytes:bytesFor(desiredIds),
      acceptedBytes:bytesFor(ids),
      budgetBytes,
      candidates:near.map(candidate=>({id:candidate.id,score:candidate.score,pixels:candidate.pixels,distance:candidate.distance})),
    };
  }
}

export type RoadCoverageDiagnostics = ReturnType<RoadCoveragePlanner['plan']> & {
  desiredFinePartitionIds: string[];
  reservedFinePartitionIds: string[];
  acceptedFinePartitionIds: string[];
  readyFinePartitionIds: string[];
  deferredFinePartitionIds: string[];
  unavailableFinePartitionIds: string[];
  desiredFineBytes: number | null;
  reservedFineBytes: number;
  profileMeshBudgetBytes: number;
  grantedMeshBudgetBytes: number;
  poolCapBytes: number;
  exteriorPlanBytes: number;
};
