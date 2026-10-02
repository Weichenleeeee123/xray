import test from 'node:test';
import assert from 'node:assert/strict';
import { researchInput } from '../app/research-input.ts';
import { startRun } from '../app/research-events.ts';

const preset = { company_name: '示例公司', need: '替母亲了解理财', scenario: 'savings', for_whom: '母亲', amount: 200000, material_text: '宣传材料原文', material_title: '示例材料' };
test('selected example sends initial material and context through the real run transport', async () => {
  let submitted;
  const result = await startRun(researchInput(' 示例公司 ', preset.need, preset), async (url, options) => {
    assert.equal(url, '/api/runs');
    submitted = JSON.parse(options.body);
    return Response.json({run_id:'test-run'});
  });
  assert.equal(result, 'test-run');
  assert.deepEqual(submitted, preset);
  assert.deepEqual(researchInput(submitted.company_name, submitted.need, submitted), preset);
});
test('changing company prevents example material and scenario leaking into a different company', () => {
  assert.deepEqual(researchInput('另一家公司', '求职', preset), {company_name:'另一家公司', need:'求职'});
});
test('editing need retains company material but clears stale scenario, amount and beneficiary', () => {
  assert.deepEqual(researchInput(preset.company_name, '准备入职', preset), {
    company_name:preset.company_name, need:'准备入职', material_text:preset.material_text, material_title:preset.material_title,
  });
});
test('ordinary input and removing a preset do not attach material', () => {
  assert.deepEqual(researchInput('示例公司'), {company_name:'示例公司', need:'了解这家公司的登记、资质与公开资料'});
});

test('explicit source refresh choice is retained for the same company only', () => {
  for (const refresh_sources of [true, false]) {
    const input = {...preset, refresh_sources};
    assert.equal(researchInput(preset.company_name, preset.need, input).refresh_sources, refresh_sources);
    assert.equal(researchInput('另一家公司', preset.need, input).refresh_sources, undefined);
  }
});
