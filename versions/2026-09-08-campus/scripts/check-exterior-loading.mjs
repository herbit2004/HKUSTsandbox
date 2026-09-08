/**
 * Run: node --test scripts/check-exterior-loading.mjs
 * Uses an ephemeral localhost HTTP server; sandboxed runs may need listen approval.
 * Real fetch and installed Three GLTF parsing, controllable mock bitmap decoding.
 * Evidence: docs/source-evidence-v4/exterior-loading-tests.json
 */
import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import http from 'node:http';
import fs from 'node:fs/promises';
import * as THREE from 'three';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';

// Compile the current checkout on every run; no mirror or persistent build artifact.
const project = fileURLToPath(new URL('../', import.meta.url));
const temporary = await fs.mkdtemp(join(tmpdir(), 'hkust-exterior-lifecycle-'));
const runtime = join(temporary, 'runtime.mjs');
await build({
  stdin: {
    contents:
      "export {CoherentExteriors,BundleLoadingManager} from './app/coherent-exteriors'; export {SpatialMasks} from './app/spatial-masks'; export {exteriorEntityId,exteriorBuildingId,parseExteriorManifest} from './app/source-types';",
    resolveDir: project,
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  outfile: runtime,
  plugins: [
    {
      name: 'shared-installed-three',
      setup(builder) {
        builder.onResolve({ filter: /^three(?:\/|$)/ }, ({ path }) => ({
          path: fileURLToPath(import.meta.resolve(path)),
          external: true,
        }));
      },
    },
  ],
});
const { CoherentExteriors, BundleLoadingManager, SpatialMasks, exteriorEntityId, exteriorBuildingId, parseExteriorManifest } = await import(runtime);

globalThis.self = globalThis;
globalThis.ProgressEvent = class extends Event {
  constructor(name, init = {}) {
    super(name);
    Object.assign(this, init);
  }
};
const routes = new Map();
const requests = [];
const bitmaps = [];
const decoding = new Map();
const imageSizes = new Map();
const results = [];
let maxDecodes = 0;
let activeDecodes = 0;
class Bitmap {
  width = 2;
  height = 2;
  closes = 0;
  constructor(label) {
    this.label = label;
    [this.width,this.height] = imageSizes.get(label) || [2,2];
    bitmaps.push(this);
  }
  close() {
    this.closes++;
  }
}
globalThis.createImageBitmap = async (blob) => {
  const label = await blob.text();
  if (label === 'BROKEN') throw new Error('Invalid image data');
  activeDecodes++;
  maxDecodes = Math.max(maxDecodes, activeDecodes);
  try {
    const deferred = decoding.get(label);
    if (deferred) await deferred.promise;
    return new Bitmap(label);
  } finally {
    activeDecodes--;
  }
};
const server = http.createServer((req, res) => {
  const record = {
    path: req.url,
    at: performance.now(),
    closed: false,
    finished: false,
  };
  requests.push(record);
  res.on('close', () => {
    record.closed = true;
    record.finished = res.writableFinished;
  });
  const handler = routes.get(req.url);
  if (handler) handler(req, res);
  else {
    res.writeHead(404);
    res.end('BROKEN');
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const baseURL = `http://127.0.0.1:${server.address().port}/`;
function deferred() {
  let resolve, reject;
  const promise = new Promise((r, fail) => { resolve = r; reject = fail; });
  return { promise, resolve, reject };
}
function glb(textureURI, externalBuffer) {
  const binary = Buffer.alloc(68);
  new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]).forEach((v, i) =>
    binary.writeFloatLE(v, i * 4),
  );
  new Float32Array([0, 0, 1, 0, 0, 1]).forEach((v, i) =>
    binary.writeFloatLE(v, 36 + i * 4),
  );
  [0, 1, 2].forEach((v, i) => binary.writeUInt16LE(v, 60 + i * 2));
  const json = {
    asset: { version: '2.0' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [
      {
        primitives: [
          {
            attributes: { POSITION: 0, TEXCOORD_0: 1 },
            indices: 2,
            material: 0,
          },
        ],
      },
    ],
    buffers: [
      { byteLength: 68, ...(externalBuffer ? { uri: externalBuffer } : {}) },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36 },
      { buffer: 0, byteOffset: 36, byteLength: 24 },
      { buffer: 0, byteOffset: 60, byteLength: 6 },
    ],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 3,
        type: 'VEC3',
        min: [0, 0, 0],
        max: [1, 1, 0],
      },
      { bufferView: 1, componentType: 5126, count: 3, type: 'VEC2' },
      { bufferView: 2, componentType: 5123, count: 3, type: 'SCALAR' },
    ],
    materials: [
      {
        pbrMetallicRoughness: textureURI
          ? { baseColorTexture: { index: 0 } }
          : { baseColorFactor: [1, 1, 1, 1] },
      },
    ],
    ...(textureURI
      ? { textures: [{ source: 0 }], images: [{ uri: textureURI }] }
      : {}),
  };
  const raw = JSON.stringify(json);
  const data = Buffer.from(
    raw + ' '.repeat((4 - (Buffer.byteLength(raw) % 4)) % 4),
  );
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + data.length + binary.length, 8);
  header.writeUInt32LE(data.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, data, binHeader, binary]);
}
const bounds = { min: [0, 0, 0], max: [1, 1, 1] };
function bundle(id, dimensions = [2,2], objectCount = 1, texture = false) {
  const objects = Array.from({ length: objectCount }, (_, i) => ({
    id: `${id}-${i}`,
    url: `${id}/${i}.glb`,
    bounds,
    triangles: 1,
    textureDecodedBytes: texture ? dimensions[0]*dimensions[1]*4 : 0,
    textureDimensions: texture ? [dimensions] : [],
  }));
  imageSizes.set(`${id}-texture`,dimensions);
  for (const o of objects)
    routes.set('/' + o.url, (_q, r) =>
      r.end(glb(texture ? 'texture.png' : undefined)),
    );
  routes.set(`/${id}/mask.png`, (_q, r) => r.end(`${id}-mask`));
  routes.set(`/${id}/texture.png`, (_q, r) => r.end(`${id}-texture`));
  return {
    id,
    buildingId: `building-${id}`,
    buildingName: id,
    catalogIds: [],
    objects,
    mask: {
      url: `${id}/mask.png`,
      boundsXZ: { min: [0, 0], max: [1, 1] },
      heightMin: 0,
      width: 2,
      height: 2,
    },
    bounds,
    textureDecodedBytes: objects.reduce((sum,o)=>sum+o.textureDecodedBytes,0),
  };
}
const controllers = [];
function create(options = {}) {
  const scene = new THREE.Scene(),
    masks = new SpatialMasks();
  const samples = [];
  const controller = new CoherentExteriors(
    scene,
    masks,
    () => {
      const s = controller.stats();
      samples.push({
        visible: [...controller.visible.keys()],
        pending: controller.pending?.id,
        committed: controller.pending?.committed,
        bytes: controller.residentBytes(),
      });
      assert.ok(
        controller.residentBytes() <= controller.options.budgetBytes,
        JSON.stringify(s),
      );
    },
    { baseURL, requestTimeoutMs: 2000, bundleTimeoutMs: 10000, ...options },
  );
  controllers.push(controller);
  return { controller, masks, scene, samples };
}
async function until(predicate, description, timeout = 3000) {
  const start = performance.now();
  while (!predicate()) {
    if (performance.now() - start > timeout)
      throw new Error(`Timed out: ${description}`);
    await new Promise((r) => setTimeout(r, 5));
  }
}
function count(path) {
  return requests.filter((r) => r.path === path).length;
}
async function settle(controller) {
  controller.dispose();
  if (controller.pending) await controller.pending.done;
  assert.equal(controller.residentBytes(), 0);
}
after(async () => {
  for (const controller of controllers) await settle(controller);
  const sourceHashes = {};
  for (const name of [
    'app/coherent-exteriors.ts',
    'app/spatial-masks.ts',
    'app/source-types.ts',
  ])
    sourceHashes[name] = createHash('sha256')
      .update(await fs.readFile(join(project, name)))
      .digest('hex');
  const evidenceDir = join(project, 'docs/source-evidence-v4');
  await fs.mkdir(evidenceDir, { recursive: true });
  await fs.writeFile(
    join(evidenceDir, 'exterior-loading-tests.json'),
    JSON.stringify(
      {
        sourceHashes,
        threeRevision: THREE.REVISION,
        passedChecks: results.length,
        tests: results,
        requestCount: requests.length,
        maxSimultaneousMockImageDecodes: maxDecodes,
        bitmapCount: bitmaps.length,
        unclosedBitmaps: bitmaps.filter((b) => !b.closes).map((b) => b.label),
        doubleClosed: bitmaps.filter((b) => b.closes > 1).map((b) => b.label),
        notes: [
          'Real HTTP fetch cancellation and real Three.js 0.185.1 GLTFLoader parsing; createImageBitmap decode uses controllable fake 2x2 pixels for lifecycle tests.',
          'Budget fixtures use explicit source dimensions matching mock bitmap sizes and exact mip chains. Actual source image headers are checked separately; no browser GPU memory profiling claim.',
        ],
      },
      null,
      2,
    ),
  );
  server.closeAllConnections();
  await new Promise((r) => server.close(r));
  await fs.rm(temporary, { recursive: true, force: true });
  assert.equal(
    bitmaps.filter((b) => !b.closes).length,
    0,
    'all decoded bitmaps must be released',
  );
  assert.equal(
    bitmaps.filter((b) => b.closes > 1).length,
    0,
    'shared image bitmap must be closed exactly once',
  );
});

