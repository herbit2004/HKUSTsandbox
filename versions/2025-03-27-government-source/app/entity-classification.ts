import type { Entity, EntityRegistry } from './entity-registry';
import { t, type Locale } from './i18n';
import {
  entityDisplayName,
  entitySearchNames,
  normalizeSearch,
} from './entity-names';

export const entityCategories = [
  { id: 'building', label: '建筑', group: '校园与户外' },
  { id: 'outdoor_area', label: '场地', group: '校园与户外' },
  { id: 'path', label: '道路', group: '校园与户外' },
  { id: 'zone', label: '区域', group: '校园与户外' },
  { id: 'floor', label: '楼层', group: '建筑内' },
  { id: 'space', label: '空间', group: '建筑内' },
  { id: 'elevator', label: '电梯', group: '通行与设施' },
  { id: 'stairs', label: '楼梯', group: '通行与设施' },
  { id: 'escalator', label: '扶梯', group: '通行与设施' },
  { id: 'entrance', label: '出入口', group: '通行与设施' },
  { id: 'connector', label: '其他连接设施', group: '通行与设施' },
  { id: 'facility', label: '一般设施', group: '通行与设施' },
  { id: 'other', label: '其他实体', group: '其他' },
] as const;

export type EntityCategory = (typeof entityCategories)[number]['id'];
export type EntityFilter = EntityCategory | 'all' | 'overview';
type Classification = { category: EntityCategory; label: string };
type ClassifiableEntity = Pick<Entity, 'type' | 'function' | 'sourceTypes'> & {
  subtype?: string;
};
const connectorTypes: Record<string, Classification> = {
  elevator: { category: 'elevator', label: '电梯' },
  lift: { category: 'elevator', label: '电梯' },
  stairs: { category: 'stairs', label: '楼梯' },
  escalator: { category: 'escalator', label: '扶梯' },
  entrance: { category: 'entrance', label: '出入口' },
  exit: { category: 'entrance', label: '出入口' },
  door: { category: 'entrance', label: '门' },
};
const connectorSourceTypes: Record<string, string> = {
  'Lift Shaft': 'elevator',
  Staircase: 'stairs',
  Escalator: 'escalator',
};
const functionLabels: Record<string, Record<string, string>> = {
  path: { vehicle_access: '车行通道' },
  space: {
    room: '房间',
    toilet: '洗手间',
    library: '图书馆空间',
    corridor: '走廊',
    lobby: '大堂',
  },
  outdoor_area: {
    sports_court: '球场',
    tennis_court: '网球场',
    soccer_field: '足球场',
    track_and_infield_surface: '田径场',
    plaza: '广场',
  },
  facility: {
    drinkingfountain: '饮水机',
    drinking_water: '饮水设施',
    aed: 'AED',
    atm: 'ATM',
    bus_station: '巴士站',
    foodbooth: '餐饮摊位',
    kmbkiosk: '九巴服务站',
    landmark: '地标',
    sundial: '日晷',
    sundial_sculpture: '日晷',
  },
};

function ownValue<T>(values: Record<string, T>, key: string): T | undefined {
  return Object.hasOwn(values, key) ? values[key] : undefined;
}
const typeLabels: Record<string, string> = {
  building: '建筑',
  floor: '楼层',
  space: '空间',
  outdoor_area: '场地',
  path: '道路',
  connector: '连接设施',
  facility: '设施',
  zone: '区域',
  campus: '校园',
};

/** Registry function is its source-backed semantic subtype; representation subtype describes geometry. */
function classifySourceEntity(entity: ClassifiableEntity): Classification {
  const subtype = entity.subtype ?? entity.function;
  if (entity.type === 'connector') {
    const known = subtype ? ownValue(connectorTypes, subtype) : undefined;
    if (known) return known;
    if (!subtype) {
      const sourceKinds = new Set(
        (entity.sourceTypes || [])
          .map((t) => ownValue(connectorSourceTypes, t))
          .filter((kind): kind is string => typeof kind === 'string'),
      );
      if (sourceKinds.size === 1) return connectorTypes[[...sourceKinds][0]];
    }
    return { category: 'connector', label: typeLabels.connector };
  }
  const category =
    entityCategories.find((item) => item.id === entity.type)?.id || 'other';
  const functions = ownValue(functionLabels, entity.type);
  return {
    category,
    label:
      (subtype && functions && ownValue(functions, subtype)) ||
      ownValue(typeLabels, entity.type) ||
      '实体',
  };
}

