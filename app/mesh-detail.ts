import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {releaseObject} from './resources';
import type {Quality} from './detail-stream';
export class MeshDetail{
 patches:any[]=[];root=new THREE.Group();current:any=null;loading:any=null;wanted='';dead=false;progress=0;failures=new Set<string>();clip:THREE.Plane[]=[];
 constructor(public scene:THREE.Scene,public baseline:THREE.Group){scene.add(this.root)}
 async init(){const r=await fetch('/models/hires/manifest.json');if(r.ok){const d:any=await r.json();if(!this.dead)this.patches=d.patches}}
 update(quality:Quality,camera:THREE.Vector3,target:THREE.Vector3,visible:boolean){this.root.visible=visible;const distance=camera.distanceTo(target);let patch=quality!=='light'&&visible&&distance<650?this.patches.slice().sort((a,b)=>Math.hypot(a.center[0]-target.x,a.center[2]-target.z)-Math.hypot(b.center[0]-target.x,b.center[2]-target.z))[0]:null;if(patch&&Math.hypot(patch.center[0]-target.x,patch.center[2]-target.z)>185)patch=null;const level=quality==='detail'&&distance<290&&patch?.levels.fine?'fine':'high',key=patch?patch.id+'/'+level:'';this.wanted=key;
 if(this.loading&&this.loading.key!==key){this.loading.controller.abort();this.loading=null}
 if(this.current&&this.current.key!==key)this.unload();if(!key||this.current?.key===key||this.loading?.key===key||this.failures.has(key))return;this.load(patch,level,key)}
 unload(){if(!this.current)return;for(const o of this.baseline.children)if(this.current.patch.baselineIds.includes(o.name))o.visible=true;releaseObject(this.root);this.root.clear();this.current=null}
 async load(patch:any,level:string,key:string){const controller=new AbortController();this.loading={controller,key};this.progress=0;const group=new THREE.Group(),loader=new GLTFLoader();try{for(const tile of patch.levels[level].tiles){const response=await fetch('/models/hires/'+tile.url,{signal:controller.signal});if(!response.ok)throw Error('高细节分块读取失败');const gltf=await loader.parseAsync(await response.arrayBuffer(),'/models/hires/');gltf.scene.applyMatrix4(new THREE.Matrix4().fromArray(tile.matrix));gltf.scene.traverse((o:any)=>{if(!o.isMesh)return;const wasArray=Array.isArray(o.material);const converted=(wasArray?o.material:[o.material]).map((m:any)=>{if(m.map){m.map.generateMipmaps=false;m.map.minFilter=THREE.LinearFilter;m.map.anisotropy=4}const mat=new THREE.MeshBasicMaterial({map:m.map,color:m.color,side:THREE.DoubleSide,vertexColors:!!o.geometry.attributes.color,clippingPlanes:this.clip});m.dispose();return mat});o.material=wasArray?converted:converted[0]});group.add(gltf.scene);if(this.dead||controller.signal.aborted||this.wanted!==key){releaseObject(group);return}this.progress++}
 // Replace the complete frontier atomically. Old geometry stays visible until this point.
 if(this.dead||controller.signal.aborted||this.wanted!==key){releaseObject(group);return}this.unload();this.root.add(group);this.current={key,patch,level};for(const o of this.baseline.children)if(patch.baselineIds.includes(o.name))o.visible=false;
 }catch(e){releaseObject(group);if(!controller.signal.aborted)this.failures.add(key)}finally{if(this.loading?.controller===controller)this.loading=null}}
 setClip(planes:THREE.Plane[]){this.clip=planes;this.root.traverse((o:any)=>{for(const m of(o.material?(Array.isArray(o.material)?o.material:[o.material]):[])){m.clippingPlanes=planes;m.needsUpdate=true}})}
 stats(){const p=this.current;return {meshPatch:p?.patch.id||'',meshLevel:p?.level||'baseline',meshTriangles:p?p.patch.levels[p.level].triangles:0,meshTextureMiB:p?Math.round(p.patch.levels[p.level].textureBytes/1048576):0,meshLoading:this.loading?this.progress:0,meshTotal:this.loading?this.patches.find(p=>this.loading.key.startsWith(p.id+'/'))?.levels[this.loading.key.split('/')[1]]?.tiles.length:0,meshErrors:this.failures.size}}
 dispose(){this.dead=true;this.loading?.controller.abort();this.unload();this.scene.remove(this.root)}
}
