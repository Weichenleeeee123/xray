import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyResearch, reduceEvent, readCaseStream, followRun, lifecycleLabel, stationState, researchProgress, reportPresentation, researchProvenance } from '../app/research-events.ts';
import { sceneNotice } from '../app/scene-feedback.ts';

const provenance = { type: 'prebuilt', demo_id: 'B', built_at: '2026-10-02 12:00' };
const begin = { type: 'begin', company: '测试公司', steps: [{id:'web',label:'政府公告',lookup:true}] };
const result = {id:'case',current:1,versions:[{no:1,prebuilt:provenance}]};
test('prebuilt progress stays neutral and does not claim saving before confirmation', () => {
  let state = reduceEvent(emptyResearch(), provenance);
  state = reduceEvent(state, begin);
  state = reduceEvent(state, {type:'step',id:'web',label:'政府公告',phase:'start'});
  assert.equal(state.prebuilt.built_at, provenance.built_at);
  assert.equal(lifecycleLabel(state), '报告整理中');
  assert.equal(stationState(state,'news').label,'整理中');
  assert.equal(researchProgress(state).current,'正在整理报告');
  assert.equal(sceneNotice(state).label,'报告整理中');
  assert.equal(reportPresentation(state).canOpen,false);
  const saved = {...state,connection:'saved',result};
  assert.equal(lifecycleLabel(saved),'报告已保存');
  assert.equal(sceneNotice(saved).label,'报告已完成');
  assert.equal(reportPresentation(saved).canOpen,true);
  assert.equal(lifecycleLabel({...saved,saveStatus:'failed'}),'报告保存失败');
});
test('stream and durable run recovery both retain prebuilt provenance',async()=>{
  const received=[];
  await readCaseStream('/test',{}, {onEvent:e=>received.push(e),fetchImpl:async()=>new Response([provenance,begin,{type:'case',case:result}].map(JSON.stringify).join('\n'))});
  assert.deepEqual(received,[provenance,begin]);
  const recovered=[];
  await followRun('run',{onEvent:e=>recovered.push(e),fetchImpl:async()=>Response.json({run_id:'run',status:'complete',case_id:'case',version:1,next:2,events:[provenance,begin]})});
  assert.deepEqual(recovered,[provenance,begin]);
});
test('legacy saved snapshots and current real versions are distinguished',()=>{
  const saved={...emptyResearch(),connection:'saved',result:{id:'old',current:1,versions:[{no:1,notes:['预制示例：现场演示直接展示，不重新联网查询。']}]}};
  assert.ok(researchProvenance(saved));
  assert.equal(lifecycleLabel(saved),'报告已保存');
  saved.result.current=2;
  saved.result.versions.push({no:2,notes:['基于预制快照的人工复核：本版未重新联网查询。']});
  assert.equal(researchProvenance(saved),null);
  assert.equal(lifecycleLabel(saved),'报告已保存');
});
