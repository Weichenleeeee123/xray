const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function harness(){
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ctx=vm.createContext({document:{querySelector:()=>null,addEventListener(){}},esc:escape,termText:escape,
 FLAG:new Set(['bad','warn','miss']),SEV:{bad:4,warn:3,miss:2,none:1,ok:0},selCls:()=>'',chgTag:()=>'',askBtn:()=>'',stLabel:i=>i.status,
 srcLink:(s,r)=>`<button data-ref="${escape(r)}">${escape(s)}</button>`,sigExtra:()=>'',KIND:{official:'官方记录'},COVERAGE:{found:'查到了'},
 versionRaws:v=>v.raws,srcOf:id=>({name:id,kind:'official'})});
 // Gap helpers live in app.js; load exactly those definitions so the radar is tested with the real wording.
 const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
 const start=app.indexOf('const GAP = '), end=app.indexOf('const stLabel = ');
 vm.runInContext(app.slice(start,end).replace(/^const /gm,'var ').replace(/^function /gm,'function '),ctx);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../case-design.js'),'utf8'),ctx);
 return {ctx,run:code=>vm.runInContext(code,ctx)};
}
test('dated repeated records keep every entry and the qualifying explanation',()=>{
 const h=harness();h.ctx.detail='质押不说明公司缺钱；需看比例。'+Array.from({length:19},(_,i)=>`2016-09-08，公司${i}把 ${i}.5押给「银行」`).join('；');
 const parts=JSON.parse(h.run('JSON.stringify(researchDetailParts(detail))'));
 assert.equal(parts.intro,'质押不说明公司缺钱；需看比例。');assert.equal(parts.records.length,19);
 const html=h.run('researchItemDetail(detail,new Set())');
 assert.equal((html.match(/<li>/g)||[]).length,19);assert.match(html,/展开其余 16 条记录/);
 assert.equal((html.split('<details')[0].match(/<li>/g)||[]).length,3);
 parts.records.forEach(record=>assert.ok(html.includes(record.replace(/^2016-09-08，/,''))));
});
test('ordinary prose containing a date is not broken into a record list',()=>{
 const h=harness();h.ctx.detail='成立于 1996-09-25，30 年 0 个月';
 const result=JSON.parse(h.run('JSON.stringify(researchDetailParts(detail))'));
 assert.equal(result.intro,h.ctx.detail);assert.equal(result.records.length,0);
});
test('all signal items are visible; priority items precede ok and uncovered records',()=>{
 const h=harness();h.ctx.sig={key:'finance',title:'财务',lede:'说明',items:[{key:'ok',status:'ok',label:'正常',value:'无',ref:'R1'},{key:'none',status:'none',label:'未查',value:'未覆盖',ref:'R2'},{key:'bad',status:'bad',label:'异常',value:'5 条',ref:'R3'}]};
 const html=h.run('researchSignalCard(sig,{}, {})');
 assert.equal((html.match(/<article/g)||[]).length,3);assert.ok(html.indexOf('finance.bad')<html.indexOf('finance.none'));assert.ok(html.indexOf('finance.none')<html.indexOf('finance.ok'));
 assert.doesNotMatch(html,/<details|data-act="rest"/);for(const ref of ['R1','R2','R3'])assert.ok(html.includes(ref));
});
test('question cards use the current company output for zero, one and seven questions',()=>{
 const h=harness();
 for(const count of [0,1,7]){
  h.ctx.v={questions:Array.from({length:count},(_,i)=>({ask:`公司 ${i} 的许可证有效期？`}))};
  const html=h.run('researchQuestions(v)');assert.equal((html.match(/data-act="question-detail"/g)||[]).length,count);assert.ok(html.includes(`${count} 个问题`));
  h.ctx.v.questions.forEach(q=>assert.ok(html.includes(q.ask)));
 }
 h.ctx.v={questions:[{ask:'<script>测试</script>？'}]};assert.doesNotMatch(h.run('researchQuestions(v)'),/<script>/);
});
test('sources start in one closed disclosure and retain every underlying record',()=>{
 const h=harness();h.ctx.v={raws:Array.from({length:10},(_,i)=>({id:`R${i}`,source_id:`来源${i}`,kind:'official',title:`记录${i}`,coverage:'found'}))};
 const html=h.run('researchSources(v)');
 assert.match(html,/<details class="source-collection"><summary>/);
 assert.equal((html.split('<details class="source-collection">')[0].match(/class="source-entry"/g)||[]).length,0);
 assert.equal((html.match(/class="source-entry"/g)||[]).length,10);
 assert.doesNotMatch(html,/source-record-id|<details[^>]*\bopen\b/);
 h.ctx.v.raws.forEach(r=>assert.ok(html.includes(`data-ref="${r.id}"`)));
});
test('flow response starts at the leading edge and fades smoothly after the bubble',()=>{
 const h=harness();
 const pulse=p=>h.run(`researchFlowPulse(${p},10,30)`);
 assert.equal(pulse(9.9),0);assert.equal(pulse(10),0);
 assert.ok(pulse(10.2)>0,'responds just after touching the edge');
 assert.ok(pulse(13)>0.9,'is already bright before reaching the bubble centre');
 assert.equal(pulse(20),1);assert.equal(pulse(30),1);
 assert.ok(pulse(30.2)>0.99,'does not flash off on exit');
 assert.ok(pulse(36)>0 && pulse(36)<1);assert.equal(pulse(42),0);
 const samples=Array.from({length:501},(_,i)=>pulse(i/10));
 assert.ok(samples.every(p=>p>=0 && p<=1));
 assert.ok(samples.slice(1).every((p,i)=>Math.abs(p-samples[i])<0.05),'has no sudden jumps');
});
test('radar axes use every signal item once and an unchecked item does not hide checked ones',()=>{
 const h=harness();
 const items=(sts,prefix='x')=>sts.map((status,i)=>({key:`${prefix}${i}`,status,label:`${prefix}${i}`}));
 h.ctx.v={signals:[
  {key:'risk',items:[...items(['warn','warn','none','warn'],'q'),{key:'controller',status:'ok'},{key:'promise',status:'bad'}]},
  {key:'finance',items:[...items(['ok','ok','ok','ok','ok','ok','ok','ok','ok','ok','ok'],'f'),{key:'pledges',status:'none'},{key:'paid_capital',status:'ok'}]},
  {key:'credit',items:[{key:'status',status:'ok'},{key:'penalties',status:'bad'},{key:'lawsuits',status:'none'}]},
  {key:'reputation',items:[]}]};
 const axes=JSON.parse(h.run('JSON.stringify(researchRadarAxes(v))'));
 const by=Object.fromEntries(axes.map(a=>[a.label,a]));
 assert.deepEqual(axes.map(a=>a.label),['经营资格','基本面','资金面','风险稳定性','消息面','宣传承诺']);
 assert.equal(by['经营资格'].status,'warn');assert.equal(by['经营资格'].unchecked,1);
 assert.equal(by['资金面'].status,'ok','eleven checked items outweigh one unchecked item');assert.equal(by['资金面'].unchecked,1);
 assert.equal(by['基本面'].status,'ok');assert.equal(by['基本面'].checked,3);
 assert.equal(by['风险稳定性'].status,'bad');
 assert.equal(by['宣传承诺'].status,'bad');
 assert.equal(by['消息面'].status,'none','nothing checked is uncovered');
 const total=h.ctx.v.signals.reduce((n,s)=>n+s.items.length,0);
 assert.equal(axes.reduce((n,a)=>n+a.checked+a.unchecked+a.quiet,0),total);
 const svg=h.run('researchRadar(v)');
 assert.match(svg,/资金面未见异常（查了 11 项，另有 1 项没查）/);
 assert.match(svg,/消息面未覆盖/);
 assert.doesNotMatch(svg,/技术面|行业表现|记录较完整/);
});
test('an axis whose items were all unchecked stays uncovered',()=>{
 const h=harness();h.ctx.v={signals:[{key:'finance',items:[{key:'pledges',status:'none'},{key:'revenue',status:'none'}]}]};
 const axes=JSON.parse(h.run('JSON.stringify(researchRadarAxes(v))'));
 assert.ok(axes.every(a=>a.status==='none'));
});
test('radar names failed lookups and pending material instead of calling them unchecked',()=>{
 const h=harness();
 h.ctx.v={signals:[
  {key:'finance',items:[{key:'registry',status:'none',gap:'failed'},{key:'reports',status:'none',gap:'failed'}]},
  {key:'risk',items:[{key:'bank_list',status:'ok'},{key:'product_code',status:'none',gap:'needs_input'},{key:'scope',status:'none',gap:'failed'}]},
  {key:'credit',items:[{key:'penalties',status:'ok'},{key:'official_web',status:'none',gap:'listed'}]}]};
 const by=Object.fromEntries(JSON.parse(h.run('JSON.stringify(researchRadarAxes(v))')).map(a=>[a.label,a]));
 assert.equal(by['资金面'].failed,true);
 assert.equal(by['风险稳定性'].status,'ok');assert.equal(by['风险稳定性'].unchecked,0,'a listed item is not a gap');
 const svg=h.run('researchRadar(v)');
 assert.match(svg,/资金面没查成（2 项没查成）/);
 assert.match(svg,/经营资格未见异常（查了 1 项，另有 1 项没查成、1 项待补材料）/);
 assert.match(svg,/data-status="failed"/);
});

