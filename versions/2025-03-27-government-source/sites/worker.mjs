// Sites applies the owner-only access gate before requests reach this Worker.
const MAX_PANORAMA_BYTES = 32 * 1024 * 1024;
const MAX_IMPORT_BYTES = 100 * 1024 * 1024;
const activeCache = new WeakMap();
const validHash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

async function active(env) {
  if (!env.CAMPUS_ASSETS) return null;
  const bucket = env.CAMPUS_ASSETS;
  const cached = activeCache.get(bucket);
  if (cached && cached.expires > Date.now()) return cached.promise;
  const promise = (async () => {
    const value = await bucket.get('active.json');
    return value ? value.json() : null;
  })().catch(error => { activeCache.delete(bucket); throw error; });
  activeCache.set(bucket, {promise, expires: Date.now() + 5000});
  return promise;
}

function byteRange(value, size) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(value);
  if (!match || (!match[1] && !match[2])) return null;
  const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
  const end = match[1] && match[2] ? Math.min(size - 1, Number(match[2])) : size - 1;
  return Number.isSafeInteger(start) && Number.isSafeInteger(end) && start >= 0 && start <= end && start < size
    ? [start, end] : null;
}

async function runtimeAsset(request, env) {
  const manifest = await active(env);
  const path = decodeURIComponent(new URL(request.url).pathname);
  const entry = manifest?.routes?.[path];
  if (!entry) return manifest ? new Response('Not found', {status: 404}) : env.ASSETS.fetch(request);
  const etag = '"' + entry.sha256 + '"';
  const headers = new Headers({'Content-Type': entry.contentType, 'ETag': etag, 'Accept-Ranges': 'bytes',
    'Cache-Control': path.startsWith('/_next/static/') ? 'private,max-age=31536000,immutable' : 'private,no-cache',
    'X-Content-Type-Options': 'nosniff'});
  if (request.headers.get('If-None-Match') === etag) return new Response(null, {status: 304, headers});
  let start = 0, end = entry.bytes - 1, status = 200;
  const range = request.headers.get('Range');
  if (range && (!request.headers.has('If-Range') || request.headers.get('If-Range') === etag)) {
    const selected = byteRange(range, entry.bytes);
    if (!selected) return new Response(null, {status: 416, headers: {'Content-Range': 'bytes */' + entry.bytes}});
    [start, end] = selected;
    status = 206;
    headers.set('Content-Range', 'bytes ' + start + '-' + end + '/' + entry.bytes);
  }
  headers.set('Content-Length', String(end - start + 1));
  if (request.method === 'HEAD') return new Response(null, {status, headers});
  const object = await env.CAMPUS_ASSETS.get('blobs/' + entry.sha256, status === 206 ? {range: {offset: start, length: end - start + 1}} : undefined);
  if (!object) return new Response('Missing campus resource', {status: 503});
  return new Response(object.body, {status, headers});
}

async function* boundedBody(body) {
  const reader = body.getReader();
  let bytes = 0;
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) return;
      bytes += value.byteLength;
      if (bytes > MAX_PANORAMA_BYTES) throw new Error('Oversized panorama');
      yield value;
    }
  } finally { await reader.cancel().catch(() => {}); }
}

function responseStream(iterator) {
  return new ReadableStream({
    async pull(controller) {
      try {
        const result = await iterator.next();
        if (result.done) controller.close(); else controller.enqueue(result.value);
      } catch (error) { controller.error(error); }
    },
    async cancel() { await iterator.return?.(); },
  });
}