test('shared original lower body retains domain-only ownership through real GLTF loading', async () => {
  const shared = bundle('shared-lower-body');
  shared.objects[0].ownership = 'domain-only';
  shared.objects[0].subtype = 'original-individualised-lower-building-body-and-terrace';
  const { controller: c } = create();
  c.request(shared);
  await until(() => c.visible.has(shared.id) && !c.pending, 'shared lower body ready');
  const body = c.visible.get(shared.id).group.children[0];
  assert.equal(body.userData.sourceOwnership, 'domain-only');
  assert.equal(body.userData.sourceObjectId, shared.objects[0].id);
  assert.notEqual(body.userData.sourceRole, 'source-photogrammetry-gap-surface');
  await settle(c);
  results.push({test:'shared-source-domain-only-ownership',status:'pass'});
});

test('aborted top-level network releases pending and starts latest candidate', async () => {
  const a = bundle('abort-a'),
    b = bundle('abort-b');
  routes.set('/abort-a/0.glb', () => {});
  const { controller: c } = create();
  c.request(a);
  await until(() => count('/abort-a/0.glb') === 1, 'first network');
  const old = c.pending;
  c.request(b);
  assert.equal(c.pending, old);
  assert.equal(old.abort.signal.aborted, true);
  await until(() => c.visible.has(b.id) && !c.pending, 'replacement ready');
  await until(
    () => requests.find((r) => r.path === '/abort-a/0.glb').closed,
    'socket aborted',
  );
  assert.equal(c.visible.has(a.id), false);
  results.push({
    test: 'network-abort',
    closedUnfinished: !requests.find((r) => r.path === '/abort-a/0.glb')
      .finished,
    latestLoaded: c.current.bundle.id,
  });
  await settle(c);
});

