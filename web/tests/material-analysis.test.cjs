const {test}=require('node:test');
const assert=require('node:assert/strict');
const MA=require('../material-analysis.js');
const a={id:'MA2',report_version:2,created_at:'2026-10-03T09:00',title:'合同 <script>',summary:'有条款待核实',raw_ids:['R2'],findings:[],observations:[],changes:[]};
const c={case:{company_name:'公司 <img>'},material_analyses:[a]};
test('saved entries escape titles and reopen the matching analysis, newest first',()=>{
 const html=MA.list({...c,material_analyses:[a,{...a,id:'MA3',report_version:3}]});
 assert.ok(html.indexOf('data-analysis="MA3"')<html.indexOf('data-analysis="MA2"'));
 assert.match(html,/合同 &lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/data-act="material-open"/);
});
test('result keeps raw evidence and contract observations, with no invented all-clear',()=>{
 const empty=MA.result(c,a);assert.match(empty,/未识别到说法，不代表材料没有问题/);
 const html=MA.result(c,{...a,observations:[{text:'甲方不同 <img>',basis:[{ref:'R2',quote:'甲方：测试公司'}],unknown:['签约主体'],cannot:['合同是假的']}]});
 assert.match(html,/甲方不同 &lt;img&gt;/);assert.match(html,/data-ref="R2"/);
 assert.match(html,/不能据此认定：合同是假的/);assert.doesNotMatch(html,/还不能形成具体核对结论/);
 assert.match(html,/收起材料分析/);
});
test('progress reflects backend events monotonically and stops on connection errors',()=>{
 const title={},detail={},stages=[0,1,2].map(()=>({attrs:{},small:{},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},querySelector(){return this.small}}));
 const host={attrs:{},classList:{add(){}},setAttribute(k,v){this.attrs[k]=v},querySelector(s){return s==='[data-ma-title]'?title:detail},querySelectorAll(){return stages}};
 const progress=MA.mount(host);
 progress.onEvent({type:'step',id:'registry',phase:'start',label:'核对登记'});
 assert.equal(title.textContent,'核对记录');assert.equal(stages[0].small.textContent,'已完成');
 progress.onEvent({type:'step',id:'plain',phase:'start',label:'整理结论'});
 progress.onEvent({type:'step',id:'registry',phase:'done',text:'登记完成'});
 assert.equal(title.textContent,'整理分析');assert.equal(stages[2].attrs['aria-current'],'step');
 progress.error(false);assert.equal(title.textContent,'连接中断，进度待确认');assert.equal(host.attrs['aria-busy'],'false');
 progress.stop();progress.onEvent({type:'step',id:'plain'});assert.equal(title.textContent,'连接中断，进度待确认');
});
