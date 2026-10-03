const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const listeners = {};
  const node = { classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } }, hidden: true, open: false, close() {}, scrollIntoView() {}, offsetWidth: 1 };
  const ctx = vm.createContext({ console, FormData, AbortController, URLSearchParams, CSS: { escape: s => s }, history: { replaceState() {} }, location: { hash: '#/case/c/v/1' },
    setTimeout: () => 0, clearTimeout() {}, document: { body: node, querySelector: () => node, querySelectorAll: () => [], addEventListener: (k, f) => { listeners[k] = f; } },
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

test('answer has one source entry without raw quotes or internal diagnostics', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,text:'解释 [A2] [v:1:signal:risk:bank_list]',citations:['Q1','term.capital'],quotes:[{text:'隐藏的原始引文',ref:'R3'}],suggest:[],rewrites:2,dropped:8,blocked:['禁止展示的内部信息']},null,3)`);
  assert.match(html, /data-act="chat-sources" data-index="3"/);
  assert.equal((html.match(/原文出处 ↗/g) || []).length, 1);
  assert.doesNotMatch(html, /隐藏的原始引文|禁止展示的内部信息|重写|丢掉|\[A2\]|data-act="goto"/);
  assert.match(h.run(`msgHtml({role:'user',version:1,text:'问',refs:['A2']})`), /data-id="A2" data-version="1"/);
});
test('answers disclose omitted unsupported wording without exposing rejected content or diagnostics',()=>{
 const h=harness();
 const filtered=h.run(`msgHtml({role:'assistant',mode:'model',version:1,text:'已有依据支持的内容',citations:[],suggest:[],has_omitted_claims:true})`);
 assert.match(filtered,/部分表述未获依据支持，已省略/);
 assert.doesNotMatch(filtered,/被拒绝的原句|3 条|2 次/);
 for(const has_omitted_claims of [false,undefined,'true']) {
   h.ctx.testReply={role:'assistant',mode:'model',version:1,text:'答复',citations:[],suggest:[],has_omitted_claims};
   assert.doesNotMatch(h.run('msgHtml(testReply)'),/已省略/);
 }
 const missing=h.run(`msgHtml({role:'assistant',mode:'guard',version:1,text:'资料不足',citations:[],suggest:[],has_omitted_claims:false,not_found:true})`);
 assert.match(missing,/部分信息仍待核实/);assert.doesNotMatch(missing,/已省略/);
});

test('selective evidence disclosure coexists with the upstream omitted-claim notice',()=>{
  const h=harness();
  const html=h.run(`msgHtml({role:'assistant',mode:'model',version:1,text:'已核对的答复',context_mode:'selective',has_omitted_claims:true,citations:['R1'],suggest:[]},null,4)`);
  assert.match(html,/按需核对相关材料/);
  assert.match(html,/部分表述未获依据支持，已省略/);
  assert.equal((html.match(/原文出处 ↗/g)||[]).length,1);
  assert.doesNotMatch(html,/原文（|程序拦下|重写|丢掉/);
});

test('source detail resolves report facts to original records from the answer version', () => {
  const h = harness();
  h.run(`S.case.raw=[{id:'R3',source_id:'registry',title:'旧版登记资料',kind:'official',content:'原文'}];
    S.case.versions[0].raw_ids=['R3'];S.case.versions[0].assertions=[{id:'A2',refs:['R3']}];
    S.case.versions[1].raw_ids=[];S.viewNo=2;`);
  const html = h.run(`chatSourcesHtml({version:1,text:'解释 [A2]',citations:['A2'],quotes:[{ref:'R3',text:'原文'}]})`);
  assert.match(html, /旧版登记资料/);
  assert.match(html, /data-ref="R3" data-version="1"/);
  assert.match(html, /<mark>原文<\/mark>/);
  assert.equal(h.run('S.viewNo'), 2, 'viewing the source list must not silently replace the current report');
});

test('uncited empathy has no fake source button; source highlight escapes markup', () => {
  const h = harness();
  assert.doesNotMatch(h.run(`msgHtml({role:'assistant',version:1,text:'我们可以慢慢弄清楚。'})`), /chat-sources/);
  const html = h.run(`contentHtml({详情:'<script>原文</script>'},['原文'])`);
  assert.match(html, /<mark>原文<\/mark>/);
  assert.doesNotMatch(html, /<script>/);
  assert.equal(h.run(`markText('原文原文',['原文','原文原文'])`), '<mark>原文原文</mark>');
});

test('selective context is disclosed and processing failure is not a company risk', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,text:'暂不能完整核对',context_mode:'selective',error_code:'evidence_coverage',not_found:true})`);
  assert.match(html, /按需核对相关材料/);
  assert.match(html, /本次材料处理未完成，不是企业风险结论/);
  assert.doesNotMatch(html, /部分信息仍待核实|chat-sources/);
  assert.doesNotMatch(h.run(`msgHtml({role:'assistant',version:1,text:'旧版回答'})`), /按需核对相关材料/);
});

