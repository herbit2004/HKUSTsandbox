// Current source modules and registry; no mirrored name/search implementation.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = new Map();
function load(name) {
  if (modules.has(name)) return modules.get(name);
  const source = fs.readFileSync(path.join(root, 'app', name + '.ts'), 'utf8');
  const out = {};
  modules.set(name, out);
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  vm.runInNewContext(code, { exports: out, require(id) {
    assert.ok(id.startsWith('./'), 'unexpected external dependency ' + id);
    return load(id.slice(2));
  } }, { filename: name + '.ts' });
  return out;
}

const registryPath = path.join(root, 'public/data/entity-registry.json');
const bytes = fs.readFileSync(registryPath);
const raw = JSON.parse(bytes);
const original = JSON.stringify(raw);
const { EntityRegistry } = load('entity-registry');
const registry = new EntityRegistry(raw);
const { entityDisplayName, entitySearchNames, normalizeSearch } = load('entity-names');
const { entityNameLocales, descriptiveNameTranslations } = load('entity-name-locales');
const { classifyEntity, entityCategories, searchClassifiedEntities, prepareEntitySearch } = load('entity-classification');
const { hasTranslation, t } = load('i18n');
const locales = ['zh-Hans', 'zh-Hant', 'en'];
const entities = registry.entities.filter(e => e.type === 'building' || e.type === 'zone');
const checks = [];
function check(name, fn) { fn(); checks.push(name); }

