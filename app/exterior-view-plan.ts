import { planExteriorBundles } from './coherent-exteriors';
import type { VisibleDetail } from './detail-priority';
import { replacementSlots } from './spatial-masks';
import type { ExteriorBundle } from './source-types';

/** Render policy, not geographic identity evidence: natural close views may
 * borrow from lower-priority mesh/original lanes for complete neighbouring
 * exteriors. A small exit margin avoids repeated cancellation around 300 m.
 */
export const exteriorNearRange = { enterMeters: 300, exitMeters: 330 } as const;
const wholeBytes = (value: number) => Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;

export class ExteriorViewPlanner {
  private near = new Set<string>();

  plan(
    candidates: ExteriorBundle[],
    visible: VisibleDetail[],
    baseBudgetBytes: number,
    sharedCapBytes: number,
  ) {
    const cap = wholeBytes(sharedCapBytes), base = Math.min(cap, wholeBytes(baseBudgetBytes));
    const ranked = [...new Map(candidates.map(bundle => [bundle.id, bundle])).values()];
    const screen = new Map(visible.map(candidate => [candidate.id, candidate]));
    const nextNear = new Set<string>();
    for (const bundle of ranked.slice(0, replacementSlots.length)) {
      const candidate = screen.get(bundle.id);
      if (!candidate || !Number.isFinite(candidate.distance) || candidate.distance < 0) continue;
      const limit = this.near.has(bundle.id) ? exteriorNearRange.exitMeters : exteriorNearRange.enterMeters;
      if (candidate.distance <= limit) nextNear.add(bundle.id);
    }
    this.near = nextNear;
    const ordinary = planExteriorBundles(ranked, base);
    const ordinaryIds = new Set(ordinary.bundles.map(bundle => bundle.id));
    // Do not let a distant group rejected at the base ceiling spend the credit
    // intended for a close neighbour. Recompute from source demand, never from
    // a previous grant or a clicked entity, so credit cannot accumulate.
    const eligible = ranked.filter(bundle => ordinaryIds.has(bundle.id) || nextNear.has(bundle.id));
    const plan = planExteriorBundles(eligible, cap);
    const budgetBytes = Math.max(base, plan.bytes);
    return {
      ...plan,
      budgetBytes,
      borrowedBytes: Math.max(0, budgetBytes - base),
      nearIds: [...nextNear],
    };
  }
}
