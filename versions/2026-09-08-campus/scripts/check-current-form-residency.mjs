// Execute the production residency and complete-set classes with real Three
// cameras/resources. Controlled I/O tests scheduling; real GLB image headers
// verify that admission estimates match source dimensions. No browser claims.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import ts from 'typescript';
import sharp from 'sharp';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

const project = new URL('../', import.meta.url), modules = new Map(), reports = [];
function load(name) {
  if (modules.has(name)) return modules.get(name);
  const exports = {}; modules.set(name, exports);
  const code = ts.transpileModule(fs.readFileSync(new URL(`app/${name}.ts`, project), 'utf8'), {
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText;
  vm.runInNewContext(code, {exports, console, performance, ArrayBuffer, Uint8Array, Blob, URL, DOMException,
    AbortController, setTimeout, clearTimeout, crypto: webcrypto,
    require(id) {
      if (id === 'three') return THREE;
      if (id === 'three/addons/loaders/GLTFLoader.js') return {GLTFLoader};
      if (id.startsWith('./')) return load(id.slice(2));
      throw new Error(id);
    }});
  return exports;
}
const {CurrentFormResidency, currentFormFixedTextureBytes, currentFormResidencyPolicy: policy} = load('current-form-residency');
const {CurrentFormSet, parseCurrentFormSetManifest} = load('current-form-set');
const {textureMipBytes} = load('source-types');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function settled(manager) {
  for (let i = 0; i < 100; i++) { await tick(); if (!manager.stats().packages.some(p => ['loading', 'draining'].includes(p.state))) return; }
  throw new Error('Controlled loader did not settle');
}
function gate() { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; }
function camera(position = [0, 30, 150], target = [0, 15, 0], offAxis = false) {
  const value = new THREE.PerspectiveCamera(42, 1600 / 900, .5, 9000);
  value.position.fromArray(position); value.lookAt(new THREE.Vector3(...target));
  if (offAxis) value.setViewOffset(1600, 900, -161, -31, 1600, 900);
  value.updateMatrixWorld(); return value;
}
const front = () => camera(), away = () => camera([0, 30, 150], [0, 30, 500]);
let sequence = 0;
function fixture({count = 4, x = 0, id = `controlled-${++sequence}`, cost = textureMipBytes(8, 8)} = {}) {
  const image = {width: 8, height: 8, closes: 0, close() { this.closes++; }};
  const map = new THREE.Texture(image), material = new THREE.MeshBasicMaterial({map, vertexColors: true});
  const geometry = new THREE.BoxGeometry(12, 20, 12), group = new THREE.Group(), parent = new THREE.Group();
  const members = Array.from({length: count}, (_, i) => {
    const root = new THREE.Group(); root.position.set(x + i * 15, 10, 0);
    root.add(new THREE.Mesh(geometry, material)); group.add(root);
    const descriptor = {entityId: `building:${id}-${i}`, buildingId: `${id}-${i}`, nodeName: `${id}-${i}`,
      bounds: {min: [x + i * 15 - 6, 0, -6], max: [x + i * 15 + 6, 20, 6]}};
    Object.assign(root.userData, descriptor); return {root, descriptor};
  });
  const manifest = {version: 1, asset: {url: `${id}.glb`, bytes: 1, sha256: id.padEnd(64, '0')}, members: members.map(m => m.descriptor)};
  const set = new CurrentFormSet(manifest, group, members);
  const coverage = new Set(); let activations = 0, deactivations = 0, loads = 0, disposed = 0;
  for (const resource of [geometry, material, map]) resource.addEventListener('dispose', () => disposed++);
  const demand = {id, manifest, fixedTextureBytes: cost, load: async () => {
    loads++; set.commit(parent, {activate: ready => { activations++; for (const member of ready) coverage.add(member.descriptor.buildingId); },
      deactivate: () => { deactivations++; coverage.clear(); }}); return set;
  }};
  return {demand, set, parent, coverage, image, material, geometry,
    get loads() { return loads; }, get disposed() { return disposed; }, get activations() { return activations; }, get deactivations() { return deactivations; }};
}
async function check(name, run) {
  try { const detail = await run(); reports.push({name, pass: true, detail}); }
  catch (error) { reports.push({name, pass: false, error: error.stack}); }
}

await check('offscreen and distant startup fetch no complete assets; near off-axis demand loads one full shared set', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(away(), 900, 0); await tick(); assert.equal(f.loads, 0);
  manager.update(camera([0, 30, 3000]), 900, 100); await tick(); assert.equal(f.loads, 0);
  const view = camera([0, 30, 150], [0, 15, 0], true), before = [...view.position.toArray(), ...view.quaternion.toArray(), view.fov];
  manager.update(view, 900, 200); await settled(manager);
  assert.equal(f.loads, 1); assert.equal(f.parent.children.length, 4);
  assert.equal(manager.stats().chargedBytes, f.demand.fixedTextureBytes);
  assert.equal(f.set.textureBytes(), f.demand.fixedTextureBytes);
  assert.deepEqual([...view.position.toArray(), ...view.quaternion.toArray(), view.fov], before);
  manager.dispose(); return {sharedRoots: 4, allocations: 1, cameraUnchanged: true};
});

await check('120 small rotations and zoom changes retain exact roots, material, bitmap, coverage and source level', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager); const roots = [...f.parent.children];
  for (let i = 1; i <= 120; i++) {
    manager.update(camera([Math.sin(i) * 3, 30, 150 + Math.cos(i) * 5], [Math.sin(i) * 2, 15, 0], true), 900, i * 350);
    assert.equal(f.set.state, 'committed'); assert.equal(f.parent.children.every((r, n) => r === roots[n] && r.visible), true);
  }
  assert.equal(f.loads, 1); assert.equal(f.activations, 1); assert.equal(f.deactivations, 0); assert.equal(f.image.closes, 0);
  manager.dispose(); return {samples: 120, reloads: 0, baselineTransitions: 0};
});