check('every current building and zone has an explicit canonical trilingual display name; no stale mapping IDs', () => {
  assert.equal(new Set(entities.map(e => e.entityId)).size, entities.length);
  assert.deepEqual(Object.keys(entityNameLocales).sort(), entities.map(e => e.entityId).sort());
  for (const entity of entities) for (const locale of locales) {
    const name = entityDisplayName(entity, locale);
    assert.equal(name, entityNameLocales[entity.entityId][locale]);
    assert.ok(name.length && !/[{}]/.test(name));
    if (locale === 'en') assert.doesNotMatch(name, /[\u3400-\u9fff]/, entity.entityId);
    else assert.match(name, /[\u3400-\u9fff]/, entity.entityId);
  }
});
check('all three displayed names and all original aliases retrieve the same canonical entity without duplicate results', () => {
  const index = prepareEntitySearch(registry);
  assert.equal(prepareEntitySearch(registry), index, 'language lookup must reuse the immutable registry index');
  for (const entity of entities) for (const query of entitySearchNames(entity)) {
    const results = searchClassifiedEntities(registry, query);
    assert.equal(results.filter(e => e.entityId === entity.entityId).length, 1, entity.entityId + ' :: ' + query);
    assert.equal(new Set(results.map(e => e.entityId)).size, results.length);
  }
});
check('verified donor names and source identity distinctions survive fallback ordering and alternate scripts', () => {
  assert.equal(entityDisplayName(registry.get('building:catalog:campus-32'), 'en'), 'Tsang Chiu Sang Tower');
  assert.equal(entityDisplayName(registry.get('building:catalog:campus-33'), 'en'), 'Lam Po Yu Tower');
  assert.equal(entityDisplayName(registry.get('building:catalog:campus-33'), 'zh-Hant'), '林寳茹樓');
  for (const query of ['林宝茹楼', '林寶茹樓', '林寳茹樓', 'University Apartments Tower B'])
    assert.ok(searchClassifiedEntities(registry, query).some(e => e.entityId === 'building:catalog:campus-33'));
  const uc = registry.get('building:b00000000000000000000006');
  const cd = ['c', 'd'].map(letter => registry.get('building:catalog:university-apartments-tower-' + letter));
  for (const locale of locales) assert.equal(new Set([uc, ...cd].map(e => entityDisplayName(e, locale))).size, 3);
  assert.equal(registry.entities.filter(e => e.aliases?.includes('UG Hall VI')).length, 1);
  assert.equal(registry.entities.filter(e => e.entityId.startsWith('building:catalog:staff-quarters-apartments-')).length, 4);
});
check('Chinese staff residence names convert fully while floors keep official short labels', () => {
  for (const entity of entities.filter(e => /staff-quarters/.test(e.entityId))) {
    assert.doesNotMatch(entityDisplayName(entity, 'zh-Hans'), /Staff|Tower|House|Apartment|Block/);
    assert.doesNotMatch(entityDisplayName(entity, 'zh-Hant'), /职|员|独|号|楼/);
    assert.equal(normalizeSearch(entityDisplayName(entity, 'zh-Hant')), normalizeSearch(entityDisplayName(entity, 'zh-Hans')));
  }
  for (const entity of registry.entities.filter(e => e.type === 'floor'))
    for (const locale of locales) assert.equal(entityDisplayName(entity, locale), entity.name);
});
check('existing official Chinese road aliases become display names and keep English searches on the same road IDs', () => {
  for (const [id, hans, hant] of [
    ['path:universityroad', '大学道', '大學道'],
    ['path:nganyingroad', '银影路', '銀影路'],
    ['path:clearwaterbayroad', '清水湾道', '清水灣道'],
  ]) {
    const entity = registry.get(id);
    assert.equal(entityDisplayName(entity, 'zh-Hans'), hans);
    assert.equal(entityDisplayName(entity, 'zh-Hant'), hant);
    for (const query of [entity.name, hans, hant]) assert.ok(searchClassifiedEntities(registry, query).some(e => e.entityId === id));
  }
});
check('every actual entity classification and filter label has a translation without changing taxonomy', () => {
  for (const entity of registry.entities) {
    const original = classifyEntity(entity, 'zh-Hans');
    assert.ok(hasTranslation(original.label) || ['AED', 'ATM'].includes(original.label), original.label);
    for (const locale of locales) {
      const localized = classifyEntity(entity, locale);
      assert.equal(localized.category, original.category);
      if (locale === 'en') assert.doesNotMatch(localized.label, /[\u3400-\u9fff]/);
    }
  }
  for (const category of entityCategories) {
    assert.ok(hasTranslation(category.label));
    assert.ok(hasTranslation(category.group));
    for (const locale of locales) {
      const results = searchClassifiedEntities(registry, t(locale, category.label));
      assert.ok(results.every(e => classifyEntity(e).category === category.id));
    }
  }
});
check('display and search leave original source names, aliases, stable IDs and registry bytes unchanged', () => {
  assert.equal(JSON.stringify(raw), original);
  assert.ok(fs.readFileSync(registryPath).equals(bytes));
});

const rows = entities.map(entity => ({
  entityId: entity.entityId, type: entity.type, sourceName: entity.name,
  sourceAliases: entity.aliases, displayNames: entityNameLocales[entity.entityId],
  basis: descriptiveNameTranslations.includes(entity.entityId)
    ? 'Descriptive translation of the original English name; no independently verified Chinese naming record.'
    : /staff-quarters|university-apartments-tower/.test(entity.entityId) || entity.type === 'zone' && entity.entityId !== 'zone:catalog:campus-52'
      ? 'Literal translation of the checked source group/residence identity; no new physical subdivision.'
      : 'Checked registry name and aliases; donor identity preserved, Chinese script localized.',
}));
const report = {
  passed: true, checks,
  registrySha256: crypto.createHash('sha256').update(bytes).digest('hex'),
  counts: { buildings: entities.filter(e => e.type === 'building').length, zones: entities.filter(e => e.type === 'zone').length, locales: locales.length },
  scope: 'Actual current registry, display, taxonomy and search modules. UI continuity is exercised separately by check-ui-session.mjs; pixel layout and rendered labels require browser QA. Registry building count is not a unique physical building denominator.',
  rows,
};
fs.writeFileSync(path.join(root, 'docs/source-evidence-v4/entity-locale-tests.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ ...report, rows: report.rows.length }, null, 2));
