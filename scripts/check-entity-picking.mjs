// Actual checked-in TS, real source triangle fixtures, and controlled negative cases.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';
import * as ts from 'typescript';
import * as THREE from 'three';
import { runNamedBuildingPickingChecks } from './named-building-picking-checks.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)), compiled=new Map();
function compile(name){if(compiled.has(name))return compiled.get(name);const exports={};compiled.set(name,exports);
  const code=ts.transpileModule(fs.readFileSync(root+'app/'+name+'.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,require(id){return id==='three'?THREE:compile(id.replace('./',''));},Uint8Array,Map,Set,WeakMap,Math,Number,Error});return exports;}
const {SpatialMasks}=compile('spatial-masks'), {EntityRegistry}=compile('entity-registry');
const {exteriorEntityId}=compile('source-types');
const {pickEntity,isVisibleSurfaceHit,insideSourceFootprint,exteriorSourceOwner}=compile('entity-picking');
const json=p=>JSON.parse(fs.readFileSync(root+p,'utf8'));
const registry=new EntityRegistry(json('public/data/entity-registry.json'));
const footprints=json('public/data/building-footprints.json').footprints;
function readPng(path){const b=fs.readFileSync(path);let width,height,channels;const chunks=[];for(let at=8;at<b.length;){const n=b.readUInt32BE(at),kind=b.toString('ascii',at+4,at+8),d=b.subarray(at+8,at+8+n);at+=12+n;if(kind==='IHDR'){width=d.readUInt32BE(0);height=d.readUInt32BE(4);assert.equal(d[8],8);channels={0:1,2:3,6:4}[d[9]];assert.ok(channels);assert.equal(d[12],0);}if(kind==='IDAT')chunks.push(d);}const packed=zlib.inflateSync(Buffer.concat(chunks)),stride=width*channels,data=new Uint8Array(width*height*channels);let at=0;for(let y=0;y<height;y++){const filter=packed[at++];for(let x=0;x<stride;x++){const i=y*stride+x,a=x>=channels?data[i-channels]:0,b=y?data[i-stride]:0,c=x>=channels&&y?data[i-stride-channels]:0,p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c),predict=filter===0?0:filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):pa<=pb&&pa<=pc?a:pb<=pc?b:c;data[i]=(packed[at++]+predict)&255;}}const rgba=new Uint8Array(width*height*4);for(let i=0;i<width*height;i++){rgba[i*4]=data[i*channels];rgba[i*4+1]=channels===1?data[i]:data[i*channels+1];rgba[i*4+2]=channels===1?data[i]:data[i*channels+2];rgba[i*4+3]=channels===4?data[i*4+3]:255;}return {width,height,rgba};}
const results=[];
function check(name,fn){fn();results.push({name,status:'pass'});}
function mesh(points){const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));geometry.computeVertexNormals();return new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));}
function horizontal(x,y,z,size=1){return mesh([[x-size,y,z-size],[x,y,z+size],[x+size,y,z-size]]);}
function hitFor(m,p,normal=[0,1,0]){m.updateWorldMatrix(true,true);return {object:m,point:new THREE.Vector3(...p),face:{normal:new THREE.Vector3(...normal),materialIndex:0},distance:1};}
function setMask(masks,name,rgba,bounds=[-2,-2,2,2]){const texture=new THREE.DataTexture(new Uint8Array(rgba),1,1);masks.set(name,texture,bounds);}
const previousNamedDomains=json('public/data/picking/building-domains.json').domains;
const extraNamedDomains=json('public/data/picking/building-domains-extra.json');
const namedDomains=[...previousNamedDomains,...extraNamedDomains.domains];
const listOnlyIds=[
  'building:catalog:campus-20',
  'building:catalog:campus-27',
  'building:catalog:ug-hall-8',
  'building:catalog:ug-hall-9',
];
const listOnlyAudit=[];
function context(roots,masks=new SpatialMasks()){return {registry,footprints,buildingDomains:namedDomains,roots,masks,groundAt:()=>0};}
const academic='building:b00000000000000000000001', innovation='building:69201b741c838d03d9fbe71b';