test('per-manager abort reaches nested GLTF texture requests', async () => {
  const a = bundle('nested-a', [2,2], 1, true),
    b = bundle('nested-b');
  routes.set('/nested-a/texture.png', () => {});
  const { controller: c } = create();
  c.request(a);
  await until(
    () => count('/nested-a/texture.png') === 1,
    'nested image request',
  );
  const manager = c.pending.manager;
  assert.equal(manager.active, 1);
  c.request(b);
  await until(
    () => c.visible.has(b.id) && !c.pending,
    'nested replacement ready',
  );
  await until(
    () => requests.find((r) => r.path === '/nested-a/texture.png').closed,
    'nested request socket close',
  );
  assert.equal(manager.active, 0);
  const diagnostic = c.stats().lastImageFailure;
  assert.equal(diagnostic.outcome, 'cancelled');
  assert.equal(diagnostic.error.name, 'AbortError');
  assert.equal(diagnostic.aborted, true);
  assert.equal(diagnostic.stale, true);
  assert.equal(diagnostic.groupId, a.id);
  assert.equal(diagnostic.sourceAsset, '/nested-a/0.glb');
  assert.equal(diagnostic.sourceObjectId, 'nested-a-0');
  assert.equal(c.stats().failures, 0);
  results.push({
    test: 'nested-texture-abort',
    activeAfterDrain: manager.active,
    latestLoaded: c.current.bundle.id,
    diagnostic,
    failures: c.stats().failures,
  });
  await settle(c);
});

test('late native mask decode holds pending identity then closes stale bitmap', async () => {
  const a = bundle('decode-a'),
    b = bundle('decode-b');
  const gate = deferred();
  decoding.set('decode-a-mask', gate);
  const { controller: c } = create();
  c.request(a);
  await until(
    () => count('/decode-a/mask.png') === 1 && activeDecodes === 1,
    'mask decoding',
  );
  const pending = c.pending;
  c.request(b);
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(c.pending, pending);
  assert.equal(count('/decode-b/0.glb'), 0);
  gate.resolve();
  await until(() => c.visible.has(b.id) && !c.pending, 'after decoder drain');
  assert.equal(bitmaps.find((b) => b.label === 'decode-a-mask').closes, 1);
  results.push({
    test: 'late-mask-decode',
    newNetworkBeforeDrain: 0,
    staleBitmapClosed: 1,
  });
  await settle(c);
});

test('late GLTF texture decoder drains before a new group starts', async () => {
  const a = bundle('texture-decode-a', [2,2], 1, true),
    b = bundle('texture-decode-b');
  const gate = deferred();
  decoding.set('texture-decode-a-texture', gate);
  const { controller: c } = create();
  c.request(a);
  await until(
    () => count('/texture-decode-a/texture.png') === 1 && activeDecodes === 1,
    'texture decoding',
  );
  const pending = c.pending;
  c.request(b);
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(c.pending, pending);
  assert.equal(count('/texture-decode-b/0.glb'), 0);
  gate.resolve();
  await until(() => c.visible.has(b.id) && !c.pending, 'texture decoder drain');
  assert.equal(
    bitmaps.find((b) => b.label === 'texture-decode-a-texture').closes,
    1,
  );
  results.push({
    test: 'late-glTF-texture-decode',
    newNetworkBeforeDrain: 0,
    staleBitmapClosed: 1,
  });
  await settle(c);
});