test('the report brief preserves all supplied summary lines and their version-bound references',()=>{
 const h=harness();
 h.ctx.refLinks=refs=>refs.map(id=>`<button data-act="goto" data-id="${id}">${id}</button>`).join('');
 h.ctx.v={onepager:{headline:'核实材料中的主体与付款安排。',mismatch:[{text:'承诺 <保本> 尚无依据',refs:['A2','R1']},{text:'收款人不同',refs:['A7']},{text:'合同缺条款',refs:['M1']}],found:[{text:'已查到登记记录',refs:['credit.status','R2']}],unknown:[{text:'接口没查成',refs:['finance.revenue']} ]},questions:[{id:'Q1',ask:'请提供盖章合同？',check_where:'对照合同主体与登记名称',linked:['A7']} ]};
 const html=h.run('researchBrief(v)');
 for(const id of ['A2','R1','A7','M1','credit.status','R2','finance.revenue']) assert.ok(html.includes(`data-id="${id}"`));
 assert.match(html,/&lt;保本&gt;/);assert.doesNotMatch(html,/<保本>/);
 assert.match(html,/接口没查成/);assert.match(html,/请提供盖章合同/);
 assert.match(html,/data-act="question-detail" data-question="0"/);
 assert.ok(html.indexOf('需要核实')<html.indexOf('查到的记录'));
});

