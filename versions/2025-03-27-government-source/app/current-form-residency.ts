import * as THREE from 'three';
import {visibleDetails, StableDetailOrder} from './detail-priority';
import {textureMipBytes, type Bounds3} from './source-types';
import type {CurrentFormSet, CurrentFormSetManifest} from './current-form-set';

/** Display policy, not source geography. Single-level current forms never
 * downgrade to the obsolete construction underneath their replacement mask. */
export const currentFormResidencyPolicy = {
  enterDistance: 1800, enterPixels: 24, guardBand: .2,
  minimumResidentMs: 8000, exitGraceMs: 2000,
  retryMs: [2000, 5000, 15000] as readonly number[],
};

export type CurrentFormDemand = {
  id: string;
  manifest: CurrentFormSetManifest;
  /** Full-set original texture mips + member masks + coverage/protection reserve. */
  fixedTextureBytes: number;
  load: (signal: AbortSignal) => Promise<CurrentFormSet>;
};
type Entry = CurrentFormDemand & {
  bounds: Bounds3;
  set?: CurrentFormSet;
  controller?: AbortController;
  wanted: boolean;
  active: boolean;
  lastSeen: number;
  committedAt: number;
  retryAt: number;
  failures: number;
  error: string;
};

/** Admission cost is checked against decoded Texture objects before commit.
 * Encoded GLB bytes are deliberately not used as a GPU texture estimate. */
export function currentFormFixedTextureBytes(input: unknown, manifest: CurrentFormSetManifest, protectionBytes = 0) {
  if (!input || typeof input !== 'object' || !('appearanceTextures' in input) || !Array.isArray(input.appearanceTextures))
    throw new Error('Current form manifest lacks original texture dimensions');
  let bytes = 0;
  for (const image of input.appearanceTextures) {
    if (!image || typeof image !== 'object' || !('dimensions' in image) || !Array.isArray(image.dimensions) ||
        image.dimensions.length !== 2 || !image.dimensions.every((n: unknown) => typeof n === 'number' && Number.isSafeInteger(n) && n > 0))
      throw new Error('Invalid current form original texture dimensions');
    bytes += textureMipBytes(image.dimensions[0], image.dimensions[1]);
  }
  const masks = new Map(manifest.members.flatMap(member => member.mask ? [[member.mask.url, member.mask] as const] : []));
  for (const mask of masks.values()) bytes += mask.width * mask.height * 4;
  // Account for the installed coverage and its atomic replacement allocation.
  // The current four-member masks share one checked grid; union bounds remain explicit.
  if (masks.size) {
    const values = [...masks.values()], pixel = Math.min(...values.map(mask => mask.pixelSizeMeters));
    const width = Math.ceil((Math.max(...values.map(mask => mask.boundsXZ.max[0])) - Math.min(...values.map(mask => mask.boundsXZ.min[0]))) / pixel);
    const height = Math.ceil((Math.max(...values.map(mask => mask.boundsXZ.max[1])) - Math.min(...values.map(mask => mask.boundsXZ.min[1]))) / pixel);
    bytes += 2 * width * height * 4;
  }
  if (!Number.isSafeInteger(protectionBytes) || protectionBytes < 0) throw new Error('Invalid current form protection cost');
  return bytes + protectionBytes;
}

/** Bounded fixed-asset residency, using the same off-axis projector as native
 * details. A cached set keeps its source masks and original textures. There is
 * one allocation per registered package, never one allocation per Hall root.
 * Budget reductions defer admission, rather than dismantling a valid current
 * building. A source-compatible lower level is required before safe eviction. */
export class CurrentFormResidency {
  private entries = new Map<string, Entry>();
  private order = new StableDetailOrder();
  private pending?: Entry;
  private dead = false;
  private openedBuildingId = '';
  private time = 0;
  private targetBudget = 0;
  private effectiveBudget = 0;
  private peakCharged = 0;
  constructor(private changed: () => void = () => {}) {}

