const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function harness() {
  const ctx = vm.createContext({console, URLSearchParams, FormData, AbortController, setTimeout:()=>0, clearTimeout(){},
    location:{hash:'#/case/test',search:''}, document:{querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener(){}}});
  for (const file of ['case-design.js','dossier/artwork.js','dossier-report.js','app.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8').replace(/boot\(\);\s*$/,''),ctx);
  }
  const run = code=>vm.runInContext(code,ctx);
  run(`S.case={id:'test',current:1,case:{company_name:'测试 <公司>'},versions:[],sources:{},raw:[]};
    S.viewNo=1; S.scenarios=[];
    globalThis.v={no:1,created_at:'2026-10-03',need:'核实付款',scenario:'general',glance:{first:[],short:{}},
      assertions:[],missing:[],signals:[],questions:[],charts:[],raw_ids:[],notes:[],terms:[],sources:{},onepager:null};
    S.case.versions=[v];`);
  return {ctx,run};
}
test('live questions keep arbitrary counts, full wording, escaping and original actions',()=>{
  const h=harness();
  for(const n of [0,1,7]) {
    h.ctx.n=n;
    h.run(`v.questions=Array.from({length:n},(_,i)=>({id:'Q'+i,ask:'请说明第'+i+'项 <条款> 的完整条件及对应合同位置'}))`);
    const html=h.run('dossierQuestions(v)');
    assert.equal((html.match(/data-act="question-detail"/g)||[]).length,n);
    assert.match(html,/建议后续询问/); assert.match(html,/data-kind="reply"/);
    if(n) {assert.match(html,/&lt;条款&gt; 的完整条件及对应合同位置/);assert.doesNotMatch(html,/<条款>/);}
  }
});
test('overview uses current version evidence, excludes reviews and separates pending work',()=>{
  const h=harness();
  h.run(`v.signals=[{key:'risk',items:[{key:'license',label:'许可',value:'待提供',status:'none',gap:'needs_input'},
    {key:'contract',label:'合同',value:'有差异',status:'bad'}]},
    {key:'credit',items:[{key:'status',label:'登记',value:'存续',status:'ok'}]},
    {key:'reputation',items:[{key:'user_reviews',status:'warn',value:'仅供参考'}]}];`);
  assert.deepEqual(JSON.parse(h.run('JSON.stringify(Object.fromEntries(Object.entries(dossierGroups(v)).map(([k,a])=>[k,a.length])))')),{problem:1,clear:1,open:1});
  let html=h.run('dossierOverview(v)');assert.match(html,/有异常，<\/span><span class="verdict-phrase">需注意风险/);assert.doesNotMatch(html,/仅供参考/);
  h.run(`v.glance.first=['risk.license']`);html=h.run('dossierOverview(v)');
  assert.match(html,/有异常，<\/span><span class="verdict-phrase">需注意风险/);assert.doesNotMatch(html,/id="verdict-title">可信度较高/);
  h.run(`v.glance.first=['credit.status']`);assert.match(h.run('dossierOverview(v)'),/有异常，<\/span><span class="verdict-phrase">需注意风险/);
});
test('signal folder counts actual backend items and preserves its full details action',()=>{
  const h=harness();h.run(`v.signals=[{key:'finance',title:'财务',lede:'未提供财报 <说明>',items:[{key:'cash',label:'现金流',status:'none',gap:'failed'}]}]`);
  const html=h.run('dossierSignal(v.signals[0],0,v)');
  assert.match(html,/内含 1 项核查记录/);assert.match(html,/没查成/);assert.match(html,/data-act="sigtile" data-key="finance"/);
  assert.match(html,/&lt;说明&gt;/);assert.doesNotMatch(html,/暂未见异常/);
});
test('live header binds every saved version and only flags demo evidence in the viewed version',()=>{
  const h=harness();h.run(`S.case.current=2;S.case.versions.push({...v,no:2});S.case.raw=[{id:'R1',kind:'demo',coverage:'found'}];v.raw_ids=['R1'];`);
  let html=h.run('dossierHero(S.case,v)');assert.match(html,/value="1" selected/);assert.match(html,/value="2"/);assert.match(html,/返回最新报告/);
  assert.match(html,/演示数据 · 公司为虚构/);assert.match(html,/测试 &lt;公司&gt;/);
  h.run('v.raw_ids=[]');assert.doesNotMatch(h.run('dossierHero(S.case,v)'),/公司为虚构/);
});
test('live reviews retain backend publishing and version refresh, with the opinion note last',()=>{
  const h=harness();h.run(`S.reviews={count:1,dist:{2:1},reviews:[{stars:2,nickname:'测试',relation_label:'客户',text:'体验 <描述>',created_at:'2026-10-03'}]}`);
  const html=h.run('dossierReviews(v)');
  assert.match(html,/id="rvForm"/);assert.match(html,/发布评价/);assert.match(html,/data-act="rv-refresh"/);
  assert.match(html,/体验 &lt;描述&gt;/);assert.doesNotMatch(html,/保存演示评价|还没有评价进这一版/);
  assert.ok(html.indexOf('review-opinion-note') > html.indexOf('体验 &lt;描述&gt;'));
});
test('full live report retains evidence, extra charts, changes, sources and photo entry points',()=>{
  const h=harness();h.run(`v.no=2;S.viewNo=2;S.case.current=2;v.changes=[];v.assertions=[];v.charts=[];`);
  const html=h.run('dossierReport(S.case,v)');
  for(const section of ['overview','signals','inquiry','details','changes','sources','versions']) assert.ok(html.includes('id="research-'+section+'"'),section);
  assert.match(html,/data-act="contract"/);assert.match(html,/data-act="supplement"/);
  assert.doesNotMatch(html,/远山科技|20 万元的软件服务|独立设计预览/);
});

