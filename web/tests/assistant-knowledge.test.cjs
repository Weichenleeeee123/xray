const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const node = { classList: { add() {}, remove() {}, contains() { return false; } } };
  const ctx = vm.createContext({
    console, FormData, AbortController, CSS: { escape: s => s },
    history: { replaceState() {} }, location: { hash: '#/case/c/v/2' },
    setTimeout: () => 0, clearTimeout() {},
    document: { querySelector: () => node, querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`S.case={id:'c',current:2,chat:[],raw:[],sources:{},versions:[
    {no:1,signals:[],terms:[{id:'status',term:'登记状态',plain:'旧报告定义'}]},
    {no:2,signals:[],terms:[{id:'status',term:'登记状态',plain:'新报告定义'}]}
  ]}; S.viewNo=2;
  S.terms=[{id:'status',term:'登记状态',plain:'现行通用定义'},
    {id:'judgment',term:'裁判文书',plain:'经核对的裁判文书定义',why:'不等于公司有过错。'}];`);
  return { run, ctx };
}

test('knowledge source uses the answer snapshot before historical and live glossary definitions', () => {
  const h = harness();
  const before = h.run('JSON.stringify(S.case.versions)');
  const html = h.run(`chatSourcesHtml({version:1,citations:['term.status'],knowledge_terms:[
    {id:'status',term:'登记状态',plain:'本次解释保存的定义',why:'仅是登记信息，不说明偿付能力。',law:'本次说明依据'}
  ]})`);
  assert.match(html, /本次解释保存的定义/);
  assert.match(html, /仅是登记信息，不说明偿付能力/);
  assert.match(html, /本次说明依据/);
  assert.match(html, /通用名词解释，不代表企业情况/);
  assert.doesNotMatch(html, /旧报告定义|新报告定义|现行通用定义/);
  assert.equal(h.run('JSON.stringify(S.case.versions)'), before);
  assert.equal(h.run('S.viewNo'), 2);
});

test('legacy answers retain historical definitions instead of current definitions', () => {
  const h = harness();
  const html = h.run(`chatSourcesHtml({version:1,citations:['term.status']})`);
  assert.match(html, /旧报告定义/);
  assert.doesNotMatch(html, /新报告定义|现行通用定义/);
});

test('absent terms fall back to the fixed glossary even when the selected version has other terms', () => {
  const h = harness();
  const html = h.run(`chatSourcesHtml({version:1,citations:['term.judgment'],knowledge_terms:[]})`);
  assert.match(html, /经核对的裁判文书定义/);
  assert.match(html, /不等于公司有过错/);
  assert.doesNotMatch(html, /旧报告定义/);
});

test('knowledge snapshots escape all displayed prose and preserve model provenance', () => {
  const h = harness();
  const html = h.run(`chatSourcesHtml({version:1,citations:['term.x'],knowledge_terms:[
    {id:'x',term:'<img src=x>',plain:'<script>bad()</script>',why:'<button>假的操作</button>',law:'<svg onload=bad()>'}
  ]})`);
  assert.doesNotMatch(html, /<img|<script|<button|<svg/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;button/);
  const model = h.run(`chatSourcesHtml({version:1,citations:['term.x'],knowledge_terms:[
    {id:'x',term:'例词',plain:'解释',origin:'model'}
  ]})`);
  assert.match(model, /AI 解释，未经人工核对/);
});

test('glossary answers have an explanation label and one bottom source entry, not template failure copy', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'glossary',mode:'template',
    text:'存续说的是登记状态。[term.status]',citations:['term.status'],knowledge_terms:[
      {id:'status',term:'登记状态',plain:'出处中才显示的细节'}
    ]},null,5)`);
  assert.match(html, /<span>名词解释<\/span>/);
  assert.equal((html.match(/原文出处 ↗/g) || []).length, 1);
  assert.match(html, /data-act="chat-sources" data-index="5"/);
  assert.doesNotMatch(html, /当前为基础答复|出处中才显示的细节|\[term.status\]/);
  assert.ok(html.indexOf('chat-source-footer') > html.indexOf('msg-meta'));
});

test('clarification answers show the scope label without fabricated source navigation', () => {
  const h = harness();
  const html = h.run(`msgHtml({role:'assistant',version:1,answer_kind:'clarification',mode:'template',
    text:'你是指买股票还是购买产品？',citations:[]})`);
  assert.match(html, /<span>先确认需求<\/span>/);
  assert.doesNotMatch(html, /当前为基础答复|chat-sources|原文出处/);
});

test('existing templates and replay disclosure remain visible without invented labels', () => {
  const h = harness();
  assert.match(h.run(`msgHtml({role:'assistant',version:1,mode:'template',text:'原有兜底'})`), /当前为基础答复/);
  const replay = h.run(`msgHtml({role:'assistant',version:1,mode:'replay',answer_kind:'glossary',text:'解释'})`);
  assert.match(replay, /名词解释/);
  assert.match(replay, /离线回放/);
  assert.doesNotMatch(h.run(`msgHtml({role:'assistant',version:1,mode:'model',answer_kind:'<img src=x>',text:'答复'})`), /<img|先确认需求|名词解释/);
});

test('knowledge snapshots cannot expose uncited terms or cross-version source records', () => {
  const h = harness();
  assert.equal(h.run(`chatSourcesHtml({version:1,citations:['term.missing'],knowledge_terms:[
    {id:'secret',term:'未引用词语',plain:'不应该出现'}
  ]})`), '');
  const absent = h.run(`chatSourcesHtml({version:99,citations:['term.status'],knowledge_terms:[
    {id:'status',term:'登记状态',plain:'不应该出现'}
  ]})`);
  assert.match(absent, /报告版本暂不可用/);
  assert.doesNotMatch(absent, /不应该出现/);
});
