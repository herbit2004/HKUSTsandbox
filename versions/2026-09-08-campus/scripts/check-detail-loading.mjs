// Run from any directory: node /path/to/project/scripts/check-detail-loading.mjs
// Exercises the current checkout classes; only I/O/decode/clock boundaries are controlled.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { inflateSync } from 'node:zlib';
import ts from 'typescript';
import * as THREE from 'three';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = root + '/app';
const results = [],
  checks = [];
async function run(name, check) {
  const start = performance.now(),
    before = results.length;
  try {
    await check();
    checks.push({
      name,
      status: 'passed',
      notes: results.slice(before),
      elapsedMs: Math.round(performance.now() - start),
    });
  } catch (error) {
    checks.push({
      name,
      status: 'failed',
      error: error instanceof Error ? error.stack : String(error),
      elapsedMs: Math.round(performance.now() - start),
    });
    console.error('FAIL ' + name, error);
  }
}
const source = (url) => ({
  url,
  width: 1024,
  height: 1024,
  decodedBytes: 4 * 1048576,
  bytes: 123,
});
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};
const flush = () => new Promise((resolve) => setImmediate(resolve));
function fixture(options = {}) {
  let now = 10000,
    nextTimer = 0;
  const timers = new Map(),
    calls = [],
    bitmaps = [],
    events = [],
    cache = new Map();
  const f = { fetch: null, decode: null, modules: {} };
  const bitmap = (url) => {
    const image = {
      url,
      closed: 0,
      close() {
        this.closed++;
        events.push('close:' + url);
      },
    };
    bitmaps.push(image);
    return image;
  };
  const response = (url) => ({ ok: true, blob: async () => ({ url }) });
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const exports = {};
    cache.set(name, exports);
    const text = fs.readFileSync(out + '/' + name + '.ts', 'utf8');
    const js = ts.transpileModule(text, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    vm.runInNewContext(js, {
      exports,
      console,
      AbortController,
      DOMException,
      URL,
      navigator: { hardwareConcurrency: 8 },
      devicePixelRatio: 2,
      performance: { now: () => now },
      Map,
      Set,
      ArrayBuffer,
      Float32Array,
      Uint8Array,
      setTimeout(fn, ms) {
        const id = ++nextTimer;
        timers.set(id, { fn, at: now + ms });
        return id;
      },
      clearTimeout(id) {
        timers.delete(id);
      },
      fetch(url, init = {}) {
        calls.push({ url, signal: init.signal });
        events.push('fetch:' + url);
        return f.fetch ? f.fetch(url, init) : Promise.resolve(response(url));
      },
      createImageBitmap(blob) {
        events.push('decode:' + blob.url);
        return f.decode ? f.decode(blob) : Promise.resolve(bitmap(blob.url));
      },
      require(id) {
        if (id in f.modules) return f.modules[id];
        if (id === 'three') return THREE;
        if (
          id.startsWith('./') &&
          fs.existsSync(out + '/' + id.slice(2) + '.ts')
        )
          return load(id.slice(2));
        return {};
      },
    });
    return exports;
  }
  const atomic = new (load('atomic-textures').AtomicTextures)(options);
  return {
    atomic,
    calls,
    bitmaps,
    events,
    bitmap,
    response,
    f,
    flush,
    load,
    async tick(ms) {
      now += ms;
      for (const [id, timer] of timers)
        if (timer.at <= now) {
          timers.delete(id);
          timer.fn();
        }
      await flush();
    },
    bind(url) {
      const low = new THREE.Texture();
      const material = new THREE.MeshBasicMaterial({ map: low });
      atomic.catalog.set(url, { materials: { 0: source(url) } });
      atomic.register(url, material, 0);
      return { material, low };
    },
  };
}

// Same-key errors retry at 2, 5, then 15 seconds without reselecting or moving the camera.
await run('atomic_same_key_retry', async () => {
  const x = fixture();
  let attempts = 0;
  x.f.fetch = async (url) => (++attempts < 4 ? { ok: false } : x.response(url));
  const b = x.bind('/a');
  x.atomic.request('A', [source('/a')]);
  await flush();
  assert.equal(x.atomic.retryAt - 10000, 2000);
  await x.tick(1999);
  x.atomic.request('A', [source('/a')]);
  assert.equal(attempts, 1);
  await x.tick(1);
  x.atomic.request('A', [source('/a')]);
  await flush();
  assert.equal(attempts, 2);
  assert.equal(x.atomic.stats().retryInMs, 5000);
  await x.tick(5000);
  x.atomic.request('A', [source('/a')]);
  await flush();
  assert.equal(attempts, 3);
  assert.equal(x.atomic.stats().retryInMs, 15000);
  assert.equal(b.material.map, b.low);
  await x.tick(15000);
  x.atomic.request('A', [source('/a')]);
  await flush();
  assert.equal(attempts, 4);
  assert.equal(x.atomic.ready, 'A');
  assert.notEqual(b.material.map, b.low);
  for (let i = 0; i < 10; i++) x.atomic.request('A', [source('/a')]);
  assert.equal(attempts, 4);
  assert.equal(x.atomic.failureCount, 0);
  x.atomic.dispose();
  assert.equal(x.bitmaps[0].closed, 1);
  assert.equal(x.atomic.cacheBytes, 0);
  assert.equal(b.material.map, b.low);
  results.push(
    'PASS same-key failure retries 2/5/15s, commits only success, and ready same key never reloads',
  );
});

// Successful shared images are not decoded/downloaded again when the desired set changes.
await run('atomic_whole_commit_shared_cache', async () => {
  const x = fixture(),
    pending = new Map();
  x.f.fetch = (url, { signal }) => {
    const d = deferred();
    pending.set(url, d);
    signal.addEventListener(
      'abort',
      () => d.reject(new DOMException('Cancelled', 'AbortError')),
      { once: true },
    );
    return d.promise;
  };
  const a = x.bind('/a'),
    b = x.bind('/b');
  x.atomic.request('AB', [source('/a'), source('/b')]);
  pending.get('/a').resolve(x.response('/a'));
  await flush();
  assert.equal(x.atomic.cache.size, 1);
  assert.equal(x.atomic.current.size, 0);
  assert.equal(a.material.map, a.low);
  assert.equal(b.material.map, b.low);
  pending.get('/b').resolve(x.response('/b'));
  await flush();
  assert.equal(x.atomic.ready, 'AB');
  assert.equal(x.atomic.current.size, 2);
  x.atomic.request('ABC', [source('/a'), source('/b'), source('/c')]);
  assert.equal(x.calls.length, 3);
  pending.get('/c').resolve(x.response('/c'));
  await flush();
  assert.equal(x.atomic.ready, 'ABC');
  x.atomic.request('AB', [source('/a'), source('/b')]);
  x.atomic.request('ABC', [source('/a'), source('/b'), source('/c')]);
  assert.equal(x.calls.length, 3);
  assert.equal(x.atomic.current.size, 3);
  x.atomic.dispose();
  assert.ok(x.bitmaps.every((image) => image.closed === 1));
  results.push(
    'PASS atomic group commit and AB -> ABC -> AB -> ABC shares all completed original textures',
  );
});

// Fetch cancellation is real; cancellation during non-cancellable bitmap decoding awaits cleanup.
await run('atomic_partial_failure_resume', async () => {
  const x = fixture(),
    lateFailure = deferred();
  x.f.fetch = (url) =>
    url === '/b' ? lateFailure.promise : Promise.resolve(x.response(url));
  x.atomic.request('AB', [source('/a'), source('/b')]);
  await flush();
  assert.equal(x.atomic.cache.has('/a'), true);
  assert.equal(x.atomic.current.size, 0);
  lateFailure.resolve({ ok: false });
  await flush();
  assert.equal(x.atomic.failureCount, 1);
  x.f.fetch = (url) => Promise.resolve(x.response(url));
  await x.tick(2000);
  x.atomic.request('AB', [source('/a'), source('/b')]);
  await flush();
  assert.equal(x.atomic.ready, 'AB');
  assert.equal(x.calls.filter((call) => call.url === '/a').length, 1);
  assert.equal(x.calls.filter((call) => call.url === '/b').length, 2);
  x.atomic.dispose();
  results.push(
    'PASS failed group retains successful image progress and retries only the missing image',
  );
});

// A fully cached latest group can display immediately while obsolete decode cleanup finishes.
await run('atomic_cached_latest_immediate', async () => {
  const x = fixture();
  x.atomic.request('A', [source('/a')]);
  await flush();
  x.atomic.request('', []);
  const decode = deferred();
  x.f.decode = (blob) =>
    blob.url === '/old' ? decode.promise : Promise.resolve(x.bitmap(blob.url));
  x.atomic.request('old', [source('/old')]);
  await flush();
  x.atomic.request('A', [source('/a')]);
  assert.equal(x.atomic.ready, 'A');
  assert.equal(x.atomic.current.has('/a'), true);
  assert.equal(x.calls.length, 2);
  decode.resolve(x.bitmap('/old'));
  await flush();
  assert.equal(x.atomic.pending, null);
  assert.equal(x.atomic.ready, 'A');
  x.atomic.dispose();
  results.push(
    'PASS fully cached latest group commits immediately without starting another decode job',
  );
});

// Fetch cancellation is real; cancellation during non-cancellable bitmap decoding awaits cleanup.
await run('atomic_cancel_during_decode', async () => {
  const x = fixture(),
    decode = deferred();
  x.f.decode = (blob) =>
    blob.url === '/old' ? decode.promise : Promise.resolve(x.bitmap(blob.url));
  x.atomic.request('old', [source('/old')]);
  await flush();
  x.atomic.request('middle', [source('/middle')]);
  x.atomic.request('latest', [source('/latest')]);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.calls.length, 1);
  assert.equal(x.atomic.pendingKey, 'old');
  const oldBitmap = x.bitmap('/old');
  decode.resolve(oldBitmap);
  await flush();
  await flush();
  assert.equal(oldBitmap.closed, 1);
  assert.equal(x.calls.length, 2);
  assert.equal(x.calls[1].url, '/latest');
  assert.equal(x.atomic.ready, 'latest');
  assert.ok(x.events.indexOf('close:/old') < x.events.indexOf('fetch:/latest'));
  assert.equal(x.atomic.reservedBytes, 0);
  x.atomic.dispose();
  results.push(
    'PASS latest target starts after old bitmap cleanup; obsolete middle never loads; no overlapping jobs',
  );
});

// A timeout aborts the actual fetch and permits the same wanted group to retry.
await run('atomic_fetch_timeout', async () => {
  const x = fixture();
  let healthy = false;
  x.f.fetch = (url, { signal }) =>
    healthy
      ? Promise.resolve(x.response(url))
      : new Promise((resolve, reject) =>
          signal.addEventListener(
            'abort',
            () => reject(new DOMException('Timed out', 'AbortError')),
            { once: true },
          ),
        );
  x.atomic.request('A', [source('/a')]);
  await x.tick(44999);
  assert.equal(x.calls[0].signal.aborted, false);
  await x.tick(1);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.atomic.pending, null);
  assert.equal(x.atomic.failureCount, 1);
  assert.equal(x.atomic.stats().retryInMs, 2000);
  healthy = true;
  await x.tick(2000);
  x.atomic.request('A', [source('/a')]);
  await flush();
  assert.equal(x.atomic.ready, 'A');
  assert.equal(x.calls.length, 2);
  x.atomic.dispose();
  results.push(
    'PASS 45s timeout aborts fetch, releases reservation, and same-key retry succeeds',
  );
});

// One failed worker must stop its sibling instead of downloading the rest of a doomed group.
await run('atomic_sibling_failure_abort', async () => {
  const x = fixture();
  x.f.fetch = (url, { signal }) =>
    url === '/bad'
      ? Promise.resolve({ ok: false })
      : new Promise((resolve, reject) =>
          signal.addEventListener(
            'abort',
            () => reject(new DOMException('Cancelled', 'AbortError')),
            { once: true },
          ),
        );
  x.atomic.request('bad-group', [
    source('/bad'),
    source('/slow'),
    source('/never'),
  ]);
  await flush();
  assert.equal(x.calls.length, 2);
  assert.equal(x.calls[1].signal.aborted, true);
  assert.equal(x.atomic.pending, null);
  assert.equal(x.atomic.reservedBytes, 0);
  assert.equal(x.atomic.current.size, 0);
  x.atomic.dispose();
  results.push(
    'PASS first worker failure aborts sibling and prevents remaining image downloads',
  );
});

// LRU may evict old cache images, but never current/wanted images needed for a whole-group commit.
await run('atomic_lru_budget', async () => {
  const x = fixture({ cacheBudgetBytes: 20 * 1048576 });
  for (const key of ['A', 'B', 'C', 'D']) {
    x.atomic.request(key, [source('/' + key)]);
    await flush();
    await x.tick(1);
    assert.ok(
      x.atomic.cacheBytes + x.atomic.reservedBytes <= x.atomic.cacheBudgetBytes,
    );
  }
  assert.equal(x.atomic.cache.size, 3);
  assert.equal(x.atomic.cache.has('/A'), false);
  assert.equal(x.bitmaps.find((image) => image.url === '/A').closed, 1);
  assert.equal(x.atomic.ready, 'D');
  assert.equal(x.atomic.current.has('/D'), true);
  x.atomic.dispose();
  assert.ok(x.bitmaps.every((image) => image.closed === 1));
  results.push(
    'PASS LRU stays within budget and closes evicted/disposed bitmaps exactly once',
  );
});

