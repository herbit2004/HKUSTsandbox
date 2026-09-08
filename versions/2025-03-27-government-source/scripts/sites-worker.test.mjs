import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {test} from 'node:test';
import {createWorker} from '../sites/worker.mjs';

function fixture() {
  const body = 'abcdefghij';
  const sha256 = createHash('sha256').update(body).digest('hex');
  const blobs = new Map();
  const routes = {};
  for (const [path, value] of Object.entries({'/model.glb':body, '/data/panoramas-online.json':JSON.stringify({nodes:[{asset_id:'allowed-id'}]}), '/':'<html>HKUST</html>'})) {
    const hash=createHash('sha256').update(value).digest('hex');
    blobs.set('blobs/'+hash,Buffer.from(value));
    routes[path]={bytes:Buffer.byteLength(value),sha256:hash,contentType:path.endsWith('.glb')?'model/gltf-binary':'application/json'};
  }
  blobs.set('active.json',Buffer.from(JSON.stringify({routes})));
  const bucket={
    async head(key){const b=blobs.get(key);return b?{size:b.length}:null;},
    async get(key,options){const b=blobs.get(key);if(!b)return null;const r=options?.range;
      return {size:b.length,json:async()=>JSON.parse(b),body:new Response(r?b.subarray(r.offset,r.offset+r.length):b).body};},
    async put(key,body,options){const b=Buffer.from(await new Response(body).arrayBuffer());
      if(options?.sha256 && createHash('sha256').update(b).digest('hex')!==options.sha256)throw new Error('Checksum mismatch');
      blobs.set(key,b);return {size:b.length};},
  };
  return {sha256,blobs,env:{CAMPUS_ASSETS:bucket,ASSETS:{fetch:async()=>new Response('fallback')}}};
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

test('ranges, suffixes, HEAD, ETag and unsatisfiable ranges', async () => {
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

test('import authorization, verified writes and atomic activation', async()=>{
  const {env,blobs}=fixture();const worker=createWorker();
  const req=(path,method,body,extra={})=>worker.fetch(new Request('https://campus.test/_sites/import/'+path,{method,body,headers:{'X-HKUST-Import-Token':'test-only',...extra}}),env);
  assert.equal((await req('check','POST','[]')).status,404);
  env.HKUST_SITE_IMPORT_TOKEN='test-only';
  const text='replacement';const sha256=createHash('sha256').update(text).digest('hex');
  const item={sha256,bytes:11,contentType:'text/plain'};
  assert.deepEqual(await (await req('check','POST',JSON.stringify([item]))).json(),{missing:[sha256]});
  assert.equal((await req('blob/'+sha256,'PUT','wrong',{'X-Asset-Bytes':'5'})).status,502);
  assert.equal(blobs.has('blobs/'+sha256),false);
  assert.equal((await req('blob/'+sha256,'PUT',text,{'X-Asset-Bytes':'11'})).status,200);
  assert.deepEqual(await (await req('check','POST',JSON.stringify([item]))).json(),{missing:[]});
  const release={profile:'full-local',release:'a'.repeat(64),routes:{'/':item,'/data/dataset-profile.json':item}};
  assert.equal(await (await worker.fetch(new Request('https://campus.test/'),env)).text(),'<html>HKUST</html>');
  assert.equal((await req('activate','PUT',JSON.stringify(release))).status,200);
  assert.equal(await (await worker.fetch(new Request('https://campus.test/'),env)).text(),text);
  assert.equal((await worker.fetch(new Request('https://campus.test/old-only'),env)).status,404);
  delete env.HKUST_SITE_IMPORT_TOKEN;
  assert.equal((await req('activate','PUT',JSON.stringify(release))).status,404);
});
