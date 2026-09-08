import * as THREE from 'three';
import { EntityRegistry } from './entity-registry';
import {
  SpatialMasks,
  replacementSlots,
  spatialMaskNames,
  type SpatialMaskRole,
} from './spatial-masks';
import type { BuildingFootprint, PointXZ, PolygonPart } from './source-types';

/** Ownership is attached only to actual individual bodies, never shared terraces. */
export function exteriorSourceOwner(
  object: THREE.Object3D,
  bundleEntityId: string,
  overrides: readonly { sourceObjectId: string; entityId: string }[],
): string | undefined {
  if (object.userData.sourceRole === 'source-photogrammetry-gap-surface' ||
      object.userData.sourceOwnership === 'domain-only') return undefined;
  // A complete shared/range envelope belongs to the aggregate zone itself.
  // Member buildings remain unresolved unless a separate source-backed split
  // is recorded; the whole object is never assigned to one arbitrary member.
  if (object.userData.sourceOwnership === 'aggregate-source') return bundleEntityId;
  return overrides.find(owner => owner.sourceObjectId === object.userData.sourceObjectId)?.entityId ?? bundleEntityId;
}

type PixelImage = {
  width: number;
  height: number;
  data: ArrayLike<number>;
  channels: number;
};
const pixels = new WeakMap<object, PixelImage>();

function imagePixels(texture: THREE.Texture): PixelImage {
  const image = texture.image as {
    width: number;
    height: number;
    data?: ArrayLike<number>;
  };
  const saved = pixels.get(image);
  if (saved) return saved;
  const { width, height } = image;
  let data = image.data;
  if (!data) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Source mask pixel reader unavailable');
    context.drawImage(image as CanvasImageSource, 0, 0);
    data = context.getImageData(0, 0, width, height).data;
  }
  const result = {
    width,
    height,
    data,
    channels: data.length / (width * height),
  };
  pixels.set(image, result);
  return result;
}

/** The mask textures use source row order, flipY=false, nearest/clamp sampling. */
function maskSample(
  masks: SpatialMasks,
  name: string,
  point: THREE.Vector3,
): number[] | null {
  const slot = masks.slots[name];
  if (!slot.enabled.value) return null;
  const b = slot.bounds.value;
  if (point.x < b.x || point.x > b.z || point.z < b.y || point.z > b.w)
    return null;
  const p = imagePixels(slot.texture.value);
  const col = Math.min(
    p.width - 1,
    Math.floor(((point.x - b.x) / (b.z - b.x)) * p.width),
  );
  const row = Math.min(
    p.height - 1,
    Math.floor(((point.z - b.y) / (b.w - b.y)) * p.height),
  );
  const index = (row * p.width + col) * p.channels;
  return [
    p.data[index],
    p.channels > 1 ? p.data[index + 1] : 0,
    p.channels > 2 ? p.data[index + 2] : 0,
    p.channels > 3 ? p.data[index + 3] : 255,
  ];
}

function hitMaterial(hit: THREE.Intersection): THREE.Material | undefined {
  if (!(hit.object instanceof THREE.Mesh)) return undefined;
  return Array.isArray(hit.object.material)
    ? hit.object.material[hit.face?.materialIndex ?? 0]
    : hit.object.material;
}

function normalY(hit: THREE.Intersection): number {
  if (!hit.face) return 0;
  return Math.abs(
    hit.face.normal
      .clone()
      .applyNormalMatrix(
        new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld),
      ).y,
  );
}

function isRole(value: unknown): value is SpatialMaskRole {
  return (
    value === 'terrain' ||
    value === 'baseline' ||
    value === 'photogrammetry' ||
    value === 'exterior' ||
    value === 'supplement'
  );
}

/** A real source ground sample, using the same height and face-slope test as GLSL. */
function preservedGround(
  hit: THREE.Intersection,
  masks: SpatialMasks,
): boolean {
  const sample = maskSample(masks, 'groundReference', hit.point);
  return (
    !!sample &&
    sample[0] > 127 &&
    Math.abs(hit.point.y - sample[1] - sample[2] / 256) <=
      masks.slots.groundReference.heightClearance.value &&
    normalY(hit) >= 0.6
  );
}

function preservedCurrentFormSource(hit: THREE.Intersection, masks: SpatialMasks) {
  if (!hitMaterial(hit)?.userData.sourceProtectionSampler) return false;
  const p = maskSample(masks, 'sourceProtection', hit.point);
  if (!p) return false;
  const ground = p[0] > 0 && Math.abs(hit.point.y - p[0] - p[1] / 256) <=
    masks.slots.sourceProtection.heightClearance.value && normalY(hit) >= 0.6;
  const structure = p[2] < 255 && p[3] < 255 && hit.point.y >= p[2] && hit.point.y <= p[3] &&
    masks.insideSourceProtection(hit.point.x, hit.point.z);
  return ground || structure;
}