export function classifyEntity(
  entity: ClassifiableEntity,
  locale: Locale = 'zh-Hans',
): Classification {
  const source = classifySourceEntity(entity);
  return { ...source, label: t(locale, source.label) };
}

/** Keep original entity references and stable IDs when a multi-floor connector appears in both lists. */
export function uniqueEntities(entities: Entity[]): Entity[] {
  return [
    ...new Map(entities.map((entity) => [entity.entityId, entity])).values(),
  ];
}

export function categoryCounts(
  entities: Entity[],
): Map<EntityCategory, number> {
  const counts = new Map<EntityCategory, number>();
  for (const entity of uniqueEntities(entities)) {
    const category = classifyEntity(entity).category;
    counts.set(category, (counts.get(category) || 0) + 1);
  }
  return counts;
}

/** Physical ownership follows recorded parents. A connector only gets a floor from a recorded stop. */
export function entityLocation(
  entity: Entity,
  registry: EntityRegistry,
  contextFloorId = '',
): Entity[] {
  const ancestors: Entity[] = [];
  const seen = new Set([entity.entityId]);
  let current = registry.parent(entity);
  if (!current) {
    const relation = entity.relations?.find(
      (r) => r.type === 'locatedIn' || r.type === 'hostedBy',
    );
    current = relation ? registry.get(relation.targetId) : undefined;
  }
  while (current && !seen.has(current.entityId)) {
    seen.add(current.entityId);
    ancestors.unshift(current);
    current = registry.parent(current);
  }
  if (
    contextFloorId &&
    entity.stops?.some((stop) => stop.floorId === contextFloorId)
  ) {
    const floor = registry.get(contextFloorId);
    if (floor && !seen.has(floor.entityId)) ancestors.push(floor);
  }
  return ancestors.length > 1
    ? ancestors.filter((parent) => parent.type !== 'campus')
    : ancestors;
}

export function describeEntity(
  entity: Entity,
  registry: EntityRegistry,
  contextFloorId = '',
  locale: Locale = 'zh-Hans',
) {
  return [
    classifyEntity(entity, locale).label,
    ...entityLocation(entity, registry, contextFloorId).map((parent) =>
      entityDisplayName(parent, locale),
    ),
  ].join(' · ');
}

type SearchEntry = { entity: Entity; text: string; names: Set<string> };
const searchIndexes = new WeakMap<EntityRegistry, SearchEntry[]>();
/** Build the three-language index once per immutable source registry. */
export function prepareEntitySearch(registry: EntityRegistry): SearchEntry[] {
  const existing = searchIndexes.get(registry);
  if (existing) return existing;
  const index = registry.entities
    .filter((entity) => entity.type !== 'campus')
    .map((entity) => {
      const names = entitySearchNames(entity);
      const texts = [
        ...names,
        entity.function || '',
        ...(['en', 'zh-Hant', 'zh-Hans'] as const).flatMap((locale) => [
          describeEntity(entity, registry, '', locale),
          t(locale, ownValue(typeLabels, entity.type) || ''),
          t(
            locale,
            (entity.function &&
              ownValue(
                ownValue(functionLabels, entity.type) || {},
                entity.function,
              )) ||
              '',
          ),
        ]),
      ];
      return {
        entity,
        text: normalizeSearch(texts.join(' ')),
        names: new Set(names.map(normalizeSearch)),
      };
    });
  searchIndexes.set(registry, index);
  return index;
}

/** Source aliases and all displayed languages search the same stable entities. */
export function searchClassifiedEntities(
  registry: EntityRegistry,
  query: string,
): Entity[] {
  const text = normalizeSearch(query);
  if (!text) return [];
  const exactType = entityCategories.find((category) =>
    ['en', 'zh-Hant', 'zh-Hans'].some(
      (locale) => normalizeSearch(t(locale as Locale, category.label)) === text,
    ),
  );
  return prepareEntitySearch(registry)
    .filter((entry) =>
      exactType
        ? classifyEntity(entry.entity).category === exactType.id
        : entry.text.includes(text),
    )
    .sort((a, b) => Number(b.names.has(text)) - Number(a.names.has(text)))
    .map((entry) => entry.entity);
}
