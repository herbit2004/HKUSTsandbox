import * as THREE from 'three';
import {GLTFLoader, type GLTF, type GLTFParser} from 'three/addons/loaders/GLTFLoader.js';
import {BundleLoadingManager, disposeResources, resources} from './coherent-exteriors';
import type {CurrentFormMask} from './current-form-coverage';
import {textureMipBytes} from './source-types';

type Bounds = {min: [number, number, number]; max: [number, number, number]};
export type CurrentFormSetMask = CurrentFormMask & {sha256?: string; bytes?: number};
export type CurrentFormSetMember = {
  entityId: string;
  buildingId: string;
  nodeName: string;
  bounds: Bounds;
  mask?: CurrentFormSetMask;
};
export type CurrentFormSetManifest = {
  version: 1;
  asset: {url: string; sha256: string; bytes: number};
  members: CurrentFormSetMember[];
};
export type ReadyCurrentFormMember = {
  descriptor: CurrentFormSetMember;
  root: THREE.Object3D;
  /** Set owns this texture and bitmap. Coverage may copy pixels or clone its wrapper. */
  mask?: THREE.Texture;
};
export type CurrentFormSetOptions = {
  baseURL: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  fetch?: typeof globalThis.fetch;
  createLoader?: (manager: THREE.LoadingManager) => Pick<GLTFLoader, 'register' | 'parseAsync'>;
  decodeBitmap?: (blob: Blob, options: ImageBitmapOptions) => Promise<ImageBitmap>;
};
export type CurrentFormCommitEffects = {
  /** Synchronous batch coverage installation; all member masks already decoded. */
  activate: (members: readonly ReadyCurrentFormMember[]) => void;
  /** Must undo even a partially throwing activate; also called on set disposal. */
  deactivate: () => void;
};

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f\d]{64}$/i.test(value);
const positiveInteger = (value: unknown): value is number => finite(value) && Number.isSafeInteger(value) && value > 0;
function tuple(value: unknown, size: number): value is number[] {
  return Array.isArray(value) && value.length === size && value.every(finite);
}
function bounds(value: unknown): value is Bounds {
  return record(value) && tuple(value.min, 3) && tuple(value.max, 3) && value.min.every((n, i) => n <= (value.max as number[])[i]);
}
function parseMask(value: unknown): CurrentFormSetMask {
  if (!record(value) || !text(value.url) || !record(value.boundsXZ) ||
      !tuple(value.boundsXZ.min, 2) || !tuple(value.boundsXZ.max, 2) ||
      !positiveInteger(value.width) || !positiveInteger(value.height) ||
      !finite(value.pixelSizeMeters) || value.pixelSizeMeters <= 0 ||
      !finite(value.replacementMinY) || !finite(value.replacementMaxY) ||
      value.replacementMaxY < value.replacementMinY || value.replacementMaxY >= 256 ||
      (value.sha256 !== undefined && !digest(value.sha256)) ||
      (value.bytes !== undefined && !positiveInteger(value.bytes)) ||
      (value.pixelMinYEncoding !== undefined && value.pixelMinYEncoding !== 'int-meters-alpha-255-common'))
    throw new Error('Invalid current form mask descriptor');
  const min = value.boundsXZ.min, max = value.boundsXZ.max;
  if (Math.abs(max[0]-min[0]-value.width*value.pixelSizeMeters) > 1e-6 ||
      Math.abs(max[1]-min[1]-value.height*value.pixelSizeMeters) > 1e-6)
    throw new Error('Current form mask grid does not match its bounds');
  return {
    url: value.url, boundsXZ: {min: [...min], max: [...max]},
    width: value.width, height: value.height, pixelSizeMeters: value.pixelSizeMeters,
    replacementMinY: value.replacementMinY, replacementMaxY: value.replacementMaxY,
    ...(value.sha256 === undefined ? {} : {sha256: value.sha256}),
    ...(value.bytes === undefined ? {} : {bytes: value.bytes}),
    ...(value.pixelMinYEncoding === undefined ? {} : {pixelMinYEncoding: value.pixelMinYEncoding}),
  };
}

