// Static, source-asset audit of direct building picking coverage.
// This deliberately does not start the app or publish a preview.  It reads the
// checked-in manifests and real triangles, then calls the production pickEntity.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const readJson = p => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const cache = new Map();
function compile(name) {
  if (cache.has(name)) return cache.get(name);
  const exports = {};
  cache.set(name, exports);
  const source = fs.readFileSync(path.join(root, 'app', `${name}.ts`), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, {
    exports, require: id => id === 'three' ? THREE : compile(id.replace('./', '')),
    THREE, console, Map, Set, WeakMap, Uint8Array, Float32Array, Float64Array,
    Array, Math, Number, String, Object, Error,
  });
  return exports;
}
const { pickEntity, exteriorSourceOwner } = compile('entity-picking');
const { SpatialMasks } = compile('spatial-masks');
const { exteriorEntityId } = compile('source-types');
const { EntityRegistry } = compile('entity-registry');

const registry = new EntityRegistry(readJson('public/data/entity-registry.json'));
const footprints = readJson('public/data/building-footprints.json').footprints;
const named = readJson('public/data/picking/building-domains.json').domains;
const extra = readJson('public/data/picking/building-domains-extra.json');
const exteriors = readJson('public/models/exteriors/manifest.json');
const hires = readJson('public/models/hires/manifest.json');
const fixtureEvidence = ['docs/source-evidence-v4/entity-picking/source-triangle-fixtures.json', 'docs/source-evidence-v4/entity-picking/named-domain-source-fixtures.json'].map(asset => {
  const cases = readJson(asset).cases || [], byRepresentation = {};
  for (const item of cases) byRepresentation[item.representation] = (byRepresentation[item.representation] || 0) + 1;
  return { asset, cases: cases.length, byRepresentation };
});
const rangeDomains = exteriors.bundles.flatMap(bundle => {
  const id = exteriorEntityId(bundle);
  if (registry.get(id)?.type !== 'zone') return [];
  return (extra.auditOnlyAggregateDomains || []).filter(d => d.entityId === id && d.physicalDomainId === bundle.physicalDomainId).map(d => ({
    ...d, minY: Math.min(d.minY, bundle.bounds.min[1]), maxY: bundle.bounds.max[1], sourceObjectIds: bundle.objects.map(o => o.id),
  }));
});

function readGltf(file) {
  const raw = fs.readFileSync(file);
  let gltf, buffers;
  if (file.endsWith('.gltf')) {
    gltf = JSON.parse(raw);
    buffers = gltf.buffers.map(b => {
      assert.ok(b.uri && !b.uri.startsWith('data:'), `unsupported embedded buffer: ${file}`);
      return fs.readFileSync(path.join(path.dirname(file), b.uri));
    });
  } else {
    assert.equal(raw.toString('ascii', 0, 4), 'glTF');
    const chunks = {};
    for (let at = 12; at < raw.length;) {
      const size = raw.readUInt32LE(at), kind = raw.toString('ascii', at + 4, at + 8);
      chunks[kind] = raw.subarray(at + 8, at + 8 + size); at += 8 + size;
    }
    gltf = JSON.parse(chunks.JSON.toString()); buffers = [chunks['BIN\0']];
  }
  const component = { 5121: ['readUInt8', 1], 5123: ['readUInt16LE', 2], 5125: ['readUInt32LE', 4], 5126: ['readFloatLE', 4] };
  function accessor(index) {
    const a = gltf.accessors[index], view = gltf.bufferViews[a.bufferView], [method, bytes] = component[a.componentType];
    assert.ok(method, `unsupported component ${a.componentType} in ${file}`);
    const n = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[a.type], buffer = buffers[view.buffer || 0];
    const stride = view.byteStride || n * bytes, base = (view.byteOffset || 0) + (a.byteOffset || 0), out = [];
    for (let i = 0; i < a.count; i++) for (let j = 0; j < n; j++) out.push(buffer[method](base + i * stride + j * bytes));
    return out;
  }
  function localMatrix(node) {
    if (node.matrix) return new THREE.Matrix4().fromArray(node.matrix);
    const t = new THREE.Vector3(...(node.translation || [0, 0, 0]));
    const q = new THREE.Quaternion(...(node.rotation || [0, 0, 0, 1]));
    const s = new THREE.Vector3(...(node.scale || [1, 1, 1]));
    return new THREE.Matrix4().compose(t, q, s);
  }
  const triangles = [];
  function visit(index, parent) {
    const node = gltf.nodes[index], world = parent.clone().multiply(localMatrix(node));
    if (node.mesh !== undefined) for (const primitive of gltf.meshes[node.mesh].primitives) {
      if ((primitive.mode ?? 4) !== 4) continue;
      const positions = accessor(primitive.attributes.POSITION), indices = primitive.indices === undefined
        ? Array.from({ length: positions.length / 3 }, (_, i) => i) : accessor(primitive.indices);
      for (let i = 0; i + 2 < indices.length; i += 3) {
        const points = [indices[i], indices[i + 1], indices[i + 2]].map(k =>
          new THREE.Vector3(positions[k * 3], positions[k * 3 + 1], positions[k * 3 + 2]).applyMatrix4(world));
        const cross = new THREE.Vector3().crossVectors(points[1].clone().sub(points[0]), points[2].clone().sub(points[0]));
        const area = cross.length() / 2; if (area > 1e-8) triangles.push({ points, area, normalY: Math.abs(cross.y) / (cross.length() || 1) });
      }
    }
    for (const child of node.children || []) visit(child, world);
  }
  const identity = new THREE.Matrix4();
  for (const index of gltf.scenes[gltf.scene || 0].nodes) visit(index, identity);
  return triangles;
}

