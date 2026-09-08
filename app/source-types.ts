/** DTOs for the checked-in source manifests. Coordinates remain source local X/Y/Z. */
import type * as THREE from "three";

export type PointXZ = [number, number];
export type Point3 = [number, number, number];
export type SourcePosition = [number, number | null, number];
export type Matrix16 = [
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
];
export interface Bounds3 {
  min: Point3;
  max: Point3;
}
export interface BoundsXZ {
  min: PointXZ;
  max: PointXZ;
}
export interface PolygonPart {
  rings: PointXZ[][];
  partIndex?: number;
  sourceZ?: number | null;
  areaSquareMeters?: number;
}

export interface EntityExternalIds {
  pathAdvisorBuildingId?: string;
  pathAdvisorFloorId?: string;
  pathAdvisor?: { building_floor_id?: string };
  legacyCatalogIds?: string[];
  exteriorBundleId?: string;
  exteriorBundleIds?: string[];
  physicalDomainIds?: string[];
  exteriorObjectIds?: string[];
  landsDepartmentModelIds?: string[];
  pathAdvisorNavNodeIds?: string[];
  pathAdvisorPoiIds?: string[];
  pathAdvisorRemoteIds?: string[];
  locationId?: string;
  locationIds?: string[];
  ambiguousLocationIds?: string[];
  officialStreetCode?: string;
  officialStreetCentrelineIds?: string[];
  iB1000PolygonId?: string;
  surfaceNodeId?: string;
}
export interface EntityRepresentation {
  id: string;
  type: string;
  asset: string;
  featureId?: string | number;
  physicalDomainId?: string;
  floorId?: string;
  partIndices?: number[];
  position?: SourcePosition;
  bounds?: Bounds3;
  boundsXZ?: BoundsXZ;
  sourceZValues?: number[];
  sourceZ?: number | null;
  referenceZ?: number;
  subtype?: string;
  sourceId?: string;
  heightMode?: string;
  objects?: Array<{
    id: string;
    asset: string;
    subtype?: string;
    offset?: Point3;
    bounds: Bounds3;
    triangles: number;
    textureDecodedBytes: number;
  }>;
  mask?: Omit<ExteriorMask, "url"> & { asset: string; exactAsset?: string };
  sourceDates?: Record<string, unknown>;
  replacement?: Record<string, unknown>;
  registration?: string;
  depictsEntityId?: string;
  nodeName?: string;
  sourceZRange?: number[];
  textureDate?: string;
  geometrySurveyDate?: string;
  offset?: Point3;
  origin?: Record<string, unknown>;
  positionMethod?: string | null;
  evidence?: string;
  accuracyMeters?: number | null;
  heightMeaning?: string;
  format?: string;
  deckHeight?: number | null;
}
export interface EntityStop {
  floorId: string;
  sourceFloorId: string;
  representationId?: string;
  locationId?: string;
  sourceFeatureIds?: Array<number | string>;
  partIndices?: number[];
  sourceZValues?: number[];
  position?: Point3;
  positionKind?: string;
}
export interface EntityData {
  entityId: string;
  type: string;
  name: string;
  representations: EntityRepresentation[];
  aliases?: string[];
  parentId?: string | null;
  primaryParent?: string;
  externalIds?: EntityExternalIds;
  function?: string;
  relations?: Array<{ type: string; targetId: string; evidence?: string }>;
  bounds?: Bounds3;
  sourceZ?: number | null;
  sourceZValues?: number[];
  sourceTypes?: string[];
  stops?: EntityStop[];
  sourceId?: string;
  status?: string;
  identityEvidence?: string;
  containmentEvidence?: string;
  identityStatus?: string;
  catalogElevation?: string;
  catalogElevationMeaning?: string;
  connectionScope?: string;
  isAggregate?: boolean;
  notes?: string[];
}
export interface EntityRegistryData {
  entities: EntityData[];
  legacyMap?: Record<string, string>;
}
export interface EntityResource {
  resourceId: string;
  type: string;
  name: string;
  asset: string;
  bindings: Array<{ entityId: string; [field: string]: unknown }>;
  source?: string;
  sourcePage?: string;
}

