// Current-source display/search checks and controlled React-hook state transitions.
// This is not browser layout or WebGL visual acceptance.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import ts from 'typescript';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..'),
  require = createRequire(import.meta.url);
const checks = [];
async function run(name, fn) {
  try {
    const detail = await fn();
    checks.push({ name, status: 'passed', detail });
  } catch (error) {
    checks.push({
      name,
      status: 'failed',
      error: String(error.stack || error),
    });
    console.error(name, error);
  }
}
function modules(hooks) {
  const cache = new Map();
  return function load(name) {
    if (cache.has(name)) return cache.get(name);
    const path =
      root +
      '/app/' +
      name +
      (fs.existsSync(root + '/app/' + name + '.ts') ? '.ts' : '.tsx');
    let source = fs.readFileSync(path, 'utf8');
    if (hooks && ['page', 'panorama'].includes(name)) {
      const tree = ts.createSourceFile(
          path,
          source,
          ts.ScriptTarget.Latest,
          true,
          ts.ScriptKind.TSX,
        ),
        edits = [];
      function visit(node) {
        if (
          ts.isCallExpression(node) &&
          ts.isIdentifier(node.expression) &&
          ['useState', 'useRef'].includes(node.expression.text) &&
          ts.isVariableDeclaration(node.parent)
        ) {
          const binding = node.parent.name,
            key = ts.isIdentifier(binding)
              ? binding.text
              : binding.elements[0].name.text;
          edits.push([
            node.getStart(tree),
            node.end,
            `__hooks.${node.expression.text}(${JSON.stringify(key)},${node.arguments[0]?.getText(tree) || 'undefined'})`,
          ]);
          return;
        }
        ts.forEachChild(node, visit);
      }
      visit(tree);
      for (const [start, end, value] of edits.sort((a, b) => b[0] - a[0]))
        source = source.slice(0, start) + value + source.slice(end);
    }
    const compiledModule = { exports: {} };
    cache.set(name, compiledModule.exports);
    vm.runInNewContext(
      ts.transpileModule(source, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.CommonJS,
          jsx: ts.JsxEmit.ReactJSX,
        },
      }).outputText,
      {
        module: compiledModule,
        exports: compiledModule.exports,
        __hooks: hooks,
        require: (path) =>
          path === 'react' && hooks
            ? hooks
            : path.startsWith('./')
              ? load(path.slice(2))
              : require(path),
        console,
        performance,
        setTimeout,
        clearTimeout,
        queueMicrotask,
        AbortController,
        DOMException,
        document: hooks?.document || { documentElement: { lang: 'zh-Hans' } },
        localStorage: hooks?.storage,
      },
    );
    return compiledModule.exports;
  };
}
const load = modules(),
  { messages, t, localeOptions, resolveLocale } = load('i18n'),
  { EntityRegistry } = load('entity-registry'),
  { entityDisplayName } = load('entity-names'),
  { resourceText } = load('resource-i18n'),
  { prepareEntitySearch, searchClassifiedEntities } = load(
    'entity-classification',
  );
const sourceRegistry = fs.readFileSync(
    root + '/public/data/entity-registry.json',
  ),
  registry = new EntityRegistry(JSON.parse(sourceRegistry));