// The shipped region union fits the default cache including mipmap allocation.
await run('atomic_actual_original_union', async () => {
  const manifest = JSON.parse(
    fs.readFileSync(
      root + '/public/models/exteriors/baseline-texture-regions.json',
      'utf8',
    ),
  );
  const images = [
    ...new Map(
      manifest.regions
        .flatMap((r) => r.textures)
        .filter((t) => Math.max(t.width, t.height) > 512)
        .map((t) => [t.url, t]),
    ).values(),
  ];
  const x = fixture();
  x.atomic.request('all-source-originals', images);
  await flush();
  await flush();
  assert.ok(images.length >= 22);
  assert.equal(x.atomic.ready, 'all-source-originals');
  assert.equal(x.atomic.cache.size, images.length);
  assert.ok(x.atomic.cacheBytes <= 128 * 1048576);
  results.push(
    'PASS all ' +
      manifest.regions.length +
      ' real regions: ' +
      images.length +
      ' original images / ' +
      (x.atomic.cacheBytes / 1048576).toFixed(4) +
      'MiB with mipmaps, under 128MiB',
  );
  x.atomic.dispose();
});

// dispose may occur after HTTP success but before the bitmap promise settles.
await run('atomic_empty_set_idempotent', async () => {
  const x = fixture(),
    binding = x.bind('/a');
  const version = binding.material.version;
  for (let i = 0; i < 20; i++) x.atomic.request('', []);
  assert.equal(binding.material.version, version);
  assert.equal(x.calls.length, 0);
  x.atomic.dispose();
  results.push(
    'PASS unchanged empty region set does not dirty every baseline material repeatedly',
  );
});

// dispose may occur after HTTP success but before the bitmap promise settles.
await run('atomic_dispose_late_decode', async () => {
  const x = fixture(),
    decode = deferred();
  x.f.decode = () => decode.promise;
  x.atomic.request('A', [source('/a')]);
  await flush();
  x.atomic.dispose();
  const image = x.bitmap('/a');
  decode.resolve(image);
  await flush();
  assert.equal(image.closed, 1);
  assert.equal(x.atomic.cache.size, 0);
  assert.equal(x.atomic.current.size, 0);
  assert.equal(x.atomic.pending, null);
  assert.equal(x.atomic.reservedBytes, 0);
  x.atomic.request('B', [source('/b')]);
  assert.equal(x.calls.length, 1);
  results.push(
    'PASS dispose during decode prevents any late commit/restart and closes bitmap once',
  );
});

await run('atomic_old_new_budget_transition', async () => {
  const x = fixture({ cacheBudgetBytes: 12 * 1048576 }),
    bindings = ['/a', '/b', '/c', '/d'].map((url) => x.bind(url));
  x.atomic.request('AB', [source('/a'), source('/b')]);
  await flush();
  assert.equal(x.atomic.current.size, 2);
  const waiting = new Map();
  x.f.fetch = (url) => {
    const d = deferred();
    waiting.set(url, d);
    return d.promise;
  };
  x.atomic.request('CD', [source('/c'), source('/d')]);
  assert.equal(x.atomic.current.size, 0);
  assert.equal(bindings[0].material.map, bindings[0].low);
  assert.equal(bindings[1].material.map, bindings[1].low);
  assert.ok(x.atomic.cacheBytes + x.atomic.reservedBytes <= 12 * 1048576);
  waiting.get('/c').resolve(x.response('/c'));
  await flush();
  assert.equal(x.atomic.current.size, 0);
  waiting.get('/d').resolve(x.response('/d'));
  await flush();
  assert.equal(x.atomic.ready, 'CD');
  assert.equal(x.atomic.current.size, 2);
  assert.notEqual(bindings[2].material.map, bindings[2].low);
  assert.notEqual(bindings[3].material.map, bindings[3].low);
  assert.ok(x.atomic.cacheBytes <= 12 * 1048576);
  x.atomic.dispose();
  results.push(
    'PASS two complete groups cannot coexist: old group returns to baseline atomically, valid new group completes within budget',
  );
});

await run('atomic_absolute_overbudget_keeps_previous', async () => {
  const x = fixture({ cacheBudgetBytes: 12 * 1048576 }),
    a = x.bind('/a'),
    b = x.bind('/b');
  x.atomic.request('AB', [source('/a'), source('/b')]);
  await flush();
  const previousA = a.material.map,
    previousB = b.material.map;
  x.atomic.request('CDE', [source('/c'), source('/d'), source('/e')]);
  await flush();
  assert.equal(x.atomic.ready, 'AB');
  assert.equal(x.atomic.current.size, 2);
  assert.equal(a.material.map, previousA);
  assert.equal(b.material.map, previousB);
  assert.equal(x.atomic.pending, null);
  assert.ok(x.atomic.failureCount > 0);
  assert.ok(x.atomic.cacheBytes + x.atomic.reservedBytes <= 12 * 1048576);
  x.atomic.dispose();
  results.push(
    'PASS absolutely over-budget new group preserves the previous complete group without partial commit',
  );
});

await run('atomic_release_invisible_keeps_shared_visible_sources', async () => {
  const x=fixture(),a=x.bind('/a'),b=x.bind('/b');
  x.atomic.request('AB',[source('/a'),source('/b')]);await flush();
  const retained=a.material.map,removed=b.material.map;
  const calls=x.calls.length;
  x.atomic.releaseInvisibleSources(new Set(['/a']));
  assert.equal(a.material.map,retained);assert.equal(b.material.map,b.low);
  assert.equal(retained.image.closed,0);assert.equal(removed.image.closed,1);
  assert.equal(x.atomic.cache.size,1);assert.equal(x.atomic.current.size,1);
  x.atomic.releaseInvisibleSources(new Set(['/a']));assert.equal(removed.image.closed,1);
  x.atomic.request('A',[source('/a')]);await flush();
  assert.equal(x.atomic.ready,'A');assert.equal(x.calls.length,calls);
  x.atomic.dispose();assert.equal(retained.image.closed,1);
  results.push('PASS atlas without any visible source user is unbound and closed once; shared visible atlas survives and completes without refetch');
});

await run('atomic_invisible_pending_keeps_reservation_until_decode_drains', async () => {
  const x=fixture(),gate=deferred();let late;
  x.f.decode=async blob=>{if(blob.url==='/b'){await gate.promise;late=x.bitmap('/b');return late;}return x.bitmap(blob.url);};
  x.bind('/a');x.bind('/b');x.atomic.request('AB',[source('/a'),source('/b')]);await flush();
  assert.ok(x.atomic.pending);assert.ok(x.atomic.reservedBytes>0);
  const reserved=x.atomic.reservedBytes;
  x.atomic.releaseInvisibleSources(new Set(['/a']));x.atomic.request('A',[source('/a')]);
  assert.equal(x.atomic.reservedBytes,reserved);assert.equal(x.atomic.pending.signal.aborted,true);
  assert.equal(x.atomic.ready,'A');gate.resolve();await flush();
  assert.equal(late.closed,1);assert.equal(x.atomic.reservedBytes,0);assert.equal(x.atomic.pending,null);
  assert.equal(x.atomic.cache.has('/b'),false);assert.equal(x.atomic.ready,'A');x.atomic.dispose();
  results.push('PASS cancelled invisible bitmap keeps its reservation until native decode drains and never enters the replacement cache');
});

const publicData = (path) =>
  JSON.parse(fs.readFileSync(root + '/public/' + path, 'utf8'));
const bundleManifest = publicData('models/exteriors/manifest.json');
const sourceRegions = publicData(
  'models/exteriors/baseline-texture-regions.json',
);
const sourceCatalog = publicData('models/texture-detail-manifest.json');
const sourceFootprints = publicData('data/building-footprints.json');
const sourceHeightGrid = publicData('terrain/height-grid-5m.json');
const sourceRegistry = publicData('data/entity-registry.json');
const priorityFixture = fixture();
const { visibleDetails, StableDetailChoice, textureDetailPlan } =
  priorityFixture.load('detail-priority');
const { textureMipBytes } = priorityFixture.load('source-types');
const cameraPose = {
  position: [650, 500, -750],
  target: [420, 120, -1410],
  fov: 42,
  aspect: 16 / 9,
  height: 800,
};
const camera = () => {
  const c = new THREE.PerspectiveCamera(
    cameraPose.fov,
    cameraPose.aspect,
    0.5,
    9000,
  );
  c.position.fromArray(cameraPose.position);
  c.lookAt(...cameraPose.target);
  c.updateMatrixWorld();
  return c;
};
async function sceneFixture(previousSelection = '') {
  const x = fixture();
  x.f.fetch = async (url) => ({
    json: async () =>
      url.includes('texture-detail-manifest') ? sourceCatalog : sourceRegions,
  });
  await x.atomic.init();
  x.calls.length = 0;
  const { CampusScene } = x.load('scene'),
    { EntityRegistry } = x.load('entity-registry');
  const scene = Object.create(CampusScene.prototype),
    exteriorRequests = [],
    textureRequests = [];
  const geometry = new THREE.Group();
  for (const tile of x.atomic.catalog.values()) {
    const original = new THREE.Group();
    original.name = tile.id;
    geometry.add(original);
  }
  Object.assign(scene, {
    textures: x.atomic,
    geometry,
    qualityLevel: 'high',
    footprints: sourceFootprints.footprints,
    grid: sourceHeightGrid,
    camera: camera(),
    host: { clientHeight: 800 },
    registry: new EntityRegistry(sourceRegistry),
    opened: null,
    selectedId: previousSelection,
    controls: { target: new THREE.Vector3(...cameraPose.target) },
    detailChoice: new StableDetailChoice(),
    detailSeen: new Map(),
    detailCandidates: [],
    lastDetailUpdate: 0,
    detailPool: new (x.load('detail-resource-pool').DetailResourcePool)(1536*1048576),
    exteriorViewPlanner: new (x.load('exterior-view-plan').ExteriorViewPlanner)(),
    roadCoveragePlanner: new (x.load('road-coverage-plan').RoadCoveragePlanner)(x.load('road-coverage-plan').parseRoadProtection(publicData('models/hires/road-protection.json'))),
    exteriors: new (x.load('coherent-exteriors').CoherentExteriors)(new THREE.Scene(),new (x.load('spatial-masks').SpatialMasks)(),()=>{}),
    meshDetail: new (x.load('campus-mesh-detail').CampusMeshDetail)(new THREE.Scene(),geometry,new (x.load('spatial-masks').SpatialMasks)(),()=>{}),
  });
  scene.exteriors.bundles=bundleManifest.bundles;
  scene.exteriors.request=bundles=>exteriorRequests.push(bundles.map(b=>b.id));
  scene.meshDetail.patches=publicData('models/hires/manifest.json').patches;
  scene.meshDetail.request=choices=>{scene.meshRequests=choices;};
  x.atomic.request = (key, images) =>
    textureRequests.push({ key, urls: images.map((t) => t.url) });
  scene.prepareTextureGroups();
  return { scene, x, exteriorRequests, textureRequests };
}

await run('visibility_real_three_building_view', async () => {
  const { scene } = await sceneFixture();
  const candidates = bundleManifest.bundles.map((b) => ({
    id: b.id,
    bounds: scene.detailBounds(b.buildingId, b.bounds),
  }));
  const visible = visibleDetails(scene.camera, candidates, 800, 40);
  for (const id of ['campus-01', 'campus-18', 'campus-22'])
    assert.ok(
      visible.some((item) => item.id === id),
      id + ' must remain a visible candidate',
    );
  results.push(
    'PASS real camera simultaneously sees Academic/CYT/Shaw: ' +
      JSON.stringify(
        visible
          .filter((item) =>
            ['campus-01', 'campus-18', 'campus-22'].includes(item.id),
          )
          .map((item) => ({ id: item.id, pixels: Math.round(item.pixels) })),
      ),
  );
});

await run('scene_same_view_ignores_old_selection_and_pivot', async () => {
  const fresh = await sceneFixture(),
    old = await sceneFixture('b00000000000000000003');
  old.scene.controls.target.set(10000, 0, 10000);
  fresh.scene.updateDetails(1000);
  old.scene.updateDetails(1000);
  assert.equal(
    JSON.stringify(old.exteriorRequests),
    JSON.stringify(fresh.exteriorRequests),
  );
  assert.equal(
    JSON.stringify(old.textureRequests),
    JSON.stringify(fresh.textureRequests),
  );
  assert.ok(old.scene.detailCandidates.includes('campus-22'));
  assert.ok(old.scene.detailCandidates.includes('campus-18'));
  assert.ok(old.exteriorRequests[0].includes('campus-01'));
  assert.ok(old.scene.exteriors.previewPlan(bundleManifest.bundles.filter(b=>old.exteriorRequests[0].includes(b.id)),old.scene.detailPool.grants.exterior).bytes<=old.scene.detailPool.grants.exterior);
  results.push(
    'PASS current Scene.updateDetails gives identical whole-group requests for fresh vs stale selected history and a remote orbit pivot',
  );
});

await run('visible_behind_camera_excluded', async () => {
  const c = camera(),
    away = c.position
      .clone()
      .sub(new THREE.Vector3(...cameraPose.target))
      .add(c.position);
  c.lookAt(away);
  const visible = visibleDetails(c, bundleManifest.bundles, 800, 40);
  assert.equal(visible.length, 0);
  results.push('PASS all real campus bundles behind the camera are excluded');
});