test('multiple complete groups commit independently; priority reorder preserves pending', async () => {
  const a = bundle('multi-a'),
    b = bundle('multi-b', [2,2], 2);
  const gate = deferred();
  routes.set('/multi-b/1.glb', async (_q, r) => {
    await gate.promise;
    r.end(glb());
  });
  const { controller: c, masks, samples } = create();
  c.request([a, b]);
  await until(
    () => count('/multi-b/1.glb') === 1,
    'second group second object',
  );
  assert.deepEqual([...c.visible.keys()], [a.id]);
  assert.equal(c.root.children.length, 1);
  const tx = c.pending;
  c.request([b, a]);
  assert.equal(c.pending, tx);
  assert.equal(tx.abort.signal.aborted, false);
  gate.resolve();
  await until(() => c.visible.size === 2 && !c.pending, 'both groups');
  assert.equal(c.current.bundle.id, b.id);
  assert.equal(new Set([...c.visible.values()].map((e) => e.slot)).size, 2);
  assert.equal(masks.slots[c.visible.get(a.id).slot].enabled.value, 1);
  assert.equal(c.maskFor(a.buildingId).texture.image.label, 'multi-a-mask');
  assert.ok(
    samples
      .filter((s) => s.pending === 'multi-b' && !s.committed)
      .every((s) => s.visible.join() === a.id),
  );
  results.push({
    test: 'atomic-multi-group',
    visible: [...c.visible.keys()],
    slots: [...c.visible.values()].map((e) => e.slot),
    pendingReorderAborted: tx.abort.signal.aborted,
  });
  await settle(c);
});

test('failed same candidate retries automatically with bounded increasing delay', async () => {
  const a = bundle('retry-a');
  let failures = 3;
  routes.set('/retry-a/0.glb', (_q, r) => {
    if (failures-- > 0) {
      r.writeHead(503);
      r.end('temporary');
    } else r.end(glb());
  });
  const { controller: c } = create({ retryDelaysMs: [40, 80, 150] });
  c.request(a);
  await until(() => c.visible.has(a.id) && !c.pending, 'automatic retries');
  const times = requests
    .filter((r) => r.path === '/retry-a/0.glb')
    .map((r) => r.at);
  const intervals = times.slice(1).map((at, i) => Math.round(at - times[i]));
  assert.equal(times.length, 4);
  [35, 75, 145].forEach((min, i) =>
    assert.ok(intervals[i] >= min, JSON.stringify(intervals)),
  );
  assert.equal(c.stats().failures, 3);
  results.push({
    test: 'automatic-retry',
    requests: times.length,
    intervalsMs: intervals,
    productionDelaysMs: create().controller.options.retryDelaysMs,
  });
  await settle(c);
});

test('request timeout aborts real I/O, drains, and permits same-candidate recovery', async () => {
  const a = bundle('timeout-a');
  let first = true;
  routes.set('/timeout-a/0.glb', (_q, r) => {
    if (first) {
      first = false;
      return;
    }
    r.end(glb());
  });
  const { controller: c } = create({
    requestTimeoutMs: 50,
    retryDelaysMs: [30],
  });
  c.request(a);
  await until(() => c.visible.has(a.id) && !c.pending, 'timeout recovery');
  assert.equal(c.stats().timeouts, 1);
  assert.equal(c.stats().failures, 1);
  await until(
    () => requests.find((r) => r.path === '/timeout-a/0.glb').closed,
    'timeout closes socket',
  );
  results.push({
    test: 'timeout-recovery',
    requests: count('/timeout-a/0.glb'),
    timeouts: c.stats().timeouts,
  });
  await settle(c);
});

test('mask failure and swallowed texture failure never commit partial groups', async () => {
  const a = bundle('failure-existing'),
    b = bundle('failure-mask'),
    d = bundle('failure-texture', [2,2], 1, true);
  routes.set('/failure-mask/mask.png', (_q, r) => {
    r.writeHead(500);
    r.end('BROKEN');
  });
  routes.set('/failure-texture/texture.png', (_q, r) => {
    r.writeHead(500);
    r.end('BROKEN');
  });
  const { controller: c } = create({ retryDelaysMs: [10000] });
  c.request(a);
  await until(() => c.visible.has(a.id), 'existing');
  c.request([a, b]);
  await until(() => c.stats().failures === 1 && !c.pending, 'mask failure');
  assert.deepEqual([...c.visible.keys()], [a.id]);
  c.request([a, d]);
  await until(() => c.stats().failures === 2 && !c.pending, 'texture failure');
  assert.deepEqual([...c.visible.keys()], [a.id]);
  assert.equal(c.root.children.length, 1);
  assert.equal(c.stats().lastImageFailure.outcome, 'failed');
  assert.equal(c.stats().lastImageFailure.aborted, false);
  assert.equal(c.stats().lastImageFailure.error.message, 'Invalid image data');
  results.push({
    test: 'atomic-failure',
    failures: c.stats().failures,
    visible: [...c.visible.keys()],
  });
  await settle(c);
});

