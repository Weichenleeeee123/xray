import test from 'node:test';
import assert from 'node:assert/strict';
import * as events from '../app/research-events.ts';
import { OfficeDirector } from '../app/office-director.ts';
const state = (steps, connection = 'live') => ({ ...events.emptyResearch(), connection, steps });
const step = (id, phase, coverage, counts) => ({ id, label: id, lookup: true, phase, coverage, counts });

test('completed mixed results are complete, with evidence outcomes separate from progress', () => {
  const s = state([step('lists', 'done', 'found', {found:1,not_found:3}), step('registry','done','found',{found:8,not_found:1})]);
  const station = events.stationState(s,'enterprise');
  assert.equal(station.label, '已完成');
  assert.equal(station.done,true);
  assert.match(station.resultLabel,/9.*4/);
  assert.equal(station.progress,'done');
});
test('all skipped sources and partially failed sources never masquerade as pending or fully successful', () => {
  assert.equal(events.stationState(state([step('pack','done','not_covered')]),'library').label,'已跳过');
  const partial = events.stationState(state([step('lists','done','found'),step('registry','done','failed')]),'enterprise');
  assert.equal(partial.label,'已结束 · 部分失败');
  assert.equal(partial.progress,'failed');
});
test('connection loss preserves finished work but never claims an active query is still running', () => {
  const station = events.stationState(state([step('lists','done','found'),step('registry','start')],'disconnected'),'enterprise');
  assert.equal(station.active,false);
  assert.equal(station.label,'状态待确认');
});
test('current activity exposes every parallel query and saved state takes precedence', () => {
  const s = state([step('lists','start'),step('web','start')]);
  assert.equal(typeof events.researchProgress,'function');
  assert.match(events.researchProgress(s).current,/lists.*web/);
  assert.equal(events.researchProgress({...s,connection:'saved'}).current,'研究已完成，可以查看报告');
});
test('fast saved results skip the source tour, including found social records', () => {
  const s = { ...state(['lists','registry','pack','web','amac','reviews'].map(id=>step(id,'done','found')),'saved'),
    result: { id:'saved', current:1, versions:[{no:1}] } };
  const d = new OfficeDirector();
  for(let t=0;t<3000 && !d.finished;t+=20) {
    d.tick(20,s);
    const scene = d.sample();
    assert.equal(events.reportPresentation(s,scene.phase.id).canOpen,true);
    assert.equal(scene.phase.station,undefined);
    assert.notEqual(scene.phase.mode,'walk');
    assert.equal(scene.knocking,false);
    assert.equal(scene.door,0);
  }
  assert.equal(d.finished,true);
});
test('live lookups retain the full page-turn cycle without replaying finished stations', () => {
  const s = state([step('lists','done','found'), step('pack','done','not_found'),
    step('web','start'),step('amac','done','failed'),step('registry','done','not_covered')]);
  const d = new OfficeDirector();
  const frames = new Set();
  for(let t=0;t<8000;t+=20) {
    d.tick(20,s);
    if(d.action.station) {
      assert.equal(d.action.station,'news');
      frames.add(Math.floor(d.local/400));
    }
  }
  assert.deepEqual([...frames],[0,1,2,3]);
});
test('completion while walking cancels unstarted research and returns continuously', () => {
  const d = new OfficeDirector();
  let s = state([step('web','start'),step('lists','waiting')]);
  for(let t=0;t<1400;t+=20) d.tick(20,s);
  assert.equal(d.action.mode,'walk');
  s = {...s, connection:'saved',steps:s.steps.map(s=>({...s,phase:'done',coverage:'found'}))};
  let prior = d.sample().motion.position;
  for(let t=0;t<8000 && !d.finished;t+=20) {
    d.tick(20,s);
    assert.equal(d.action.station,undefined,'no lookup may start after completion');
    const p = d.sample().motion.position;
    assert.ok(Math.hypot((p.x-prior.x)*16.72,(p.y-prior.y)*9.41)<15,'movement must stay continuous');
    assert.ok(!(p.x>28 && p.x<72 && p.y>70 && p.y<95),'must route around desk');
    prior=p;
  }
  assert.equal(d.finished,true);
});
test('a source finishing en route is not consulted while other tasks remain pending', () => {
  const d = new OfficeDirector();
  let s = state([step('web','start'),step('lists','waiting')]);
  for(let t=0;t<1400;t+=20) d.tick(20,s);
  s = state([step('web','done','found'),step('lists','start')]);
  let reachedEnterprise = false;
  for(let t=0;t<10000;t+=20) {
    d.tick(20,s);
    assert.notEqual(d.action.station,'news');
    if(d.action.station==='enterprise') reachedEnterprise=true;
  }
  assert.equal(reachedEnterprise,true);
});

test('completion during standing cancels the trip and settles back into the chair', () => {
  const d=new OfficeDirector();
  let s=state([step('web','start'),step('lists','waiting')]);
  d.tick(900,s);
  assert.equal(d.action.id,'stand');
  s=state([step('web','done','found'),step('lists','waiting')]);
  for(let t=0;t<3000;t+=20) {
    d.tick(20,s);
    assert.notEqual(d.action.mode,'walk');
    assert.equal(d.action.station,undefined);
  }
  assert.equal(d.sample().seated,1);
  assert.equal(d.action.id,'idle');
});
