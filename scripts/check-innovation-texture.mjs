/** Real Three GLTF parsing and Sharp PNG decoding; no WebGL/browser claim. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { Box3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const directory = new URL(
  '../public/models/current-forms/innovation/',
  import.meta.url,
);
const manifest = JSON.parse(
  await fs.readFile(new URL('manifest.json', directory), 'utf8'),
);
const raw = await fs.readFile(new URL(manifest.asset.url, directory));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
assert.equal(sha(raw), manifest.asset.sha256);
assert.equal(raw.length, manifest.asset.bytes);
const source = JSON.parse(
  raw.subarray(20, 20 + raw.readUInt32LE(12)).toString(),
);
const decoded = [];
globalThis.self = globalThis;
globalThis.ProgressEvent = class extends Event {
  constructor(name, properties = {}) {
    super(name);
    Object.assign(this, properties);
  }
};
const nativeFetch = globalThis.fetch;
globalThis.fetch = (url, options) => {
  assert.ok(
    (typeof url === 'string'
      ? url
      : url instanceof URL
        ? url.href
        : url.url
    ).startsWith('blob:'),
    'GLB must parse without external network resources',
  );
  return nativeFetch(url, options);
};
globalThis.createImageBitmap = async (blob) => {
  const bytes = Buffer.from(await blob.arrayBuffer());
  const { data, info } = await sharp(bytes)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const texture = manifest.appearanceTextures.find(
    (item) => item.sha256 === sha(bytes),
  );
  assert.ok(
    texture,
    'Every embedded decoded image must match its saved texture SHA',
  );
  assert.deepEqual([info.width, info.height], texture.dimensions);
  assert.equal(data.length, texture.baseRGBABytes);
  const reference = await fs.readFile(new URL(texture.asset, directory));
  assert.equal(sha(reference), texture.sha256);
  assert.deepEqual(bytes, reference);
  assert.equal(texture.embeddedByteEqual, true);
  decoded.push({
    asset: texture.asset,
    bytes: bytes.length,
    sha256: sha(bytes),
    dimensions: texture.dimensions,
  });
  // Bitmap adapter provides real decoded dimensions/data to Three; it is not a GPU upload.
  return { width: info.width, height: info.height, data, close() {} };
};
const gltf = await new GLTFLoader().parseAsync(
  raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength),
  '',
);
const meshObjects = [],
  maps = new Set();
gltf.scene.traverse((object) => {
  if (!object.isMesh) return;
  meshObjects.push(object);
  assert.ok(!Array.isArray(object.material));
  if (object.material.map) {
    maps.add(object.material.map);
    const uv = object.geometry.getAttribute('uv');
    assert.equal(uv.count, object.geometry.getAttribute('position').count);
    const finiteUV = [...uv.array].every(Number.isFinite);
    assert.ok(finiteUV);
    const repeatUV =
      object.name.startsWith('layer-transition-') ||
      object.material.name?.includes('roof');
    if (!repeatUV) {
      assert.ok([...uv.array].every((v) => v >= 0 && v <= 1));
    }
    assert.equal(object.material.map.flipY, false);
    assert.equal(object.material.map.colorSpace, 'srgb');
  }
});
const activeMeshObjects = meshObjects.filter(
  (object) => !object.name.startsWith('layer-transition-'),
);
// The current closed asset has 14 closure meshes and no renderable primitive on
// the eight inactive source-floor nodes. Keep both counts explicit: the
// expected 73 audited objects are 65 active exterior/roof meshes + 8 inactive
// source-floor nodes, while GLTFLoader traverses 79 mesh objects including the
// 14 closure meshes.
assert.equal(meshObjects.length, 79);
assert.equal(activeMeshObjects.length + 8, 73);
const mappedMeshObjects = meshObjects.filter((object) => object.material.map);
const mappedFacadeMeshes = activeMeshObjects.filter(
  (object) => object.material.map && !object.name.startsWith('approx-roof-cap'),
);
const mappedRoofTerraceMeshes = meshObjects.filter(
  (object) =>
    object.material.map &&
    (object.name.startsWith('layer-transition-') ||
      object.name.startsWith('approx-roof-cap')),
);
assert.equal(mappedFacadeMeshes.length, 64);
assert.equal(mappedRoofTerraceMeshes.length, 8);
assert.equal(mappedMeshObjects.length, 72);
assert.equal(maps.size, 3);
assert.equal(decoded.length, 3);
const triangles = meshObjects.reduce(
  (n, object) =>
    n +
    (object.geometry.index?.count ??
      object.geometry.getAttribute('position').count) /
      3,
  0,
);
assert.equal(triangles, 69573);
assert.equal(triangles, manifest.triangles);
const bounds = new Box3().setFromObject(gltf.scene);
assert.deepEqual(bounds.min.toArray(), manifest.bounds.min);
assert.deepEqual(bounds.max.toArray(), manifest.bounds.max);
const floors = source.nodes.filter(
  (node) => node.extras?.representationRole === 'exact_source_floor_parts',
);
assert.equal(floors.length, 8);
const windows = source.nodes.filter((node) =>
  node.name.startsWith('approx-window-band-'),
);
assert.equal(windows.length, 8);
const floorWindowMapping = floors.map((floor) => {
  const window = windows.filter(
    (node) => node.extras.sourceFloorId === floor.extras.sourceFloorId,
  );
  assert.equal(
    window.length,
    1,
    'Only one window band per original source floor',
  );
  const lo = window[0].extras.sourceBottomY;
  assert.equal(lo, floor.extras.sourceZValues[0]);
  return {
    floor: floor.extras.floorName,
    sourceZ: lo,
    glazedY: [lo + 1.2, lo + 3.45],
  };
});
const textureRGBABytes = manifest.appearanceTextures.reduce(
  (total, texture) => total + texture.baseRGBABytes,
  0,
);
const textureRGBAWithMipBytes = manifest.appearanceTextures.reduce(
  (total, texture) => total + texture.rgbaWithMipBytes,
  0,
);
const report = {
  status: 'pass',
  implementation:
    'Installed Three GLTFLoader + real Sharp PNG decode, bitmap adapter; no WebGL/GPU or browser rendering claim',
  sha256: sha(raw),
  glbBytes: raw.length,
  gltfMeshDefinitions: source.meshes.length,
  threeRenderMeshObjects: meshObjects.length,
  activeThreeRenderMeshObjects: activeMeshObjects.length,
  texturedRenderMeshes: mappedMeshObjects.length,
  mappedFacadeMeshes: mappedFacadeMeshes.length,
  mappedRoofTerraceMeshes: mappedRoofTerraceMeshes.length,
  triangles,
  decoded,
  textureRGBABytes,
  textureRGBAWithMipBytes,
  externalRequests: 0,
  floorWindowMapping,
  sourceGeometryByteComparison:
    'texture-geometry-validation.json and scripts/validate-registry.py',
};
await fs.writeFile(
  new URL('three-texture-validation.json', directory),
  JSON.stringify(report, null, 2) + '\n',
);
console.log(
  JSON.stringify(
    {
      ...report,
      floorWindowMapping: '8 source floors, one glazed interval each',
      report: fileURLToPath(
        new URL('three-texture-validation.json', directory),
      ),
    },
    null,
    2,
  ),
);
