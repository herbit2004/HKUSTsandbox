import {
  parseEntityRegistry,
  type EntityData,
  type EntityRegistryData,
  type EntityResource,
} from "./source-types";
export type Entity = EntityData;
export class EntityRegistry {
  entities: Entity[];
  byId: Map<string, Entity>;
  legacyMap: Record<string, string>;
  children = new Map<string, Entity[]>();
  resources: EntityResource[] = [];
  data: EntityRegistryData;
  constructor(value: unknown) {
    const data = parseEntityRegistry(value);
    this.data = data;
    this.entities = data.entities;
    this.byId = new Map(this.entities.map((e) => [e.entityId, e]));
    this.legacyMap = data.legacyMap || {};
    for (const e of this.entities) {
      const parent = e.primaryParent || e.parentId;
      if (parent) {
        if (!this.children.has(parent)) this.children.set(parent, []);
        this.children.get(parent)!.push(e);
      }
    }
  }
  get(id: string) {
    return this.byId.get(this.legacyMap[id] || id);
  }
  parent(e: Entity) {
    return this.get(e.primaryParent || e.parentId || "");
  }
  zoneMembers(e: Entity): Entity[] {
    if (e.type !== "zone") return [];
    const members = new Map((this.children.get(e.entityId) || []).map(child => [child.entityId, child]));
    for (const relation of e.relations || []) {
      if (relation.type !== "contains") continue;
      const member = this.get(relation.targetId);
      if (member && member.entityId !== e.entityId) members.set(member.entityId, member);
    }
    return [...members.values()];
  }
  building(e?: Entity): Entity | undefined {
    const seen = new Set<string>();
    while (e && !seen.has(e.entityId)) {
      if (e.type === "building") return e;
      seen.add(e.entityId);
      e = this.parent(e);
    }
    return undefined;
  }
  floor(e?: Entity): Entity | undefined {
    const seen = new Set<string>();
    while (e && !seen.has(e.entityId)) {
      if (e.type === "floor") return e;
      seen.add(e.entityId);
      e = this.parent(e);
    }
    return undefined;
  }
  floorSource(e: Entity) {
    return (
      e.externalIds?.pathAdvisorFloorId ||
      e.externalIds?.pathAdvisor?.building_floor_id ||
      e.entityId.replace(/^floor:/, "")
    );
  }
  buildingSource(e: Entity) {
    return e.externalIds?.pathAdvisorBuildingId || e.entityId.replace(/^building:/, "");
  }
  legacy(e: Entity) {
    return Object.keys(this.legacyMap).find((id) => this.legacyMap[id] === e.entityId);
  }
  search(query: string, scope?: Entity) {
    const q = query.toLocaleLowerCase().trim();
    return this.entities
      .filter(
        (e) =>
          e.type !== "campus" &&
          (!scope ||
            this.building(e)?.entityId === scope.entityId ||
            e.entityId === scope.entityId) &&
          [
            e.name,
            ...(e.aliases || []),
            e.function || "",
            this.building(e)?.name || "",
            this.floor(e)?.name || "",
          ]
            .join(" ")
            .toLocaleLowerCase()
            .includes(q),
      )
      .sort((a, b) => Number(b.name.toLowerCase() === q) - Number(a.name.toLowerCase() === q));
  }
}