check('all actual official holes reject their interior; outer edges are not AABB-expanded',()=>{
  const rings=[[[0,0],[10,0],[10,10],[0,10],[0,0]],[[3,3],[7,3],[7,7],[3,7],[3,3]]];
  assert.equal(insideSourceFootprint(1,1,rings),true);assert.equal(insideSourceFootprint(5,5,rings),false);assert.equal(insideSourceFootprint(10.01,5,rings),false);assert.equal(insideSourceFootprint(10,5,rings),true);
});
check('hidden parent and non-visible materials reject ray hits',()=>{const m=horizontal(0,10,0),group=new THREE.Group();group.add(m);group.visible=false;const masks=new SpatialMasks();assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),false);group.visible=true;m.material.visible=false;assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),false);});
check('wireframe/near-transparent helpers do not intercept entity or PAN anchors',()=>{const m=horizontal(0,10,0),masks=new SpatialMasks();m.material.wireframe=true;assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),false);m.material.wireframe=false;m.material.opacity=.01;assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),false);});
check('baseline R discards, new photogrammetry uses independent Academic G',()=>{const masks=new SpatialMasks();setMask(masks,'replacement',[255,0,0,255]);masks.setPhotogrammetryCore('replacement',true);const baseline=horizontal(0,10,0),fine=horizontal(0,10,0);masks.apply(baseline,'baseline');masks.apply(fine,'photogrammetry');assert.equal(isVisibleSurfaceHit(hitFor(baseline,[0,10,0]),masks),false);assert.equal(isVisibleSurfaceHit(hitFor(fine,[0,10,0]),masks),true);masks.setPhotogrammetryCore('replacement',false);assert.equal(isVisibleSurfaceHit(hitFor(fine,[0,10,0]),masks),false);});
check('ground reference preserves near-DTM sloped source ground but never a wall',()=>{const masks=new SpatialMasks();setMask(masks,'replacement',[255,0,0,255]);setMask(masks,'groundReference',[255,10,0,255]);masks.slots.groundReference.heightClearance.value=1;const m=horizontal(0,10,0);masks.apply(m,'baseline');assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10.5,0]),masks),true);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10.5,0],[1,0,0]),masks),false);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,12,0]),masks),false);});
check('partial coverage cuts old baseline/supplement and never its new photogrammetry',()=>{const masks=new SpatialMasks();setMask(masks,'partialCoverage',[255,0,0,255]);for(const role of ['baseline','supplement','photogrammetry']){const m=horizontal(0,10,0);masks.apply(m,role);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),role==='photogrammetry');}});
check('surface encoded height removes ground competition and preserves canopy',()=>{const masks=new SpatialMasks();masks.setSurface('surface2',new THREE.DataTexture(new Uint8Array([255,10,128,255]),1,1),[-2,-2,2,2],1.75);const m=horizontal(0,10,0);masks.apply(m,'baseline');assert.equal(isVisibleSurfaceHit(hitFor(m,[0,12.2,0]),masks),false);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,12.3,0]),masks),true);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,12.2,0],[1,0,0]),masks),true);});
check('opening height and outside-raster clipping match current slots',()=>{const masks=new SpatialMasks();setMask(masks,'opening',[255,0,0,255]);masks.slots.opening.minY.value=10;const m=horizontal(0,10,0);masks.apply(m,'exterior');assert.equal(isVisibleSurfaceHit(hitFor(m,[0,9,0]),masks),true);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,10,0]),masks),false);assert.equal(isVisibleSurfaceHit(hitFor(m,[3,20,0]),masks),true);masks.enable('opening',false);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,20,0]),masks),true);});
check('terrain coverage fallback and source ground use the shader OR condition',()=>{const masks=new SpatialMasks();setMask(masks,'coverage',[255,0,0,255]);const m=horizontal(0,0,0);masks.apply(m,'terrain');assert.equal(isVisibleSurfaceHit(hitFor(m,[0,0,0]),masks),false);setMask(masks,'replacement',[255,0,0,255]);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,0,0]),masks),true);setMask(masks,'groundReference',[255,0,0,255]);assert.equal(isVisibleSurfaceHit(hitFor(m,[0,0,0]),masks),false);});
check('only marked current-form cleanup pixels hand photography to terrain',()=>{const masks=new SpatialMasks();setMask(masks,'coverage',[255,0,0,255]);setMask(masks,'currentForms',[255,255,255,140]);const terrain=horizontal(0,0,0),source=horizontal(0,150,0);masks.apply(terrain,'terrain');masks.apply(source,'photogrammetry');masks.slots.currentForms.minY.value=129;masks.slots.currentForms.maxY.value=256;masks.slots.currentForms.heightEncoded.value=2;assert.equal(isVisibleSurfaceHit(hitFor(terrain,[0,0,0]),masks),true);assert.equal(isVisibleSurfaceHit(hitFor(source,[0,150,0]),masks),false);assert.equal(isVisibleSurfaceHit(hitFor(source,[0,139,0]),masks),true);setMask(masks,'currentForms',[255,179,0,140]);assert.equal(isVisibleSurfaceHit(hitFor(terrain,[0,0,0]),masks),false);});
check('retired baseline is skipped, then current explicit mesh wins the same ray',()=>{const masks=new SpatialMasks(),old=horizontal(0,12,0),current=horizontal(0,10,0);masks.apply(old,'baseline');setMask(masks,'replacement',[255,0,0,255]);current.userData.entityId=innovation;const ray=new THREE.Raycaster(new THREE.Vector3(0,20,0),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,context([old,current],masks)).entityId,innovation);});
check('explicit source owner binds roofs and walls outside drawing edge without tile ownership',()=>{for(const points of [[[0,10,-1],[0,12,0],[0,10,1]],[[-1,10,-1],[0,10,1],[1,10,-1]]]){const m=mesh(points),group=new THREE.Group();group.add(m);const c=context([group]);c.owners=new Map([[group,academic]]);const center=new THREE.Vector3(...points[0]).add(new THREE.Vector3(...points[1])).add(new THREE.Vector3(...points[2])).divideScalar(3),normal=new THREE.Vector3().crossVectors(new THREE.Vector3(...points[1]).sub(new THREE.Vector3(...points[0])),new THREE.Vector3(...points[2]).sub(new THREE.Vector3(...points[0]))).normalize();const ray=new THREE.Raycaster(center.clone().addScaledVector(normal,2),normal.negate());assert.equal(pickEntity(ray,c).entityId,academic);}});
check('aggregate source ownership selects the declared zone without inventing a member owner',()=>{const body=new THREE.Group();body.userData.sourceObjectId='joint-envelope';body.userData.sourceOwnership='aggregate-source';assert.equal(exteriorSourceOwner(body,'zone:test:joint',[]),'zone:test:joint');assert.equal(exteriorSourceOwner(body,'zone:test:joint',[{sourceObjectId:'joint-envelope',entityId:'building:test:member'}]),'zone:test:joint');});
check('specific coincident room beats canonical floor/building',()=>{const a=horizontal(0,10,0),b=horizontal(0,10,0);a.userData.entityId=academic;b.userData.entityId='space:catalog:campus-04';const ray=new THREE.Raycaster(new THREE.Vector3(0,20,0),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,context([a,b])).entityId,'space:catalog:campus-04');});
check('opaque unassigned foreground surface blocks deeper building selection',()=>{const tree=horizontal(0,12,0),building=horizontal(0,10,0);building.userData.entityId=academic;const ray=new THREE.Raycaster(new THREE.Vector3(0,20,0),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,context([tree,building])).entityId,undefined);});