export interface InteriorRoom extends PolygonPart {
  id: string;
  sourceLocationId?: string | null;
  sourceFeatureId?: number | string;
  name: string;
  type: string;
  color: string;
  interactive?: boolean;
  hiddenFromMap?: boolean;
  heightSourceZ: number;
  center: PointXZ | null;
}
export interface FloorManifestEntry {
  id: string;
  buildingId: string;
  buildingName: string;
  floorName: string;
  url: string;
  z: number | null;
  sourceZValues: number[];
  isDefault: boolean;
  bounds: Bounds3;
  rooms: number;
  publicPolygonParts?: number;
  labeledFeatures?: number;
  namedFeatures?: number;
  backgroundFeatures?: number;
  cadSegments?: number;
  cadBytes?: number;
  bytes?: number;
  source?: string;
}
export interface FloorManifest {
  floors: FloorManifestEntry[];
}
export interface InteriorFloor {
  id: string;
  buildingId: string;
  buildingName: string;
  floorName: string;
  z: number | null;
  sourceZValues: number[];
  isDefault: boolean;
  bounds: Bounds3;
  rooms: InteriorRoom[];
  cad?: {
    url: string;
    format?: string;
    vertexCount?: number;
    segmentCount?: number;
    bytes?: number;
    referenceZ?: number;
  } | null;
  source?: string;
  catalogElevation?: string;
  cadPositions?: ArrayBuffer;
}
export interface CachedInteriorFloor extends InteriorFloor {
  cacheBytes: number;
}
export interface BuildingFootprint {
  id: string;
  catalogId: string | null;
  catalogName: string | null;
  officialBuildingId: string;
  officialBuildingName: string;
  parts: PolygonPart[];
  boundsXZ: BoundsXZ;
  computedAreaCentroidXZ?: PointXZ;
  sourceZ?: number | null;
  observedFloorZLevels?: number[];
  minObservedFloorZ?: number;
  maxObservedFloorZ?: number;
}
export interface BuildingFootprintManifest {
  footprints: BuildingFootprint[];
}

export interface TextureSource {
  url: string;
  width: number;
  height: number;
  bytes: number;
  decodedBytes: number;
  sha256?: string;
}
export interface TextureTile {
  id: string;
  center: Point3;
  bounds: Bounds3;
  materials: Record<string, TextureSource>;
}
export interface TextureManifest {
  tiles: TextureTile[];
}
export interface TextureRegion {
  id: string;
  buildingId: string;
  buildingName?: string;
  baselineIds: string[];
  textures: TextureSource[];
  textureDecodedBytes?: number;
  textureEncodedBytes?: number;
}
export interface TextureRegionManifest {
  regions: TextureRegion[];
}
export interface ExteriorMask {
  hasCoreMask?: boolean;
  coreChannel?: string;

  url: string;
  exactUrl?: string;
  boundsXZ: BoundsXZ;
  heightMin: number;
  heightMax?: number;
  width: number;
  height: number;
  metersPerPixel?: number;
  textureFlipY?: boolean;
  rowDirection?: string;
  channel?: string;
  occupiedValue?: number;
  emptyValue?: number;
}
export interface ExteriorObject {
  objectRole?: string;
  /**
   * `domain-only` keeps shared lower bodies/terraces unowned outside recorded
   * source domains. `aggregate-source` assigns a complete, officially named
   * joint envelope to its aggregate zone without inventing member boundaries.
   */
  ownership?: 'domain-only' | 'aggregate-source';
  id: string;
  url: string;
  offset?: Point3;
  matrix?: Matrix16;
  bounds: Bounds3;
  triangles: number;
  textureDecodedBytes: number;
  textureMaxDimension?: number;
  textureDimensions: Array<[number, number]>;
  textureFiles?: Array<{ url: string; width: number; height: number; decodedBytes: number }>;
}
export interface ExteriorBundle {
  id: string;
  /** Legacy source building ID. Omit for a verified non-building range entity. */
  buildingId?: string;
  /** Full existing registry ID; if both IDs exist they must identify the same entity. */
  entityId?: string;
  physicalDomainId?: string;
  buildingName: string;
  catalogIds: string[];
  objects: ExteriorObject[];
  mask: ExteriorMask;
  bounds: Bounds3;
  textureDecodedBytes: number;
}
export interface ExteriorManifest {
  bundles: ExteriorBundle[];
}