  register(demand: CurrentFormDemand) {
    if (this.dead) throw new Error('Current form residency is disposed');
    if (this.entries.has(demand.id) || [...this.entries.values()].some(entry => entry.manifest.asset.sha256 === demand.manifest.asset.sha256))
      throw new Error('Duplicate current form package');
    if (!Number.isSafeInteger(demand.fixedTextureBytes) || demand.fixedTextureBytes < 0)
      throw new Error('Invalid current form fixed texture budget');
    const box = new THREE.Box3();
    for (const member of demand.manifest.members)
      box.union(new THREE.Box3(new THREE.Vector3(...member.bounds.min), new THREE.Vector3(...member.bounds.max)));
    this.entries.set(demand.id, {...demand, bounds: {min: box.min.toArray(), max: box.max.toArray()}, wanted: false, active: false,
      lastSeen: -Infinity, committedAt: -Infinity, retryAt: 0, failures: 0, error: ''});
  }

  catalogBytes() { return [...this.entries.values()].reduce((sum, entry) => sum + entry.fixedTextureBytes, 0); }
  memoryBytes() { return [...this.entries.values()].reduce((sum, entry) => sum + (entry.set || entry.controller ? entry.fixedTextureBytes : 0), 0); }
  setBudget(bytes: number) {
    this.targetBudget = Number.isFinite(bytes) ? Math.max(0, Math.floor(bytes)) : 0;
    this.effectiveBudget = Math.max(this.targetBudget, this.memoryBytes());
    if (this.pending && this.memoryBytes() > this.targetBudget) this.pending.controller?.abort();
    this.pump();
  }
  setOpened(buildingId: string) {
    this.openedBuildingId = buildingId;
    for (const entry of this.entries.values()) entry.set?.setActive(entry.active, buildingId);
  }

  /** Called before render even during an input gesture. Planning may wait for
   * the normal detail tick, but cached geometry must return in the same frame
   * as its still-installed source mask. This method never starts I/O. */
  refreshVisibility(camera: THREE.PerspectiveCamera, height: number, time: number, openedBuildingId = '') {
    if (this.dead) return;
    const held = [...this.entries.values()].filter(entry => entry.set);
    if (!held.length) return;
    const policy = currentFormResidencyPolicy;
    const visible = new Set(visibleDetails(camera, held, height, 0, {ids: new Set(held.map(entry => entry.id)), guardBand: policy.guardBand}).map(candidate => candidate.id));
    for (const entry of held) {
      const visibleNow = visible.has(entry.id) || entry.manifest.members.some(member => member.buildingId === openedBuildingId);
      if (visibleNow) entry.lastSeen = time;
      entry.wanted = visibleNow || time - entry.lastSeen < policy.exitGraceMs;
      const active = entry.wanted || time - entry.committedAt < policy.minimumResidentMs;
      if (!entry.active && active) entry.committedAt = time;
      entry.active = active;
      entry.set!.setActive(active, openedBuildingId);
    }
    this.openedBuildingId = openedBuildingId;
  }

  update(camera: THREE.PerspectiveCamera, height: number, time: number, openedBuildingId = '') {
    if (this.dead) return;
    this.time = time;
    const entries = [...this.entries.values()], policy = currentFormResidencyPolicy;
    const retained = new Set(entries.filter(entry => entry.wanted || entry.set || entry.controller).map(entry => entry.id));
    const projected = visibleDetails(camera, entries, height, 0, {ids: retained, guardBand: policy.guardBand});
    const visible = new Map(projected.map(candidate => [candidate.id, candidate]));
    this.order.rank(projected);
    for (const entry of entries) {
      const candidate = visible.get(entry.id);
      const opened = entry.manifest.members.some(member => member.buildingId === openedBuildingId);
      // Once committed, keep a current representation whenever it intersects
      // the retained frustum, even when too small/far for a new admission.
      const wanted = opened || !!candidate && (!!entry.set ||
        candidate.distance <= policy.enterDistance && candidate.pixels >= policy.enterPixels);
      if (wanted) entry.lastSeen = time;
      entry.wanted = wanted || (entry.wanted && time - entry.lastSeen < policy.exitGraceMs);
      if (entry.set) {
        const active = entry.wanted || time - entry.committedAt < policy.minimumResidentMs;
        if (!entry.active && active) entry.committedAt = time;
        entry.active = active;
        entry.set.setActive(entry.active, openedBuildingId);
      } else if (!entry.wanted) entry.controller?.abort();
    }
    this.setOpened(openedBuildingId);
    this.pump();
  }