await run('visible_moving_camera_stable_identity', async () => {
  const choice = new StableDetailChoice(),
    c = camera(),
    identities = [];
  for (let i = 0; i < 80; i++) {
    c.position.x = cameraPose.position[0] + Math.sin(i * 0.2) * 0.08;
    c.position.z = cameraPose.position[2] + Math.cos(i * 0.2) * 0.08;
    c.lookAt(...cameraPose.target);
    identities.push(
      choice.choose(visibleDetails(c, bundleManifest.bundles, 800, 40), i * 16),
    );
  }
  assert.equal(identities[35], 'campus-01');
  assert.ok(identities.slice(35).every((id) => id === 'campus-01'));
  const f = await sceneFixture();
  for (let i = 0; i < 12; i++) {
    f.scene.camera.position.x = cameraPose.position[0] + Math.sin(i) * 0.04;
    f.scene.camera.lookAt(...cameraPose.target);
    f.scene.updateDetails(1000 + i * 400);
  }
  assert.equal(new Set(f.exteriorRequests.map((ids) => ids.join('|'))).size, 1);
  assert.equal(new Set(f.textureRequests.map((plan) => plan.key)).size, 1);
  results.push(
    'PASS continuous small camera motion selects after 500ms and does not repeatedly change exterior/texture group identities',
  );
});

await run('whole_region_budget_accept_or_defer', async () => {
  const { scene } = await sceneFixture(),
    academic = scene.textureGroups.find((g) => g.id === 'campus-01');
  assert.ok(academic);
  const high = [
    ...new Map(
      academic.textures
        .filter((t) => Math.max(t.width, t.height) > 512)
        .map((t) => [t.url, t]),
    ).values(),
  ];
  const fullCost = high.reduce(
      (sum, t) => sum + textureMipBytes(t.width, t.height),
      0,
    ),
    visible = [{ id: academic.id, score: 10, pixels: 200, distance: 50 }];
  const rejected = textureDetailPlan([academic], visible, fullCost - 1);
  assert.equal(rejected.images.length, 0);
  assert.equal(rejected.accepted.length, 0);
  assert.equal(rejected.deferred[0], academic.id);
  const accepted = textureDetailPlan([academic], visible, fullCost);
  assert.equal(accepted.images.length, high.length);
  assert.equal(accepted.bytes, fullCost);
  assert.equal(accepted.accepted[0], academic.id);
  results.push(
    'PASS actual Academic region is wholly deferred one byte below its budget and wholly accepted at its exact mip allocation',
  );
});

await run('real_context_groups_preserve_known_whole_regions', async () => {
  const { scene } = await sceneFixture();
  const contexts = scene.textureGroups.filter((g) =>
    g.id.startsWith('context:'),
  );
  assert.ok(contexts.length > 0);
  const catalogById = new Map(sourceCatalog.tiles.map((t) => [t.id, t]));
  let checked = 0;
  for (const context of contexts) {
    const urls = new Set(context.textures.map((t) => t.url));
    for (const region of sourceRegions.regions) {
      const touches = region.baselineIds.some((id) => {
        const tile = catalogById.get(id);
        return (
          tile &&
          'context:' +
            Math.floor(tile.center[0] / 300) +
            ':' +
            Math.floor(tile.center[2] / 300) ===
            context.id
        );
      });
      if (touches) {
        for (const texture of region.textures)
          assert.ok(
            urls.has(texture.url),
            context.id + ' cannot truncate ' + region.id,
          );
        checked++;
      }
    }
  }
  const visible = visibleDetails(scene.camera, scene.textureGroups, 800, 56);
  const plan = textureDetailPlan(scene.textureGroups, visible);
  assert.ok(plan.bytes <= 128 * 1048576);
  results.push(
    'PASS real scene context grouping retains all textures of ' +
      checked +
      ' intersecting known-region references; visible plan remains within budget',
  );
});

await run('synthetic_24_atlas_exact_128mib_boundary', async () => {
  const images = Array.from({ length: 24 }, (_, i) =>
    source('/synthetic-budget-atlas-' + i),
  );
  assert.equal(textureMipBytes(1024, 1024), 5592404);
  const group = {
    id: 'synthetic-24',
    bounds: bundleManifest.bundles[0].bounds,
    textures: images,
  };
  const plan = textureDetailPlan(
    [group],
    [{ id: group.id, score: 100, pixels: 500, distance: 10 }],
    128 * 1048576,
  );
  assert.equal(plan.images.length, 24);
  assert.equal(plan.bytes, 134217696);
  assert.equal(plan.deferred.length, 0);
  const x = fixture();
  x.atomic.request(plan.key, plan.images);
  await flush();
  await flush();
  assert.equal(x.atomic.ready, plan.key);
  assert.equal(x.atomic.current.size, 24);
  assert.equal(x.atomic.cacheBytes, plan.bytes);
  assert.equal(x.atomic.failureCount, 0);
  x.atomic.dispose();
  results.push(
    'PASS synthetic 24 x 1024-square atlas boundary fits 128MiB exactly using finite mip chains; no rounded-up last-source starvation',
  );
});

function meshFixture() {
  const x = fixture(),
    parsed = [],
    disposed = [];
  x.f.parse = null;
  x.f.fetch = async (url) => ({
    ok: true,
    arrayBuffer: async () => ({ url }),
    blob: async () => ({ url }),
  });
  function model(url, parser) {
    const bitmap = x.bitmap(url),
      texture = new THREE.Texture(bitmap);
    const material = new THREE.MeshBasicMaterial({ map: texture });
    const geometry = new THREE.BoxGeometry();
    geometry.addEventListener('dispose', () => disposed.push(url));
    const mesh = new THREE.Mesh(geometry, material),
      scene = new THREE.Group();
    scene.add(mesh);
    parser.associations.set(mesh, {});
    parser.associations.set(material, {});
    parser.associations.set(texture, {});
    return { scene };
  }
  class ControlledGLTFLoader {
    constructor(manager) {
      this.manager = manager;
    }
    register(plugin) {
      this.plugin = plugin;
    }
    parseAsync(data) {
      const textureLoader = Object.create(THREE.ImageBitmapLoader.prototype);
      textureLoader.manager = this.manager;
      textureLoader.load = (url, onLoad, _onProgress, onError) =>
        x.f.imageLoad?.(this.manager, url, onLoad, onError);
      const parser = {
        associations: new Map(),
        fileLoader: { abort() {} },
        textureLoader,
      };
      this.plugin(parser);
      parsed.push({ url: data.url, parser, manager: this.manager });
      return x.f.parse
        ? x.f.parse(data, parser, this.manager)
        : Promise.resolve(model(data.url, parser));
    }
  }
  x.f.modules['three/addons/loaders/GLTFLoader.js'] = {
    GLTFLoader: ControlledGLTFLoader,
  };
  const { SpatialMasks } = x.load('spatial-masks');
  const masks = new SpatialMasks(),
    baseline = new THREE.Group();
  const mesh = new (x.load('campus-mesh-detail').CampusMeshDetail)(
    new THREE.Scene(),
    baseline,
    masks,
    () => {},
  );
  mesh.setBudget(128 * 1048576);
  function choice(id, count = 1, levelName = 'high', patch) {
    const tiles = Array.from({ length: count }, (_, i) => ({
      url: id + '-' + i + '.glb',
      matrix: new THREE.Matrix4().makeTranslation(i * 12, 0, 0).toArray(),
      textureDimensions: [[1024, 1024]],
      triangles: 12,
    }));
    const level = { tiles, triangles: count * 12 };
    if (!patch)
      patch = {
        id,
        bounds: { min: [0, 0, 0], max: [30, 20, 30] },
        baselineIds: ['baseline:' + id],
        levels: { high: level },
      };
    if (!baseline.getObjectByName(patch.baselineIds[0])) {
      const object = new THREE.Group();
      object.name = patch.baselineIds[0];
      baseline.add(object);
    }
    return {
      key: patch.id + '/' + levelName,
      patch,
      level,
      bytes: count * textureMipBytes(1024, 1024),
    };
  }
  return { ...x, mesh, masks, baseline, choice, model, parsed, disposed };
}

await run('mesh_complete_frontier_and_late_baseline', async () => {
  const x = meshFixture(),
    second = deferred(),
    choice = x.choice('A', 2);
  x.f.fetch = (url) =>
    url.endsWith('A-1.glb')
      ? second.promise
      : Promise.resolve({ ok: true, arrayBuffer: async () => ({ url }) });
  x.mesh.request([choice]);
  await flush();
  assert.equal(x.mesh.progress, 1);
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.baseline.children[0].visible, true);
  second.resolve({
    ok: true,
    arrayBuffer: async () => ({ url: '/models/hires/A-1.glb' }),
  });
  await flush();
  assert.equal(x.mesh.visible.get('A').group.children.length, 2);
  assert.equal(x.baseline.children[0].visible, false);
  const placed = x.mesh.visible.get('A').group.children[1];
  placed.updateWorldMatrix(true, false);
  assert.equal(new THREE.Vector3().setFromMatrixPosition(placed.matrixWorld).x, 12);
  assert.equal(placed.matrixAutoUpdate, false, 'Native placement must retain its source matrix without TRS decomposition');
  const late = new THREE.Group();
  late.name = choice.patch.baselineIds[0];
  x.baseline.add(late);
  x.mesh.syncBaseline();
  assert.equal(late.visible, false);
  x.mesh.request([]);
  assert.ok(x.baseline.children.every((object) => object.visible));
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  results.push(
    'PASS complete two-tile frontier commits once, applies source matrices, hides late baseline arrivals, and restores all baseline tiles together',
  );
});

await run('mesh_same_region_automatic_retry', async () => {
  const x = meshFixture(),
    choice = x.choice('A');
  let attempts = 0;
  x.f.fetch = async (url) =>
    ++attempts < 4
      ? { ok: false }
      : { ok: true, arrayBuffer: async () => ({ url }) };
  x.mesh.request([choice]);
  await flush();
  assert.equal(attempts, 1);
  assert.equal(x.mesh.visible.size, 0);
  await x.tick(1999);
  assert.equal(attempts, 1);
  await x.tick(1);
  assert.equal(attempts, 2);
  await x.tick(4999);
  assert.equal(attempts, 2);
  await x.tick(1);
  assert.equal(attempts, 3);
  await x.tick(14999);
  assert.equal(attempts, 3);
  await x.tick(1);
  assert.equal(attempts, 4);
  assert.equal(x.mesh.visible.get('A').key, choice.key);
  assert.equal(x.mesh.failures, 3);
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS unchanged region retries automatically at 2/5/15s without another request or camera movement',
  );
});

await run('mesh_cancel_waits_for_parse_and_latest_only', async () => {
  const x = meshFixture(),
    old = deferred(),
    choices = ['A', 'B', 'C'].map((id) => x.choice(id));
  x.f.parse = (data, parser) =>
    data.url.includes('A-')
      ? old.promise
      : Promise.resolve(x.model(data.url, parser));
  x.mesh.request([choices[0]]);
  await flush();
  x.mesh.request([choices[1]]);
  x.mesh.request([choices[2]]);
  assert.equal(x.calls.length, 1);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.mesh.pending.key, 'A/high');
  old.resolve(x.model('/models/hires/A-0.glb', x.parsed[0].parser));
  await flush();
  assert.equal(x.calls.length, 2);
  assert.ok(x.calls[1].url.includes('C-'));
  assert.equal(x.mesh.visible.has('C'), true);
  assert.ok(
    x.events.indexOf('close:/models/hires/A-0.glb') <
      x.events.indexOf('fetch:/models/hires/C-0.glb'),
  );
  assert.equal(x.bitmaps[0].closed, 1);
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  results.push(
    'PASS actual request signal aborts, late parse resources close before latest C starts, obsolete B never fetches',
  );
});

await run('mesh_failed_parser_drains_orphan_bitmap', async () => {
  const x = meshFixture(),
    choices = ['A', 'B'].map((id) => x.choice(id));
  let finish;
  x.f.imageLoad = (manager, url, onLoad) => {
    manager.itemStart(url);
    finish = () => {
      onLoad(x.bitmap('orphan-image'));
      manager.itemEnd(url);
    };
  };
  x.f.parse = (data, parser) => {
    if (data.url.includes('B-'))
      return Promise.resolve(x.model(data.url, parser));
    parser.textureLoader.load('late-image', () => {});
    return Promise.reject(
      new Error('one dependency failed while another bitmap still decodes'),
    );
  };
  x.mesh.request([choices[0]]);
  await flush();
  x.mesh.request([choices[1]]);
  assert.equal(x.calls.length, 1);
  assert.equal(x.mesh.pending.key, 'A/high');
  assert.equal(x.calls[0].signal.aborted, true);
  finish();
  await flush();
  assert.equal(x.mesh.visible.has('B'), true);
  assert.equal(
    x.bitmaps.find((bitmap) => bitmap.url === 'orphan-image').closed,
    1,
  );
  assert.ok(
    x.events.indexOf('close:orphan-image') <
      x.events.indexOf('fetch:/models/hires/B-0.glb'),
  );
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS rejected parser drains outstanding manager work and closes its orphan bitmap before the next region starts',
  );
});

