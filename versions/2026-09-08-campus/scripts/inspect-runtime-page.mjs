const port = Number(process.env.HKUST_CDP_PORT || 9222);
const base = process.env.HKUST_RUNTIME_URL || 'http://127.0.0.1:4319/';
const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = pages.find((item) => item.type === 'page' && item.url.startsWith(base));
if (!page) throw new Error(`No ${base} page on ${port}`);
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
let id = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data));
  if (message.id && pending.has(message.id)) {
    const target = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) target.reject(message.error);
    else target.resolve(message.result);
  }
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const next = ++id;
  pending.set(next, { resolve, reject });
  socket.send(JSON.stringify({ id: next, method, params }));
});
const result = await send('Runtime.evaluate', {
  expression: `({
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    body: document.body?.innerText?.slice(0, 4000),
    canvas: [...document.querySelectorAll('canvas')].map(c => ({width:c.width,height:c.height})),
    world: document.querySelector('.atlas-world')?.dataset.sceneState || null,
    webgl2: !!document.createElement('canvas').getContext('webgl2'),
  })`,
  returnByValue: true,
});
console.log(JSON.stringify(result.result.value, null, 2));
socket.close();
