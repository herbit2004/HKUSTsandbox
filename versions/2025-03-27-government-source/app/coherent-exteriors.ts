import * as THREE from 'three';
import {
  GLTFLoader,
  type GLTFParser,
} from 'three/addons/loaders/GLTFLoader.js';
import { SpatialMasks, replacementSlots } from './spatial-masks';
import {
  isMesh,
  exteriorEntityId,
  parseExteriorManifest,
  textureMipBytes,
  type ExteriorBundle,
} from './source-types';

const MIB = 1048576;
const RETRY_DELAYS = [2000, 5000, 15000] as const;

/** Original image mip chains and the complete replacement mask, without resampling. */
export function exteriorBundleBytes(bundle: ExteriorBundle) {
  return bundle.objects.reduce(
    (sum, object) => sum + object.textureDimensions.reduce(
      (bytes, [width, height]) => bytes + textureMipBytes(width, height), 0,
    ), 0,
  ) + bundle.mask.width * bundle.mask.height * 4;
}

/** A single whole-group planner shared by normal and borrowed view budgets. */
export function planExteriorBundles(candidates: ExteriorBundle[], budgetBytes: number) {
  let bytes = 0;
  const bundles: ExteriorBundle[] = [];
  for (const bundle of new Map(candidates.map(b => [b.id, b])).values()) {
    if (bundles.length === replacementSlots.length) break;
    exteriorEntityId(bundle);
    const cost = exteriorBundleBytes(bundle);
    if (bytes + cost > budgetBytes) continue;
    bytes += cost;
    bundles.push(bundle);
  }
  return { bundles, bytes };
}

export interface ExteriorLifecycleOptions {
  /** Exact RGBA8 source mip chains plus mask base level; excludes CPU image backing and driver overhead. */
  budgetBytes: number;
  maxCachedGroups: number;
  requestTimeoutMs: number;
  bundleTimeoutMs: number;
  baseURL: string;
  retryDelaysMs: readonly number[];
}

type CompletedBundle = {
  bundle: ExteriorBundle;
  group: THREE.Group;
  /** Owned by this entry; SpatialMasks receives a disposable texture clone. */
  mask: THREE.Texture;
  bytes: number;
};
type VisibleBundle = CompletedBundle & { slot: string };
type RetryState = { attempts: number; nextAt: number };
type PendingBundle = {
  id: string;
  bundle: ExteriorBundle;
  abort: AbortController;
  manager: BundleLoadingManager;
  group: THREE.Group;
  mask: THREE.Texture | null;
  parsers: Set<GLTFParser>;
  bitmaps: Set<ImageBitmap>;
  bytes: number;
  done: Promise<void>;
  committed: boolean;
  timedOut: boolean;
};

export type ImageFailureContext = {
  lane: 'exterior' | 'mesh';
  groupId: string;
  sourceAsset: string;
  sourceObjectId?: string;
  aborted: boolean;
  stale: boolean;
  timedOut: boolean;
};
export type ImageFailureDiagnostic = {
  phase: 'image-fetch-or-decode';
  lane: ImageFailureContext['lane'] | 'unknown';
  groupId: string;
  sourceAsset: string;
  sourceObjectId: string;
  imageURL: string;
  error: { name: string; message: string };
  aborted: boolean;
  stale: boolean | null;
  timedOut: boolean;
  outcome: 'cancelled' | 'timeout' | 'failed-after-cancel' | 'failed';
};

