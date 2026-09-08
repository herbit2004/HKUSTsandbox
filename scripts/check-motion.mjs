// Real current source handlers and installed Three/OrbitControls; no browser gesture claim.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const source = fs.readFileSync(
  new URL('../app/scene.ts', import.meta.url),
  'utf8',
);
function load(name) {
  const code = ts.transpileModule(
    fs.readFileSync(new URL('../app/' + name + '.ts', import.meta.url), 'utf8'),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText;
  const compiled = { exports: {} };
  vm.runInNewContext(code, {
    exports: compiled.exports,
    require: (id) => {
      assert.equal(id, 'three');
      return THREE;
    },
    performance,
    console,
    Map,
    Set,
    Float64Array,
  });
  return compiled.exports;
}
const { AnchoredPan, pickVisiblePanAnchor } = load('anchored-pan');
const { qualityProfiles } = load('quality');
const { CameraGroundConstraint } = load('camera-ground-constraint');
const ast = ts.createSourceFile(
  'scene.ts',
  source,
  ts.ScriptTarget.Latest,
  true,
);
function bind(name, owner) {
  let member;
  const visit = (n) => {
    if (
      (ts.isPropertyDeclaration(n) || ts.isMethodDeclaration(n)) &&
      n.name.getText(ast) === name
    )
      member = n;
    ts.forEachChild(n, visit);
  };
  visit(ast);
  assert.ok(member, name);
  const definition = ts.isPropertyDeclaration(member)
    ? `(${member.initializer.getText(ast)})`
    : `({${member.getText(ast)}}).${name}`;
  const code = ts.transpileModule(
    `module.exports=function(){return ${definition}}`,
    {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.CommonJS,
      },
    },
  ).outputText;
  const compiled = { exports: {} };
  vm.runInNewContext(code, {
    module: compiled,
    performance,
    THREE,
    pickVisiblePanAnchor,
    qualityProfiles,
    devicePixelRatio: 2,
  });
  const result = compiled.exports.call(owner);
  return ts.isMethodDeclaration(member) ? result.bind(owner) : result;
}
function fixture({
  button = 2,
  position = [430, 216, -1436],
  target = [336, 123, -1550],
  rect = { left: 320, top: 70, width: 1280, height: 838 },
} = {}) {
  const camera = new THREE.PerspectiveCamera(
    42,
    rect.width / rect.height,
    0.5,
    9000,
  );
  camera.position.fromArray(position);
  const controls = new OrbitControls(camera, null);
  const captures = new Set();
  const canvas = {
    ownerDocument: { addEventListener() {}, removeEventListener() {} },
    style: {},
    clientWidth: rect.width,
    clientHeight: rect.height,
    setPointerCapture: (id) => captures.add(id),
    hasPointerCapture: (id) => captures.has(id),
    releasePointerCapture: (id) => captures.delete(id),
    addEventListener() {},
    removeEventListener() {},
    getBoundingClientRect: () => rect,
  };
  controls.domElement = canvas;
  controls.target.fromArray(target);
  controls.update();
  controls.enableDamping = true;
  controls.dampingFactor = 0.14;
  if (button === 0) controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(20000, 20000),
    new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }),
  );
  plane.rotation.x = -Math.PI / 2;
  plane.position.y = target[1];
  plane.name = 'real-triangle-ground';
  plane.updateMatrixWorld();
  const cssValues = new Map();
  const owner = {
    camera,
    controls,
    qualityLevel: 'high',
    renderer: {
      pixelRatio: 1.6,
      getPixelRatio() { return this.pixelRatio; },
      setPixelRatio(value) { this.pixelRatio=value; },
      domElement: canvas,
      setSize() {
        throw new Error(
          'A projection transition must not resize the full canvas',
        );
      },
    },
    host: {
      dataset: {},
      clientWidth: rect.width,
      clientHeight: rect.height,
      closest: () => ({
        style: { setProperty: (name, value) => cssValues.set(name, value) },
      }),
    },
    labels: { style: {} },
    safeFrameInsets: { left: 0, right: 0, top: 0, bottom: 0 },
    immersive: false,
    immersionProgress: 0,
    immersionFrom: 0,
    immersionStarted: null,
    immersionMedia: { matches: true },
    notify() {},
    anchorPan: new AnchoredPan(),
    panControlsEnabled: true,
    panMode: button === 0,
    motion: { pointer() {}, input() {} },
    pointerDown: [0, 0],
    pointerActive: false,
    lastInput: 0,
    flight: {},
    groundGuard: new CameraGroundConstraint(),
    groundSample: () => -1000,
    detailHeight: () => null,
    opened: null,
    floorId: '',
    allowedFloor: undefined,
    pickPanAnchor: (ray) => pickVisiblePanAnchor(ray, [plane]),
  };
  for (const name of [
    'preventMapContextMenu',
    'applySafeFrameProjection',
    'setSafeFrameInsets',
    'setImmersive',
    'writeImmersion',
    'advanceImmersion',
    'viewportStats',
    'constrainPan',
    'cancelPointer',
    'endPanForWheel',
    'down',
    'move',
    'up',
    'resize',
  ])
    owner[name] = bind(name, owner);
  const event = (
    x = rect.left + rect.width / 2,
    y = rect.top + rect.height / 2,
    extra = {},
  ) => ({
    pointerType: 'mouse',
    pointerId: 1,
    button,
    buttons: button === 2 ? 2 : 1,
    clientX: x,
    clientY: y,
    pageX: x,
    pageY: y,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    timeStamp: performance.now(),
    stopped: false,
    preventDefault() {},
    stopImmediatePropagation() {
      this.stopped = true;
    },
    ...extra,
  });
  const route = (kind, e) => {
    owner[kind](e);
    if (!e.stopped)
      controls[
        kind === 'down'
          ? '_onPointerDown'
          : kind === 'move'
            ? '_onPointerMove'
            : '_onPointerUp'
      ](e);
  };
  return { owner, camera, controls, event, route, plane, rect, cssValues };
}
const reports = [];
for (const button of [2, 0])
  for (const pose of [
    { name: 'near', position: [8, 8, 12], target: [0, 0, 0] },
    {
      name: 'entrance',
      position: [430, 216, -1436],
      target: [336, 123, -1550],
    },
    { name: 'far', position: [1580, 1100, -200], target: [450, 65, -1370] },
    { name: 'near-horizon', position: [0, 1, 1000], target: [0, 0, 0] },
  ]) {
    const f = fixture({ button, ...pose }),
      { owner, camera, controls, event, route, rect } = f;
    let picks = 0;
    const pick = owner.pickPanAnchor;
    owner.pickPanAnchor = (ray) => {
      picks++;
      return pick(ray);
    };
    const down = event();
    route('down', down);
    assert.equal(down.stopped, true);
    assert.equal(controls.enabled, false);
    assert.equal(owner.flight, null);
    assert.equal(controls._pointers.length, 0, 'old Orbit pan never starts');
    const beforeCamera = camera.position.clone(),
      beforeTarget = controls.target.clone();
    for (let i = 1; i <= 20; i++) {
      const move = event(down.clientX + i * 6, down.clientY + i * 2);
      route('move', move);
      assert.equal(move.stopped, true);
      owner.constrainPan();
      assert.ok(
        owner.anchorPan.stats().last.errorPx < 1e-6,
        pose.name + ' anchored error',
      );
    }
    assert.equal(picks, 1, 'no per-move scene raycasts');
    const lastCamera = camera.position.clone(),
      lastTarget = controls.target.clone();
    assert.ok(
      lastCamera
        .clone()
        .sub(beforeCamera)
        .distanceTo(lastTarget.clone().sub(beforeTarget)) < 1e-6,
      'same translation',
    );
    assert.ok(lastTarget.distanceTo(beforeTarget) > 0);
    const up = event(down.clientX + 120, down.clientY + 40);
    route('up', up);
    assert.equal(up.stopped, true);
    assert.equal(owner.anchorPan.active, false);
    assert.equal(controls.enabled, true);
    assert.equal(controls.enableDamping, true);
    for (let i = 0; i < 120; i++) controls.update();
    assert.ok(
      controls.target.distanceTo(lastTarget) < 1e-7,
      'no residual pan tail',
    );
    assert.ok(camera.position.distanceTo(lastCamera) < 1e-7, 'no camera tail');
    assert.equal(JSON.parse(owner.host.dataset.panState).active, false);
    reports.push({
      case: 'anchor-' + pose.name,
      button: button === 2 ? 'right' : 'left-pan-mode',
      samples: owner.anchorPan.stats().samples.length,
      maxErrorPx: owner.anchorPan.stats().maxUnclampedErrorPx,
      picks,
      canvasLeft: rect.left,
    });
    f.plane.geometry.dispose();
    f.plane.material.dispose();
  }
{
  const f = fixture(),
    { owner, controls, event, route, camera } = f;
  const down = event();
  route('down', down);
  owner.groundSample = () => camera.position.y + 10;
  route('move', event(down.clientX + 30, down.clientY + 100));
  owner.constrainPan();
  assert.equal(owner.anchorPan.stats().last.clamped, true);
  assert.ok(owner.anchorPan.stats().last.errorPx > 0.1);
  assert.ok(camera.position.y >= owner.groundState.cameraSurfaceY + 1.8 - 1e-6);
  owner.cancelPointer();
  assert.equal(controls.enabled, true);
  reports.push({
    case: 'ground-clamp-honoured',
    last: owner.anchorPan.stats().last,
  });
}
{
  const f = fixture({ button: 0 }),
    { owner, controls, event, route, camera } = f;
  controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  owner.panMode = false;
  const down = event();
  route('down', down);
  assert.equal(down.stopped, false);
  assert.equal(owner.anchorPan.active, false);
  const before = camera.position.clone();
  route('move', event(down.clientX + 80, down.clientY + 20));
  assert.ok(camera.position.distanceTo(before) > 0);
  route('up', event(down.clientX + 80, down.clientY + 20));
  assert.equal(controls._pointers.length, 0);
  reports.push({ case: 'ordinary-left-rotation-preserved' });
}
{
  const f = fixture(),
    { owner, controls, event, route } = f;
  route('down', event());
  owner.endPanForWheel();
  assert.equal(controls.enabled, true);
  assert.equal(owner.anchorPan.active, false);
  const before = controls.object.position.distanceTo(controls.target);
  controls._onMouseWheel({
    deltaY: -120,
    deltaMode: 0,
    clientX: 100,
    clientY: 100,
    ctrlKey: false,
    preventDefault() {},
  });
  assert.notEqual(controls.object.position.distanceTo(controls.target), before);
  reports.push({ case: 'wheel-exits-anchor-and-zooms' });
}
{
  const f = fixture({ button: 0 }),
    { owner, controls, event, route } = f;
  const first = event(700, 400, { pointerType: 'touch', pointerId: 11 }),
    second = event(800, 400, { pointerType: 'touch', pointerId: 12 });
  route('down', first);
  route('down', second);
  assert.equal(first.stopped, false);
  assert.equal(second.stopped, false);
  assert.equal(owner.anchorPan.active, false);
  assert.equal(controls._pointers.length, 2);
  route('move', event(850, 420, { pointerType: 'touch', pointerId: 12 }));
  route('up', event(850, 420, { pointerType: 'touch', pointerId: 12 }));
  route('up', event(700, 400, { pointerType: 'touch', pointerId: 11 }));
  assert.equal(controls._pointers.length, 0);
  reports.push({ case: 'two-finger-Orbit-touch-preserved' });
}
{
  const f = fixture(),
    { owner, camera, controls } = f;
  const position = camera.position.toArray(),
    target = controls.target.toArray(),
    distance = camera.position.distanceTo(controls.target),
    quaternion = camera.quaternion.toArray();
  owner.host.clientWidth = 900;
  owner.host.clientHeight = 838;
  owner.renderer.setSize = (width, height) => {
    assert.deepEqual([width, height], [900, 838]);
    f.rect.width = width;
    f.rect.height = height;
  };
  owner.resize();
  assert.equal(camera.aspect, 900 / 838);
  assert.deepEqual(camera.position.toArray(), position);
  assert.deepEqual(controls.target.toArray(), target);
  assert.equal(camera.position.distanceTo(controls.target), distance);
  assert.deepEqual(camera.quaternion.toArray(), quaternion);
  const viewport = bind('viewportStats', owner)();
  assert.ok(
    Math.hypot(
      viewport.targetPixel[0] - viewport.center[0],
      viewport.targetPixel[1] - viewport.center[1],
    ) < 1e-7,
  );
  assert.equal(viewport.left, 320);
  assert.equal(viewport.width, 900);
  reports.push({ case: 'real-canvas-resize-preserves-pose', viewport });
}
{
  const movements = [];
  for (const pivotDistance of [40, 4000]) {
    const f = fixture(),
      { owner, camera, controls, event, route } = f;
    owner.groundSample = () => -10000; // Isolate pan scale from the independently tested ground clamp.
    controls.target
      .copy(camera.position)
      .addScaledVector(
        camera.getWorldDirection(new THREE.Vector3()),
        pivotDistance,
      );
    controls.update();
    const before = camera.position.clone(),
      down = event();
    route('down', down);
    route('move', event(down.clientX + 100, down.clientY + 30));
    owner.constrainPan();
    movements.push(camera.position.clone().sub(before));
    owner.cancelPointer();
  }
  assert.ok(
    movements[0].distanceTo(movements[1]) < 1e-7,
    'pan scale comes from grabbed source point, not old selected target distance',
  );
  reports.push({
    case: 'same-view-different-pivot-distance-identical-pan',
    differenceMeters: movements[0].distanceTo(movements[1]),
  });
}
{
  const f = fixture(),
    { owner, camera, controls, event, route } = f;
  controls._sphericalDelta.theta = 0.05;
  const position = camera.position.clone(),
    target = controls.target.clone();
  const down = event();
  route('down', down);
  assert.ok(
    position.distanceTo(camera.position) < 1e-8,
    'begin cancels stale rotate without jumping',
  );
  assert.ok(target.distanceTo(controls.target) < 1e-8);
  route('move', event(down.clientX + 30, down.clientY + 10));
  owner.constrainPan();
  owner.cancelPointer();
  const final = camera.position.clone();
  for (let i = 0; i < 120; i++) controls.update();
  assert.ok(
    camera.position.distanceTo(final) < 1e-8,
    'stale rotation was drained before anchored gesture',
  );
  reports.push({ case: 'pending-Orbit-rotation-drained-without-pose-jump' });
}
{
  const f = fixture(),
    { owner, camera, event, route } = f;
  const down = event();
  route('down', down);
  route('move', event(1e12, -1e12));
  owner.constrainPan();
  assert.ok(camera.position.toArray().every(Number.isFinite));
  assert.equal(owner.anchorPan.stats().last.clamped, true);
  assert.ok(
    ['near-parallel-ray', 'remote-pointer-step'].includes(
      owner.anchorPan.stats().last.reason,
    ),
  );
  owner.cancelPointer();
  reports.push({ case: 'remote-captured-pointer-remains-finite-and-marked' });
}
{
  const f = fixture(),
    { camera, controls, plane } = f;
  const hidden = new THREE.Group();
  hidden.visible = false;
  const roof = new THREE.Mesh(
    new THREE.PlaneGeometry(20000, 20000),
    new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }),
  );
  roof.rotation.x = -Math.PI / 2;
  roof.position.y = 150;
  hidden.add(roof);
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(0, 0), camera);
  const hit = pickVisiblePanAnchor(ray, [hidden, plane]);
  assert.ok(hit);
  assert.ok(
    Math.abs(hit.point.y - controls.target.y) < 1e-7,
    'hidden ancestor cannot provide an anchor',
  );
  roof.geometry.dispose();
  roof.material.dispose();
  reports.push({ case: 'hidden-parent-excluded-from-source-anchor' });
}
{
  const f = fixture(),
    { owner } = f;
  owner.labels = { style: {} };
  owner.showLabels = true;
  const immersive = bind('setImmersive', owner);
  immersive(true);
  assert.equal(owner.labels.style.visibility, 'hidden');
  assert.equal(owner.showLabels, true);
  immersive(false);
  assert.equal(owner.labels.style.visibility, '');
  assert.equal(owner.showLabels, true);
  reports.push({ case: 'immersive-label-suppression-preserves-user-setting' });
}
for (const distance of [0, 4.9]) {
  const f = fixture({ button: 0 }),
    { owner, event, route, controls } = f;
  const picks = [];
  owner.pick = (ray) => {
    const hit = pickVisiblePanAnchor(ray, [f.plane]);
    assert.ok(hit);
    picks.push(hit.point.toArray());
  };
  const down = event();
  route('down', down);
  if (distance) route('move', event(down.clientX + distance, down.clientY));
  const up = event(down.clientX + distance, down.clientY);
  route('up', up);
  assert.equal(
    picks.length,
    1,
    'left PAN tap reaches shared entity pick exactly once',
  );
  assert.equal(
    up.stopped,
    true,
    'Orbit did not receive an untracked PAN pointerup',
  );
  assert.equal(owner.anchorPan.active, false);
  assert.equal(controls.enabled, true);
  reports.push({
    case: 'left-PAN-tap-shared-pick',
    travelPx: distance,
    picks: picks.length,
  });
}
for (const button of [0, 2]) {
  const f = fixture({ button }),
    { owner, event, route } = f;
  let picks = 0;
  owner.pick = () => picks++;
  const down = event();
  route('down', down);
  route('move', event(down.clientX + 60, down.clientY));
  route('move', event(down.clientX, down.clientY));
  route('up', event(down.clientX, down.clientY));
  assert.equal(picks, 0, 'a drag returning to its start must never click');
  assert.equal(owner.pointerTravel, 60);
  reports.push({
    case: 'round-trip-PAN-is-drag',
    button,
    maxTravelPx: owner.pointerTravel,
    picks,
  });
}
{
  const f = fixture({ button: 0 }),
    { owner, event, route } = f;
  let picks = 0;
  owner.pick = () => picks++;
  const down = event();
  route('down', down);
  route(
    'move',
    event(down.clientX, down.clientY, {
      getCoalescedEvents: () => [
        { clientX: down.clientX + 40, clientY: down.clientY },
      ],
    }),
  );
  route('up', event(down.clientX, down.clientY));
  assert.equal(picks, 0);
  assert.equal(owner.pointerTravel, 40);
  reports.push({
    case: 'coalesced-round-trip-is-drag',
    maxTravelPx: owner.pointerTravel,
  });
}
{
  const f = fixture({ button: 2 }),
    { owner, event, route } = f;
  let picks = 0;
  owner.pick = () => picks++;
  const down = event();
  route('down', down);
  route('up', event(down.clientX, down.clientY));
  assert.equal(picks, 0);
  reports.push({ case: 'right-PAN-tap-does-not-select' });
}
{
  const f = fixture({ button: 0 }),
    { owner, event, route, camera, controls } = f;
  let picks = 0;
  owner.pick = () => picks++;
  const down = event(undefined, undefined, { shiftKey: true });
  route('down', down);
  assert.equal(owner.anchorPan.active, false);
  assert.equal(
    down.stopped,
    false,
    'modifier PAN button follows existing Orbit rotation mapping',
  );
  const before = camera.position.clone();
  route(
    'move',
    event(down.clientX + 50, down.clientY + 20, { shiftKey: true }),
  );
  route('up', event(down.clientX + 50, down.clientY + 20, { shiftKey: true }));
  assert.ok(camera.position.distanceTo(before) > 0);
  assert.equal(controls._pointers.length, 0);
  assert.equal(picks, 0);
  reports.push({ case: 'modifier-PAN-button-keeps-Orbit-rotation' });
}
{
  const registrations = [];
  const visit = (node) => {
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      ['addEventListener', 'removeEventListener'].includes(
        node.expression.name.text,
      ) &&
      node.arguments[0]?.getText(ast) === "'contextmenu'"
    )
      registrations.push({
        operation: node.expression.name.text,
        target: node.expression.expression.getText(ast),
        handler: node.arguments[1].getText(ast),
        capture: node.arguments[2]?.getText(ast),
      });
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.deepEqual(registrations, [
    {
      operation: 'addEventListener',
      target: 'this.renderer.domElement',
      handler: 'this.preventMapContextMenu',
      capture: 'true',
    },
    {
      operation: 'removeEventListener',
      target: 'this.renderer.domElement',
      handler: 'this.preventMapContextMenu',
      capture: 'true',
    },
  ]);
  reports.push({
    case: 'contextmenu-interception-is-canvas-local-with-matching-disposal',
  });
}
for (const timing of ['before-down', 'after-down', 'after-up']) {
  const f = fixture({ button: 2 }),
    { owner, event, route, controls } = f;
  let picks = 0;
  owner.pick = () => picks++;
  owner.setImmersive(true);
  const menu = new Event('contextmenu', { cancelable: true, bubbles: true }),
    down = event();
  let forwarded = 0;
  const interceptMenu = () => {
    const target = new EventTarget();
    target.addEventListener('contextmenu', owner.preventMapContextMenu);
    target.addEventListener('contextmenu', () => forwarded++);
    target.dispatchEvent(menu);
  };
  if (timing === 'before-down') interceptMenu();
  route('down', down);
  assert.equal(owner.anchorPan.active, true);
  assert.equal(controls.enabled, false);
  const anchor = owner.anchorPan.stats().anchor;
  if (timing === 'after-down') {
    const oldMenu = new Event('contextmenu', { cancelable: true });
    controls._onContextMenu(oldMenu);
    assert.equal(
      oldMenu.defaultPrevented,
      false,
      'actual disabled OrbitControls cannot suppress the menu',
    );
    interceptMenu();
  }
  route('move', event(down.clientX + 80, down.clientY + 20));
  owner.constrainPan();
  assert.deepEqual(
    owner.anchorPan.stats().anchor,
    anchor,
    'contextmenu does not restart or lose the held anchor',
  );
  assert.ok(owner.anchorPan.stats().last.errorPx < 1e-6);
  route('up', event(down.clientX + 80, down.clientY + 20));
  if (timing === 'after-up') interceptMenu();
  assert.equal(menu.defaultPrevented, true);
  assert.equal(forwarded, 0, 'later app or browser listeners are stopped');
  assert.equal(picks, 0);
  assert.equal(owner.immersive, true);
  assert.equal(owner.anchorPan.active, false);
  assert.equal(controls.enabled, true);
  reports.push({
    case: 'right-contextmenu-' + timing,
    prevented: menu.defaultPrevented,
    keptImmersive: owner.immersive,
    picks,
  });
}
{
  const f = fixture({ button: 2 }),
    { owner, event, route, camera, controls } = f;
  let picks = 0;
  owner.pick = () => picks++;
  const down = event();
  route('down', down);
  const before = camera.position.clone();
  route('move', event(down.clientX + 50, down.clientY, { pointerId: 99 }));
  assert.ok(camera.position.distanceTo(before) < 1e-8);
  assert.equal(owner.anchorPan.active, true);
  route('move', event(down.clientX + 50, down.clientY, { buttons: 0 }));
  assert.ok(camera.position.distanceTo(before) < 1e-8);
  assert.equal(owner.anchorPan.active, false);
  assert.equal(controls.enabled, true);
  route('up', event(down.clientX + 50, down.clientY, { buttons: 0 }));
  assert.equal(picks, 0);
  reports.push({
    case: 'foreign-pointer-ignored-and-missing-button-releases-anchor',
  });
}
{
  const f = fixture({ button: 2 }),
    { owner, event, route, controls } = f;
  let picks = 0;
  owner.pick = () => picks++;
  owner.setImmersive(true);
  route('down', event());
  owner.cancelPointer();
  assert.equal(owner.anchorPan.active, false);
  assert.equal(controls.enabled, true);
  assert.equal(owner.renderer.domElement.hasPointerCapture(1), false);
  route('up', event());
  assert.equal(picks, 0);
  assert.equal(owner.immersive, true);
  reports.push({ case: 'lost-capture-releases-right-PAN-without-selection' });
}
for (const left of [236, 286, 348.5]) {
  const f = fixture({ rect: { left: 0, top: 62, width: 1600, height: 838 } }),
    { owner, camera, controls } = f;
  const pose = {
    camera: camera.position.toArray(),
    target: controls.target.toArray(),
    quaternion: camera.quaternion.toArray(),
    distance: camera.position.distanceTo(controls.target),
  };
  owner.setSafeFrameInsets({ left, right: 12, top: 24, bottom: 8 });
  const expected = [(1600 + left - 12) / 2, 62 + (838 + 24 - 8) / 2];
  for (let i = 0; i < 20; i++) owner.applySafeFrameProjection();
  const viewport = owner.viewportStats();
  assert.ok(
    Math.hypot(
      viewport.targetPixel[0] - expected[0],
      viewport.targetPixel[1] - expected[1],
    ) < 1e-7,
  );
  assert.deepEqual(Array.from(viewport.canvasCenter), [800, 481]);
  assert.equal(
    camera.view.width,
    1600,
    'full-width canvas projection, no crop',
  );
  assert.equal(camera.view.height, 838);
  assert.equal(camera.aspect, 1600 / 838);
  assert.deepEqual(camera.position.toArray(), pose.camera);
  assert.deepEqual(controls.target.toArray(), pose.target);
  assert.deepEqual(camera.quaternion.toArray(), pose.quaternion);
  assert.equal(camera.position.distanceTo(controls.target), pose.distance);
  const inverse = camera.projectionMatrix
    .clone()
    .multiply(camera.projectionMatrixInverse);
  assert.ok(
    inverse.elements.every(
      (n, i) => Math.abs(n - (i % 5 === 0 ? 1 : 0)) < 1e-10,
    ),
  );
  const ray = new THREE.Raycaster();
  ray.setFromCamera(
    new THREE.Vector2(
      (expected[0] / 1600) * 2 - 1,
      1 - ((expected[1] - 62) / 838) * 2,
    ),
    camera,
  );
  assert.ok(
    ray.ray.direction.distanceTo(
      camera.getWorldDirection(new THREE.Vector3()),
    ) < 1e-10,
    'picking ray and target use the same shifted optical axis',
  );
  owner.setImmersive(true);
  assert.ok(
    Math.hypot(
      ...owner
        .viewportStats()
        .targetPixel.map((n, i) => n - viewport.canvasCenter[i]),
    ) < 1e-7,
  );
  owner.setImmersive(false);
  assert.ok(
    Math.hypot(
      ...owner.viewportStats().targetPixel.map((n, i) => n - expected[i]),
    ) < 1e-7,
  );
  owner.setSafeFrameInsets({ left: 0 });
  assert.ok(
    Math.hypot(
      ...owner
        .viewportStats()
        .targetPixel.map((n, i) => n - viewport.canvasCenter[i]),
    ) < 1e-7,
  );
  assert.deepEqual(camera.position.toArray(), pose.camera);
  assert.deepEqual(controls.target.toArray(), pose.target);
  reports.push({
    case: 'full-canvas-offaxis-safe-frame',
    left,
    canvasCenter: viewport.canvasCenter,
    safeCenter: viewport.safeCenter,
    targetPixel: viewport.targetPixel,
  });
}
for (const button of [0, 2]) {
  const f = fixture({
      button,
      rect: { left: 0, top: 62, width: 1600, height: 838 },
    }),
    { owner, event, route } = f;
  owner.setSafeFrameInsets({ left: 304.5 });
  const center = owner.viewportStats().safeCenter,
    down = event(...center);
  route('down', down);
  for (let i = 1; i <= 20; i++) {
    route('move', event(down.clientX + i * 5, down.clientY + i));
    owner.constrainPan();
    assert.ok(owner.anchorPan.stats().last.errorPx < 1e-6);
  }
  route('up', event(down.clientX + 100, down.clientY + 20));
  reports.push({
    case: 'offaxis-anchor-PAN-keeps-point-under-pointer',
    button,
    maxErrorPx: owner.anchorPan.stats().maxUnclampedErrorPx,
  });
}
{
  const f = fixture({ rect: { left: 0, top: 0, width: 1600, height: 900 } }),
    { owner, camera, controls, cssValues } = f;
  owner.immersionMedia.matches = false;
  owner.setSafeFrameInsets({ left: 304, top: 62 });
  const original = {
    camera: camera.position.toArray(),
    target: controls.target.toArray(),
    quaternion: camera.quaternion.toArray(),
    rect: { ...f.rect },
  };
  const states = [];
  const capture = (time, progress) => {
    owner.advanceImmersion(time);
    assert.ok(Math.abs(owner.immersionProgress - progress) < 1e-12);
    assert.equal(Number(cssValues.get('--immersion')), progress);
    const viewport = owner.viewportStats(),
      expected = [800 + 152 * (1 - progress), 450 + 31 * (1 - progress)];
    assert.ok(
      Math.hypot(...viewport.targetPixel.map((n, i) => n - expected[i])) < 1e-7,
    );
    assert.deepEqual(camera.position.toArray(), original.camera);
    assert.deepEqual(controls.target.toArray(), original.target);
    assert.deepEqual(camera.quaternion.toArray(), original.quaternion);
    assert.deepEqual(f.rect, original.rect);
    states.push({
      time,
      progress,
      targetPixel: Array.from(viewport.targetPixel),
    });
  };
  owner.setImmersive(true);
  assert.equal(owner.immersionProgress, 0);
  assert.equal(owner.labels.inert, true);
  capture(1000, 0);
  capture(1150, 0.5);
  owner.setImmersive(false);
  assert.equal(
    owner.immersionProgress,
    0.5,
    'reverse starts at current progress',
  );
  capture(1150, 0.5);
  capture(1300, 0.25);
  owner.setImmersive(true);
  assert.equal(
    owner.immersionProgress,
    0.25,
    'second reversal stays continuous',
  );
  capture(1300, 0.25);
  capture(1450, 0.625);
  capture(1600, 1);
  assert.equal(owner.labels.style.visibility, 'hidden');
  owner.setImmersive(false);
  capture(1700, 1);
  capture(1850, 0.5);
  capture(2000, 0);
  assert.equal(owner.labels.inert, false);
  reports.push({
    case: 'single-RAF-immersion-projection-reverses-continuously-with-fixed-full-canvas',
    states,
  });
}
{
  const f = fixture({ button: 2 }),
    { owner, event, route, camera, controls } = f;
  owner.immersionMedia.matches = false;
  route('down', event());
  assert.equal(owner.anchorPan.active, true);
  owner.flight = { start: 1 };
  controls._sphericalDelta.theta = 0.1;
  const before = camera.position.clone();
  owner.setImmersive(true);
  assert.equal(owner.anchorPan.active, false);
  assert.equal(owner.flight, null);
  assert.equal(controls.enabled, true);
  assert.ok(camera.position.distanceTo(before) < 1e-8);
  owner.advanceImmersion(1000);
  owner.advanceImmersion(1300);
  for (let i = 0; i < 120; i++) controls.update();
  assert.ok(
    camera.position.distanceTo(before) < 1e-8,
    'no leftover PAN/Orbit or flight motion during immersion',
  );
  reports.push({ case: 'immersion-ends-PAN-and-flight-without-camera-drift' });
}
{
  const f = fixture(),
    { owner, cssValues } = f;
  owner.setSafeFrameInsets({ left: 286, top: 62 });
  owner.setImmersive(true);
  assert.equal(owner.immersionProgress, 1);
  assert.equal(cssValues.get('--immersion'), '1');
  owner.setImmersive(false);
  assert.equal(owner.immersionProgress, 0);
  assert.equal(cssValues.get('--immersion'), '0');
  owner.immersionMedia.matches = false;
  owner.setImmersive(true);
  owner.advanceImmersion(1000);
  owner.advanceImmersion(1100);
  assert.ok(owner.immersionProgress > 0 && owner.immersionProgress < 1);
  owner.immersionMedia.matches = true;
  owner.advanceImmersion(1116);
  assert.equal(owner.immersionProgress, 1);
  reports.push({
    case: 'reduced-motion-immediate-including-live-preference-change',
  });
}
for (const button of [0, 2]) {
  const {owner, event, route} = fixture({button, rect:{left:0,top:0,width:1600,height:900}});
  owner.immersionMedia.matches=false;
  owner.pick=()=>{};
  owner.setSafeFrameInsets({left:322,top:62});
  owner.setImmersive(true);
  owner.advanceImmersion(1000);
  owner.advanceImmersion(1060);
  const center=owner.viewportStats().safeCenter, down=event(...center);
  route('down',down);
  const anchor=owner.anchorPan.stats().anchor;
  for(let time=1075;time<=1300;time+=15){
    owner.advanceImmersion(time);
    owner.constrainPan();
    assert.deepEqual(owner.anchorPan.stats().anchor,anchor,'projection never repicks the held surface');
    assert.ok(owner.anchorPan.stats().last.errorPx<1e-6,'stationary held pointer survives animated projection');
  }
  route('up',event(down.clientX,down.clientY));
  reports.push({case:'PAN-started-during-immersion-keeps-stationary-pointer-anchor',button,maxErrorPx:owner.anchorPan.stats().maxUnclampedErrorPx});
}
assert.ok(!source.includes('time-this.last<30'), 'no forced 30ms frame gate');
assert.ok(source.includes('this.groundGuard.constrain('));
assert.ok(source.includes('time-this.lastInput>180'));
const result = {
  checkedAt: new Date().toISOString(),
  scope:
    'Current source pan math/handlers + installed real OrbitControls pointer routing and real Three triangle intersections. Synthetic component events, not browser right-drag automation or GPU visibility acceptance.',
  reports,
};
fs.writeFileSync(
  new URL(
    '../docs/source-evidence-v4/motion-component-checks.json',
    import.meta.url,
  ),
  JSON.stringify(result, null, 2) + '\n',
);
console.log(JSON.stringify(result, null, 2));