await run('mesh_image_failure_diagnostics_preserve_arrival_order', async () => {
  for (const cancelledFirst of [false, true]) {
    const x = meshFixture(), a = x.choice('diagnostic-A'), b = x.choice('diagnostic-B');
    let failImage;
    x.f.imageLoad = (_manager, _url, _onLoad, onError) => { failImage = onError; };
    x.f.parse = (data, parser, manager) => {
      if (data.url.includes('diagnostic-B-')) return Promise.resolve(x.model(data.url, parser));
      return new Promise((resolve) => {
        const imageURL = 'blob:https://campus.invalid/mesh-texture';
        manager.itemStart(imageURL);
        parser.textureLoader.load(imageURL, undefined, undefined, () => {
          manager.itemError(imageURL);
          manager.itemEnd(imageURL);
          resolve(x.model(data.url, parser));
        });
      });
    };
    x.mesh.request([a]);
    await flush();
    if (cancelledFirst) x.mesh.request([b]);
    else {
      const manager = x.mesh.pending.manager, imageError = manager.imageError.bind(manager);
      manager.imageError = (...args) => {
        const diagnostic = imageError(...args);
        x.mesh.request([b]);
        return diagnostic;
      };
    }
    failImage(new DOMException('ImageBitmap could not be allocated', 'InvalidStateError'));
    await flush();
    assert.equal(x.mesh.visible.has(a.patch.id), false);
    assert.equal(x.mesh.visible.has(b.patch.id), true);
    assert.equal(x.mesh.failures, cancelledFirst ? 0 : 1);
    const diagnostic = x.mesh.stats().lastImageFailure;
    assert.equal(diagnostic.lane, 'mesh');
    assert.equal(diagnostic.groupId, a.key);
    assert.equal(diagnostic.sourceAsset, '/models/hires/diagnostic-A-0.glb');
    assert.equal(diagnostic.imageURL, 'blob:mesh-texture');
    assert.equal(diagnostic.outcome, cancelledFirst ? 'failed-after-cancel' : 'failed');
    assert.equal(diagnostic.aborted, cancelledFirst);
    assert.equal(diagnostic.stale, cancelledFirst);
    x.mesh.dispose();
    x.masks.dispose();
    assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  }
  results.push('PASS real mesh lifecycle records source GLB for blob failures; failure before cancellation counts, allocation rejection after cancellation stays identifiable, neither commits old geometry and both drain before latest source');
});

await run('mesh_fetch_timeout_and_dispose_retry', async () => {
  const x = meshFixture(),
    choice = x.choice('A');
  x.f.fetch = (url, { signal }) =>
    new Promise((resolve, reject) =>
      signal.addEventListener(
        'abort',
        () => reject(new DOMException('Timeout', 'AbortError')),
        { once: true },
      ),
    );
  x.mesh.request([choice]);
  await x.tick(44999);
  assert.equal(x.calls[0].signal.aborted, false);
  await x.tick(1);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.mesh.pending, null);
  assert.equal(x.mesh.failures, 1);
  x.mesh.dispose();
  await x.tick(30000);
  assert.equal(x.calls.length, 1);
  assert.equal(x.mesh.visible.size, 0);
  x.masks.dispose();
  results.push(
    'PASS per-source 45s timeout aborts fetch and disposal cancels its scheduled automatic retry',
  );
});

await run('mesh_cache_return_and_budget_baseline', async () => {
  const x = meshFixture(),
    a = x.choice('A'),
    b = x.choice('B');
  x.mesh.request([a]);
  await flush();
  x.mesh.request([b]);
  await flush();
  x.mesh.request([a]);
  await flush();
  assert.equal(x.calls.length, 2);
  assert.equal(x.mesh.cacheHits, 1);
  assert.equal(x.mesh.visible.has('A'), true);
  assert.ok(x.mesh.resident() <= x.mesh.budgetBytes);
  x.mesh.setBudget(0, []);
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.mesh.cache.size, 0);
  assert.ok(x.baseline.children.every((object) => object.visible));
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS returning to a cached complete region performs no network I/O; zero mesh budget releases all resident groups and restores baseline',
  );
});

await run('mesh_budget_drop_during_decode', async () => {
  const x = meshFixture(),
    pending = deferred(),
    choice = x.choice('A');
  x.f.parse = () => pending.promise;
  x.mesh.request([choice]);
  await flush();
  x.mesh.setBudget(0, []);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.baseline.children[0].visible, true);
  assert.equal(x.mesh.visible.size, 0);
  pending.resolve(x.model('/models/hires/A-0.glb', x.parsed[0].parser));
  await flush();
  assert.equal(x.mesh.pending, null);
  assert.equal(x.mesh.resident(), 0);
  assert.equal(x.calls.length, 1);
  assert.equal(x.bitmaps[0].closed, 1);
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS a quality downgrade during decoding keeps baseline visible, drains the cancelled region and does not restart an over-budget request',
  );
});

await run('mesh_real_frontiers_quality_budgets', async () => {
  const x = meshFixture(),
    manifest = publicData('models/hires/manifest.json');
  const { qualityProfiles } = x.load('quality');
  x.mesh.patches = manifest.patches;
  const accepted = {};
  for (const level of ['smooth', 'balanced', 'high', 'ultra']) {
    const profile = qualityProfiles[level];
    x.mesh.setBudget(profile.meshMiB * 1048576);
    let choices;
    x.mesh.request = (next) => {
      choices = next;
    };
    x.mesh.update(
      camera(),
      800,
      profile,
      10000 + ['smooth', 'balanced', 'high', 'ultra'].indexOf(level) * 3000,
    );
    assert.ok(
      choices.reduce((sum, choice) => sum + choice.bytes, 0) <=
        profile.meshMiB * 1048576,
    );
    for (const choice of choices) {
      assert.ok(manifest.patches.includes(choice.patch));
      assert.ok(
        choice.level === choice.patch.levels.high ||
          choice.level === choice.patch.levels.fine,
        'Only a complete published frontier may be selected; Auto near can now use fine',
      );
      assert.equal(
        choice.bytes,
        choice.level.tiles.reduce(
          (sum, tile) =>
            sum +
            tile.textureDimensions.reduce(
              (bytes, dimensions) => bytes + textureMipBytes(...dimensions),
              0,
            ),
          (choice.level.mask ?? choice.patch.mask)
            ? (choice.level.mask ?? choice.patch.mask).width *
                (choice.level.mask ?? choice.patch.mask).height *
                4
            : 0,
        ),
      );
    }
    accepted[level] = choices.map((choice) => ({
      key: choice.key,
      tiles: choice.level.tiles.length,
      mipBytes: choice.bytes,
    }));
  }
  assert.equal(accepted.smooth.length, 0);
  assert.ok(accepted.ultra.length > 0);
  const finePatch = manifest.patches.find((patch) => patch.levels.fine);
  assert.ok(finePatch);
  const center = new THREE.Vector3()
    .addVectors(
      new THREE.Vector3(...finePatch.bounds.min),
      new THREE.Vector3(...finePatch.bounds.max),
    )
    .multiplyScalar(0.5);
  const closeCamera = camera();
  closeCamera.position.copy(center).add(new THREE.Vector3(0, 220, 100));
  closeCamera.lookAt(center);
  x.mesh.patches = [finePatch];
  let nearest;
  x.mesh.request = (choices) => {
    nearest = choices;
  };
  x.mesh.update(closeCamera, 800, qualityProfiles.ultra, 30000);
  assert.equal(nearest.length, 1);
  assert.equal(nearest[0].key, finePatch.id + '/fine');
  assert.equal(nearest[0].level, finePatch.levels.fine);
  assert.equal(
    nearest[0].level.tiles.length,
    finePatch.levels.fine.tiles.length,
  );
  accepted.closeFine = nearest.map((choice) => ({
    key: choice.key,
    tiles: choice.level.tiles.length,
    mipBytes: choice.bytes,
  }));
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS actual whole high/fine frontiers fit each configured quality budget without truncating source tiles: ' +
      JSON.stringify(accepted),
  );
});

await run('quality_profiles_and_sustained_auto_downgrade', async () => {
  const {
    qualityOptions,
    qualityProfiles,
    initialQualityLevel,
    AutomaticQuality,
  } = priorityFixture.load('quality');
  assert.equal(
    qualityOptions.map((option) => option.id).join('|'),
    'auto|smooth|balanced|high|ultra',
  );
  assert.equal(initialQualityLevel(4, 16384), 'smooth');
  assert.equal(initialQualityLevel(8, 16384), 'high');
  assert.equal(initialQualityLevel(8, 4096), 'smooth');
  const levels = ['smooth', 'balanced', 'high', 'ultra'];
  for (let i = 1; i < levels.length; i++)
    for (const field of [
      'dpr',
      'exteriorMiB',
      'textureMiB',
      'meshMiB',
      'terrainTiles',
    ])
      assert.ok(
        qualityProfiles[levels[i]][field] >=
          qualityProfiles[levels[i - 1]][field],
      );
  const auto = new AutomaticQuality('high');
  for (let i = 0; i < 179; i++)
    assert.equal(auto.observe(35, 20000 + i), 'high');
  assert.equal(auto.observe(35, 20179), 'balanced');
  for (let i = 0; i < 180; i++)
    assert.equal(auto.observe(35, 22000 + i), 'balanced');
  assert.equal(auto.observe(35, 36000), 'smooth');
  for (let i = 0; i < 720; i++)
    assert.equal(auto.observe(2, 60000 + i * 16), 'smooth');
  for (let i = 0; i < 180; i++) auto.observe(2, 90000 + i * 16);
  assert.equal(
    auto.level,
    'balanced',
    'five fast windows after 45s recover one step',
  );
  for (let i = 0; i < 900; i++) auto.observe(2, 150000 + i * 16);
  assert.equal(auto.level, 'high');
  for (let i = 0; i < 900; i++) auto.observe(60, 180000 + i * 16, false);
  assert.equal(auto.level, 'high', 'loading-only frames are excluded');
  results.push(
    'PASS profile resource limits are monotonic; automatic mode needs sustained slow samples and a 15s interval, and only recovers after five fast windows/45s up to its hardware ceiling; loading-only frames do not downgrade',
  );
});

await run('atomic_quality_budget_drop_during_decode', async () => {
  const x = fixture(),
    decoding = new Map();
  x.f.decode = (blob) => {
    if (blob.url === '/c') return Promise.resolve(x.bitmap(blob.url));
    const pending = deferred();
    decoding.set(blob.url, pending);
    return pending.promise;
  };
  x.atomic.request('AB', [source('/a'), source('/b')]);
  await flush();
  x.atomic.setBudget(6 * 1048576, 1);
  x.atomic.request('C', [source('/c')]);
  assert.equal(x.calls[0].signal.aborted, true);
  assert.equal(x.calls.length, 2);
  assert.equal(x.atomic.current.size, 0);
  decoding.get('/a').resolve(x.bitmap('/a'));
  await flush();
  assert.equal(x.calls.length, 2);
  decoding.get('/b').resolve(x.bitmap('/b'));
  await flush();
  assert.equal(x.calls.length, 3);
  assert.equal(x.calls[2].url, '/c');
  assert.equal(x.atomic.ready, 'C');
  assert.equal(x.atomic.workers, 1);
  assert.ok(x.atomic.cacheBytes + x.atomic.reservedBytes <= 6 * 1048576);
  assert.ok(
    x.bitmaps
      .filter((image) => image.url !== '/c')
      .every((image) => image.closed === 1),
  );
  x.atomic.dispose();
  results.push(
    'PASS quality budget reduction cancels both obsolete decodes, waits for both bitmaps, then commits the latest complete group with the new worker/budget limits',
  );
});

await run('scene_quality_keeps_camera_entity_and_floor', async () => {
  const { scene } = await sceneFixture();
  const { qualityProfiles } = priorityFixture.load('quality');
  const budgets = [];
  scene.opened = { entityId: 'building:current' };
  scene.selectedId = 'space:current';
  scene.floorId = 'floor:current';
  scene.host.clientWidth = 1280;
  scene.safeFrameInsets = {left:0,right:0,top:0,bottom:0};
  scene.immersionProgress = 0;
  let rendererDpr = 1;
  scene.renderer = {
    capabilities: { maxTextureSize: 16384 },
    setPixelRatio(value) {
      rendererDpr = value;
      budgets.push(['dpr', value]);
    },
    getPixelRatio() { return rendererDpr; },
    setSize() {},
  };
  const setExterior=scene.exteriors.setBudget.bind(scene.exteriors),setMesh=scene.meshDetail.setBudget.bind(scene.meshDetail);
  scene.exteriors.setBudget = (bytes,groups) => {budgets.push(['exterior',bytes,groups]);setExterior(bytes,groups);};
  scene.meshDetail.setBudget = bytes => {budgets.push(['mesh',bytes]);setMesh(bytes);};
  scene.detail = { terrainLimit: 8, last: 100 };
  scene.notify = () => {};
  const position = scene.camera.position.toArray(),
    target = scene.controls.target.toArray(),
    quaternion = scene.camera.quaternion.toArray(),
    opened = scene.opened;
  scene.setQuality('smooth');
  assert.ok(scene.textures.cacheBudgetBytes <= 48 * 1048576);
  assert.equal(scene.textures.cacheBudgetBytes,scene.detailPool.grants.original);
  assert.equal(scene.textures.workers, 1);
  assert.equal(scene.detail.terrainLimit, 2);
  scene.setQuality('ultra');
  assert.ok(scene.textures.cacheBudgetBytes <= 384 * 1048576);
  assert.equal(scene.textures.cacheBudgetBytes,scene.detailPool.grants.original);
  assert.equal(scene.textures.workers, 2);
  assert.equal(scene.qualityMode, 'ultra');
  assert.equal(scene.selectedId, 'space:current');
  assert.equal(scene.floorId, 'floor:current');
  assert.equal(scene.opened, opened);
  assert.deepEqual(scene.camera.position.toArray(), position);
  assert.deepEqual(scene.controls.target.toArray(), target);
  assert.deepEqual(scene.camera.quaternion.toArray(), quaternion);
  assert.ok(budgets.some((item) => item[0] === 'mesh' && item[1] === 0));
  assert.ok(
    budgets.some(
      (item) =>
        item[0] === 'mesh' &&
        item[1] > 0 && item[1] === scene.detailPool.grants.mesh && item[1] <= qualityProfiles.ultra.meshMiB * 1048576,
    ),
  );
  results.push(
    'PASS actual Scene.setQuality applies DPR, whole-model and original-texture budgets while preserving camera pose, orbit target, opened building, floor and entity selection',
  );
});

