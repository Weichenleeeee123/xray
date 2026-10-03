const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const store = {};
  const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } };
  const node = { classList: { add() {}, remove() {}, contains() { return false; } }, hidden: true, innerHTML: '', style: {} };
  const ctx = vm.createContext({ console, FormData, AbortController, URLSearchParams, CSS: { escape: s => s }, history: { replaceState() {} },
    location: { hash: '#/me' }, localStorage, setTimeout: fn => { fn(); return 0; }, clearTimeout() {},
    document: { body: node, querySelector: () => null, querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`globalThis.calls=[]; toast=()=>{}; api=async (url,opts={})=>{ calls.push([url,opts.method||'GET',opts.body]); return globalThis.remote; };`);
  return { run, store, ctx };
}
const entry = (id, savedAt, seen = []) => ({ id, term: id, plain: '', savedAt, seen });

test('guest-collected terms are merged into the account on first login, newest first', async () => {
  const h = harness();
  h.store['xray.library'] = JSON.stringify([entry('a', '2026-10-03T02:00:00Z', [{ caseId: 'c1' }]), entry('b', '2026-10-01T00:00:00Z')]);
  h.ctx.remote = [entry('a', '2026-10-02T00:00:00Z', [{ caseId: 'c2' }]), entry('c', '2026-10-02T12:00:00Z')];
  h.run(`S.session={account:{email:'me@example.com'}}`);
  await h.run('libSync()');
  const list = JSON.parse(h.store['xray.library']);
  assert.deepEqual(list.map(e => e.id), ['a', 'c', 'b']);
  assert.deepEqual(list[0].seen.map(s => s.caseId), ['c2', 'c1']);
  assert.equal(h.store['xray.library.owner'], 'me@example.com');
  assert.ok(h.run('calls').some(([url, method]) => url === '/api/me/library' && method === 'PUT'));
});

test('once owned by an account, the server copy wins so deletions elsewhere stick', async () => {
  const h = harness();
  h.store['xray.library'] = JSON.stringify([entry('deleted-on-laptop', '2026-10-03T00:00:00Z')]);
  h.store['xray.library.owner'] = 'me@example.com';
  h.ctx.remote = [entry('kept', '2026-10-02T00:00:00Z')];
  h.run(`S.session={account:{email:'me@example.com'}}`);
  await h.run('libSync()');
  assert.deepEqual(JSON.parse(h.store['xray.library']).map(e => e.id), ['kept']);
  assert.ok(!h.run('calls').some(([, method]) => method === 'PUT'));
});

test('guests never call the account library and logout forgets the local copy', async () => {
  const h = harness();
  h.run(`S.session={account:null}`);
  await h.run('libSync()');
  assert.equal(h.run('calls').length, 0);
  h.store['xray.library'] = '[]'; h.store['xray.library.owner'] = 'x';
  h.run('libForget()');
  assert.equal(h.store['xray.library'], undefined);
  assert.equal(h.store['xray.library.owner'], undefined);
});

test('account panel: login form for guests, merge prompt and quota when signed in', () => {
  const h = harness();
  h.run(`S.session={account:null,mail:true,quota:{used:2,limit:5}}`);
  let html = h.run('acctHtml()');
  assert.match(html, /id="acctForm" data-mode="login"/);
  assert.match(html, /忘记密码/);
  assert.match(html, /今天已新建 2 \/ 5 次研究/);
  h.run(`S.acctMode='register'`);
  assert.match(h.run('acctHtml()'), /邮箱填错了就没法找回密码/);
  h.run(`S.session={account:{email:'me@example.com'},quota:{used:1,limit:30},guest_cases:2}`);
  html = h.run('acctHtml()');
  assert.match(html, /me@example\.com/);
  assert.match(html, /2 份未登录时查的案卷/);
  assert.match(html, /data-act="acct-merge"/);
  assert.match(html, /data-act="acct-logout"/);
  assert.match(html, /id="acctDel"/);
});

test('library header says where the list lives', () => {
  const h = harness();
  h.run(`S.session={account:null}`);
  assert.match(h.run(`libraryHtml([{id:'a',term:'a',plain:'',seen:[]}])`), /登录后可以同步到账号/);
  h.run(`S.session={account:{email:'me@example.com'}}`);
  assert.match(h.run(`libraryHtml([{id:'a',term:'a',plain:'',seen:[]}])`), /已同步到账号 me@example\.com/);
});
