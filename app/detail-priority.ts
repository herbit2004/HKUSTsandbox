import * as THREE from 'three';
import {textureMipBytes,type Bounds3} from './source-types';

export type DetailCandidate={id:string;bounds:Bounds3;buildingId?:string};
export type VisibleDetail={id:string;score:number;pixels:number;distance:number};
export type DetailVisibilityRetention={ids:ReadonlySet<string>;pixelRatio?:number;guardBand?:number};

/** Rank actual building bounds in the current image, independently of orbit target or selection history. */
export function visibleDetails(camera:THREE.PerspectiveCamera,candidates:DetailCandidate[],height:number,minPixels=48,retention?:DetailVisibilityRetention):VisibleDetail[]{
 camera.updateMatrixWorld();
 const matrix=new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);
 const frustum=new THREE.Frustum().setFromProjectionMatrix(matrix);
 const band=1+(retention?.guardBand??.12);
 const retainedFrustum=retention?new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().makeScale(1/band,1/band,1).multiply(matrix)):frustum;
 const result:VisibleDetail[]=[];
 for(const candidate of candidates){
  const box=new THREE.Box3(new THREE.Vector3(...candidate.bounds.min),new THREE.Vector3(...candidate.bounds.max));
  const retained=retention?.ids.has(candidate.id)??false,edge=retained?band:1;
  if(!(retained?retainedFrustum:frustum).intersectsBox(box))continue;
  const distance=box.distanceToPoint(camera.position);
  let left=1,right=-1,bottom=1,top=-1;
  if(box.containsPoint(camera.position)){left=bottom=-1;right=top=1}
  else{
   const corners:THREE.Vector4[]=[];
   for(let i=0;i<8;i++)corners.push(new THREE.Vector4(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z,1).applyMatrix4(matrix));
   const points=corners.filter(p=>p.w>0&&p.z>=-p.w);
   // Include edge/near-plane intersections so a nearby facade cannot vanish from the candidate set.
   for(let i=0;i<8;i++)for(const bit of [1,2,4])if(!(i&bit)){
    const a=corners[i],b=corners[i|bit],da=a.z+a.w,db=b.z+b.w;
    if((da<0)!==(db<0)){const point=a.clone().lerp(b,da/(da-db));if(point.w>0)points.push(point)}
   }
   for(const p of points){left=Math.min(left,p.x/p.w);right=Math.max(right,p.x/p.w);bottom=Math.min(bottom,p.y/p.w);top=Math.max(top,p.y/p.w)}
   left=Math.max(-edge,left);right=Math.min(edge,right);bottom=Math.max(-edge,bottom);top=Math.min(edge,top);
  }
  if(right<=left||top<=bottom)continue;
  const widthPixels=(right-left)*height*camera.aspect/2,heightPixels=(top-bottom)*height/2;
  const pixels=Math.max(widthPixels,heightPixels);
  if(pixels<minPixels*(retained?(retention?.pixelRatio??.7):1))continue;
  const cx=(left+right)/2,cy=(bottom+top)/2;
  const centrality=.22+.78*Math.exp(-2.8*(cx*cx+cy*cy));
  const score=Math.sqrt(widthPixels*heightPixels)*centrality/(1+distance/800);
  result.push({id:candidate.id,score,pixels,distance});
 }
 return result.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
}

/** Spatial/score hysteresis, not a camera-stop timer. A retained neighbour gives
 * up its place only to a candidate with a clear projected advantage; leaving
 * the small frustum guard band removes it immediately. Whole-group budgets are
 * still applied afterwards, so this never grants an extra source reservation.
 */
export class StableDetailOrder{
 ids:string[]=[];
 rank(candidates:readonly VisibleDetail[]):VisibleDetail[]{
  const byId=new Map(candidates.map(candidate=>[candidate.id,candidate]));
  const order=this.ids.filter(id=>byId.has(id));
  const included=new Set(order);
  for(const candidate of candidates)if(!included.has(candidate.id)){order.push(candidate.id);included.add(candidate.id);}
  for(let index=1;index<order.length;index++)for(let at=index;at>0;at--){
   if(byId.get(order[at])!.score<=byId.get(order[at-1])!.score*1.2)break;
   [order[at-1],order[at]]=[order[at],order[at-1]];
  }
  this.ids=order;return order.map(id=>byId.get(id)!);
 }
}

/** Stable candidate identity, not a requirement that the camera stop moving. */
export class StableDetailChoice{
 proposed='';since=0;choice='';
 choose(candidates:VisibleDetail[],now:number,currentId='',priorityId=''){
  let best=candidates[0];
  const priority=candidates.find(c=>c.id===priorityId);
  if(priority)best=priority;
  const current=candidates.find(c=>c.id===currentId);
  if(!priority&&current&&best&&current.score*1.3>=best.score)best=current;
  const proposed=best?.id||'';
  if(proposed!==this.proposed){this.proposed=proposed;this.since=now}
  if(proposed===currentId&&proposed)this.choice=proposed;
  else if(now-this.since>=(proposed?500:1800))this.choice=proposed;
  return this.choice;
 }
}

export type TextureDetailGroup=DetailCandidate&{textures:import('./source-types').TextureSource[]};
/** Budget whole source groups, deduplicating shared atlases; never truncate an individual building's group. */
export function textureDetailPlan(groups:TextureDetailGroup[],visible:VisibleDetail[],budgetBytes=128*1048576){
 const byId=new Map(groups.map(g=>[g.id,g]));
 const images=new Map<string,import('./source-types').TextureSource>();
 const accepted:string[]=[],deferred:string[]=[];
 let bytes=0;
 for(const candidate of visible){
  const group=byId.get(candidate.id);if(!group)continue;
  const additions=group.textures.filter(t=>Math.max(t.width,t.height)>512&&!images.has(t.url));
  const unique=[...new Map(additions.map(t=>[t.url,t])).values()];
  const cost=unique.reduce((n,t)=>n+textureMipBytes(t.width,t.height),0);
  if(bytes+cost>budgetBytes){deferred.push(group.id);continue}
  bytes+=cost;for(const t of unique)images.set(t.url,t);accepted.push(group.id);
 }
 const sources=[...images.values()].sort((a,b)=>a.url.localeCompare(b.url));
 return {key:sources.map(t=>t.url).join('|'),images:sources,bytes,accepted,deferred};
}
