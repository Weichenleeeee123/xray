const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { innerHTML: '', textContent: '', isConnected: true,
      dataset: {}, hidden: true, open: true, value: '', close() { this.open = false; }, append() {}, remove() {}, addEventListener() {},
      classList: { add() {}, remove() {}, contains() { return false; } }, querySelector: () => null });
    return nodes.get(selector);
  }
  const sent = [], stops = [];
  let resolveRequest, rejectRequest;
  const ctx = vm.createContext({ console, FormData, AbortController, URLSearchParams, CSS: { escape: s => s },
    location: { hash: '#/check', search: '' }, history: { replaceState() {} },
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
    document: { body: node('body'), querySelector: node, querySelectorAll: () => [], addEventListener() {}, createElement: () => node('progress') },
    ResearchProgress: {
      mount: () => ({ onEvent() {}, stop() { stops.push(true); } }),
      readCaseStream: (url, body) => { sent.push({ url, body }); return new Promise((resolve, reject) => { resolveRequest = resolve; rejectRequest = reject; }); },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../case-design.js'), 'utf8'), ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`toast=()=>{}; bindForm=()=>{}; renderCase=()=>{}; intakeHtml=()=>'';
    api=async()=>{throw new Error('Legacy non-stream endpoint should not be used')};`);
  const form = node('#caseForm');
  for (const key of ['company', 'need', 'for_whom', 'amount', 'material_text', 'material_title']) form[key] = { value: '' };
  return { run, node, sent, stops, resolve: value => resolveRequest(value), reject: err => rejectRequest(err) };
}
const input = { company_name: '测试公司', need: '想合作', material_text: '合同原文' };
const result = { id: 'new-case', current: 1, versions: [{ no: 1 }], raw: [] };

test('the mounted report returns to the research-room home in the same tab', async () => {
  const h=harness();
  h.run(`location.pathname='/xray/'; location.hash='#/check'; location.replace=path=>{globalThis.returnedTo=path};`);
  await h.run('route()');
  assert.equal(h.run('returnedTo'),'/');
});

for (const hash of ['#/new', '#/new/', '#/new?old=1', '#/unknown', '#/', '']) {
  test(`retired or unknown query link ${hash || '(empty)'} returns to the research room`, async () => {
    const h = harness();
    h.run(`location.pathname='/xray/'; location.hash=${JSON.stringify(hash)};
      location.replace=path=>{globalThis.returnedTo=path};`);
    await h.run('route()');
    assert.equal(h.run('returnedTo'), '/');
    assert.equal(h.node('#view').innerHTML, '');
    assert.equal(h.run('typeof renderCheck'), 'undefined');
  });
}

test('creation waits for a real streamed case, forwards all material and prevents duplicate submission', async () => {
  const h = harness();
  const pending = h.run(`createCase(${JSON.stringify(input)})`);
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0].url, '/api/cases/stream');
  assert.deepEqual(JSON.parse(JSON.stringify(h.sent[0].body)), input);
  await h.run(`createCase(${JSON.stringify(input)})`);
  assert.equal(h.sent.length, 1);
  assert.equal(h.run('location.hash'), '#/check');
  h.resolve(result); await pending;
  assert.equal(h.run('location.hash'), '#/case/new-case');
  assert.equal(h.run('S.case.id'), 'new-case');
  assert.equal(h.stops.length, 1);
});

test('a completed old creation does not replace a page the user navigated to', async () => {
  const h = harness();
  const pending = h.run(`createCase(${JSON.stringify(input)})`);
  assert.equal(h.sent.length, 1);
  h.run(`location.hash='#/case/other'; S.case={id:'other'};`);
  h.resolve(result); await pending;
  assert.equal(h.run('S.case.id'), 'other');
  assert.equal(h.run('location.hash'), '#/case/other');
});

test('stream failure restores the complete input and allows a deliberate retry', async () => {
  const h = harness();
  const pending = h.run(`createCase(${JSON.stringify(input)})`);
  assert.equal(h.sent.length, 1);
  h.reject(new Error('连接已结束')); await pending;
  assert.equal(h.node('#caseForm').material_text.value, '合同原文');
  assert.match(h.node('#formErr').textContent, /连接已结束/);
  assert.equal(h.run('S.creating'), false);
  assert.equal(h.stops.length, 1);
});

test('supplement uses captured case id and opens the actual returned version', async () => {
  const h = harness();
  h.run(`S.case={id:'c',case:{company_name:'测试公司'}}; location.hash='#/case/c';`);
  h.node('#supDlg').dataset.kind = 'material';
  h.run(`globalThis.progressContainer=''; globalThis.form={text:{value:'补充合同原文'},title:{value:'合同'},isConnected:true,
    append(){progressContainer='form'},querySelector(selector){return {append(){progressContainer=selector},scrollTop:0,scrollHeight:800}}};`);
  const pending = h.run(`submitSupplement({preventDefault(){},target:form})`);
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0].url, '/api/cases/c/supplements/stream');
  assert.equal(h.sent[0].body.text, '补充合同原文');
  assert.equal(h.run('progressContainer'), '.dlg-body', 'progress belongs inside the scrollable body, not below its footer');
  h.resolve({ ...result, id: 'c', current: 2 }); await pending;
  assert.equal(h.run('location.hash'), '#/case/c/v/2');
  assert.equal(h.node('#supDlg').open, false);
  assert.equal(h.stops.length, 1);
});

test('a duplicate supplement submission explains that the previous request is still running', async () => {
  const h = harness();
  h.run(`S.supplementBusy=true; globalThis.notice=''; toast=message=>{notice=message};`);
  await h.run(`submitSupplement({preventDefault(){}})`);
  assert.equal(h.sent.length, 0);
  assert.match(h.run('notice'), /正在|稍候/);
});
