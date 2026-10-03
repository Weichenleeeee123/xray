const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { innerHTML: '', textContent: '', isConnected: true,
      dataset: {}, hidden: true, open: true, value: '', focus(){}, setAttribute(){}, close() { this.open = false; }, showModal(){this.open=true;}, append() {}, remove() {}, addEventListener() {},
      classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } }, querySelector: () => null });
    return nodes.get(selector);
  }
  const sent = [], stops = [];
  let resolveRequest, rejectRequest;
  const store=new Map();
  const ctx = vm.createContext({ console, FormData, AbortController, URLSearchParams, CSS: { escape: s => s },
    localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},crypto:{randomUUID:()=> 'test-key'},
    taskApi:(url,opts)=>{if(opts?.method==='POST'){sent.push({url,body:opts.body,headers:opts.headers});return new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject})}
      return Promise.resolve(url.includes('/api/runs/')?{run_id:'a'.repeat(24),status:'complete',case_id:'c',version:2,events:[],next:0}:{id:'c',case:{company_name:'测试公司'},current:3,versions:[{no:1},{no:2},{no:3}],material_analyses:[{id:'MA2',report_version:2,title:'合同',summary:'需要核实',raw_ids:[],findings:[]}]});},
    location: { hash: '#/check', search: '' }, history: { replaceState() {} },
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
    document: { body: node('body'), querySelector: node, querySelectorAll: () => [], addEventListener() {}, createElement: () => node('progress') },
    MaterialAnalysis: {...require('../material-analysis.js'), mount:()=>({onEvent(){},stop(){stops.push(true)},error(terminal){node('#material-status').textContent=terminal?'分析未完成':'连接中断，进度待确认'}})},
    ResearchProgress: {
      mount: () => ({ onEvent() {}, stop() { stops.push(true); } }),
      readCaseStream: (url, body) => { sent.push({ url, body }); return new Promise((resolve, reject) => { resolveRequest = resolve; rejectRequest = reject; }); },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../case-design.js'), 'utf8'), ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../supplement-runs.js'), 'utf8'), ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8').replace(/boot\(\);\s*$/, ''), ctx);
  const run = code => vm.runInContext(code, ctx);
  run(`toast=()=>{}; bindForm=()=>{}; renderCase=()=>{}; intakeHtml=()=>'';
    api=taskApi;`);
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
  assert.equal(h.node('#caseForm').company.value, input.company_name);
  assert.equal(h.node('#caseForm').need.value, input.need);
  assert.match(h.node('#formErr').textContent, /连接已结束/);
  assert.equal(h.run('S.creating'), false);
  assert.equal(h.stops.length, 1);
});

test('supplement saves its appendix and displays the result without changing the report route', async () => {
  const h = harness();
  h.run(`S.case={id:'c',case:{company_name:'测试公司'}}; location.hash='#/case/c';`);
  h.node('#supDlg').dataset.kind = 'material';
  h.run(`globalThis.progressContainer=''; globalThis.form={text:{value:'补充合同原文'},title:{value:'合同'},isConnected:true,
    append(){progressContainer='form'},querySelector(selector){return {append(){progressContainer=selector},scrollTop:0,scrollHeight:800}}};`);
  const pending = h.run(`submitSupplement({preventDefault(){},target:form})`);
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0].url, '/api/cases/c/runs');
  assert.equal(h.sent[0].headers['Idempotency-Key'],'test-key');
  assert.equal(h.sent[0].body.text, '补充合同原文');
  assert.match(h.node('#supDlg').innerHTML, /supProgress/);
  h.resolve({run_id:'a'.repeat(24)}); await pending;
  assert.equal(h.run('location.hash'), '#/case/c');
  assert.equal(h.node('#supDlg').open, true);
  assert.match(h.node('#supDlg').innerHTML,/收起材料分析/);
  assert.equal(h.run(`pendingSupplement('c')`),null);
  assert.equal(h.stops.length, 1);
});