/** CPU equivalent of SpatialMasks' fragment discard, shared by clicks and PAN.
 * This tests real triangle intersections; it never substitutes a tile box.
 */
export function isVisibleSurfaceHit(
  hit: THREE.Intersection,
  masks: SpatialMasks,
): boolean {
  for (
    let object: THREE.Object3D | null = hit.object;
    object;
    object = object.parent
  )
    if (!object.visible || object.userData.pickable === false) return false;
  const material = hitMaterial(hit);
  if (
    !material ||
    !material.visible ||
    material.opacity <= 0.05 ||
    ('wireframe' in material && material.wireframe === true)
  )
    return false;
  const planes = material.clippingPlanes;
  if (planes?.length) {
    const outside = planes.map((plane) => plane.distanceToPoint(hit.point) < 0);
    if (
      material.clipIntersection ? outside.every(Boolean) : outside.some(Boolean)
    )
      return false;
  }
  const role: unknown = material.userData.spatialMaskRole;
  if (!isRole(role)) return true;
  const point = hit.point;
  for (const name of spatialMaskNames(role)) {
    if (name === 'groundReference' || name === 'sourceProtection') continue;
    const replacement = replacementSlots.includes(name);
    if (role === 'terrain' && replacement) continue;
    const slot = masks.slots[name];
    if (point.y < slot.minY.value || point.y > slot.maxY.value) continue;
    if (role === 'terrain' && name === 'coverage') {
      const currentForm = maskSample(masks, 'currentForms', point);
      const inReplacement = replacementSlots.some(
        (n) => (maskSample(masks, n, point)?.[0] ?? 0) > 127,
      ) || !!currentForm && currentForm[0] > 254 && currentForm[1] > 254 && currentForm[2] > 254;
      const hasGround =
        (maskSample(masks, 'groundReference', point)?.[0] ?? 0) > 127;
      if (inReplacement && !hasGround) continue;
    }
    if (
      (role === 'baseline' || role === 'photogrammetry') &&
      replacement &&
      preservedGround(hit, masks)
    )
      continue;
    const sample = maskSample(masks, name, point);
    if (!sample) continue;
    if (name === 'currentForms' && (role === 'baseline' || role === 'photogrammetry') &&
      (preservedGround(hit, masks) || preservedCurrentFormSource(hit, masks))) continue;
    if (name === 'currentForms' && sample[3] < 255 && point.y < sample[3]) continue;
    const occupied =
      role === 'photogrammetry' && replacement && slot.coreOnly.value > 0.5
        ? sample[1]
        : sample[0];
    if (
      occupied > 127 &&
      (slot.heightEncoded.value < 0.5 ||
        (point.y <= sample[1] + sample[2] / 256 + slot.heightClearance.value &&
          (slot.heightEncoded.value > 1.5 || normalY(hit) >= 0.6)))
    )
      return false;
  }
  return true;
}

function segmentDistance(x: number, z: number, a: PointXZ, b: PointXZ): number {
  const dx = b[0] - a[0],
    dz = b[1] - a[1];
  const t = Math.max(
    0,
    Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz || 1)),
  );
  return Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz);
}

function inRing(x: number, z: number, ring: PointXZ[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i],
      b = ring[j];
    // Treat the actual boundary as part of the polygon; no expanded AABB/domain.
    if (segmentDistance(x, z, a, b) <= 0.0001) return true;
    if (
      a[1] > z !== b[1] > z &&
      x < ((b[0] - a[0]) * (z - a[1])) / (b[1] - a[1]) + a[0]
    )
      inside = !inside;
  }
  return inside;
}

export function insideSourceFootprint(
  x: number,
  z: number,
  rings: PointXZ[][],
): boolean {
  return (
    !!rings[0] &&
    inRing(x, z, rings[0]) &&
    !rings.slice(1).some((ring) => inRing(x, z, ring))
  );
}