/** Validate unknown JSON without mutating source IDs, names or descriptors. */
export function parseCurrentFormSetManifest(value: unknown): CurrentFormSetManifest {
  if (!record(value) || value.version !== 1 || !record(value.asset) ||
      !text(value.asset.url) || !digest(value.asset.sha256) || !positiveInteger(value.asset.bytes) ||
      !Array.isArray(value.members) || !value.members.length)
    throw new Error('Invalid current form set manifest');
  const members = value.members.map((member): CurrentFormSetMember => {
    if (!record(member) || !text(member.entityId) || !text(member.buildingId) || !text(member.nodeName) || !bounds(member.bounds))
      throw new Error('Invalid current form member identity or bounds');
    return {entityId: member.entityId, buildingId: member.buildingId, nodeName: member.nodeName,
      bounds: {min: [...member.bounds.min], max: [...member.bounds.max]},
      ...(member.mask === undefined ? {} : {mask: parseMask(member.mask)})};
  });
  for (const key of ['entityId', 'buildingId', 'nodeName'] as const)
    if (new Set(members.map(m => m[key])).size !== members.length)
      throw new Error(`Duplicate current form ${key}`);
  return {version: 1, asset: {url: value.asset.url, sha256: value.asset.sha256.toLowerCase(), bytes: value.asset.bytes}, members};
}

/** Reject unverified external dependencies before Three starts loading them. */
function validateSelfContainedGLB(bytes: ArrayBuffer) {
  const view = new DataView(bytes);
  if (bytes.byteLength < 20 || view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 ||
      view.getUint32(8, true) !== bytes.byteLength || view.getUint32(16, true) !== 0x4e4f534a)
    throw new Error('Current form asset is not a complete GLB v2');
  const length = view.getUint32(12, true);
  if (length > bytes.byteLength-20) throw new Error('Truncated current form GLB JSON');
  const json: unknown = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 20, length)));
  if (!record(json)) throw new Error('Invalid current form GLB JSON');
  for (const key of ['buffers', 'images']) {
    const entries = json[key];
    if (entries === undefined) continue;
    if (!Array.isArray(entries)) throw new Error('Invalid current form GLB dependencies');
    for (const entry of entries)
      if (!record(entry) || (entry.uri !== undefined && (typeof entry.uri !== 'string' || !entry.uri.startsWith('data:'))))
        throw new Error('Current form GLB must embed every buffer and image');
  }
}

async function verifyBytes(bytes: ArrayBuffer, expected: {sha256?: string; bytes?: number}, label: string) {
  if (expected.bytes !== undefined && bytes.byteLength !== expected.bytes)
    throw new Error(`${label} byte length differs from manifest`);
  if (expected.sha256) {
    const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== expected.sha256.toLowerCase()) throw new Error(`${label} SHA-256 differs from manifest`);
  }
}

/** One loaded set owns its shared resources for its entire lifetime. Complete
 * member roots commit in one synchronous turn directly under the scene parent,
 * preserving per-building hide/pick behavior without cloning shared resources. */
export class CurrentFormSet {
  private committed = false;
  private disposed = false;
  private active = true;
  private effects?: CurrentFormCommitEffects;
  constructor(readonly manifest: CurrentFormSetManifest, readonly root: THREE.Group, readonly members: readonly ReadyCurrentFormMember[]) {}

  get state(): 'ready' | 'committed' | 'inactive' | 'disposed' {
    return this.disposed ? 'disposed' : this.committed ? this.active ? 'committed' : 'inactive' : 'ready';
  }

  /** Inactive means a bounded, reusable complete-set cache. Keep coverage and
   * shared resources: obsolete source construction is not a lower LOD. */
  setActive(active: boolean, openedBuildingId = '') {
    if (this.disposed) return;
    this.active = active;
    for (const member of this.members)
      member.root.visible = active && member.descriptor.buildingId !== openedBuildingId;
  }

