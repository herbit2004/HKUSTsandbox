import * as THREE from 'three';
import {
  GLTFLoader,
  type GLTFParser,
} from 'three/addons/loaders/GLTFLoader.js';
import {
  BundleLoadingManager,
  resources,
  disposeResources,
  type ImageFailureDiagnostic,
} from './coherent-exteriors';
import { SpatialMasks, partialSlots } from './spatial-masks';
import { visibleDetails, StableDetailOrder, type VisibleDetail } from './detail-priority';
import {
  isMesh,
  textureMipBytes,
  type Bounds3,
  type Matrix16,
} from './source-types';
import type { QualityProfile } from './quality';
type Tile = {
  url: string;
  matrix: Matrix16;
  textureDimensions: number[][];
  triangles: number;
  originalError?: number;
  geometricError?: number;
};
type Level = { tiles: Tile[]; triangles: number; mask?: PartialMask; geometricErrorMax?: number };
type PartialMask = {
  url: string;
  minX: number;
  minZ: number;
  maxX: number;
  maxZ: number;
  width: number;
  height: number;
};
type Patch = {
  id: string;
  bounds: Bounds3;
  baselineIds: string[];
  levels: { high: Level; fine?: Level };
  mask?: PartialMask;
};
export type NativeDetailChoice = { key: string; patch: Patch; level: Level; bytes: number; projectedErrorPixels?: number; qualityReason?: string; near?: boolean; expandedRange?: boolean };
type Choice = NativeDetailChoice;
const choiceMask=(choice:Choice)=>choice.level.mask??choice.patch.mask;

function nativeLevelBytes(level:Level,mask?:PartialMask){
  return level.tiles.reduce((total,tile)=>total+tile.textureDimensions.reduce((sum,[w,h])=>sum+textureMipBytes(w,h),0),mask?mask.width*mask.height*4:0);
}

/** The one R8 union actually used by SpatialMasks. The
 * original square grids must align at the finest spacing; oversized or too
 * numerous masks are rejected before I/O, never silently downsampled.
 */
function nativeUnionBytes(choices:Choice[]):number {
  const masks=choices.flatMap(choice=>choiceMask(choice)?[choiceMask(choice)!]:[]);
  if(!masks.length)return 1;
  if(masks.length>partialSlots.length)return Infinity;
  if(masks.some(mask=>![mask.minX,mask.minZ,mask.maxX,mask.maxZ].every(Number.isFinite)||!Number.isInteger(mask.width)||!Number.isInteger(mask.height)||mask.width<1||mask.height<1))return Infinity;
  const steps=masks.map(mask=>(mask.maxX-mask.minX)/mask.width);
  if(masks.some((mask,index)=>!Number.isFinite(steps[index])||steps[index]<=0||Math.abs(steps[index]-(mask.maxZ-mask.minZ)/mask.height)>1e-6))return Infinity;
  const step=Math.min(...steps),minX=Math.min(...masks.map(mask=>mask.minX)),minZ=Math.min(...masks.map(mask=>mask.minZ));
  const maxX=Math.max(...masks.map(mask=>mask.maxX)),maxZ=Math.max(...masks.map(mask=>mask.maxZ));
  const width=Math.round((maxX-minX)/step),height=Math.round((maxZ-minZ)/step);
  if(width>4096||height>4096||width*height>16*1024*1024)return Infinity;
  if(masks.some((mask,index)=>[(mask.minX-minX)/step,(mask.minZ-minZ)/step,steps[index]/step].some(value=>Math.abs(value-Math.round(value))>1e-6)))return Infinity;
  return width*height;
}

export function nativePlanBytes(choices:Choice[],currentUnionBytes=0):number {
  if(!choices.length)return 1;
  const union=nativeUnionBytes(choices);
  // Rebuilding a union allocates the new R8 array/texture before disposing the
  // old wrapper. Reserve both generations rather than relying on immediate GC.
  return choices.reduce((total,choice)=>total+choice.bytes,0)+union+Math.max(union,currentUnionBytes);
}

/** Auto/high can request a complete terminal frontier at normal close range.
 * Source geometric error is projected using the same camera and canvas height
 * as selection. Two thresholds retain a chosen level around the transition.
 */
