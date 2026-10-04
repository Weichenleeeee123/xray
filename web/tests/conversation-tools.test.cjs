const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const listeners = {}, store = new Map();
  const node = { classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    hidden: true, open: false, close() {}, focus() {}, scrollIntoView() {}, offsetWidth: 1, value: '' };
  const ctx = vm.createContext({ console, FormData, AbortController, URLSearchParams,
    CSS: { escape: value => value }, history: { replaceState() {} }, location: { hash: '#/case/c/v/1' },
    setTimeout: () => 0, clearTimeout() {},
    localStorage: { getItem: () => null },
    sessionStorage: { getItem: key => store.get(key) || null, setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key) },
    document: { body: node, querySelector: () => node, querySelectorAll: () => [], addEventListener: (name, fn) => { listeners[name] = fn; } },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`S.case={id:'c',current:2,chat:[],sources:{},raw:[{id:'R1',title:'旧版资料'},{id:'R2',title:'新版资料'}],versions:[
    {no:1,raw_ids:['R1'],terms:[{id:'status',term:'登记状态',plain:'旧版词条内容'}],
      assertions:[{id:'A1'}],missing:[{id:'M1'}],questions:[{id:'Q1'}],signals:[{key:'credit',items:[{key:'status',label:'登记状态'}]}]},
    {no:2,raw_ids:['R2'],terms:[{id:'status',term:'登记状态',plain:'新版词条内容'}],signals:[]}
  ]}; S.viewNo=1; setGlossary([{id:'judgment',term:'裁判文书',plain:'词表定义'}]); useTerms(ver().terms);
  renderCase=()=>useTerms(ver().terms); renderPanel=()=>{}; refreshChat=()=>{}; refreshSel=()=>{};
  toast=text=>{globalThis.notice=text}; openSupplement=body=>{globalThis.supplement=body};
  api=async(url, options)=>{globalThis.sent=options.body;return {role:'assistant',version:options.body.version,text:'解释'}};`);
  const read = code => JSON.parse(run(`JSON.stringify(${code})`));
  const click = dataset => listeners.click({ target: { closest: selector => selector === '[data-act]' ? { dataset } : null } });
  return { run, read, click, ctx, node, store, listeners };
}

