// Extension of check-entity-picking.mjs: current source methods, real source
// coordinates/topology, controlled DOM boundary. No browser acceptance claim.
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import ts from 'typescript';

export function runNamedBuildingPickingChecks({root,json,registry,footprints,namedDomains,extraNamedDomains,THREE,pickEntity,SpatialMasks,insideSourceFootprint,exteriorSourceOwner,exteriorEntityId}) {
  const results=[], actualTriangleRays=[], actualBoundaryRays=[], cache=new Map(), verifiedHashes=new Set();
  const fixtures=json('docs/source-evidence-v4/entity-picking/named-domain-source-fixtures.json');
  const boundaryFixtures=json('docs/source-evidence-v4/entity-picking/named-domain-boundary-ambiguity-fixtures.json');
  const sceneSource=fs.readFileSync(root+'app/scene.ts','utf8'),ast=ts.createSourceFile('scene.ts',sceneSource,ts.ScriptTarget.Latest,true);
  const sceneMethods=[];function visit(node){if(ts.isMethodDeclaration(node)&&['pick','exteriorRangeDomains','buildingFloors','entityPosition','detailBounds'].includes(node.name.getText(ast)))sceneMethods.push(node.getText(ast));ts.forEachChild(node,visit);}visit(ast);assert.equal(sceneMethods.length,5);
  const sandboxModule={exports:{}};
  vm.runInNewContext(ts.transpileModule(`module.exports=({${sceneMethods.join(",")}})`,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:sandboxModule,THREE,pickEntity,exteriorSourceOwner,exteriorEntityId,Map,Set,extraBuildingDomains:extraNamedDomains,namedBuildingDomains:{domains:json('public/data/picking/building-domains.json').domains},pickingDomains:json('public/surfaces/entrance/entity-picking-domains.json')});
  function check(name,fn){fn();results.push({name,status:'pass'});}
  function material(){return new THREE.MeshBasicMaterial({side:THREE.DoubleSide});}
  function triangleMesh(points){const geometry=new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));geometry.computeVertexNormals();return new THREE.Mesh(geometry,material());}
  function rayFor(sample,distance=2){const [a,b,c]=sample.worldTriangle.map(p=>new THREE.Vector3(...p)),normal=new THREE.Vector3().crossVectors(b.clone().sub(a),c.clone().sub(a)).normalize();return new THREE.Raycaster(new THREE.Vector3(...sample.point).addScaledVector(normal,distance),normal.negate());}
  function context(roots,groundY){return {registry,footprints,buildingDomains:namedDomains,roots,masks:new SpatialMasks(),groundAt:()=>groundY};}
  function sceneHarness(){const group=()=>new THREE.Group(),selected=[];const scene={registry,footprints,masks:new SpatialMasks(),groundSample:()=>0,facilityPins:group(),interior:{root:group()},sports:group(),entrance:group(),landmarks:group(),updates:group(),exteriors:{root:group(),visible:new Map(),bundles:json('public/models/exteriors/manifest.json').bundles},meshDetail:{root:group()},geometry:group(),detail:{group:group()},terrain:group(),outdoor:{roads:[],surfaces:[]},host:{dataset:{}},options:{select:id=>selected.push(id)}};scene.floorManifest=json('public/interiors/manifest.json');for(const[name,method]of Object.entries(sandboxModule.exports))scene[name]=method.bind(scene);return {scene,selected};}
  function readSource(sample){
    const key=sample.asset+'|'+sample.placement.join(',');if(cache.has(key))return cache.get(key);
    const path=root+'public'+sample.asset,raw=fs.readFileSync(path);assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),sample.sourceSha256);verifiedHashes.add(sample.asset);
    let gltf,buffers;
    if(sample.asset.endsWith('.gltf')){
      gltf=JSON.parse(raw);const folder=path.slice(0,path.lastIndexOf('/')+1);buffers=gltf.buffers.map(b=>fs.readFileSync(folder+b.uri));
      const sourceManifest=JSON.parse(fs.readFileSync(folder+'source-manifest.json'));
      for(const file of sourceManifest.files){assert.equal(crypto.createHash('sha256').update(fs.readFileSync(folder+file.filename)).digest('hex'),file.sha256);verifiedHashes.add(sample.asset.slice(0,sample.asset.lastIndexOf('/')+1)+file.filename);}
    }else{
      assert.equal(raw.toString('ascii',0,4),'glTF');assert.equal(raw.readUInt32LE(8),raw.length);
      const chunks={};for(let at=12;at<raw.length;){const n=raw.readUInt32LE(at),kind=raw.toString('ascii',at+4,at+8);chunks[kind]=raw.subarray(at+8,at+8+n);at+=8+n;}
      gltf=JSON.parse(chunks.JSON.toString());buffers=[chunks['BIN\0']];
    }
    function accessor(index){const a=gltf.accessors[index],v=gltf.bufferViews[a.bufferView],buffer=buffers[v.buffer||0],n={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type],methods={5126:['readFloatLE',4],5125:['readUInt32LE',4],5123:['readUInt16LE',2],5121:['readUInt8',1]},[method,bytes]=methods[a.componentType],out=[];for(let i=0;i<a.count;i++)for(let j=0;j<n;j++)out.push(buffer[method]((v.byteOffset||0)+(a.byteOffset||0)+i*(v.byteStride||n*bytes)+j*bytes));return out;}
    function node(index){const source=gltf.nodes[index],object=new THREE.Group();assert.ok(!['translation','rotation','scale'].some(k=>k in source));object.name=source.name||'';if(source.matrix){object.matrixAutoUpdate=false;object.matrix.fromArray(source.matrix);object.matrixWorldNeedsUpdate=true;}if(source.mesh!==undefined)for(const primitive of gltf.meshes[source.mesh].primitives){assert.equal(primitive.mode??4,4);const g=new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(accessor(primitive.attributes.POSITION),3));if(primitive.indices!==undefined)g.setIndex(accessor(primitive.indices));g.computeVertexNormals();object.add(new THREE.Mesh(g,material()));}for(const child of source.children||[])object.add(node(child));return object;}
    const group=new THREE.Group();group.matrixAutoUpdate=false;group.matrix.fromArray(sample.placement);group.matrixWorldNeedsUpdate=true;for(const index of gltf.scenes[gltf.scene||0].nodes)group.add(node(index));group.updateWorldMatrix(true,true);
    const triangles=[];group.traverse(object=>{if(!object.isMesh)return;const a=object.geometry.getAttribute('position'),indices=object.geometry.index;for(let i=0;i<(indices?.count??a.count);i+=3)triangles.push([0,1,2].map(j=>new THREE.Vector3().fromBufferAttribute(a,indices?indices.getX(i+j):i+j).applyMatrix4(object.matrixWorld).toArray()));});
    const result={group,triangles};cache.set(key,result);return result;
  }
  check('new-domain fixtures reproduce actual source buffer triangles/matrices and original hashes',()=>{
    for(const sample of [...fixtures.cases,...boundaryFixtures.cases]){const tri=readSource(sample).triangles[sample.sourceTriangleIndex];assert.ok(tri);for(let i=0;i<3;i++)for(let j=0;j<3;j++)assert.ok(Math.abs(tri[i][j]-sample.worldTriangle[i][j])<1e-8,`${sample.asset} source triangle mismatch ${Math.abs(tri[i][j]-sample.worldTriangle[i][j])}: ${tri[i][j]} vs ${sample.worldTriangle[i][j]}`);}
    assert.deepEqual(new Set(fixtures.coverage.map(c=>c.physicalDomainId)),new Set(extraNamedDomains.domains.map(d=>d.physicalDomainId)));
  });
  check('actual named baseline roof/wall-like triangles resolve named domains and shared UC once',()=>{
    for(const sample of fixtures.cases.filter(s=>s.representation!=='native-individual')){const mesh=triangleMesh(sample.worldTriangle),ctx=context([mesh],sample.groundY);ctx.masks.apply(mesh,sample.representation==='baseline'?'baseline':'photogrammetry');const result=pickEntity(rayFor(sample),ctx);assert.equal(result?.entityId,sample.entityId,JSON.stringify({sample,result:result?.method,actual:result?.entityId}));actualTriangleRays.push({entityId:sample.entityId,physicalDomainId:sample.physicalDomainId,representation:sample.representation,faceClass:sample.faceClass,asset:sample.asset,method:result.method});}
  });
  check('photogrammetry role preserves named-domain fallback on the same verified source triangles (role test, not fine-asset proof)',()=>{
    for(const sample of fixtures.cases.filter(s=>s.representation==='baseline')){const mesh=triangleMesh(sample.worldTriangle),ctx=context([mesh],sample.groundY);ctx.masks.apply(mesh,'photogrammetry');assert.equal(pickEntity(rayFor(sample),ctx)?.entityId,sample.entityId);}
  });
  const native=fixtures.cases.filter(s=>s.representation==='native-individual');
  check('actual CampusScene.pick binds complete C/D source children in the shared UC bundle; HallVI components remain one hall',()=>{
    for(const sample of native){const {scene,selected}=sceneHarness(),source=readSource(sample);source.group.userData.sourceObjectId=sample.sourceId;const group=new THREE.Group();group.add(source.group);scene.exteriors.root.add(group);const bundle=json('public/models/exteriors/manifest.json').bundles.find(b=>b.objects.some(o=>o.id===sample.sourceId));assert.ok(bundle);scene.exteriors.visible.set(bundle.id,{bundle,group});scene.groundSample=()=>sample.groundY;const result=scene.pick(rayFor(sample));assert.equal(result?.entityId,sample.entityId,JSON.stringify(sample));assert.equal(result?.method,'explicit-source-owner');assert.deepEqual(selected,[sample.entityId]);actualTriangleRays.push({entityId:sample.entityId,physicalDomainId:sample.physicalDomainId,representation:sample.representation,sourceObjectId:sample.sourceId,asset:sample.asset,faceClass:sample.faceClass,method:result.method});source.group.removeFromParent();}
  });
  check('unassigned opaque foreground outside source domains blocks actual C/D native wall rays',()=>{
    for(const sample of native.filter(s=>s.faceClass==='wall-like'&&extraNamedDomains.sourceObjectOwners.some(o=>o.sourceObjectId===s.sourceId))){const {scene}=sceneHarness(),source=readSource(sample),group=new THREE.Group();source.group.userData.sourceObjectId=sample.sourceId;group.add(source.group);scene.exteriors.root.add(group);const bundle=json('public/models/exteriors/manifest.json').bundles.find(b=>b.objects.some(o=>o.id===sample.sourceId));scene.exteriors.visible.set(bundle.id,{bundle,group});scene.groundSample=()=>sample.groundY;const base=rayFor(sample),center=new THREE.Vector3(...sample.point);let ray,front;
      for(const sign of [1,-1]){const n=base.ray.direction.clone().multiplyScalar(-sign);for(const distance of [10,25,50,100]){const candidate=center.clone().addScaledVector(n,distance);if([...footprints,...namedDomains].some(d=>d.parts.some(p=>insideSourceFootprint(candidate.x,candidate.z,p.rings))))continue;const candidateRay=new THREE.Raycaster(center.clone().addScaledVector(n,distance+2),n.clone().negate());if(scene.pick(candidateRay)?.entityId===sample.entityId){front=candidate;ray=candidateRay;break;}}if(ray)break;}
      assert.ok(ray&&front,'No verified exterior wall occlusion ray');const direction=ray.ray.direction,basis=new THREE.Vector3(0,1,0).cross(direction).normalize(),up=direction.clone().cross(basis).normalize(),tree=triangleMesh([front.clone().addScaledVector(basis,-1).addScaledVector(up,-1).toArray(),front.clone().addScaledVector(up,1).toArray(),front.clone().addScaledVector(basis,1).addScaledVector(up,-1).toArray()]);tree.name='controlled-opaque-canopy-occluder';scene.geometry.add(tree);const blocked=scene.pick(ray);assert.equal(blocked?.hit.object,tree);assert.equal(blocked?.entityId,undefined);source.group.removeFromParent();
    }
  });
  check('actual CampusScene.pick applies domain-only ownership to the complete 208-face Staff source object',()=>{
    const fixture=json('docs/source-evidence-v4/building-quality/staff-domain-only-ray-fixtures.json');
    const bundle=json('public/models/exteriors/manifest.json').bundles.find(b=>b.id==='staff-quarters-tower-3');
    const object=bundle.objects.find(o=>o.id===fixture.sourceObjectId);
    const source=readSource({asset:'/models/exteriors/'+object.url,sourceSha256:fixture.gltfSha256,placement:new THREE.Matrix4().makeTranslation(...object.offset).toArray()});
    assert.equal(source.triangles.length,208);
    for(const sample of fixture.fixtures){
      const {scene,selected}=sceneHarness(),group=new THREE.Group();
      source.group.userData.sourceObjectId=object.id;source.group.userData.sourceOwnership=object.ownership;
      group.add(source.group);scene.exteriors.root.add(group);scene.exteriors.visible.set(bundle.id,{bundle,group});
      scene.groundSample=()=>sample.runtimeGrid5mGroundY;
      const picked=scene.pick(new THREE.Raycaster(new THREE.Vector3(...sample.ray.origin),new THREE.Vector3(...sample.ray.direction)));
      assert.equal(picked?.entityId??null,sample.expectedDomainEntityId);
      assert.ok(picked.hit.point.distanceTo(new THREE.Vector3(...sample.centroidLocalXYZ))<.0001);
      assert.deepEqual(selected,sample.expectedDomainEntityId?[sample.expectedDomainEntityId]:[]);
      source.group.removeFromParent();
    }
  });
  const uc='building:b00000000000000000000006',towerIds=extraNamedDomains.sourceObjectOwners.map(o=>o.entityId);
  const rooms=registry.entities.filter(e=>e.type==='space'&&registry.building(e)?.entityId===uc);
  const roomSamples=towerIds.map(tower=>{const domain=extraNamedDomains.domains.find(d=>d.entityId===tower);for(const entity of rooms)for(const representation of entity.representations.filter(r=>r.type==='room_parts')){const floor=json('public'+representation.asset);for(const index of representation.partIndices){const room=floor.rooms[index],p=room.center;if(p&&domain.parts.some(part=>insideSourceFootprint(p[0],p[1],part.rings)))return {entity,room,tower,floorId:representation.floorId};}}assert.fail('No published UC room in '+tower);});
  check('published UC room priority survives new tower ownership without reparenting its floor/room',()=>{
    for(const sample of roomSamples){const {scene}=sceneHarness(),[x,z]=sample.room.center,y=sample.room.heightSourceZ,points=[[x-.01,y,z-.01],[x,y,z+.01],[x+.01,y,z-.01]],room=triangleMesh(points),floor=triangleMesh(points),shell=triangleMesh(points);room.userData.entityId=sample.entity.entityId;floor.userData.entityId=sample.floorId;shell.userData.entityId=sample.tower;scene.interior.root.add(floor,room);scene.exteriors.root.add(shell);scene.groundSample=()=>y-5;assert.equal(scene.pick(new THREE.Raycaster(new THREE.Vector3(x,y+1,z),new THREE.Vector3(0,-1,0)))?.entityId,sample.entity.entityId);assert.equal(registry.building(sample.entity)?.entityId,uc);}
  });
  check('published floor beats a near-coincident tower shell independently of hit order',()=>{
    for(const sample of roomSamples){const [x,z]=sample.room.center,y=sample.room.heightSourceZ,points=[[x-.01,y,z-.01],[x,y,z+.01],[x+.01,y,z-.01]],floor=triangleMesh(points),shell=triangleMesh(points);floor.userData.entityId=sample.floorId;shell.userData.entityId=sample.tower;shell.position.y=.01;const result=pickEntity(new THREE.Raycaster(new THREE.Vector3(x,y+1,z),new THREE.Vector3(0,-1,0)),context([shell,floor],y-5));assert.equal(result?.entityId,sample.floorId);}
  });
  check('only declared shared envelopes are removed; two real named domain candidates stay ambiguous',()=>{
    const sample=fixtures.cases.find(s=>s.entityId===towerIds[0]&&s.representation==='baseline'),m=triangleMesh(sample.worldTriangle),ctx=context([m],sample.groundY),domain=extraNamedDomains.domains.find(d=>d.entityId===towerIds[0]);ctx.buildingDomains=[...namedDomains,{...domain,entityId:towerIds[1]}];const ambiguous=pickEntity(rayFor(sample),ctx);assert.equal(ambiguous?.entityId,undefined);assert.equal(ambiguous?.method,'ambiguous-source-footprints');
    ctx.buildingDomains=namedDomains.map(d=>{const result={...d};delete result.sharedPhysicalEnvelopeWith;return result;});assert.equal(pickEntity(rayFor(sample),ctx)?.method,'ambiguous-source-footprints');
  });
  check('actual shared-edge House 1/2 source triangle preserves ambiguity without choosing either neighbor',()=>{
    for(const sample of boundaryFixtures.cases){const m=triangleMesh(sample.worldTriangle),ctx=context([m],sample.groundY);ctx.masks.apply(m,'baseline');const result=pickEntity(rayFor(sample),ctx);assert.equal(result?.entityId,undefined);assert.equal(result?.method,'ambiguous-source-footprints');
      // Each real domain can own this source point independently; together they
      // must remain ambiguous at the source drawing's documented edge tolerance.
      for(const id of sample.expectedCandidates){ctx.buildingDomains=namedDomains.filter(d=>d.entityId===id);assert.equal(pickEntity(rayFor(sample),ctx)?.entityId,id);}
      actualBoundaryRays.push({asset:sample.asset,sourceTriangleIndex:sample.sourceTriangleIndex,point:sample.point,expectedCandidates:sample.expectedCandidates,method:result.method});}
  });
  const rangeRays=[];
  const rangeFixtures=json('docs/source-evidence-v4/building-quality/staff-range-source-rays.json').cases;
  check('actual complete Staff range source roofs and walls select their aggregate zones',()=>{
    for(const sample of rangeFixtures){
      const {scene,selected}=sceneHarness(),source=readSource(sample),group=new THREE.Group();
      const bundle=scene.exteriors.bundles.find(b=>b.id===sample.bundleId);
      assert.equal(bundle.entityId,sample.entityId);assert.equal(bundle.buildingId,undefined);
      const object=bundle.objects.find(o=>o.id===sample.sourceId);assert.equal(object.ownership,'aggregate-source');
      source.group.userData.sourceObjectId=sample.sourceId;source.group.userData.sourceOwnership=object.ownership;
      group.add(source.group);scene.exteriors.root.add(group);scene.exteriors.visible.set(bundle.id,{bundle,group});
      scene.masks.apply(group,'exterior');scene.groundSample=()=>sample.groundY;
      const result=scene.pick(new THREE.Raycaster(new THREE.Vector3(...sample.ray.origin),new THREE.Vector3(...sample.ray.direction)));
      assert.equal(result?.entityId,sample.entityId,JSON.stringify(sample));
      assert.ok(result.hit.point.distanceTo(new THREE.Vector3(...sample.point))<.0001);
      assert.equal(result.method,'explicit-source-owner');
      assert.deepEqual(selected,[sample.entityId]);
      rangeRays.push({bundleId:bundle.id,sourceObjectId:sample.sourceId,triangleIndex:sample.triangleIndex,faceClass:sample.faceClass,entityId:result.entityId??null,physicalDomainId:result.physicalDomainId??null,method:result.method});
      source.group.removeFromParent();
    }
  });
  check('zone range roles preserve canonical identity without granting neighboring source objects ownership',()=>{
    for(const sample of rangeFixtures.filter(s=>s.faceClass==='roof')){
      const {scene}=sceneHarness();scene.groundSample=()=>sample.groundY;
      const m=triangleMesh(sample.worldTriangle);scene.geometry.add(m);
      const ray=new THREE.Raycaster(new THREE.Vector3(...sample.ray.origin),new THREE.Vector3(...sample.ray.direction));
      for(const role of ['baseline','photogrammetry']){
        m.material.dispose();m.material=material();scene.masks.apply(m,role);
        assert.equal(scene.pick(ray)?.entityId,sample.entityId);
      }
      m.userData.sourceObjectId='unrelated-source-object';
      assert.equal(scene.pick(ray)?.entityId,undefined);
      delete m.userData.sourceObjectId;
      m.position.y=100;ray.ray.origin.y+=100;assert.equal(scene.pick(ray)?.entityId,undefined);
    }
  });
  check('two envelopes retain one existing zone identity and no invented building or floor entries',()=>{
    const {scene}=sceneHarness(),zone=registry.get('zone:catalog:campus-42');
    assert.equal(zone.type,'zone');assert.equal(registry.building(zone),undefined);
    const groups=scene.exteriors.bundles.filter(b=>exteriorEntityId(b)===zone.entityId);
    assert.equal(groups.length,2);assert.equal(new Set(groups.map(b=>b.physicalDomainId)).size,2);
    assert.equal(zone.representations.filter(r=>r.type==='mesh_group').length,2);
    assert.deepEqual(zone.externalIds.exteriorBundleIds,groups.map(b=>b.id));
    assert.equal(zone.externalIds.exteriorBundleId,undefined);
    const position=scene.entityPosition(zone);assert.ok(position.toArray().every(Number.isFinite));
    for(const bundle of groups)assert.deepEqual(scene.detailBounds(undefined,bundle.bounds),bundle.bounds);
    assert.equal(scene.buildingFloors(zone).length,0);
    assert.ok(scene.buildingFloors(registry.get('building:b00000000000000000000001')).length>0);
    assert.equal(scene.exteriorRangeDomains().filter(d=>d.entityId.startsWith('zone:catalog:')).length,5);
  });
  const result={results,actualTriangleRays,actualBoundaryRays,rangeRays,coverage:fixtures.coverage,sourceFilesHashVerified:verifiedHashes.size,
    nativePhysicalDomainsProven:new Set(actualTriangleRays.filter(c=>c.representation==='native-individual').map(c=>c.physicalDomainId)).size,
    actualFineAssetRayCases:actualTriangleRays.filter(c=>c.representation==='fine'||c.representation==='high').length,
    limitations:['Native geometry and source-object ownership are proven only for the four listed C/D/HallVI domains. Other 21 domains have actual baseline geometry rays, not installed native model proof.','Current high/fine assets supplied no valid triangles within these 25 domains. The photogrammetry-role test reuses verified baseline triangles and is explicitly not fine-source coverage.','Room tests use actual public entity IDs, centers and source Z with controlled coincident triangles; no use-by-floor partition or hidden geometry is inferred.','Controlled canopy occluders prove nearest-visible-hit behavior outside source domains; slope/domain tests cannot semantically distinguish a tree canopy directly over a roof.']};
  fs.writeFileSync(root+'docs/source-evidence-v4/entity-picking/named-domain-qa.json',JSON.stringify(result,null,2)+'\n');
  for(const {group} of cache.values())group.traverse(o=>{if(o.isMesh){o.geometry.dispose();o.material.dispose();}});
  return result;
}