export type PickingRoad = {
  entityId: string;
  linesLocalXZ: PointXZ[][];
  segments: Array<{ displayGroundReference: boolean }>;
};
export type PickingSurface = { entityId: string; parts: PolygonPart[] };
export type SourceAssociation = PickingSurface & {
  minY: number;
  maxY: number;
  roles: string[];
};
export type SourceBuildingDomain = PickingSurface & {
  sharedPhysicalEnvelopeWith?: string;
  minY: number;
  maxY: number;
  boundaryToleranceMeters?: number;
};
export type SourceRangeDomain = SourceBuildingDomain & {
  physicalDomainId: string;
  sourceObjectIds: string[];
};
export type EntityPickingContext = {
  registry: EntityRegistry;
  masks: SpatialMasks;
  footprints: BuildingFootprint[];
  buildingDomains?: SourceBuildingDomain[];
  /** Named multi-tower ranges stay zones; they never become invented buildings. */
  rangeDomains?: SourceRangeDomain[];
  roots: THREE.Object3D[];
  /** Only individually attributed source objects; exclude fused photo supplements. */
  owners?: Map<THREE.Object3D, string>;
  groundAt: (x: number, z: number) => number | null;
  roads?: PickingRoad[];
  surfaces?: PickingSurface[];
  sourceAssociations?: SourceAssociation[];
};
export type EntityPick = {
  hit: THREE.Intersection;
  entityId?: string;
  method: string;
  physicalDomainId?: string;
};

function explicitEntity(
  hit: THREE.Intersection,
  context: EntityPickingContext,
): string | undefined {
  for (
    let object: THREE.Object3D | null = hit.object;
    object;
    object = object.parent
  ) {
    const owner = context.owners?.get(object);
    if (owner) {
      const entity = context.registry.get(owner);
      return entity?.type === 'zone' ? entity.entityId : context.registry.building(entity)?.entityId;
    }
    const id: unknown = object.userData.entityId;
    if (typeof id === 'string') {
      const entity = context.registry.get(id);
      if (entity) return entity.entityId;
    }
  }
  return undefined;
}

/** Return identity only for the nearest *visible* actual surface. An opaque tree
 * or unassigned surface blocks buildings behind it instead of selecting through it.
 */