  /** Texture allocations, including decoded member masks, counted once per
   * actual shared Texture object. Does not claim to measure geometry/driver RAM. */
  textureBytes() {
    const owned = resources([this.root, ...this.members.map(member => member.root)]).texture;
    for (const member of this.members) if (member.mask) owned.add(member.mask);
    let bytes = 0;
    for (const texture of owned) {
      const image: unknown = texture.image;
      if (!record(image) || !positiveInteger(image.width) || !positiveInteger(image.height))
        throw new Error('Current form texture has no finite decoded dimensions');
      bytes += texture.generateMipmaps ? textureMipBytes(image.width, image.height) : image.width * image.height * 4;
    }
    return bytes;
  }

  commit(parent: THREE.Object3D, effects?: CurrentFormCommitEffects) {
    if (this.disposed) throw new Error('Cannot commit a disposed current form set');
    if (this.committed) {
      if (!this.members.every(member => member.root.parent === parent))
        throw new Error('Current form set already committed to another parent');
      return;
    }
    this.effects = effects;
    try {
      effects?.activate(this.members);
      parent.add(...this.members.map(member => member.root));
      this.committed = true;
    } catch (error) {
      this.dispose();
      throw error;
    }
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.root.removeFromParent();
    for (const member of this.members) member.root.removeFromParent();
    try { this.effects?.deactivate(); }
    finally {
      const owned = resources([this.root, ...this.members.map(member => member.root)]);
      for (const member of this.members) if (member.mask) owned.texture.add(member.mask);
      disposeResources(owned);
      this.root.clear();
      this.effects = undefined;
    }
  }
}

/** Fetch/parse/decode may abort, but the returned promise settles only after
 * outstanding decoder callbacks drain and their resources can be safely freed. */