await run('page_close_matches_map_selection_without_second_fly', async () => {
  const page = fs.readFileSync(out + '/page.tsx', 'utf8');
  const line = page
    .split('\n')
    .find((text) => text.includes('const closeBuilding=useCallback('));
  assert.ok(line);
  const source = ts.transpileModule(line, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  let selectedId = 'space:room',
    category = 'space',
    camera = 'indoor';
  const calls = [],
    intent = { current: 0 };
  const current = {
    opened: { entityId: 'building:owner' },
    selectedId,
    closeBuilding(restore) {
      this.opened = null;
      if (restore) camera = 'restored';
      calls.push(['close', restore]);
    },
    async selectEntity(id, move) {
      this.selectedId = id;
      if (move !== false) camera = 'second-fly';
      calls.push(['select', id, move]);
    },
  };
  vm.runInNewContext(source + ';closeBuilding()', {
    useCallback: (callback) => callback,
    intent,
    scene: { current },
    setCategory(value) {
      category = value;
    },
    setSelectedId(value) {
      selectedId = value;
    },
    setError() {
      assert.fail('Unexpected selection failure');
    },
  });
  await flush();
  assert.equal(camera, 'restored');
  assert.equal(selectedId, 'building:owner');
  assert.equal(current.selectedId, selectedId);
  assert.equal(category, 'overview');
  assert.equal(intent.current, 1);
  assert.deepEqual(calls, [
    ['close', true],
    ['select', 'building:owner', false],
  ]);
  results.push(
    'PASS actual page close handler selects the same owning building in UI and map after restoration, explicitly disabling a second camera move',
  );
});

await run('mesh_high_to_fine_complete_replacement', async () => {
  const x = meshFixture(),
    high = x.choice('A'),
    fine = x.choice('fine-A', 2, 'fine', high.patch),
    last = deferred();
  high.patch.levels.fine = fine.level;
  x.mesh.request([high]);
  await flush();
  x.f.fetch = (url) =>
    url.endsWith('fine-A-1.glb')
      ? last.promise
      : Promise.resolve({ ok: true, arrayBuffer: async () => ({ url }) });
  x.mesh.request([fine]);
  await flush();
  assert.equal(x.mesh.visible.get('A').key, high.key);
  assert.equal(x.mesh.root.children.length, 1);
  assert.equal(x.mesh.progress, 1);
  assert.equal(x.baseline.children[0].visible, false);
  last.resolve({
    ok: true,
    arrayBuffer: async () => ({ url: '/models/hires/fine-A-1.glb' }),
  });
  await flush();
  assert.equal(x.mesh.visible.get('A').key, fine.key);
  assert.equal(
    x.mesh.visible.get('A').group.children.length,
    fine.level.tiles.length,
  );
  assert.equal(x.mesh.root.children.length, 1);
  assert.equal(
    x.bitmaps.find((bitmap) => bitmap.url.endsWith('/A-0.glb')).closed,
    1,
  );
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  results.push(
    'PASS high remains the complete visible region while fine is partially loaded; all fine tiles replace high together and old original textures close once',
  );
});

await run('mesh_upgrade_defers_without_baseline_flash_when_peak_does_not_fit', async () => {
  const x = meshFixture(),
    high = x.choice('A'),
    fine = x.choice('fine-A', 2, 'fine', high.patch);
  high.patch.levels.fine = fine.level;
  x.mesh.request([high]);
  await flush();
  const old = x.mesh.visible.get('A'), calls = x.calls.length;
  x.mesh.setBudget(fine.bytes, [fine]);
  x.mesh.request([fine]);
  await flush();
  assert.equal(x.calls.length, calls, 'deferred fine must not start an over-peak transaction');
  assert.equal(x.mesh.visible.get('A'), old);
  assert.equal(x.mesh.visible.get('A').key, high.key);
  assert.equal(x.baseline.children[0].visible, false);
  assert.equal(x.bitmaps.find(bitmap => bitmap.url.endsWith('/A-0.glb')).closed, 0);
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every(bitmap => bitmap.closed === 1));
  results.push(
    'PASS an upgrade whose old+new peak exceeds the grant stays deferred with the complete old frontier visible; it never flashes baseline or frees the old bitmap',
  );
});

function partialMeshFixture(count = 2) {
  const x = meshFixture(),
    choice = x.choice('partial', count);
  const mask = {
    url: 'partial/mask.png',
    minX: 2,
    minZ: 3,
    maxX: 22,
    maxZ: 18,
    width: 4,
    height: 3,
  };
  choice.patch.mask = mask;
  choice.bytes += mask.width * mask.height * 4;
  x.f.decode = (blob) =>
    Promise.resolve(
      Object.assign(x.bitmap(blob.url), {
        width: mask.width,
        height: mask.height,
        data: new Uint8Array(mask.width * mask.height).fill(255),
      }),
    );
  return { ...x, partial: choice, mask };
}

function manyPartialFixture(count = 97) {
  const x = meshFixture();
  const choices = Array.from({length:count}, (_, index) => {
    const choice = x.choice('small-cluster-' + index);
    const minX = 100 + index % 4 * 4, minZ = -100 + Math.floor(index / 4) * 4;
    choice.patch.mask = {url:choice.patch.id+'/mask.png',minX,minZ,maxX:minX+2,maxZ:minZ+2,width:2,height:2};
    choice.bytes += 16;
    return choice;
  });
  const decode = blob => {
    const choice = choices.find(choice => blob.url.endsWith(choice.patch.mask.url));
    assert.ok(choice, blob.url);
    return Object.assign(x.bitmap(blob.url), {width:2,height:2,data:new Uint8Array([255,0,0,255])});
  };
  x.f.decode = blob => Promise.resolve(decode(blob));
  return {...x,choices,decode};
}

await run('mesh_more_than_sixteen_partial_clusters_share_one_union_without_starvation', async () => {
  const x = manyPartialFixture(), {partialSlots} = x.load('spatial-masks');
  const {nativePlanBytes} = x.load('campus-mesh-detail');
  assert.equal(partialSlots.length, 96, 'bounded logical owner capacity covers a wide current view');
  const choices = x.choices.slice(0,20), delayed = deferred();
  x.f.decode = blob => blob.url.endsWith(choices[4].patch.mask.url) ? delayed.promise : Promise.resolve(x.decode(blob));
  x.mesh.request(choices);
  await flush();
  assert.equal(x.mesh.visible.size, 4, 'fifth mask is not exposed while decoding');
  assert.equal(x.masks.partialCoverageStats().enabledSlots, 4);
  const live = x.mesh.visible.get(choices[0].patch.id);
  delayed.resolve(x.decode({url:'/models/hires/'+choices[4].patch.mask.url}));
  await flush();
  assert.equal(x.mesh.visible.size,20);
  assert.equal(x.masks.partialCoverageStats().enabledSlots,20);
  assert.equal(x.mesh.partialOwners.size,20);
  assert.equal(new Set(x.mesh.partialOwners.values()).size,20);
  assert.equal(x.mesh.visible.get(choices[0].patch.id),live);
  const union=x.masks.slots.partialCoverage.texture.value.image;
  assert.deepEqual([union.width,union.height],[14,18]);
  for(let index=0;index<20;index++){
    const offset=Math.floor(index/4)*4*union.width+(index%4)*4;
    assert.equal(union.data[offset],255);
    assert.equal(union.data[offset+1],0,'source mask holes survive exact union');
    assert.equal(union.data[offset+union.width+1],255);
  }
  assert.equal(x.mesh.memoryBytes(),choices.reduce((sum,choice)=>sum+choice.bytes,0)+252);
  assert.equal(nativePlanBytes(choices),choices.reduce((sum,choice)=>sum+choice.bytes,0)+504);
  assert.equal(nativePlanBytes(x.choices),Infinity,'ninety-seventh logical owner cannot reserve');
  const calls=x.calls.length, removed=choices[6], entry=x.mesh.visible.get(removed.patch.id);
  x.mesh.request(choices.filter(choice=>choice!==removed));
  assert.equal(x.masks.partialCoverageStats().enabledSlots,19);
  assert.equal(x.mesh.visible.get(choices[0].patch.id),live);
  assert.equal(entry.mask.image.closed,0,'cached mask remains entry-owned');
  x.mesh.request(choices);
  assert.equal(x.calls.length,calls,'return uses cached source and mask');
  assert.equal(x.masks.partialCoverageStats().enabledSlots,20);
  assert.equal(x.calls.length,calls,'cached return starts no I/O');
  assert.ok(x.baseline.children.every(object=>object.visible),'partial masks never hide whole baseline parents');
  const material = new THREE.MeshBasicMaterial(), geometry = new THREE.BoxGeometry();
  x.masks.apply(new THREE.Mesh(geometry,material),'baseline');
  const shader={vertexShader:THREE.ShaderLib.basic.vertexShader,fragmentShader:THREE.ShaderLib.basic.fragmentShader,uniforms:{}};
  material.onBeforeCompile(shader,{});
  assert.equal((shader.fragmentShader.match(/uniform sampler2D u_partialCoverage;/g)||[]).length,1);
  assert.equal(/uniform sampler2D u_meshPartial/.test(shader.fragmentShader),false);
  x.mesh.setBudget(0, []);
  assert.equal(x.mesh.visible.size,0);
  assert.equal(x.masks.partialCoverageStats().enabledSlots,0);
  x.mesh.dispose();x.masks.dispose();material.dispose();geometry.dispose();
  assert.ok(x.bitmaps.every(bitmap=>bitmap.closed===1));
  results.push('PASS 16 complete masked clusters share one 14x14 R8 union, exact holes, one sampler and unique owners; fifth decode stays atomic, remove/cache/return preserves other 15, seventeenth blocks before I/O, zero budget closes every bitmap once');
});

await run('mesh_fifth_partial_cancel_drains_without_disturbing_four_live_clusters', async () => {
  const x = manyPartialFixture(6), delayed=deferred();
  x.f.decode=blob=>blob.url.endsWith(x.choices[4].patch.mask.url)?delayed.promise:Promise.resolve(x.decode(blob));
  x.mesh.request(x.choices);
  await flush();
  assert.equal(x.mesh.visible.size,4);
  const pending=x.mesh.pending, live=[...x.mesh.visible.values()];
  x.mesh.request(x.choices.slice(0,4));
  assert.equal(x.mesh.pending,pending);
  assert.equal(pending.abort.signal.aborted,true);
  const bitmap=x.decode({url:'/models/hires/'+x.choices[4].patch.mask.url});
  delayed.resolve(bitmap);
  await flush();
  assert.equal(bitmap.closed,1);
  assert.equal(x.mesh.pending,null);
  assert.equal(x.masks.partialCoverageStats().enabledSlots,4);
  assert.ok(live.every(entry=>x.mesh.visible.get(entry.patch.id)===entry));
  assert.equal(x.calls.some(call=>call.url.includes('small-cluster-5')),false);
  x.mesh.dispose();x.masks.dispose();
  assert.ok(x.bitmaps.every(bitmap=>bitmap.closed===1));
  results.push('PASS cancellation of fifth cluster during mask decode drains and closes stale bitmap; four committed source clusters/owners remain unchanged and obsolete sixth never loads');
});

await run('mesh_partial_union_size_alignment_and_exact_budget_guards', async () => {
  const x=manyPartialFixture(1),{nativePlanBytes}=x.load('campus-mesh-detail'),choice=x.choices[0];
  const huge={...choice,patch:{...choice.patch,mask:{...choice.patch.mask,minX:0,minZ:0,maxX:4096,maxZ:4096,width:4096,height:4096}}};
  huge.bytes=textureMipBytes(1024,1024)+4096*4096*4;
  assert.equal(nativePlanBytes([huge]),huge.bytes+2*16*1048576);
  const oversized={...huge,patch:{...huge.patch,mask:{...huge.patch.mask,width:4097,maxX:4097}}};
  assert.equal(nativePlanBytes([oversized]),Infinity);
  const shifted={...choice,patch:{...choice.patch,id:'shifted',mask:{...choice.patch.mask,minX:102.25,maxX:104.25}}};
  assert.equal(nativePlanBytes([choice,shifted]),Infinity,'fractional grid alignment must reject without resampling');
  const {fitNativeDetailChoices}=x.load('campus-mesh-detail');
  assert.equal(fitNativeDetailChoices([{choice,score:1}],nativePlanBytes([choice])-1).length,0);
  x.mesh.dispose();x.masks.dispose();
  results.push('PASS logical expansion retains exact 4096x4096/16MiB union cap, two-generation reservation, grid alignment and one-byte-short whole-group rejection; no texture downsampling');
});

