// Real browser acceptance for the fixed runtime page.
// Connects to an already running Chrome CDP tab; it never starts or republishes 4317.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cdpPort = Number(process.env.HKUST_CDP_PORT || 9222);
const runtimeUrl = process.env.HKUST_RUNTIME_URL || 'http://127.0.0.1:4317/';
const reportPath = process.env.HKUST_BROWSER_QA_REPORT ||
  path.join(root, 'docs/source-evidence-v4/building-quality/fixed-page-browser-qa.json');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const tabs = await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json();
const tab = tabs.find((item) => item.type === 'page' && item.url.startsWith(runtimeUrl));
if (!tab) {
  throw new Error(`No existing CDP page starts with ${runtimeUrl}; start the fixed page separately, then rerun.`);
}

const socket = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
let nextId = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data));
  if (!message.id || !pending.has(message.id)) return;
  const request = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) request.reject(new Error(JSON.stringify(message.error)));
  else request.resolve(message.result);
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
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
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const sceneState = () => evaluate(`(() => {
  try { return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState || 'null'); }
  catch { return null; }
})()`);
const pickState = () => evaluate(`(() => {
  try { return JSON.parse(document.querySelector('.atlas-world')?.dataset.pickState || 'null'); }
  catch { return null; }
})()`);
const waitFor = async (predicate, timeoutMs, label) => {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const value = await predicate();
    if (value) return value;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${label}`);
};

async function searchAndChoose(query, expectedName = query) {
  return evaluate(`(async () => {
    const input = document.querySelector('input[aria-label="搜索校园实体"]');
    if (!input) return { ok: false, error: 'search-input-missing' };
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(query)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 600));
    const buttons = [...document.querySelectorAll('.entity-results > button')];
    const button = buttons.find((item) =>
      (item.querySelector('strong')?.textContent || '').trim() === ${JSON.stringify(expectedName)}
    );
    if (!button) return { ok: false, error: 'result-missing', results: buttons.map((item) => item.querySelector('strong')?.textContent || '') };
    button.click();
    return { ok: true, label: button.querySelector('strong')?.textContent || '' };
  })()`);
}

const report = {
  status: 'pending',
  checkedAt: new Date().toISOString(),
  runtime: runtimeUrl,
  tab: { url: tab.url, title: tab.title },
  method: 'Existing Chrome WebGL tab over CDP; production search UI and a real canvas pointer click. No server start, reload, publish, or asset mutation.',
  checks: [],
};

try {
  const initial = await evaluate(`({ href: location.href, readyState: document.readyState, title: document.title })`);
  assert.equal(initial.href.startsWith(runtimeUrl), true);
  await waitFor(async () => {
    const state = await sceneState();
    return state && state.total > 0 && state.loaded === state.total && !state.loadingFloor;
  }, 30000, 'initial campus scene');

  const chosenLo = await searchAndChoose('罗桂祥楼');
  assert.equal(chosenLo.ok, true, JSON.stringify(chosenLo));
  await waitFor(async () => (await evaluate(`document.querySelector('.entity-card h2')?.textContent?.trim() === '罗桂祥楼'`)), 10000, 'Lo Kwee-Seong card');
  const loUi = await evaluate(`({
    card: document.querySelector('.entity-card')?.innerText || '',
    breadcrumb: [...document.querySelectorAll('.entity-card .entity-breadcrumb')].map((node) => node.innerText).join(' '),
    selected: document.querySelector('.entity-card h2')?.textContent?.trim() || '',
  })`);
  const loData = await evaluate(`(async () => {
    const [registry, exteriors, ...currentForms] = await Promise.all([
      fetch('/data/entity-registry.json').then((response) => response.json()),
      fetch('/models/exteriors/manifest.json').then((response) => response.json()),
      ...['innovation', 'ivillage-rebuild', 'halls-current', 'hall2-corridor'].map((name) => fetch('/models/current-forms/' + name + '/manifest.json').then((response) => response.ok ? response.json() : null)),
    ]);
    const entity = registry.entities.find((item) => item.entityId === 'space:catalog:campus-14');
    const exteriorOwners = (exteriors.bundles || []).map((bundle) => bundle.entityId || bundle.catalogId);
    const currentOwners = currentForms.flatMap((manifest) => (manifest?.buildings || []).map((item) => item.entityId || item.catalogId));
    return { entity, exteriorOwners, currentOwners };
  })()`);
  assert.equal(loUi.selected, '罗桂祥楼');
  assert.match(loUi.breadcrumb, /主学术大楼/);
  assert.match(loUi.card, /位置尚未确定/);
  assert.equal(loData.entity?.parentId, 'building:b00000000000000000000001');
  const independentRepresentations = (loData.entity?.representations || []).filter((representation) =>
    representation.type === 'mesh_group' || /current[_-]?form/i.test(representation.subtype || '')
  );
  assert.deepEqual(independentRepresentations, []);
  assert.equal(loData.exteriorOwners.includes('space:catalog:campus-14'), false);
  assert.equal(loData.currentOwners.includes('space:catalog:campus-14'), false);
  report.checks.push({
    name: 'Lo Kwee-Seong search shows Academic Building ownership and no independent exterior/current form',
    status: 'pass',
    ui: loUi,
    entity: { entityId: loData.entity.entityId, parentId: loData.entity.parentId, representationTypes: (loData.entity.representations || []).map((representation) => representation.type) },
    independentExterior: false,
    independentCurrentForm: false,
  });

  const chosenHall = await searchAndChoose('本科生宿舍8座');
  assert.equal(chosenHall.ok, true, JSON.stringify(chosenHall));
  await evaluate(`(() => {
    document.querySelector('button[aria-label="清除搜索"]')?.click();
    return document.querySelector('input[aria-label="搜索校园实体"]')?.value || '';
  })()`);
  await waitFor(async () => {
    const state = await sceneState();
    return state && state.selectedId === 'building:catalog:ug-hall-8' && !state.loadingFloor;
  }, 10000, 'Hall VIII focus');
  await waitFor(async () => {
    const state = await sceneState();
    return state?.exterior?.visibleIds?.includes('ug-halls-8-9-shared-source') ||
      state?.exterior?.visibleBundles?.includes('ug-halls-8-9-shared-source') ||
      state?.exterior?.visibleCount > 0;
  }, 30000, 'shared Hall VIII/IX exterior residency');
  const canvas = await evaluate(`(() => {
    const element = document.querySelector('.atlas-world canvas');
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const labels = [...document.querySelectorAll('.entity-label')].filter((label) =>
      /本科生宿舍 VIII／IX|Undergraduate Hall VIII & IX/.test(label.textContent || '')
    );
    const label = labels.find((item) => getComputedStyle(item).display !== 'none');
    const labelRect = label?.getBoundingClientRect();
    // Labels sit above the canvas and are useful for locating the target, but
    // the following CDP click must reach the real WebGL canvas.
    document.querySelectorAll('.entity-label').forEach((item) => { item.style.pointerEvents = 'none'; });
    return {
      rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      point: labelRect ? { x: labelRect.left + labelRect.width / 2, y: labelRect.top + labelRect.height / 2, source: 'shared-zone-label' } : { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, source: 'canvas-center' },
    };
  })()`);
  assert.ok(canvas?.rect?.width > 0 && canvas?.rect?.height > 0);
  const point = canvas.point;
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  await evaluate(`document.querySelectorAll('.entity-label').forEach((item) => { item.style.pointerEvents = ''; }); true`);
  const sharedPick = await waitFor(async () => {
    const pick = await pickState();
    return pick?.entityId === 'zone:hkust-cwb:ug-halls-8-9' ? pick : null;
  }, 10000, 'shared Hall VIII/IX shell pick');
  const sharedUi = await evaluate(`({
    card: document.querySelector('.entity-card h2')?.textContent?.trim() || '',
    members: [...document.querySelectorAll('.entity-results > button strong')].map((node) => node.textContent?.trim() || ''),
  })`);
  assert.equal(sharedUi.card, '本科生宿舍 VIII／IX');
  assert.ok(sharedUi.members.includes('本科生宿舍8座'));
  assert.ok(sharedUi.members.includes('本科生宿舍9座'));
  report.checks.push({ name: 'Real canvas click resolves the shared Hall VIII/IX shell to the aggregate zone', status: 'pass', click: point, pick: sharedPick, ui: sharedUi });

  const memberResults = [];
  for (const [query, expected] of [['本科生宿舍8座', '本科生宿舍8座'], ['本科生宿舍9座', '本科生宿舍9座']]) {
    const chosen = await searchAndChoose(query, expected);
    assert.equal(chosen.ok, true, JSON.stringify(chosen));
    await waitFor(async () => (await evaluate(`document.querySelector('.entity-card h2')?.textContent?.trim() === ${JSON.stringify(expected)}`)), 10000, `${expected} member card`);
    const ui = await evaluate(`({ card: document.querySelector('.entity-card h2')?.textContent?.trim() || '', breadcrumb: document.querySelector('.entity-card .entity-breadcrumb')?.innerText || '' })`);
    memberResults.push(ui);
  }
  assert.deepEqual(memberResults.map((item) => item.card), ['本科生宿舍8座', '本科生宿舍9座']);
  report.checks.push({ name: 'Both Hall VIII and Hall IX members remain reachable after shared-shell selection', status: 'pass', members: memberResults });
  report.status = 'pass';
} catch (error) {
  report.status = 'fail';
  report.error = error instanceof Error ? error.message : String(error);
  throw error;
} finally {
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
  socket.close();
  console.log(JSON.stringify({ status: report.status, reportPath, checks: report.checks.map((check) => check.name) }, null, 2));
}