test('image warning is one bounded JSON string with source paths and cross-realm error fields', () => {
  const manager = new BundleLoadingManager();
  const originalWarn = console.warn;
  const warnings = [];
  console.warn = (...args) => { warnings.push(args); originalWarn(...args); };
  let diagnostic;
  try {
    diagnostic = manager.imageError('blob:https://campus.invalid/b2ab9098-test?token=secret', {
      name: 'InvalidStateError',
      message: 'ImageBitmap could not be allocated https://user:password@campus.invalid/image.jpg?token=secret ' + 'x'.repeat(2000),
    }, {
      lane: 'mesh', groupId: 'source-region:fine', sourceAsset: 'https://user:password@campus.invalid/models/hires/source.glb?token=secret',
      aborted: false, stale: false, timedOut: false,
    });
  } finally {
    console.warn = originalWarn;
  }
  assert.equal(warnings.length, 1);
  assert.equal(warnings[0].length, 1, 'no opaque second Object argument');
  const warning = warnings[0][0];
  assert.ok(warning.length < 2048);
  assert.equal(warning.includes('secret'), false);
  assert.equal(warning.includes('password'), false);
  assert.deepEqual(JSON.parse(warning.slice('Campus image decode failed '.length)), diagnostic);
  assert.equal(diagnostic.error.name, 'InvalidStateError');
  assert.equal(diagnostic.error.message.length, 512);
  assert.equal(diagnostic.sourceAsset, '/models/hires/source.glb');
  assert.equal(diagnostic.imageURL, 'blob:b2ab9098-test');
  assert.equal(manager.failureBeforeCancellation, true);
  results.push({test:'bounded-readable-image-diagnostic',status:'pass',diagnostic,loggedCharacters:warning.length});
});

test('real texture failure before a view cancellation remains a counted failure', async () => {
  const a = bundle('fail-before-cancel', [2,2], 1, true), b = bundle('fail-before-cancel-next');
  const gate = deferred();
  decoding.set('fail-before-cancel-texture', gate);
  const {controller:c} = create({retryDelaysMs:[10000]});
  c.request(a);
  await until(() => activeDecodes === 1 && count('/fail-before-cancel/texture.png') === 1, 'allocation in progress');
  const manager = c.pending.manager;
  const imageError = manager.imageError.bind(manager);
  manager.imageError = (...args) => {
    const diagnostic = imageError(...args);
    // Re-enter a real request between the image callback and GLTF parse catch.
    c.request(b);
    return diagnostic;
  };
  gate.reject(new DOMException('ImageBitmap could not be allocated', 'InvalidStateError'));
  await until(() => c.visible.has(b.id) && !c.pending, 'new view after failure drain');
  assert.equal(c.visible.has(a.id), false);
  assert.equal(c.stats().failures, 1);
  assert.equal(c.stats().lastImageFailure.outcome, 'failed');
  assert.equal(c.stats().lastImageFailure.aborted, false);
  assert.equal(c.stats().lastImageFailure.stale, false);
  assert.match(c.stats().failureDetail, /InvalidStateError: ImageBitmap could not be allocated/);
  results.push({test:'failure-before-later-cancel-counted',status:'pass',failures:c.stats().failures,diagnostic:c.stats().lastImageFailure});
  await settle(c);
});

test('allocation rejection after cancellation remains distinguishable from AbortError', async () => {
  const a = bundle('fail-after-cancel', [2,2], 1, true), b = bundle('fail-after-cancel-next');
  const gate = deferred();
  decoding.set('fail-after-cancel-texture', gate);
  const {controller:c} = create();
  c.request(a);
  await until(() => activeDecodes === 1 && count('/fail-after-cancel/texture.png') === 1, 'old allocation in progress');
  const pending = c.pending;
  c.request(b);
  assert.equal(c.pending, pending);
  assert.equal(count('/fail-after-cancel-next/0.glb'), 0, 'latest group waits for native decode drain');
  gate.reject(new DOMException('ImageBitmap could not be allocated', 'InvalidStateError'));
  await until(() => c.visible.has(b.id) && !c.pending, 'new view after late allocation rejection');
  assert.equal(c.visible.has(a.id), false);
  assert.equal(c.stats().lastImageFailure.outcome, 'failed-after-cancel');
  assert.equal(c.stats().lastImageFailure.aborted, true);
  assert.equal(c.stats().lastImageFailure.stale, true);
  assert.equal(c.stats().lastImageFailure.error.name, 'InvalidStateError');
  assert.equal(c.stats().failures, 0, 'already-cancelled transaction is not retried, but its allocation failure remains visible');
  results.push({test:'allocation-failure-after-cancel-visible',status:'pass',failures:c.stats().failures,diagnostic:c.stats().lastImageFailure});
  await settle(c);
});

