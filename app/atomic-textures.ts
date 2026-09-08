import * as THREE from "three";
import { releaseTexture } from "./resources";
import {textureMipBytes} from "./source-types";
import type {
  TextureManifest,
  TextureRegion,
  TextureRegionManifest,
  TextureSource,
  TextureTile,
} from "./source-types";

type LoadedRegion = TextureRegion & {
  minX: number;
  minZ: number;
  maxX: number;
  maxZ: number;
};
type TextureBinding = {
  material: THREE.MeshBasicMaterial;
  low: THREE.Texture;
  source: TextureSource;
};
type CachedTexture = {
  texture: THREE.Texture;
  source: TextureSource;
  bytes: number;
  usedAt: number;
};
export type AtomicTextureOptions = {
  cacheBudgetBytes?: number;
  requestTimeoutMs?: number;
};

export class AtomicTextures {
  catalog = new Map<string, TextureTile>();
  regions: LoadedRegion[] = [];
  bindings: TextureBinding[] = [];
  /** The cache owns textures; current is the complete set attached to materials. */
  cache = new Map<string, CachedTexture>();
  current = new Map<string, THREE.Texture>();
  pending: AbortController | null = null;
  pendingKey = "";
  wanted = "";
  ready = "";
  dead = false;
  last = 0;
  cacheBytes = 0;
  reservedBytes = 0;
  loaded = 0;
  total = 0;
  failureCount = 0;
  retryAt = 0;
  error = "";
  private desired: TextureSource[] = [];
  private pendingSources = new Set<string>();
  cacheBudgetBytes: number;
  workers=2;
  readonly requestTimeoutMs: number;
  private readonly retryDelays = [2000, 5000, 15000];

  constructor(options: AtomicTextureOptions = {}) {
    // Exact RGBA8 mip allocation keeps shared original atlases within a fixed budget.
    this.cacheBudgetBytes = options.cacheBudgetBytes ?? 128 * 1048576;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 45000;
  }

  async init() {
    const [manifest, regions] = await Promise.all([
      fetch("/models/texture-detail-manifest.json").then(
        async (r) => (await r.json()) as TextureManifest,
      ),
      fetch("/models/exteriors/baseline-texture-regions.json").then(
        async (r) => (await r.json()) as TextureRegionManifest,
      ),
    ]);
    if (this.dead) return;
    this.catalog = new Map(manifest.tiles.map((t) => [t.id, t]));
    this.regions = regions.regions.map((r) => {
      const ts = r.baselineIds
        .map((id) => this.catalog.get(id))
        .filter((tile): tile is TextureTile => tile !== undefined);
      return {
        ...r,
        minX: Math.min(...ts.map((t) => t.bounds.min[0])),
        minZ: Math.min(...ts.map((t) => t.bounds.min[2])),
        maxX: Math.max(...ts.map((t) => t.bounds.max[0])),
        maxZ: Math.max(...ts.map((t) => t.bounds.max[2])),
      };
    });
  }

  register(tileId: string, material: THREE.MeshBasicMaterial, index: number) {
    if (this.dead) return;
    const source = this.catalog.get(tileId)?.materials[String(index)];
    if (source && material.map) {
      this.bindings.push({ material, low: material.map, source });
      const ready = this.current.get(source.url);
      if (ready) {
        material.map = ready;
        material.needsUpdate = true;
      }
    }
  }

  setBudget(bytes:number,workers=2) {
    this.cacheBudgetBytes=bytes;this.workers=Math.max(1,Math.min(2,workers));
    const evict=(keepCurrent:boolean)=>{for(const [url,item] of [...this.cache].sort((a,b)=>a[1].usedAt-b[1].usedAt)){
      if(this.cacheBytes+(keepCurrent?this.reservedBytes:0)<=bytes)break;
      if(keepCurrent&&this.current.has(url))continue;
      this.cache.delete(url);this.cacheBytes-=item.bytes;releaseTexture(item.texture);
    }};
    // A cache trim or a pending decode is not a reason to detach every visible
    // original atlas. Abort remains charged until native workers have drained.
    evict(true);
    if(this.cacheBytes+this.reservedBytes>bytes)this.pending?.abort();
    if(this.cacheBytes>bytes){this.ready='';this.commit(new Map());evict(false);}
  }

