import * as THREE from 'three';
export function releaseObject(root:THREE.Object3D){
 const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>(),textures=new Set<THREE.Texture>();
 root.traverse((o:any)=>{if(o.geometry)geometries.add(o.geometry);for(const m of(o.material?(Array.isArray(o.material)?o.material:[o.material]):[])){materials.add(m);for(const value of Object.values(m))if(value instanceof THREE.Texture)textures.add(value)}});
 for(const g of geometries)g.dispose();for(const m of materials)m.dispose();for(const t of textures)releaseTexture(t);
}
export function releaseTexture(t:THREE.Texture){t.dispose();const images=Array.isArray(t.image)?t.image:[t.image];for(const image of images)image?.close?.()}
export function localCadCopy(source:ArrayBuffer,center:{x:number;y:number;z:number}){const p=new Float32Array(source.slice(0));for(let i=0;i<p.length;i+=3){p[i]-=center.x;p[i+1]-=center.y-.08;p[i+2]-=center.z}return p}
