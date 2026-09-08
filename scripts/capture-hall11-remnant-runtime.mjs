import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = Number(process.env.HKUST_CDP_PORT || 9222);
const base = process.env.HKUST_RUNTIME_URL || 'http://127.0.0.1:4319/';
const quality = process.env.HKUST_QUALITY || 'ultra';
const searchQuery = process.env.HKUST_SEARCH_QUERY || '本科生宿舍11座';
const entityLabel = process.env.HKUST_ENTITY_LABEL || searchQuery;
const requiredCurrentFormPackage = Object.hasOwn(process.env, 'HKUST_REQUIRED_CURRENT_FORM_PACKAGE')
  ? process.env.HKUST_REQUIRED_CURRENT_FORM_PACKAGE
  : '/models/current-forms/ivillage-rebuild/';
const outputName = process.env.HKUST_CAPTURE_NAME || 'u69-hall11-remnant-candidate';
const reportName = process.env.HKUST_REPORT_NAME || 'hall11-runtime-u69.json';
const output = path.join(root, 'docs/screenshots/v4', outputName);
const reportPath = path.join(root, 'docs/source-evidence-v4/ivillage-remnants', reportName);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = pages.find(
  (item) => item.type === 'page' && item.url.startsWith(base),
);
if (!page) throw new Error(`No ${base} page on CDP port ${port}`);
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
let nextId = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data));
  if (!message.id || !pending.has(message.id)) return;
  const target = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) target.reject(new Error(JSON.stringify(message.error)));
  else target.resolve(message.result);
});
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
    userGesture: true,
  });
  if (result.exceptionDetails)
    throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const sceneState = () =>
  evaluate(
    `(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()`,
  );

const waitForDetailSettle = async (label, timeoutMs = 120000) => {
  const started = Date.now();
  let stableSince = 0;
  let latest = null;
  while (Date.now() - started < timeoutMs) {
    latest = await sceneState();
    const meshBusy = Boolean(latest?.meshDetail?.loading);
    const exteriorBusy = Boolean(latest?.exterior?.loading);
    const currentFormsReady = !requiredCurrentFormPackage || latest?.currentFormResidency?.packages
      ?.find((item) => item.id === requiredCurrentFormPackage)
      ?.state === 'resident';
    if (!meshBusy && !exteriorBusy && currentFormsReady) {
      if (!stableSince) stableSince = Date.now();
      if (Date.now() - stableSince >= 5000)
        return { ok: true, label, waitedMs: Date.now() - started, state: latest };
    } else stableSince = 0;
    await sleep(1000);
  }
  return { ok: false, label, waitedMs: Date.now() - started, state: latest };
};

await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  // Match the measured canvas viewport of the prior U68 Hall XI evidence.
  height: 857,
  deviceScaleFactor: 1,
  mobile: false,
});
await fs.mkdir(output, { recursive: true });
await evaluate(
  `localStorage.setItem('hkust-map-locale','zh-Hans');localStorage.setItem('hkust-map-quality',${JSON.stringify(quality)});location.reload();true`,
);
await sleep(12000);
const chosen = await evaluate(`(async()=>{
  const input=document.querySelector('input[aria-label="搜索校园实体"]');
  if(!input)return {ok:false,error:'search-input-missing'};
  const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
  setter.call(input,${JSON.stringify(searchQuery)});input.dispatchEvent(new Event('input',{bubbles:true}));
  await new Promise(r=>setTimeout(r,700));
  const buttons=[...document.querySelectorAll('.entity-results>button')];
  const button=buttons.find(b=>(b.querySelector('strong')?.textContent||'').includes(${JSON.stringify(entityLabel)}));
  if(!button)return {ok:false,error:'result-missing'};
  button.click();return {ok:true,label:button.querySelector('strong')?.textContent||''};
})()`);
if (!chosen.ok) throw new Error(JSON.stringify(chosen));
await sleep(5000);
const wideSettle = await waitForDetailSettle('wide');
const wide = wideSettle.state;
const wideShot = await send('Page.captureScreenshot', {
  format: 'png',
  captureBeyondViewport: false,
});
await fs.writeFile(
  path.join(output, 'wide.png'),
  Buffer.from(wideShot.data, 'base64'),
);
for (let i = 0; i < 4; i++) {
  await send('Input.dispatchMouseEvent', {
    type: 'mouseWheel',
    x: 900,
    y: 500,
    deltaX: 0,
    deltaY: -400,
  });
  await sleep(150);
}
const transitionFrames = [];
let previousTransitionMs = 0;
for (const atMs of [0, 500, 1500, 3000, 6000]) {
  await sleep(atMs - previousTransitionMs);
  previousTransitionMs = atMs;
  const state = await sceneState();
  const shot = await send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  });
  const screenshot = `docs/screenshots/v4/${outputName}/transition-${atMs}ms.png`;
  await fs.writeFile(
    path.join(output, `transition-${atMs}ms.png`),
    Buffer.from(shot.data, 'base64'),
  );
  transitionFrames.push({
    atMs,
    screenshot,
    camera: state?.camera,
    target: state?.target,
    meshDetail: state?.meshDetail,
    exterior: state?.exterior,
  });
}
const closeSettle = await waitForDetailSettle('close');
const settled = closeSettle.state;
const closeShot = await send('Page.captureScreenshot', {
  format: 'png',
  captureBeyondViewport: false,
});
await fs.writeFile(
  path.join(output, 'close.png'),
  Buffer.from(closeShot.data, 'base64'),
);
await send('Input.dispatchMouseEvent', {
  type: 'mousePressed',
  x: 900,
  y: 500,
  button: 'left',
  buttons: 1,
  clickCount: 1,
});
for (const x of [940, 980, 1020, 1060, 1100, 1140]) {
  await send('Input.dispatchMouseEvent', {
    type: 'mouseMoved',
    x,
    y: 500,
    button: 'left',
    buttons: 1,
  });
  await sleep(50);
}
await send('Input.dispatchMouseEvent', {
  type: 'mouseReleased',
  x: 1140,
  y: 500,
  button: 'left',
  buttons: 0,
  clickCount: 1,
});
const secondAngleSettle = await waitForDetailSettle('second-angle');
const secondAngle = secondAngleSettle.state;
const secondShot = await send('Page.captureScreenshot', {
  format: 'png',
  captureBeyondViewport: false,
});
await fs.writeFile(
  path.join(output, 'second-angle.png'),
  Buffer.from(secondShot.data, 'base64'),
);
const logs = await send('Runtime.evaluate', {
  expression: `({title:document.title,status:document.querySelector('.world-status')?.textContent||''})`,
  returnByValue: true,
});
const report = {
  status: 'captured',
  checkedAt: new Date().toISOString(),
  runtime: base,
  viewport: { width: 1440, height: 857, deviceScaleFactor: 1 },
  requestedQuality: quality,
  chosen,
  settle: { wide: wideSettle, close: closeSettle, secondAngle: secondAngleSettle },
  transitionFrames,
  screenshots: {
    wide: `docs/screenshots/v4/${outputName}/wide.png`,
    close: `docs/screenshots/v4/${outputName}/close.png`,
    secondAngle: `docs/screenshots/v4/${outputName}/second-angle.png`,
  },
  wide,
  settled,
  secondAngle,
  ui: logs.result.value,
  limitations: [
    'The fixed production selection and wheel route reproduces the prior Hall XI QA pose; visual acceptance must still compare the screenshot itself.',
  ],
};
await fs.mkdir(path.dirname(reportPath), { recursive: true });
await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: report.status, camera: settled?.camera, target: settled?.target, screenshot: report.screenshots.close }));
socket.close();