export function nativeDetailChoice(
  patch:Patch,candidate:VisibleDetail,camera:THREE.PerspectiveCamera,
  height:number,profile:QualityProfile,budgetBytes:number,previousFine=false,previousNear=false,
):Choice{
  const high=patch.levels.high;
  const residual=high.geometricErrorMax??Math.max(0,...high.tiles.map(tile=>tile.originalError??tile.geometricError??0));
  const projectedErrorPixels=residual*height/(2*Math.tan(THREE.MathUtils.degToRad(camera.getEffectiveFOV())/2)*Math.max(20,candidate.distance));
  const near=candidate.distance<=(previousFine||previousNear?330:300)&&candidate.pixels>=(previousFine||previousNear?280:360);
  const close=near&&(previousFine
    ?candidate.pixels>=280&&projectedErrorPixels>=2
    :candidate.pixels>=360&&projectedErrorPixels>=3);
  // Ultra expands the near range, not every region intersecting the frustum.
  // Entry/retention thresholds use the same projected source error as Auto.
  const expanded=profile.meshFine&&(
    near||(candidate.distance<=(previousFine?660:600)&&projectedErrorPixels>=(previousFine?1.5:2))
  );
  const fine=patch.levels.fine;
  const fitsFine=!!fine&&nativeLevelBytes(fine,fine.mask??patch.mask)<=budgetBytes;
  const useFine=!!fine&&fitsFine&&(expanded||close);
  const level=useFine?fine!:high;
  return {key:patch.id+(useFine?'/fine':'/high'),patch,level,
    bytes:nativeLevelBytes(level,level.mask??patch.mask),projectedErrorPixels,near,expandedRange:profile.meshFine,
    qualityReason:useFine?(expanded?'expanded-near-terminal-range':'near-source-error'):
      fine&&!fitsFine?'whole-terminal-group-exceeds-budget':fine?'distant-high-frontier':'highest-saved-only-level'};
}

/** Reserve complete high frontiers across the normal close view before upgrading
 * selected groups. Otherwise one fine region can regress its visible neighbour
 * all the way to baseline. Every quality mode reserves near complete frontiers
 * first, then spends remaining budget on terminal groups in priority order.
 * Distant groups receive only the remaining budget.
 */
function minimumNativeChoice(choice:Choice):Choice {
  const level=choice.patch.levels.high;
  return {...choice,key:choice.patch.id+'/high',level,bytes:nativeLevelBytes(level,level.mask??choice.patch.mask),qualityReason:choice.level===level?choice.qualityReason:'complete-near-neighbour-reservation'};
}
function terminalFineLevel(patch:Patch) {
  const fine=patch.levels.fine;
  return fine&&fine.tiles.length>0&&(fine.geometricErrorMax===0||fine.tiles.every(tile=>(tile.originalError??tile.geometricError)===0))?fine:undefined;
}