async function importRequest(request, env, path) {
  if (!env.HKUST_SITE_IMPORT_TOKEN || request.headers.get('X-HKUST-Import-Token') !== env.HKUST_SITE_IMPORT_TOKEN)
    return new Response('Not found', {status: 404});
  if (!env.CAMPUS_ASSETS) return new Response('Storage unavailable', {status: 503});
  if (path === '/_sites/import/check' && request.method === 'POST') {
    const files = await request.json();
    if (!Array.isArray(files) || files.length > 32 || files.some(f => !validHash(f.sha256) || !Number.isSafeInteger(f.bytes) || f.bytes < 0 || f.bytes > MAX_IMPORT_BYTES))
      return new Response('Invalid inventory', {status: 400});
    const missing = [];
    for (const file of files) {
      const object = await env.CAMPUS_ASSETS.head('blobs/' + file.sha256);
      if (!object || object.size !== file.bytes) missing.push(file.sha256);
    }
    return Response.json({missing});
  }
  if (path.startsWith('/_sites/import/blob/') && request.method === 'PUT') {
    const sha256 = path.slice('/_sites/import/blob/'.length);
    const bytes = Number(request.headers.get('X-Asset-Bytes'));
    if (!validHash(sha256) || !Number.isSafeInteger(bytes) || bytes < 0 || bytes > MAX_IMPORT_BYTES || (bytes > 0 && !request.body))
      return new Response('Invalid asset', {status: 400});
    const body = bytes === 0 ? new Uint8Array(0) : typeof FixedLengthStream === 'function' ? request.body.pipeThrough(new FixedLengthStream(bytes)) : request.body;
    const object = await env.CAMPUS_ASSETS.put('blobs/' + sha256, body, {sha256});
    if (!object || object.size !== bytes) return new Response('Asset verification failed', {status: 422});
    return Response.json({sha256, bytes: object.size});
  }
  if (path === '/_sites/import/activate' && request.method === 'PUT') {
    const text = await request.text();
    if (text.length > 4 * 1024 * 1024) return new Response('Manifest too large', {status: 413});
    const manifest = JSON.parse(text);
    const routes = Object.entries(manifest.routes || {});
    if (manifest.profile !== 'full-local' || !validHash(manifest.release) || !routes.length || routes.length > 20000 ||
        !manifest.routes['/'] || !manifest.routes['/data/dataset-profile.json'] ||
        routes.some(([name, f]) => !name.startsWith('/') || name.includes('..') || name.startsWith('/_sites/import') ||
          !validHash(f.sha256) || !Number.isSafeInteger(f.bytes) || f.bytes < 0 || typeof f.contentType !== 'string' || /[\r\n]/.test(f.contentType)))
      return new Response('Invalid release', {status: 400});
    // The importer verifies every blob in bounded batches before this atomic pointer change.
    await env.CAMPUS_ASSETS.put('releases/' + manifest.release + '.json', text);
    await env.CAMPUS_ASSETS.put('active.json', text);
    activeCache.delete(env.CAMPUS_ASSETS);
    return Response.json({release: manifest.release, profile: manifest.profile, routes: routes.length});
  }
  return new Response('Not found', {status: 404});
}

export function createWorker(fetchUpstream = fetch) {
  return {async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith('/_sites/import/')) return await importRequest(request, env, url.pathname);
      if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405, headers: {Allow: 'GET, HEAD'}});
      if (url.pathname === '/api/panorama') {
        if (request.method !== 'GET') return new Response(null, {status: 405, headers: {Allow: 'GET'}});
        const dataResponse = await runtimeAsset(new Request(new URL('/data/panoramas-online.json', request.url)), env);
        if (!dataResponse.ok) throw new Error('Missing panorama index');
        const data = await dataResponse.json();
        const id = url.searchParams.get('id');
        if (!data.nodes.some(node => node.asset_id === id)) return new Response('Unknown panorama', {status: 404});
        const response = await fetchUpstream('https://navigate.ust.hk/path/api/app/assets/panorama/id?id=' + encodeURIComponent(id), {signal: AbortSignal.timeout(40000)});
        const type = response.headers.get('Content-Type') || '';
        const length = Number(response.headers.get('Content-Length') || 0);
        if (!response.ok || !type.startsWith('image/') || length > MAX_PANORAMA_BYTES || !response.body) {
          await response.body?.cancel();
          return new Response('Official panorama unavailable', {status: 502});
        }
        return new Response(responseStream(boundedBody(response.body)), {headers: {'Content-Type': type, 'Cache-Control': 'private,max-age=86400', 'X-Content-Type-Options': 'nosniff'}});
      }
      return await runtimeAsset(request, env);
    } catch {
      return new Response('Resource temporarily unavailable', {status: 502});
    }
  }};
}

export default createWorker();
