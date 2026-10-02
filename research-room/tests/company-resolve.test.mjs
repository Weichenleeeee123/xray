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

test('a failed lookup never blocks the search', async () => {
  assert.equal(await resolveCompany('杭州银行', reply({}, false)), null);
  assert.equal(await resolveCompany('杭州银行', async () => { throw new Error('offline'); }), null);
  assert.equal(await resolveCompany('杭州银行', reply({ exact: 'yes' })), null);
});
