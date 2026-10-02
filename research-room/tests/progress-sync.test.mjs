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
test('a fast saved run does not replay historical source visits', () => {
  const s = state(['lists','registry','pack','web','amac','reviews'].map(id=>step(id,'done','found')),'saved');
  const d = new OfficeDirector();
  for(let t=0;t<6000 && !d.finished;t+=20) {
    d.tick(20,s);
    assert.notEqual(d.sample().phase.id,'research');
  }
  assert.equal(d.finished,true,'saved report must be presented within six seconds');
});
test('completion while walking returns promptly without teleporting or crossing the desk', () => {
  const d = new OfficeDirector();
  let s = state([step('web','start'),step('lists','waiting')]);
  for(let t=0;t<1200;t+=20) d.tick(20,s);
  s = {...s, connection:'saved',steps:s.steps.map(s=>({...s,phase:'done',coverage:'found'}))};
  let prior = d.sample().motion.position;
  for(let t=0;t<7000 && !d.finished;t+=20) {
    d.tick(20,s);
    const p = d.sample().motion.position;
    assert.ok(Math.hypot((p.x-prior.x)*16.72,(p.y-prior.y)*9.41)<15,'movement must stay continuous');
    assert.ok(!(p.x>28 && p.x<72 && p.y>70 && p.y<95),'must route around desk');
    prior=p;
  }
  assert.equal(d.finished,true,'should catch up within seven seconds even mid-route');
});
