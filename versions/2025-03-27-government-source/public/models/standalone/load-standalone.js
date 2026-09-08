// Use your existing Three.js and GLTFLoader imports; this file has no package assumptions.
export async function loadStandalone({ THREE, loader, entry, manifestUrl }) {
  const url = new URL(entry.url, new URL(manifestUrl, location.href));
  const gltf = await loader.loadAsync(url.href);
  const group = new THREE.Group();
  group.name = `standalone-${entry.catalogId}`;
  group.position.fromArray(entry.offset);
  group.add(gltf.scene);
  group.userData = { catalogId: entry.catalogId, sourceModelId: entry.id };
  // GLTFLoader has already applied original node matrices. No added rotation or height shift.
  group.updateMatrixWorld(true);
  return group;
}