function assetTriangles(relative, placement) {
  const file = path.join(root, 'public', relative.replace(/^\//, ''));
  const triangles = readGltf(file);
  if (!placement) return triangles;
  const matrix = new THREE.Matrix4().makeTranslation(...placement);
  return triangles.map(t => ({ ...t, points: t.points.map(p => p.clone().applyMatrix4(matrix)) }));
}

function pickTriangle(triangles, kind) {
  const candidates = triangles.filter(t => kind === 'roof' ? t.normalY >= 0.72 : t.normalY <= 0.28);
  return candidates.sort((a, b) => b.area - a.area)[0] || null;
}
function rayFor(triangle) {
  const [a, b, c] = triangle.points;
  const normal = new THREE.Vector3().crossVectors(b.clone().sub(a), c.clone().sub(a)).normalize();
  const point = a.clone().add(b).add(c).divideScalar(3);
  return { point, ray: new THREE.Raycaster(point.clone().addScaledVector(normal, 2), normal.negate()) };
}
function triangleMesh(triangle) {
  const geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(triangle.points.flatMap(p => p.toArray()), 3));
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
}
function sourcePick(bundle, object, kind, triangles) {
  const triangle = pickTriangle(triangles, kind);
  if (!triangle) return { kind, status: 'no-candidate-surface' };
  assert.ok(triangle.points.every(p => p.toArray().every(Number.isFinite)), `${bundle.id}/${object.id}/${kind} non-finite triangle ${JSON.stringify(triangle.points.map(p => p.toArray()))}`);
  const mesh = triangleMesh(triangle), body = new THREE.Group();
  body.userData.sourceObjectId = object.id;
  body.userData.sourceRole = object.objectRole;
  body.userData.sourceOwnership = object.ownership;
  body.add(mesh);
  const bundleId = exteriorEntityId(bundle);
  const owner = exteriorSourceOwner(body, bundleId, extra.sourceObjectOwners);
  const expectedRangeOwner = registry.get(bundleId)?.type === 'zone' ? bundleId : null;
  const owners = new Map(); if (owner) { owners.set(body, owner); owners.set(mesh, owner); }
  const result = pickEntity(rayFor(triangle).ray, {
    registry, footprints, buildingDomains: [...named, ...extra.domains], rangeDomains,
    roots: [body], owners, masks: new SpatialMasks(), groundAt: () => 0,
  });
  const expectedEntityId = owner || expectedRangeOwner;
  const unownedSupplement = !expectedEntityId && object.objectRole === 'source-photogrammetry-gap-surface';
  return {
    kind, status: expectedEntityId ? (result?.entityId === expectedEntityId ? 'pass' : (result?.entityId ? 'misassigned' : 'missed-owner')) : (result?.entityId ? (unownedSupplement ? 'unowned-supplement-fallback' : 'misassigned') : 'unassigned-visible-surface'),
    expectedEntityId: expectedEntityId || null, pickedEntityId: result?.entityId || null,
    method: result?.method || null, point: rayFor(triangle).point.toArray().map(v => +v.toFixed(4)),
    triangleAreaM2: +triangle.area.toFixed(4), sourceObjectId: object.id,
  };
}

function currentFormMembers() {
  const rows = [];
  for (const set of ['public/models/current-forms/innovation/manifest.json', 'public/models/current-forms/ivillage-rebuild/manifest.json', 'public/models/current-forms/halls-current/manifest.json']) {
    const manifest = readJson(set), base = path.dirname(set);
    const members = manifest.members || manifest.buildings || [];
    for (const member of members) rows.push({ set, member, asset: path.join(base, manifest.asset?.url || member.url) });
  }
  return rows;
}
function currentPick(row, kind) {
  const tris = readGltf(row.asset);
  const t = pickTriangle(tris, kind); if (!t) return { kind, status: 'no-candidate-surface' };
  const mesh = triangleMesh(t), body = new THREE.Group(); body.userData.entityId = row.member.entityId; body.add(mesh);
  const result = pickEntity(rayFor(t).ray, { registry, footprints, buildingDomains: [...named, ...extra.domains], roots: [body], masks: new SpatialMasks(), groundAt: () => 0 });
  return { kind, status: result?.entityId === row.member.entityId ? 'pass-static-owner' : 'fail', pickedEntityId: result?.entityId || null, method: result?.method || null, point: rayFor(t).point.toArray().map(v => +v.toFixed(4)), triangleAreaM2: +t.area.toFixed(4) };
}

const scopes = new Map();
function ensure(id) { if (!scopes.has(id)) scopes.set(id, { entityId: id, name: registry.get(id)?.name || null, exteriorBundles: [], currentForms: [], domainCount: 0, footprintCount: 0, hires: { patches: 0, highTiles: 0, fineTiles: 0 }, rays: [] }); return scopes.get(id); }
for (const entity of registry.entities.filter(e => e.type === 'building')) ensure(entity.entityId);
const byBundle = [];
for (const bundle of exteriors.bundles) {
  const entityId = exteriorEntityId(bundle), scope = ensure(entityId); scope.exteriorBundles.push(bundle.id);
  const objectResults = [];
  for (const object of bundle.objects) {
    const relative = object.url;
    const file = path.join(root, 'public', 'models/exteriors', relative);
    if (!fs.existsSync(file)) { objectResults.push({ sourceObjectId: object.id, status: 'missing-asset' }); continue; }
    const triangles = assetTriangles(`models/exteriors/${relative}`, object.offset);
    const rays = ['roof', 'facade'].map(kind => sourcePick(bundle, object, kind, triangles));
    objectResults.push({ sourceObjectId: object.id, triangles: triangles.length, objectRole: object.objectRole || null, ownership: object.ownership || null, rays });
    for (const ray of rays) if (ray.status !== 'no-candidate-surface') {
      const finding = { layer: 'exterior', bundleId: bundle.id, ...ray };
      scope.rays.push(finding);
      if (ray.pickedEntityId && ray.pickedEntityId !== entityId) ensure(ray.pickedEntityId).rays.push(finding);
    }
  }
  byBundle.push({ bundleId: bundle.id, entityId, physicalDomainId: bundle.physicalDomainId || null, objectCount: bundle.objects.length, objects: objectResults });
}
for (const domain of [...named, ...extra.domains]) { const s = ensure(domain.entityId); if (s) s.domainCount++; }
for (const fp of footprints) { const id = 'building:' + fp.officialBuildingId, s = scopes.get(id); if (s) s.footprintCount++; }

const currentFormResults = [];
for (const row of currentFormMembers()) {
  const scope = ensure(row.member.entityId); scope.currentForms.push(row.set);
  const rays = ['roof', 'facade'].map(kind => currentPick(row, kind));
  for (const ray of rays) if (ray.status !== 'no-candidate-surface') scope.rays.push({ layer: 'current-form', set: row.set, ...ray });
  currentFormResults.push({ set: row.set, entityId: row.member.entityId, catalogId: row.member.catalogId || null, asset: row.asset.slice(root.length + 1), rays });
}

// Hires are retained native high/fine tiles. Their checked-in descriptors have
// matrices and real GLB assets, but no entity owner. We count them separately;
// assigning them to a nearby building would turn a detail presence claim into
// an unsafe direct-picking claim.
for (const patch of hires.patches) {
  const source = `${patch.sourceAncestor || patch.id}`;
  for (const level of ['high', 'fine']) for (const tile of patch.levels?.[level]?.tiles || []) {
    const matches = [...scopes.values()].filter(s => s.entityId.includes('691adb789d35c25557ecab1f') && source.includes('12-NW-11A-3'));
    for (const s of matches) { s.hires.patches++; s.hires[`${level}Tiles`]++; }
  }
}

for (const s of scopes.values()) {
  const ext = s.rays.filter(r => r.layer === 'exterior'), cf = s.rays.filter(r => r.layer === 'current-form');
  const hasRoof = [...ext, ...cf].some(r => r.kind === 'roof' && (r.status === 'pass' || r.status === 'pass-static-owner'));
  const hasFacade = [...ext, ...cf].some(r => r.kind === 'facade' && (r.status === 'pass' || r.status === 'pass-static-owner'));
  s.coverage = hasRoof && hasFacade ? 'direct-roof-and-facade-ray-proven' : hasRoof || hasFacade ? 'partial-one-surface-ray' : s.currentForms.length ? 'current-form-manifest-only' : s.exteriorBundles.length ? 'no-independent-hit' : 'list-or-registry-only';
  s.flags = [];
  if (!s.exteriorBundles.length) s.flags.push('no-exterior-bundle');
  if (!s.currentForms.length) s.flags.push('no-current-form');
  if (s.domainCount > 1) s.flags.push('multiple-domains-or-shared-scope');
  if (s.coverage === 'no-independent-hit') s.flags.push('missing-visible-geometry-or-owner');
  const entity = registry.get(s.entityId);
  const sharedExterior = entity?.relations?.find(relation => relation.type === 'sharesExteriorWith');
  s.lifecycleStatus = entity?.status || null;
  s.scopeRole = s.coverage !== 'list-or-registry-only'
    ? 'direct-visible-scope'
    : entity?.status === 'construction'
      ? 'construction-or-upcoming-record'
      : sharedExterior
        ? 'named-member-of-shared-physical-domain'
        : 'current-service-name-without-independent-domain';
  if (sharedExterior) s.sharedExteriorWith = sharedExterior.targetId;
}

const listOnlyByRole = Object.fromEntries(
  [...scopes.values()]
    .filter(s => s.coverage === 'list-or-registry-only')
    .reduce((counts, s) => counts.set(s.scopeRole, (counts.get(s.scopeRole) || 0) + 1), new Map()),
);

const report = {
  status: 'audit-complete-with-explicit-gaps', checkedAt: new Date().toISOString(), scope: 'Static local audit only; no 4317 server, browser, or visual acceptance claim.',
  method: 'For every exterior bundle object with a checked-in asset, load real indexed triangles, choose the largest roof-like and facade-like triangle, cast a normal-offset ray, and call app/entity-picking.ts pickEntity with the same domain and source-owner rules. Current-form rays use manifest entityId nodes as the actual runtime owner contract.',
  counts: {
    registryBuildings: registry.entities.filter(e => e.type === 'building').length,
    sharedScopes: [...scopes.values()].filter(s => registry.get(s.entityId)?.type === 'zone').length,
    auditedBuildingOrSharedScopes: [...scopes.values()].length, exteriorBundles: exteriors.bundles.length,
    exteriorObjects: exteriors.bundles.reduce((n, b) => n + b.objects.length, 0),
    exteriorRaySamples: byBundle.reduce((n, b) => n + b.objects.reduce((m, o) => m + (o.rays?.filter(r => r.status !== 'no-candidate-surface').length || 0), 0), 0),
    currentFormMembers: currentFormResults.length, currentFormRaySamples: currentFormResults.reduce((n, r) => n + r.rays.filter(x => x.status !== 'no-candidate-surface').length, 0),
    hiresPatches: hires.patches.length,
    hiresHighTiles: hires.patches.reduce((n, p) => n + (p.levels?.high?.tiles?.length || 0), 0),
    hiresFineTiles: hires.patches.reduce((n, p) => n + (p.levels?.fine?.tiles?.length || 0), 0),
  },
  layerFindings: {
    baselineExterior: 'Real surface rays are audited per exterior object; source-photogrammetry-gap-surface objects intentionally remain unassigned.',
    nativeHighFine: 'Hires high/fine manifest is counted as native detail inventory. Tiles have no safe entity owner in the manifest, so this report does not claim direct building picking for them. Existing source-triangle fixtures separately cover fine rays and named-domain fixtures cover native-individual rays.',
    currentForm: 'Current-form assets are statically ray-tested with the manifest entityId owner; this proves geometry plus owner contract, not browser/runtime loading or visibility.',
  },
  existingFixtureEvidence: fixtureEvidence,
  findings: {
    cannotIndependentlyHit: [...scopes.values()].filter(s => ['list-or-registry-only', 'partial-one-surface-ray', 'no-independent-hit'].includes(s.coverage)).map(s => s.entityId),
    listOnlySelectable: [...scopes.values()].filter(s => s.coverage === 'list-or-registry-only').map(s => s.entityId),
    listOnlyByRole,
    constructionOrUpcomingRecords: [...scopes.values()].filter(s => s.scopeRole === 'construction-or-upcoming-record').map(s => s.entityId),
    namedMembersOfSharedPhysicalDomains: [...scopes.values()].filter(s => s.scopeRole === 'named-member-of-shared-physical-domain').map(s => ({entityId:s.entityId, sharedExteriorWith:s.sharedExteriorWith})),
    currentServiceNamesWithoutIndependentDomain: [...scopes.values()].filter(s => s.scopeRole === 'current-service-name-without-independent-domain').map(s => s.entityId),
    missingVisibleGeometry: [...scopes.values()].filter(s => s.rays.length === 0).map(s => s.entityId),
    misassignedOrUnexpectedRays: [...byBundle.flatMap(b => b.objects.flatMap(o => o.rays || [])), ...currentFormResults.flatMap(r => r.rays)].filter(r => ['misassigned', 'fail'].includes(r.status)),
    unownedSupplementFallbackRays: byBundle.flatMap(b => b.objects.flatMap(o => o.rays || [])).filter(r => r.status === 'unowned-supplement-fallback'),
    unassignedVisibleSurfaceRays: byBundle.flatMap(b => b.objects.flatMap(o => o.rays || [])).filter(r => ['unassigned-visible-surface', 'missed-owner'].includes(r.status)),
    sharedPhysicalEnvelopeDomains: extra.domains.filter(d => d.sharedPhysicalEnvelopeWith).map(d => ({ entityId: d.entityId, sharedPhysicalEnvelopeWith: d.sharedPhysicalEnvelopeWith, physicalDomainId: d.physicalDomainId, rayProof: scopes.get(d.entityId)?.coverage || 'no-independent-hit' })),
    sharedZoneScopes: exteriors.bundles.filter(b => registry.get(exteriorEntityId(b))?.type === 'zone').map(b => ({ bundleId: b.id, entityId: exteriorEntityId(b), physicalDomainId: b.physicalDomainId || null, note: 'One aggregate zone owner; no building subdivision inferred.' })),
  },
  buildings: [...scopes.values()].sort((a, b) => a.entityId.localeCompare(b.entityId)),
  exteriorBundles: byBundle,
  currentFormResults,
  limitations: [
    'Ray candidates are the largest actual triangle meeting a roof/facade normal threshold; they are witnesses, not exhaustive per-pixel coverage.',
    'A pass proves the selected triangle is visible to pickEntity under this static context. It does not prove every facade point, camera angle, occlusion state, or browser gesture.',
    'Shared zone bundles remain one zone scope. This audit does not split a physical shared envelope into invented buildings.',
    'Hires high/fine tiles are not assigned to a building without an explicit owner; their presence cannot be reported as direct pick coverage.',
    'List-only rows are classified by lifecycle and physical role; construction records, named members of one shared physical domain, and unresolved current service names are not interchangeable missing-building claims.',
    'Registry entities with no exterior/current-form geometry remain list-only or reference-only where the evidence says so.',
  ],
  sourceSha256: Object.fromEntries(['app/entity-picking.ts', 'app/source-types.ts', 'public/data/entity-registry.json', 'public/data/building-footprints.json', 'public/data/picking/building-domains.json', 'public/data/picking/building-domains-extra.json', 'public/models/exteriors/manifest.json', 'public/models/hires/manifest.json', ...fixtureEvidence.map(x => x.asset)].map(p => [p, crypto.createHash('sha256').update(fs.readFileSync(path.join(root, p))).digest('hex')])),
};
const out = path.join(root, 'docs/source-evidence-v4/building-quality/all-building-pick-coverage-u68.json');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: report.status, counts: report.counts, coverage: Object.fromEntries([...scopes.values()].reduce((m, s) => m.set(s.coverage, (m.get(s.coverage) || 0) + 1), new Map())), listOnlyByRole }, null, 2));
