import * as THREE from 'three';

export type PanRect = Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>;
export type PanPointer = {
  pointerId: number;
  clientX: number;
  clientY: number;
};
export type PanSample = {
  pointer: [number, number];
  projected: [number, number];
  errorPx: number;
  clamped: boolean;
  reason: string;
};
export type PanAnchor = { point: THREE.Vector3; source: string };

/** One geometric pick per gesture. Hidden parents and helper lines are excluded. */
export function pickVisiblePanAnchor(
  ray: THREE.Raycaster,
  roots: THREE.Object3D[],
  accept?: (hit: THREE.Intersection) => boolean,
): PanAnchor | null {
  const meshes: THREE.Object3D[] = [];
  for (const root of roots) {
    if (!root.visible) continue;
    root.updateWorldMatrix(true, true);
    root.traverseVisible((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const materials = Array.isArray(object.material)
        ? object.material
        : [object.material];
      if (materials.some((material) => material.visible)) meshes.push(object);
    });
  }
  const hit = ray
    .intersectObjects(meshes, false)
    .find((hit) => !accept || accept(hit));
  return hit
    ? { point: hit.point.clone(), source: hit.object.name || 'rendered-mesh' }
    : null;
}

/** A fixed plane through the grabbed source point: horizontal for ordinary map
 * views, camera-facing near the horizon. It never switches during a drag.
 * Ground constraints run after translation; diagnostic error reports their limit.
 */
export class AnchoredPan {
  active = false;
  pointerId = -1;
  private anchor = new THREE.Vector3();
  private plane = new THREE.Plane();
  private ray = new THREE.Raycaster();
  private ndc = new THREE.Vector2();
  private intersection = new THREE.Vector3();
  private translation = new THREE.Vector3();
  private pointer: [number, number] = [0, 0];
  private source = '';
  private samples: PanSample[] = [];
  private pickMs = 0;
  private limited = '';
  private framePending = false;
  private gesture = 0;
  private rect: PanRect = { left: 0, top: 0, width: 1, height: 1 };
  private setRay(
    camera: THREE.PerspectiveCamera,
    pointer: PanPointer,
    rect: PanRect,
  ) {
    if (!(rect.width > 0 && rect.height > 0)) return false;
    camera.updateMatrixWorld();
    this.ndc.set(
      ((pointer.clientX - rect.left) / rect.width) * 2 - 1,
      1 - ((pointer.clientY - rect.top) / rect.height) * 2,
    );
    this.ray.setFromCamera(this.ndc, camera);
    return true;
  }
  begin(
    camera: THREE.PerspectiveCamera,
    target: THREE.Vector3,
    pointer: PanPointer,
    rect: PanRect,
    pick: (ray: THREE.Raycaster) => PanAnchor | null,
  ) {
    if (!this.setRay(camera, pointer, rect)) return false;
    const start = performance.now(),
      hit = pick(this.ray);
    this.pickMs = performance.now() - start;
    const normal = camera.getWorldDirection(new THREE.Vector3());
    if (hit) this.anchor.copy(hit.point);
    else {
      this.plane.setFromNormalAndCoplanarPoint(normal, target);
      if (!this.ray.ray.intersectPlane(this.plane, this.anchor)) return false;
    }
    const dragNormal =
      Math.abs(this.ray.ray.direction.y) >= 0.2
        ? new THREE.Vector3(0, 1, 0)
        : normal;
    this.plane.setFromNormalAndCoplanarPoint(dragNormal, this.anchor);
    this.source = hit?.source || 'target-depth-no-surface';
    this.pointerId = pointer.pointerId;
    this.active = true;
    this.samples = [];
    this.gesture++;
    this.pointer = [pointer.clientX, pointer.clientY];
    this.rect = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
    this.limited = '';
    this.framePending = true;
    this.record(camera, false, rect);
    return true;
  }
  move(
    camera: THREE.PerspectiveCamera,
    target: THREE.Vector3,
    pointer: PanPointer,
    rect: PanRect,
  ) {
    if (
      !this.active ||
      pointer.pointerId !== this.pointerId ||
      !this.setRay(camera, pointer, rect)
    )
      return false;
    this.pointer = [pointer.clientX, pointer.clientY];
    this.rect = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
    this.limited = '';
    this.framePending = true;
    const facing = this.ray.ray.direction.dot(this.plane.normal);
    if (
      Math.abs(facing) < 0.05 ||
      !this.ray.ray.intersectPlane(this.plane, this.intersection)
    ) {
      this.limited = 'near-parallel-ray';
      return false;
    }
    this.translation.subVectors(this.anchor, this.intersection);
    // Pointer capture can report very remote coordinates; never jump across the campus.
    const limit = Math.max(10, camera.position.distanceTo(this.anchor) * 2);
    if (this.translation.length() > limit) {
      this.translation.clampLength(0, limit);
      this.limited = 'remote-pointer-step';
    }
    if (!this.translation.toArray().every(Number.isFinite)) {
      this.limited = 'nonfinite-ray';
      return false;
    }
    camera.position.add(this.translation);
    target.add(this.translation);
    camera.updateMatrixWorld();
    return true;
  }
  /** Keep a held point fixed when the shared off-axis projection is animating,
   * including frames with no new pointermove event. Never pick a new anchor. */
  reproject(camera: THREE.PerspectiveCamera, target: THREE.Vector3, rect: PanRect) {
    return this.move(camera, target, {
      pointerId: this.pointerId,
      clientX: this.pointer[0],
      clientY: this.pointer[1],
    }, rect);
  }
  /** Record the point the user actually sees, after the existing ground guard. */
  record(
    camera: THREE.PerspectiveCamera,
    groundClamped: boolean,
    rect: PanRect = this.rect,
  ) {
    if (!this.active || !this.framePending) return;
    camera.updateMatrixWorld();
    const p = this.anchor.clone().project(camera);
    const projected: [number, number] = [
      rect.left + ((p.x + 1) * rect.width) / 2,
      rect.top + ((1 - p.y) * rect.height) / 2,
    ];
    this.samples.push({
      pointer: [...this.pointer],
      projected,
      errorPx: Math.hypot(
        projected[0] - this.pointer[0],
        projected[1] - this.pointer[1],
      ),
      clamped: groundClamped || !!this.limited,
      reason: this.limited || (groundClamped ? 'ground-constraint' : ''),
    });
    if (this.samples.length > 64) this.samples.shift();
    this.framePending = false;
  }
  get needsRecord() {
    return this.active && this.framePending;
  }
  end() {
    this.active = false;
    this.pointerId = -1;
  }
  stats() {
    return {
      active: this.active,
      gesture: this.gesture,
      anchor: this.anchor.toArray(),
      source: this.source,
      planeNormal: this.plane.normal.toArray(),
      pickMs: this.pickMs,
      last: this.samples.at(-1) ?? null,
      samples: this.samples.map((sample) => ({
        ...sample,
        pointer: [...sample.pointer],
        projected: [...sample.projected],
      })),
      maxUnclampedErrorPx: Math.max(
        0,
        ...this.samples
          .filter((sample) => !sample.clamped)
          .map((sample) => sample.errorPx),
      ),
    };
  }
}
