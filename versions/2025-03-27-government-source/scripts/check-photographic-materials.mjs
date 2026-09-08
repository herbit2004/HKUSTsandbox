import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';

const root = new URL('../', import.meta.url), exports = {};
const source = fs.readFileSync(new URL('app/photographic-materials.ts', root), 'utf8');
vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,
  {exports, require:name=>{assert.equal(name,'three');return THREE;}});
const {preparePhotographicMaterials} = exports;
const map = new THREE.Texture(), alpha = new THREE.Texture();
const original = new THREE.MeshStandardMaterial({map,alphaMap:alpha,
  color:new THREE.Color(.37,.51,.68),vertexColors:true,opacity:.6,transparent:true,
  alphaTest:.25,side:THREE.DoubleSide,depthWrite:false,toneMapped:false,
  polygonOffset:true,polygonOffsetFactor:2,polygonOffsetUnits:3});
original.userData = {source:'controlled-original-photo'};
let oldDisposals = 0; original.addEventListener('dispose',()=>oldDisposals++);
const geometry = new THREE.BufferGeometry();
const colors = new THREE.Float32BufferAttribute([.52,.52,.52, .71,.71,.71, 1,1,1],3);
geometry.setAttribute('color',colors);
const alreadyUnlit = new THREE.MeshBasicMaterial({map,vertexColors:true});
const untextured = new THREE.MeshStandardMaterial({color:.6});
const baked = new THREE.MeshStandardMaterial({color:new THREE.Color(.4,.42,.43),vertexColors:true});
baked.userData.campusBakedLighting = true;
const group = new THREE.Group();
group.add(new THREE.Mesh(geometry,[original,alreadyUnlit]),new THREE.Mesh(geometry,original),new THREE.Mesh(geometry,untextured),new THREE.Mesh(geometry,baked));
preparePhotographicMaterials(group,4);
const converted = group.children[1].material;
const bakedConverted = group.children[3].material;
assert.ok(converted instanceof THREE.MeshBasicMaterial);
assert.equal(group.children[0].material[0],converted);
assert.equal(group.children[0].material[1],alreadyUnlit);
assert.equal(group.children[2].material,untextured);
assert.ok(bakedConverted instanceof THREE.MeshBasicMaterial);
assert.equal(bakedConverted.map,null);
assert.equal(bakedConverted.vertexColors,true);
assert.equal(bakedConverted.userData.runtimeAppearance,'unlit-baked-current-form');
assert.deepEqual(bakedConverted.color.toArray(),baked.color.toArray());
assert.equal(converted.map,map);assert.equal(converted.alphaMap,alpha);
assert.equal(converted.vertexColors,true);assert.equal(geometry.attributes.color,colors);
assert.deepEqual(converted.color.toArray(),original.color.toArray());
for(const field of ['side','transparent','opacity','alphaTest','depthTest','depthWrite','toneMapped','polygonOffset','polygonOffsetFactor','polygonOffsetUnits'])
  assert.equal(converted[field],original[field],field);
assert.equal(converted.userData.source,original.userData.source);
assert.equal(map.anisotropy,4);assert.equal(map.minFilter,THREE.LinearMipmapLinearFilter);
assert.equal(oldDisposals,1);
preparePhotographicMaterials(group,4);
assert.equal(group.children[1].material,converted);assert.equal(oldDisposals,1);
const calibrated=new THREE.MeshBasicMaterial({map,vertexColors:true});
calibrated.userData.campusPhotoCalibration={saturation:.45,exposure:.96,linearTint:[1.05,.95,1]};
let inherited=0;calibrated.onBeforeCompile=()=>inherited++;
const photoRoot=new THREE.Group();photoRoot.add(new THREE.Mesh(geometry,calibrated));
preparePhotographicMaterials(photoRoot,4);preparePhotographicMaterials(photoRoot,4);
const shader={uniforms:{},fragmentShader:THREE.ShaderLib.basic.fragmentShader,vertexShader:THREE.ShaderLib.basic.vertexShader};
calibrated.onBeforeCompile(shader,{});
assert.equal(inherited,1);assert.equal(shader.uniforms.campusPhotoSaturation.value,.45);
assert.equal(shader.uniforms.campusPhotoExposure.value,.96);
assert.deepEqual(shader.uniforms.campusPhotoTint.value.toArray(),[1.05,.95,1]);
assert.equal(shader.fragmentShader.match(/float campusPhotoLuminance =/g).length,1);
assert.ok(shader.fragmentShader.indexOf('float campusPhotoLuminance =')<shader.fragmentShader.indexOf('#include <color_fragment>'));
assert.equal(calibrated.vertexColors,true);
const plainShader={uniforms:{},fragmentShader:THREE.ShaderLib.basic.fragmentShader};alreadyUnlit.onBeforeCompile(plainShader,{});
assert.equal(plainShader.fragmentShader,THREE.ShaderLib.basic.fragmentShader);
const report={status:'pass',checks:[
  'Shared mapped PBR material converted once, original disposed once',
  'Existing unlit photographic materials and shared textures retain identity',
  'Baked COLOR_0 values and enablement preserved during conversion',
  'Linear base colour, alpha, depth and polygon offset settings preserved',
  'Device anisotropy respected; repeated preparation is idempotent',
  'Unmapped material is unchanged',
  'Explicit baked current-form material uses its vertex lighting without a second PBR light pass',
  'Data-driven source colour calibration runs once before baked vertex lighting',
  'Native uncalibrated photographic material shader remains unchanged'],visualAcceptance:false};
fs.writeFileSync(new URL('docs/source-evidence-v4/photographic-material-tests.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