test('texture timeout is reported as timeout even when fetch rejects with AbortError', async () => {
  const a = bundle('image-timeout', [2,2], 1, true);
  routes.set('/image-timeout/texture.png', () => {});
  const {controller:c} = create({requestTimeoutMs:100,retryDelaysMs:[10000]});
  c.request(a);
  await until(() => c.stats().failures === 1 && !c.pending, 'timed out texture drain');
  assert.equal(c.visible.size, 0);
  assert.equal(c.stats().lastImageFailure.outcome, 'timeout');
  assert.equal(c.stats().lastImageFailure.timedOut, true);
  assert.equal(c.stats().lastImageFailure.error.name, 'AbortError');
  assert.equal(c.stats().timeouts, 1);
  results.push({test:'texture-timeout-diagnostic',status:'pass',failures:c.stats().failures,diagnostic:c.stats().lastImageFailure});
  await settle(c);
});

test('completed LRU cache reuses source group and bitmap without fetching', async () => {
  const a = bundle('cache-a', [2,2], 1, true),
    b = bundle('cache-b');
  const { controller: c } = create();
  c.request(a);
  await until(() => c.visible.has(a.id) && !c.pending, 'a ready');
  const group = c.visible.get(a.id).group,
    bitmap = c.visible.get(a.id).mask.image;
  c.request(b);
  await until(() => c.visible.has(b.id) && !c.pending, 'b ready');
  assert.equal(c.cache.has(a.id), true);
  assert.equal(bitmap.closes, 0);
  c.request([a, b]);
  assert.equal(c.visible.get(a.id).group, group);
  assert.equal(bitmap.closes, 0);
  assert.equal(count('/cache-a/0.glb'), 1);
  assert.equal(c.visible.size, 2);
  results.push({
    test: 'return-cache',
    sameGroup: true,
    sourceRequests: count('/cache-a/0.glb'),
    cacheHits: c.stats().cacheHits,
  });
  await settle(c);
  assert.equal(bitmap.closes, 1);
});

test('exact mip budget protects higher-priority groups and evicts full lower groups', async () => {
  const a = bundle('budget-a', [16,8], 1, true),
    b = bundle('budget-b', [8,8], 1, true),
    d = bundle('budget-d', [16,8], 1, true);
  const { controller: c, samples } = create({
    budgetBytes: 1100,
    maxCachedGroups: 1,
  });
  c.request([a, b]);
  await until(
    () => c.visible.size === 2 && !c.pending,
    'initial budget groups',
  );
  c.request([d, a, b]);
  await until(
    () => c.visible.has(d.id) && !c.pending,
    'high priority new group',
  );
  assert.deepEqual(
    [...c.visible.keys()].sort((a, b) => a.localeCompare(b)),
    [d.id, b.id].sort((a, b) => a.localeCompare(b)),
  );
  assert.equal(c.visible.has(a.id), false);
  assert.equal(count('/budget-a/0.glb'), 1);
  assert.ok(samples.every((s) => s.bytes <= 1100));
  c.request([a, d, b]);
  await until(() => c.visible.has(a.id) && !c.pending, 'priority reversal');
  assert.equal(c.visible.has(d.id), false);
  assert.equal(c.visible.has(b.id), true);
  results.push({
    test: 'budget-priority',
    peakReservedBytes: Math.max(...samples.map((s) => s.bytes)),
    budgetBytes: 1100,
    visible: [...c.visible.keys()],
    evictions: c.stats().budgetFallbacks,
  });
  await settle(c);
});

function imageDimensions(data) {
  if (data.subarray(1,4).toString() === 'PNG')
    return [data.readUInt32BE(16),data.readUInt32BE(20)];
  assert.equal(data.readUInt16BE(0),0xffd8,'Source image must be PNG or JPEG');
  for(let at=2;at<data.length;){
    while(data[at]===0xff)at++;
    const marker=data[at++];
    if(marker===0xd9||marker===0xda)break;
    if(marker===0x01||marker>=0xd0&&marker<=0xd7)continue;
    const length=data.readUInt16BE(at);
    if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker))
      return [data.readUInt16BE(at+5),data.readUInt16BE(at+3)];
    at+=length;
  }
  assert.fail('Source JPEG dimensions unavailable');
}