test('source fallback uses a readable report label and keeps its versioned navigation', () => {
  const h = harness();
  h.run(`S.case.versions[0].signals=[{key:'risk',items:[{key:'promise',label:'收益承诺'}]}]`);
  const html = h.run(`chatSourcesHtml({version:1,text:'解释',citations:['risk.promise']})`);
  assert.match(html, /查看报告条目：收益承诺/);
  assert.match(html, /data-id="risk.promise" data-version="1"/);
  assert.doesNotMatch(html, />risk\.promise</);
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

test('retry after uncertain failure reuses request identity and can stop waiting', async () => {
  const h = harness();
  h.run(`globalThis.keys=[];api=async(url,opts)=>{keys.push(opts.headers['Idempotency-Key']);throw new Error('connection lost')};`);
  await h.run(`ask('需要核对')`);
  await h.run(`ask('需要核对')`);
  assert.equal(h.run('keys[0]'), h.run('keys[1]'));
  assert.equal(h.run('S.busy'), false);
  h.run(`api=(url,opts)=>new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(new Error('cancelled'))));`);
  const pending = h.run(`ask('需要核对')`);
  h.run(`S.chatAbort.abort('cancelled')`);
  await pending;
  assert.equal(h.run('S.busy'), false);
  assert.equal(h.run('S.case.chat.length'), 0);
  assert.ok(h.run(`pendingChat('c')`));
});

test('report references show record titles and item names instead of internal ids', () => {
  const h = harness();
  h.run(`isDesignReview=()=>true;
    S.case.raw=[{id:'R3',title:'企查查·行政处罚记录明细（共 5 条）',source_id:'qcc',kind:'commercial'}];
    S.case.versions[0]=Object.assign(S.case.versions[0],{assertions:[{id:'A1',kind_label:'资格'}],missing:[{id:'M1',text:'没写收款账户'}],
      questions:[{id:'Q1',ask:'钱交给谁？'}],signals:[{key:'risk',items:[{key:'bank_list',label:'持牌机构名单'}]}]});`);
  const labels = html => [...html.matchAll(/<button[^>]*class="(?:cite|rf)[^"]*"[^>]*>([^<]*)<\/button>/g)].map(m => m[1]);
  const asked = h.run(`msgHtml({role:'user',text:'解释',version:1,refs:['v:1:assertion:A1','v:1:missing:M1','v:1:question:Q1','v:1:signal:risk:bank_list','R3','risk.gone']})`);
  assert.deepEqual(labels(asked), ['它说的·资格', '该写没写·没写收款账户', '第 1 个问题', '持牌机构名单', '企查查·行政处罚记录明细', '查看出处']);
  assert.match(asked, /data-id="v:1:signal:risk:bank_list"/, 'navigation still uses the id');
  assert.deepEqual(labels(h.run(`refLinks(['A1','R3'])`)), ['它说的·资格', '企查查·行政处罚记录明细']);
  const answer = h.run(`msgHtml({role:'assistant',text:'查了名单 [risk.bank_list]，见 [R3]',version:1,citations:['A1','R3'],suggest:[],quotes:[]})`);
  assert.doesNotMatch(answer, />(A1|R3|risk\.bank_list)</);
  assert.match(h.run(`goLink('A1',1,'查看报告条目：资格')`), />查看报告条目：资格</, 'an explicit label wins');
  h.run(`S.selected=new Set(['risk.bank_list','A1'])`);
  assert.doesNotMatch(h.run('selHtml()'), />(risk\.bank_list|A1)</);
  h.run(`isDesignReview=()=>false`);
  assert.match(h.run(`goLink('risk.bank_list',1)`), />risk\.bank_list</, 'classic view keeps ids');
});