export async function loadCurrentFormSet(input: unknown, options: CurrentFormSetOptions): Promise<CurrentFormSet> {
  const manifest = parseCurrentFormSetManifest(input);
  const controller = new AbortController(), manager = new BundleLoadingManager();
  const parsers = new Set<GLTFParser>(), bitmaps = new Set<ImageBitmap>(), masks = new Map<string, THREE.Texture>();
  const maskBytes = new Map<string, ArrayBuffer>();
  const fetchAsset = options.fetch ?? globalThis.fetch;
  const decodeBitmap = options.decodeBitmap ?? ((blob, config) => createImageBitmap(blob, config));
  const base = new URL(options.baseURL, typeof location === 'undefined' ? 'http://localhost/' : location.href);
  const url = (path: string) => new URL(path, base).href;
  const loader = (options.createLoader ?? (m => new GLTFLoader(m)))(manager);
  let gltf: GLTF | undefined;
  const check = () => {
    if (controller.signal.aborted) throw new DOMException('Current form set cancelled', 'AbortError');
    if (manager.failed) throw new Error('A current form GLB dependency failed');
  };
  const stop = () => {
    controller.abort();
    manager.stop();
    for (const parser of parsers) {
      parser.fileLoader.abort();
      if (parser.textureLoader instanceof THREE.ImageBitmapLoader) parser.textureLoader.abort();
    }
  };
  options.signal?.addEventListener('abort', stop, {once: true});
  if (options.signal?.aborted) stop();
  const timer = setTimeout(stop, options.timeoutMs ?? 120000);
  loader.register(parser => {
    parsers.add(parser);
    if (parser.textureLoader instanceof THREE.ImageBitmapLoader) {
      const imageLoader = parser.textureLoader, load = imageLoader.load.bind(imageLoader);
      imageLoader.load = (path, onLoad, progress, onError) => load(path, image => {
        bitmaps.add(image);
        onLoad?.(image);
      }, progress, onError);
    }
    return {name: 'CampusCurrentFormSetLifecycle'};
  });
  const bytesAt = async (path: string) => {
    check();
    const response = await fetchAsset(url(path), {signal: controller.signal});
    if (!response.ok) throw new Error(`Current form asset HTTP ${response.status}`);
    const bytes = await response.arrayBuffer();
    check();
    return bytes;
  };
  try {
    const bytes = await bytesAt(manifest.asset.url);
    await verifyBytes(bytes, manifest.asset, 'Current form GLB');
    check();
    validateSelfContainedGLB(bytes);
    const assetURL = url(manifest.asset.url);
    gltf = await loader.parseAsync(bytes, assetURL.slice(0, assetURL.lastIndexOf('/')+1));
    await manager.drained();
    check();
    if (gltf.scene.children.length !== manifest.members.length)
      throw new Error('Current form GLB roots differ from the complete member set');
    const roots = new Map(gltf.scene.children.map(root => [root.name, root]));
    if (roots.size !== manifest.members.length) throw new Error('Current form GLB has duplicate root names');
    gltf.scene.updateMatrixWorld(true);
    const members: ReadyCurrentFormMember[] = [];
    for (const descriptor of manifest.members) {
      const root = roots.get(descriptor.nodeName);
      if (!root || root.userData.entityId !== descriptor.entityId || root.userData.buildingId !== descriptor.buildingId)
        throw new Error('Current form root identity does not match its manifest');
      const actual = new THREE.Box3().setFromObject(root, true);
      if (actual.isEmpty() || ![...actual.min, ...actual.max].every(Number.isFinite) ||
          actual.min.toArray().some((n, i) => n < descriptor.bounds.min[i]-.02) ||
          actual.max.toArray().some((n, i) => n > descriptor.bounds.max[i]+.02))
        throw new Error('Current form root geometry lies outside its checked bounds');
      root.traverse(node => {
        if ((node.userData.entityId !== undefined && node.userData.entityId !== descriptor.entityId) ||
            (node.userData.buildingId !== undefined && node.userData.buildingId !== descriptor.buildingId))
          throw new Error('Current form descendant has a conflicting identity');
        node.userData.entityId = descriptor.entityId;
        node.userData.buildingId = descriptor.buildingId;
      });
      members.push({descriptor, root});
    }
    // Validate the entire identity/geometry set before decoding any masks.
    for (const member of members) {
      const descriptor = member.descriptor;
      let mask: THREE.Texture | undefined;
      if (descriptor.mask) {
        const m = descriptor.mask, key = url(m.url);
        mask = masks.get(key);
        if (!mask) {
          const data = await bytesAt(m.url);
          await verifyBytes(data, m, 'Current form mask');
          check();
          const bitmap = await decodeBitmap(new Blob([data]), {imageOrientation: 'none', premultiplyAlpha: 'none', colorSpaceConversion: 'none'});
          bitmaps.add(bitmap);
          check();
          if (bitmap.width !== m.width || bitmap.height !== m.height)
            throw new Error('Current form mask dimensions differ from its checked grid');
          mask = new THREE.Texture(bitmap);
          mask.colorSpace = THREE.NoColorSpace;
          mask.flipY = false;
          mask.generateMipmaps = false;
          mask.minFilter = THREE.NearestFilter;
          mask.magFilter = THREE.NearestFilter;
          mask.needsUpdate = true;
          masks.set(key, mask);
          maskBytes.set(key, data);
        } else {
          await verifyBytes(maskBytes.get(key)!, m, 'Shared current form mask');
          const image: unknown = mask.image;
          if (!record(image) || image.width !== m.width || image.height !== m.height)
            throw new Error('Shared current form mask descriptors disagree');
        }
      }
      member.mask = mask;
    }
    check();
    const keep = resources([gltf.scene]);
    for (const mask of masks.values()) keep.texture.add(mask);
    disposeResources(resources(gltf.scenes, parsers), keep, bitmaps);
    return new CurrentFormSet(manifest, gltf.scene, members);
  } catch (error) {
    stop();
    await manager.drained();
    const owned = resources(gltf?.scenes ?? [], parsers);
    for (const mask of masks.values()) owned.texture.add(mask);
    disposeResources(owned, undefined, bitmaps);
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', stop);
    parsers.clear();
    bitmaps.clear();
  }
}
