// Actual representation geometry and scene selection handlers; no browser acceptance claim.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
const root=new URL('../',import.meta.url),cache=new Map();
function load(name){if(cache.has(name))return cache.get(name);const exports={};cache.set(name,exports);const code=ts.transpileModule(fs.readFileSync(new URL('app/'+name+'.ts',root),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInNewContext(code,{exports,require:id=>id==='three'?THREE:load(id.replace('./','')),console,Map,Set,WeakMap,Float32Array});return exports;}
const {createBuildingSelection}=load('building-selection');
const {releaseObject}=load('resources');
const {exteriorEntityId}=load('source-types');
const results=[];function check(name,fn){const detail=fn();results.push({name,detail});}
function assetGroup(path){
 const bytes=fs.readFileSync(new URL(path,root)),jsonLength=bytes.readUInt32LE(12),g=JSON.parse(bytes.subarray(20,20+jsonLength).toString()),binary=bytes.subarray(28+jsonLength);
 function accessor(i){const a=g.accessors[i],v=g.bufferViews[a.bufferView],n={SCALAR:1,VEC2:2,VEC3:3}[a.type],out=new Float32Array(a.count*n),base=(v.byteOffset||0)+(a.byteOffset||0),stride=v.byteStride||n*4;assert.equal(a.componentType,5126);for(let row=0;row<a.count;row++)for(let col=0;col<n;col++)out[row*n+col]=binary.readFloatLE(base+row*stride+col*4);return out;}
 function node(i){const n=g.nodes[i],o=new THREE.Group();o.name=n.name||'';o.userData={...n.extras};if(n.matrix)o.applyMatrix4(new THREE.Matrix4().fromArray(n.matrix));if(n.mesh!==undefined){for(const pr of g.meshes[n.mesh].primitives){const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(accessor(pr.attributes.POSITION),3));assert.equal(pr.indices,undefined);const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial());mesh.name=o.name;mesh.userData={...o.userData};o.add(mesh);}}for(const child of n.children||[])o.add(node(child));return o;}
 const group=new THREE.Group();for(const i of g.scenes[g.scene||0].nodes)group.add(node(i));return group;
}
const manifest=JSON.parse(fs.readFileSync(new URL('public/models/current-forms/halls-current/manifest.json',root),'utf8'));
const halls=manifest.buildings.map(b=>({descriptor:b,root:assetGroup('public/models/current-forms/halls-current/'+b.url)}));
check('three actual current hall outlines use envelope geometry, source heights and depth testing',()=>halls.map(({descriptor:b,root:group})=>{
 const line=createBuildingSelection([{root:group,kind:'current-form'}]);assert.ok(line);
 assert.equal(line.material.depthTest,true);assert.equal(line.material.depthWrite,false);
 assert.ok(line.userData.representedMeshes.every(n=>!n.includes('pv-')&&!n.includes('shade')&&!n.includes('source-floor')));
 const pos=line.geometry.getAttribute('position'),ys=new Set();for(let i=0;i<pos.count;i++)ys.add(pos.getY(i).toFixed(3));assert.ok(ys.size>5);assert.ok(![...ys].every(y=>Number(y)===156.2));
 const box=new THREE.Box3().setFromObject(line);assert.ok(box.max.y>160);assert.ok(box.max.y<=b.bounds.max[1]+.001);assert.ok(box.min.y>=b.bounds.min[1]-.001);
 const facts={catalogId:b.catalogId,edges:pos.count/2,representedMeshes:line.userData.representedMeshes,sourceHeightLevels:ys.size,bounds:{min:box.min.toArray(),max:box.max.toArray()}};releaseObject(line);return facts;
}));
check('coplanar subdivisions produce perimeter only and preserve parent world transform',()=>{
 const geometry=new THREE.PlaneGeometry(12,8,6,4),mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial());mesh.userData.geometryRole='approximate_facade';const group=new THREE.Group();group.add(mesh);group.position.set(10,20,-30);const source=geometry.getAttribute('position').array.slice();const line=createBuildingSelection([{root:group,kind:'current-form'}]);assert.ok(line);
 const pos=line.geometry.getAttribute('position');for(let i=0;i<pos.count;i++){const x=pos.getX(i)-10,y=pos.getY(i)-20;assert.ok(Math.abs(Math.abs(x)-6)<1e-5||Math.abs(Math.abs(y)-4)<1e-5);assert.equal(pos.getZ(i),-30);}assert.deepEqual(geometry.getAttribute('position').array,source);releaseObject(line);assert.ok(geometry.getAttribute('position').count>0);return {edges:pos.count/2};
});
check('hidden parts, interior source-floor meshes and photographic supplements do not make current boundaries',()=>{
 const group=new THREE.Group();for(const role of ['exact_source_floor_parts','approximate_exterior_band']){const m=new THREE.Mesh(new THREE.BoxGeometry(2,3,4),new THREE.MeshBasicMaterial());m.name=role;m.userData.representationRole=role;group.add(m);}
 group.children[1].visible=false;assert.equal(createBuildingSelection([{root:group,kind:'current-form'}]),null);group.children[1].visible=true;const line=createBuildingSelection([{root:group,kind:'current-form'}]);assert.deepEqual([...line.userData.representedMeshes],['approximate_exterior_band']);releaseObject(line);const hiddenParent=new THREE.Group();hiddenParent.visible=false;hiddenParent.add(group);assert.equal(createBuildingSelection([{root:group,kind:'current-form'}]),null);hiddenParent.visible=true;group.userData.sourceRole='source-photogrammetry-gap-surface';assert.equal(createBuildingSelection([{root:group,kind:'source'}]),null);
});
const sceneSource=fs.readFileSync(new URL('app/scene.ts',root),'utf8'),ast=ts.createSourceFile('scene.ts',sceneSource,ts.ScriptTarget.Latest,true);
function method(name,owner){let found;const visit=n=>{if(ts.isMethodDeclaration(n)&&n.name.getText(ast)===name)found=n;ts.forEachChild(n,visit);};visit(ast);assert.ok(found);const compiled={exports:{}};vm.runInNewContext(ts.transpileModule('module.exports=({'+found.getText(ast)+'}).'+name,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,{module:compiled,THREE,createBuildingSelection,releaseObject,exteriorEntityId});return compiled.exports.bind(owner);}
const b=halls[2].descriptor,entity={entityId:b.entityId,type:'building'},source=halls[2].root;source.userData.buildingId=b.buildingId;
const owner={selectedId:b.entityId,registry:{get:id=>id===entity.entityId?entity:undefined,buildingSource:()=>b.buildingId},selection:new THREE.Group(),updates:new THREE.Group(),exteriors:{visible:new Map()},masks:{apply(){}},opened:null,interior:{selected:'room:old',select(id){this.selected=id;}},setNavigationMode(){},notify(){this.updateBuildingSelection();}};owner.updates.add(source);
for(const name of ['updateBuildingSelection','clearSelection','selectEntity'])owner[name]=method(name,owner);
check('selection refresh is atomic on current representation arrival, hidden/opened and repeat selection',()=>{
 owner.updateBuildingSelection();assert.equal(owner.selection.children.length,1);const first=owner.selection.children[0];owner.updateBuildingSelection();assert.equal(owner.selection.children[0],first);
 releaseObject(owner.selection);owner.selection.clear();owner.updateBuildingSelection();assert.equal(owner.selection.children.length,1);assert.notEqual(owner.selection.children[0],first);
 owner.opened=entity;owner.updateBuildingSelection();assert.equal(owner.selection.children.length,0);owner.opened=null;owner.updateBuildingSelection();assert.equal(owner.selection.children.length,1);
 source.visible=false;owner.updateBuildingSelection();assert.equal(owner.selection.children.length,0);source.visible=true;owner.updateBuildingSelection();assert.equal(owner.selection.children.length,1);
});
await owner.selectEntity('');
check('selectEntity empty id clears world and interior selection while leaving source geometry intact',()=>{
 assert.equal(owner.selectedId,'');assert.equal(owner.selection.children.length,0);assert.equal(owner.interior.selected,'');assert.equal(owner.updates.children[0],source);assert.ok(new THREE.Box3().setFromObject(source).max.y>170);
});
const fp=JSON.parse(fs.readFileSync(new URL('public/data/building-footprints.json',root),'utf8')).footprints.find(f=>f.catalogId==='ug-hall-13');
const report={status:'pass',checks:results.length,previousFailure:{entityId:b.entityId,source:'official all-base-map multipart building drawing; not an as-built roof',parts:fp.parts.length,rings:fp.parts.reduce((n,p)=>n+p.rings.length,0),vertices:fp.parts.reduce((n,p)=>n+p.rings.reduce((a,r)=>a+r.length,0),0),oldUniformY:fp.maxObservedFloorZ+.2,depthTestWasFalse:true,cardClosePreviouslyOnlyClearedReact:true},results,sourceSha256:Object.fromEntries(['app/building-selection.ts','app/scene.ts','app/page.tsx'].map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(new URL(p,root))).digest('hex')])),limitations:['Actual asset geometry and current source handlers are tested. Real browser line visibility and card/keyboard interactions require separate runtime acceptance.','Fallback without a loaded attributable building representation deliberately has no invented roof line; entity selection and labels remain available.']};
fs.writeFileSync(new URL('docs/source-evidence-v4/building-selection-tests.json',root),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,checks:report.checks,previousFailure:report.previousFailure,actualHalls:results[0].detail.map(b=>({catalogId:b.catalogId,edges:b.edges}))},null,2));
