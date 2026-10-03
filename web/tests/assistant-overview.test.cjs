const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const node = {
    classList: { add() {}, remove() {}, contains() { return false; } },
    open: false, innerHTML: '', showModal() { this.open = true; },
  };
  const ctx = vm.createContext({
    console, FormData, AbortController, CSS: { escape: s => s },
    history: { replaceState() {} }, location: { hash: '#/case/c/v/2' },
    setTimeout: () => 0, clearTimeout() {},
    document: { querySelector: () => node, querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`S.case={id:'c',current:2,chat:[],raw:[
    {id:'R1',title:'旧版核实资料',source_id:'registry',kind:'official',content:'合成登记资料'},
    {id:'R2',title:'新版资料不可串入',source_id:'registry',kind:'official',content:'第二版'}
  ],sources:{registry:{name:'登记来源'}},versions:[
    {no:1,raw_ids:['R1'],signals:[{key:'credit',items:[{key:'status',label:'登记状态',refs:['R1']}]}],terms:[]},
    {no:2,raw_ids:['R2'],signals:[],terms:[]}
  ]}; S.viewNo=2;`);
  return { run, ctx, node };
}

test('overview has a report label and scope without template or fresh-reading claims', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'overview',answer_scope:'report_snapshot',
    mode:'template',context_mode:'selective',text:'本版报告记录的登记状态。[credit.status]',citations:['credit.status']},null,4)`);
  assert.match(html, /<span>本版报告概览<\/span>/);
  assert.match(html, /<span>依据已生成报告<\/span>/);
  assert.match(html, /基于第 1 版/);
  assert.doesNotMatch(html, /当前为基础答复|按需核对相关材料|\[credit.status\]/);
  assert.equal((html.match(/原文出处 ↗/g) || []).length, 1);
  assert.match(html, /data-act="chat-sources" data-index="4"/);
  assert.ok(html.indexOf('chat-source-footer') > html.indexOf('msg-meta'));
});

test('overview source button opens the source in its saved report version', () => {
  const h = harness();
  const before = h.run('JSON.stringify(S.case.versions)');
  h.run(`S.case.chat=[{role:'assistant',version:1,answer_kind:'overview',answer_scope:'report_snapshot',
    text:'报告记录。[credit.status]',citations:['credit.status','v:2:signal:credit:status']}]; openChatSources(0)`);
  assert.equal(h.node.open, true);
  assert.match(h.node.innerHTML, /原文出处 · 第 1 版/);
  assert.match(h.node.innerHTML, /旧版核实资料/);
  assert.match(h.node.innerHTML, /data-ref="R1" data-version="1"/);
  assert.doesNotMatch(h.node.innerHTML, /新版资料不可串入|data-ref="R2"/);
  assert.equal(h.run('S.viewNo'), 2);
  assert.equal(h.run('JSON.stringify(S.case.versions)'), before);
});

test('overview report-only references retain readable version-bound detail navigation', () => {
  const h = harness();
  h.run(`S.case.versions[0].missing=[{id:'M1',label:'付款条款待核对'}]`);
  const html = h.run(`chatSourcesHtml({version:1,answer_kind:'overview',citations:['M1']})`);
  assert.match(html, /报告条目（可能包含规则判断或待核实问题，不等于外部原文）/);
  assert.match(html, /查看报告条目：付款条款待核对/);
  assert.match(html, /data-id="M1" data-version="1"/);
});

test('overview prose and suggestions remain escaped and scope is never injected as markup', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'overview',
    answer_scope:'<img src=x onerror=bad()>',text:'<script>bad()</script>',suggest:['<svg onload=bad()>'],citations:[]})`);
  assert.doesNotMatch(html, /<script|<img|<svg|依据已生成报告|chat-sources/);
  assert.match(html, /&lt;script/);
  assert.match(html, /&lt;svg/);
});

test('overview label does not hide processing failures, source omissions, or replay provenance', () => {
  const h = harness();
  const failed = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'overview',answer_scope:'report_snapshot',
    mode:'guard',error_code:'evidence_coverage',not_found:true,text:'处理未完成'})`);
  assert.match(failed, /本次材料处理未完成，不是企业风险结论/);
  assert.doesNotMatch(failed, /部分信息仍待核实/);
  const filtered = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'overview',answer_scope:'report_snapshot',
    has_omitted_claims:true,text:'支持的概览'})`);
  assert.match(filtered, /部分表述未获依据支持，已省略/);
  const replay = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'overview',answer_scope:'report_snapshot',
    mode:'replay',text:'回放的报告概览'})`);
  assert.match(replay, /本版报告概览/);
  assert.match(replay, /离线回放/);
});

test('existing explanation, clarification and normal selective responses retain their labels', () => {
  const h = harness();
  const glossary = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'glossary',mode:'template',text:'词语解释'})`);
  const clarification = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'clarification',mode:'template',text:'确认需求'})`);
  assert.match(glossary, /名词解释/);
  assert.match(clarification, /先确认需求/);
  assert.doesNotMatch(glossary + clarification, /当前为基础答复|本版报告概览|依据已生成报告/);
  const normal = h.run(`msgHtml({role:'assistant',version:1,mode:'template',context_mode:'selective',text:'正常回退'})`);
  assert.match(normal, /当前为基础答复/);
  assert.match(normal, /按需核对相关材料/);
});

test('identical fast overview replies from distinct requests are not swallowed', async () => {
  const h = harness();
  h.run(`refreshChat=()=>{}; refreshSel=()=>{}; toast=()=>{};
    api=async(url,opts)=>({role:'assistant',version:2,text:'相同的报告概览',answer_kind:'overview',
      created_at:'2026-10-04T03:00:00',request_id:opts.headers['Idempotency-Key']});`);
  await h.run(`ask('你觉得它怎么样')`);
  await h.run(`ask('你觉得这家公司怎么样')`);
  assert.equal(h.run(`S.case.chat.filter(m=>m.role==='assistant').length`), 2);
  assert.equal(h.run(`new Set(S.case.chat.filter(m=>m.role==='assistant').map(m=>m.request_id)).size`), 2);
  assert.equal(h.run(`S.case.chat.every(m=>!!m.request_id)`), true);
});

test('reloading the same identified request still does not duplicate either turn', async () => {
  const h = harness();
  h.run(`refreshChat=()=>{}; refreshSel=()=>{}; toast=()=>{};
    api=(url,opts)=>new Promise(resolve=>{globalThis.resolveReply=resolve;globalThis.sentKey=opts.headers['Idempotency-Key']});`);
  const pending = h.run(`ask('你觉得它怎么样')`);
  h.run(`globalThis.reply={role:'assistant',version:2,text:'概览',created_at:'2026-10-04T03:00:00',request_id:sentKey};
    S.case={...S.case,chat:[{...S.case.chat[0],created_at:reply.created_at},{...reply}]}; resolveReply(reply);`);
  await pending;
  assert.equal(h.run('S.case.chat.length'), 2);
});