await run('mesh_protected_source_coverage_precedes_higher_score_upgrades', async () => {
  const x=meshFixture(),{fitNativeDetailChoices,nativePlanBytes}=x.load('campus-mesh-detail');
  const high=x.choice('audited-source-cluster'),near=x.choice('high-score-neighbour',2);
  const road=x.choice('audited-source-cluster',2,'fine',high.patch);
  road.patch.levels.fine=road.level;road.level.geometricErrorMax=0;
  road.near=true;near.near=true;
  const capacity=nativePlanBytes([road]);
  let plan=fitNativeDetailChoices([{choice:near,score:1000},{choice:road,score:1}],capacity,0,[road,road]);
  assert.equal(plan.map(choice=>choice.patch.id).join('|'),road.patch.id);
  assert.equal(plan[0].level.tiles.length,2);
  assert.equal(plan[0].bytes,road.bytes);
  assert.equal(nativePlanBytes(plan),capacity);
  plan=fitNativeDetailChoices([{choice:near,score:1000},{choice:road,score:1}],capacity-1,0,[road]);
  assert.equal(plan.some(choice=>choice.key===road.key),false,'never trim a protected source frontier to make it fit');
  x.mesh.patches=[road.patch,near.patch];
  const {qualityProfiles}=x.load('quality'),c=camera();
  c.position.set(15,120,150);c.lookAt(15,0,15);c.updateMatrixWorld();
  const seenBefore=x.mesh.seen.size,callsBefore=x.calls.length;
  const coverage=x.mesh.previewCoveragePlan(c,800,qualityProfiles.high,new Set([road.patch.id,'unknown-id']));
  assert.equal(coverage.choices.map(choice=>choice.patch.id).join('|'),road.patch.id);
  assert.equal(coverage.bytes,x.mesh.planBytes(coverage.choices));
  assert.equal(coverage.choices[0].key,road.key);
  assert.equal(coverage.choices[0].level.tiles.length,2,'protected fine never falls back to one-tile high');
  assert.equal(x.mesh.seen.size,seenBefore);assert.equal(x.calls.length,callsBefore);
  const final=x.mesh.previewPlan(c,800,qualityProfiles.high,coverage.bytes,10000,coverage.choices);
  assert.equal(final.map(choice=>choice.patch.id).join('|'),road.patch.id);
  assert.equal(final[0].key,road.key);
  const missing=x.mesh.previewCoveragePlan(c,800,qualityProfiles.high,new Set([near.patch.id]));
  assert.equal(missing.choices.length,0);assert.equal(missing.unavailableIds.join('|'),near.patch.id);
  c.lookAt(15,120,1000);c.updateMatrixWorld();
  const offscreen=x.mesh.previewCoveragePlan(c,800,qualityProfiles.high,new Set([road.patch.id]));
  assert.equal(offscreen.choices.length,0);assert.equal(offscreen.bytes,0);
  assert.equal(x.mesh.previewCoveragePlan(c,800,qualityProfiles.smooth,new Set([road.patch.id])).bytes,0);
  x.mesh.dispose();x.masks.dispose();
  results.push('PASS explicitly audited current-view cluster reserves its complete error-zero fine frontier before higher-score upgrades, never substitutes its cheaper high as protected, deduplicates IDs, remains whole under short grants, reports missing fine, excludes offscreen/unknown IDs, and previews without IO/history mutation');
});

await run('mesh_partial_mask_atomic_cache_and_baseline', async () => {
  const x = partialMeshFixture(),
    maskDecode = deferred();
  x.f.decode = () => maskDecode.promise;
  x.mesh.request([x.partial]);
  await flush();
  assert.equal(x.mesh.progress, 2);
  assert.equal(x.mesh.stats().total, 3);
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.equal(x.baseline.children[0].visible, true);
  const bitmap = Object.assign(x.bitmap('partial-mask'), {
    width: x.mask.width,
    height: x.mask.height,
    data: new Uint8Array(x.mask.width * x.mask.height).fill(255),
  });
  maskDecode.resolve(bitmap);
  await flush();
  const entry = x.mesh.visible.get(x.partial.patch.id),
    wrapper = x.masks.slots.meshPartial.texture.value;
  assert.equal(entry.group.children.length, x.partial.level.tiles.length);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 1);
  assert.notEqual(wrapper, entry.mask);
  assert.equal(wrapper.image, entry.mask.image);
  assert.equal(entry.mask.image, bitmap);
  assert.equal(wrapper.flipY, false);
  assert.deepEqual(
    x.masks.slots.meshPartial.bounds.value.toArray(),
    [2, 3, 22, 18],
  );
  assert.equal(x.baseline.children[0].visible, true);
  const late = new THREE.Group();
  late.name = x.partial.patch.baselineIds[0];
  x.baseline.add(late);
  x.mesh.syncBaseline();
  assert.equal(late.visible, true);
  const fetches = x.calls.length;
  x.mesh.request([]);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.notEqual(x.masks.slots.meshPartial.texture.value.image, bitmap);
  assert.equal(bitmap.closed, 0);
  x.mesh.request([x.partial]);
  assert.equal(x.calls.length, fetches);
  assert.equal(x.mesh.cacheHits, 1);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 1);
  assert.equal(bitmap.closed, 0);
  x.mesh.setBudget(0, []);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.equal(bitmap.closed, 1);
  assert.ok(x.baseline.children.every((object) => object.visible));
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((image) => image.closed === 1));
  results.push(
    'PASS partial branch and projection mask commit together, keep its parent and late baseline tiles visible, reuse the cached mask, and close the shared bitmap once after disabling the slot',
  );
});

await run('mesh_partial_mask_failure_and_dimensions_retry', async () => {
  const x = partialMeshFixture();
  let masks = 0;
  x.f.fetch = async (url) =>
    url.endsWith('.png') && ++masks === 1
      ? { ok: false }
      : {
          ok: true,
          arrayBuffer: async () => ({ url }),
          blob: async () => ({ url }),
        };
  x.f.decode = (blob) =>
    Promise.resolve(
      Object.assign(x.bitmap(blob.url), {
        width: x.mask.width,
        height: masks === 2 ? x.mask.height + 1 : x.mask.height,
        data: new Uint8Array(x.mask.width * x.mask.height).fill(255),
      }),
    );
  x.mesh.request([x.partial]);
  await flush();
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.mesh.failures, 1);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.equal(x.baseline.children[0].visible, true);
  await x.tick(2000);
  assert.equal(x.mesh.failures, 2);
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.equal(
    x.bitmaps.find((bitmap) => bitmap.url.endsWith('.png')).closed,
    1,
  );
  await x.tick(5000);
  assert.equal(x.mesh.visible.size, 1);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 1);
  assert.equal(x.mesh.resident(), x.partial.bytes);
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  results.push(
    'PASS mask HTTP failure or wrong dimensions cannot expose partial content; automatic retry loads the complete branch and valid mask, closing rejected mask bitmaps exactly once',
  );
});

await run('mesh_partial_cancel_mask_decode_drains', async () => {
  const x = partialMeshFixture(),
    decode = deferred(),
    whole = x.choice('next');
  x.f.decode = () => decode.promise;
  x.mesh.request([x.partial]);
  await flush();
  const priorFetches = x.calls.length;
  x.mesh.request([whole]);
  assert.equal(x.calls.at(-1).signal.aborted, true);
  assert.equal(x.calls.length, priorFetches);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  const bitmap = Object.assign(x.bitmap('cancelled-partial-mask'), {
    width: x.mask.width,
    height: x.mask.height,
    data: new Uint8Array(x.mask.width * x.mask.height).fill(255),
  });
  decode.resolve(bitmap);
  await flush();
  assert.equal(bitmap.closed, 1);
  assert.equal(x.mesh.visible.has('next'), true);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 0);
  assert.ok(
    x.events.indexOf('close:cancelled-partial-mask') <
      x.events.indexOf('fetch:/models/hires/next-0.glb'),
  );
  assert.equal(x.baseline.children[0].visible, true);
  x.mesh.dispose();
  x.masks.dispose();
  assert.ok(x.bitmaps.every((image) => image.closed === 1));
  results.push(
    'PASS cancellation during mask decoding drains and closes the late bitmap before the next complete region starts; the partial mask never activates',
  );
});

await run('mesh_partial_shader_excludes_own_mask', async () => {
  const x = partialMeshFixture(1),
    coarse = new THREE.Mesh(
      new THREE.BoxGeometry(),
      new THREE.MeshBasicMaterial(),
    );
  x.mesh.request([x.partial]);
  await flush();
  assert.equal(x.mesh.visible.size, 1);
  x.masks.apply(coarse, 'baseline');
  const compile = (material) => {
    const shader = {
      uniforms: {},
      vertexShader: '#include <project_vertex>',
      fragmentShader: '#include <clipping_planes_fragment>',
    };
    material.onBeforeCompile(shader, {});
    return shader;
  };
  const baseShader = compile(coarse.material),
    meshShader = compile(
      x.mesh.visible.get('partial').group.children[0].children[0].material,
    );
  assert.ok(baseShader.fragmentShader.includes('partialCoverage'));
  assert.ok(!meshShader.fragmentShader.includes('partialCoverage'));
  assert.ok(meshShader.fragmentShader.includes('replacement'));
  assert.ok(meshShader.fragmentShader.includes('opening'));
  coarse.geometry.dispose();
  coarse.material.dispose();
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS actual coarse shader uses the partialCoverage union, replacement photogrammetry excludes its own masks while retaining building replacement/opening masks',
  );
});

await run('mesh_partial_exact_mask_budget', async () => {
  const x = partialMeshFixture(1),
    { qualityProfiles } = x.load('quality');
  x.mesh.patches = [x.partial.patch];
  const closeCamera = camera();
  closeCamera.position.set(15, 120, 90);
  closeCamera.lookAt(15, 10, 15);
  const allocation=x.mesh.planBytes([x.partial]);
  assert.equal(allocation,x.partial.bytes+2*x.mask.width*x.mask.height);
  x.mesh.setBudget(allocation - 1);
  x.mesh.update(closeCamera, 800, qualityProfiles.high, 10000);
  await flush();
  assert.equal(x.calls.length, 0);
  assert.equal(x.mesh.visible.size, 0);
  assert.equal(x.baseline.children[0].visible, true);
  x.mesh.setBudget(allocation);
  x.mesh.update(closeCamera, 800, qualityProfiles.high, 11000);
  await flush();
  assert.equal(x.mesh.visible.size, 1);
  assert.equal(x.mesh.resident(), x.partial.bytes);
  assert.equal(x.mesh.memoryBytes(),x.partial.bytes+x.mask.width*x.mask.height);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 1);
  x.mesh.dispose();
  x.masks.dispose();
  results.push(
    'PASS branch budget includes source mask RGBA bytes plus old/new exact R8 union reservation: one byte short rejects the entire group, exact capacity commits with measured union storage below its reservation',
  );
});

