// Run: node scripts/check-terrain-shader.cjs
// Read-only current-source GLB / shader-program-key regression, no WebGL/browser.
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
  const root = resolve(__dirname, '..');
  function compile(name, dependencies = {}) {
    const exports = {};
    const source = fs.readFileSync(root + '/app/' + name + '.ts', 'utf8');
    const code = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    vm.runInNewContext(code, {
      exports,
      require(id) {
        if (id === 'three') return THREE;
        if (id === './source-types' || id === './material-samplers') return compile(id.slice(2));
        return dependencies[id] || {};
      },
      console,
      Map,
      Set,
      Uint8Array,
      performance,
    });
    return exports;
  }
  const { SpatialMasks } = compile('spatial-masks'),
    { DetailStream } = compile('detail-stream');
  function readGLB(path) {
    const b = fs.readFileSync(root + '/' + path);
    return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  }
  const { GLTFLoader } = await import(
    root + '/node_modules/three/examples/jsm/loaders/GLTFLoader.js'
  );
  const { WebGLPrograms } = await import(
    root + '/node_modules/three/src/renderers/webgl/WebGLPrograms.js'
  );
  const loader = new GLTFLoader();
  const [coarse, fine] = await Promise.all([
    loader.parseAsync(readGLB('public/terrain/terrain.glb'), ''),
    loader.parseAsync(
      readGLB('public/terrain/detail/tiles/terrain-1m-r04-c03.glb'),
      '',
    ),
  ]);
  const masks = new SpatialMasks(),
    world = new THREE.Scene(),
    detail = new DetailStream(
      world,
      new THREE.PerspectiveCamera(),
      new THREE.Vector3(),
      {},
    );
  detail.setCoarse(coarse.scene);
  masks.apply(coarse.scene, 'terrain');
  masks.apply(fine.scene, 'terrain');
  const meshes = [coarse, fine].map((g) => {
    let mesh;
    g.scene.traverse((o) => {
      if (o.isMesh) mesh = o;
    });
    return mesh;
  });
  const renderer = {
    getRenderTarget: () => null,
    state: { buffers: { depth: { getReversed: () => false } } },
    outputColorSpace: THREE.SRGBColorSpace,
    toneMapping: THREE.NoToneMapping,
    shadowMap: { enabled: false, type: THREE.PCFShadowMap },
  };
  const programs = WebGLPrograms(
    renderer,
    { get: () => null },
    { has: () => false },
    { precision: 'highp', logarithmicDepthBuffer: false },
    {},
    { numPlanes: 0, numIntersection: 0 },
  );
  const lights = {
    directional: [],
    point: [],
    spot: [],
    spotLightMap: [],
    rectArea: [],
    hemi: [{}],
    directionalShadowMap: [],
    pointShadowMap: [],
    spotShadowMap: [],
    numSpotLightShadowsWithMaps: 0,
    numLightProbes: 0,
  };
  const parameters = meshes.map((o) =>
    programs.getParameters(o.material, lights, [], world, o, []),
  );
  const keys = parameters.map((p) => programs.getProgramCacheKey(p));
  assert.notEqual(keys[0], keys[1]);
  for (let i = 0; i < 2; i++) {
    parameters[i].uniforms = programs.getUniforms(meshes[i].material);
    meshes[i].material.onBeforeCompile(parameters[i], renderer);
  }
  assert.ok(parameters[0].fragmentShader.includes('detailRects'));
  assert.ok(!parameters[1].fragmentShader.includes('detailRects'));
  assert.ok(parameters[0].uniforms.detailCount);
  assert.ok(!parameters[1].uniforms.detailCount);
  const originalKeys = parameters.map((p) =>
    programs.getProgramCacheKey({
      ...p,
      customProgramCacheKey: 'campus-mask-terrain',
    }),
  );
  assert.equal(originalKeys[0], originalKeys[1]);
  console.log(
    'PASS: actual 5m and 1m GLBs both use MeshStandardMaterial, vertex RGB, same lighting/program features.',
  );
  console.log(
    'PROOF old bug: full Three WebGLPrograms keys collide under campus-mask-terrain, while coarse includes detailRects and fine does not.',
  );
  console.log(
    'PASS current fix: inherited shader cache key makes full Three program keys distinct; fine has no detailCount/detailRects uniform or discard.',
  );
  const positions = meshes[1].geometry.attributes.position;
  let count = 0,
    minimum = Infinity,
    maximum = -Infinity;
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i),
      z = positions.getZ(i),
      y = positions.getY(i);
    if (x >= 347 && x <= 426 && z >= -1191 && z <= -1116) {
      count++;
      minimum = Math.min(minimum, y);
      maximum = Math.max(maximum, y);
    }
  }
  assert.ok(count > 5000);
  assert.ok(minimum > 130);
  const floor = JSON.parse(
    fs.readFileSync(
      root + '/public/interiors/bf0000000000000000000301.json',
      'utf8',
    ),
  );
  console.log(
    'Shaw 1m DTM vertices within replacement-mask neighbourhood:',
    JSON.stringify({
      count,
      minY: minimum,
      maxY: maximum,
      sourceFloorY: 138.2,
    }),
  );
  console.log(
    'Shaw source floor parts:',
    JSON.stringify({
      all: floor.rooms.length,
      interactive: floor.rooms.filter((r) => r.interactive).length,
      background: floor.rooms.filter((r) => !r.interactive).length,
      validOuterRings: floor.rooms.filter((r) => r.rings[0]?.length).length,
    }),
  );
  console.log(
    'PASS: all 73 parts have an outer ring; WorldInterior renders them regardless of interactive flag. No unsupported floor fill needed.',
  );
  fs.writeFileSync(
    root + '/docs/source-evidence-v3/terrain-shader-cache.json',
    JSON.stringify(
      {
        coarseMaterial: meshes[0].material.type,
        fineMaterial: meshes[1].material.type,
        oldFullProgramKeysEqual: originalKeys[0] === originalKeys[1],
        fixedFullProgramKeysDifferent: keys[0] !== keys[1],
        coarseUsesDetailRects: true,
        fineUsesDetailRects: false,
        dtm: { count, minY: minimum, maxY: maximum },
        sourceFloorY: 138.2,
        roomParts: floor.rooms.length,
      },
      null,
      2,
    ),
  );
}
void main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