/** Diagnostics expose asset paths, never URL credentials, query strings or data payloads. */
function diagnosticAssetPath(url: string) {
  if (url.startsWith('data:')) return 'data:[omitted]';
  if (url.startsWith('blob:')) return 'blob:' + url.slice(url.lastIndexOf('/') + 1).split(/[?#]/)[0].slice(0, 80);
  try {
    return new URL(url, 'https://campus.invalid/').pathname.slice(0, 384);
  } catch {
    return '[invalid asset URL]';
  }
}
function imageFailureError(error: unknown) {
  // DOMException and errors from other realms need not pass instanceof Error.
  const record = error !== null && typeof error === 'object' ? error : undefined;
  const name = record && 'name' in record && typeof record.name === 'string' ? record.name : 'UnknownError';
  const message = record && 'message' in record && typeof record.message === 'string'
    ? record.message : typeof error === 'string' ? error : String(error);
  return {
    name: name.slice(0, 80),
    message: message.replace(/(?:https?:\/\/|blob:|data:)[^\s)]+/g, diagnosticAssetPath).slice(0, 512),
  };
}

/** Tracks actual child fetch/decode completion, including rejected glTF parses. */
export class BundleLoadingManager extends THREE.LoadingManager {
  active = 0;
  failed = false;
  failureDetail = '';
  failureURL = '';
  /** A later view cancellation must not erase a failure that arrived while wanted. */
  failureBeforeCancellation = false;
  private waiters: Array<() => void> = [];
  constructor() {
    super();
    const start = this.itemStart.bind(this);
    const end = this.itemEnd.bind(this);
    this.itemStart = (url) => {
      this.active++;
      start(url);
    };
    this.itemEnd = (url) => {
      end(url);
      this.active--;
      if (this.active === 0) {
        for (const resolve of this.waiters.splice(0)) resolve();
      }
    };
    this.onError = (url) => {
      // GLTFLoader otherwise swallows failed texture loads and returns null maps.
      this.failed = true;
      this.failureURL ||= url;
    };
  }
  imageError(url: string, error: unknown, context?: ImageFailureContext): ImageFailureDiagnostic {
    const detail = imageFailureError(error);
    const aborted = context?.aborted ?? this.abortController.signal.aborted;
    const stale = context?.stale ?? null;
    const timedOut = context?.timedOut ?? false;
    const diagnostic: ImageFailureDiagnostic = {
      phase: 'image-fetch-or-decode',
      lane: context?.lane ?? 'unknown',
      groupId: (context?.groupId ?? '').slice(0, 160),
      sourceAsset: context?.sourceAsset ? diagnosticAssetPath(context.sourceAsset) : '',
      sourceObjectId: (context?.sourceObjectId ?? '').slice(0, 160),
      imageURL: diagnosticAssetPath(url),
      error: detail,
      aborted,
      stale,
      timedOut,
      outcome: timedOut ? 'timeout' : aborted ? detail.name === 'AbortError' ? 'cancelled' : 'failed-after-cancel' : 'failed',
    };
    const activeFailure = !aborted && stale !== true;
    this.failureBeforeCancellation ||= activeFailure;
    this.failed = true;
    // Sibling abort callbacks must not overwrite the original useful failure.
    if (!this.failureDetail || activeFailure) {
      this.failureURL = diagnostic.imageURL;
      this.failureDetail = detail.name + ': ' + detail.message;
    }
    // A single bounded JSON string survives browser log collectors that render
    // additional object arguments as just "Object". Three's warning is retained.
    console.warn('Campus image decode failed ' + JSON.stringify(diagnostic));
    return diagnostic;
  }
  stop() {
    this.abort();
    // Three renews its controller on abort. Keep the replacement aborted too:
    // parser dependencies scheduled after cancellation must not start fresh I/O.
    this.abortController.abort();
  }
  async drained() {
    if (this.active !== 0)
      await new Promise<void>((resolve) => this.waiters.push(resolve));
  }
}

type Resources = {
  geometry: Set<THREE.BufferGeometry>;
  material: Set<THREE.Material>;
  texture: Set<THREE.Texture>;
};
export function resources(
  objects: Iterable<THREE.Object3D>,
  parsers: Iterable<GLTFParser> = [],
) {
  const result: Resources = {
    geometry: new Set(),
    material: new Set(),
    texture: new Set(),
  };
  const material = (m: THREE.Material) => {
    result.material.add(m);
    for (const value of Object.values(m))
      if (value instanceof THREE.Texture) result.texture.add(value);
  };
  const object = (root: THREE.Object3D) => {
    root.traverse((o) => {
      if ('geometry' in o && o.geometry instanceof THREE.BufferGeometry)
        result.geometry.add(o.geometry);
      if (isMesh(o))
        for (const m of Array.isArray(o.material) ? o.material : [o.material])
          material(m);
    });
  };
  for (const root of objects) object(root);
  for (const parser of parsers)
    for (const owned of parser.associations.keys()) {
      if (owned instanceof THREE.Object3D) object(owned);
      else if (owned instanceof THREE.Material) material(owned);
      else if (owned instanceof THREE.Texture) result.texture.add(owned);
    }
  return result;
}
function images(texture: THREE.Texture): unknown[] {
  const image: unknown = texture.image;
  return Array.isArray(image) ? image : [image];
}
export function disposeResources(
  all: Resources,
  keep?: Resources,
  sourceBitmaps: Iterable<ImageBitmap> = [],
) {
  const retainedImages = new Set<unknown>();
  for (const texture of keep?.texture || [])
    for (const image of images(texture)) retainedImages.add(image);
  for (const geometry of all.geometry)
    if (!keep?.geometry.has(geometry)) geometry.dispose();
  for (const material of all.material)
    if (!keep?.material.has(material)) material.dispose();
  const closed = new Set<unknown>();
  for (const texture of all.texture) {
    if (keep?.texture.has(texture)) continue;
    texture.dispose();
    for (const image of images(texture)) {
      if (retainedImages.has(image) || closed.has(image)) continue;
      closed.add(image);
      if (
        image &&
        typeof image === 'object' &&
        'close' in image &&
        typeof image.close === 'function'
      )
        image.close();
    }
  }
  // A rejected parser can finish an image decode before its associations update.
  // Capture decoder results directly so these orphan bitmaps are also released.
  for (const bitmap of sourceBitmaps) {
    if (retainedImages.has(bitmap) || closed.has(bitmap)) continue;
    bitmap.close();
    closed.add(bitmap);
  }
}

export class CoherentExteriors {
  root = new THREE.Group();
  bundles: ExteriorBundle[] = [];
  current: VisibleBundle | null = null;
  visible = new Map<string, VisibleBundle>();
  pending: PendingBundle | null = null;
  /** Insertion order is LRU. The current entry is never also in this map. */
  cache = new Map<string, CompletedBundle>();
  wanted = '';
  dead = false;
  progress = 0;
  error = '';
  last = 0;
  readonly options: ExteriorLifecycleOptions;
  private desired: ExteriorBundle[] = [];
  private retries = new Map<string, RetryState>();
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private initAbort: AbortController | null = null;
  private cacheHits = 0;
  private cancelled = 0;
  private timeouts = 0;
  private failures = 0;
  private failureDetail = '';
  private failureKey = '';
  private lastImageFailure: ImageFailureDiagnostic | null = null;
  private budgetFallbacks = 0;

  constructor(
    public scene: THREE.Scene,
    public masks: SpatialMasks,
    public changed: () => void,
    options: Partial<ExteriorLifecycleOptions> = {},
  ) {
    this.options = {
      budgetBytes: 640 * MIB,
      maxCachedGroups: 3,
      requestTimeoutMs: 30000,
      bundleTimeoutMs: 180000,
      baseURL: '/models/exteriors/',
      retryDelaysMs: RETRY_DELAYS,
      ...options,
    };
    scene.add(this.root);
  }

  async init() {
    if (this.dead) return;
    this.initAbort?.abort();
    const abort = new AbortController();
    this.initAbort = abort;
    const timer = setTimeout(
      () => abort.abort(),
      this.options.requestTimeoutMs,
    );
    try {
      const response = await fetch(this.url('manifest.json'), {
        signal: abort.signal,
      });
      if (!response.ok)
        throw new Error(`Exterior manifest HTTP ${response.status}`);
      const data = parseExteriorManifest(await response.json());
      if (!abort.signal.aborted && !this.dead)
        this.bundles = data.bundles || [];
    } finally {
      clearTimeout(timer);
      if (this.initAbort === abort) this.initAbort = null;
    }
  }

  /** Candidates are already scored by the caller, highest priority first. */
  request(input: ExteriorBundle | ExteriorBundle[] | null) {
    if (this.dead) return;
    const candidates = input ? (Array.isArray(input) ? input : [input]) : [];
    for (const bundle of candidates) exteriorEntityId(bundle);
    // Shader capacity is independent of decoded-byte budget. Limit the already
    // ranked list before keeping pending/visible identities alive.
    const unique = new Map(
      [...new Map(candidates.map((bundle) => [bundle.id, bundle])).values()]
        .slice(0, replacementSlots.length)
        .map((bundle) => [bundle.id, bundle]),
    );
    const next = [...unique.values()];
    if (
      next.map((b) => b.id).join('|') !==
      this.desired.map((b) => b.id).join('|')
    ) {
      this.clearRetryTimer();
      this.error = '';
    }
    this.desired = next;
    this.wanted = next[0]?.id || '';
    // Re-ranking alone does not cancel a still-visible candidate's decode.
    if (this.pending && !unique.has(this.pending.id)) this.cancelPending();
    // When the reservation can hold the transition, keep completed outgoing
    // facades until their replacements are ready. Empty/off mode still releases
    // immediately; makeRoom performs whole-group eviction if double residency
    // cannot fit the real grant.
    if(!next.length||next.every(bundle=>this.visible.has(bundle.id)))
      for (const entry of this.visible.values())
        if (!unique.has(entry.bundle.id)) this.deactivate(entry);
    const previous = this.current;
    this.refreshPrimary();
    if (previous !== this.current) this.changed();
    this.pump();
  }

  maskFor(
    entityOrBuildingId: string,
    physicalDomainId?: string,
  ): { texture: THREE.Texture; bounds: number[] } | undefined {
    const entries = [...this.visible.values()].filter(
      (item) => (item.bundle.buildingId === entityOrBuildingId ||
        exteriorEntityId(item.bundle) === entityOrBuildingId) &&
        (!physicalDomainId || item.bundle.physicalDomainId === physicalDomainId),
    );
    // Multiple physical envelopes of one zone do not have one interchangeable mask.
    if (entries.length !== 1) return undefined;
    const entry = entries[0];
    const slot = this.masks.slots[entry.slot];
    return { texture: slot.texture.value, bounds: slot.bounds.value.toArray() };
  }

  private refreshPrimary() {
    this.current =
      this.desired
        .map((b) => this.visible.get(b.id))
        .find((entry) => entry !== undefined) || null;
  }

  distance(bundle: ExteriorBundle, point: THREE.Vector3) {
    const min = bundle.bounds.min,
      max = bundle.bounds.max;
    return Math.hypot(
      Math.max(min[0] - point.x, 0, point.x - max[0]),
      Math.max(min[2] - point.z, 0, point.z - max[2]),
    );
  }

  /** Kept for existing callers; automatic retries remain driven by request/timer. */
  async load(bundle: ExteriorBundle) {
    this.request(bundle);
    while (
      !this.dead &&
      this.desired.some((b) => b.id === bundle.id) &&
      this.pending
    )
      await this.pending.done;
  }

  private url(path: string) {
    return this.options.baseURL.replace(/\/?$/, '/') + path;
  }
  private entryBytes(bundle: ExteriorBundle) {
    return exteriorBundleBytes(bundle);
  }
  /** Whole-bundle demand, independent of a temporarily reduced runtime grant. */
  previewPlan(candidates: ExteriorBundle[], budgetBytes: number) {
    return planExteriorBundles(candidates, budgetBytes);
  }
  memoryBytes() {
    return this.residentBytes();
  }
  private cacheBytes() {
    let total = 0;
    for (const entry of this.cache.values()) total += entry.bytes;
    return total;
  }
  private residentBytes() {
    let visible = 0;
    for (const entry of this.visible.values()) visible += entry.bytes;
    return (
      visible +
      this.cacheBytes() +
      (this.pending?.committed ? 0 : this.pending?.bytes || 0)
    );
  }
  private destroy(entry: CompletedBundle) {
    const owned = resources([entry.group]);
    owned.texture.add(entry.mask);
    disposeResources(owned);
    entry.group.clear();
  }
  private evictOldest(except = '') {
    const first = [...this.cache.entries()].find(([id]) => id !== except);
    if (!first) return false;
    this.cache.delete(first[0]);
    this.destroy(first[1]);
    return true;
  }
  private trimCache(additionalBytes = 0, except = '') {
    while (
      this.cache.size &&
      (this.cache.size > this.options.maxCachedGroups ||
        this.residentBytes() + additionalBytes > this.options.budgetBytes)
    ) {
      if (!this.evictOldest(except)) break;
    }
  }
  private clearReplacement(name: string) {
    // Do not leave a disabled slot pointing at an ImageBitmap an LRU may close.
    const empty = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1);
    this.masks.set(name, empty, [0, 0, 1, 1]);
    this.masks.enable(name, false);
  }
  private deactivate(
    entry: VisibleBundle,
    cache = true,
    preserveCachedId = '',
  ) {
    this.root.remove(entry.group);
    this.visible.delete(entry.bundle.id);
    this.clearReplacement(entry.slot);
    if (cache) this.cache.set(entry.bundle.id, entry);
    else this.destroy(entry);
    this.refreshPrimary();
    this.trimCache(0, preserveCachedId);
    this.changed();
  }
  unload() {
    this.request(null);
  }

  setBudget(bytes:number,maxCachedGroups=3,plan:readonly ExteriorBundle[]=this.desired) {
    this.options.budgetBytes=bytes;this.options.maxCachedGroups=maxCachedGroups;
    this.trimCache();
    if(this.pending&&this.residentBytes()>bytes)this.cancelPending();
    const rank=(entry:VisibleBundle)=>{const at=plan.findIndex(bundle=>bundle.id===entry.bundle.id);return at<0?Infinity:at;};
    const lower=[...this.visible.values()].sort((a,b)=>rank(b)-rank(a));
    // A cancelled decode drains before pump can begin another transaction.
    while(lower.length&&this.residentBytes()-(this.pending?.bytes||0)>bytes)this.deactivate(lower.shift()!,false);
    // An explicit next plan is followed by request in the same scheduler turn.
    // Do not start an obsolete desired bundle during that budget handoff.
    if(plan===this.desired)this.pump();this.changed();
  }

  private commit(entry: CompletedBundle, tx?: PendingBundle) {
    // Decoding does not need a shader slot. Exchange a retired slot only once
    // the incoming whole model and mask are ready, avoiding a needless gap.
    if(this.visible.size>=replacementSlots.length){
      const outgoing=[...this.visible.values()].find(item=>!this.desired.some(bundle=>bundle.id===item.bundle.id));
      if(outgoing)this.deactivate(outgoing,true,entry.bundle.id);
    }
    const used = new Set([...this.visible.values()].map((item) => item.slot));
    const slot = replacementSlots.find((name) => !used.has(name));
    if (!slot) throw new Error('No reserved exterior replacement slot');
    for(const child of entry.group.children)this.masks.apply(child,child.userData.sourceRole==='source-photogrammetry-gap-surface'?'supplement':'exterior');
    const b = entry.bundle.mask.boundsXZ;
    // SpatialMasks owns/disposes the wrapper; the entry owns its shared bitmap.
    this.masks.set(
      slot,
      entry.mask.clone(),
      [b.min[0], b.min[1], b.max[0], b.max[1]],
      entry.bundle.mask.heightMin - 0.15,
    );
    this.masks.setPhotogrammetryCore(slot,!!entry.bundle.mask.hasCoreMask);
    this.cache.delete(entry.bundle.id);
    if (tx) tx.committed = true;
    this.root.add(entry.group);
    this.visible.set(entry.bundle.id, { ...entry, slot });
    if(this.desired.every(bundle=>this.visible.has(bundle.id)))
      for(const item of this.visible.values())if(!this.desired.some(bundle=>bundle.id===item.bundle.id))this.deactivate(item);
    this.refreshPrimary();
    this.progress = entry.bundle.objects.length;
    this.error = '';
    this.retries.delete(entry.bundle.id);
    this.trimCache();
    // updateOpening may retrieve any visible building's matching independent mask.
    this.changed();
  }

  /** Never evict a higher-priority visible group to admit a lower-priority one. */
  private makeRoom(bundle: ExteriorBundle) {
    const rank = this.desired.findIndex((b) => b.id === bundle.id);
    const higher = [...this.visible.values()].filter(
      (entry) => {const at=this.desired.findIndex((b) => b.id === entry.bundle.id);return at>=0&&at<rank;},
    );
    const bytes = this.entryBytes(bundle);
    if (
      bytes + higher.reduce((sum, entry) => sum + entry.bytes, 0) >
        this.options.budgetBytes ||
      higher.length >= replacementSlots.length
    )
      return false;
    const added = this.cache.has(bundle.id) ? 0 : bytes;
    this.trimCache(added, bundle.id);
    const lower = [...this.visible.values()]
      .filter((entry) => !higher.includes(entry))
      .sort((a,b)=>{
        const position=(entry:VisibleBundle)=>{const at=this.desired.findIndex(bundle=>bundle.id===entry.bundle.id);return at<0?Infinity:at;};
        return position(b)-position(a);
      });
    while (
      this.residentBytes() + added > this.options.budgetBytes &&
      lower.length
    ) {
      const entry = lower.shift()!;
      this.budgetFallbacks++;
      // Each entire low-priority group returns to the intact baseline at once.
      this.deactivate(entry, true, bundle.id);
      this.trimCache(added, bundle.id);
    }
    return (
      this.residentBytes() + added <= this.options.budgetBytes &&
      (this.visible.size < replacementSlots.length||[...this.visible.values()].some(entry=>!this.desired.some(bundle=>bundle.id===entry.bundle.id)))
    );
  }

  private clearRetryTimer() {
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }
  private pump() {
    if (this.dead || this.pending) return;
    this.clearRetryTimer();
    let wait = Infinity;
    for (const bundle of this.desired) {
      if (this.visible.has(bundle.id)) continue;
      const retry = this.retries.get(bundle.id);
      const delay = retry ? retry.nextAt - performance.now() : 0;
      if (delay > 0) {
        wait = Math.min(wait, delay);
        continue;
      }
      if (!this.makeRoom(bundle)) continue;
      const cached = this.cache.get(bundle.id);
      if (cached) {
        this.cacheHits++;
        this.commit(cached);
        continue;
      }
      this.start(bundle);
      return;
    }
    if (Number.isFinite(wait))
      this.retryTimer = setTimeout(() => {
        this.retryTimer = null;
        this.pump();
      }, wait);
  }

  private start(bundle: ExteriorBundle) {
    const bytes = this.entryBytes(bundle);
    const tx: PendingBundle = {
      id: bundle.id,
      bundle,
      abort: new AbortController(),
      manager: new BundleLoadingManager(),
      group: new THREE.Group(),
      mask: null,
      parsers: new Set(),
      bitmaps: new Set(),
      bytes,
      done: Promise.resolve(),
      committed: false,
      timedOut: false,
    };
    this.pending = tx;
    this.progress = 0;
    this.error = '';
    // Publish the pending identity before any user callback can re-enter request.
    tx.done = Promise.resolve().then(() => this.run(tx));
    this.changed();
  }

  private cancelPending() {
    const tx = this.pending;
    if (!tx || tx.abort.signal.aborted) return;
    this.cancelled++;
    tx.abort.abort();
    // Keep pending until its finally has drained native image decodes and freed
    // partial resources; a second group cannot reserve or decode concurrently.
  }
  private check(tx: PendingBundle) {
    if (
      tx.abort.signal.aborted ||
      this.dead ||
      !this.desired.some((b) => b.id === tx.id)
    )
      throw new DOMException('Exterior request cancelled', 'AbortError');
    if (tx.manager.failed) throw new Error('An exterior dependency failed');
  }
  private timeout(tx: PendingBundle) {
    if (tx.abort.signal.aborted) return;
    tx.timedOut = true;
    this.timeouts++;
    tx.abort.abort();
  }
  private async operation<T>(tx: PendingBundle, task: () => Promise<T>) {
    this.check(tx);
    const timer = setTimeout(
      () => this.timeout(tx),
      this.options.requestTimeoutMs,
    );
    try {
      return await task();
    } finally {
      clearTimeout(timer);
    }
  }

  private async run(tx: PendingBundle) {
    const stop = () => {
      tx.manager.stop();
      for (const parser of tx.parsers) {
        parser.fileLoader.abort();
        if (parser.textureLoader instanceof THREE.ImageBitmapLoader)
          parser.textureLoader.abort();
      }
    };
    tx.abort.signal.addEventListener('abort', stop, { once: true });
    const deadline = setTimeout(
      () => this.timeout(tx),
      this.options.bundleTimeoutMs,
    );
    try {
      this.check(tx);
      let sourceObject = tx.bundle.objects[0];
      const loader = new GLTFLoader(tx.manager);
      loader.register((parser) => {
        const object = sourceObject;
        tx.parsers.add(parser);
        if (parser.textureLoader instanceof THREE.ImageBitmapLoader) {
          const imageLoader = parser.textureLoader;
          const loadImage = imageLoader.load.bind(imageLoader);
          imageLoader.load = (url, onLoad, onProgress, onError) =>
            loadImage(url, (bitmap) => {
              tx.bitmaps.add(bitmap);
              onLoad?.(bitmap);
            }, onProgress, (error) => {
              this.lastImageFailure = tx.manager.imageError(url, error, {
                lane: 'exterior', groupId: tx.id,
                sourceAsset: this.url(object.url), sourceObjectId: object.id,
                aborted: tx.abort.signal.aborted,
                stale: this.dead || !this.desired.some((b) => b.id === tx.id),
                timedOut: tx.timedOut,
              });
              onError?.(error);
            });
        }
        return { name: 'CampusExteriorLifecycle' };
      });
      for (const object of tx.bundle.objects) {
        sourceObject = object;
        const gltf = await this.operation(tx, async () => {
          const url = this.url(object.url);
          // Top-level GLB fetch is explicitly abortable, independently of Three's
          // global FileLoader URL de-duplication and browser AbortSignal.any support.
          const response = await fetch(url, { signal: tx.abort.signal });
          if (!response.ok)
            throw new Error(`Exterior object HTTP ${response.status}`);
          const data = await response.arrayBuffer();
          this.check(tx);
          return loader.parseAsync(
            data,
            url.slice(0, url.lastIndexOf('/') + 1),
          );
        });
        const positioned = new THREE.Group();
        positioned.userData.sourceObjectId=object.id;
        positioned.userData.sourceRole=object.objectRole;
        positioned.userData.sourceOwnership=object.ownership;
        if (object.offset) positioned.position.fromArray(object.offset);
        if (object.matrix)
          positioned.applyMatrix4(new THREE.Matrix4().fromArray(object.matrix));
        positioned.add(gltf.scene);
        tx.group.add(positioned);
        this.check(tx);
        gltf.scene.traverse((o) => {
          if (!isMesh(o)) return;
          const isArray = Array.isArray(o.material);
          const material = (
            Array.isArray(o.material) ? o.material : [o.material]
          ).map((m) => {
            const map =
              'map' in m && m.map instanceof THREE.Texture ? m.map : null;
            const color =
              'color' in m && m.color instanceof THREE.Color
                ? m.color
                : undefined;
            if (map) {
              map.generateMipmaps = true;
              map.minFilter = THREE.LinearMipmapLinearFilter;
              map.magFilter = THREE.LinearFilter;
              map.anisotropy = 8;
            }
            const next = new THREE.MeshBasicMaterial({
              map,
              color,
              vertexColors: !!o.geometry.attributes.color,
              side: THREE.DoubleSide,
            });
            m.dispose();
            return next;
          });
          o.material = isArray ? material : material[0];
        });
        this.progress++;
        this.changed();
      }
      tx.mask = await this.operation(tx, async () => {
        const response = await fetch(this.url(tx.bundle.mask.url), {
          signal: tx.abort.signal,
        });
        if (!response.ok)
          throw new Error(`Exterior mask HTTP ${response.status}`);
        const bitmap = await createImageBitmap(await response.blob(), {
          imageOrientation: 'none',
          premultiplyAlpha: 'none',
          colorSpaceConversion: 'none',
        });
        if (
          tx.abort.signal.aborted ||
          this.dead ||
          !this.desired.some((b) => b.id === tx.id)
        ) {
          bitmap.close();
          throw new DOMException('Exterior mask cancelled', 'AbortError');
        }
        if (
          bitmap.width !== tx.bundle.mask.width ||
          bitmap.height !== tx.bundle.mask.height
        ) {
          bitmap.close();
          throw new Error(
            'Exterior mask dimensions do not match its reserved source metadata',
          );
        }
        const texture = new THREE.Texture(bitmap);
        texture.colorSpace = THREE.NoColorSpace;
        texture.flipY = false;
        texture.needsUpdate = true;
        return texture;
      });
      await tx.manager.drained();
      this.check(tx);
      const keep = resources([tx.group]);
      keep.texture.add(tx.mask);
      disposeResources(resources([], tx.parsers), keep, tx.bitmaps);
      this.commit(
        { bundle: tx.bundle, group: tx.group, mask: tx.mask, bytes: tx.bytes },
        tx,
      );
    } catch (error) {
      const cancelled = tx.abort.signal.aborted && !tx.timedOut && !tx.manager.failureBeforeCancellation;
      // Error paths also stop sibling texture requests before awaiting their cleanup.
      if (!tx.abort.signal.aborted) tx.abort.abort();
      if (!cancelled && !this.dead) {
        this.failures++;
        this.failureDetail = (error instanceof Error ? error.name + ': ' + error.message : String(error)) + (tx.manager.failureDetail ? ' | '+tx.manager.failureDetail : '');
        this.failureKey = tx.id+' @ '+this.progress+'/'+tx.bundle.objects.length+' '+tx.manager.failureURL;
        const attempts = (this.retries.get(tx.id)?.attempts || 0) + 1;
        const delays = this.options.retryDelaysMs.length
          ? this.options.retryDelaysMs
          : RETRY_DELAYS;
        const delay = delays[Math.min(attempts - 1, delays.length - 1)];
        this.retries.set(tx.id, {
          attempts,
          nextAt: performance.now() + delay,
        });
        if (this.desired.some((b) => b.id === tx.id))
          this.error = '建筑原始细节暂未载入，保留完整外观并稍后重试';
      }
    } finally {
      clearTimeout(deadline);
      await tx.manager.drained();
      tx.abort.signal.removeEventListener('abort', stop);
      if (!tx.committed) {
        const owned = resources([tx.group], tx.parsers);
        if (tx.mask) owned.texture.add(tx.mask);
        disposeResources(owned, undefined, tx.bitmaps);
        tx.group.clear();
      }
      tx.parsers.clear();
      tx.bitmaps.clear();
      if (this.pending === tx) this.pending = null;
      this.trimCache();
      if (!this.dead) {
        this.changed();
        this.pump();
      }
    }
  }

  stats() {
    const retry = this.retries.get(this.wanted);
    return {
      building: this.current?.bundle.buildingName || '',
      loading: this.pending?.id || '',
      loaded: this.progress,
      total: this.pending?.bundle.objects.length,
      textureMiB: this.current
        ? Math.round(this.current.bytes / MIB)
        : 0,
      error: this.error,
      visibleCount: this.visible.size,
      visibleBuildings: [...this.visible.values()].map(
        (entry) => entry.bundle.buildingName,
      ),
      visibleIds: [...this.visible.keys()],
      visibleTextureMiB: +(
        [...this.visible.values()].reduce(
          (sum, entry) => sum + entry.bytes,
          0,
        ) / MIB
      ).toFixed(1),
      cacheGroups: this.cache.size,
      cacheTextureMiB: +(this.cacheBytes() / MIB).toFixed(1),
      pendingTextureMiB: +(
        (this.pending?.committed ? 0 : this.pending?.bytes || 0) / MIB
      ).toFixed(1),
      residentTextureMiB: +(this.residentBytes() / MIB).toFixed(1),
      budgetTextureMiB: this.options.budgetBytes / MIB,
      cancelling: this.pending?.abort.signal.aborted || false,
      retryCount: retry?.attempts || 0,
      retryInSeconds: Math.max(
        0,
        Math.ceil(((retry?.nextAt || 0) - performance.now()) / 1000),
      ),
      cacheHits: this.cacheHits,
      cancelled: this.cancelled,
      timeouts: this.timeouts,
      failures: this.failures,
      failureDetail: this.failureDetail,
      failureKey: this.failureKey,
      ...(this.lastImageFailure ? { lastImageFailure: this.lastImageFailure } : {}),
      budgetFallbacks: this.budgetFallbacks,
    };
  }

  dispose() {
    if (this.dead) return;
    this.dead = true;
    this.wanted = '';
    this.desired = [];
    this.clearRetryTimer();
    this.initAbort?.abort();
    this.cancelPending();
    for (const entry of this.visible.values()) this.deactivate(entry, false);
    while (this.evictOldest()) {
      /* Release every completed owned group and bitmap. */
    }
    this.retries.clear();
    this.scene.remove(this.root);
  }
}
