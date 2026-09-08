// Run: node scripts/check-runtime-races.cjs
// Reads current checkout. No browser/network or checkout writes.
async function main() {
  const [fs, vm, { default: assert }, { resolve }, ts, THREE] =
    await Promise.all([
      import('node:fs'),
      import('node:vm'),
      import('node:assert/strict'),
      import('node:path'),
      import('typescript'),
      import('three'),
    ]);
  const base = resolve(__dirname, '..');
  const modules = new Map();
  function read(name) {
    return fs.readFileSync(base + '/app/' + name + '.ts', 'utf8');
  }
  function evaluate(source, overrides = {}, globals = {}) {
    const exports = {};
    const js = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    const context = {
      exports,
      console,
      AbortController,
      DOMException,
      performance,
      Map,
      Set,
      ArrayBuffer,
      Float32Array,
      Uint8Array,
      setTimeout,
      clearTimeout,
      fetch() {
        throw Error('network disabled in audit');
      },
      require(id) {
        if (id in overrides) return overrides[id];
        if (id === 'three') return THREE;
        if (
          id.startsWith('./') &&
          fs.existsSync(base + '/app/' + id.slice(2) + '.ts')
        )
          return load(id.slice(2));
        return {};
      },
      ...globals,
    };
    vm.runInNewContext(js, context);
    return exports;
  }
  function load(name) {
    if (!modules.has(name)) modules.set(name, evaluate(read(name)));
    return modules.get(name);
  }
  function deferred() {
    let resolve, reject;
    const promise = new Promise((a, b) => {
      resolve = a;
      reject = b;
    });
    return { promise, resolve, reject };
  }

  const { WorldInterior } = load('world-interior');
  const { EntityRegistry } = load('entity-registry');
  const { CampusScene } = evaluate(read('scene'));
  const registry = new EntityRegistry({ entities: [] });
  const interior = new WorldInterior(new THREE.Scene(), registry, () => {});
  interior.floor = (f, signal) =>
    new Promise((resolve, reject) =>
      signal.addEventListener(
        'abort',
        () => reject(new DOMException('Cancelled', 'AbortError')),
        { once: true },
      ),
    );
  const scene = Object.create(CampusScene.prototype);
  Object.assign(scene, {
    opened: { entityId: 'building:A' },
    floorId: '',
    floorRequest: 0,
    dead: false,
    registry,
    interior,
    masks: { enable() {} },
    footprints: [{ officialBuildingId: 'A' }],
    buildingFloors: () => [{ id: 'A-LG' }],
    updateOpening() {},
    updateFacilities() {},
    notify() {},
  });
  const pendingFloor = scene.setFloor('A-LG');
  scene.opened = null;
  interior.stop();
  await pendingFloor;
  console.log(
    'PASS fixed: close during pending floor has no null-building continuation',
  );

  scene.opened = { entityId: 'building:A' };
  scene.footprints = [];
  const layers = [];
  interior.floor = (f) => {
    const d = deferred();
    layers.push({ ...d, id: f.id });
    return d.promise;
  };
  scene.buildingFloors = () => [{ id: 'A-LG' }, { id: 'A-1' }];
  const older = scene.setFloor('A-LG'),
    newer = scene.setFloor('A-1');
  layers[1].resolve({ id: 'A-1', rooms: [] });
  assert.equal(await newer, true);
  layers[0].resolve({ id: 'A-LG', rooms: [] });
  assert.equal(await older, false);
  assert.equal(scene.floorId, 'A-1');
  assert.equal(interior.data[0].id, 'A-1');
  console.log(
    'PASS fixed: old floor resolving after newer floor cannot change current floor',
  );

  interior.data = [{ id: 'A-LG', rooms: [] }];
  const pendingBoundary = interior.show([{ id: 'A-1' }], 'A-1');
  interior.setBoundary(2);
  assert.equal(interior.data.length, 0);
  assert.equal(interior.root.children.length, 0);
  interior.stop();
  layers.at(-1).resolve({ id: 'A-1', rooms: [] });
  await pendingBoundary;
  console.log(
    'PASS fixed: changing boundary while loading cannot resurrect old floor',
  );

  const { AtomicTextures } = load('atomic-textures');
  const atomic = new AtomicTextures();
  const original = new THREE.Texture(),
    low = new THREE.Texture();
  atomic.catalog.set('tile', { materials: { 0: { url: '/original' } } });
  atomic.commit(new Map([['/original', original]]));
  const material = new THREE.MeshBasicMaterial({ map: low });
  atomic.register('tile', material, 0);
  assert.equal(material.map, original);
  atomic.dispose();
  material.dispose();
  low.dispose();
  console.log(
    'PASS fixed: late baseline material binds already committed original',
  );

  const page = fs.readFileSync(base + '/app/page.tsx', 'utf8');
  const floorMatch = page.match(
    /async function selectFloor\(id:string\)\{([^\n]*)\}/,
  );
  const connectorMatch = page.match(
    /onClick=\{async\(\)=>\{await selectFloor\(s.sourceFloorId\);([^}]*)\}\}/,
  );
  if (!floorMatch || !connectorMatch) {
    const fn = page
      .split('\n')
      .find((line) => line.includes('async function selectFloor('));
    assert.ok(fn, 'current selectFloor function exists');
    const js = ts.transpileModule(fn, {
      compilerOptions: { target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const request = deferred(),
      intent = { current: 0 },
      events = [];
    let selectedId = 'connector:A';
    const context = {
      intent,
      scene: {
        current: {
          setFloor() {
            return request.promise;
          },
          floorView() {
            events.push('floorView');
          },
          selectEntity(id) {
            events.push('reselect ' + id);
          },
        },
      },
      registry: { get: (id) => ({ entityId: id }) },
      setStack() {},
      setSelectedId(id) {
        selectedId = id;
      },
      setError(message) {
        events.push('error ' + message);
      },
    };
    const pending = vm.runInNewContext(
      js + ';selectFloor("A-LG","connector:A")',
      context,
    );
    intent.current++;
    selectedId = 'space:B-room';
    request.resolve(true);
    assert.equal(await pending, false);
    assert.equal(selectedId, 'space:B-room');
    assert.equal(events.length, 0);
    console.log(
      'PASS fixed: newer page intent prevents old connector selection and camera move',
    );
    context.scene.current.setFloor = () =>
      Promise.reject(Error('mock floor HTTP failure'));
    assert.equal(
      await vm.runInNewContext(js + ';selectFloor("A-LG")', context),
      false,
    );
    assert.equal(events.length, 1);
    assert.ok(events[0].startsWith('error '));
    console.log(
      'PASS fixed: failed floor request returns false and reports error without unhandled rejection',
    );
  } else {
    const request = deferred(),
      events = [];
    let selectedId = 'connector:A',
      opened = 'A';
    const scene = {
      current: {
        setFloor() {
          events.push('start A floor');
          return request.promise;
        },
        floorView() {
          events.push('stale floorView');
        },
        selectEntity(id) {
          selectedId = id;
          opened = 'A';
          events.push('old connector reopens A');
        },
      },
    };
    const context = {
      scene,
      registry: { get: (id) => ({ entityId: id }) },
      selected: { entityId: 'connector:A' },
      s: { sourceFloorId: 'A-LG' },
      setStack() {},
      setSelectedId(id) {
        selectedId = id;
      },
      console,
    };
    const code =
      'async function selectFloor(id){' +
      floorMatch[1] +
      '};async function stopClick(){await selectFloor(s.sourceFloorId);' +
      connectorMatch[1] +
      '};stopClick()';
    const oldClick = vm.runInNewContext(code, context);
    selectedId = 'space:B-room';
    opened = 'B';
    events.push('new user intent selects B room');
    request.resolve();
    await oldClick;
    assert.equal(selectedId, 'connector:A');
    assert.equal(opened, 'A');
    console.log('REPRODUCED page connector race:', events.join(' -> '));
  }

  const flush = () => new Promise((resolve) => setImmediate(resolve));
  const { SpatialMasks } = load('spatial-masks');
  const bundles = ['A', 'B', 'C', 'D'].map((id) => ({
    id,
    buildingId: id,
    buildingName: id,
    bounds: { min: [-10, 0, -10], max: [10, 10, 10] },
    objects: [{ url: id + '.glb', textureDimensions: [[16,16]], textureDecodedBytes: 1024 }],
    textureDecodedBytes: 1024,
    mask: {
      url: id + '.png',
      width: 1,
      height: 1,
      heightMin: 0,
      boundsXZ: { min: [-10, -10], max: [10, 10] },
    },
  }));
  function exteriorFixture() {
    const loads = [],
      calls = [],
      bitmaps = [],
      disposed = [];
    const mask = deferred();
    class FakeGLTFLoader {
      register(plugin) {
        this.plugin = plugin;
      }
      parseAsync(data) {
        const request = deferred();
        const parser = {
          associations: new Map(),
          fileLoader: { abort() {} },
          textureLoader: {},
        };
        this.plugin(parser);
        loads.push({ ...request, url: data.url, parser });
        return request.promise;
      }
    }
    const { CoherentExteriors } = evaluate(
      read('coherent-exteriors'),
      {
        'three/addons/loaders/GLTFLoader.js': { GLTFLoader: FakeGLTFLoader },
      },
      {
        fetch: async (url, { signal }) => {
          calls.push({ url, signal });
          return {
            ok: true,
            arrayBuffer: async () => ({ url }),
            blob: async () => ({ url }),
          };
        },
        createImageBitmap: () => mask.promise,
      },
    );
    const masks = new SpatialMasks();
    const exterior = new CoherentExteriors(new THREE.Scene(), masks, () => {});
    exterior.bundles = bundles;
    function model(id) {
      const image = {
        closed: 0,
        close() {
          this.closed++;
        },
      };
      bitmaps.push(image);
      const texture = new THREE.Texture(image);
      const material = new THREE.MeshBasicMaterial({ map: texture });
      const geometry = new THREE.BoxGeometry();
      geometry.addEventListener('dispose', () => disposed.push(id));
      const group = new THREE.Group();
      group.add(new THREE.Mesh(geometry, material));
      return { scene: group };
    }
    return { exterior, loads, calls, bitmaps, disposed, mask, model, masks };
  }
  const x = exteriorFixture();
  x.exterior.request(bundles[0]);
  await flush();
  for (const bundle of bundles.slice(1)) x.exterior.request(bundle);
  assert.equal(x.loads.length, 1);
  assert.equal(x.exterior.pending.id, 'A');
  assert.equal(x.exterior.wanted, 'D');
  assert.equal(x.calls[0].signal.aborted, true);
  console.log(
    'PASS fixed: 4 quick targets leave 1 in-flight GLTF and abort its actual fetch signal',
  );
  x.exterior.dispose();
  x.loads[0].resolve(x.model('A'));
  await flush();
  assert.equal(x.exterior.pending, null);
  assert.equal(x.exterior.root.children.length, 0);
  assert.equal(x.exterior.visible.size, 0);
  assert.deepEqual(x.disposed, ['A']);
  assert.ok(x.bitmaps.every((image) => image.closed === 1));
  assert.equal(x.calls.length, 1);
  x.masks.dispose();
  console.log(
    'PASS disposal: late cancelled exterior geometry and original bitmap are released exactly once with no restart',
  );

  const serial = exteriorFixture();
  serial.exterior.request(bundles[0]);
  await flush();
  for (const bundle of bundles.slice(1)) serial.exterior.request(bundle);
  assert.equal(serial.loads.length, 1);
  assert.equal(serial.exterior.wanted, 'D');
  serial.loads[0].resolve(serial.model('A'));
  await flush();
  assert.equal(serial.loads.length, 2);
  assert.ok(serial.loads[1].url.endsWith('D.glb'));
  assert.deepEqual(serial.disposed, ['A']);
  assert.equal(serial.bitmaps[0].closed, 1);
  assert.equal(
    serial.calls.some((call) => /[BC]\.glb$/.test(call.url)),
    false,
  );
  serial.loads[1].resolve(serial.model('D'));
  await flush();
  assert.equal(serial.exterior.visible.size, 0);
  assert.equal(serial.exterior.pending.id, 'D');
  serial.exterior.dispose();
  const lateMask = {
    width: 1,
    height: 1,
    closed: 0,
    close() {
      this.closed++;
    },
  };
  serial.mask.resolve(lateMask);
  await flush();
  assert.equal(lateMask.closed, 1);
  assert.equal(serial.exterior.pending, null);
  assert.equal(serial.exterior.root.children.length, 0);
  assert.equal(serial.exterior.visible.size, 0);
  assert.deepEqual(serial.disposed, ['A', 'D']);
  assert.ok(serial.bitmaps.every((image) => image.closed === 1));
  serial.masks.dispose();
  console.log(
    'PASS current serialization: latest D starts after cancelled A cleanup, B/C never load, late D mask closes without committing',
  );
}
void main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
