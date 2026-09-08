// Execute the actual scene transaction method, with a controlled clock/network.
// Real CurrentFormSet/Three resources cover ready-set ownership and disposal.
// The GLTF parser/decoder itself remains covered by check-current-form-set.mjs.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import ts from 'typescript';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

const project = new URL('../', import.meta.url);
const source = fs.readFileSync(new URL('app/scene.ts', project), 'utf8');
const tree = ts.createSourceFile('scene.ts', source, ts.ScriptTarget.Latest, true);
let method;
function find(node) {
  if (ts.isMethodDeclaration(node) && node.name.getText(tree) === 'loadCurrentFormSet') method = node;
  ts.forEachChild(node, find);
}
find(tree);
assert.ok(method, 'Current production scene transaction must exist');
const transactionCode = ts.transpileModule(`module.exports={${method.getText(tree)}}`, {
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
}).outputText;
const modules = new Map();
function load(name) {
  if (modules.has(name)) return modules.get(name);
  const exports = {}; modules.set(name, exports);
  const code = ts.transpileModule(fs.readFileSync(new URL(`app/${name}.ts`, project), 'utf8'), {
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText;
  vm.runInNewContext(code, {exports, THREE, console, performance, ArrayBuffer, Uint8Array, Blob, URL,
    DOMException, AbortController, setTimeout, clearTimeout, crypto: webcrypto,
    require(id) {
      if (id === 'three') return THREE;
      if (id === 'three/addons/loaders/GLTFLoader.js') return {GLTFLoader};
      if (id.startsWith('./')) return load(id.slice(2));
      throw new Error(`Unexpected production dependency ${id}`);
    }});
  return exports;
}
const {CurrentFormSet} = load('current-form-set');
const reports = [];
const ticks = () => new Promise(resolve => setImmediate(resolve));
async function until(test) {
  for (let i = 0; i < 100 && !test(); i++) await ticks();
  assert.ok(test(), 'Controlled phase was not reached');
}
function gate() { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; }
function aborted() { return new DOMException('Controlled request cancelled', 'AbortError'); }
function pending(signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) reject(aborted());
    else signal.addEventListener('abort', () => reject(aborted()), {once: true});
  });
}
function resourceSet(prefix, mask = true) {
  const group = new THREE.Group(), geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
  const image = {width: 1, height: 1, closed: 0, close() { this.closed++; }};
  const texture = new THREE.Texture(image), material = new THREE.MeshBasicMaterial({map: texture});
  const maskTexture = new THREE.DataTexture(new Uint8Array([255, 0, 0, 255]), 1, 1);
  const owned = [geometry, material, texture, ...(mask ? [maskTexture] : [])];
  const disposed = new Map(owned.map(r => [r, 0]));
  for (const r of owned) r.addEventListener('dispose', () => disposed.set(r, disposed.get(r) + 1));
  const members = [0, 1].map(i => {
    const root = new THREE.Group(), descriptor = {entityId: `building:${prefix}-${i}`, buildingId: `${prefix}-${i}`,
      nodeName: `${prefix}-${i}`, bounds: {min: [0, 0, 0], max: [1, 1, 0]},
      ...(mask ? {mask: {url: 'mask.png', width: 1, height: 1}} : {})};
    root.name = descriptor.nodeName; root.userData.buildingId = descriptor.buildingId;
    root.add(new THREE.Mesh(geometry, material)); group.add(root);
    return {root, descriptor, ...(mask ? {mask: maskTexture} : {})};
  });
  const set = new CurrentFormSet({version: 1, asset: {url: 'group.glb', bytes: 1, sha256: '0'.repeat(64)}, members: members.map(m => m.descriptor)}, group, members);
  return {set, image, disposed};
}
function fixture(options = {}) {
  let now = 0, next = 0, phase = '', settled = false, started = false, listeners = 0;
  const timers = new Map(), requests = [], decoder = gate(), manifestGate = gate();
  const resources = resourceSet('new', options.memberMasks !== false), previous = resourceSet('previous');
  const controller = new AbortController(), signal = controller.signal;
  const add = signal.addEventListener.bind(signal), remove = signal.removeEventListener.bind(signal);
  signal.addEventListener = (...args) => { if (args[0] === 'abort') listeners++; return add(...args); };
  signal.removeEventListener = (...args) => { if (args[0] === 'abort') listeners--; return remove(...args); };
  const data = new Uint8Array([10, 20, 30, 40]);
  const protection = {url: 'source-protection.rgba', width: 1, height: 1,
    sha256: createHash('sha256').update(data).digest('hex'), boundsXZ: {min: [0, 0], max: [1, 1]}, groundBandMeters: 1};
  const errors = [], added = [], removed = [], allocatedProtection = [];
  const coverage = new Set(previous.set.members.map(m => m.descriptor.buildingId));
  const host = {dead: false, currentFormAbort: controller, currentFormSets: new Set([previous.set]), updates: new THREE.Group(),
    renderer: {capabilities: {getMaxAnisotropy: () => 4}}, options: {error: e => errors.push(e)}, notify() {},
    masks: {setSourceProtection(texture) { host.protectionTexture = texture; }, enable() {}},
    currentFormCoverage: {
      addBatch(entries) { added.push(entries); for (const e of entries) coverage.add(e.id); },
      removeBatch(ids) { removed.push(ids); for (const id of ids) coverage.delete(id); },
    }};
  previous.set.commit(host.updates);
  const transactionModule = {exports: {}};
  vm.runInNewContext(transactionCode, {module: transactionModule, DOMException, AbortController, Uint8Array, Array, crypto: webcrypto,
    THREE: {...THREE, DataTexture: class extends THREE.DataTexture {
      constructor(...args) { super(...args); this.testDisposals = 0; this.addEventListener('dispose', () => this.testDisposals++); allocatedProtection.push(this); }
    }}, preparePhotographicMaterials() {},
    setTimeout(fn, delay) { const id = ++next; timers.set(id, {at: now + delay, fn}); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, init) => {
      requests.push({url, signal: init.signal});
      if (init.signal.aborted) throw aborted();
      if (url.endsWith('manifest.json')) {
        phase = 'manifest'; if (options.stall === 'manifest') return pending(init.signal);
        return {ok: true, json: async () => {
          phase = 'manifest-body';
          if (options.stall === 'manifest-body') return pending(init.signal);
          if (options.manifestDelay) await manifestGate.promise;
          return {version: 1};
        }};
      }
      phase = 'protection';
      if (options.stall === 'protection') return pending(init.signal);
      return {ok: true, arrayBuffer: async () => {
        phase = 'protection-body';
        if (options.stall === 'protection-body') return pending(init.signal);
        return data.buffer;
      }};
    },
    loadCurrentFormSet: async (manifest, opts) => {
      requests.push({url: 'controlled-GLB-and-mask-loader', signal: opts.signal}); phase = 'model';
      if (options.stall === 'model') return pending(opts.signal);
      if (options.stall === 'mask-decode') { phase = 'mask-decode'; await decoder.promise; }
      return resources.set;
    },
  });
  return {host, resources, previous, errors, requests, added, removed, timers, allocatedProtection, coverage, decoder,
    manifestGate, get phase() { return phase; }, get settled() { return settled; }, get listeners() { return listeners; },
    advance(ms) {
      now += ms;
      for (const [id, timer] of timers) if (timer.at <= now) { timers.delete(id); timer.fn(); }
    },
    run() {
      assert.equal(started, false); started = true;
      return transactionModule.exports.loadCurrentFormSet.call(host, '/controlled/', protection).finally(() => settled = true);
    },
    assertPreviousIntact() {
      assert.ok(previous.set.members.every(m => m.root.parent === host.updates));
      assert.ok([...previous.disposed.values()].every(n => n === 0));
      assert.equal(previous.image.closed, 0);
      for (const m of previous.set.members) assert.ok(coverage.has(m.descriptor.buildingId));
    },
    cleanup() { resources.set.dispose(); previous.set.dispose(); host.protectionTexture?.dispose(); },
  };
}
async function check(name, fn) {
  await fn(); reports.push({name, pass: true});
}
await check('success clears the outer timer/listener and preserves previously committed shared resources', async () => {
  const f = fixture(); await f.run(); f.assertPreviousIntact();
  assert.equal(f.resources.set.state, 'committed'); assert.equal(f.host.updates.children.length, 4);
  assert.equal(f.added.length, 1); assert.equal(f.timers.size, 0); assert.equal(f.listeners, 0);
  assert.ok(f.requests.every(r => r.signal === f.requests[0].signal));
  f.advance(120001); assert.equal(f.requests[0].signal.aborted, false); f.cleanup();
});
for (const stall of ['manifest', 'manifest-body', 'model', 'protection-body']) {
  await check(`${stall} uses the same 120-second transaction deadline`, async () => {
    const f = fixture({stall}), promise = f.run(); await until(() => f.phase === stall);
    f.advance(119999); await ticks(); assert.equal(f.settled, false);
    f.advance(1); await promise; assert.ok(f.requests.every(r => r.signal.aborted));
    assert.equal(f.added.length, 0); assert.equal(f.errors.length, 1); assert.equal(f.timers.size, 0); assert.equal(f.listeners, 0);
    if (stall === 'protection-body') {
      assert.equal(f.resources.set.state, 'disposed'); assert.ok([...f.resources.disposed.values()].every(n => n === 1));
    }
    f.assertPreviousIntact(); f.cleanup();
  });
}
await check('slow manifest leaves only the remaining deadline for post-GLB source protection', async () => {
  const f = fixture({manifestDelay: true, stall: 'protection'}), promise = f.run();
  await until(() => f.phase === 'manifest-body'); f.advance(119000); f.manifestGate.resolve();
  await until(() => f.phase === 'protection'); f.advance(999); await ticks(); assert.equal(f.settled, false);
  f.advance(1); await promise; assert.equal(f.resources.set.state, 'disposed');
  assert.ok([...f.resources.disposed.values()].every(n => n === 1)); assert.equal(f.resources.image.closed, 1);
  assert.equal(f.added.length, 0); assert.equal(f.timers.size, 0); assert.equal(f.listeners, 0); f.assertPreviousIntact(); f.cleanup();
});
await check('late unabortable mask readiness after deadline is disposed without commit', async () => {
  const f = fixture({stall: 'mask-decode'}), promise = f.run(); await until(() => f.phase === 'mask-decode');
  f.advance(120000); await ticks(); assert.equal(f.settled, false); assert.equal(f.requests[1].signal.aborted, true);
  f.decoder.resolve(); await promise; assert.equal(f.resources.set.state, 'disposed'); assert.equal(f.resources.image.closed, 1);
  assert.equal(f.added.length, 0); assert.equal(f.listeners, 0); assert.equal(f.timers.size, 0); f.assertPreviousIntact(); f.cleanup();
});
await check('scene disposal cancels protection and releases only the local ready set without a late UI error', async () => {
  const f = fixture({stall: 'protection'}), promise = f.run(); await until(() => f.phase === 'protection');
  f.host.dead = true; f.host.currentFormAbort.abort(); await promise;
  assert.equal(f.resources.set.state, 'disposed'); assert.equal(f.errors.length, 0); assert.equal(f.listeners, 0);
  assert.equal(f.timers.size, 0); f.assertPreviousIntact(); f.cleanup();
});
await check('already cancelled scene performs no fetch and retains no listener or timer', async () => {
  const f = fixture(); f.host.dead = true; f.host.currentFormAbort.abort(); await f.run();
  assert.equal(f.requests.length, 0); assert.equal(f.errors.length, 0); assert.equal(f.listeners, 0); assert.equal(f.timers.size, 0);
  f.assertPreviousIntact(); f.cleanup();
});
await check('failed protection prerequisites dispose the new texture and ready set without changing prior coverage', async () => {
  const f = fixture({memberMasks: false}); await f.run();
  assert.equal(f.allocatedProtection.length, 1); assert.equal(f.allocatedProtection[0].testDisposals, 1);
  assert.equal(f.resources.set.state, 'disposed'); assert.equal(f.added.length, 0); assert.equal(f.timers.size, 0); assert.equal(f.listeners, 0);
  f.assertPreviousIntact(); f.cleanup();
});
const report = {status: 'PASS', tests: reports, sceneMethodSHA256: createHash('sha256').update(method.getText(tree)).digest('hex'),
  limits: ['Executes the current scene method with controlled network, clock and inner-loader completion. Real Three and CurrentFormSet own and dispose shared ready resources.',
    'No browser, WebGL renderer, asset rebuild or production network requests. GLTF/mask decoder drain behavior is independently tested by check-current-form-set.mjs.']};
const output = new URL('docs/source-evidence-v4/current-form-transaction-tests.json', project);
fs.writeFileSync(output, JSON.stringify(report, null, 2)+'\n');
console.log(JSON.stringify({status: report.status, passed: reports.length, report: output.pathname}));