export function fitNativeDetailChoices(entries:Array<{choice:Choice;score:number}>,budgetBytes:number,currentUnionBytes=0,protectedChoices:readonly Choice[]=[]):Choice[]{
  const choices:Choice[]=[];
  const ranked=[...entries].sort((a,b)=>b.score-a.score||a.choice.key.localeCompare(b.choice.key));
  const reserved=new Set<string>();
  // These IDs come from source-audited view coverage, never from a guessed road
  // name or the selected entity. Each source cluster remains an atomic frontier.
  for(const choice of protectedChoices){
    if(reserved.has(choice.patch.id))continue;
    // Road/portal/canopy coverage needs the complete original terminal geometry,
    // not the cheaper ordinary high frontier of the same stable partition.
    if(choice.level!==terminalFineLevel(choice.patch))continue;
    const base={...choice,bytes:nativeLevelBytes(choice.level,choiceMask(choice)),qualityReason:'protected-visible-terminal-source-coverage'};
    if(nativePlanBytes([...choices,base],currentUnionBytes)>budgetBytes)continue;
    choices.push(base);reserved.add(choice.patch.id);
  }
  for(const {choice}of ranked){
    if(!choice.near||reserved.has(choice.patch.id))continue;
    const base=minimumNativeChoice(choice);
    if(nativePlanBytes([...choices,base],currentUnionBytes)>budgetBytes)continue;
    choices.push(base);reserved.add(choice.patch.id);
  }
  for(const {choice}of ranked){
    const index=choices.findIndex(c=>c.patch.id===choice.patch.id);
    if(index<0||choice.level!==choice.patch.levels.fine)continue;
    if(nativePlanBytes(choices.map((entry,i)=>i===index?choice:entry),currentUnionBytes)>budgetBytes)continue;
    choices[index]=choice;
  }
  const unfinishedNear=ranked.some(({choice})=>choice.near&&(
    !reserved.has(choice.patch.id)||choice.level===choice.patch.levels.fine&&
      choices.find(entry=>entry.patch.id===choice.patch.id)?.level!==choice.level
  ));
  for(const {choice}of ranked){
    if(reserved.has(choice.patch.id))continue;
    let accepted=choice;
    // A cheaper far terminal cluster must not look preferentially detailed
    // while the current near view still lacks its requested complete frontier.
    // Keep the surrounding complete high source, without enlarging the budget.
    if(!choice.near&&unfinishedNear&&choice.level===choice.patch.levels.fine)
      accepted={...minimumNativeChoice(choice),qualityReason:'near-frontier-before-distant-terminal-upgrade'};
    if(nativePlanBytes([...choices,accepted],currentUnionBytes)>budgetBytes&&choice.level===choice.patch.levels.fine){
      accepted={...minimumNativeChoice(choice),qualityReason:'whole-high-frontier-after-nearer-groups'};
    }
    if(nativePlanBytes([...choices,accepted],currentUnionBytes)>budgetBytes)continue;
    choices.push(accepted);
  }
  return choices;
}
type Ready = Choice & { group: THREE.Group; mask?: THREE.Texture };
type Transaction = Ready & {
  abort: AbortController;
  manager: BundleLoadingManager;
  parsers: Set<GLTFParser>;
  bitmaps: Set<ImageBitmap>;
  committed: boolean;
  timedOut: boolean;
};
/** Complete source frontiers; cancellation drains before another transaction starts. */
export class CampusMeshDetail {
  patches: Patch[] = [];
  root = new THREE.Group();
  visible = new Map<string, Ready>();
  cache = new Map<string, Ready>();
  pending: Transaction | null = null;
  desired: Choice[] = [];
  dead = false;
  budgetBytes = 0;
  progress = 0;
  failures = 0;
  cacheHits = 0;
  error = '';
  failureDetail = '';
  failureKey = '';
  private lastImageFailure: ImageFailureDiagnostic | null = null;
  private retries = new Map<string, { attempts: number; at: number }>();
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private last = 0;
  private order = new StableDetailOrder();
  private partialOwners = new Map<string,string>();
  private seen = new Map<
    string,
    { choice: Choice; score: number; at: number }
  >();
  constructor(
    public scene: THREE.Scene,
    public baseline: THREE.Group,
    public masks: SpatialMasks,
    public changed: () => void,
  ) {
    scene.add(this.root);
  }
  async init() {
    const r = await fetch('/models/hires/manifest.json');
    if (!r.ok) return;
    const data = (await r.json()) as { patches: Patch[] };
    if (!this.dead) this.patches = data.patches;
  }
  private resident() {
    return (
      [...this.visible.values(), ...this.cache.values()].reduce(
        (s, e) => s + e.bytes,
        0,
      ) + (this.pending && !this.pending.committed ? this.pending.bytes : 0)
    );
  }
  /** Shared-pool accounting: completed groups, full in-flight reservations and
   * the separately allocated exact partial-coverage union. Source image/GPU
   * allocation semantics match the manifest mip-byte budgets, not VRAM sensing.
   */
  memoryBytes() {
    return this.resident() + this.masks.partialCoverageStats().bytes +
      (this.pending && !this.pending.committed ? this.unionSwapBytes(this.pending) : 0);
  }
  planBytes(choices: Choice[]) {
    return nativePlanBytes(choices,this.masks.partialCoverageStats().bytes);
  }
  private unionSwapBytes(choice: Choice) {
    if(!choiceMask(choice))return 0;
    const kept:Choice[]=[...this.visible.values()].filter(entry=>entry.patch.id!==choice.patch.id);
    return nativeUnionBytes([...kept,choice]);
  }
  private release(entry: Ready) {
    const owned = resources([entry.group]);
    if (entry.mask) owned.texture.add(entry.mask);
    disposeResources(owned);
    entry.group.clear();
  }
  syncBaseline() {
    this.baselineVisibility();
  }
  private baselineVisibility() {
    const ids = new Set(
      [...this.visible.values()].flatMap((e) =>
        choiceMask(e) ? [] : e.patch.baselineIds,
      ),
    );
    for (const object of this.baseline.children)
      object.visible = !ids.has(object.name);
  }
  private remove(entry: Ready, cache = true) {
    this.root.remove(entry.group);
    this.visible.delete(entry.patch.id);
    if (this.partialOwners.has(entry.patch.id)) this.clearPartialMask(entry.patch.id);
    if (cache) this.cache.set(entry.key, entry);
    else this.release(entry);
    this.baselineVisibility();
  }
  private clearPartialMask(patchId:string) {
    const slot=this.partialOwners.get(patchId);if(!slot)return;
    // The slot owns its wrapper; cached entries continue to own the shared bitmap.
    const empty = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1);
    this.masks.set(slot, empty, [0, 0, 1, 1]);
    this.masks.enable(slot, false);
    this.partialOwners.delete(patchId);
  }
  private trim(extra = 0, except = '') {
    for (const [key, entry] of this.cache) {
      if (this.cache.size <= partialSlots.length && this.memoryBytes() + extra <= this.budgetBytes)
        break;
      if (key === except) continue;
      this.cache.delete(key);
      this.release(entry);
    }
  }
  setBudget(bytes: number, plan: readonly Choice[] = this.desired) {
    this.budgetBytes = bytes;
    this.trim();
    if (this.memoryBytes() > bytes) this.cancel();
    // A reduced grant must not tear down an already displayed complete source
    // frontier when the same physical patch is still requested. It can remain
    // temporarily over the target; the shared ledger reports that pressure and
    // blocks new admissions. Patches absent from the current view plan are safe
    // to release immediately.
    const planned = new Set(plan.map(choice => choice.patch.id));
    for (const entry of this.visible.values())
      if (!planned.has(entry.patch.id)) this.remove(entry, false);
    this.last = 0;
  }
  update(
    camera: THREE.PerspectiveCamera,
    height: number,
    profile: QualityProfile,
    time: number,
  ) {
    if (this.dead || time - this.last < 500) return;
    this.last = time;
    this.request(this.previewPlan(camera, height, profile, this.budgetBytes, time));
  }
  /** Preview a complete plan for a proposed shared-pool grant. Potential source
   * levels always use the profile ceiling so a temporarily reduced grant cannot
   * permanently suppress future fine demand. No loads or visible changes occur.
   */
  previewPlan(
    camera: THREE.PerspectiveCamera,
    height: number,
    profile: QualityProfile,
    budgetBytes: number,
    time: number,
    protectedChoices: readonly Choice[] = [],
  ): Choice[] {
    if (this.dead) return [];
    const ranked = this.order.rank(profile.meshMiB
      ? visibleDetails(camera, this.patches, height, profile.meshPixels,{ids:new Set(this.order.ids)})
      : []);
    for (const candidate of ranked) {
      const patch = this.patches.find((p) => p.id === candidate.id)!;
      // Hysteresis follows what the user actually sees. A fine request that was
      // deferred by the budget must not rewrite the displayed-level history.
      const previous=this.visible.get(patch.id)??this.seen.get(patch.id)?.choice;
      const choice=nativeDetailChoice(patch,candidate,camera,height,profile,profile.meshMiB*1048576,
        !!previous&&previous.level===patch.levels.fine,previous?.near);
      this.seen.set(patch.id, { choice, score: candidate.score, at: time });
    }
    const visibleIds=new Set(ranked.map(candidate=>candidate.id));
    for (const id of this.seen.keys())if(!visibleIds.has(id))this.seen.delete(id);
    // Fitting uses stable order, while diagnostics retain the physical score.
    const stable=ranked.map((candidate,index)=>({...this.seen.get(candidate.id)!,score:ranked.length-index}));
    return fitNativeDetailChoices(stable,budgetBytes,this.masks.partialCoverageStats().bytes,protectedChoices);
  }
  /** Complete error-zero fine frontiers for an externally audited coverage set.
   * Current screen visibility is required; this does not guess road ownership,
   * use selection/history, mutate the seen cache, or initiate any I/O. Callers
   * reserve these bytes before exterior borrowing and pass the same choices to
   * the final grant-sized previewPlan. Geometry/textures retain native sizes.
   */
  previewCoveragePlan(camera:THREE.PerspectiveCamera,height:number,profile:QualityProfile,patchIds:ReadonlySet<string>) {
    const choices:Choice[]=[],unavailableIds:string[]=[];
    if(!this.dead&&profile.meshMiB){
      const patches=this.patches.filter(patch=>patchIds.has(patch.id));
      const byId=new Map(patches.map(patch=>[patch.id,patch]));
      for(const candidate of visibleDetails(camera,patches,height,profile.meshPixels)){
        const patch=byId.get(candidate.id)!;
        const choice=nativeDetailChoice(patch,candidate,camera,height,profile,profile.meshMiB*1048576);
        const level=terminalFineLevel(patch);
        if(!level){unavailableIds.push(patch.id);continue;}
        choices.push({...choice,key:patch.id+'/fine',level,bytes:nativeLevelBytes(level,level.mask??patch.mask),qualityReason:'protected-visible-terminal-source-coverage'});
      }
    }
    return {choices,bytes:choices.length?this.planBytes(choices):0,unavailableIds};
  }
  request(choices: Choice[]) {
    if (this.dead) return;
    this.desired = choices;
    if (this.pending && !choices.some((c) => c.key === this.pending!.key))
      this.cancel();
    for (const entry of this.visible.values())
      if (!choices.some((c) => c.patch.id === entry.patch.id))
        this.remove(entry);
    // Preserve the requested cache hit while the outgoing group joins the LRU.
    this.trim(0, choices.find((choice) => this.cache.has(choice.key))?.key);
    this.pump();
  }
  private cancel() {
    const tx = this.pending;
    if (!tx || tx.abort.signal.aborted) return;
    tx.abort.abort();
    tx.manager.stop();
  }
  private commit(entry: Ready, tx?: Transaction) {
    if (choiceMask(entry) && !entry.mask)
      throw new Error('区域投影遮罩尚未就绪');
    this.masks.apply(entry.group, 'photogrammetry');
    const previous = this.visible.get(entry.patch.id);
    if (previous) this.remove(previous, false);
    this.cache.delete(entry.key);
    if (choiceMask(entry) && entry.mask) {
      const bounds = choiceMask(entry)!;
      const slot=partialSlots.find(name=>![...this.partialOwners.values()].includes(name));
      if(!slot)throw new Error('区域遮罩容量暂未就绪');
      this.masks.set(slot, entry.mask.clone(), [
        bounds.minX,
        bounds.minZ,
        bounds.maxX,
        bounds.maxZ,
      ]);
      this.partialOwners.set(entry.patch.id,slot);
    }
    this.visible.set(entry.patch.id, entry);
    this.root.add(entry.group);
    this.baselineVisibility();
    if (tx) tx.committed = true;
    this.error = '';
    this.retries.delete(entry.key);
    this.changed();
  }
  private pump() {
    if (this.dead || this.pending) return;
    clearTimeout(this.retryTimer);
    let retry = Infinity;
    for (const choice of this.desired) {
      if (this.visible.get(choice.patch.id)?.key === choice.key) continue;
      // Logical masks are independently owned; the shader samples their exact coverage union.
      if (
        choiceMask(choice) &&
        this.partialOwners.size >= partialSlots.length &&
        !this.partialOwners.has(choice.patch.id)
      )
        continue;
      const wait = (this.retries.get(choice.key)?.at || 0) - performance.now();
      if (wait > 0) {
        retry = Math.min(retry, wait);
        continue;
      }
      const cached = this.cache.get(choice.key);
      const additional=()=> (cached ? 0 : choice.bytes)+this.unionSwapBytes(choice);
      this.trim(additional(), choice.key);
      // Keep the old complete level until old + new + mask-union peak fits.
      // Deferred upgrades expose no baseline flash and retry on a later plan.
      if (this.memoryBytes() + additional() > this.budgetBytes)
        continue;
      if (cached) {
        this.cacheHits++;
        this.commit(cached);
        continue;
      }
      const tx: Transaction = {
        ...choice,
        group: new THREE.Group(),
        abort: new AbortController(),
        manager: new BundleLoadingManager(),
        parsers: new Set(),
        bitmaps: new Set(),
        committed: false,
        timedOut: false,
      };
      this.pending = tx;
      this.progress = 0;
      void this.load(tx);
      return;
    }
    if (Number.isFinite(retry))
      this.retryTimer = setTimeout(() => this.pump(), retry);
  }
  private check(tx: Transaction) {
    if (
      this.dead ||
      tx.abort.signal.aborted ||
      !this.desired.some((c) => c.key === tx.key)
    )
      throw new DOMException('Cancelled', 'AbortError');
  }
  private async load(tx: Transaction) {
    const stop = () => {
      tx.timedOut = true;
      tx.abort.abort();
      tx.manager.stop();
    };
    const timeout = setTimeout(stop, 180000);
    try {
      let sourceAsset = '';
      const loader = new GLTFLoader(tx.manager);
      loader.register((parser) => {
        const asset = sourceAsset;
        tx.parsers.add(parser);
        if (parser.textureLoader instanceof THREE.ImageBitmapLoader) {
          const imageLoader = parser.textureLoader,
            original = imageLoader.load.bind(imageLoader);
          imageLoader.load = (url, onLoad, onProgress, onError) =>
            original(
              url,
              (bitmap) => {
                tx.bitmaps.add(bitmap);
                onLoad?.(bitmap);
              },
              onProgress,
              (error) => {
                this.lastImageFailure = tx.manager.imageError(url, error, {
                  lane: 'mesh', groupId: tx.key, sourceAsset: asset,
                  aborted: tx.abort.signal.aborted,
                  stale: this.dead || !this.desired.some((c) => c.key === tx.key),
                  timedOut: tx.timedOut,
                });
                onError?.(error);
              },
            );
        }
        return { name: 'CampusMeshLifecycle' };
      });
      for (const tile of tx.level.tiles) {
        this.check(tx);
        const operationTimeout = setTimeout(stop, 45000);
        let gltf;
        try {
          const url = '/models/hires/' + tile.url;
          sourceAsset = url;
          const r = await fetch(url, { signal: tx.abort.signal });
          if (!r.ok) throw new Error('区域网格读取失败');
          const data = await r.arrayBuffer();
          this.check(tx);
          gltf = await loader.parseAsync(
            data,
            url.slice(0, url.lastIndexOf('/') + 1),
          );
        } finally {
          clearTimeout(operationTimeout);
        }
        tx.group.add(gltf.scene);
        this.check(tx);
        if (tx.manager.failed) throw new Error('区域原纹理读取失败');
        // Preserve the exact surveyed affine transform (including its small
        // shear) and the glTF root's own transform. TRS recomposition would
        // silently move adjoining source frontiers after updateMatrixWorld.
        if(gltf.scene.matrixAutoUpdate)gltf.scene.updateMatrix();
        gltf.scene.matrix.premultiply(new THREE.Matrix4().fromArray(tile.matrix));
        gltf.scene.matrixAutoUpdate=false;
        gltf.scene.matrixWorldNeedsUpdate=true;
        gltf.scene.traverse((o) => {
          if (!isMesh(o)) return;
          const multiple = Array.isArray(o.material);
          const materials = (
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
              map.anisotropy = 8;
            }
            const material = new THREE.MeshBasicMaterial({
              map,
              color,
              side: THREE.DoubleSide,
              vertexColors: !!o.geometry.attributes.color,
            });
            m.dispose();
            return material;
          });
          o.material = multiple ? materials : materials[0];
        });
        this.progress++;
      }
      if (choiceMask(tx)) {
        const mask = choiceMask(tx)!;
        const operationTimeout = setTimeout(stop, 45000);
        try {
          this.check(tx);
          const response = await fetch('/models/hires/' + mask.url, {
            signal: tx.abort.signal,
          });
          if (!response.ok) throw new Error('区域投影遮罩读取失败');
          const bitmap = await createImageBitmap(await response.blob(), {
            imageOrientation: 'none',
            premultiplyAlpha: 'none',
            colorSpaceConversion: 'none',
          });
          tx.bitmaps.add(bitmap);
          this.check(tx);
          if (bitmap.width !== mask.width || bitmap.height !== mask.height)
            throw new Error('区域投影遮罩尺寸与来源预留不符');
          tx.mask = new THREE.Texture(bitmap);
          tx.mask.colorSpace = THREE.NoColorSpace;
          tx.mask.flipY = false;
          tx.mask.generateMipmaps = false;
          tx.mask.needsUpdate = true;
          this.progress++;
        } finally {
          clearTimeout(operationTimeout);
        }
      }
      await tx.manager.drained();
      this.check(tx);
      if (tx.manager.failed) throw new Error('区域原纹理读取失败');
      this.commit(tx, tx);
    } catch (error) {
      if (!tx.abort.signal.aborted || tx.timedOut || tx.manager.failureBeforeCancellation) {
        this.failures++;
        this.failureDetail=(error instanceof Error?error.name+': '+error.message:String(error))+(tx.manager.failureDetail?' | '+tx.manager.failureDetail:'');
        this.failureKey=tx.key+' @ '+this.progress+'/'+tx.level.tiles.length+' '+tx.manager.failureURL;
        const attempts = (this.retries.get(tx.key)?.attempts || 0) + 1;
        this.retries.set(tx.key, {
          attempts,
          at:
            performance.now() + [2000, 5000, 15000][Math.min(attempts - 1, 2)],
        });
        this.error = '附近地面细节暂未就绪，将自动重试';
      }
    } finally {
      clearTimeout(timeout);
      if (!tx.committed) {
        tx.abort.abort();
        tx.manager.stop();
      }
      await tx.manager.drained();
      const owned = resources([tx.group], tx.parsers);
      const keep = tx.committed ? resources([tx.group]) : undefined;
      if (tx.mask) {
        owned.texture.add(tx.mask);
        keep?.texture.add(tx.mask);
      }
      disposeResources(owned, keep, tx.bitmaps);
      // Visible/cache entries retain this transaction object. Parser caches hold
      // GLB buffers and superseded materials, so release them after ownership is
      // transferred to the completed group (also on cancellation).
      tx.parsers.clear();
      tx.bitmaps.clear();
      if (this.pending === tx) this.pending = null;
      this.trim();
      this.changed();
      this.pump();
    }
  }
  stats() {
    return {
      visible: [...this.visible.values()].map((e) => e.key),
      triangles: [...this.visible.values()].reduce(
        (s, e) => s + e.level.triangles,
        0,
      ),
      loading: this.pending?.key || '',
      progress: this.progress,
      total: this.pending
        ? this.pending.level.tiles.length + (choiceMask(this.pending) ? 1 : 0)
        : 0,
      residentBytes: this.resident(),
      budgetBytes: this.budgetBytes,
      partialCoverage:this.masks.partialCoverageStats(),
      cacheGroups: this.cache.size,
      cacheHits: this.cacheHits,
      failures: this.failures,
      failureDetail:this.failureDetail,
      failureKey:this.failureKey,
      lastImageFailure:this.lastImageFailure,
      error: this.error,
    };
  }
  dispose() {
    this.dead = true;
    clearTimeout(this.retryTimer);
    this.cancel();
    for(const patchId of this.partialOwners.keys())this.clearPartialMask(patchId);
    for (const entry of this.visible.values()) this.release(entry);
    for (const entry of this.cache.values()) this.release(entry);
    this.visible.clear();
    this.cache.clear();
    this.baselineVisibility();
    this.scene.remove(this.root);
  }
}
