/**
 * Three.js loader for the HKUST government mesh subset.
 * Supply THREE and GLTFLoader from the application's existing Three version.
 * No Cesium token, external map service, network geodata API or global origin is needed.
 */
export async function loadGovernmentMesh(THREE, GLTFLoader, manifestUrl, {
  concurrency = 4, unlit = true, signal, onProgress = () => {},
  focus = [400, 30, -1200],
} = {}) {
  const baseUrl = new URL(manifestUrl, window.location.href);
  const response = await fetch(baseUrl, {signal});
  if (!response.ok) throw new Error(`Mesh manifest HTTP ${response.status}`);
  const manifest = await response.json();
  const group = new THREE.Group();
  group.name = 'HKUST — Lands Department original photogrammetric geometry';
  group.userData.manifest = manifest;
  const loader = new GLTFLoader();
  const tiles = [...manifest.tiles].sort((a, b) => {
    const dist = t => t.center.reduce((s, v, i) => s + (v - focus[i]) ** 2, 0);
    return dist(a) - dist(b);
  });
  let next = 0, completed = 0, loadedBytes = 0;
  const failures = [];
  const ready = (async () => {
    await Promise.all(Array.from({length: Math.max(1, Math.min(8, concurrency))}, async () => {
      while (next < tiles.length && !signal?.aborted) {
        const tile = tiles[next++];
        try {
          const gltf = await loader.loadAsync(new URL(tile.url, baseUrl).href);
          const object = gltf.scene;
          if (signal?.aborted) break;
          object.name = tile.id;
          object.userData.source = tile;
          // The matrix already maps raw glTF coordinates to east/up/south.
          // Do not add a Z-up rotation, elevation offset, or second origin subtraction.
          object.applyMatrix4(new THREE.Matrix4().fromArray(tile.matrix));
          object.matrixAutoUpdate = false;
          object.traverse(child => {
            if (!child.isMesh) return;
            child.userData.sourceTileId = tile.id;
            child.castShadow = false;
            child.receiveShadow = false;
            if (unlit) {
              const old = Array.isArray(child.material) ? child.material : [child.material];
              const nextMaterials = old.map(m => new THREE.MeshBasicMaterial({
                map: m.map, color: m.color, side: m.side, transparent: m.transparent,
                opacity: m.opacity, alphaTest: m.alphaTest, vertexColors: m.vertexColors,
              }));
              child.material = Array.isArray(child.material) ? nextMaterials : nextMaterials[0];
              old.forEach(m => m.dispose()); // retains the original texture objects
            }
          });
          group.add(object);
          loadedBytes += tile.bytes;
        } catch (error) { failures.push({id: tile.id, error: String(error)}); }
        completed++;
        onProgress({completed, total: tiles.length, loadedBytes,
          totalBytes: manifest.stats.glbBytes, failures: [...failures]});
      }
    }));
    group.updateMatrixWorld(true);
    return {group, manifest, failures, complete: completed === tiles.length && failures.length === 0};
  })();
  return {group, manifest, ready};
}
