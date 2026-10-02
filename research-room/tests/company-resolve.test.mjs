import test from 'node:test';
import assert from 'node:assert/strict';
import { candidateLine, resolveCompany } from '../app/company-resolve.ts';

const reply = (body, ok = true) => async (url) => {
  reply.url = url;
  return { ok, json: async () => body };
};

test('asks the backend with the typed name and returns candidates as given', async () => {
  const body = { query: '巨鲸财富', exact: false, name: null, source: 'qcc', note: '请选一家',
    candidates: [{ name: '杭州巨鲸财富管理有限公司', code: '913301053281951475', founded: '2015-04-28', status: '存续' }] };
  const r = await resolveCompany(' 巨鲸财富 ', reply(body));
  assert.equal(reply.url, `/api/companies/resolve?q=${encodeURIComponent('巨鲸财富')}`);
  assert.equal(r.exact, false);
  assert.equal(candidateLine(r.candidates[0]), '存续 · 成立于 2015-04-28 · 913301053281951475');
});

test('a failed lookup returns an unavailable result for the caller to recover', async () => {
  assert.equal(await resolveCompany('杭州银行', reply({}, false)), null);
  assert.equal(await resolveCompany('杭州银行', async () => { throw new Error('offline'); }), null);
  assert.equal(await resolveCompany('杭州银行', reply({ exact: 'yes' })), null);
});

const tick = () => new Promise(resolve => setImmediate(resolve));

test('the default eight second limit settles and aborts a stalled lookup', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let result = 'pending', requestSignal;
  void resolveCompany('杭州银行', (_url, options) => {
    requestSignal = options?.signal;
    return new Promise(() => {});
  }).then(value => { result = value; });
  t.mock.timers.tick(7999);
  await tick();
  assert.equal(result, 'pending');
  t.mock.timers.tick(1);
  await tick();
  assert.equal(result, null);
  assert.equal(requestSignal.aborted, true);
});

test('a configurable timeout also bounds a stalled response body', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let result = 'pending', requestSignal;
  void resolveCompany('杭州银行', async (_url, options) => {
    requestSignal = options?.signal;
    return { ok: true, json: () => new Promise(() => {}) };
  }, { timeoutMs: 25 }).then(value => { result = value; });
  await tick();
  t.mock.timers.tick(25);
  await tick();
  assert.equal(result, null);
  assert.equal(requestSignal.aborted, true);
});

test('cancellation settles even when the transport ignores the abort signal', async () => {
  const controller = new AbortController();
  let result = 'pending', requestSignal;
  void resolveCompany('杭州银行', (_url, options) => {
    requestSignal = options?.signal;
    return new Promise(() => {});
  }, { signal: controller.signal }).then(value => { result = value; });
  controller.abort();
  await tick();
  assert.equal(result, null);
  assert.equal(requestSignal.aborted, true);
});

test('an already cancelled lookup does not contact the backend', async () => {
  const controller = new AbortController();
  controller.abort();
  let called = false;
  const result = await resolveCompany('杭州银行', async () => {
    called = true;
    return { ok: false };
  }, { signal: controller.signal });
  assert.equal(called, false);
  assert.equal(result, null);
});

test('successful lookups release their timeout and parent abort listener', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const controller = new AbortController();
  const body = { exact: true, name: '杭州银行股份有限公司', candidates: [] };
  let requestSignal;
  const result = await resolveCompany('杭州银行', async (_url, options) => {
    requestSignal = options?.signal;
    return { ok: true, json: async () => body };
  }, { signal: controller.signal, timeoutMs: 25 });
  controller.abort();
  t.mock.timers.tick(25);
  assert.equal(result, body);
  assert.ok(requestSignal);
  assert.equal(requestSignal.aborted, false);
});

test('an exact match without a usable full name is unavailable', async () => {
  assert.equal(await resolveCompany('简称', reply({ exact: true, name: null, candidates: [] })), null);
  assert.equal(await resolveCompany('简称', reply({ exact: true, name: ' ', candidates: [] })), null);
});

const candidate = { name: '杭州测试科技有限公司', code: null, founded: null, status: null };
const choices = { exact: false, name: null, note: '请选一家', candidates: [candidate] };

test('every candidate must be an object with a nonempty text name', async () => {
  for (const malformed of [null, false, 7, '公司', [], {},
    { name: null }, { name: 7 }, { name: {} }, { name: '' }, { name: ' \n\t ' }]) {
    assert.equal(await resolveCompany('简称', reply({ ...choices, candidates: [candidate, malformed] })),
      null, `reject candidate ${JSON.stringify(malformed)}`);
  }
});

test('candidate display metadata must be text or absent', async () => {
  for (const field of ['code', 'founded', 'status']) {
    for (const value of [{ text: 'unexpected' }, ['unexpected'], 123, false]) {
      assert.equal(await resolveCompany('简称', reply({
        ...choices, candidates: [{ ...candidate, [field]: value }],
      })), null, `reject ${field}: ${JSON.stringify(value)}`);
    }
  }
});

test('the displayed resolution note must be text or absent', async () => {
  for (const note of [{ message: 'unexpected' }, ['unexpected'], 123, false]) {
    assert.equal(await resolveCompany('简称', reply({ ...choices, note })), null,
      `reject note ${JSON.stringify(note)}`);
  }
});

test('safe nullable and omitted metadata still renders a usable candidate', async () => {
  for (const body of [choices, { ...choices, note: null },
    { exact: false, name: null, candidates: [{ name: candidate.name }] }]) {
    const result = await resolveCompany('简称', reply(body));
    assert.equal(result, body);
    assert.equal(candidateLine(result.candidates[0]), '');
  }
});
