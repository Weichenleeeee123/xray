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
