const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readCaseStream, progressState, updateProgress, progressHtml, stationFor } = require('../research-progress.js');

const result = { id: 'case-123', current: 1, versions: [{ no: 1 }], raw: [] };
const begin = { type: 'begin', company: '测试公司', steps: [{ id: 'registry', label: '工商登记', lookup: true }] };
test('prebuilt source is displayed during both streaming and step replay', async () => {
  const event={type:'prebuilt',demo_id:'B',built_at:'2026-10-02 12:00'};
  const state=progressState(), received=[];
  await readCaseStream('/test',{}, {onEvent:e=>{received.push(e);updateProgress(state,e);},fetchImpl:async()=>response([event,begin,{type:'case',case:result}])});
  assert.deepEqual(received,[event,begin]);
  updateProgress(state,{type:'step',id:'registry',phase:'start'});
  const html=progressHtml(state);
  assert.match(html,/预制示例快照/);
  assert.match(html,/本次未重新联网查询/);
  assert.match(html,/预制包生成时间/);
  assert.match(html,/回放中/);
  assert.doesNotMatch(progressHtml(progressState()),/预制示例快照/);
});
function response(events, { bytewise = false, newline = true } = {}) {
  const bytes = new TextEncoder().encode(events.map(e => JSON.stringify(e)).join('\n') + (newline ? '\n' : ''));
  return new Response(new ReadableStream({ start(controller) {
    if (bytewise) for (const b of bytes) controller.enqueue(Uint8Array.of(b));
    else controller.enqueue(bytes);
    controller.close();
  } }), { headers: { 'Content-Type': 'application/x-ndjson' } });
}

test('stream preserves split Chinese UTF-8 and returns the actual case without a final newline', async () => {
  const seen = [];
  const done = { type: 'step', id: 'registry', phase: 'done', coverage: 'not_covered', text: '没查：没有数据源' };
  const got = await readCaseStream('/api/cases/stream', { company_name: '测试公司', need: '合作' }, {
    onEvent: e => seen.push(e),
    fetchImpl: async (url, options) => {
      assert.equal(url, '/api/cases/stream');
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), { company_name: '测试公司', need: '合作' });
      return response([begin, done, { type: 'case', case: result }], { bytewise: true, newline: false });
    },
  });
  assert.deepEqual(got, result);
  assert.deepEqual(seen, [begin, done]);
});

test('an unfinished stream fails and never automatically submits the creation twice', async () => {
  let calls = 0;
  await assert.rejects(readCaseStream('/api/cases/stream', {}, {
    fetchImpl: async () => { calls++; return response([begin]); },
  }), /案卷/);
  assert.equal(calls, 1);
});

test('HTTP validation and streamed errors do not produce a fake report', async () => {
  await assert.rejects(readCaseStream('/api/cases/stream', {}, {
    fetchImpl: async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'need'], msg: 'Field required' }] }), { status: 422 }),
  }), /need.*Field required/);
  await assert.rejects(readCaseStream('/api/cases/stream', {}, {
    fetchImpl: async () => response([begin, { type: 'error', message: '生成失败，请重试' }]),
  }), /生成失败/);
});

test('malformed events and malformed terminal cases are rejected', async () => {
  for (const event of [{ type: 'case', case: {} }, { type: 'unexpected' }]) {
    await assert.rejects(readCaseStream('/api/cases/stream', {}, { fetchImpl: async () => response([begin, event]) }));
  }
});

test('only real step events change progress; missing data is not success', () => {
  const state = progressState();
  updateProgress(state, begin);
  assert.equal(state.steps[0].phase, 'waiting');
  updateProgress(state, { type: 'step', id: 'registry', phase: 'start' });
  assert.equal(state.steps[0].phase, 'start');
  assert.equal(state.steps[0].coverage, null);
  updateProgress(state, { type: 'step', id: 'registry', phase: 'done', coverage: 'not_covered', counts: { found: 0, not_covered: 1 }, text: '没查' });
  assert.equal(state.steps[0].coverage, 'not_covered');
  assert.equal(state.steps[0].counts.found, 0);
  assert.equal(state.steps[0].text, '没查');
});

test('abort signal is forwarded to the single fetch', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(readCaseStream('/api/cases/stream', {}, {
    signal: controller.signal,
    fetchImpl: async (_url, options) => {
      assert.equal(options.signal, controller.signal);
      options.signal.throwIfAborted();
    },
  }), { name: 'AbortError' });
});

test('waiting view escapes source content and distinguishes missing from failed', () => {
  const state = progressState();
  updateProgress(state, { ...begin, company: '<img src=x onerror=alert(1)>', steps: [
    { id: 'registry', label: '工商登记', lookup: true }, { id: 'web', label: '网络搜索', lookup: true },
  ] });
  updateProgress(state, { type: 'step', id: 'registry', phase: 'done', coverage: 'not_covered', text: '没有数据源' });
  updateProgress(state, { type: 'step', id: 'web', phase: 'done', coverage: 'failed', text: '<script>危险</script>' });
  const html = progressHtml(state);
  assert.ok(!html.includes('<script>') && !html.includes('<img src=x'));
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /没查/);
  assert.match(html, /没查成/);
  assert.ok(!html.includes('100%') && !html.includes('报告已生成'));
});

test('animation station follows the active backend step rather than elapsed time', () => {
  const state = progressState();
  updateProgress(state, { ...begin, steps: [...begin.steps, { id: 'plain', label: '写成短句', lookup: false }] });
  updateProgress(state, { type: 'step', id: 'registry', phase: 'start' });
  assert.equal(stationFor(state).name, 'data');
  updateProgress(state, { type: 'step', id: 'registry', phase: 'done', coverage: 'not_covered', text: '没查' });
  updateProgress(state, { type: 'step', id: 'plain', phase: 'start' });
  assert.equal(stationFor(state).name, 'desk');
});
