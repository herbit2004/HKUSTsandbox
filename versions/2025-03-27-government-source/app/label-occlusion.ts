import type {
  BuildingFootprint,
  Point3,
  PointXZ,
  PolygonPart,
} from './source-types';

const EPSILON = 1e-7;

export interface BuildingOccluder {
  readonly buildingId: string;
  readonly parts: readonly PolygonPart[];
  readonly minX: number;
  readonly maxX: number;
  readonly minZ: number;
  readonly maxZ: number;
  readonly minY: number;
  readonly maxY: number;
}

/** Build once after source footprints arrive; unknown heights are not invented. */
export function createBuildingOccluders(
  footprints: readonly BuildingFootprint[],
): BuildingOccluder[] {
  const result: BuildingOccluder[] = [];
  for (const footprint of footprints) {
    const minY = footprint.minObservedFloorZ;
    const maxY = footprint.maxObservedFloorZ;
    if (
      typeof minY !== 'number' ||
      typeof maxY !== 'number' ||
      !Number.isFinite(minY) ||
      !Number.isFinite(maxY) ||
      maxY <= minY
    )
      continue;
    const parts = footprint.parts.filter(
      (part) =>
        part.rings[0]?.length >= 3 &&
        part.rings.every((ring) =>
          ring.every((p) => Number.isFinite(p[0]) && Number.isFinite(p[1])),
        ),
    );
    if (!parts.length) continue;
    let minX = Infinity,
      maxX = -Infinity,
      minZ = Infinity,
      maxZ = -Infinity;
    for (const part of parts)
      for (const ring of part.rings)
        for (const [x, z] of ring) {
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
          minZ = Math.min(minZ, z);
          maxZ = Math.max(maxZ, z);
        }
    result.push({
      buildingId: footprint.officialBuildingId,
      parts,
      minX,
      maxX,
      minZ,
      maxZ,
      minY,
      maxY,
    });
  }
  return result;
}

// 0 outside, 1 strictly inside, 2 boundary. A tangent does not hide a label.
function ringLocation(
  x: number,
  z: number,
  ring: readonly PointXZ[],
): 0 | 1 | 2 {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[j],
      b = ring[i];
    const dx = b[0] - a[0],
      dz = b[1] - a[1];
    const cross = (x - a[0]) * dz - (z - a[1]) * dx;
    if (
      Math.abs(cross) <= EPSILON * Math.max(1, Math.abs(dx) + Math.abs(dz)) &&
      x >= Math.min(a[0], b[0]) - EPSILON &&
      x <= Math.max(a[0], b[0]) + EPSILON &&
      z >= Math.min(a[1], b[1]) - EPSILON &&
      z <= Math.max(a[1], b[1]) + EPSILON
    )
      return 2;
    if (a[1] > z !== b[1] > z && x < a[0] + ((z - a[1]) * dx) / dz)
      inside = !inside;
  }
  return inside ? 1 : 0;
}

function insideParts(
  x: number,
  z: number,
  parts: readonly PolygonPart[],
): boolean {
  return parts.some(
    (part) =>
      ringLocation(x, z, part.rings[0]) === 1 &&
      part.rings.slice(1).every((hole) => ringLocation(x, z, hole) === 0),
  );
}

/**
 * Segment/volume visibility using actual footprint rings and observed floor Z.
 * AABBs only reject candidates. Concave yards and holes remain open. The source
 * floor interval is conservative and does not assert a measured roof or walls.
 */
export function markerOccluded(
  camera: Point3,
  marker: Point3,
  occluders: readonly BuildingOccluder[],
  selfBuildingId?: string,
): boolean {
  if (!camera.every(Number.isFinite) || !marker.every(Number.isFinite))
    return false;
  const dx = marker[0] - camera[0],
    dy = marker[1] - camera[1],
    dz = marker[2] - camera[2];
  const planarLengthSquared = dx * dx + dz * dz;
  for (const building of occluders) {
    if (building.buildingId === selfBuildingId) continue;
    let start = 0,
      end = 1;
    // Intersect the open segment with the broad box and known source-height slab.
    let rejected = false;
    for (const [origin, delta, min, max] of [
      [camera[0], dx, building.minX, building.maxX],
      [camera[1], dy, building.minY, building.maxY],
      [camera[2], dz, building.minZ, building.maxZ],
    ]) {
      if (Math.abs(delta) <= EPSILON) {
        if (origin <= min + EPSILON || origin >= max - EPSILON) {
          rejected = true;
          break;
        }
      } else {
        const a = (min - origin) / delta,
          b = (max - origin) / delta;
        start = Math.max(start, Math.min(a, b));
        end = Math.min(end, Math.max(a, b));
      }
    }
    if (rejected || end - start <= EPSILON) continue;
    if (planarLengthSquared <= EPSILON * EPSILON) {
      if (insideParts(camera[0], camera[2], building.parts)) return true;
      continue;
    }
    const cuts = [start, end];
    for (const part of building.parts)
      for (const ring of part.rings) {
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const a = ring[j],
            b = ring[i],
            ex = b[0] - a[0],
            ez = b[1] - a[1];
          const qx = a[0] - camera[0],
            qz = a[1] - camera[2];
          const denominator = dx * ez - dz * ex;
          if (Math.abs(denominator) <= EPSILON) {
            // Collinear edges still split at their ends; strict inside testing below
            // prevents their boundary from becoming a solid courtyard obstruction.
            if (Math.abs(qx * dz - qz * dx) <= EPSILON)
              for (const point of [a, b]) {
                const t =
                  ((point[0] - camera[0]) * dx + (point[1] - camera[2]) * dz) /
                  planarLengthSquared;
                if (t > start && t < end) cuts.push(t);
              }
            continue;
          }
          const t = (qx * ez - qz * ex) / denominator;
          const u = (qx * dz - qz * dx) / denominator;
          if (t > start && t < end && u >= -EPSILON && u <= 1 + EPSILON)
            cuts.push(t);
        }
      }
    cuts.sort((a, b) => a - b);
    for (let i = 1; i < cuts.length; i++) {
      if (cuts[i] - cuts[i - 1] <= EPSILON) continue;
      const t = (cuts[i] + cuts[i - 1]) / 2;
      if (insideParts(camera[0] + dx * t, camera[2] + dz * t, building.parts))
        return true;
    }
  }
  return false;
}