function readGrayMask(path) {
  const file = fs.readFileSync(path);
  assert.equal(file.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  const width = file.readUInt32BE(16),
    height = file.readUInt32BE(20);
  assert.deepEqual(
    [...file.subarray(24, 29)],
    [8, 0, 0, 0, 0],
    'Expected retained 8-bit non-interlaced grayscale source PNG',
  );
  const chunks = [];
  for (let offset = 8; offset < file.length;) {
    const length = file.readUInt32BE(offset);
    if (file.toString('ascii', offset + 4, offset + 8) === 'IDAT')
      chunks.push(file.subarray(offset + 8, offset + 8 + length));
    offset += 12 + length;
  }
  const scan = inflateSync(Buffer.concat(chunks)),
    data = new Uint8Array(width * height);
  assert.equal(scan.length, height * (width + 1));
  const paeth = (a, b, c) => {
    const p = a + b - c,
      pa = Math.abs(p - a),
      pb = Math.abs(p - b),
      pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  for (let y = 0; y < height; y++) {
    const filter = scan[y * (width + 1)];
    assert.ok(filter <= 4);
    for (let x = 0; x < width; x++) {
      const i = y * width + x,
        a = x ? data[i - 1] : 0,
        b = y ? data[i - width] : 0,
        c = x && y ? data[i - width - 1] : 0;
      const predictor =
        filter === 0
          ? 0
          : filter === 1
            ? a
            : filter === 2
              ? b
              : filter === 3
                ? Math.floor((a + b) / 2)
                : paeth(a, b, c);
      data[i] = (scan[y * (width + 1) + x + 1] + predictor) & 255;
    }
  }
  return { width, height, data };
}

await run('mesh_partial_actual_source_frontier', async () => {
  const manifest = publicData('models/hires/manifest.json');
  const patch = entrancePartialPatches()[0];
  assert.ok(manifest.patches.some((entry) => entry.id === patch.id));
  const descriptor = publicData('models/hires/' + patch.sourceManifest);
  assert.ok(patch);
  const level = patch.levels.high;
  assert.equal(patch.id, descriptor.id);
  assert.ok(level.tiles.length > 0);
  assert.equal(new Set(level.tiles.map((tile) => tile.id)).size, level.tiles.length);
  let sourceBytes = 0;
  for (const tile of level.tiles) {
    const original = descriptor.levels.high.tiles.find(
      (source) => source.id === tile.id,
    );
    assert.ok(original);
    assert.deepEqual(tile.matrix, original.matrix);
    assert.deepEqual(
      tile.textureDimensions,
      original.textures.map((texture) => [texture.width, texture.height]),
    );
    const bytes = fs.readFileSync(root + '/public/models/hires/' + tile.url);
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      original.sha256,
    );
    assert.equal(bytes.length, original.bytes);
    assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
    assert.equal(bytes.readUInt32LE(4), 2);
    assert.equal(bytes.readUInt32LE(8), bytes.length);
    sourceBytes += bytes.length;
  }
  const png = fs.readFileSync(root + '/public/models/hires/' + patch.mask.url);
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.deepEqual(
    [png.readUInt32BE(16), png.readUInt32BE(20)],
    [patch.mask.width, patch.mask.height],
  );
  assert.ok(patch.mask.width > 0 && patch.mask.height > 0);
  const bytes = level.tiles.reduce(
    (sum, tile) =>
      sum +
      tile.textureDimensions.reduce(
        (total, dimensions) => total + textureMipBytes(...dimensions),
        0,
      ),
    patch.mask.width * patch.mask.height * 4,
  );
  assert.equal(sourceBytes, level.bytes, "Encoded GLB bytes and decoded mip allocation are separate quantities");
  const x = meshFixture(),
    { qualityProfiles } = x.load('quality');
  assert.ok(bytes <= qualityProfiles.high.meshMiB * 1048576);
  assert.ok(bytes <= qualityProfiles.ultra.meshMiB * 1048576);
  const parent = new THREE.Group();
  parent.name = patch.baselineIds[0];
  x.baseline.add(parent);
  x.f.decode = (blob) =>
    Promise.resolve(
      Object.assign(x.bitmap(blob.url), {
        width: patch.mask.width,
        height: patch.mask.height,
        data: readGrayMask(root + '/public/models/hires/' + patch.mask.url)
          .data,
      }),
    );
  const choice={key:patch.id+'/high',patch,level,bytes};
  x.mesh.setBudget(x.mesh.planBytes([choice]));
  x.mesh.request([choice]);
  await flush();
  const entry = x.mesh.visible.get(patch.id);
  assert.ok(entry);
  assert.equal(entry.group.children.length, level.tiles.length);
  assert.equal(parent.visible, true);
  assert.equal(x.masks.slots.meshPartial.enabled.value, 1);
  assert.equal(x.mesh.resident(), bytes);
  assert.deepEqual(
    x.calls.map((call) => call.url),
    [
      ...level.tiles.map((tile) => '/models/hires/' + tile.url),
      '/models/hires/' + patch.mask.url,
    ],
  );
  for (let i = 0; i < level.tiles.length; i++)
    assert.deepEqual(
      entry.group.children[i].matrix.toArray(),
      level.tiles[i].matrix,
    );
  x.mesh.dispose();
  x.masks.dispose();
  assert.equal(parent.visible, true);
  assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
  results.push(
    'PASS actual native high frontier GLB SHA-256/lengths, unchanged original texture dimensions and placement matrices, and PNG are verified; current loader commits the full source frontier and mask together without hiding its incomplete parent. Controlled decode only; sourceBytes=' +
      sourceBytes +
      ', decodedMipAndMaskBytes=' +
      bytes,
  );
});

function entrancePartialPatches() {
  const manifest = publicData('models/hires/manifest.json');
  // Opposite sides of the north entrance, formerly two regional partial owners.
  // Assert source identity explicitly; arbitrary manifest order is not geography.
  const ids = [
    'native-12-NW-6C_12-NW-6C-1_Tile_300_147_L18_002',
    'native-12-NW-6C_12-NW-6C-7_Tile_301_146_L18_001',
  ];
  return ids.map(id => {
    const patch = manifest.patches.find(patch => patch.id === id);
    assert.ok(patch?.partial && patch.mask && patch.sourceManifest, id);
    return patch;
  });
}

function realPartialFixture() {
  const x = meshFixture(),
    patches = entrancePartialPatches();
  for (const patch of patches)
    for (const id of patch.baselineIds) {
      const object = new THREE.Group();
      object.name = id;
      x.baseline.add(object);
    }
  const decode = (blob) =>
    Promise.resolve(
      Object.assign(
        x.bitmap(blob.url),
        readGrayMask(root + '/public' + blob.url),
      ),
    );
  x.f.decode = decode;
  const choice = (patch, name = 'high') => {
    const level = patch.levels[name],
      mask = level.mask ?? patch.mask;
    assert.ok(level);
    return {
      key: patch.id + '/' + name,
      patch,
      level,
      bytes: level.tiles.reduce(
        (sum, tile) =>
          sum +
          tile.textureDimensions.reduce(
            (bytes, dimensions) => bytes + textureMipBytes(...dimensions),
            0,
          ),
        mask.width * mask.height * 4,
      ),
    };
  };
  return { ...x, patches, sourceChoice: choice, sourceDecode: decode };
}

await run(
  'mesh_both_partial_actual_frontiers_and_fine_assets_unchanged',
  async () => {
    const patches = entrancePartialPatches(),
      verified = new Set(),
      frontiers = [];
    for (const patch of patches) {
      const descriptor = publicData('models/hires/' + patch.sourceManifest);
      assert.ok(descriptor);
      for (const [name, level] of Object.entries(patch.levels)) {
        const originalLevel = descriptor.levels[name],
          mask = level.mask ?? patch.mask;
        assert.equal(level.tiles.length, originalLevel.tiles.length);
        assert.deepEqual(
          level.tiles.map((tile) => tile.id),
          originalLevel.tiles.map((tile) => tile.id),
        );
        assert.equal(
          new Set(level.tiles.map((tile) => tile.id)).size,
          level.tiles.length,
        );
        for (let i = 0; i < level.tiles.length; i++) {
          const tile = level.tiles[i],
            original = originalLevel.tiles[i];
          assert.deepEqual(tile.matrix, original.matrix);
          assert.deepEqual(
            tile.textureDimensions,
            original.textures.map((texture) => [texture.width, texture.height]),
          );
          const bytes = fs.readFileSync(
            root + '/public/models/hires/' + tile.url,
          );
          assert.equal(bytes.length, original.bytes);
          assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
          assert.equal(bytes.readUInt32LE(4), 2);
          assert.equal(bytes.readUInt32LE(8), bytes.length);
          assert.equal(
            createHash('sha256').update(bytes).digest('hex'),
            original.sha256,
          );
          verified.add(tile.url);
        }
        const pixels = readGrayMask(root + '/public/models/hires/' + mask.url);
        assert.deepEqual(
          [pixels.width, pixels.height],
          [mask.width, mask.height],
        );
        assert.equal(
          pixels.data.filter((value) => value > 127).length,
          mask.coveredPixels,
        );
        if (name === 'fine')
          assert.notEqual(
            mask.url,
            patch.mask.url,
            'Fine must identify its own actual projection, not reuse the high-level descriptor',
          );
        frontiers.push({
          patch: patch.id,
          level: name,
          tiles: level.tiles.length,
          mask: mask.url,
          coveredPixels: mask.coveredPixels,
        });
      }
    }
    assert.equal(frontiers.length, 4);
    assert.ok(frontiers.every((frontier) => frontier.tiles > 0 && frontier.coveredPixels > 0));
    assert.notEqual(frontiers[0].mask, frontiers[1].mask);
    results.push(
      'PASS both actual native partial branches retain every high/fine GLB, original SHA-256/texture size/matrix and source PNG coverage: ' +
        JSON.stringify({ uniqueAssets: verified.size, frontiers }),
    );
  },
);

await run(
  'mesh_two_actual_partial_masks_commit_and_remove_independently',
  async () => {
    const x = realPartialFixture(),
      a = x.sourceChoice(x.patches[0]),
      b = x.sourceChoice(x.patches[1]),
      delayed = deferred();
    x.mesh.setBudget(x.mesh.planBytes([a,b]));
    x.f.decode = (blob) =>
      blob.url.endsWith(b.patch.mask.url)
        ? delayed.promise
        : x.sourceDecode(blob);
    x.mesh.request([a, b]);
    await flush();
    assert.equal(x.mesh.visible.size, 1);
    assert.equal(x.mesh.visible.has(a.patch.id), true);
    assert.equal(x.mesh.pending.key, b.key);
    assert.equal(x.mesh.pending.group.children.length, b.level.tiles.length);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 1);
    assert.ok(x.baseline.children.every((object) => object.visible));
    const bBitmap = Object.assign(
      x.bitmap('/models/hires/' + b.patch.mask.url),
      readGrayMask(root + '/public/models/hires/' + b.patch.mask.url),
    );
    delayed.resolve(bBitmap);
    await flush();
    assert.equal(x.mesh.visible.size, 2);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 2);
    const aEntry = x.mesh.visible.get(a.patch.id),
      bEntry = x.mesh.visible.get(b.patch.id),
      bSlot = x.mesh.partialOwners.get(b.patch.id),
      bWrapper = x.masks.slots[bSlot].texture.value;
    assert.notEqual(x.mesh.partialOwners.get(a.patch.id), bSlot);
    assert.equal(aEntry.group.children.length, a.level.tiles.length);
    assert.equal(bEntry.group.children.length, b.level.tiles.length);
    const fetches = x.calls.length;
    x.mesh.request([b]);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 1);
    assert.equal(x.mesh.visible.get(b.patch.id), bEntry);
    assert.equal(x.masks.slots[bSlot].texture.value, bWrapper);
    assert.equal(bBitmap.closed, 0);
    assert.equal(aEntry.mask.image.closed, 0);
    x.mesh.request([a, b]);
    assert.equal(x.calls.length, fetches);
    assert.equal(x.mesh.cacheHits, 1);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 2);
    assert.equal(x.mesh.visible.get(b.patch.id), bEntry);
    assert.equal(x.masks.slots[bSlot].texture.value, bWrapper);
    x.mesh.setBudget(0, []);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 0);
    assert.equal(x.mesh.visible.size, 0);
    assert.ok(x.baseline.children.every((object) => object.visible));
    x.mesh.dispose();
    x.masks.dispose();
    assert.ok(x.bitmaps.every((bitmap) => bitmap.closed === 1));
    results.push(
      'PASS real native source groups commit with separate mask owners; second decode cannot disturb the first, removing/caching/reopening one preserves the other and does not re-download, zero budget disables both before closing every bitmap once',
    );
  },
);

await run(
  'mesh_actual_fine_level_mask_replaces_only_its_own_high_branch',
  async () => {
    const x = realPartialFixture(),
      high = x.sourceChoice(x.patches[0]),
      fine = x.sourceChoice(x.patches[0], 'fine'),
      other = x.sourceChoice(x.patches[1]);
    x.mesh.setBudget(high.bytes+x.mesh.planBytes([fine,other]));
    x.mesh.request([high, other]);
    await flush();
    const old = x.mesh.visible.get(high.patch.id),
      kept = x.mesh.visible.get(other.patch.id),
      keptSlot = x.mesh.partialOwners.get(other.patch.id),
      keptWrapper = x.masks.slots[keptSlot].texture.value;
    const mask = fine.level.mask,
      delayed = deferred();
    x.f.decode = (blob) =>
      blob.url.endsWith(mask.url) ? delayed.promise : x.sourceDecode(blob);
    x.mesh.request([fine, other]);
    await flush();
    assert.equal(x.mesh.visible.get(high.patch.id), old);
    assert.equal(x.mesh.pending.group.children.length, fine.level.tiles.length);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 2);
    assert.equal(x.mesh.visible.get(other.patch.id), kept);
    const bitmap = Object.assign(
      x.bitmap('/models/hires/' + mask.url),
      readGrayMask(root + '/public/models/hires/' + mask.url),
    );
    delayed.resolve(bitmap);
    await flush();
    const next = x.mesh.visible.get(fine.patch.id);
    assert.equal(next.key, fine.key);
    assert.equal(next.group.children.length, fine.level.tiles.length);
    assert.equal(next.mask.image, bitmap);
    assert.equal(old.mask.image.closed, 1);
    assert.equal(x.mesh.visible.get(other.patch.id), kept);
    assert.equal(x.masks.slots[keptSlot].texture.value, keptWrapper);
    assert.equal(kept.mask.image.closed, 0);
    assert.equal(x.masks.partialCoverageStats().enabledSlots, 2);
    assert.equal(
      x.calls.filter((call) => call.url.endsWith(mask.url)).length,
      1,
    );
    x.mesh.dispose();
    x.masks.dispose();
    assert.ok(x.bitmaps.every((image) => image.closed === 1));
    results.push(
    'PASS actual fine frontier uses its level-specific source PNG; the old high branch stays complete until its replacement mask is decoded, while the adjacent partial group and mask retain identity',
    );
  },
);

