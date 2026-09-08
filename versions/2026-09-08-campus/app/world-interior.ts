import * as THREE from "three";
import { releaseObject } from "./resources";
import type { EntityRegistry, Entity } from "./entity-registry";
import type { CachedInteriorFloor, FloorManifestEntry, InteriorRoom } from "./source-types";
type RoomMesh = THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> & {
  userData: { room: InteriorRoom; floorId: string; entityId?: string };
};

export class WorldInterior {
  partMap = new Map<string, Entity>();
  root = new THREE.Group();
  highlight = new THREE.Group();
  cache = new Map<string, CachedInteriorFloor>();
  bytes = 0;
  abort: AbortController | null = null;
  generation = 0;
  roomObjects: RoomMesh[] = [];
  data: CachedInteriorFloor[] = [];
  boundary = 0.8;
  selected = "";
  floorId = "";
  loading = false;
  stack = false;
  constructor(
    public scene: THREE.Scene,
    public registry: EntityRegistry,
    public changed: () => void,
  ) {
    scene.add(this.root, this.highlight);
    for (const e of registry.entities)
      for (const p of e.representations || [])
        if (p.type === "room_parts") {
          const f = (p.floorId || "").replace(/^floor:/, "");
          for (const i of p.partIndices || []) this.partMap.set(f + "/" + i, e);
        }
  }
  async floor(f: FloorManifestEntry, signal: AbortSignal) {
    if (this.cache.has(f.id)) {
      const d = this.cache.get(f.id)!;
      this.cache.delete(f.id);
      this.cache.set(f.id, d);
      return d;
    }
    const response = await fetch("/interiors/" + f.url, { signal });
    if (!response.ok) throw Error("楼层读取失败");
    const d = (await response.json()) as CachedInteriorFloor;
    if (d.cad) {
      const r = await fetch("/interiors/" + d.cad.url, { signal });
      if (!r.ok) throw Error("楼层参考线读取失败");
      d.cadPositions = await r.arrayBuffer();
    }
    d.cacheBytes = (d.cadPositions?.byteLength || 0) + JSON.stringify(d.rooms).length * 2;
    if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
    this.cache.set(f.id, d);
    this.bytes += d.cacheBytes;
    while (this.cache.size > 5 || this.bytes > 32 * 1048576) {
      const key = this.cache.keys().next().value!;
      this.bytes -= this.cache.get(key)!.cacheBytes;
      this.cache.delete(key);
    }
    return d;
  }
  async show(floors: FloorManifestEntry[], floorId: string, stack = false) {
    this.abort?.abort();
    const abort = new AbortController();
    this.abort = abort;
    const gen = ++this.generation;
    this.loading = true;
    this.floorId = floorId;
    this.stack = stack;
    this.data = [];
    this.clear();
    this.changed();
    try {
      const wanted = stack ? floors : floors.filter((f) => f.id === floorId);
      const data = [];
      for (const f of wanted) data.push(await this.floor(f, abort.signal));
      if (abort.signal.aborted || gen !== this.generation) return;
      this.data = data;
      this.render();
      this.loading = false;
      this.changed();
    } catch (e) {
      if (!abort.signal.aborted) {
        this.loading = false;
        this.changed();
        throw e;
      }
    }
  }
  entityFor(floorId: string, index: number) {
    return this.partMap.get(floorId + "/" + index);
  }
  clear() {
    this.root.userData.cadAnchor = "";
    releaseObject(this.root);
    this.root.clear();
    releaseObject(this.highlight);
    this.highlight.clear();
    this.roomObjects = [];
  }
  render() {
    this.clear();
    for (const f of this.data) {
      const layer = new THREE.Group();
      layer.userData.floorId = f.id;
      this.root.add(layer);
      for (const [partIndex, r] of f.rooms.entries()) {
        if (!r.rings[0]?.length) continue;
        const shape = new THREE.Shape(r.rings[0].map((p) => new THREE.Vector2(p[0], -p[1])));
        for (const hole of r.rings.slice(1))
          shape.holes.push(new THREE.Path(hole.map((p) => new THREE.Vector2(p[0], -p[1]))));
        const geo = new THREE.ShapeGeometry(shape);
        geo.rotateX(-Math.PI / 2);
        const color = /^#?[0-9a-f]{6}$/i.test(r.color)
          ? r.color.startsWith("#")
            ? r.color
            : "#" + r.color
          : "#e0e9ed";
        const material = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
        const mesh = new THREE.Mesh(geo, material);
        mesh.position.y = r.heightSourceZ;
        const entity = r.interactive !== false ? this.entityFor(f.id, partIndex) : null;
        const roomMesh = Object.assign(mesh, {
          userData: { room: r, floorId: f.id, entityId: entity?.entityId },
        });
        layer.add(mesh);
        if (entity) this.roomObjects.push(roomMesh);
        const wall: number[] = [],
          edge: number[] = [];
        for (const ring of r.rings)
          for (let i = 0; i < ring.length - 1; i++) {
            const a = ring[i],
              b = ring[i + 1],
              y = r.heightSourceZ + 0.04;
            edge.push(a[0], y, a[1], b[0], y, b[1]);
            if (this.boundary > 0 && r.interactive !== false)
              wall.push(
                a[0],
                y,
                a[1],
                b[0],
                y,
                b[1],
                b[0],
                y + this.boundary,
                b[1],
                a[0],
                y,
                a[1],
                b[0],
                y + this.boundary,
                b[1],
                a[0],
                y + this.boundary,
                a[1],
              );
          }
        if (wall.length) {
          const g = new THREE.BufferGeometry();
          g.setAttribute("position", new THREE.Float32BufferAttribute(wall, 3));
          layer.add(
            new THREE.Mesh(
              g,
              new THREE.MeshBasicMaterial({
                color: 0xd2dfe5,
                side: THREE.DoubleSide,
                transparent: true,
                opacity: 0.7,
              }),
            ),
          );
        }
        if (!f.cad) {
          const g = new THREE.BufferGeometry();
          g.setAttribute("position", new THREE.Float32BufferAttribute(edge, 3));
          layer.add(
            new THREE.LineSegments(
              g,
              new THREE.LineBasicMaterial({ color: 0x748995, transparent: true, opacity: 0.7 }),
            ),
          );
        }
      }
      if (f.cadPositions) {
        const g = new THREE.BufferGeometry(),
          positions = new Float32Array(f.cadPositions.slice(0));
        for (let i = 1; i < positions.length; i += 3) positions[i] += 0.075;
        g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        layer.add(
          new THREE.LineSegments(
            g,
            new THREE.LineBasicMaterial({ color: 0x607986, transparent: true, opacity: 0.8 }),
          ),
        );
        this.root.userData.cadAnchor = Array.from(positions.slice(0, 6))
          .map((v) => v.toFixed(3))
          .join(",");
      }
    }
    if (this.selected) this.select(this.selected);
  }
  setBoundary(value: number) {
    this.boundary = value;
    if (!this.loading && this.data.length) this.render();
  }
  select(entityId: string) {
    this.selected = entityId;
    releaseObject(this.highlight);
    this.highlight.clear();
    const matches = this.roomObjects.filter((o) => o.userData.entityId === entityId);
    for (const o of matches) {
      const fill = new THREE.Mesh(
        o.geometry.clone(),
        new THREE.MeshBasicMaterial({
          color: 0x1895bc,
          transparent: true,
          opacity: 0.45,
          depthTest: false,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      );
      fill.position.copy(o.position);
      fill.position.y += 0.1;
      fill.renderOrder = 25;
      this.highlight.add(fill);
      for (const ring of o.userData.room.rings) {
        const g = new THREE.BufferGeometry().setFromPoints(
          ring.map((p) => new THREE.Vector3(p[0], o.position.y + 0.14, p[1])),
        );
        const line = new THREE.Line(
          g,
          new THREE.LineBasicMaterial({ color: 0xf1aa3a, transparent: true, depthTest: false }),
        );
        line.renderOrder = 26;
        this.highlight.add(line);
      }
    }
    return matches.length ? new THREE.Box3().setFromObject(this.highlight) : null;
  }
  stop() {
    this.generation++;
    this.abort?.abort();
    this.clear();
    this.data = [];
    this.loading = false;
    this.floorId = "";
    this.selected = "";
    this.changed();
  }
  dispose() {
    this.stop();
    this.cache.clear();
    this.scene.remove(this.root, this.highlight);
  }
}