check('six list-only canonical buildings stay unbound without a measured source domain',()=>{
  const manifest=json('public/models/exteriors/manifest.json');
  const currentFormSets=[
    'public/models/current-forms/innovation/manifest.json',
    'public/models/current-forms/ivillage-rebuild/manifest.json',
    'public/models/current-forms/halls-current/manifest.json',
  ].map(json);
  for(const entityId of listOnlyIds){
    const entity=registry.get(entityId);assert.equal(entity?.type,'building',entityId);
    const footprintCount=footprints.filter(f=>'building:'+f.officialBuildingId===entityId).length;
    const namedDomainCount=namedDomains.filter(d=>d.entityId===entityId).length;
    const exteriorBundles=manifest.bundles.filter(b=>exteriorEntityId(b)===entityId).map(b=>b.id);
    const currentForms=currentFormSets.flatMap(set=>(set.members||set.buildings||[]).filter(m=>m.entityId===entityId).map(m=>m.entityId));
    const representationTypes=entity.representations.map(r=>r.type);
    assert.equal(footprintCount,0,entityId);
    assert.equal(namedDomainCount,0,entityId);
    assert.deepEqual(exteriorBundles,[],entityId);
    assert.deepEqual(currentForms,[],entityId);
    assert.ok(representationTypes.length===0||representationTypes.every(type=>type==='reference_point'),`${entityId} has non-reference representation`);
    const sharedMemberOf=entity.relations.filter(r=>r.type==='sharesExteriorWith').map(r=>r.targetId);
    listOnlyAudit.push({entityId,name:entity.name,representationTypes,footprintCount,namedDomainCount,exteriorBundles,currentForms,sharedMemberOf,disposition:'no-safe-direct-building-owner'});
  }
  assert.deepEqual(listOnlyAudit.map(x=>x.entityId),listOnlyIds);
  const sharedZoneId='zone:hkust-cwb:ug-halls-8-9', shared=manifest.bundles.find(b=>b.id==='ug-halls-8-9-shared-source');
  assert.ok(shared, 'shared UG VIII/IX source bundle missing');
  assert.equal(exteriorEntityId(shared),sharedZoneId);
  assert.equal(shared.objects.length,1);
  assert.equal(shared.objects[0].ownership,'aggregate-source');
  assert.deepEqual(shared.memberEntityIds.toSorted(),['building:catalog:ug-hall-8','building:catalog:ug-hall-9']);
});

