import test from 'node:test';
import assert from 'node:assert/strict';
import { followRun, startRun, BackendError } from '../app/research-events.ts';

const RUN = 'a'.repeat(24);

test('creating a task forwards cancellation and a stable idempotency key', async () => {
  const controller = new AbortController();
  let sent;
  await startRun({ company_name: '测试公司' }, async (url, init) => {
    sent = { url, ...init };
    return new Response(JSON.stringify({ run_id: RUN }), { status: 202 });
  }, { signal: controller.signal, requestKey: 'home-test-request' });
  assert.equal(sent.signal, controller.signal);
  assert.equal(sent.headers['Idempotency-Key'], 'home-test-request');
});

test('polling removes settled abort listeners and stops before fetching an aborted run', async () => {
  const controller = new AbortController();
  let added = 0, removed = 0, reads = 0;
  const add = controller.signal.addEventListener.bind(controller.signal);
  const remove = controller.signal.removeEventListener.bind(controller.signal);
  controller.signal.addEventListener = (...args) => { added++; return add(...args); };
  controller.signal.removeEventListener = (...args) => { removed++; return remove(...args); };
  const fetchImpl = async () => {
    reads++;
    return new Response(JSON.stringify({ status: reads < 4 ? 'running' : 'complete', case_id: 'c1', events: [], next: 0 }));
  };
  await followRun(RUN, { signal: controller.signal, fetchImpl, onEvent() {}, interval: 1 });
  assert.equal(added, removed);
  controller.abort();
  await assert.rejects(followRun(RUN, { signal: controller.signal, fetchImpl, onEvent() {} }), { name: 'AbortError' });
  assert.equal(reads, 4);
});
const begin = { type: 'begin', company: '测试公司', steps: [{ id: 'lists', label: '名单', lookup: true }] };
const step = (phase) => ({ type: 'step', id: 'lists', label: '名单', phase, ...(phase === 'done' ? { coverage: 'found' } : {}) });

// 假后端：每次轮询吐出下一批事件
function backend(pages) {
  const seen = [];
  const fetchImpl = async (url) => {
    seen.push(String(url));
    const page = pages.shift();
    if (page === 404) return new Response('{}', { status: 404 });
    return new Response(JSON.stringify({ run_id: RUN, ...page }), { headers: { 'Content-Type': 'application/json' } });
  };
  return { fetchImpl, seen };
}

test('polling replays events in order and returns the saved case id only when complete', async () => {
  const { fetchImpl, seen } = backend([
    { status: 'running', case_id: null, events: [begin, step('start')], next: 2 },
    { status: 'running', case_id: null, events: [], next: 2 },
    { status: 'complete', case_id: 'c1', events: [step('done'), { type: 'complete', case_id: 'c1' }], next: 4 },
  ]);
  const got = [];
  const id = await followRun(RUN, { onEvent: (e) => got.push(e.type + ':' + (e.phase || '')), fetchImpl, interval: 1 });
  assert.equal(id, 'c1');
  assert.deepEqual(got, ['begin:', 'step:start', 'step:done']);
  assert.deepEqual(seen.map((u) => u.split('after=')[1]), ['0', '2', '2']);  // 只要新事件，不重复
});

test('a run that died with the server is reported, not shown as finished', async () => {
  const { fetchImpl } = backend([{ status: 'interrupted', case_id: null, events: [begin], next: 1 }]);
  await assert.rejects(followRun(RUN, { onEvent() {}, fetchImpl, interval: 1 }), BackendError);
});

test('backend error event and unknown run are errors', async () => {
  let b = backend([{ status: 'error', case_id: null, events: [{ type: 'error', message: '生成失败' }], next: 1 }]);
  await assert.rejects(followRun(RUN, { onEvent() {}, fetchImpl: b.fetchImpl, interval: 1 }), /生成失败/);
  b = backend([404]);
  await assert.rejects(followRun(RUN, { onEvent() {}, fetchImpl: b.fetchImpl, interval: 1 }), /找不到这次查询/);
});

test('starting a run needs a run id back', async () => {
  const ok = async () => new Response(JSON.stringify({ run_id: RUN, status: 'running' }), { status: 202 });
  assert.equal(await startRun({ company_name: 'x' }, ok), RUN);
  const bad = async () => new Response(JSON.stringify({ detail: '公司名称不能为空' }), { status: 422 });
  await assert.rejects(startRun({}, bad), /公司名称不能为空/);
});

test('a recovered run can confirm and retry its saved report without starting another query', async () => {
  const { confirmSavedCase } = await import('../app/research-events.ts');
  const saved = { id: 'c1', current: 2, versions: [{ no: 2 }], case: { company_name: '测试公司' } };
  const calls = [];
  let reads = 0;
  const fetchImpl = async (url, init) => {
    calls.push([String(url), init?.method ?? 'GET']);
    if (String(url).startsWith('/api/runs/'))
      return new Response(JSON.stringify({ status: 'complete', case_id: saved.id, events: [begin, step('done')], next: 2 }));
    reads++;
    if (reads === 1) return new Response('', { status: 503 });
    return new Response(JSON.stringify(saved));
  };
  const id = await followRun(RUN, { onEvent() {}, fetchImpl });
  await assert.rejects(confirmSavedCase({ id }, '测试公司', fetchImpl), /确认保存/);
  assert.deepEqual(await confirmSavedCase({ id }, '测试公司', fetchImpl), saved);
  await assert.rejects(confirmSavedCase({ id }, '其他公司', fetchImpl), /校验不一致/);
  assert.ok(calls.every(([, method]) => method === 'GET'));
});