test('timeline range includes future recorded dates instead of ending at query year',()=>{
  const h=harness();h.run(`v.charts=[{kind:'timeline',events:[{date:'2025-02-18',label:'成立'},{date:'2030-01-31',label:'认缴到期'}]}]`);
  assert.match(h.run('dossierTimeline(v)'),/2025 — 2030/);
});

test('production dossier assets contain no preview company or preview print footer',()=>{
  const root=path.join(__dirname,'..','dossier');
  for(const filename of fs.readdirSync(root).filter(name=>/\.(css|js)$/.test(name))) {
    assert.doesNotMatch(fs.readFileSync(path.join(root,filename),'utf8'),/远山科技|独立设计预览|127\.0\.0\.1:8010/,filename);
  }
});

test('overview replaces the numeric headline with escaped version-specific company keywords',()=>{
  const h=harness();
  h.run(`v.raw_ids=['R1'];v.onepager={headline:'材料核对：4项需重点核实'};
    v.company_keywords=[{label:'软件开发 <标签>',ref:'R1',basis:'登记范围'},
      {label:'不属于本版的资质',ref:'R2',basis:'其他版本'}]`);
  const html=h.run('dossierOverview(v)');
  assert.match(html,/公司关键词：/);
  assert.match(html,/软件开发 &lt;标签&gt;/);
  assert.match(html,/data-act="raw" data-ref="R1"/);
  assert.doesNotMatch(html,/材料核对：4项|不属于本版的资质/);
  h.run('v.company_keywords=[]');
  assert.match(h.run('dossierCompanyKeywords(v)'),/资料不足/);
  assert.doesNotMatch(h.run('dossierCompanyKeywords(v)'),/高新技术|天使轮/);
});


test('trust answer distinguishes missing evidence from a clear report and preserves issue priority',()=>{
  const h=harness();
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'资料较少，需警惕');
  h.run(`v.signals=[{key:'credit',items:[{key:'status',status:'ok'}]}]`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'可信度较高');
  h.run(`v.signals[0].items.push({key:'other',status:'none',gap:'not_covered'})`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'资料较少，需警惕');
  h.run(`v.signals[0].items[1]={key:'other',status:'none',gap:'failed'}`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'资料较少，需警惕');
  h.run(`v.signals[0].items[1]={key:'other',status:'warn'}`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'有异常，需注意风险');
  h.run(`v.signals[0].items[1]={key:'other',status:'miss'}`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'资料较少，需警惕');
  const html=h.run('dossierOverview(v)');
  assert.match(html,/这家公司是否值得你的信任/);
  assert.doesNotMatch(html,/结论仅限本版已查记录|id="verdict-scope"|这次合作，关键项有没有问题/);
});