const sharedSourceDomainRays=[];
check('actual shared Staff lower body resolves both recorded domains and leaves its outside terrace unassigned',()=>{
  const fixture=json('docs/source-evidence-v4/building-quality/staff-domain-only-ray-fixtures.json');
  const manifest=json('public/models/exteriors/manifest.json');
  const bundle=manifest.bundles.find(b=>b.id==='staff-quarters-tower-3');
  const object=bundle.objects.find(o=>o.id===fixture.sourceObjectId);
  assert.equal(object.ownership,'domain-only');
  for(const file of fixture.sourceFiles){
    const sourcePath=root+'public/models/exteriors/objects/'+fixture.sourceObjectId+'/'+file.filename;
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(sourcePath)).digest('hex'),file.sha256);
  }
  for(const sample of fixture.fixtures){
    const body=new THREE.Group(),triangle=mesh(sample.triangleLocalXYZ);body.add(triangle);
    body.userData.sourceObjectId=object.id;body.userData.sourceOwnership=object.ownership;
    const owner=exteriorSourceOwner(body,'building:'+bundle.buildingId,extraNamedDomains.sourceObjectOwners);
    assert.equal(owner,undefined);
    const ctx=context([body]);ctx.groundAt=()=>sample.runtimeGrid5mGroundY;ctx.owners=new Map();
    if(owner)ctx.owners.set(body,owner);
    ctx.masks.apply(body,'exterior');
    const result=pickEntity(new THREE.Raycaster(new THREE.Vector3(...sample.ray.origin),new THREE.Vector3(...sample.ray.direction)),ctx);
    assert.equal(result?.entityId??null,sample.expectedDomainEntityId);
    assert.equal(result?.method,sample.expectedDomainEntityId?'source-footprint-and-height':'unassigned-visible-surface');
    assert.ok(result.hit.point.distanceTo(new THREE.Vector3(...sample.centroidLocalXYZ))<.0001);
    sharedSourceDomainRays.push({sourceObjectId:object.id,triangleIndex:sample.triangleIndex,entityId:result.entityId??null,method:result.method,sourceSurfaceMinusDtmMeters:sample.sourceSurfaceMinusDtmMeters});
  }
});

const source=json('docs/source-evidence-v4/entity-picking/source-triangle-fixtures.json');
const actual=[];
for(const sample of source.cases){const m=mesh(sample.worldTriangle),center=new THREE.Vector3(...sample.point);const [a,b,c]=sample.worldTriangle.map(p=>new THREE.Vector3(...p));const normal=new THREE.Vector3().crossVectors(b.clone().sub(a),c.clone().sub(a)).normalize();const ray=new THREE.Raycaster(center.clone().addScaledVector(normal,2),normal.clone().negate());const ctx=context([m]);ctx.groundAt=()=>sample.groundY;ctx.masks.apply(m,sample.representation==='fine'?'photogrammetry':'baseline');const picked=pickEntity(ray,ctx);const shared=extraNamedDomains.domains.filter(d=>d.sharedPhysicalEnvelopeWith===sample.entityId&&d.parts.some(p=>insideSourceFootprint(sample.point[0],sample.point[2],p.rings)));const expected=shared.length===1?shared[0].entityId:sample.entityId;assert.equal(picked?.entityId,expected,JSON.stringify(sample));actual.push({entityId:expected,originalFixtureEntityId:sample.entityId,representation:sample.representation,faceClass:sample.faceClass,method:picked.method});}
results.push({name:'actual source roof/wall triangle rays, source transforms and official polygons',status:'pass',cases:actual.length,buildings:new Set(actual.map(x=>x.entityId)).size});

