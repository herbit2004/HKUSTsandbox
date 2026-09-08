import type { QualityLevel } from './quality';

export const detailResourceLanes = ['exterior', 'mesh', 'original'] as const;
export type DetailResourceLane = typeof detailResourceLanes[number];
export type DetailResourceBytes = Record<DetailResourceLane, number>;
export type DetailResourceControls = Record<DetailResourceLane, {
  /** Includes cached resources and every pending reservation until native drain. */
  memoryBytes: () => number;
  setBudget: (bytes: number) => void;
}>;
export const sharedDetailCaps: Record<QualityLevel, number> = {
  ultra: 2048 * 1048576,
  high: 1536 * 1048576,
  balanced: 768 * 1048576,
  smooth: 208 * 1048576,
};
const empty = (): DetailResourceBytes => ({ exterior: 0, mesh: 0, original: 0 });
const bytes = (value: number) => Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
const sum = (values: DetailResourceBytes) => detailResourceLanes.reduce((n, lane) => n + values[lane], 0);

/** A shared reservation ledger, not a physical GPU/process-memory measurement.
 * Demand comes from whole-group plans at profile ceilings, independently of the
 * previous grants. A cancelled native decode keeps its full charge until drain.
 */
export class DetailResourcePool {
  grants = empty();
  demand = empty();
  targetCap: number;
  effectiveCap: number;
  private initialized = false;
  private peakActualBytes = 0;
  private peakChargedBytes = 0;
  private peakOverCapBytes = 0;

  constructor(cap: number) {
    this.targetCap = this.effectiveCap = bytes(cap);
  }

  private read(controls: DetailResourceControls): DetailResourceBytes {
    return Object.fromEntries(detailResourceLanes.map(lane => [lane, bytes(controls[lane].memoryBytes())])) as DetailResourceBytes;
  }

  reconcile(cap: number, demand: DetailResourceBytes, ceilings: DetailResourceBytes, controls: DetailResourceControls, refresh = false) {
    this.targetCap = bytes(cap);
    if (this.targetCap > this.effectiveCap) this.effectiveCap = this.targetCap;
    let remaining = this.targetCap;
    const target = empty();
    for (const lane of detailResourceLanes) {
      target[lane] = Math.min(bytes(demand[lane]), bytes(ceilings[lane]), remaining);
      remaining -= target[lane];
    }
    this.demand = { ...target };
    // Completed cache may borrow otherwise unused capacity, but cannot displace
    // any planned whole group or exceed its own profile ceiling.
    const initial = this.read(controls);
    for (const lane of detailResourceLanes) {
      const keep = Math.min(remaining, Math.max(0, Math.min(initial[lane], bytes(ceilings[lane])) - target[lane]));
      target[lane] += keep;
      remaining -= keep;
    }
    // Publish every reduction before granting any newly freed capacity. A
    // controller callback may report diagnostics synchronously in setBudget.
    for (const lane of detailResourceLanes) {
      if (refresh || !this.initialized || this.grants[lane] > target[lane]) {
        this.grants[lane] = Math.min(this.grants[lane], target[lane]);
        controls[lane].setBudget(this.grants[lane]);
      }
    }
    this.initialized = true;
    let actual = this.read(controls);
    const charged = () => detailResourceLanes.reduce((n, lane) => n + Math.max(actual[lane], this.grants[lane]), 0);
    // Lowering a setting cannot synchronously cancel an ImageBitmap decode.
    // Freeze increases until actual drain permits the new cap to take effect.
    if (this.targetCap < this.effectiveCap && charged() <= this.targetCap)
      this.effectiveCap = this.targetCap;
    if (this.targetCap === this.effectiveCap) {
      for (const lane of detailResourceLanes) {
        actual = this.read(controls);
        const credit = Math.max(0, this.effectiveCap - charged());
        const increase = Math.min(credit, target[lane] - this.grants[lane]);
        if (increase <= 0) continue;
        this.grants[lane] += increase;
        controls[lane].setBudget(this.grants[lane]);
      }
    }
    return this.stats(this.read(controls));
  }

  stats(actual: DetailResourceBytes) {
    const actualBytes = sum(actual);
    const chargedBytes = detailResourceLanes.reduce((n, lane) => n + Math.max(actual[lane], this.grants[lane]), 0);
    const overCapBytes = Math.max(0, chargedBytes - this.effectiveCap);
    this.peakActualBytes = Math.max(this.peakActualBytes, actualBytes);
    this.peakChargedBytes = Math.max(this.peakChargedBytes, chargedBytes);
    this.peakOverCapBytes = Math.max(this.peakOverCapBytes, overCapBytes);
    return {
      scope: 'dynamic-source-texture-mips-and-replacement-masks',
      targetCapBytes: this.targetCap,
      effectiveCapBytes: this.effectiveCap,
      reducing: this.targetCap < this.effectiveCap,
      grants: { ...this.grants },
      demand: { ...this.demand },
      actual: { ...actual },
      actualBytes,
      chargedBytes,
      waitingForDrain: detailResourceLanes.filter(lane => actual[lane] > this.grants[lane]),
      overCapBytes,
      peakActualBytes: this.peakActualBytes,
      peakChargedBytes: this.peakChargedBytes,
      peakOverCapBytes: this.peakOverCapBytes,
      excludes: 'baseline thumbnails, fixed current forms/surfaces/terrain, CPU ImageBitmaps, decode scratch, geometry and driver overhead',
    };
  }
}