test('all installed exterior source image headers match exact mip reservations; Hall XIII view remains bounded', async () => {
  const manifest=JSON.parse(await fs.readFile(join(project,'public/models/exteriors/manifest.json'),'utf8'));
  const state=JSON.parse(await fs.readFile(join(project,'docs/source-evidence-v4/halls-current-first-stage.json'),'utf8')).state;
  const {controller:c,samples}=create({budgetBytes:800*1048576,maxCachedGroups:0});
  let imageCount=0,objectCount=0;
  const rows=[];
  for(const b of manifest.bundles){
    for(const object of b.objects){
      const file=join(project,'public/models/exteriors',object.url),raw=await fs.readFile(file);
      let gltf,binary;
      if(object.url.endsWith('.gltf'))gltf=JSON.parse(raw);
      else {
        assert.equal(raw.toString('ascii',0,4),'glTF');
        const jsonLength=raw.readUInt32LE(12);gltf=JSON.parse(raw.subarray(20,20+jsonLength).toString());
        const binAt=20+jsonLength;binary=raw.subarray(binAt+8,binAt+8+raw.readUInt32LE(binAt));
      }
      const dimensions=[];
      for(const image of gltf.images||[]){
        const view=image.bufferView!==undefined?gltf.bufferViews[image.bufferView]:null;
        const data=image.uri?await fs.readFile(new URL(image.uri,'file://'+file)):binary.subarray(view.byteOffset||0,(view.byteOffset||0)+view.byteLength);
        dimensions.push(imageDimensions(data));imageCount++;
      }
      assert.deepEqual(dimensions,object.textureDimensions,object.id);
      assert.equal(dimensions.reduce((n,[w,h])=>n+w*h*4,0),object.textureDecodedBytes,object.id);
      objectCount++;
    }
    assert.equal(b.objects.reduce((n,o)=>n+o.textureDecodedBytes,0),b.textureDecodedBytes);
    const base=b.textureDecodedBytes+b.mask.width*b.mask.height*4,mip=c.entryBytes(b);
    assert.ok(mip>=base);
    rows.push({id:b.id,objects:b.objects.length,baseBytes:base,mipBytes:mip});
  }
  // Exact small/rectangular/NPOT chains differ from a blind 4/3 multiplier.
  const dimensional=bundle('mip-shapes');dimensional.objects[0].textureDimensions=[[1,8],[3,5],[2,2],[8192,8192]];
  assert.equal(c.entryBytes(dimensional),60+72+20+357913940+16);
  // Replace only network completion, then exercise real request/makeRoom/commit.
  // Real source bytes above are reserved; no full-resolution browser decode is claimed.
  c.start=function(b){const mask=new THREE.DataTexture(new Uint8Array([0,0,0,255]),1,1);this.commit({bundle:b,group:new THREE.Group(),mask,bytes:this.entryBytes(b)});};
  const candidates=state.detailCandidates.map(id=>manifest.bundles.find(b=>b.id===id)).filter(Boolean);
  c.request(candidates);
  for(let i=0;i<candidates.length;i++)c.pump();
  const before=rows.filter(r=>state.exterior.visibleIds.includes(r.id));
  const after=[...c.visible.values()];
  assert.ok(after.length>0&&after.length<state.exterior.visibleIds.length);
  assert.ok(samples.every(s=>s.bytes<=800*1048576));
  assert.ok(after.some(e=>e.bundle.id==='campus-01'));
  assert.equal(c.options.budgetBytes,800*1048576);
  results.push({test:'real-source-mip-accounting',objectCount,imageCount,rows,
    hallXIIIPose:state.camera,beforeVisible:state.exterior.visibleIds,
    beforeReportedBaseBytes:before.reduce((n,r)=>n+r.baseBytes,0),
    beforeActualMipBytes:before.reduce((n,r)=>n+r.mipBytes,0),
    afterVisible:after.map(e=>e.bundle.id),afterMipBytes:c.residentBytes(),
    peakReservedBytes:Math.max(...samples.map(s=>s.bytes)),budgetBytes:c.options.budgetBytes,
    accountingBoundary:'RGBA8 source mip chains plus one mask base level. CPU ImageBitmap backing, encoded buffers, native decode scratch, geometry and driver overhead remain outside this reservation.'});
  await settle(c);
});

test('cache group limit is bounded during repeated travel and zoom-out', async () => {
  const { controller: c } = create({ maxCachedGroups: 2 });
  for (let i = 0; i < 6; i++) {
    const b = bundle(`travel-${i}`);
    c.request(b);
    await until(() => c.visible.has(b.id) && !c.pending, `travel ${i}`);
    assert.ok(c.cache.size <= 2);
  }
  c.request(null);
  assert.equal(c.visible.size, 0);
  assert.equal(c.cache.size, 2);
  assert.equal(c.current, null);
  results.push({
    test: 'bounded-travel-cache',
    cacheGroups: c.cache.size,
    visibleGroups: c.visible.size,
  });
  await settle(c);
});

test('dispose cancels active I/O and releases all owned completed bitmaps', async () => {
  const a = bundle('dispose-a'),
    b = bundle('dispose-b');
  routes.set('/dispose-b/0.glb', () => {});
  const { controller: c, scene } = create();
  c.request([a, b]);
  await until(() => count('/dispose-b/0.glb') === 1, 'dispose pending');
  await settle(c);
  assert.equal(c.pending, null);
  assert.equal(c.visible.size, 0);
  assert.equal(scene.children.length, 0);
  results.push({
    test: 'dispose',
    residentBytes: c.residentBytes(),
    pending: c.pending,
    unclosedBitmaps: bitmaps.filter((b) => !b.closes).length,
  });
});