export function pickEntity(
  ray: THREE.Raycaster,
  context: EntityPickingContext,
): EntityPick | null {
  const meshes = new Set<THREE.Object3D>();
  for (const root of context.roots) {
    let visible = true;
    for (
      let object: THREE.Object3D | null = root;
      object;
      object = object.parent
    )
      visible &&= object.visible;
    if (!visible) continue;
    root.updateWorldMatrix(true, true);
    root.traverseVisible((object) => {
      if (object instanceof THREE.Mesh) meshes.add(object);
    });
  }
  const hits = ray
    .intersectObjects([...meshes], false)
    .filter((hit) => isVisibleSurfaceHit(hit, context.masks));
  const first = hits[0];
  if (!first) return null;
  // Coincident room/facility source polygons are more specific than their floor.
  const near = hits.filter((hit) => hit.distance <= first.distance + 0.02);
  const rank = (id: string) => {
    const type = context.registry.get(id)?.type ?? '';
    return ['space', 'facility', 'connector'].includes(type) ? 0 : type === 'floor' ? 1 : 2;
  };
  const bound = near
    .flatMap((hit) => {
      const id = explicitEntity(hit, context);
      return id ? [{ hit, id }] : [];
    })
    .sort((a, b) => rank(a.id) - rank(b.id));
  if (bound.length)
    return {
      hit: bound[0].hit,
      entityId: bound[0].id,
      method: 'explicit-source-owner',
    };
  const role: unknown = hitMaterial(first)?.userData.spatialMaskRole;
  const sourceOwner = context.sourceAssociations?.find(
    (binding) =>
      typeof role === 'string' &&
      binding.roles.includes(role) &&
      first.point.y >= binding.minY &&
      first.point.y <= binding.maxY &&
      binding.parts.some((part) =>
        insideSourceFootprint(first.point.x, first.point.z, part.rings),
      ),
  );
  if (sourceOwner && context.registry.get(sourceOwner.entityId))
    return {
      hit: first,
      entityId: sourceOwner.entityId,
      method: 'local-source-representation-association',
    };
  const { x, y, z } = first.point;
  const ground = context.groundAt(x, z);
  const groundLike =
    normalY(first) >= 0.6 &&
    ((ground !== null && Math.abs(y - ground) <= 1.25) ||
      preservedGround(first, context.masks));
  if (
    normalY(first) >= 0.6 &&
    (groundLike || (ground !== null && Math.abs(y - ground) <= 2))
  ) {
    const surface = context.surfaces?.filter((s) =>
      s.parts.some((part) => insideSourceFootprint(x, z, part.rings)),
    );
    // Nested football-field/run-track domains select the more specific smaller domain.
    const area = (s: PickingSurface) =>
      s.parts.reduce(
        (sum, part) =>
          sum +
          part.rings.reduce((subtotal, ring, index) => {
            let value = 0;
            for (let i = 0, j = ring.length - 1; i < ring.length; j = i++)
              value += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
            return subtotal + ((index === 0 ? 1 : -1) * Math.abs(value)) / 2;
          }, 0),
        0,
      );
    surface?.sort((a, b) => area(a) - area(b));
    if (surface?.[0] && context.registry.get(surface[0].entityId))
      return {
        hit: first,
        entityId: surface[0].entityId,
        method: 'source-outdoor-domain-near-ground',
      };
  }
  if (!groundLike) {
    const candidates = new Set<string>();
    for (const footprint of context.footprints) {
      if (
        !footprint.parts.some((part) => insideSourceFootprint(x, z, part.rings))
      )
        continue;
      // Public floor Z is a lower support bound, not an invented roof height.
      if (
        footprint.minObservedFloorZ !== undefined &&
        y < footprint.minObservedFloorZ - 0.5
      )
        continue;
      const entity = context.registry.get(
        'building:' + footprint.officialBuildingId,
      );
      if (entity?.type === 'building') candidates.add(entity.entityId);
    }
    for (const domain of context.buildingDomains ?? []) {
      if (y < domain.minY - 0.5) continue;
      if (
        domain.parts.some(
          (part) =>
            insideSourceFootprint(x, z, part.rings) ||
            (!!domain.boundaryToleranceMeters &&
              !part.rings.slice(1).some((ring) => inRing(x, z, ring)) &&
              part.rings[0].some(
                (b, i, ring) =>
                  segmentDistance(
                    x,
                    z,
                    ring[(i + ring.length - 1) % ring.length],
                    b,
                  ) <= domain.boundaryToleranceMeters!,
              )),
        ) &&
        context.registry.get(domain.entityId)?.type === 'building'
      )
        candidates.add(domain.entityId);
    }
    // A named tower body can be part of a legacy shared exterior envelope.
    // Use only an explicit recorded relationship, never nearest-name guessing.
    for (const domain of context.buildingDomains ?? [])
      if (candidates.has(domain.entityId) && domain.sharedPhysicalEnvelopeWith)
        candidates.delete(domain.sharedPhysicalEnvelopeWith);
    if (candidates.size === 1)
      return {
        hit: first,
        entityId: [...candidates][0],
        method: 'source-footprint-and-height',
      };
    if (candidates.size > 1)
      return { hit: first, method: 'ambiguous-source-footprints' };
    let sourceObjectId: string | undefined;
    for (let object: THREE.Object3D | null = first.object; object; object = object.parent) {
      if (typeof object.userData.sourceObjectId === 'string') {
        sourceObjectId = object.userData.sourceObjectId;
        break;
      }
    }
    const ranges = (context.rangeDomains ?? []).filter(domain =>
      context.registry.get(domain.entityId)?.type === 'zone' &&
      y >= domain.minY - .5 && y <= domain.maxY + .5 &&
      (sourceObjectId ? domain.sourceObjectIds.includes(sourceObjectId) :
        role === 'baseline' || role === 'photogrammetry') &&
      domain.parts.some(part => insideSourceFootprint(x, z, part.rings)),
    );
    const rangeOwners = new Set(ranges.map(domain => domain.entityId));
    if (rangeOwners.size === 1)
      return { hit: first, entityId: ranges[0].entityId,
        physicalDomainId: ranges.length === 1 ? ranges[0].physicalDomainId : undefined,
        method: 'source-range-footprint-and-height' };
    if (rangeOwners.size > 1)
      return { hit: first, method: 'ambiguous-source-ranges' };
  }
  if (
    groundLike ||
    (ground !== null && normalY(first) >= 0.6 && Math.abs(y - ground) <= 2)
  ) {
    const roads = (context.roads ?? [])
      .map((road) => ({
        road,
        distance: Math.min(
          Infinity,
          ...road.linesLocalXZ.flatMap((line, j) =>
            road.segments[j]?.displayGroundReference
              ? line.slice(1).map((b, i) => segmentDistance(x, z, line[i], b))
              : [],
          ),
        ),
      }))
      .sort((a, b) => a.distance - b.distance);
    if (roads[0]?.distance < 4)
      return {
        hit: first,
        entityId: roads[0].road.entityId,
        method: 'source-road-near-ground',
      };
  }
  return {
    hit: first,
    method: groundLike ? 'unassigned-ground' : 'unassigned-visible-surface',
  };
}