// Ground at the exact same source-domain XZ must not become a building owner.
check('real-footprint near-DTM horizontal surfaces never acquire building ID',()=>{for(const sample of source.cases.filter(x=>x.faceClass==='roof')){const m=horizontal(sample.point[0],sample.groundY,sample.point[2],.02);const ray=new THREE.Raycaster(new THREE.Vector3(sample.point[0],sample.groundY+2,sample.point[2]),new THREE.Vector3(0,-1,0));const c=context([m]);c.groundAt=()=>sample.groundY;assert.equal(pickEntity(ray,c)?.entityId,undefined);}});
check('actual Academic R/G mask pixels keep source row order for clicks and PAN',()=>{const manifest=json('public/models/exteriors/manifest.json'),bundle=manifest.bundles.find(x=>x.id==='campus-01'),bounds=bundle.mask.boundsXZ, p=readPng(root+'public/models/exteriors/'+bundle.mask.url), masks=new SpatialMasks();masks.set('replacement',new THREE.DataTexture(p.rgba,p.width,p.height),[...bounds.min,...bounds.max]);masks.setPhotogrammetryCore('replacement',true);const a=horizontal(0,300,0),b=horizontal(0,300,0);masks.apply(a,'baseline');masks.apply(b,'photogrammetry');for(let k=0;k<2000;k++){const i=(k*7919)%(p.width*p.height),col=i%p.width,row=Math.floor(i/p.width),point=[bounds.min[0]+(col+.5)*(bounds.max[0]-bounds.min[0])/p.width,300,bounds.min[1]+(row+.5)*(bounds.max[1]-bounds.min[1])/p.height];assert.equal(isVisibleSurfaceHit(hitFor(a,point),masks),p.rgba[i*4]<=127);assert.equal(isVisibleSurfaceHit(hitFor(b,point),masks),p.rgba[i*4+1]<=127);}});
check('source polygon overlap refuses arbitrary first-building ownership',()=>{const point=[712.6175219801734,160.32120615988882,-1099.2964068659778],m=horizontal(...point,.1),ray=new THREE.Raycaster(new THREE.Vector3(point[0],170,point[2]),new THREE.Vector3(0,-1,0)),c=context([m]);c.groundAt=()=>144.0326256804001;const picked=pickEntity(ray,c);assert.equal(picked.entityId,undefined);assert.equal(picked.method,'ambiguous-source-footprints');});
const domains=json('public/surfaces/entrance/entity-picking-domains.json');
check('actual immersive plaza platform source point selects Piazza from a fine hit',()=>{const p=[331.073794,121.988728,-1556.444185],m=horizontal(...p,.1),ctx=context([m]);ctx.masks.apply(m,'photogrammetry');ctx.groundAt=()=>121.8;ctx.surfaces=domains.groundSurfaces;const ray=new THREE.Raycaster(new THREE.Vector3(p[0],p[1]+2,p[2]),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,ctx)?.entityId,'outdoor_area:catalog:campus-61');});
check('actual old photographic sculpture point shares red-bird canonical ID locally',()=>{const p=[336.27203,124.25547,-1549.63852],m=horizontal(...p,.01),ctx=context([m]);ctx.masks.apply(m,'photogrammetry');ctx.groundAt=()=>121.7;ctx.sourceAssociations=domains.sourceAssociations;const ray=new THREE.Raycaster(new THREE.Vector3(p[0],p[1]+2,p[2]),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,ctx)?.entityId,'facility:hkust-cwb:red-bird-sundial');m.position.x=10;ray.ray.origin.x+=10;assert.notEqual(pickEntity(ray,ctx)?.entityId,'facility:hkust-cwb:red-bird-sundial');m.position.x=0;m.position.y=10;ray.ray.origin.x-=10;ray.ray.origin.y+=10;assert.notEqual(pickEntity(ray,ctx)?.entityId,'facility:hkust-cwb:red-bird-sundial');});
check('official swimming pool parts resolve the same outdoor entity on source surfaces',()=>{const fp=footprints.find(f=>f.officialBuildingId==='691590cf9d35c2555798e299');assert.ok(fp);let p;for(const part of fp.parts){for(const a of part.rings[0]){const center=part.rings[0].reduce((s,v)=>[s[0]+v[0]/part.rings[0].length,s[1]+v[1]/part.rings[0].length],[0,0]),q=[a[0]*.9+center[0]*.1,a[1]*.9+center[1]*.1];if(insideSourceFootprint(q[0],q[1],part.rings)){p=q;break;}}if(p)break;}assert.ok(p);const m=horizontal(p[0],24.6,p[1],.01),c=context([m]);c.surfaces=[{entityId:'outdoor_area:691590cf9d35c2555798e299',parts:fp.parts}];c.groundAt=()=>24.5;const ray=new THREE.Raycaster(new THREE.Vector3(p[0],30,p[1]),new THREE.Vector3(0,-1,0));assert.equal(pickEntity(ray,c)?.entityId,'outdoor_area:691590cf9d35c2555798e299');});
const exteriors=json('public/models/exteriors/manifest.json');
const namedAudit=runNamedBuildingPickingChecks({root,json,compile,registry,footprints,namedDomains,extraNamedDomains,THREE,pickEntity,SpatialMasks,insideSourceFootprint,exteriorSourceOwner,exteriorEntityId});
results.push(...namedAudit.results);
const bindings=registry.entities.filter(e=>e.type==='building').map(e=>({entityId:e.entityId,name:e.name,
  footprintRecords:footprints.filter(f=>'building:'+f.officialBuildingId===e.entityId).length,
  namedOfficialDomains:namedDomains.filter(d=>d.entityId===e.entityId).length,
  exteriorObjectIds:e.externalIds?.exteriorObjectIds??[],
  visibleMeshOwnerEligible:exteriors.bundles.some(b=>exteriorEntityId(b)===e.entityId),
  currentForm:e.representations.some(r=>r.subtype?.endsWith('_current_form_approximation')),
  referenceOnly:e.representations.length>0&&e.representations.every(r=>r.type==='reference_point'),
  noRepresentation:e.representations.length===0,
  sourceRayCases:actual.filter(c=>c.entityId===e.entityId).length+namedAudit.actualTriangleRays.filter(c=>c.entityId===e.entityId).length,verifiedIndividualSourceOwner:extraNamedDomains.sourceObjectOwners.some(o=>o.entityId===e.entityId),physicalDomainIds:extraNamedDomains.domains.filter(d=>d.entityId===e.entityId).map(d=>d.physicalDomainId)}));
