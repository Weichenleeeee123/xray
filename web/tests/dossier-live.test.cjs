const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function harness() {
  const ctx = vm.createContext({console, URLSearchParams, FormData, AbortController, setTimeout:()=>0, clearTimeout(){},
    location:{hash:'#/case/test',search:''}, document:{querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener(){}}});
  for (const file of ['case-design.js','dossier/artwork.js','dossier-report.js','material-analysis.js','app.js']) {
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
test('overview uses the server snapshot for the verdict, all four counts and evidence links',()=>{
  const h=harness();
  h.run(`v.glance.first=['credit.status'];
    v.overview={schema_version:1,status:'warn',trust_level:'high',trust_label:'信任度较高',trust_note:'个别事项仍需核实',headline:'信任度较高，个别事项仍需核实',detail:'2 项正常；1 项一般关注；1 项待核实。',
      counts:{normal:2,attention:1,abnormal:0,unknown:1},items:[
      {id:'credit.status',label:'登记状态',text:'存续',status:'ok',category:'normal',axis:'basics'},
      {id:'credit.penalties',label:'处罚查询',text:'未见记录',status:'ok',category:'normal',axis:'stability'},
      {id:'reputation.news_negative',label:'舆情关注',text:'时间待核实 <报道>',status:'warn',category:'attention',axis:'news'},
      {id:'finance.annual',label:'年报',text:'本次未查成',status:'none',gap:'failed',category:'unknown',axis:'funds'}]};`);
  const groups=JSON.parse(h.run('JSON.stringify(Object.fromEntries(Object.entries(dossierGroups(v)).map(([k,a])=>[k,a.length])))'));
  assert.deepEqual(groups,{normal:2,attention:1,abnormal:0,unknown:1});
  const html=h.run('dossierOverview(v)');
  assert.match(html,/class="trust-label">信任度较高/);assert.match(html,/class="trust-note">个别事项仍需核实/);assert.match(html,/data-trust-level="high"/);
  assert.match(html,/4 项公司记录/);assert.doesNotMatch(html,/有异常，需注意风险|资料较少，需警惕/);
  assert.match(html,/data-group="attention"/);assert.match(html,/data-id="reputation.news_negative"/);
  assert.match(html,/时间待核实 &lt;报道&gt;/);
  for(const [key,count] of Object.entries(groups)) assert.match(html,new RegExp('class="verdict-count '+key+'"[^>]*data-count="'+count+'"'));
  const axes=JSON.parse(h.run('JSON.stringify(researchRadarAxes(v))'));
  assert.equal(axes.find(a=>a.id==='news').status,'warn');
  assert.equal(axes.find(a=>a.id==='funds').failed,true);
  assert.equal(axes.reduce((n,a)=>n+a.checked+a.unchecked,0),4);
});
test('signal folder counts actual backend items and preserves its full details action',()=>{
  const h=harness();h.run(`v.signals=[{key:'finance',title:'财务',lede:'未提供财报 <说明>',items:[{key:'cash',label:'现金流',status:'none',gap:'failed'}]}]`);
  const html=h.run('dossierSignal(v.signals[0],0,v)');
  assert.match(html,/内含 1 项核查记录/);assert.match(html,/未查成/);assert.match(html,/data-act="sigtile" data-key="finance"/);
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

test('timeline gives each node a separate decorative track and retains full event labels and source actions',()=>{
  const h=harness();h.run(`v.charts=[{kind:'timeline',events:[{date:'2025-02-18',label:'记录 <一>',ref:'R1'},{date:'2025-02-18',label:'同日另一条记录',ref:'R2'}]}]`);
  const html=h.run('dossierTimeline(v)');
  assert.equal((html.match(/class="timeline-axis" aria-hidden="true"/g)||[]).length,2);
  assert.equal((html.match(/aria-pressed="true"/g)||[]).length,1);
  assert.match(html,/记录 &lt;一&gt;/);assert.match(html,/同日另一条记录/);
  assert.match(html,/data-ref="R1"/);
  h.run('v.charts=[]');assert.match(h.run('dossierTimeline(v)'),/暂无有日期的事件记录/);
});

test('signal sources retain exact original-record actions and dates while separating the action visually',()=>{
  const h=harness();h.run(`v.sources={commercial:{name:'商业数据',kind:'commercial',as_of:'2026-10-01'}};S.case.sources=v.sources;v.raw_ids=['R1'];S.case.raw=[{id:'R1',source_id:'commercial',kind:'commercial',as_of:'2026-10-02',title:'原始记录'}]`);
  const html=h.run(`srcLink('commercial','R1',true)`);
  assert.match(html,/class="signal-source-meta"/);assert.match(html,/class="signal-source-action">查看出处/);
  assert.match(html,/data-act="raw" data-ref="R1"/);assert.match(html,/2026-10-02/);assert.doesNotMatch(html,/2026-10-01/);
  assert.doesNotMatch(h.run(`srcLink('commercial','R1')`),/signal-source-action/);
  assert.match(h.run(`srcLink('commercial',null,true)`),/data-act="src"/);
});

test('signal selection labels can be explicit without changing the original selection contract',()=>{
  const h=harness();let html=h.run(`askBtn('credit.penalty','问小企')`);
  assert.match(html,/data-act="sel" data-id="credit.penalty"/);assert.match(html,/data-idle-label="问小企"/);
  assert.match(html,/>问小企<\/button>/);
  h.run(`S.selected.add('credit.penalty')`);
  assert.match(h.run(`askBtn('credit.penalty','问小企')`),/aria-pressed="true"[^>]*>已选<\/button>/);
  assert.match(h.run(`askBtn('credit.status')`),/>问<\/button>/);
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


test('browser never substitutes an optimistic or alarming verdict for the backend snapshot',()=>{
  const h=harness();
  h.run(`v.signals=[{key:'credit',items:[{key:'status',status:'ok'}]}]`);
  assert.equal(h.run('dossierTrustAnswer(v)[1]'),'概况待更新，请刷新报告');
  for(const [status,headline] of [['ok','信任度较高，已查信息未见明显异常'],['none','资料较少，需谨慎判断'],['bad','信任度较低，需要注意风险']]) {
    h.ctx.snapshot={schema_version:1,status,headline,detail:'说明 <范围>',items:[],counts:{normal:0,attention:0,abnormal:0,unknown:0}};
    h.run('v.overview=snapshot');
    assert.equal(h.run('dossierTrustAnswer(v)[1]'),headline);
    const html=h.run('dossierOverview(v)');
    assert.match(html,/这家公司是否值得你的信任/);
    assert.match(html,/说明 &lt;范围&gt;/);
    assert.doesNotMatch(html,/结论仅限本版已查记录|可信度较高|资料较少，需警惕/);
  }
});

test('materials and user opinions cannot overwrite a company overview or its radar',()=>{
  const h=harness();h.run(`v.signals=[{key:'risk',items:[{key:'payee',status:'bad',source:'material'}]},
    {key:'reputation',items:[{key:'user_reviews',status:'warn'}]}];
    v.overview={schema_version:1,status:'ok',trust_level:'high',trust_label:'信任度较高',trust_note:'已查信息未见明显异常',headline:'信任度较高，已查信息未见明显异常',detail:'1 项正常',counts:{normal:1,attention:0,abnormal:0,unknown:0},
      items:[{id:'credit.status',label:'登记',text:'存续',status:'ok',category:'normal',axis:'basics'}]};`);
  assert.equal(h.run('dossierTrustAnswer(v)[0]'),'ok');
  assert.equal(h.run("researchRadarAxes(v).find(a=>a.id==='qualify').checked"),0);
  assert.equal(h.run("researchRadarAxes(v).find(a=>a.id==='news').checked"),0);
  assert.equal(h.run('dossierFindings(v).length'),1);
});

test('saved material analyses are placed after inquiry features and before company details',()=>{
 const h=harness();
 h.run(`S.case.material_analyses=[{id:'MA2',report_version:2,title:'合同',summary:'待核实',raw_ids:[]}];`);
 const html=h.run('dossierReport(S.case,v)');
 assert.ok(html.indexOf('class="ma-archive"')>html.indexOf('class="recheck-grid"'));
 assert.ok(html.indexOf('class="ma-archive"')<html.indexOf('id="research-details"'));
 assert.match(html,/data-analysis="MA2"/);
});

test('an inapplicable licence is labelled explicitly and does not increase cleared signal counts',()=>{
  const h=harness();
  assert.equal(h.run("stLabel({status:'ok',gap:'not_applicable'})"),'不适用');
  h.run(`v.signals=[{key:'risk',title:'风险',lede:'',items:[{key:'bank_list',status:'ok'},
    {key:'amac',status:'ok',gap:'not_applicable'}]}]`);
  assert.match(h.run('dossierSignal(v.signals[0],0,v)'),/1 项已核验/);
  assert.doesNotMatch(h.run('dossierSignal(v.signals[0],0,v)'),/2 项已核验/);
});

test('degree, qualifier and tone come from structured backend fields, including low trust and insufficient data',()=>{
  const h=harness();
  for(const [level,label,note,status] of [
    ['high','信任度较高','个别事项仍需核实','warn'],
    ['pending','信任度待确认','建议先核实关键事项','warn'],
    ['low','信任度较低','需要注意风险','bad'],
    ['unknown','资料较少','需谨慎判断','warn']]) {
    h.ctx.result={schema_version:1,status,trust_level:level,trust_label:label,trust_note:note,
      headline:label+'，'+note,detail:'核查范围',items:[],counts:{normal:0,attention:0,abnormal:0,unknown:0}};
    h.run('v.overview=result');
    const html=h.run('dossierOverview(v)');
    assert.ok(html.includes('data-trust-level="'+level+'"'));
    assert.ok(html.includes('<span class="trust-label">'+label+'</span>'));
    assert.ok(html.includes('<span class="trust-note">'+note+'</span>'));
    assert.doesNotMatch(html,/has-normal-basics|基础核查正常|信任度\d+|可信度较高/);
  }
  h.run(`v.overview.trust_label='资料 <标记>';v.overview.trust_note='待核实 <说明>'`);
  const html=h.run('dossierOverview(v)');
  assert.match(html,/资料 &lt;标记&gt;/);assert.match(html,/待核实 &lt;说明&gt;/);
});

test('insufficient core evidence opens the uncovered records even when another record needs attention',()=>{
  const h=harness();
  h.run(`v.overview={schema_version:1,status:'warn',trust_level:'unknown',trust_label:'资料较少',trust_note:'需谨慎判断',
    headline:'资料较少，需谨慎判断',detail:'核心资料仍有缺口',counts:{normal:1,attention:1,abnormal:0,unknown:1},items:[
    {id:'credit.status',label:'登记状态',text:'存续',status:'ok',category:'normal',axis:'basics'},
    {id:'credit.dishonest',label:'失信核查',text:'未覆盖',status:'none',category:'unknown',axis:'stability'},
    {id:'reputation.news',label:'报道',text:'需了解',status:'warn',category:'attention',axis:'news'}]}`);
  const html=h.run('dossierOverview(v)');
  assert.match(html,/data-inspection="unknown"/);
  assert.match(html,/data-group="unknown" aria-controls="dossier-inspection">查看判断依据/);
  assert.match(html,/data-id="credit.dishonest"/);
});
