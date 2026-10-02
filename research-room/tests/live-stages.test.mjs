import test from 'node:test';
import assert from 'node:assert/strict';
import { OfficeDirector } from '../app/office-director.ts';
import { emptyResearch, reduceEvent } from '../app/research-events.ts';

const plan = [
  { id: 'intake', label: '读懂需求', lookup: false },
  { id: 'lists', label: '持牌名单', lookup: true },
  { id: 'web', label: '政府网站', lookup: true },
  { id: 'rules', label: '对照规则', lookup: false },
  { id: 'plain', label: '写成短句', lookup: false },
];
const initial = () => reduceEvent(emptyResearch(), { type: 'begin', company: '测试公司', steps: plan });
const event = (id, phase, coverage) => ({ type: 'step', id, phase, label: plan.find(s => s.id === id).label, coverage });

test('goose reads the need at its desk without inventing a lookup', () => {
  const d = new OfficeDirector();
  const s = reduceEvent(initial(), event('intake', 'start'));
  for (let i = 0; i < 100; i++) d.tick(40, s);
  assert.equal(d.sample().motion.distance, 0);
  assert.equal(d.sample().phase.label, '读懂研究需求');
  assert.equal(d.visited.size, 0);
});

test('a current backend lookup is visited before a completed lookup backlog', () => {
  const d = new OfficeDirector();
  let s = reduceEvent(initial(), event('lists', 'done', 'found'));
  s = reduceEvent(s, event('web', 'start'));
  for (let i = 0; i < 1000 && !d.sample().phase.station; i++) d.tick(40, s);
  assert.equal(d.sample().phase.station, 'news');
});

test('a disconnected or failed task cannot continue acting as an active query', () => {
  for (const connection of ['disconnected', 'error']) {
    const d = new OfficeDirector();
    const s = { ...reduceEvent(initial(), event('web', 'start')), connection };
    const before = d.sample();
    for (let i = 0; i < 1000; i++) d.tick(40, s);
    assert.deepEqual(d.sample().motion.position, before.motion.position);
    assert.equal(d.sample().finished, false);
  }
});

test('after collecting, desk work follows analysis then prose without claiming completion', () => {
  const d = new OfficeDirector();
  let s = initial();
  s = reduceEvent(s, event('lists', 'done', 'not_covered'));
  s = reduceEvent(s, event('web', 'done', 'not_covered'));
  s = reduceEvent(s, event('rules', 'start'));
  for (let i = 0; i < 3000; i++) d.tick(40, s);
  assert.equal(d.sample().phase.label, '对照记录与规则');
  s = reduceEvent(s, event('rules', 'done'));
  s = reduceEvent(s, event('plain', 'start'));
  d.tick(40, s);
  assert.equal(d.sample().phase.label, '撰写研究报告');
  assert.equal(d.sample().finished, false);
});
