import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyResearch, reduceEvent, researchProgress } from '../app/research-events.ts';

test('an unplanned processing stage is never presented as waiting after the saved result arrives', () => {
  let state=reduceEvent(emptyResearch(),{type:'begin',company:'公司',steps:[{id:'registry',label:'工商',lookup:true}]});
  state=reduceEvent(state,{type:'step',id:'registry',label:'工商',phase:'done',coverage:'found'});
  state={...state,connection:'saved',result:{id:'c1',current:1,versions:[{no:1}]}};
  const progress=researchProgress(state);
  assert.equal(progress.stages.find(s=>s.id==='intake').label,'未安排');
  assert.equal(progress.stages.find(s=>s.id==='collect').label,'已完成');
  assert.equal(progress.stages.find(s=>s.id==='save').label,'已完成');
  assert.equal(progress.percent,100);
});

test('clock follows actual completed events and needs read-back confirmation for 100 percent', () => {
  let s=reduceEvent(emptyResearch(),{type:'begin',company:'公司',steps:[{id:'registry',label:'工商',lookup:true},{id:'plain',label:'报告',lookup:false}]});
  assert.equal(researchProgress(s).percent,0);
  s=reduceEvent(s,{type:'step',id:'registry',label:'工商',phase:'start'});
  assert.equal(researchProgress(s).percent,0);
  s=reduceEvent(s,{type:'step',id:'registry',label:'工商',phase:'done',coverage:'not_found'});
  assert.equal(researchProgress(s).percent,33);
  s=reduceEvent(s,{type:'step',id:'registry',label:'工商',phase:'start'});
  assert.equal(researchProgress(s).percent,33);
  s=reduceEvent(s,{type:'step',id:'plain',label:'报告',phase:'done'});
  for(const extra of [{verifying:true},{saveStatus:'unconfirmed'},{connection:'disconnected'}])
    assert.equal(researchProgress({...s,...extra}).percent,66);
  assert.equal(researchProgress({...s,connection:'saved',result:{id:'c1',current:1,versions:[{no:1}]}}).percent,100);
});

test('missing and failed lookups finish processing without implying successful coverage', () => {
  for(const coverage of ['not_covered','failed']) {
    let s=reduceEvent(emptyResearch(),{type:'begin',company:'公司',steps:[{id:'registry',label:'工商',lookup:true}]});
    s=reduceEvent(s,{type:'step',id:'registry',label:'工商',phase:'done',coverage});
    assert.equal(researchProgress(s).percent,50);
    assert.equal(s.steps[0].coverage,coverage);
  }
});
