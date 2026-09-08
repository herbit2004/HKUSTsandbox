// Read-only checks. Pass an existing Sites access token through the process environment.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

const origin = process.argv[2];
if (!origin || !process.env.HKUST_SITES_CHECK_TOKEN) throw new Error('Expected Site origin and existing access token in environment.');
const headers = {'OAI-Sites-Authorization': 'Bearer ' + process.env.HKUST_SITES_CHECK_TOKEN};
const local = JSON.parse(fs.readFileSync(new URL('../out/runtime/_sites/runtime-integrity.json', import.meta.url)));
async function get(path, extra = {}) {
  const response = await fetch(new URL(path, origin), {headers: {...headers, ...extra}, redirect: 'error', signal: AbortSignal.timeout(180000)});
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response;
}
const remote = await (await get('/_sites/runtime-integrity.json')).json();
assert.equal(JSON.stringify(remote), JSON.stringify(local), 'Published integrity index differs from build');
assert.equal(remote.profile, 'full-local');
const html = await (await get('/')).text();
assert.ok(html.includes('data-dataset-profile="full-local"'), 'Page is not the full-local build');
const paths = [
  'data/dataset-profile.json', 'data/entity-registry.json', 'data/panoramas-online.json',
  'interiors/manifest.json', 'models/exteriors/manifest.json', 'models/hires/manifest.json',
  'models/current-forms/ivillage-rebuild/ivillage-x-xiii-v1.glb',
  'models/current-forms/innovation/innovation-photo-closed.glb',
  'terrain/terrain.glb', 'brand/hkust-university-emblem-blue-gold.png',
];
for (const prefix of ['photos/', 'maps/', 'interiors/', 'panoramas/']) {
  const name = Object.keys(local.files).find(name => name.startsWith(prefix) && /\.(jpg|png|bin)$/.test(name));
  if (name) paths.push(name);
}
const verified = [];
for (const path of paths) {
  assert.ok(local.files[path], 'Missing expected local resource: ' + path);
  const response = await get('/' + path);
  const hash = createHash('sha256');
  let bytes = 0;
  for await (const chunk of response.body) { hash.update(chunk); bytes += chunk.byteLength; }
  const sha256 = hash.digest('hex');
  assert.equal(bytes, local.files[path].bytes, path + ' size');
  assert.equal(sha256, local.files[path].sha256, path + ' bytes');
  verified.push({path, bytes, sha256});
  console.log('Verified ' + path + ' (' + bytes + ' bytes)');
}
const nodes = JSON.parse(fs.readFileSync(new URL('../out/runtime/data/panoramas-online.json', import.meta.url))).nodes;
const missing = await fetch(new URL('/api/panorama?id=unknown-validation-id', origin), {headers});
assert.equal(missing.status, 404);
let panorama = 'no nodes';
if (nodes.length) {
  const response = await get('/api/panorama?id=' + encodeURIComponent(nodes[0].asset_id));
  assert.ok(response.headers.get('Content-Type')?.startsWith('image/'));
  let bytes = 0;
  for await (const chunk of response.body) bytes += chunk.byteLength;
  assert.ok(bytes > 0 && bytes <= 32 * 1024 * 1024);
  panorama = {status: response.status, bytes};
}
const report = {origin, profile: remote.profile, integrityEntries: Object.keys(remote.files).length, verified, panorama, checkedAt: new Date().toISOString()};
fs.writeFileSync(new URL('../.local/sites-live-validation.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({profile: report.profile, resourcesVerified: verified.length, panorama}));