await run('all_static_ui_messages_and_aria_are_translated', () => {
  let count = 0;
  for (const file of ['page.tsx', 'panorama.tsx']) {
    const tree = ts.createSourceFile(
      file,
      fs.readFileSync(root + '/app/' + file, 'utf8'),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    function visit(n) {
      if (ts.isJsxText(n))
        assert.ok(!/[\u3400-\u9fff]/.test(n.text), 'Raw UI text: ' + n.text);
      if (
        ts.isJsxAttribute(n) &&
        n.initializer &&
        ts.isStringLiteral(n.initializer)
      )
        assert.ok(
          !/[\u3400-\u9fff]/.test(n.initializer.text),
          'Raw attribute: ' + n.initializer.text,
        );
      if (
        ts.isCallExpression(n) &&
        n.expression.getText(tree) === 't' &&
        ts.isStringLiteral(n.arguments[1])
      ) {
        assert.ok(
          messages[n.arguments[1].text],
          'Missing translation: ' + n.arguments[1].text,
        );
        count++;
      }
      ts.forEachChild(n, visit);
    }
    visit(tree);
  }
  return { staticCalls: count, messageCount: Object.keys(messages).length };
});
await run('every_message_preserves_template_parameters', () => {
  for (const [key, value] of Object.entries(messages)) {
    const expected = [...key.matchAll(/\{(\w+)\}/g)]
      .map((m) => m[1])
      .sort((a, b) => a.localeCompare(b));
    for (const text of value.filter(Boolean))
      assert.deepEqual(
        [...text.matchAll(/\{(\w+)\}/g)]
          .map((m) => m[1])
          .sort((a, b) => a.localeCompare(b)),
        expected,
        key,
      );
  }
  assert.equal(resolveLocale('unknown'), 'zh-Hans');
  for (const { id } of localeOptions) assert.equal(resolveLocale(id), id);
  return { locales: localeOptions.map((o) => o.id) };
});
await run('all_entity_names_and_resource_captions_have_english_display', () => {
  for (const entity of registry.entities.filter(
    (entity) => entity.type === 'floor',
  ))
    for (const { id } of localeOptions)
      assert.equal(
        entityDisplayName(entity, id),
        entity.name,
        'Floor names must retain the source floor code',
      );
  for (const entity of registry.entities)
    assert.ok(
      !/[\u3400-\u9fff]/.test(entityDisplayName(entity, 'en')),
      entity.entityId,
    );
  const resources = JSON.parse(
    fs.readFileSync(root + '/public/data/entity-resources.json'),
  ).resources;
  for (const resource of resources)
    assert.ok(
      !/[\u3400-\u9fff]/.test(resourceText('en', resource.name)),
      resource.name,
    );
  for (const n of JSON.parse(
    fs.readFileSync(root + '/public/data/panoramas.json'),
  ).nodes)
    for (const note of (n.evidenceNotes || []).slice(0, 1))
      assert.ok(!/[\u3400-\u9fff]/.test(resourceText('en', note)), note);
  return { entities: registry.entities.length, resources: resources.length };
});
await run('three_language_search_preserves_ids_and_reuses_index', () => {
  const before = createHash('sha256')
      .update(JSON.stringify(registry.entities))
      .digest('hex'),
    start = performance.now(),
    index = prepareEntitySearch(registry),
    buildMs = performance.now() - start;
  assert.equal(prepareEntitySearch(registry), index);
  const groups = [
    ['红鸟', '紅鳥', 'Red Bird'],
    ['电梯', '升降機', 'Lift'],
    [
      '李家诚创科大楼',
      '李家誠創科大樓',
      'Martin Ka Shing Lee Innovation Building',
    ],
  ];
  const result = [];
  for (const aliases of groups) {
    const ids = aliases.map((query) =>
      Array.from(
        searchClassifiedEntities(registry, query),
        (entity) => entity.entityId,
      ).sort((a, b) => a.localeCompare(b)),
    );
    assert.deepEqual(ids[0], ids[1]);
    assert.deepEqual(ids[1], ids[2]);
    assert.equal(ids[0].length, new Set(ids[0]).size);
    result.push({ aliases, count: ids[0].length });
  }
  assert.equal(result[0].count, 1);
  assert.equal(result[1].count, 74);
  assert.equal(
    createHash('sha256')
      .update(JSON.stringify(registry.entities))
      .digest('hex'),
    before,
  );
  return { groups: result, indexBuildMs: +buildMs.toFixed(2) };
});
function createHooks(seed = {}) {
  const states = new Map(Object.entries(seed)),
    refs = new Map(),
    callbacks = [];
  let callbackIndex = 0,
    effects = [];
  const saved = new Map();
  const hooks = {
    document: { documentElement: { lang: 'zh-Hans' }, title: '' },
    storage: {
      setItem: (key, value) => saved.set(key, value),
      getItem: (key) => saved.get(key) || null,
    },
    saved,
    states,
    refs,
    useState(key, initial) {
      if (!states.has(key))
        states.set(key, typeof initial === 'function' ? initial() : initial);
      return [
        states.get(key),
        (value) =>
          states.set(
            key,
            typeof value === 'function' ? value(states.get(key)) : value,
          ),
      ];
    },
    useRef(key, initial) {
      if (!refs.has(key)) refs.set(key, { current: initial });
      return refs.get(key);
    },
    useMemo(fn) {
      return fn();
    },
    useCallback(fn, deps) {
      const index = callbackIndex++,
        old = callbacks[index];
      if (!old || !deps.every((d, i) => Object.is(d, old.deps[i])))
        callbacks[index] = { fn, deps };
      return callbacks[index].fn;
    },
    useEffect(fn, deps) {
      effects.push({ fn, deps });
    },
    useLayoutEffect(fn, deps) {
      effects.push({ fn, deps });
    },
    begin() {
      callbackIndex = 0;
      effects = [];
    },
    effects() {
      return effects;
    },
  };
  return hooks;
}
function nodes(element) {
  if (!element || typeof element !== 'object') return [];
  return [
    element,
    ...(Array.isArray(element.props?.children)
      ? element.props.children
      : [element.props?.children]
    ).flatMap(nodes),
  ];
}
await run(
  'actual_page_language_handler_preserves_scene_and_resource_return_state',
  () => {
    const snapshot = JSON.parse(
        fs.readFileSync(root + '/docs/source-evidence-v4/innovation-room.json'),
      ),
      photo = { name: 'Foyer', asset: '/source.jpg' };
    const hooks = createHooks({
      registry,
      selectedId: snapshot.selectedId,
      query: 'LG1 Lift',
      view: snapshot,
      panel: 'settings',
      qualityMode: 'ultra',
      photo,
      pano: null,
      floorOptions: JSON.parse(
        fs.readFileSync(root + '/public/interiors/manifest.json'),
      ).floors,
    });
    const scene = {
      camera: { position: [...snapshot.camera] },
      target: [...snapshot.target],
      selectedId: snapshot.selectedId,
      floorId: snapshot.floorId,
      qualityMode: 'ultra',
      locale: 'zh-Hans',
      setLocale(value) {
        this.locale = value;
      },
    };
    hooks.refs.set('scene', { current: scene });
    const Page = modules(hooks)('page').default;
    hooks.begin();
    let tree = Page();
    const initialEffects = hooks.effects().map((e) => e.deps),
      before = JSON.stringify({
        camera: scene.camera,
        target: scene.target,
        id: scene.selectedId,
        floor: scene.floorId,
        quality: scene.qualityMode,
      });
    for (const locale of ['en', 'zh-Hant', 'zh-Hans']) {
      const selector = nodes(tree).find(
        (n) =>
          n.type === 'select' &&
          n.props['aria-label'] === t(hooks.states.get('locale'), '语言'),
      );
      assert.ok(selector);
      selector.props.onChange({ target: { value: locale } });
      hooks.begin();
      tree = Page();
      assert.equal(hooks.refs.get('scene').current, scene);
      assert.equal(hooks.states.get('photo'), photo);
      assert.equal(hooks.states.get('query'), 'LG1 Lift');
      assert.equal(hooks.states.get('qualityMode'), 'ultra');
      assert.equal(hooks.states.get('selectedId'), snapshot.selectedId);
      assert.equal(hooks.saved.get('hkust-map-locale'), locale);
      assert.equal(scene.locale, locale);
      assert.equal(hooks.document.documentElement.lang, locale);
      assert.equal(
        hooks.document.title,
        t(locale, '香港科技大学清水湾 · 三维校园地图'),
      );
      assert.equal(
        JSON.stringify({
          camera: scene.camera,
          target: scene.target,
          id: scene.selectedId,
          floor: scene.floorId,
          quality: scene.qualityMode,
        }),
        before,
      );
      hooks.effects().forEach((e, i) =>
        assert.ok(
          e.deps.every((d, j) => Object.is(d, initialEffects[i][j])),
          'Locale changed an existing scene/resource effect dependency',
        ),
      );
    }
    const close = nodes(tree).find(
      (n) =>
        n.type === 'button' &&
        n.props['aria-label'] === t('zh-Hans', '关闭图像资料'),
    );
    close.props.onClick();
    hooks.begin();
    Page();
    assert.equal(hooks.states.get('photo'), null);
    assert.equal(hooks.states.get('selectedId'), snapshot.selectedId);
    assert.equal(scene.floorId, snapshot.floorId);
    assert.equal(
      JSON.stringify(scene.camera),
      JSON.stringify({ position: snapshot.camera }),
    );
    return {
      languages: 3,
      unchanged: [
        'scene instance',
        'camera',
        'target',
        'entity',
        'floor',
        'quality',
        'query',
        'photo',
      ],
      resourceClosePreservesEntity: true,
    };
  },
);
await run(
  'actual_panorama_locale_change_keeps_renderer_and_source_load_dependencies',
  () => {
    const local = JSON.parse(
        fs.readFileSync(root + '/public/data/panoramas.json'),
      ),
      remote = JSON.parse(
        fs.readFileSync(root + '/public/data/panoramas-online.json'),
      ),
      hooks = createHooks({
        local,
        remote,
        id: local.nodes[0].id,
        loading: false,
      }),
      engine = { identity: 'existing panorama engine' };
    hooks.refs.set('engine', { current: engine });
    const Panorama = modules(hooks)('panorama').default;
    const props = {
      initialId: local.nodes[0].id,
      onClose() {},
      contextBuilding: 'Academic Building',
      contextFloor: '1',
    };
    hooks.begin();
    Panorama({ ...props, locale: 'zh-Hans' });
    const dependencies = hooks
      .effects()
      .filter((e) => e.deps)
      .map((e) => e.deps);
    for (const locale of ['en', 'zh-Hant']) {
      hooks.begin();
      Panorama({ ...props, locale });
      assert.equal(hooks.refs.get('engine').current, engine);
      assert.equal(hooks.states.get('id'), local.nodes[0].id);
      const after = hooks.effects().filter((e) => e.deps);
      after.forEach((e, i) =>
        assert.ok(e.deps.every((d, j) => Object.is(d, dependencies[i][j]))),
      );
    }
    return {
      unchanged: [
        'panorama renderer instance',
        'scene ID',
        'source-loading effect dependencies',
      ],
    };
  },
);
const report = {
  checkedAt: new Date().toISOString(),
  scope:
    'Actual checkout source, actual entity/resource data, controlled React-hook transitions; browser and WebGL acceptance remains separate.',
  passed: checks.filter((c) => c.status === 'passed').length,
  failed: checks.filter((c) => c.status === 'failed').length,
  sourceHashes: Object.fromEntries(
    [
      'page.tsx',
      'panorama.tsx',
      'i18n.ts',
      'entity-names.ts',
      'resource-i18n.ts',
      'entity-classification.ts',
    ].map((file) => [
      file,
      createHash('sha256')
        .update(fs.readFileSync(root + '/app/' + file))
        .digest('hex'),
    ]),
  ),
  checks,
};
fs.writeFileSync(
  root + '/docs/source-evidence-v4/i18n-checks.json',
  JSON.stringify(report, null, 2) + '\n',
);
console.log(JSON.stringify({ passed: report.passed, failed: report.failed }));
if (report.failed) process.exitCode = 1;
