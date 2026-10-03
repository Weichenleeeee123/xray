const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness({ broken = false } = {}) {
  const store = {};
  const localStorage = broken
    ? { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } }
    : { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const node = { classList: { add() {}, remove() {}, contains() { return false; } }, hidden: true, open: false, close() {}, scrollIntoView() {}, offsetWidth: 1, getBoundingClientRect: () => ({ left: 0, top: 0, bottom: 0 }), closest: () => null, append() {}, parentElement: null, style: {} };
  const ctx = vm.createContext({ console, FormData, AbortController, CSS: { escape: s => s }, history: { replaceState() {} }, location: { hash: '#/case/c1/v/2' }, localStorage,
    setTimeout: () => 0, clearTimeout() {}, document: { body: node, querySelector: () => node, querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }), innerWidth: 1200, innerHeight: 800 } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`toast=m=>{globalThis.lastToast=m};
    setGlossary([{id:'dishonest',term:'失信被执行人',plain:'法院认定有能力履行却不履行的人。',why:'说明它欠钱不还。',law:'最高法相关规定'}]);
    S.case={id:'c1',case:{company_name:'巨鲸财富'},current:2,chat:[],raw:[],sources:{},versions:[{no:1,signals:[],terms:[]},{no:2,signals:[],terms:[{id:'m_x',term:'对赌协议',plain:'按业绩调整价格的约定。',origin:'model'}]}]};
    S.viewNo=2; useTerms(ver().terms.concat(S.terms));`);
  return { run, store };
}
const list = h => JSON.parse(h.run('JSON.stringify(libRead())'));

test('saving a term keeps a snapshot and where it was met', () => {
  const h = harness();
  assert.equal(h.run(`libToggle('dishonest')`), true);
  const [e] = list(h);
  assert.equal(e.term, '失信被执行人');
  assert.equal(e.plain, '法院认定有能力履行却不履行的人。');
  assert.equal(e.basis, '最高法相关规定');
  assert.deepEqual(e.seen, [{ caseId: 'c1', version: 2, company: '巨鲸财富' }]);
  assert.ok(JSON.parse(h.store['xray.library']).length === 1);
});

test('toggling again removes; saving twice never duplicates', () => {
  const h = harness();
  h.run(`libToggle('dishonest')`);
  assert.equal(h.run(`libToggle('dishonest')`), false);
  assert.equal(list(h).length, 0);
  h.run(`libToggle('dishonest'); libNote('dishonest'); libNote('dishonest')`);
  assert.equal(list(h).length, 1);
  assert.equal(list(h)[0].seen.length, 1);
});

test('opening a saved term in another case adds that case to seen', () => {
  const h = harness();
  h.run(`libToggle('dishonest')`);
  h.run(`S.case={...S.case,id:'c2',case:{company_name:'杭州银行'}}; S.viewNo=1;`);
  h.run(`libNote('dishonest')`);
  assert.deepEqual(list(h)[0].seen.map(s => [s.caseId, s.version]), [['c1', 2], ['c2', 1]]);
  h.run(`libNote('dishonest')`);
  assert.equal(list(h)[0].seen.length, 2);
});

test('outside a case nothing is recorded as seen', () => {
  const h = harness();
  h.run(`location.hash='#/me'`);
  h.run(`libToggle('dishonest')`);
  assert.deepEqual(list(h)[0].seen, []);
});

test('AI explanations can be saved and keep their label on the library page', () => {
  const h = harness();
  h.run(`libToggle('m_x')`);
  assert.equal(list(h)[0].origin, 'model');
  const html = h.run('libraryHtml(libRead())');
  assert.match(html, /对赌协议/);
  assert.match(html, /AI 解释·未经人工核对/);
  assert.match(html, /href="#\/case\/c1\/v\/2"/);
  assert.match(html, /巨鲸财富/);
  assert.match(html, /data-act="lib-remove" data-term="m_x"/);
});

test('library page has an empty state and lists newest first', () => {
  const h = harness();
  assert.match(h.run('libraryHtml([])'), /收藏复习/);
  h.run(`libToggle('dishonest'); libToggle('m_x')`);
  const html = h.run('libraryHtml(libRead())');
  assert.ok(html.indexOf('对赌协议') < html.indexOf('失信被执行人'));
  assert.match(html, /共 2 个词/);
});

test('term popup shows the save button state', () => {
  const h = harness();
  assert.match(h.run('termPopHtml(termOf("dishonest"))'), /data-act="lib-toggle" data-term="dishonest"[^>]*aria-pressed="false"[^>]*>☆ 收藏复习/);
  h.run(`libToggle('dishonest')`);
  assert.match(h.run('termPopHtml(termOf("dishonest"))'), /aria-pressed="true"[^>]*>★ 已收藏/);
});

test('blocked storage does not throw and reports failure', () => {
  const h = harness({ broken: true });
  assert.deepEqual(list(h), []);
  assert.equal(h.run(`libToggle('dishonest')`), null);
  assert.doesNotThrow(() => h.run(`libNote('dishonest')`));
});

test('library is a top-level section', () => {
  const h = harness();
  assert.match(h.run('JSON.stringify(NAV)'), /"library","知识库"/);
});
