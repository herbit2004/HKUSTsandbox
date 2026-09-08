import * as THREE from 'three';
import { isMesh } from './source-types';

export type BuildingSelectionSource = {
  root: THREE.Object3D;
  kind: 'current-form' | 'source';
};

function isCurrentEnvelope(object: THREE.Object3D): boolean {
  return object.userData.geometryRole === 'approximate_facade' ||
    object.userData.representationRole === 'approximate_exterior_band' ||
    object.name.startsWith('observed-roof-plane-') ||
    object.name.startsWith('observed-tall-core-top-') ||
    object.name.startsWith('photo-observed-pale-core-');
}

/** Outline the displayed physical representation, never a 2D drawing raised to
 * its highest published floor. Merge the envelope triangles before finding edges
 * so coplanar floor/material subdivisions do not become a facade wire grid. */
export function createBuildingSelection(
  sources: readonly BuildingSelectionSource[],
): THREE.LineSegments | null {
  const positions: number[] = [];
  const representedMeshes: string[] = [];
  const point = new THREE.Vector3();
  for (const source of sources) {
    let ancestor: THREE.Object3D | null = source.root;
    while (ancestor?.visible) ancestor = ancestor.parent;
    if (ancestor) continue;
    source.root.updateWorldMatrix(true, true);
    const visit = (object: THREE.Object3D) => {
      if (!object.visible || object.userData.sourceRole === 'source-photogrammetry-gap-surface') return;
      if (isMesh(object) && (source.kind === 'source' || isCurrentEnvelope(object))) {
        const geometry = object.geometry;
        const position = geometry.getAttribute('position');
        const index = geometry.index;
        if (position) {
          const start = geometry.drawRange.start;
          const end = Math.min(index?.count ?? position.count, start + geometry.drawRange.count);
          for (let i = start; i < end; i++) {
            point.fromBufferAttribute(position, index ? index.getX(i) : i).applyMatrix4(object.matrixWorld);
            positions.push(point.x, point.y, point.z);
          }
          representedMeshes.push(object.name || object.uuid);
        }
      }
      for (const child of object.children) visit(child);
    };
    visit(source.root);
  }
  if (!positions.length) return null;
  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  const edges = new THREE.EdgesGeometry(merged, 35);
  merged.dispose();
  if (!edges.getAttribute('position').count) { edges.dispose(); return null; }
  const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({
    color: 0x0b9ebd,
    transparent: true,
    opacity: 0.85,
    depthTest: true,
    depthWrite: false,
  }));
  line.name = 'visible-building-selection';
  line.renderOrder = 20;
  line.userData.representedMeshes = representedMeshes;
  line.userData.selectionSourceKinds = sources.map(source => source.kind);
  return line;
}