const inventory=json('docs/source-evidence-v4/building-quality/named-building-inventory.json');assert.deepEqual(new Set(bindings.map(b=>b.entityId)),new Set(inventory.rows.filter(r=>r.canonicalId&&registry.get(r.canonicalId)?.type==='building').map(r=>r.canonicalId)));for(const d of namedDomains)assert.ok(registry.get(d.entityId));
const report={status:'pass',checks:results.length,results,actualTriangleRayCases:actual,sharedSourceDomainRays,listOnlyAudit,
  namedDomainAudit:namedAudit, bindingSummary:{canonicalBuildings:bindings.length,withOfficialDomain:bindings.filter(b=>b.footprintRecords).length,individualOwnedGroups:exteriors.bundles.filter(b=>registry.get(exteriorEntityId(b))?.type==='building').length,namedRangeGroups:exteriors.bundles.filter(b=>registry.get(exteriorEntityId(b))?.type==='zone').length,currentForm:bindings.filter(b=>b.currentForm).length,additionalNamedDomains:new Set(namedDomains.map(d=>d.entityId)).size,totalWithSourceDomain:bindings.filter(b=>b.footprintRecords||b.namedOfficialDomains).length,referenceOnly:bindings.filter(b=>b.referenceOnly).length,noRepresentation:bindings.filter(b=>b.noRepresentation).length},bindings,
  sourceSha256:Object.fromEntries(['app/entity-picking.ts','app/spatial-masks.ts','app/scene.ts'].map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(root+p)).digest('hex')])),
  limitations:['Triangle slopes are not a semantic tree classifier. An unassigned visible surface is never skipped to select a hidden building.', 'Only four of the 25 added domains have locally installed independent source-object rays in this suite. The other domains have original baseline triangle evidence; no native-model or fine-asset success is implied.', 'Source fixtures validate software ownership and clipping, not independent building surveying or browser visual acceptance.']};
fs.writeFileSync(root+'docs/source-evidence-v4/entity-picking/qa.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,checks:report.checks,actualTriangleRays:actual.length+namedAudit.actualTriangleRays.length,actualBoundaryRays:namedAudit.actualBoundaryRays.length,nativePhysicalDomainsProven:namedAudit.nativePhysicalDomainsProven,...report.bindingSummary},null,2));