await check('offscreen exit obeys minimum residency and grace; cache return preserves coverage without a source fallback', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager);
  manager.update(away(), 900, 2500); assert.equal(f.set.state, 'committed');
  manager.update(away(), 900, policy.minimumResidentMs + 1); assert.equal(f.set.state, 'inactive');
  assert.equal(f.parent.children.every(r => !r.visible), true); assert.equal(f.coverage.size, 4);
  assert.equal(f.deactivations, 0); assert.equal(manager.stats().cachedBytes, f.demand.fixedTextureBytes);
  manager.update(front(), 900, 9000); assert.equal(f.set.state, 'committed'); assert.equal(f.loads, 1);
  manager.update(away(), 900, 9500); assert.equal(f.set.state, 'committed');
  manager.update(front(), 900, 10000); assert.equal(f.loads, 1);
  manager.dispose(); assert.equal(f.disposed, 3); assert.equal(f.image.closes, 1); assert.equal(f.deactivations, 1);
  return {oldConstructionRestored: false, coverageRetainedInCache: true, sharedDisposals: 3};
});

await check('opening one Hall only hides its own root and cannot resurrect an inactive package', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager);
  manager.setOpened(f.set.members[1].descriptor.buildingId);
  assert.deepEqual(f.parent.children.map(r => r.visible), [true, false, true, true]);
  manager.setOpened(''); assert.equal(f.parent.children.every(r => r.visible), true);
  manager.update(away(), 900, 9000); manager.setOpened('unrelated-open-building');
  assert.equal(f.parent.children.every(r => !r.visible), true); assert.equal(f.coverage.size, 4);
  manager.dispose(); return {isolatedMember: 1, noVisibilityOverride: true};
});