  private pump() {
    if (this.dead || this.pending) return;
    this.effectiveBudget = Math.max(this.targetBudget, this.memoryBytes());
    const sorted = [...this.entries.values()].sort((a, b) => this.order.ids.indexOf(a.id) - this.order.ids.indexOf(b.id));
    for (const entry of sorted) {
      if (!entry.wanted || entry.set || entry.retryAt > this.time || this.memoryBytes() + entry.fixedTextureBytes > this.targetBudget) continue;
      const controller = new AbortController();
      this.pending = entry; entry.controller = controller;
      this.peakCharged = Math.max(this.peakCharged, this.memoryBytes());
      // The loader promise includes native decode drain. Do not clear a
      // cancelled reservation or start the next worker until finally runs.
      void Promise.resolve().then(() => entry.load(controller.signal)).then(set => {
        if (this.dead || controller.signal.aborted) { set.dispose(); return; }
        if ((set.state !== 'committed' && set.state !== 'inactive') || set.textureBytes() > entry.fixedTextureBytes) {
          set.dispose(); throw new Error('Current form transaction did not commit within its fixed reservation');
        }
        entry.set = set; entry.committedAt = this.time; entry.active = entry.wanted;
        entry.error = ''; entry.retryAt = 0;
        set.setActive(entry.active, this.openedBuildingId);
      }).catch((error: unknown) => {
        if (!controller.signal.aborted && !this.dead) {
          entry.failures++;
          entry.error = error instanceof Error ? error.message : String(error);
          entry.retryAt = this.time + currentFormResidencyPolicy.retryMs[Math.min(entry.failures - 1, 2)];
        }
      }).finally(() => {
        entry.controller = undefined; this.pending = undefined;
        this.effectiveBudget = Math.max(this.targetBudget, this.memoryBytes());
        if (!this.dead) { this.changed(); this.pump(); }
      });
      break;
    }
  }

  stats() {
    const entries = [...this.entries.values()];
    const held = entries.filter(entry => entry.set);
    return {
      scope: 'fixed-current-form-original-texture-mips-masks-and-coverage-reserve',
      targetBudgetBytes: this.targetBudget, effectiveBudgetBytes: this.effectiveBudget,
      chargedBytes: this.memoryBytes(), pendingBytes: this.pending?.fixedTextureBytes ?? 0,
      residentBytes: held.filter(entry => entry.active).reduce((sum, entry) => sum + entry.fixedTextureBytes, 0),
      cachedBytes: held.filter(entry => !entry.active).reduce((sum, entry) => sum + entry.fixedTextureBytes, 0),
      peakChargedBytes: this.peakCharged,
      packages: entries.map(entry => ({id: entry.id, buildingIds: entry.manifest.members.map(member => member.buildingId),
        state: entry.controller ? entry.controller.signal.aborted ? 'draining' : 'loading' : entry.set ? entry.active ? 'resident' : 'inactive-cache' : entry.wanted ? 'deferred' : 'unloaded',
        desired: entry.wanted, bytes: entry.fixedTextureBytes, failures: entry.failures, error: entry.error,
        deferredReason: !entry.wanted || entry.set || entry.controller ? '' : entry.retryAt > this.time ? 'retry-backoff' : 'fixed-texture-budget',
      })),
      excludes: 'dynamic detail pool, geometry, CPU ImageBitmaps, decode scratch and driver overhead',
    };
  }

  dispose() {
    if (this.dead) return;
    this.dead = true;
    for (const entry of this.entries.values()) { entry.controller?.abort(); entry.set?.dispose(); entry.set = undefined; }
  }
}
