// Sites provides the owner-only access gate. This Worker preserves local asset URLs.
const MAX_PANORAMA_BYTES = 32 * 1024 * 1024;
const indexes = new WeakMap();

async function index(env, key, path) {
  let cache = indexes.get(env.ASSETS);
  if (!cache) indexes.set(env.ASSETS, cache = new Map());
  if (!cache.has(key)) cache.set(key, (async () => {
    const response = await env.ASSETS.fetch(new Request('https://assets.internal' + path));
    if (!response.ok) throw new Error('Missing runtime index');
    return response.json();
  })().catch(error => { cache.delete(key); throw error; }));
  return cache.get(key);
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

function byteRange(value, size) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(value);
  if (!match || (!match[1] && !match[2])) return null;
  const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
  const end = match[1] && match[2] ? Math.min(size - 1, Number(match[2])) : size - 1;
  return Number.isSafeInteger(start) && Number.isSafeInteger(end) && start >= 0 && start <= end && start < size
    ? [start, end] : null;
}

async function* assetBytes(env, entry, start, end) {
  let position = 0;
  for (const part of entry.parts) {
    const partStart = position;
    position += part.bytes;
    if (position <= start || partStart > end) continue;
    const response = await env.ASSETS.fetch(new Request('https://assets.internal' + part.url));
    if (!response.ok || !response.body) throw new Error('Missing model segment');
    const reader = response.body.getReader();
    let offset = partStart;
    try {
      while (offset <= end) {
        const {value, done} = await reader.read();
        if (done) {
          if (offset < Math.min(position, end + 1)) throw new Error('Truncated model segment');
          break;
        }
        const from = Math.max(0, start - offset);
        const to = Math.min(value.byteLength, end + 1 - offset);
        if (to > from) yield value.subarray(from, to);
        offset += value.byteLength;
      }
    } finally { await reader.cancel().catch(() => {}); }
  }
}

function largeAsset(request, env, entry) {
  const etag = '"' + entry.sha256 + '"';
  const headers = new Headers({'Content-Type': entry.contentType, 'ETag': etag,
    'Accept-Ranges': 'bytes', 'Cache-Control': 'private,max-age=3600', 'X-Content-Type-Options': 'nosniff'});
  if (request.headers.get('If-None-Match') === etag) return new Response(null, {status: 304, headers});
  let start = 0, end = entry.bytes - 1, status = 200;
  const range = request.headers.get('Range');
  if (range && (!request.headers.has('If-Range') || request.headers.get('If-Range') === etag)) {
    const selected = byteRange(range, entry.bytes);
    if (!selected) {
      headers.set('Content-Range', 'bytes */' + entry.bytes);
      return new Response(null, {status: 416, headers});
    }
    [start, end] = selected;
    status = 206;
    headers.set('Content-Range', `bytes ${start}-${end}/${entry.bytes}`);
  }
  headers.set('Content-Length', String(end - start + 1));
  return new Response(request.method === 'HEAD' ? null : responseStream(assetBytes(env, entry, start, end)), {status, headers});
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

export function createWorker(fetchUpstream = fetch) {
  return {async fetch(request, env) {
    const url = new URL(request.url);
    if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405, headers: {Allow: 'GET, HEAD'}});
    try {
      if (url.pathname === '/api/panorama') {
        if (request.method !== 'GET') return new Response(null, {status: 405, headers: {Allow: 'GET'}});
        const data = await index(env, 'panoramas', '/data/panoramas-online.json');
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
      const manifest = await index(env, 'large-assets', '/_sites/large-assets.json');
      const entry = manifest[decodeURIComponent(url.pathname)];
      if (entry) return largeAsset(request, env, entry);
      return env.ASSETS.fetch(request);
    } catch {
      return new Response('Resource temporarily unavailable', {status: 502});
    }
  }};
}

export default createWorker();