await check('pointer-time render refresh restores cached roots before the next planning tick without IO or a masked hole', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager); manager.update(away(), 900, 9000);
  assert.equal(f.set.state, 'inactive'); assert.equal(f.coverage.size, 4);
  // No update() call: scene suppresses budget planning during a gesture.
  manager.refreshVisibility(front(), 900, 9016, f.set.members[2].descriptor.buildingId);
  assert.deepEqual(f.parent.children.map(r => r.visible), [true, true, false, true]);
  assert.equal(f.coverage.size, 4); assert.equal(f.loads, 1); assert.equal(f.activations, 1);
  manager.refreshVisibility(away(), 900, 9500); assert.equal(f.set.state, 'committed');
  manager.dispose(); return {reactivatedBeforeRender: true, noNetworkCalls: true, openedMemberPreserved: true};
});

await check('first admission distance threshold does not become an unload threshold for a visible current building', async () => {
  const f = fixture({count: 1}), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(camera([0, 10, policy.enterDistance + 7], [0, 10, 0]), 3000, 0); await tick(); assert.equal(f.loads, 0);
  manager.update(camera([0, 10, policy.enterDistance + 5], [0, 10, 0]), 3000, 100); await settled(manager); assert.equal(f.loads, 1);
  for (let i = 0; i < 12; i++) manager.update(camera([0, 10, policy.enterDistance + 7 + i * 10], [0, 10, 0]), 3000, 9000 + i * 350);
  assert.equal(f.set.state, 'committed'); assert.equal(f.loads, 1); manager.dispose();
  return {entryMeters: policy.enterDistance, noSingleLevelDowngrade: true};
});

await check('full fixed-budget admission, near-package deferral and pressure reduction never dismantle committed representation', async () => {
  const a = fixture({count: 1}), b = fixture({count: 1, x: 25}), manager = new CurrentFormResidency();
  manager.register(a.demand); manager.register(b.demand); manager.setBudget(a.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager);
  assert.equal(a.loads + b.loads, 1); const visible = a.loads ? a : b, waiting = a.loads ? b : a;
  assert.equal(manager.stats().packages.find(p => p.id === waiting.demand.id).state, 'deferred');
  manager.setBudget(0); manager.update(front(), 900, 9000);
  assert.equal(visible.set.state, 'committed'); assert.equal(visible.image.closes, 0);
  assert.equal(manager.stats().effectiveBudgetBytes, visible.demand.fixedTextureBytes);
  assert.equal(waiting.loads, 0); manager.setBudget(manager.catalogBytes()); await settled(manager);
  assert.equal(a.loads + b.loads, 2); assert.equal(manager.stats().chargedBytes, manager.catalogBytes()); manager.dispose();
  return {committedEvictions: 0, wholePackageDeferral: true};
});

await check('cancelled unabortable decode holds reservation and blocks next worker until actual drain', async () => {
  const a = fixture({count: 1}), b = fixture({count: 1, x: 1000}), wait = gate(), manager = new CurrentFormResidency();
  let signal, started = 0;
  manager.register({...a.demand, load: async value => { signal = value; started++; await wait.promise; if (signal.aborted) throw new DOMException('cancelled', 'AbortError'); return a.demand.load(value); }});
  manager.register(b.demand); manager.setBudget(manager.catalogBytes()); manager.update(front(), 900, 0); await tick();
  assert.equal(started, 1); manager.update(camera([1000, 30, 150], [1000, 15, 0]), 900, 3000);
  assert.equal(signal.aborted, true); assert.equal(b.loads, 0); assert.equal(manager.stats().pendingBytes, a.demand.fixedTextureBytes);
  manager.setBudget(b.demand.fixedTextureBytes); assert.equal(b.loads, 0);
  wait.resolve(); await settled(manager); assert.equal(b.loads, 1); assert.equal(manager.stats().chargedBytes, b.demand.fixedTextureBytes);
  manager.dispose(); a.set.dispose(); return {serialWorker: true, cancelledBytesNotReusedBeforeDrain: true};
});