await run(
  'mesh_actual_both_entrance_views_fit_complete_nearby_groups',
  async () => {
    const manifest = publicData('models/hires/manifest.json'),
      required = [
        ...entrancePartialPatches().map(patch => patch.id),
        'native-12-NW-6C_12-NW-6C-2_Tile_301_147_L18_000',
        'native-12-NW-6C_12-NW-6C-6_Tile_300_146_L18_0033',
      ],
      observed = [];
    for (const poseName of ['motion-before', 'entrance-stage-surface'])
      for (const quality of ['high', 'ultra']) {
        const pose = JSON.parse(
            fs.readFileSync(
              root + '/docs/source-evidence-v4/' + poseName + '.json',
            ),
          ),
          x = meshFixture(),
          { qualityProfiles } = x.load('quality'),
          profile = qualityProfiles[quality];
        const c = camera();
        c.position.fromArray(pose.camera);
        c.lookAt(...pose.target);
        c.updateMatrixWorld();
        x.mesh.patches = manifest.patches;
        x.mesh.setBudget(profile.meshMiB * 1048576);
        let selected;
        x.mesh.request = (choices) => {
          selected = choices;
        };
        x.mesh.update(c, 800, profile, 10000);
        for (const id of required)
          assert.ok(
            selected.some((choice) => choice.patch.id === id),
            poseName + '/' + quality + ': deferred nearby source group ' + id,
          );
        assert.ok(
          selected.reduce((sum, choice) => sum + choice.bytes, 0) <=
            profile.meshMiB * 1048576,
        );
        observed.push({
          pose: poseName,
          quality,
          budgetMiB: profile.meshMiB,
          chosen: selected.map((choice) => ({
            key: choice.key,
            tiles: choice.level.tiles.length,
            MiB: choice.bytes / 1048576,
          })),
        });
        x.mesh.dispose();
        x.masks.dispose();
      }
    results.push(
      'PASS both recorded entrance views include four nearby complete native source frontiers under current high/ultra budgets without per-tile truncation: ' +
        JSON.stringify(observed),
    );
  },
);

// Read original image dimensions from GLB payloads; no image decoder or resized fixture.
function imageDimensions(bytes) {
  if (bytes.subarray(0, 8).toString('hex') === '89504e470d0a1a0a')
    return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  assert.equal(
    bytes.readUInt16BE(0),
    0xffd8,
    'Source image must be retained JPEG or PNG',
  );
  for (let offset = 2; offset < bytes.length;) {
    assert.equal(bytes[offset++], 0xff);
    while (bytes[offset] === 0xff) offset++;
    const marker = bytes[offset++];
    assert.notEqual(marker, 0xda, 'JPEG dimensions must precede scan data');
    const length = bytes.readUInt16BE(offset);
    assert.ok(length >= 2 && offset + length <= bytes.length);
    if (
      [
        0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce,
        0xcf,
      ].includes(marker)
    )
      return [bytes.readUInt16BE(offset + 5), bytes.readUInt16BE(offset + 3)];
    offset += length;
  }
  assert.fail('JPEG source dimensions missing');
}

function inspectSourceGlb(path) {
  const bytes = fs.readFileSync(path);
  assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
  assert.equal(bytes.readUInt32LE(4), 2);
  assert.equal(bytes.readUInt32LE(8), bytes.length);
  const jsonLength = bytes.readUInt32LE(12);
  assert.equal(bytes.readUInt32LE(16), 0x4e4f534a);
  const json = JSON.parse(bytes.toString('utf8', 20, 20 + jsonLength).trim());
  const binStart = 28 + jsonLength;
  assert.equal(bytes.readUInt32LE(binStart - 4), 0x004e4942);
  assert.equal(binStart + bytes.readUInt32LE(binStart - 8), bytes.length);
  const dimensions = [],
    encoded = [];
  for (const image of json.images) {
    const view = json.bufferViews[image.bufferView];
    assert.equal(view.buffer, 0);
    const start = binStart + (view.byteOffset ?? 0);
    assert.ok(start + view.byteLength <= bytes.length);
    dimensions.push(
      imageDimensions(bytes.subarray(start, start + view.byteLength)),
    );
    encoded.push(view.byteLength);
  }
  let triangles = 0,
    vertices = 0;
  for (const mesh of json.meshes)
    for (const primitive of mesh.primitives) {
      assert.equal(primitive.mode ?? 4, 4);
      const position = json.accessors[primitive.attributes.POSITION];
      const count =
        primitive.indices === undefined
          ? position.count
          : json.accessors[primitive.indices].count;
      assert.equal(count % 3, 0);
      triangles += count / 3;
      vertices += position.count;
    }
  return {
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    dimensions,
    encoded,
    triangles,
    vertices,
  };
}

await run(
  'mesh_every_manifest_patch_retains_source_assets_frontier_and_masks',
  async () => {
    const manifest = publicData('models/hires/manifest.json');
    const baseline = publicData('models/render-manifest.json').tiles;
    const assets = new Map(),
      frontiers = [];
    assert.ok(manifest.patches.length > 0);
    assert.equal(
      new Set(manifest.patches.map((patch) => patch.id)).size,
      manifest.patches.length,
    );
    const sourceRoot = (id) => id.slice(0, id.lastIndexOf('/'));
    const assertBounds = (bounds) => {
      assert.equal(bounds.min.length, 3);
      assert.equal(bounds.max.length, 3);
      for (let i = 0; i < 3; i++)
        assert.ok(
          Number.isFinite(bounds.min[i]) &&
            Number.isFinite(bounds.max[i]) &&
            bounds.min[i] <= bounds.max[i],
        );
    };
    for (const patch of manifest.patches) {
      assertBounds(patch.bounds);
      assert.ok(patch.baselineIds.length > 0);
      assert.equal(new Set(patch.baselineIds).size, patch.baselineIds.length);
      for (const id of patch.baselineIds)
        assert.ok(
          baseline.some((tile) => tile.id === id),
          patch.id + ': unknown baseline ' + id,
        );
      const descriptor = patch.sourceManifest
        ? publicData('models/hires/' + patch.sourceManifest)
        : publicData(
            'models/hires/' + dirname(patch.mask.url) + '/manifest.json',
          ).patches.find((source) => source.id === patch.id);
      assert.ok(descriptor, patch.id + ': retained source descriptor');
      assert.ok(Object.keys(patch.levels).length > 0);
      for (const [name, level] of Object.entries(patch.levels)) {
        const label = patch.id + '/' + name;
        assert.ok(level.tiles.length > 0, label);
        assert.equal(
          new Set(level.tiles.map((tile) => tile.id)).size,
          level.tiles.length,
          label,
        );
        const terminalDescriptor = level.tiles
          .map(
            (tile) =>
              root +
              '/public/models/hires/' +
              dirname(tile.url) +
              '/manifest.json',
          )
          .filter((path) => fs.existsSync(path))
          .flatMap((path) => JSON.parse(fs.readFileSync(path)).patches ?? [])
          .find((source) => source.id === patch.id);
        const levelDescriptor =
          level.sourceFrontier?.terminalLeaves && terminalDescriptor
            ? terminalDescriptor
            : descriptor;
        assert.ok(
          levelDescriptor,
          label + ': terminal descriptor must match source patch',
        );
        const sourceFrontier = levelDescriptor.frontiers?.find(
          (frontier) => frontier.key === name,
        );
        const originals =
          sourceFrontier?.assets ?? levelDescriptor.levels?.[name]?.tiles;
        assert.ok(originals, label + ': exported frontier must be retained');
        if (sourceFrontier) assert.deepEqual(sourceFrontier.issues, [], label);
        if (level.sourceFrontier?.selectedFrontierIssues)
          assert.deepEqual(
            level.sourceFrontier.selectedFrontierIssues,
            [],
            label,
          );
        if (level.sourceFrontier?.terminalLeaves)
          for (const tile of level.tiles)
            assert.equal(
              tile.originalError ?? tile.geometricError,
              0,
              label + ': all requested terminal leaves must be terminal',
            );
        assert.deepEqual(
          level.tiles.map((tile) => tile.id).sort((a, b) => a.localeCompare(b)),
          originals.map((tile) => tile.id).sort((a, b) => a.localeCompare(b)),
          label + ': no omitted or invented source leaves',
        );
        for (const tile of level.tiles) {
          const original = originals.find((source) => source.id === tile.id);
          const sourceSha = original.glb_sha256 ?? original.sha256;
          assert.ok(
            tile.sha256 === sourceSha ||
              tile.sourceCorrection?.originalSha256 === sourceSha,
            label + ': correction must retain source SHA lineage for ' + tile.id,
          );
        }
        const lineage = level.tiles.map((tile) => {
          const match = tile.id.match(/^(.*\/Tile_\d+_\d+)_L(\d+)_([0-9]+)$/);
          assert.ok(match, label + ': known source hierarchy ID ' + tile.id);
          return { root: match[1], path: match[3] };
        });
        for (let i = 0; i < lineage.length; i++)
          for (let j = i + 1; j < lineage.length; j++) {
            const a = lineage[i],
              b = lineage[j];
            assert.ok(
              a.root !== b.root ||
                !(a.path.startsWith(b.path) || b.path.startsWith(a.path)),
              label + ': ancestor and descendant overlap',
            );
          }
        let totalBytes = 0,
          totalTriangles = 0,
          totalTextureBytes = 0,
          mipBytes = 0;
        for (const tile of level.tiles) {
          const path = root + '/public/models/hires/' + tile.url;
          if (!assets.has(path)) assets.set(path, inspectSourceGlb(path));
          const actual = assets.get(path);
          assert.equal(actual.bytes, tile.bytes, tile.id);
          assert.equal(actual.sha256, tile.sha256, tile.id);
          assert.equal(actual.triangles, tile.triangles, tile.id);
          assert.equal(actual.vertices, tile.vertices, tile.id);
          assert.deepEqual(
            actual.dimensions,
            tile.textureDimensions,
            tile.id + ': retained original texture resolution',
          );
          assert.equal(
            actual.encoded.reduce((sum, bytes) => sum + bytes, 0),
            tile.textureEncodedBytes,
            tile.id,
          );
          const textureBytes = actual.dimensions.reduce(
            (sum, [width, height]) => sum + width * height * 4,
            0,
          );
          assert.equal(textureBytes, tile.textureBytes, tile.id);
          assert.equal(tile.matrix.length, 16);
          assert.ok(tile.matrix.every(Number.isFinite));
          const parent = baseline.find(
            (parent) => sourceRoot(parent.id) === sourceRoot(tile.id),
          );
          assert.ok(parent, tile.id + ': original baseline source root');
          assert.deepEqual(
            tile.matrix,
            parent.matrix,
            tile.id + ': same source root uses unchanged transform',
          );
          assertBounds(tile.bounds);
          totalBytes += actual.bytes;
          totalTriangles += actual.triangles;
          totalTextureBytes += textureBytes;
          mipBytes += actual.dimensions.reduce(
            (sum, dimensions) => sum + textureMipBytes(...dimensions),
            0,
          );
        }
        assert.equal(totalBytes, level.bytes, label);
        assert.equal(totalTriangles, level.triangles, label);
        assert.equal(totalTextureBytes, level.textureBytes, label);
        const mask = level.mask ?? patch.mask;
        let maskPixels = 0;
        if (mask) {
          const pixels = readGrayMask(
            root + '/public/models/hires/' + mask.url,
          );
          assert.deepEqual(
            [pixels.width, pixels.height],
            [mask.width, mask.height],
            label,
          );
          assert.ok(mask.minX < mask.maxX && mask.minZ < mask.maxZ, label);
          maskPixels = pixels.data.filter((value) => value > 127).length;
          assert.ok(
            maskPixels > 0,
            label + ': source projection must be nonempty',
          );
          if (mask.coveredPixels !== undefined)
            assert.equal(maskPixels, mask.coveredPixels, label);
          mipBytes += pixels.width * pixels.height * 4;
        } else
          assert.notEqual(
            patch.partial,
            true,
            label + ': incomplete baseline requires an actual source mask',
          );
        frontiers.push({
          patch: patch.id,
          level: name,
          sourceRoots: new Set(level.tiles.map((tile) => sourceRoot(tile.id)))
            .size,
          tiles: level.tiles.length,
          triangles: totalTriangles,
          sourceBytes: totalBytes,
          textureMipAndMaskBytes: mipBytes,
          maskPixels,
        });
      }
    }
    results.push(
      'PASS every current patch, including any newly added source roots, retains complete declared leaves, SHA-256, GLB primitive counts, embedded original image dimensions, unchanged source-root transforms and decoded mask coverage: ' +
        JSON.stringify({
          patches: manifest.patches.length,
          uniqueAssets: assets.size,
          frontiers,
        }),
    );
  },
);

const report = {
  checkedAt: new Date().toISOString(),
  scope:
    'Current checkout implementations; controlled fetch/decode/clock boundaries; actual source manifests and Three camera math; no browser or GPU visual acceptance.',
  camera: cameraPose,
  sourceRegions: sourceRegions.regions.length,
  implementations: Object.fromEntries(
    [
      'atomic-textures.ts',
      'detail-priority.ts',
      'source-types.ts',
      'scene.ts',
      'campus-mesh-detail.ts',
      'spatial-masks.ts',
      'quality.ts',
      'page.tsx',
      'entity-classification.ts',
    ].map((name) => [
      name,
      createHash('sha256')
        .update(fs.readFileSync(out + '/' + name))
        .digest('hex'),
    ]),
  ),
  passed: checks.filter((check) => check.status === 'passed').length,
  failed: checks.filter((check) => check.status === 'failed').length,
  checks,
};
const reportPath = root + '/docs/source-evidence-v4/detail-loading-tests.json';
fs.mkdirSync(dirname(reportPath), { recursive: true });
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(
  JSON.stringify({
    passed: report.passed,
    failed: report.failed,
    report: reportPath,
  }),
);
if (report.failed) process.exitCode = 1;