  /** Candidate selection can change independently; lifecycle and group commit stay here. */
  releaseInvisibleSources(visibleUrls: Set<string>) {
    const visible = new Map([...this.current].filter(([url]) => visibleUrls.has(url)));
    if (visible.size !== this.current.size) {
      this.commit(visible);
      this.ready = '';
    }
    for (const [url, cached] of this.cache) {
      if (visibleUrls.has(url)) continue;
      this.cache.delete(url);
      this.cacheBytes -= cached.bytes;
      releaseTexture(cached.texture);
    }
  }

  /** Candidate selection can change independently; lifecycle and group commit stay here. */
  request(key: string, images: TextureSource[]) {
    if (this.dead) return;
    if (key !== this.wanted) {
      this.wanted = key;
      this.desired = [...new Map(images.map((source) => [source.url, source])).values()];
      this.failureCount = 0;
      this.retryAt = 0;
      this.error = "";
      // Keep useful in-flight original images across a small group-set change.
      // Workers skip obsolete images; only disjoint views cancel the transaction.
      if(!this.desired.some(source=>this.pendingSources.has(source.url)))this.pending?.abort();
    }
    if (!key) {
      if (this.current.size || this.ready) this.commit(new Map());
      this.ready = "";
      this.loaded = this.total = 0;
      return;
    }
    if (this.ready === key) return;
    const complete = this.completeSet(this.desired);
    if (complete) {
      this.commit(complete);
      this.ready = key;
      this.loaded = this.total = this.desired.length;
      this.failureCount = 0;
      this.retryAt = 0;
      this.error = "";
      return;
    }
    if (this.pending || performance.now() < this.retryAt) return;
    void this.load(key, this.desired);
  }

  private completeSet(images: TextureSource[]) {
    const complete = new Map<string, THREE.Texture>();
    for (const source of images) {
      const cached = this.cache.get(source.url);
      if (!cached) return null;
      cached.usedAt = performance.now();
      complete.set(source.url, cached.texture);
    }
    return complete;
  }

  private reserve(bytes: number) {
    const desiredUrls=new Set(this.desired.map(source=>source.url));
    const evict=()=>{
      const protectedUrls=new Set([...this.current.keys(),...desiredUrls]);
      const unused=[...this.cache].filter(([url])=>!protectedUrls.has(url)).sort((a,b)=>a[1].usedAt-b[1].usedAt);
      for(const [url,item] of unused){
        if(this.cacheBytes+this.reservedBytes+bytes<=this.cacheBudgetBytes)break;
        this.cache.delete(url);this.cacheBytes-=item.bytes;releaseTexture(item.texture);
      }
    };
    evict();
    const required=this.desired.reduce((sum,source)=>sum+textureMipBytes(source.width,source.height),0);
    if(this.cacheBytes+this.reservedBytes+bytes>this.cacheBudgetBytes&&required<=this.cacheBudgetBytes&&this.current.size){
      // Two complete views may not fit together. Release the old complete view atomically,
      // then refill the new complete view; retaining it forever would starve a valid request.
      this.commit(new Map());this.ready='';evict();
    }
    if(this.cacheBytes+this.reservedBytes+bytes>this.cacheBudgetBytes)throw new Error('完整原纹理组超出缓存预算');
    this.reservedBytes+=bytes;
  }

  private async fetchTexture(source: TextureSource, signal: AbortSignal) {
    const response = await fetch(source.url, { signal });
    if (!response.ok) throw new Error("原纹理不可用");
    const blob = await response.blob();
    if (signal.aborted || this.dead) throw new DOMException("Cancelled", "AbortError");
    const bitmap = await createImageBitmap(blob, {
      imageOrientation: "none",
      premultiplyAlpha: "none",
    });
    if (signal.aborted || this.dead) {
      bitmap.close();
      throw new DOMException("Cancelled", "AbortError");
    }
    const texture = new THREE.Texture(bitmap);
    texture.flipY = false;
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.generateMipmaps = true;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.anisotropy = 8;
    texture.needsUpdate = true;
    return texture;
  }