test('a rejected parse releases orphan bitmap that finishes decoding after rejection', async () => {
  const a = bundle('orphan-a', [2,2], 1, true),
    b = bundle('orphan-b');
  const decodeGate = deferred(),
    bufferGate = deferred();
  decoding.set('orphan-a-texture', decodeGate);
  routes.set('/orphan-a/0.glb', (_q, r) =>
    r.end(glb('texture.png', 'invalid.bin')),
  );
  routes.set('/orphan-a/invalid.bin', async (_q, r) => {
    await bufferGate.promise;
    r.end(Buffer.alloc(1));
  });
  const { controller: c } = create({ retryDelaysMs: [10000] });
  c.request(a);
  await until(
    () => activeDecodes === 1 && count('/orphan-a/invalid.bin') === 1,
    'orphan decode with invalid accessor pending',
  );
  bufferGate.resolve();
  await until(
    () => c.pending?.abort.signal.aborted,
    'parse rejected, decode still draining',
  );
  c.request(b);
  assert.equal(count('/orphan-b/0.glb'), 0);
  decodeGate.resolve();
  await until(
    () => c.visible.has(b.id) && !c.pending,
    'rejected parse drained',
  );
  assert.equal(bitmaps.find((b) => b.label === 'orphan-a-texture').closes, 1);
  results.push({ test: 'parse-rejection-orphan-image', closedBitmap: 1 });
  await settle(c);
});

void test('canonical exterior identities reject conflicts and allow distinct envelopes of one zone', async () => {
  const a = bundle('identity-a'), b = bundle('identity-b');
  assert.equal(exteriorEntityId(a), 'building:' + a.buildingId);
  assert.equal(exteriorBuildingId(a), a.buildingId);
  assert.equal(exteriorBuildingId({id:'explicit-building',entityId:'building:123'}),'123');
  assert.equal(exteriorBuildingId({id:'explicit-zone',entityId:'zone:catalog:campus-42'}),undefined);
  assert.equal(exteriorEntityId({...a, entityId: 'building:' + a.buildingId}), 'building:' + a.buildingId);
  assert.throws(() => exteriorEntityId({...a, entityId:'zone:catalog:campus-42'}), /Conflicting/);
  assert.throws(() => exteriorEntityId({id:'missing'}), /Missing/);
  assert.throws(() => parseExteriorManifest({bundles:[a,a]}), /Duplicate/);
  for (const [i, item] of [a,b].entries()) {
    delete item.buildingId;
    item.entityId='zone:catalog:campus-42';
    item.physicalDomainId='physical-domain:fixture:'+i;
  }
  assert.equal(parseExteriorManifest({bundles:[a,b]}).bundles.length, 2);
  assert.throws(() => parseExteriorManifest({bundles:[a,{...b,physicalDomainId:a.physicalDomainId}]}), /physical domain/);
  const current=JSON.parse(await fs.readFile(join(project,'public/models/exteriors/manifest.json'),'utf8'));
  const parsed=parseExteriorManifest(current);
  assert.equal(parsed.bundles.filter(b=>exteriorEntityId(b)==='zone:catalog:campus-42').length,2);
  results.push({test:'canonical-exterior-owner-validation',installedGroups:parsed.bundles.length,sharedZoneEnvelopes:2,conflictRejected:true});
});

void test('same-zone envelopes retain separate masks, atomic budgets, cache entries and eight slots', async () => {
  const a=bundle('range-a',[2,2],1,true), b=bundle('range-b',[2,2],1,true);
  for (const [i,item]of[a,b].entries()) {
    delete item.buildingId;item.entityId='zone:catalog:campus-42';item.physicalDomainId='physical-domain:range:'+i;
    item.objects[0].ownership='domain-only';
  }
  const {controller:c}=create({budgetBytes:72});
  const plan=c.previewPlan([a,b],72);assert.equal(plan.bytes,72);assert.deepEqual(plan.bundles,[a,b]);
  c.request(plan.bundles);
  await until(()=>c.visible.size===2&&!c.pending,'two same-zone envelopes');
  assert.equal(new Set([...c.visible.values()].map(e=>e.slot)).size,2);
  assert.equal(c.maskFor(a.entityId),undefined);
  assert.equal(c.maskFor(a.entityId,a.physicalDomainId).texture.image.label,'range-a-mask');
  assert.equal(c.maskFor(b.entityId,b.physicalDomainId).texture.image.label,'range-b-mask');
  assert.equal(c.visible.get(a.id).group.children[0].userData.sourceOwnership,'domain-only');
  c.request(null);assert.equal(c.cache.size,2);
  const calls=requests.length;c.request([b,a]);
  await until(()=>c.visible.size===2&&!c.pending,'same-zone cache return');
  assert.equal(requests.length,calls);
  c.setBudget(36);
  await until(()=>c.memoryBytes()<=36&&!c.pending,'whole same-zone envelope reduction');
  assert.equal(c.visible.size,1);assert.ok(c.visible.has(b.id));
  const extra=Array.from({length:9},(_,i)=>({...a,id:'range-cap-'+i,physicalDomainId:'physical-domain:cap:'+i}));
  assert.equal(c.previewPlan(extra,10000).bundles.length,8);
  results.push({test:'same-zone-envelope-lifecycle',originalVisibleGroups:2,distinctMaskSlots:2,returnNetworkRequests:0,reducedWholeGroupBytes:c.memoryBytes(),maximumSlots:8});
  await settle(c);
});