/** Rendering/resource identity remains bundle.id, independently of its owner. */
export function exteriorEntityId(bundle: Pick<ExteriorBundle, 'id' | 'entityId' | 'buildingId'>): string {
  const explicit = bundle.entityId;
  const legacy = bundle.buildingId;
  if (explicit !== undefined && (typeof explicit !== 'string' || !/^[a-z][a-z0-9_]*:\S+$/.test(explicit)))
    throw new Error(`Invalid exterior entityId: ${bundle.id}`);
  if (legacy !== undefined && (typeof legacy !== 'string' || !legacy || /\s/.test(legacy)))
    throw new Error(`Invalid exterior buildingId: ${bundle.id}`);
  if (explicit && legacy && explicit !== 'building:' + legacy)
    throw new Error(`Conflicting exterior entityId/buildingId: ${bundle.id}`);
  const entityId = explicit || (legacy ? 'building:' + legacy : undefined);
  if (!entityId) throw new Error(`Missing exterior owner: ${bundle.id}`);
  return entityId;
}

/** Only real building owners can participate in the existing floor source APIs. */
export function exteriorBuildingId(bundle: Pick<ExteriorBundle, 'id' | 'entityId' | 'buildingId'>): string | undefined {
  const owner = exteriorEntityId(bundle);
  return owner.startsWith('building:') ? owner.slice('building:'.length) : undefined;
}

export function validateExteriorIdentities(bundles: readonly ExteriorBundle[]): void {
  const ids = new Set<string>();
  const domains = new Set<string>();
  for (const bundle of bundles) {
    exteriorEntityId(bundle);
    if (!bundle.id || ids.has(bundle.id)) throw new Error(`Duplicate exterior bundle ID: ${bundle.id}`);
    ids.add(bundle.id);
    if (bundle.physicalDomainId !== undefined) {
      if (typeof bundle.physicalDomainId !== 'string' || !bundle.physicalDomainId || domains.has(bundle.physicalDomainId))
        throw new Error(`Duplicate or empty exterior physical domain: ${bundle.id}`);
      domains.add(bundle.physicalDomainId);
    }
  }
}

export function parseExteriorManifest(value: unknown): ExteriorManifest {
  if (!isRecord(value) || !Array.isArray(value.bundles) || !value.bundles.every(bundle =>
    isRecord(bundle) && typeof bundle.id === 'string' && typeof bundle.buildingName === 'string' &&
    Array.isArray(bundle.objects) && isRecord(bundle.mask) && isRecord(bundle.bounds)))
    throw new Error('Invalid exterior manifest');
  const bundles = value.bundles as ExteriorBundle[];
  validateExteriorIdentities(bundles);
  return { bundles };
}

export type MaterialShader = Parameters<THREE.Material["onBeforeCompile"]>[0];
export type RenderableObject = THREE.Object3D & { material: THREE.Material | THREE.Material[] };
/** Three sets this flag on Mesh subclasses, including objects returned by GLTFLoader. */
export function isMesh(
  object: THREE.Object3D,
): object is THREE.Mesh<THREE.BufferGeometry, THREE.Material | THREE.Material[]> {
  return "isMesh" in object && object.isMesh === true;
}
/** Material-bearing renderables include source meshes and CAD line objects. */
export function hasMaterial(object: THREE.Object3D): object is RenderableObject {
  return "material" in object && object.material !== undefined && object.material !== null;
}
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isRepresentation(value: unknown): value is EntityRepresentation {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.type === "string" &&
    typeof value.asset === "string"
  );
}
function isEntity(value: unknown): value is EntityData {
  return (
    isRecord(value) &&
    typeof value.entityId === "string" &&
    typeof value.type === "string" &&
    typeof value.name === "string" &&
    Array.isArray(value.representations) &&
    value.representations.every(isRepresentation) &&
    (value.externalIds === undefined || isRecord(value.externalIds))
  );
}
/** JSON is unknown at the boundary; reject a malformed registry before using its identifiers. */
export function parseEntityRegistry(value: unknown): EntityRegistryData {
  if (!isRecord(value) || !Array.isArray(value.entities) || !value.entities.every(isEntity))
    throw new Error("实体资料格式无效");
  if (
    value.legacyMap !== undefined &&
    (!isRecord(value.legacyMap) ||
      !Object.values(value.legacyMap).every((id) => typeof id === "string"))
  )
    throw new Error("实体旧标识映射格式无效");
  return value as unknown as EntityRegistryData;
}

/** Exact RGBA8 allocation of a complete mip chain, including non-power-of-two atlases. */
export function textureMipBytes(width:number,height:number):number{
 let w=width,h=height,bytes=0;
 while(w>=1&&h>=1){bytes+=w*h*4;if(w===1&&h===1)break;w=Math.max(1,Math.floor(w/2));h=Math.max(1,Math.floor(h/2))}
 return bytes;
}