test('an empty report brief invites evidence and does not imply a clean bill of health',()=>{
 const h=harness();h.ctx.refLinks=()=>'';
 h.ctx.v={onepager:{headline:'现有资料不足。',mismatch:[],found:[],unknown:[]},questions:[]};
 const html=h.run('researchBrief(v)');
 assert.match(html,/补充材料/);assert.match(html,/未列出待确认项/);
 assert.doesNotMatch(html,/没有问题|全部正常|安全|question-detail/);
});

test('the report title discloses fictional evidence even when the topbar is hidden on mobile',()=>{
 const h=harness();h.ctx.c={id:'case-id',case:{company_name:'公司 <测试>'},versions:[{no:1}],raw:[{id:'R1',kind:'demo',coverage:'found'}]};
 h.ctx.v={no:1,created_at:'2026-10-03',raw_ids:['R1'],need:'了解 <主体>'};
 const html=h.run('researchHero(c,v)');
 assert.match(html,/演示数据 · 公司为虚构/);assert.match(html,/公司 &lt;测试&gt;/);assert.match(html,/了解 &lt;主体&gt;/);
 h.ctx.v.raw_ids=[];
 assert.doesNotMatch(h.run('researchHero(c,v)'),/演示数据 · 公司为虚构/,'only the viewed version decides its evidence label');
});

test('version one has no changes shortcut even when a later version exists',()=>{
 const h=harness();h.ctx.c={id:'case',case:{company_name:'测试公司'},versions:[{no:1},{no:2}],raw:[]};
 h.ctx.v={no:1,created_at:'2026-10-03',raw_ids:[],need:'核对资料'};
 assert.doesNotMatch(h.run('researchHero(c,v)'),/查看本版变化/);
 h.ctx.v.no=2;
 assert.match(h.run('researchHero(c,v)'),/查看本版变化/);
});

test('a historical report without a one-pager still offers its own next question',()=>{
 const h=harness();
 h.ctx.document.createElement=()=>({innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[]});
 h.ctx.glanceHtml=()=>'';
 h.ctx.v={onepager:null,signals:[],questions:[{ask:'本版要核对合同吗',check_where:'阅读合同原文'}]};
 const html=h.run('researchOverview(v)');
 assert.match(html,/本版要核对合同吗/);assert.match(html,/data-act="question-detail"/);
 h.ctx.v.questions=[];
 assert.match(h.run('researchOverview(v)'),/data-act="supplement"/);
});
