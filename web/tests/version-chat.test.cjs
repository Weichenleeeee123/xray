const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const listeners = {};
  const node = { classList: { add() {}, remove() {}, contains() { return false; } }, hidden: true, open: false, close() {}, scrollIntoView() {}, offsetWidth: 1 };
  const ctx = vm.createContext({ console, FormData, CSS: { escape: s => s }, history: { replaceState() {} }, location: { hash: '#/case/c/v/1' },
    setTimeout: () => 0, clearTimeout() {}, document: { querySelector: () => node, querySelectorAll: () => [], addEventListener: (k, f) => { listeners[k] = f; } },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`S.case = { id:'c', current:2, chat:[], raw:[], sources:{}, versions:[{no:1,signals:[],terms:[]},{no:2,signals:[],terms:[]}] }; S.viewNo=1;
    renderCase=()=>{}; renderPanel=()=>{}; refreshChat=()=>{}; refreshSel=()=>{}; toast=()=>{};`);
  return { ctx, run, listeners, node };
}

test('redesigned report keeps Xiaoqi animated and selected references visible during a request', async () => {
  const h = harness();
  h.run(`isDesignReview=()=>true; S.selected.add('A2'); api=()=>new Promise(resolve=>globalThis.resolveRequest=resolve);`);
  assert.match(h.run('qiLauncherContent()'), /data-qi-state="idle"/);
  assert.match(h.run('qiLauncherContent()'), /aria-label="已选 1 条"/);
  const pending = h.run(`ask('解释这一条')`);
  assert.match(h.run('qiLauncherContent()'), /data-qi-state="thinking"/);
  assert.match(h.run('qiLauncherContent()'), /思考中/);
  h.run(`resolveRequest({role:'assistant',text:'答复',version:1})`);
  await pending;
  assert.match(h.run('qiLauncherContent()'), /data-qi-state="idle"/);
});

test('asks about viewed version, including unselected questions and typed references', async () => {
  const h = harness();
  h.run(`api=async (url, opts)=>{ globalThis.sent=opts.body; return {role:'assistant'}; }; S.selected=new Set(['A2','M1','Q1','risk.bank_list','R3']);`);
  await h.run(`ask('解释')`);
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(sent)')), { text:'解释', version:1, refs:['v:1:assertion:A2','v:1:missing:M1','v:1:question:Q1','v:1:signal:risk:bank_list','R3'] });
  assert.equal(h.run('S.case.chat[0].version'), 1);
  await h.run(`ask('没有选中')`);
  assert.equal(h.run('sent.version'), 1);
});

