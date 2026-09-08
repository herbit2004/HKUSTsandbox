import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),stage=path.join(root,'docs/source-evidence-v4/building-quality');
const require=createRequire(path.join(root,'package.json')),ts=require('typescript'),THREE=require('three');
const {sampleTerrainLocalHeight}=await import(pathToFileURL(path.join(root,'public/terrain/sample-height.js')));
const compiled=new Map();
function load(name){if(compiled.has(name))return compiled.get(name);const exports={};compiled.set(name,exports);const source=fs.readFileSync(path.join(root,'app',name+'.ts'),'utf8');vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require(id){return id==='three'?THREE:load(id.replace('./',''));}});return exports;}
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const {EntityRegistry}=load('entity-registry'),{SpatialMasks}=load('spatial-masks'),{pickEntity}=load('entity-picking');
const registry=new EntityRegistry(read(root+'/public/data/entity-registry.json'));
const existing=[...read(root+'/public/data/picking/building-domains.json').domains,...read(root+'/public/data/picking/building-domains-extra.json').domains];
const fixture=read(stage+'/ug3-domain-fixtures.json');
const replacement=existing.filter(d=>d.entityId===fixture.priorDomain.entityId && d.sourceBuildingId===fixture.priorDomain.sourceBuildingId);
assert.equal(replacement.length,1,'UG III must have one complete cross-sheet record');
assert.equal(replacement[0].parts.length,2,'Both source sheet polygons must remain');
assert.equal(replacement[0].completeAcrossSavedSheetEdges,true);
const beforeDomains=existing.map(d=>d===replacement[0]?fixture.priorDomain:d);
const upgraded=existing;
const footprints=read(root+'/public/data/building-footprints.json').footprints,grid=read(root+'/public/terrain/height-grid-5m.json');
for (const sample of fixture.cases) assert.equal(createHash('sha256').update(fs.readFileSync(root+'/public'+sample.sourceGltf)).digest('hex'),sample.sourceGltfSha256);
const results=[];
for(const sample of fixture.cases){
 for(const role of ['baseline','photogrammetry']){
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(sample.worldTriangle.flat(),3));geometry.computeVertexNormals();const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));
  const center=new THREE.Vector3(...sample.point),normal=new THREE.Vector3(...sample.normal),ray=new THREE.Raycaster(center.clone().addScaledVector(normal,2),normal.clone().negate());
  const masks=new SpatialMasks();masks.apply(mesh,role);const context={registry,footprints,roots:[mesh],masks,groundAt:(x,z)=>sampleTerrainLocalHeight(grid,x,z),buildingDomains:beforeDomains};
  const before=pickEntity(ray,context),after=pickEntity(ray,{...context,buildingDomains:upgraded});
  assert.equal(before.entityId,undefined);assert.equal(after.entityId,sample.entityId);assert.equal(after.method,'source-footprint-and-height');
  results.push({role,faceClass:sample.faceClass,sourceTriangleIndex:sample.sourceTriangleIndex,point:sample.point,groundY:sampleTerrainLocalHeight(grid,sample.point[0],sample.point[2]),before:before.method,after:after.method,entityId:after.entityId});
  geometry.dispose();mesh.material.dispose();masks.dispose();
 }
}
const report={status:'pass',cases:results.length,actualSourceTriangles:fixture.cases.length,sourceDomainAreaBefore:fixture.sourceDomainAreaBefore,sourceDomainAreaAfter:fixture.sourceDomainAreaAfter,addedSourceDomainArea:fixture.addedSourceDomainArea,scope:'Actual current entity-picking/SpatialMasks modules, actual registry and5m DTM samples, original glTF source triangle fixtures. Before uses the retained prior clipped domain; after reads the installed exact 6A+6C domain. No browser acceptance claimed.',results};
fs.writeFileSync(stage+'/ug3-domain-qa.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({...report,results:results.length},null,2));
