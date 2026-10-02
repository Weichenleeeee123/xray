import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import * as researchEvents from '../app/research-events.ts';
import { OfficeDirector } from '../app/office-director.ts';
import { candidateLine, resolveCompany } from '../app/company-resolve.ts';
import { previewSources } from '../app/progressive-images.ts';

// Render the actual Home component into inspectable JSX objects. The harness
// supplies hook scheduling and external services; submit/input handlers are real.
const source = ts.transpileModule(readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const tick = () => new Promise(resolve => setImmediate(resolve));
const exact = name => ({ query: name, exact: true, name, candidates: [], source: 'local', note: null });
const missing = { query: '某公司', exact: false, name: null, candidates: [], source: 'local', note: '请输入全称' };
const ambiguous = { ...missing, candidates: [{ name: '杭州测试科技有限公司', code: null, status: null, founded: null }] };

function mountHome(t, { testMode = null } = {}) {
  const slots = [], effects = [], pending = [], started = [];
  let cursor = 0, mounted = true, tree, nextEffects, resets = 0;
  const office = {
    state: researchEvents.emptyResearch(), scene: new OfficeDirector().sample(),
    paused: false, setPaused() {}, speed: 1, setSpeed() {}, testMode,
    begin: (...args) => { started.push(args); return Promise.resolve(); },
    reset() { resets++; office.state = researchEvents.emptyResearch(); render(); },
    step() {}, retry() {}, retrySave() {}, reconnect() {}, canReconnect: false,
  };
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial;
      return [slots[i], value => {
        assert.ok(mounted, 'a stale resolution must not update an unmounted page');
        slots[i] = typeof value === 'function' ? value(slots[i]) : value;
        render();
      }];
    },
    useRef(initial) { const i = cursor++; return slots[i] ??= { current: initial }; },
    useCallback(callback, deps) {
      const i = cursor++;
      if (!slots[i] || deps.some((value, j) => !Object.is(value, slots[i].deps[j])))
        slots[i] = { callback, deps };
      return slots[i].callback;
    },
    useEffect(setup, deps) {
      const i = cursor++, previous = effects[i];
      if (!previous || deps.some((value, j) => !Object.is(value, previous.deps[j])))
        nextEffects.push(() => {
          previous?.cleanup?.();
          effects[i] = { deps, cleanup: setup() };
        });
    },
  };
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'lucide-react': new Proxy({}, { get: (_target, key) => key }),
    '@/components/ui/button': { Button: 'Button' },
    '@/components/ui/input': { Input: 'Input' },
    './use-office-research': { useOfficeResearch: () => office },
    './research-events': researchEvents,
    './report-dossier': { ReportDossier: 'ReportDossier' },
    './office-instruments': { OfficeInstruments: 'OfficeInstruments' },
    './scene-status': { SceneStatus: 'SceneStatus' },
    './demo-examples': { DemoExamples: 'DemoExamples' },
    './use-progressive-images': { useProgressiveImages: () => previewSources },
    './company-resolve': {
      candidateLine,
      resolveCompany: (query, _fetch, options = {}) => new Promise(resolve => {
        pending.push({ query, signal: options.signal, resolve });
      }),
    },
  };
  const exports = {};
  runInNewContext(source, {
    exports, require: name => { assert.ok(name in modules, `unexpected import: ${name}`); return modules[name]; },
    document: {}, AbortController, setTimeout, clearTimeout, queueMicrotask,
  });
  function render() {
    cursor = 0;
    nextEffects = [];
    tree = exports.default();
    for (const apply of nextEffects) apply();
  }
  function find(predicate, node = tree) {
    if (node == null || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const child of node) { const found = find(predicate, child); if (found) return found; }
    } else {
      if (predicate(node)) return node;
      return find(predicate, node.props?.children ?? null);
    }
  }
  function text(node = tree) {
    if (node == null || typeof node === 'boolean') return '';
    if (typeof node !== 'object') return String(node);
    return Array.isArray(node) ? node.map(child => text(child ?? null)).join('') : text(node.props?.children ?? null);
  }
  function unmount() {
    if (!mounted) return;
    mounted = false;
    for (const effect of effects) effect?.cleanup?.();
  }
  render();
  t.after(unmount);
  return {
    pending, started, find, text, unmount,
    get resets() { return resets; },
    edit(value, id = 'company-query') { find(node => node.props?.id === id).props.onChange({ target: { value } }); },
    submit() { return find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); },
    setConnection(connection) { office.state = { ...office.state, connection }; render(); },
    confirm() {
      const button = find(node => node.type === 'button' && text(node).includes('确认是公司全称'));
      assert.ok(button, 'offer an explicit full-name confirmation');
      button.props.onClick();
    },
  };
}

test('editing the company cancels resolution and a late exact match cannot start research', async t => {
  const h = mountHome(t);
  h.edit('旧公司');
  const work = h.submit();
  h.edit('新公司');
  h.pending[0].resolve(exact('旧公司股份有限公司'));
  await work;
  assert.equal(h.started.length, 0);
  assert.equal(h.pending[0].signal.aborted, true);
  assert.equal(h.find(node => node.type === 'Button').props.disabled, false);
});