await check('same-view failed complete transaction retries without camera motion or destruction of another ready set', async () => {
  const good = fixture({count: 1}), failed = fixture({count: 1, x: 20}), manager = new CurrentFormResidency(); let attempts = 0;
  manager.register(good.demand); manager.register({...failed.demand, load: signal => { if (++attempts === 1) throw new Error('controlled full-mask failure'); return failed.demand.load(signal); }});
  manager.setBudget(manager.catalogBytes()); manager.update(front(), 900, 0); await settled(manager);
  assert.equal(attempts, 1); assert.equal(good.set.state, 'committed'); assert.equal(failed.loads, 0);
  manager.update(front(), 900, 1999); await tick(); assert.equal(attempts, 1);
  manager.update(front(), 900, 2000); await settled(manager); assert.equal(attempts, 2); assert.equal(failed.set.state, 'committed');
  assert.equal(good.loads, 1); assert.equal(good.image.closes, 0); manager.dispose(); return {firstRetryMs: 2000};
});

await check('dispose while a loader ignores cancellation drains late complete result and releases shared resources once', async () => {
  const f = fixture(), wait = gate(), manager = new CurrentFormResidency();
  manager.register({...f.demand, load: async signal => { await wait.promise; return f.demand.load(signal); }});
  manager.setBudget(manager.catalogBytes()); manager.update(front(), 900, 0); await tick(); manager.dispose();
  assert.equal(manager.stats().pendingBytes, f.demand.fixedTextureBytes); wait.resolve(); await settled(manager);
  assert.equal(f.set.state, 'disposed'); assert.equal(f.parent.children.length, 0); assert.equal(f.coverage.size, 0);
  assert.equal(f.disposed, 3); assert.equal(f.image.closes, 1); assert.equal(manager.stats().chargedBytes, 0);
  return {lateCommitNotExposed: true, resourcesReleasedOnce: true};
});

await check('bad or duplicated budget descriptors reject rather than admitting partial or unmeasured textures', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand);
  assert.throws(() => manager.register(f.demand), /Duplicate/);
  assert.throws(() => manager.register({...f.demand, id: 'same-package'}), /Duplicate/);
  assert.throws(() => currentFormFixedTextureBytes({}, f.demand.manifest), /dimensions/);
  assert.throws(() => currentFormFixedTextureBytes({appearanceTextures: [{dimensions: [NaN, 1]}]}, f.demand.manifest), /dimensions/);
  manager.dispose(); f.set.dispose(); return {unmeasuredAdmissionRejected: true};
});

await check('live package metadata equals actual embedded image dimensions; all Hall members reserve shared texture images once', async () => {
  const details = [];
  for (const name of ['innovation', 'ivillage-rebuild', 'hall2-corridor']) {
    const base = new URL(`public/models/current-forms/${name}/`, project), input = JSON.parse(fs.readFileSync(new URL('manifest.json', base)));
    const manifest = parseCurrentFormSetManifest(input), bytes = fs.readFileSync(new URL(manifest.asset.url, base));
    const length = bytes.readUInt32LE(12), document = JSON.parse(bytes.subarray(20, 20 + length).toString()), binary = bytes.subarray(28 + length);
    const images = [];
    for (const source of document.images ?? []) {
      const view = document.bufferViews[source.bufferView], data = binary.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
      const metadata = await sharp(data).metadata(); images.push([metadata.width, metadata.height]);
    }
    assert.deepEqual(input.appearanceTextures.map(t => t.dimensions), images);
    const imageBytes = images.reduce((sum, [w, h]) => sum + textureMipBytes(w, h), 0);
    const cost = currentFormFixedTextureBytes(input, manifest, input.sourceProtection?.bytes ?? 0);
    assert.ok(cost >= imageBytes); assert.ok(cost < imageBytes + 8 * 1048576);
    const manager = new CurrentFormResidency(); let io = 0;
    manager.register({id: name, manifest, fixedTextureBytes: cost, load: async () => { io++; throw new Error('unexpected offscreen IO'); }});
    manager.setBudget(cost); manager.update(camera([0, 200, 0], [0, 200, 1000]), 900, 0); await tick(); assert.equal(io, 0);
    manager.dispose(); details.push({name, members: manifest.members.length, embeddedImages: images, imageMipBytes: imageBytes, fixedReserveBytes: cost});
  }
  return details;
});