test('renders historical text, user refs, quotes, structured citations and terms with their version', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,text:'解释 [A2] [v:1:signal:risk:bank_list]',citations:['Q1','term.capital'],quotes:[{text:'原文',ref:'R3'}],suggest:[]})`);
  assert.match(html, /data-id="A2" data-version="1"/);
  assert.match(html, /data-id="v:1:signal:risk:bank_list" data-version="1"/);
  assert.match(html, /data-id="Q1" data-version="1"/);
  assert.match(html, /data-id="term.capital" data-version="1"/);
  assert.match(html, /data-ref="R3" data-version="1"/);
  assert.match(h.run(`msgHtml({role:'user',version:1,text:'问',refs:['A2']})`), /data-id="A2" data-version="1"/);
});

test('historical citation click selects its version before locating item', () => {
  const h = harness();
  h.run('S.viewNo=2; S.selected.add("A2")');
  h.run(`gotoItem('v:1:assertion:A2', 1)`);
  assert.equal(h.run('S.viewNo'), 1);
  assert.equal(h.run('S.tab'), 'claims');
  assert.equal(h.run('S.selected.size'), 0);
});

test('switching report versions clears selected items', async () => {
  const h = harness();
  h.run('S.selected.add("A2")');
  await h.run(`openCase('c',2)`);
  assert.equal(h.run('S.selected.size'), 0);
});

test('failed request removes its own optimistic message and preserves other-version selections', async () => {
  const h = harness();
  h.run(`api=()=>new Promise((resolve,reject)=>globalThis.rejectRequest=reject); S.selected.add('A2');`);
  const pending = h.run(`ask('旧版问题')`);
  h.run(`S.viewNo=2; S.selected.add('Q1'); S.case.chat.push({role:'user',text:'另外一条'}); rejectRequest(new Error('断网'));`);
  await pending;
  assert.deepEqual(JSON.parse(h.run('JSON.stringify([...S.selected])')), ['Q1']);
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(S.case.chat.map(m=>m.text))')), ['另外一条']);
});

test('failed request restores original selections while still viewing original version', async () => {
  const h = harness();
  h.run(`api=async()=>{throw new Error('断网')}; S.selected.add('A2');`);
  await h.run(`ask('问')`);
  assert.deepEqual(JSON.parse(h.run('JSON.stringify([...S.selected])')), ['A2']);
});

test('raw quote click opens evidence after selecting the message version', () => {
  const h = harness();
  h.run(`S.viewNo=2; openRaw=(id, highlights)=>{globalThis.opened={id,highlights,version:ver().no}};`);
  const el = { dataset: { act:'raw', ref:'R3', version:'1', hl:'["原文"]' } };
  h.listeners.click({ target: { closest: selector => selector === '[data-act]' ? el : null } });
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(opened)')), { id:'R3', highlights:['原文'], version:1 });
});

test('term citation uses the historical glossary after selecting its version', () => {
  const h = harness();
  h.run(`S.viewNo=2; S.case.versions[0].terms=[{id:'capital',term:'资本',plain:'第一版定义'}];
    renderCase=()=>useTerms(ver().terms); termPop=(el,id)=>globalThis.definition=termOf(id).plain;`);
  h.run(`gotoItem('term.capital',1)`);
  assert.equal(h.run('definition'), '第一版定义');
});

test('term popover anchors to the current assistant after a version change detaches the old link', () => {
  const h = harness();
  h.run(`S.viewNo=2; globalThis.oldAnchor={isConnected:false}; termPop=(el)=>globalThis.usedAnchor=el;`);
  h.run(`gotoItem('term.capital',1,oldAnchor)`);
  assert.equal(h.ctx.usedAnchor, h.node);
});

test('bare historical signal references remain navigable', () => {
  const h = harness();
  h.run(`S.viewNo=2; gotoItem('risk.bank_list',1)`);
  assert.equal(h.run('S.viewNo'), 1);
  assert.equal(h.run('S.tab'), 'signals');
});

test('a failed old-case request does not remove messages or selections in a different case', async () => {
  const h = harness();
  h.run(`api=()=>new Promise((resolve,reject)=>globalThis.rejectRequest=reject); globalThis.oldCase=S.case; S.selected.add('A2');`);
  const pending = h.run(`ask('旧案卷问题')`);
  h.run(`S.case={id:'another',chat:[{text:'保留'}],versions:[{no:2}]}; S.viewNo=2; S.selected.add('Q1'); rejectRequest(new Error('断网'));`);
  await pending;
  assert.equal(h.run('oldCase.chat.length'), 0);
  assert.equal(h.run('S.case.chat[0].text'), '保留');
  assert.deepEqual(JSON.parse(h.run('JSON.stringify([...S.selected])')), ['Q1']);
});

test('successful request remains visible when the same case was reloaded during the request', async () => {
  const h = harness();
  h.run(`api=()=>new Promise(resolve=>globalThis.resolveRequest=resolve); globalThis.originalCase=S.case;`);
  const pending = h.run(`ask('正在问')`);
  h.run(`S.case={...S.case,chat:[]}; resolveRequest({role:'assistant',text:'答复',version:1,created_at:'2026-10-02T12:00:00'});`);
  await pending;
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(S.case.chat.map(m=>m.text))')), ['正在问','答复']);
});

test('successful response does not duplicate messages already fetched from the same case', async () => {
  const h = harness();
  h.run(`api=()=>new Promise(resolve=>globalThis.resolveRequest=resolve);`);
  const pending = h.run(`ask('正在问')`);
  h.run(`globalThis.reply={role:'assistant',text:'答复',version:1,created_at:'2026-10-02T12:00:00'};
    S.case={...S.case,chat:[{...S.case.chat[0],created_at:reply.created_at},{...reply}]}; resolveRequest(reply);`);
  await pending;
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(S.case.chat.map(m=>m.text))')), ['正在问','答复']);
});

test('failed same-case reload removes only its cloned optimistic message', async () => {
  const h = harness();
  h.run(`api=()=>new Promise((resolve,reject)=>globalThis.rejectRequest=reject);`);
  const pending = h.run(`ask('重复问题')`);
  h.run(`S.case={...S.case,chat:[{...S.case.chat[0]}, {role:'user',text:'重复问题',version:1,created_at:'earlier'}]}; rejectRequest(new Error('断网'));`);
  await pending;
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(S.case.chat.map(m=>m.created_at))')), ['earlier']);
});
