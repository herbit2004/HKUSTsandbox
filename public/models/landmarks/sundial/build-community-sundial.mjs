import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const base=path.dirname(fileURLToPath(import.meta.url));
const project=process.argv[2]||path.resolve(base,'../../../..');
const req=createRequire(project+'/package.json'),THREE=req('three');
const {STLLoader}=await import(pathToFileURL(req.resolve('three/addons/loaders/STLLoader.js')).href);
const {GLTFExporter}=await import(pathToFileURL(req.resolve('three/addons/exporters/GLTFExporter.js')).href);
globalThis.FileReader=class {readAsArrayBuffer(blob){blob.arrayBuffer().then(result=>{this.result=result;this.onloadend?.()})}};
const m=JSON.parse(fs.readFileSync(base+'/manifest.json','utf8')),entityId=m.entityId;
const raw=fs.readFileSync(base+'/community-source/redBird_OpenSCAD.stl');
const source=new STLLoader().parse(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength));
const positions=source.getAttribute('position'),clipped=[];let discarded=0,crossed=0;
// The source generator fuses its upper printing cylinder through z=0.5.
// Keep only the body above that plane. Intersections stay on original facets.
const cut=.5;
function clip(poly){const out=[];for(let i=0;i<poly.length;i++){const a=poly[i],b=poly[(i+1)%poly.length],ai=a[2]>=cut,bi=b[2]>=cut;if(ai)out.push(a);if(ai!==bi){const t=(cut-a[2])/(b[2]-a[2]);out.push(a.map((x,k)=>x+(b[k]-x)*t))}}return out}
for(let i=0;i<positions.count;i+=3){
 const triangle=[0,1,2].map(j=>[positions.getX(i+j),positions.getY(i+j),positions.getZ(i+j)]);
 if(triangle.every(p=>p[2]<=cut+1e-7)){discarded++;continue}
 const poly=clip(triangle);if(poly.length!==3||triangle.some(p=>p[2]<cut))crossed++;
 for(let j=1;j<poly.length-1;j++)clipped.push(...poly[0],...poly[j],...poly[j+1]);
}
const scale=8.5/(100-cut),angle=34*Math.PI/180;
function world([x,y,z]){return new THREE.Vector3((x*Math.cos(angle)+y*Math.sin(angle))*scale+m.position[0],(z-cut)*scale+m.position[1],(x*Math.sin(angle)-y*Math.cos(angle))*scale+m.position[2])}
const local=[];for(let i=0;i<clipped.length;i+=3)local.push(...world(clipped.slice(i,i+3)).toArray());
const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(local,3));geometry.computeVertexNormals();
const red=new THREE.MeshStandardMaterial({color:0xdc1128,metalness:.35,roughness:.38,side:THREE.DoubleSide});
const root=new THREE.Group();root.name='The Red Bird Sundial - community reconstruction';root.userData={entityId,approximation:true,license:'MIT',source:'HKFoggyU/OpenRedBird3D'};
const body=new THREE.Mesh(geometry,red);body.name='community-redbird-body-without-print-base';body.userData={entityId,representationRole:'community_reconstructed_sculpture',approximation:true};root.add(body);
// The community source omits the thin diagonal rod seen in official photographs.
// Bind its upper end to a body vertex near 4.1m, and its lower end to the bowl.
const vertices=[];for(let i=0;i<clipped.length;i+=3)vertices.push(clipped.slice(i,i+3));
function nearest(target){let result=vertices[0],best=Infinity;for(const p of vertices){const d=p.reduce((s,v,i)=>s+(v-target[i])**2,0);if(d<best){result=p;best=d}}return result}
const rodTop=nearest([-11,0,cut+4.1/scale]),rodBottom=nearest([4,23,cut+1.55/scale]);
const a=world(rodTop),b=world(rodBottom),delta=b.clone().sub(a),rodGeometry=new THREE.CylinderGeometry(.032,.032,delta.length(),16);
rodGeometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize()));rodGeometry.translate(...a.clone().add(b).multiplyScalar(.5).toArray());
const rod=new THREE.Mesh(rodGeometry,new THREE.MeshStandardMaterial({color:0x949c9e,metalness:.7,roughness:.32}));rod.name='photo-reference-slender-diagonal-rod';rod.userData={entityId,representationRole:'photo_approximated_sundial_rod',approximation:true};root.add(rod);
const bounds=new THREE.Box3().setFromObject(root);const bytes=Buffer.from(await new GLTFExporter().parseAsync(root,{binary:true}));fs.writeFileSync(base+'/'+m.url,bytes);
m.geometryBytes=bytes.length;m.sha256=crypto.createHash('sha256').update(bytes).digest('hex');m.bounds={min:bounds.min.toArray(),max:bounds.max.toArray()};m.meshes=2;m.triangles=local.length/9+rodGeometry.index.count/3;m.geometryBasis='MIT-licensed HKFoggyU/OpenRedBird3D community reconstruction plus photo-reference rod; not official CAD/BIM';
m.parameters={totalHeight:8.5,officialHeightMeaning:'CMO design proposal states 8.5 m; not independent current survey',steelThicknessMeasured:false,sourcePrintBodyHeight:100,sourcePrintingSupportTop:.5,retainedBodyHeight:99.5,scaleMetersPerSourceUnit:scale,rawSourceUnitsMeaning:'Source .py uses mm for a 100mm printable model; no original-world coordinate registration',sourceTriangles:positions.count/3,discardedPrintingSupportTriangles:discarded,clippedTriangles:crossed,orientationDegrees:34,orientationMeaning:'Qualitative alignment with official aerial/side photographs; not surveyed azimuth',poolPodiumReliefGenerated:false,rodAddedFromOfficialPhotos:true,rodRadiusMeters:.032,rodDimensionsMeasured:false,rodEndpointsSourceModel:[rodTop,rodBottom]};
m.sources.communityModel={repository:'https://github.com/HKFoggyU/OpenRedBird3D',commit:'8d42b92cca54d9da26f75b0f7ea4fd6adea3168e',commitDate:'2022-10-13',license:'MIT',copyright:'Copyright (c) 2022 Hong Kong Foggy University',files:['redBird_OpenSCAD.stl','redBird_OpenSCAD.py','LICENSE'].map(name=>({asset:'community-source/'+name,sha256:crypto.createHash('sha256').update(fs.readFileSync(base+'/community-source/'+name)).digest('hex')})),changes:'Remove fused printing base at source z<=0.5; clip crossing facets; scale retained body to published 8.5m; right-handed Z-up to Y-up campus registration; unified red material; add approximate thin rod. No artificial stage/pool added.'};
m.limitations=['Community reconstruction for 3D printing, not official CAD, measured steelwork, BIM or a scientifically calibrated sundial.','The CMO-published 8.5m constrains retained body height; shape proportions, thickness, yaw, support elevation and added rod remain approximations.','The source printing cylinder is fused through z=0.5; removing it also removes that interference band. No lost as-built geometry is claimed to be recovered.','Historic 2004/undated photos establish form, not current ground/pool condition.','The original photographic podium, steps and pool remain. CMO relief dimensions conflict (7.0 x 1.5m proposal versus 9m caption), so no relief, pool or waterfall is generated.'];
fs.writeFileSync(base+'/manifest.json',JSON.stringify(m,null,2)+'\n');
const preview=[];root.traverse(o=>{if(!o.isMesh)return;const g=o.geometry.index?o.geometry.toNonIndexed():o.geometry;preview.push({name:o.name,positions:Array.from(g.getAttribute('position').array),color:o.material.color.toArray(),role:o.userData.representationRole})});
fs.writeFileSync('/tmp/hkust-sundial-model/preview-geometry.json',JSON.stringify(preview));fs.writeFileSync('/tmp/hkust-sundial-model/manifest.json',JSON.stringify(m,null,2)+'\n');
console.log(JSON.stringify({meshes:m.meshes,triangles:m.triangles,bytes:bytes.length,bounds:m.bounds,sourceSupportTrianglesRemoved:discarded,sourceCutTriangles:crossed}));