// Extract and execute the current method, not a copied integration implementation.
const sceneSource = fs.readFileSync(new URL('app/scene.ts', project), 'utf8');
const syntax = ts.createSourceFile('scene.ts', sceneSource, ts.ScriptTarget.Latest, true);
const methods = new Map();
function collect(node) { if (ts.isMethodDeclaration(node)) methods.set(node.name.getText(syntax), node.getText(syntax)); ts.forEachChild(node, collect); }
collect(syntax);
await check('real scene notify cannot restore roots hidden by residency; quality-independent identity and floor remain unchanged', async () => {
  const f = fixture(), manager = new CurrentFormResidency(); manager.register(f.demand); manager.setBudget(f.demand.fixedTextureBytes);
  manager.update(front(), 900, 0); await settled(manager); manager.update(away(), 900, 9000);
  const stats = {stats: () => ({})}, group = () => new THREE.Group();
  const host = {dead: false, updateOpening() {}, updateBuildingSelection() {}, currentFormResidency: manager,
    opened: {entityId: 'building:unrelated'}, registry: {buildingSource: () => 'unrelated'}, firstPerson: stats,
    interior: {loading: false, cache: new Map(), bytes: 0, root: group()}, exteriors: stats, detailPool: stats,
    detailMemoryBytes: () => ({}), fixedResourceStats: () => ({}), detail: {terrainObjects: new Map()},
    renderer: {info: {memory: {textures: 1, geometries: 1}, render: {triangles: 12}}, capabilities: {}, getPixelRatio: () => 1.6},
    camera: front(), controls: {target: new THREE.Vector3(0, 15, 0)}, automaticQuality: stats, masks: {samplerStats: () => ({})},
    meshDetail: stats, motion: stats, anchorPan: stats, viewportStats: () => ({}), sports: group(), entrance: group(), landmarks: group(),
    textures: stats, updates: f.parent, currentFormSets: new Set([f.set]), host: {dataset: {}}, options: {change() {}},
    selectedId: 'space:kept', floorId: 'floor-kept', qualityMode: 'ultra', qualityLevel: 'ultra'};
  const notificationModule = {exports: {}};
  vm.runInNewContext(ts.transpileModule(`module.exports={${methods.get('notify')}}`, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText,
    {module: notificationModule, navigator: {hardwareConcurrency: 8}});
  for (const quality of ['smooth', 'high', 'ultra']) { host.qualityLevel = quality; notificationModule.exports.notify.call(host); assert.equal(f.parent.children.some(r => r.visible), false); }
  assert.equal(host.selectedId, 'space:kept'); assert.equal(host.floorId, 'floor-kept'); assert.equal(f.loads, 1);
  const state = JSON.parse(host.host.dataset.sceneState); assert.deepEqual(state.currentForms, []); assert.equal(state.currentFormResidency.cachedBytes, f.demand.fixedTextureBytes);
  manager.dispose(); return {notifications: 3, inactiveRootsNotResurrected: true};
});

const report = {status: reports.every(r => r.pass) ? 'pass' : 'fail', checks: reports.length, reports,
  limits: ['Fixed cache retains single-level current geometry and masks; it is not a GPU eviction test.', 'CPU ImageBitmap/geometry/driver allocations remain outside texture budgets.', 'No browser or pixel-quality acceptance is claimed.']};
const reportAt = process.argv.indexOf('--report');
if (reportAt >= 0) fs.writeFileSync(process.argv[reportAt + 1], JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
if (report.status !== 'pass') process.exitCode = 1;