test('conversation has no coverage, report-reading, template-failure or automatic finance follow-up labels', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:2,answer_kind:'conversation',text:'你好，我在。',
    mode:'template',not_found:true,context_mode:'selective',suggest:['先核对收款账户','加入案卷']})`);
  assert.match(html, /你好，我在/);
  assert.doesNotMatch(html, /部分信息仍待核实|按需核对|当前为基础答复|基于第|先核对收款账户|加入案卷|chat-sources|class="msg ai nf/);
  const error = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'conversation',text:'服务未完成',mode:'guard',error_code:'evidence_coverage',not_found:true})`);
  assert.match(error, /本次材料处理未完成，不是企业风险结论/);
  assert.match(error, /class="msg ai guard"/);
  const replay = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'conversation',mode:'replay',text:'你好'})`);
  assert.match(replay, /离线回放/);
});

test('free-text material suggestions cannot create controls; only explicit offer_material can', () => {
  const h = harness();
  const legacy = h.run(`msgHtml({role:'assistant',version:1,text:'你可以加入案卷',suggest:['请加入案卷重新判断']},{role:'user',text:'用户自己的材料'},1)`);
  assert.match(legacy, /请加入案卷重新判断/);
  assert.doesNotMatch(legacy, /data-act="supplement"|data-act="chat-action"|class="add-case"/);
  const explicit = h.run(`msgHtml({role:'assistant',version:1,text:'可先查看材料',actions:[{type:'offer_material',label:'加入案卷，重新判断'}]}, {role:'user',version:1,text:'用户自己的材料'},1)`);
  assert.match(explicit, /data-act="chat-action" data-index="1" data-action-index="0"/);
  assert.doesNotMatch(explicit, /data-text=|用户自己的材料/);
  assert.doesNotMatch(h.run(`msgHtml({role:'assistant',version:1,text:'答复',actions:[{type:'offer_material',label:'加入案卷'}]},{role:'assistant',text:'不能追加的模型文字'},1)`), /chat-action/);
});

test('explicit material action opens an editable draft of the preceding user text and never submits', () => {
  const h = harness();
  h.run(`S.viewNo=2; api=()=>{throw new Error('must not submit')}; S.case.chat=[
    {role:'user',version:1,text:'对方说可以随时退款'},
    {role:'assistant',version:1,text:'模型解释不能作为材料',actions:[{type:'offer_material',label:'加入案卷'}]}
  ]`);
  h.click({act:'chat-action',index:'1',actionIndex:'0'});
  assert.deepEqual(h.read('supplement'), {kind:'reply',text:'对方说可以随时退款'});
  assert.equal(h.run('S.case.versions.length'), 2);
  assert.equal(h.run('S.viewNo'), 2, 'opening an older message draft must not select an older report for writing');
});

test('report snapshot conversation tools disclose the saved scope and historical version', () => {
  const h = harness();
  h.run('S.viewNo=2');
  const html = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'conversation',answer_scope:'report_snapshot',
    mode:'template',context_mode:'selective',text:'本版报告已整理的核查问题',actions:[{type:'open_ref',label:'查看出处',ref:'R1',version:1}]})`);
  assert.match(html, /<span>依据已生成报告<\/span>/);
  assert.match(html, /<span>基于第 1 版<\/span>/);
  assert.match(html, /data-act="chat-action"/);
  assert.doesNotMatch(html, /按需核对相关材料|当前为基础答复|本版报告概览|部分信息仍待核实/);
  const current = h.run(`msgHtml({role:'assistant',version:2,answer_kind:'conversation',answer_scope:'report_snapshot',text:'本版问题清单'})`);
  assert.match(current, /依据已生成报告/);
  assert.doesNotMatch(current, /基于第/);
  const ordinary = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'conversation',text:'你好'})`);
  assert.doesNotMatch(ordinary, /依据已生成报告|基于第|按需核对/);
});

test('material offers cannot mix adjacent user turns or action versions at render or click time', () => {
  const h = harness();
  for (const userVersion of [undefined, null, '1', 2]) {
    h.ctx.userVersion = userVersion;
    h.run(`S.case.chat=[{role:'user',version:userVersion,text:'其他版本的材料'},
      {role:'assistant',version:1,text:'建议',actions:[{type:'offer_material',version:1,label:'加入案卷'}]}]`);
    assert.doesNotMatch(h.run('msgHtml(S.case.chat[1],S.case.chat[0],1)'), /chat-action/);
    h.click({act:'chat-action',index:'1',actionIndex:'0'});
    assert.equal(h.run('typeof supplement'), 'undefined');
  }
  h.run(`S.case.chat[0].version=1; S.case.chat[1].actions[0].version=2`);
  assert.doesNotMatch(h.run('msgHtml(S.case.chat[1],S.case.chat[0],1)'), /chat-action/);
  h.click({act:'chat-action',index:'1',actionIndex:'0'});
  assert.equal(h.run('typeof supplement'), 'undefined');
  h.run('S.case.chat[1].actions[0].version=1');
  assert.match(h.run('msgHtml(S.case.chat[1],S.case.chat[0],1)'), /chat-action/);
  h.run('S.case.chat[0].version=2');
  h.click({act:'chat-action',index:'1',actionIndex:'0'});
  assert.equal(h.run('typeof supplement'), 'undefined', 'a stale rendered control must recheck version identity');
});

test('open_ref controls require real entries in their saved version, including correctly typed encoded refs', () => {
  const h = harness();
  for (const ref of ['R1','A1','M1','Q1','credit.status','term.status','term.judgment','v:1:assertion:A1','v:1:signal:credit:status']) {
    h.ctx.ref = ref;
    assert.match(h.run(`chatActionsHtml({version:1,actions:[{type:'open_ref',label:'查看条目',ref}]},null,0)`), /chat-action/, ref);
  }
  for (const action of [
    {ref:'R2'}, {ref:'R99'}, {ref:'A99'}, {ref:'credit.unknown'}, {ref:'term.unknown'},
    {ref:'R1',version:2}, {ref:'R1',version:99}, {ref:'R1',version:'1'},
    {ref:'v:2:assertion:A1'}, {ref:'v:1:question:A1'}, {ref:'v:1:signal:term:status'},
    {ref:'javascript:alert(1)'}, {ref:'https://example.com'},
  ]) {
    h.ctx.action = {type:'open_ref',label:'查看条目',...action};
    assert.equal(h.run('chatActionsHtml({version:1,actions:[action]},null,0)'), '', JSON.stringify(action));
  }
});

test('open_ref click rechecks an action and selects its version through existing citation navigation', () => {
  const h = harness();
  h.run(`S.viewNo=2; S.case.chat=[{role:'assistant',version:1,actions:[{type:'open_ref',label:'查看出处',ref:'R1'}]}];
    openRaw=id=>{globalThis.opened={id,version:ver().no}};`);
  h.click({act:'chat-action',index:'0',actionIndex:'0'});
  assert.deepEqual(h.read('opened'), {id:'R1',version:1});
  h.run(`delete globalThis.opened; S.case.versions[0].raw_ids=[]`);
  h.click({act:'chat-action',index:'0',actionIndex:'0'});
  assert.equal(h.run('typeof opened'), 'undefined');
  assert.match(h.run('notice'), /暂不可用/);
});

test('open_library is a user-triggered navigation and action labels are escaped', () => {
  const h = harness();
  h.run(`S.case.chat=[{role:'assistant',version:1,actions:[{type:'open_library',label:'<img src=x>'},{type:'unknown',label:'未知操作'}]}]`);
  const html = h.run('msgHtml(S.case.chat[0])');
  assert.match(html, /&lt;img src=x&gt;/);
  assert.doesNotMatch(html, /<img|未知操作/);
  assert.equal(h.ctx.location.hash, '#/case/c/v/1');
  h.click({act:'chat-action',index:'0',actionIndex:'0'});
  assert.equal(h.ctx.location.hash, '#/library');
});

test('term popup prepares a visible removable question without sending definition text or a request', async () => {
  const h = harness();
  const popup = h.run(`termPopHtml(termOf('status'),'credit.status')`);
  assert.match(popup, /data-act="ask-term" data-term="status" data-version="1" data-ref="credit.status"/);
  h.click({act:'ask-term',term:'status',version:'1',ref:'credit.status'});
  assert.equal(h.run('typeof sent'), 'undefined');
  assert.equal(h.node.value, '登记状态是什么意思？');
  const chip = h.run('selHtml()');
  assert.match(chip, /名词：登记状态 · 第 1 版/);
  assert.match(chip, /data-act="clear-term-context"/);
  await h.run(`ask('登记状态是什么意思？')`);
  assert.deepEqual(h.read('sent'), {text:'登记状态是什么意思？',refs:[],version:1,term_context:{term_id:'status',entry_ref:'credit.status'}});
  assert.doesNotMatch(h.run('JSON.stringify(sent)'), /旧版词条内容|新版词条内容|plain|aliases|draft/);
  assert.equal(h.run('S.termContext'), null);
  assert.equal(h.run('S.case.chat[0].term_context.term_id'), 'status');
  await h.run(`ask('你好')`);
  assert.equal(h.run('sent.term_context'), undefined);
});

test('term context clears for unrelated drafts, manual cancellation and report version changes', async () => {
  const h = harness();
  h.run(`prepareTermQuestion('status',1)`);
  h.listeners.input({target:{value:'今天天气怎么样',matches:()=>true}});
  assert.equal(h.run('S.termContext'), null);
  h.run(`prepareTermQuestion('status',1)`);
  h.click({act:'clear-term-context'});
  assert.equal(h.run('S.termContext'), null);
  h.run(`prepareTermQuestion('status',1); selectRefVersion(2)`);
  assert.equal(h.run('S.termContext'), null);
  h.run(`prepareTermQuestion('status',1)`);
  assert.equal(h.run('S.termContext'), null, 'stale popup cannot select a term from the prior version');
  h.run(`S.viewNo=1; prepareTermQuestion('status',1)`);
  await h.run(`ask('你好')`);
  assert.equal(h.run('sent.term_context'), undefined);
});

test('term context is one-shot but a failed request restores the exact context and retry identity', async () => {
  const h = harness();
  h.run(`globalThis.requests=[]; api=async(url, options)=>{requests.push({body:options.body,key:options.headers['Idempotency-Key']});throw new Error('断网')};
    prepareTermQuestion('status',1,'credit.status')`);
  await h.run(`ask('这个是什么意思？')`);
  assert.equal(h.run('S.termContext.term_id'), 'status');
  assert.equal(h.run(`pendingChat('c').body.term_context.entry_ref`), 'credit.status');
  await h.run(`ask('这个是什么意思？')`);
  const requests = h.read('requests');
  assert.deepEqual(requests[0], requests[1]);
  const persisted = JSON.parse(h.store.get('qier-chat:c'));
  assert.deepEqual(persisted.body.term_context, {term_id:'status',entry_ref:'credit.status'});
  h.run('pendingChats.clear()');
  assert.deepEqual(h.read(`pendingChat('c').body.term_context`), persisted.body.term_context);
});

test('cancelled term request never restores context after stopping the wait', async () => {
  const h = harness();
  h.run(`prepareTermQuestion('status',1); api=(url, options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('cancelled'))))`);
  const request = h.run(`ask('这个是什么意思？')`);
  h.click({act:'cancel-chat'});
  await request;
  assert.equal(h.run('S.termContext'), null);
  assert.equal(h.run(`pendingChat('c').body.term_context.term_id`), 'status');
});

test('late failure cannot restore a term cancelled by closing the assistant or replace a new term selection', async () => {
  for (const change of ["clearTermContext()", "prepareTermQuestion('judgment',1)"]) {
    const h = harness();
    h.run(`prepareTermQuestion('status',1); api=()=>new Promise((resolve,reject)=>{globalThis.rejectReply=reject})`);
    const request = h.run(`ask('这个是什么意思？')`);
    h.run(change);
    h.run(`rejectReply(new Error('断网'))`);
    await request;
    assert.equal(h.run('S.termContext?.term_id'), change.startsWith('clear') ? undefined : 'judgment');
  }
});

test('old saved requests without term_context remain readable and recover with GET only', async () => {
  const h = harness();
  h.run(`savePendingChat('c',{key:'legacy',body:{text:'原来的问题',refs:[],version:1}}); pendingChats.clear();
    globalThis.paths=[]; api=async(url, options)=>{paths.push({url,method:options.method || 'GET'});return url.includes('/requests/') ? {status:'complete'} : {...S.case,chat:[{role:'assistant',text:'保存的答复',version:1}]}}`);
  await h.run('recoverChat()');
  assert.deepEqual(h.read('paths.map(item=>item.method)'), ['GET','GET']);
  assert.equal(h.run('S.case.chat[0].text'), '保存的答复');
  assert.equal(h.run(`pendingChat('c')`), null);
});