  async load(key: string, images: TextureSource[]) {
    if (this.dead || this.pending || this.wanted !== key) return;
    const abort = new AbortController();
    this.pending = abort;
    this.pendingKey = key;
    this.error = "";
    this.total = images.length;
    const missing = images.filter((source) => !this.cache.has(source.url));
    this.pendingSources = new Set(missing.map(source=>source.url));
    this.loaded = images.length - missing.length;
    let cursor = 0;
    let failure: unknown;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      abort.abort();
    }, this.requestTimeoutMs);
    const worker = async () => {
      try {
        while (cursor < missing.length) {
          if (abort.signal.aborted || this.dead) throw new DOMException("Cancelled", "AbortError");
          const source = missing[cursor++];
          if(!this.desired.some(item=>item.url===source.url)){this.pendingSources.delete(source.url);continue;}
          const bytes = textureMipBytes(source.width,source.height);
          this.reserve(bytes);
          try {
            const texture = await this.fetchTexture(source, abort.signal);
            if (abort.signal.aborted || this.dead || !this.desired.some(item=>item.url===source.url)) {
              releaseTexture(texture);
              if(abort.signal.aborted||this.dead)throw new DOMException("Cancelled", "AbortError");
              continue;
            }
            this.cache.set(source.url, {
              texture,
              source,
              bytes,
              usedAt: performance.now(),
            });
            this.cacheBytes += bytes;
            this.loaded++;
          } finally {
            this.pendingSources.delete(source.url);
            this.reservedBytes -= bytes;
          }
        }
      } catch (error) {
        // Stop the sibling worker on the first HTTP/decode failure, but await its cleanup.
        if (!abort.signal.aborted) {
          failure = error;
          abort.abort();
        }
        throw error;
      }
    };
    try {
      const results = await Promise.allSettled(Array.from({length:this.workers},()=>worker()));
      if (this.dead || this.wanted !== key) return;
      if (results.some((result) => result.status === "rejected") || abort.signal.aborted) {
        if (failure !== undefined || timedOut) {
          this.failureCount++;
          this.retryAt =
            performance.now() +
            this.retryDelays[Math.min(this.failureCount - 1, this.retryDelays.length - 1)];
          this.error = timedOut ? "原纹理请求超时，将自动重试" : "原纹理暂未就绪，将自动重试";
        }
        return;
      }
      const complete = this.completeSet(images);
      if (!complete) throw new Error("整组原纹理尚未就绪");
      this.commit(complete);
      this.ready = key;
      this.failureCount = 0;
      this.retryAt = 0;
      this.error = "";
    } finally {
      clearTimeout(timeout);
      if (this.pending === abort) {
        this.pending = null;
        this.pendingKey = "";
        this.pendingSources.clear();
      }
      // Old workers have all settled. Start only the latest target, without waiting for a camera move.
      if (!this.dead) this.request(this.wanted, this.desired);
    }
  }

  commit(next: Map<string, THREE.Texture>) {
    for (const binding of this.bindings) {
      const map=next.get(binding.source.url)||binding.low;
      if(binding.material.map!==map){binding.material.map=map;binding.material.needsUpdate=true;}
    }
    const owned = new Set([...this.cache.values()].map((item) => item.texture));
    const retained = new Set(next.values());
    for (const texture of this.current.values())
      if (!owned.has(texture) && !retained.has(texture)) releaseTexture(texture);
    this.current = next;
  }

  stats() {
    return {
      wanted: this.wanted,
      ready: this.ready,
      loading: this.pendingKey,
      loaded: this.loaded,
      total: this.total,
      cacheImages: this.cache.size,
      cacheBytes: this.cacheBytes,
      reservedBytes: this.reservedBytes,
      cacheBudgetBytes: this.cacheBudgetBytes,
      retryInMs: Math.max(0, this.retryAt - performance.now()),
      failures: this.failureCount,
      error: this.error,
    };
  }

  dispose() {
    this.dead = true;
    this.pending?.abort();
    this.commit(new Map());
    for (const item of this.cache.values()) releaseTexture(item.texture);
    this.cache.clear();
    this.cacheBytes = 0;
    this.bindings = [];
    this.desired = [];
  }
}
