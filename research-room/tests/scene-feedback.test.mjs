import test from 'node:test';
import assert from 'node:assert/strict';
import { sceneNotice, coverNameParts } from '../app/scene-feedback.ts';
import { emptyResearch } from '../app/research-events.ts';

const active = () => ({ ...emptyResearch(), connection: 'live', company: '杭州示例科技有限公司' });
const saved = () => ({ ...active(), connection: 'saved', result: { id: 'case-a', current: 1, versions: [{ no: 1 }] } });

test('idle is silent; connecting, collecting and prose completion cannot announce saved', () => {
  assert.equal(sceneNotice(emptyResearch()), null);
  for (const state of [{ ...active(), connection: 'connecting' }, active(),
    { ...active(), steps: [{ id: 'plain', phase: 'done', lookup: false, label: '报告' }] },
    { ...active(), connection: 'saved' }, { ...active(), candidate: { id: 'candidate' } }]) {
    assert.equal(sceneNotice(state).kind, 'running');
    assert.notEqual(sceneNotice(state).label, '报告已完成');
  }
});
test('independent read-back, save failures and disconnects override celebration', () => {
  assert.equal(sceneNotice({ ...saved(), verifying: true }).label, '正在确认报告保存');
  for (const extra of [{ saveStatus: 'failed' }, { saveStatus: 'unconfirmed' },
    { connection: 'disconnected' }, { connection: 'error' }])
    assert.equal(sceneNotice({ ...saved(), ...extra }).kind, 'attention');
});
test('one completion identity per saved case revision, independent of actor rerenders', () => {
  assert.equal(sceneNotice(saved()).label, '报告已完成');
  assert.equal(sceneNotice(saved()).kind, 'complete');
  assert.deepEqual(sceneNotice(saved()), sceneNotice({ ...saved(), steps: [] }));
  assert.notEqual(sceneNotice(saved()).key, sceneNotice({ ...saved(), result: { ...saved().result, id: 'case-b' } }).key);
  assert.notEqual(sceneNotice(saved()).key, sceneNotice({ ...saved(), result: { ...saved().result, current: 2 } }).key);
});
test('cover name splits legal suffix semantically and never drops characters', () => {
  assert.deepEqual(coverNameParts('杭州示例科技有限公司'), ['杭州示例科技', '有限公司']);
  assert.deepEqual(coverNameParts('示例股份有限公司'), ['示例', '股份有限公司']);
  assert.deepEqual(coverNameParts('示例集团有限公司'), ['示例', '集团有限公司']);
  for (const name of ['', '有限公司', '示例', 'Example Research Inc.', '杭州示例企业信息技术服务有限责任公司', '长'.repeat(76) + '有限公司', '<script> & "公司"'])
    assert.equal(coverNameParts(name).join(''), name);
});