test('an old candidate response cannot clear a newer request busy state or populate choices', async t => {
  const h = mountHome(t);
  h.edit('旧公司');
  const old = h.submit();
  h.edit('新公司');
  const current = h.submit();
  assert.equal(h.pending.length, 2);
  h.pending[0].resolve(ambiguous);
  await old;
  assert.equal(h.find(node => node.type === 'Button').props.disabled, true);
  assert.equal(h.text().includes('杭州测试科技有限公司'), false);
  h.pending[1].resolve(exact('新公司有限公司'));
  await current;
  assert.deepEqual(h.started, [['新公司有限公司', '']]);
});

test('selecting a demo invalidates old resolution and retains the complete preset', async t => {
  const h = mountHome(t);
  h.edit('旧公司');
  const old = h.submit();
  const demo = { id: 'A', input: { company_name: '示例有限公司', need: '示例需求', material_text: '原始材料' } };
  h.find(node => node.type === 'DemoExamples').props.onSelect(demo);
  await h.submit();
  h.pending[0].resolve(exact('旧公司有限公司'));
  await old;
  assert.deepEqual(h.started, [['示例有限公司', '示例需求', demo.input]]);
  assert.equal(h.pending[0].signal.aborted, true);
});

test('changing the research need invalidates the old submitted input snapshot', async t => {
  const h = mountHome(t);
  h.edit('公司名称');
  const old = h.submit();
  h.edit('新的需求', 'research-need');
  h.pending[0].resolve(exact('公司名称有限公司'));
  await old;
  assert.equal(h.started.length, 0);
  assert.equal(h.find(node => node.type === 'Button').props.disabled, false);
});

test('no match offers full-name confirmation and never silently chooses the entered abbreviation', async t => {
  const h = mountHome(t);
  h.edit('某公司');
  const work = h.submit();
  h.pending[0].resolve(missing);
  await work;
  assert.equal(h.started.length, 0);
  assert.match(h.text(), /全称/);
  h.confirm();
  assert.deepEqual(h.started, [['某公司', '']]);
});

test('unavailable resolution stays recoverable and requires confirmation before continuing', async t => {
  const h = mountHome(t);
  h.edit('某公司');
  const first = h.submit();
  h.pending[0].resolve(null);
  await first;
  assert.equal(h.started.length, 0);
  assert.equal(h.find(node => node.type === 'Button').props.disabled, false);
  assert.match(h.text(), /重试/);
  const retry = h.submit();
  assert.equal(h.pending.length, 2);
  h.pending[1].resolve(null);
  await retry;
  h.confirm();
  assert.deepEqual(h.started, [['某公司', '']]);
});

test('a malformed backend candidate enters the recoverable fallback instead of crashing Home', async t => {
  const h = mountHome(t);
  h.edit('某公司');
  const work = h.submit();
  const result = await resolveCompany('某公司', async () => ({
    ok: true, json: async () => ({ ...missing, candidates: [null] }),
  }));
  h.pending[0].resolve(result);
  await assert.doesNotReject(work);
  assert.equal(h.started.length, 0);
  assert.match(h.text(), /重试/);
  h.confirm();
  assert.deepEqual(h.started, [['某公司', '']]);
});

test('unmount cancels resolution and prevents late state updates', async t => {
  const h = mountHome(t);
  h.edit('某公司');
  const work = h.submit();
  h.unmount();
  h.pending[0].resolve(ambiguous);
  await assert.doesNotReject(work);
  assert.equal(h.pending[0].signal.aborted, true);
  assert.equal(h.started.length, 0);
});

test('resetting the research room invalidates any outstanding name resolution', async t => {
  const h = mountHome(t);
  h.edit('某公司');
  const work = h.submit();
  h.setConnection('saved');
  h.find(node => node.props?.['aria-label'] === '切换公司').props.onClick();
  h.pending[0].resolve(exact('某公司有限公司'));
  await work;
  assert.equal(h.resets, 1);
  assert.equal(h.started.length, 0);
  assert.equal(h.pending[0].signal.aborted, true);
});

test('test mode still starts synthetic research without depending on name lookup', async t => {
  const h = mountHome(t, { testMode: 'fast' });
  h.edit('测试公司');
  void h.submit();
  await tick();
  assert.equal(h.pending.length, 0);
  assert.equal(h.started.length, 1);
  assert.equal(h.started[0][0], '测试公司');
});

test('choosing an offered candidate starts research with that full name', async t => {
  const h = mountHome(t);
  h.edit('测试科技');
  const work = h.submit();
  h.pending[0].resolve(ambiguous);
  await work;
  h.find(node => node.type === 'button' && h.text(node).includes('杭州测试科技有限公司')).props.onClick();
  assert.deepEqual(h.started, [['杭州测试科技有限公司', '']]);
});