test('returning to a case automatically recovers its pending supplement',async()=>{
 const h=harness();h.run(`S.case={id:'c',current:1,versions:[{no:1}],case:{company_name:'测试公司'}};location.hash='#/case/c';
 localStorage.setItem('qier.supplement.v1:c',JSON.stringify({caseId:'c',requestKey:'old',runId:'${'a'.repeat(24)}',body:{kind:'material',text:'原材料'}}));`);
 await h.run('openCase("c")');
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.equal(h.sent.length,0);assert.equal(h.run('location.hash'),'#/case/c');
});
test('a completed supplement does not hijack another case and stays recoverable',async()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'}};location.hash='#/case/c';`);
 h.node('#supDlg').dataset.kind='material';
 const work=h.run(`submitSupplement({preventDefault(){},target:{text:{value:'合同'},title:{value:''},querySelector(){return {append(){}}}}})`);
 h.run(`location.hash='#/case/other';S.case={id:'other'};`);
 h.resolve({run_id:'a'.repeat(24)});await work;
 assert.equal(h.run('location.hash'),'#/case/other');assert.equal(h.run('S.case.id'),'other');
 assert.ok(h.run(`JSON.parse(localStorage.getItem('qier.supplement.v1:c'))?.runId`));
});
test('lost submission response exposes recovery and reuses the saved body',async()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'}};location.hash='#/case/c';`);
 h.node('#supDlg').dataset.kind='material';
 const work=h.run(`submitSupplement({preventDefault(){},target:{text:{value:'原合同'},title:{value:''},querySelector(){return {append(){}}}}})`);
 h.reject(new Error('offline'));await work;
 assert.equal(h.node('#supResume').hidden,false);assert.match(h.node('#supErr').textContent,/offline/);
 assert.equal(h.node('#material-status').textContent,'连接中断，进度待确认');
 const retry=h.run('resumeSupplement()');
 assert.equal(h.sent.length,2);assert.equal(h.sent[1].body.text,'原合同');
 assert.equal(h.sent[0].headers['Idempotency-Key'],h.sent[1].headers['Idempotency-Key']);
 h.resolve({run_id:'a'.repeat(24)});await retry;
 assert.equal(h.run('location.hash'),'#/case/c');
});

test('completion while collapsed saves an entry without reopening the dialog or resubmitting',async()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'}};location.hash='#/case/c';`);
 h.node('#supDlg').dataset.kind='material';
 const work=h.run(`submitSupplement({preventDefault(){},target:{text:{value:'合同'},title:{value:''}}})`);
 h.node('#supDlg').close();h.resolve({run_id:'a'.repeat(24)});await work;
 assert.equal(h.run('location.hash'),'#/case/c');assert.equal(h.run(`pendingSupplement('c')`),null);
 assert.equal(h.node('#supDlg').open,false);
 h.run(`openMaterialAnalysis('MA2')`);assert.equal(h.sent.length,1);assert.equal(h.node('#materialDlg').open,true);
 assert.match(h.node('#materialDlg').innerHTML,/合同/);
});
test('aborting an old watcher cannot clear the busy state of its replacement',async()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'}};location.hash='#/case/c';`);
 h.node('#supDlg').dataset.kind='material';
 const old=h.run(`submitSupplement({preventDefault(){},target:{text:{value:'合同'},title:{value:''}}})`);
 h.run('stopSupplementWatch()');h.resolve({run_id:'a'.repeat(24)});
 h.run('S.supplementRequest=new AbortController();S.supplementBusy=true');await old;
 assert.equal(h.run('S.supplementBusy'),true);assert.equal(h.run('location.hash'),'#/case/c');assert.ok(h.run(`pendingSupplement('c')`));
});

test('confirmed terminal failure restores original material for an explicit fresh submission',async()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'}};location.hash='#/case/c';
 api=async()=>{throw Object.assign(new Error('材料过长'),{status:422})};
 globalThis.edited=null;openSupplement=body=>{edited=body};`);
 h.node('#supDlg').dataset.kind='need';h.node('#supDlg').dataset.scen='job';
 await h.run(`submitSupplement({preventDefault(){},target:{text:{value:'我想入职'},title:{value:''}}})`);
 assert.equal(h.node('#supEdit').hidden,false);assert.ok(h.run(`pendingSupplement('c')`));
 h.run('editFailedSupplement()');assert.equal(h.run('edited.text'),'我想入职');
 assert.equal(h.run('edited.scenario'),'job');assert.equal(h.run(`pendingSupplement('c')`),null);
 assert.equal(h.sent.length,0,'editing does not submit another task');
});

test('editing a recovered need visibly restores its selected scenario',()=>{
 const h=harness();h.run(`S.case={id:'c',case:{company_name:'测试公司'},versions:[{no:1}]};S.scenarios=[{id:'job',label:'入职'}];
 openSupplement({kind:'need',text:'原需求',scenario:'job'});`);
 assert.equal(h.node('#supDlg').dataset.scen,'job');
 assert.match(h.node('#supDlg').innerHTML,/data-id="job" aria-pressed="true"/);
});

test('a duplicate supplement submission explains that the previous request is still running', async () => {
  const h = harness();
  h.run(`S.supplementBusy=true; globalThis.notice=''; toast=message=>{notice=message};`);
  await h.run(`submitSupplement({preventDefault(){}})`);
  assert.equal(h.sent.length, 0);
  assert.match(h.run('notice'), /正在|稍候/);
});
