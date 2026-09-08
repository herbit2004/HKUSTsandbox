#!/usr/bin/env node
/** Offline contract check for the registered Hall II corridor candidate. */
import {createHash} from 'node:crypto';
import {access, readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

const project = resolve(fileURLToPath(new URL('..', import.meta.url)));
const publicRoot = resolve(project, 'public');
const base = resolve(publicRoot, 'models/current-forms/hall2-corridor');
const entityId = 'space:ug-hall-2-covered-corridor';
const buildingId = '68ec6b9632cc78a7ddf60beb';
const errors = [];
const check = (ok, message) => { if (!ok) errors.push(message); };
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const asset = url => resolve(publicRoot, url.replace(/^\//, ''));

const manifest = await json(resolve(base, 'manifest.json'));
check(manifest.version === 1, 'manifest version must be 1');
check(manifest.members?.length === 1, 'manifest must contain one complete corridor root');
const member = manifest.members?.[0];
check(member?.entityId === entityId, 'manifest entity identity');
check(member?.buildingId === buildingId, 'manifest Hall II association');
check(member?.nodeName === 'UG_Hall_II_Covered_Corridor_Candidate', 'manifest root node name');
check(member?.mask?.pixelSizeMeters === .5, 'candidate projection mask grid');
check(member?.mask?.replacementMinY === 60 && member?.mask?.replacementMaxY === 71.2, 'candidate vertical source guard');
check(manifest.runtime?.currentFormRegion === true && manifest.runtime?.fineOwnerDependency === false, 'candidate must resolve as current-form region without fine-owner dependency');
const candidateReport = await json(resolve(base, 'evidence/candidate-report.json'));
check(candidateReport.runtimeIntegration?.missingFineOwnersAreSeparateFromTerminalDefect === true, 'source audit must separate missing fine owners from terminal roof defect');
check(candidateReport.runtimeIntegration?.fineOwnerDependency === false, 'candidate report must prove no fine-owner dependency');
const glbPath = resolve(base, manifest.asset?.url ?? 'candidate.glb');
const bytes = await readFile(glbPath);
check(bytes.length === manifest.asset?.bytes, 'GLB byte count differs from manifest');
check(hash(bytes) === manifest.asset?.sha256, 'GLB SHA-256 differs from manifest');
check(bytes.subarray(0, 4).toString('ascii') === 'glTF', 'GLB magic');
check(bytes.readUInt32LE(4) === 2 && bytes.readUInt32LE(8) === bytes.length, 'GLB v2 length');
const jsonLength = bytes.readUInt32LE(12);
check(bytes.subarray(16, 20).toString('ascii') === 'JSON', 'GLB JSON chunk');
const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8'));
check(gltf.scenes?.length === 1 && gltf.scenes[0].nodes?.length === 1, 'GLB complete single-root scene');
const rootNode = gltf.nodes?.[gltf.scenes?.[0]?.nodes?.[0]];
check(rootNode?.name === member?.nodeName, 'GLB root node name');
check(rootNode?.extras?.entityId === entityId, 'GLB root entityId');
check(rootNode?.extras?.buildingId === buildingId, 'GLB root buildingId');
const accessor = gltf.accessors?.[0];
check(accessor?.type === 'VEC3' && accessor?.componentType === 5126, 'GLB position accessor');
check(accessor?.count > 0 && accessor?.min?.every(Number.isFinite) && accessor?.max?.every(Number.isFinite), 'finite position bounds');
if (accessor?.min && accessor?.max && member?.bounds) {
  for (let i = 0; i < 3; i++) {
    check(accessor.min[i] >= member.bounds.min[i] - 0.02, `position minimum outside manifest bound ${i}`);
    check(accessor.max[i] <= member.bounds.max[i] + 0.02, `position maximum outside manifest bound ${i}`);
  }
}
check(!gltf.images?.length && !gltf.textures?.length, 'candidate must remain self-contained without external images');
const registry = await json(resolve(publicRoot, 'data/entity-registry.json'));
const entity = registry.entities.find(item => item.entityId === entityId);
check(entity?.type === 'space', 'registry entity type');
check(entity?.parentId === `building:${buildingId}` && entity?.primaryParent === `building:${buildingId}`, 'registry Hall II parent');
const representation = entity?.representations?.find(item => item.id === 'rep:hall2-covered-corridor-current-form');
check(representation?.asset === '/models/current-forms/hall2-corridor/candidate.glb', 'registry asset binding');
check(representation?.sourceManifest === '/models/current-forms/hall2-corridor/manifest.json', 'registry manifest binding');
check(representation?.bounds && JSON.stringify(representation.bounds) === JSON.stringify(member?.bounds), 'registry bounds binding');
check(entity?.notes?.some(note => note.includes('y=60.0')), 'registry source replacement guard');
const maskBytes = await readFile(resolve(base, member?.mask?.url ?? 'replacement.png'));
check(maskBytes.length === member?.mask?.bytes && hash(maskBytes) === member?.mask?.sha256, 'replacement mask integrity');
const sharp = (await import('sharp')).default;
const decoded = await sharp(maskBytes).ensureAlpha().raw().toBuffer({resolveWithObject: true});
check(decoded.info.width === member?.mask?.width && decoded.info.height === member?.mask?.height, 'replacement mask dimensions');
let occupied = 0;
for (let index = 0; index < decoded.data.length; index += 4) if (decoded.data[index] > 127) occupied++;
check(occupied === manifest.runtime?.sourceReplacement?.occupiedPixels && occupied > 1000, 'actual candidate projection mask coverage');
const resourceData = await json(resolve(publicRoot, 'data/entity-resources.json'));
for (const id of ['photo:user-reported-hall2-corridor-gap', 'photo:hall2-corridor-bridge-mid', 'photo:hall2-corridor-bridge-west', 'photo:hall2-corridor-flags', 'document:hall2-corridor-route']) {
  const resource = resourceData.resources.find(item => item.resourceId === id);
  check(!!resource, `missing resource ${id}`);
  check(resource?.bindings?.some(binding => binding.entityId === entityId), `resource not bound to corridor ${id}`);
  if (resource?.asset) {
    try { await access(asset(resource.asset)); }
    catch { check(false, `missing resource asset ${id}`); }
  }
}
// Resolve asynchronous resource existence checks before producing the report.
const report = {
  status: errors.length ? 'fail' : 'pass',
  entityId,
  manifest: '/models/current-forms/hall2-corridor/manifest.json',
  asset: {bytes: bytes.length, sha256: hash(bytes), triangles: 2292},
  surfaces: manifest.geometry?.surfaces,
  sourceReplacement: manifest.runtime?.sourceReplacement,
  offline: true,
  errors,
};
await writeFile(resolve(base, 'evidence/validation.json'), JSON.stringify(report, null, 2) + '\n');
if (errors.length) { console.error(JSON.stringify(report, null, 2)); process.exitCode = 1; }
else console.log(JSON.stringify(report));
