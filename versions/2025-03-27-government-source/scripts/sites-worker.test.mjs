import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {test} from 'node:test';
import {createWorker} from '../sites/worker.mjs';

function fixture() {
  const body = 'abcdefghij';
  const sha256 = createHash('sha256').update(body).digest('hex');
  const files = new Map([
    ['/_sites/large-assets.json', JSON.stringify({'/model.glb': {bytes: 10, sha256, contentType: 'model/gltf-binary', parts: [{url: '/a', bytes: 6}, {url: '/b', bytes: 4}]}})],
    ['/data/panoramas-online.json', JSON.stringify({nodes: [{asset_id: 'allowed-id'}]})],
    ['/a', 'abcdef'], ['/b', 'ghij'], ['/', '<html>HKUST</html>'],
  ]);
  const env = {ASSETS: {async fetch(request) {
    const value = files.get(new URL(request.url).pathname);
    return new Response(value ?? 'Not found', {status: value === undefined ? 404 : 200});
  }}};
  return {env, sha256};
}

test('streaming restores exact bytes, type and length', async () => {
  const {env, sha256} = fixture();
  const worker = createWorker();
  const response = await worker.fetch(new Request('https://campus.test/model.glb'), env);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Content-Length'), '10');
  assert.equal(response.headers.get('Content-Type'), 'model/gltf-binary');
  assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'), sha256);
});

test('ranges across segments, suffixes, HEAD, ETag and unsatisfiable ranges', async () => {
  const {env, sha256} = fixture();
  const worker = createWorker();
  const request = (headers, method = 'GET') => worker.fetch(new Request('https://campus.test/model.glb', {headers, method}), env);
  const range = await request({Range: 'bytes=2-7'});
  assert.equal(range.status, 206);
  assert.equal(range.headers.get('Content-Range'), 'bytes 2-7/10');
  assert.equal(await range.text(), 'cdefgh');
  assert.equal(await (await request({Range: 'bytes=-4'})).text(), 'ghij');
  assert.equal((await request({Range: 'bytes=20-30'})).status, 416);
  assert.equal((await request({'If-None-Match': '"' + sha256 + '"'})).status, 304);
  const head = await request({}, 'HEAD');
  assert.equal(head.body, null);
  assert.equal(head.headers.get('Content-Length'), '10');
});

test('only allowlisted panorama IDs reach the fixed upstream', async () => {
  const {env} = fixture();
  const calls = [];
  const worker = createWorker(async url => { calls.push(url); return new Response('image-bytes', {headers: {'Content-Type': 'image/jpeg'}}); });
  assert.equal((await worker.fetch(new Request('https://campus.test/api/panorama?id=unknown'), env)).status, 404);
  assert.equal(calls.length, 0);
  const response = await worker.fetch(new Request('https://campus.test/api/panorama?id=allowed-id'), env);
  assert.equal(await response.text(), 'image-bytes');
  assert.equal(calls[0], 'https://navigate.ust.hk/path/api/app/assets/panorama/id?id=allowed-id');
  assert.equal((await worker.fetch(new Request('https://campus.test/', {method: 'POST'}), env)).status, 405);
});

test('rejects non-image and oversized panorama responses', async () => {
  for (const headers of [{'Content-Type': 'text/html'}, {'Content-Type': 'image/jpeg', 'Content-Length': String(33 * 1024 * 1024)}]) {
    const {env} = fixture();
    const worker = createWorker(async () => new Response('bad', {headers}));
    assert.equal((await worker.fetch(new Request('https://campus.test/api/panorama?id=allowed-id'), env)).status, 502);
  }
});
