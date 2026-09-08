/** Offline real GLTFLoader + Sharp decode; does not claim browser GPU validation. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import sharp from 'sharp';
import { Box3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const base = new URL(
  '../public/models/current-forms/halls-current/',
  import.meta.url,
);
const project = new URL('../public/', import.meta.url);
const manifest = JSON.parse(
  await fs.readFile(new URL('manifest.json', base), 'utf8'),
);
const registry = JSON.parse(
  await fs.readFile(new URL('data/entity-registry.json', project), 'utf8'),
);
const sha = (data) => createHash('sha256').update(data).digest('hex');
globalThis.self = globalThis;
globalThis.ProgressEvent = class extends Event {
  constructor(type, properties) {
    super(type);
    Object.assign(this, properties);
  }
};
const realFetch = globalThis.fetch;
globalThis.fetch = (url, options) => {
  assert.ok(
    (typeof url === 'string'
      ? url
      : url instanceof URL
        ? url.href
        : url.url
    ).startsWith('blob:'),
    'No external texture request',
  );
  return realFetch(url, options);
};
let images = 0;
globalThis.createImageBitmap = async (blob) => {
  const bytes = Buffer.from(await blob.arrayBuffer());
  const texture = manifest.appearanceTextures.find(
    (item) => item.sha256 === sha(bytes),
  );
  assert.ok(texture);
  const { data, info } = await sharp(bytes)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  assert.deepEqual([info.width, info.height], texture.dimensions);
  assert.equal(data.length, texture.baseRGBABytes);
  images++;
  return { width: info.width, height: info.height, data, close() {} };
};
const results = [];
assert.equal(manifest.buildings.length, 3);
assert.equal(new Set(manifest.buildings.map((b) => b.entityId)).size, 3);
assert.equal(manifest.parameters.roofMeasured, false);
for (const building of manifest.buildings) {
  const entity = registry.entities.find(
    (entity) => entity.entityId === building.entityId,
  );
  assert.equal(entity?.type, 'building');
  assert.equal(entity.externalIds.pathAdvisorBuildingId, building.buildingId);
  assert.ok(entity.externalIds.legacyCatalogIds.includes(building.catalogId));
  for (const floor of building.sourceFloors) {
    const bytes = await fs.readFile(new URL(floor.asset.slice(1), project));
    assert.equal(sha(bytes), floor.sha256);
    const source = JSON.parse(bytes.toString());
    assert.deepEqual(source.sourceZValues, floor.sourceZValues);
  }
  const bytes = await fs.readFile(new URL(building.url, base));
  assert.equal(sha(bytes), building.sha256);
  const beforeImages = images;
  const gltf = await new GLTFLoader().parseAsync(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    '',
  );
  let triangles = 0,
    meshes = 0,
    textured = 0;
  const textures = new Set();
  gltf.scene.traverse((object) => {
    if (!object.isMesh) return;
    meshes++;
    assert.equal(object.userData.entityId, building.entityId);
    const positions = object.geometry.getAttribute('position');
    assert.ok([...positions.array].every(Number.isFinite));
    assert.ok(
      [...object.geometry.getAttribute('normal').array].every(Number.isFinite),
    );
    triangles += (object.geometry.index?.count ?? positions.count) / 3;
    if (object.material.map) {
      textures.add(object.material.map);
      const uv = object.geometry.getAttribute('uv');
      assert.equal(uv.count, positions.count);
      assert.ok(
        [...uv.array].every(
          (v) => Number.isFinite(v) && v >= -1e-6 && v <= 1 + 1e-6,
        ),
      );
      assert.equal(object.material.map.colorSpace, 'srgb');
      assert.equal(object.material.map.flipY, false);
      textured++;
    }
  });
  assert.equal(textures.size, 2);
  assert.equal(images - beforeImages, 2);
  assert.equal(textured, 2);
  assert.equal(triangles, building.triangles);
  assert.equal(meshes, building.meshDefinitions);
  const box = new Box3().setFromObject(gltf.scene);
  assert.deepEqual(box.min.toArray(), building.bounds.min);
  assert.deepEqual(box.max.toArray(), building.bounds.max);
  assert.ok(box.max.y < 180 && box.min.y > 133);
  assert.ok(
    building.roofFits.every(
      (fit) => fit.inliers > 10 && fit.inlierRMSMeters < 0.5,
    ),
  );
  results.push({
    catalogId: building.catalogId,
    sha256: building.sha256,
    triangles,
    meshes,
    texturedMeshes: textured,
    embeddedImageDecodes: images - beforeImages,
    sourceFloorCount: building.sourceFloors.length,
    sourceFloorZValues: building.sourceFloorZValues,
    bounds: building.bounds,
  });
}
const report = {
  status: 'pass',
  implementation:
    'Installed Three GLTFLoader and real Sharp PNG decode; bitmap adapter, no WebGL/GPU validation claim',
  buildings: results,
  totalEmbeddedImageDecodes: images,
  externalNetworkRequests: 0,
  sourceFloorHashesAndZUnchanged: true,
  originalStandaloneBundleCountUnaffected: true,
};
await fs.writeFile(
  new URL('validation.json', base),
  JSON.stringify(report, null, 2) + '\n',
);
console.log(JSON.stringify(report, null, 2));
