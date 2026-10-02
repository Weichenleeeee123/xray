import test from 'node:test';
import assert from 'node:assert/strict';
import {
  emptyResearch,
  reduceEvent,
  stationState,
  collectionFinished,
  readCaseStream,
  validateCase,
  lifecycleLabel,
} from '../app/research-events.ts';
import * as reports from '../app/research-events.ts';
import { OfficeDirector, routeBetween } from '../app/office-director.ts';
import { motionAt, SEAT } from '../app/office-motion.ts';
const begin = {
  type: 'begin',
  company: '测试公司',
  steps: [
    ['lists', '名单'],
    ['registry', '工商'],
    ['pack', '文书'],
    ['web', '报道'],
    ['amac', '私募'],
    ['reviews', '评价'],
  ].map(([id, label]) => ({ id, label, lookup: true })),
};
const event = (id, phase = 'done', coverage = 'found') => ({
  type: 'step',
  id,
  label: id,
  phase,
  coverage,
  counts: { [coverage]: 1 },
});
const state = () => reduceEvent(emptyResearch(), begin);
test('a social start cannot invent a visitor before a found result, including en-route failures', () => {
  for (const coverage of ['not_found', 'not_covered', 'failed', 'found']) {
    const d = new OfficeDirector();
    let s = reduceEvent(emptyResearch(), {
      ...begin,
      steps: [{ id: 'reviews', label: '评价', lookup: true }],
    });
    s = reduceEvent(s, {
      type: 'step',
      id: 'reviews',
      label: '评价',
      phase: 'start',
    });
    d.tick(900, s);
    // Complete while the actor has already queued its journey.
    s = {
      ...reduceEvent(s, event('reviews', 'done', coverage)),
      connection: 'saved',
    };
    let sawVisitor = false;
    for (let i = 0; i < 3000 && !d.finished; i++) {
      d.tick(40, s);
      if (d.sample().door > 0) sawVisitor = true;
    }
    assert.equal(sawVisitor, false, 'completed runs skip obsolete visitor scenes: ' + coverage);
  }
  const d = new OfficeDirector();
  let s = reduceEvent(emptyResearch(), {
    ...begin,
    steps: [{ id: 'reviews', label: '评价', lookup: true }],
  });
  s = reduceEvent(s, {
    type: 'step',
    id: 'reviews',
    label: '评价',
    phase: 'start',
  });
  for (let i = 0; i < 600; i++) {
    d.tick(40, s);
    assert.equal(d.sample().door, 0);
  }
  assert.equal(d.sample().motion.distance, 0);
});
test('parallel starts remain visible and mixed failures are not hidden by found records', () => {
  let s = state();
  s = reduceEvent(s, event('lists', 'start'));
  s = reduceEvent(s, event('web', 'start'));
  assert.equal(stationState(s, 'enterprise').label, '查询中');
  assert.equal(stationState(s, 'news').label, '查询中');
  s = reduceEvent(s, event('lists'));
  s = reduceEvent(s, event('registry', 'done', 'failed'));
  assert.equal(stationState(s, 'enterprise').label, '已结束 · 部分失败');
  assert.match(stationState(s, 'enterprise').resultLabel, /已查到.*查询失败/);
  assert.equal(stationState(s, 'enterprise').failed, true);
  for (const [id, cov] of [
    ['pack', 'not_covered'],
    ['web', 'not_found'],
    ['amac', 'failed'],
    ['reviews', 'found'],
  ])
    s = reduceEvent(s, event(id, 'done', cov));
  assert.equal(stationState(s, 'library').label, '已跳过');
  assert.equal(stationState(s, 'news').label, '已完成');
  assert.match(stationState(s, 'news').resultLabel, /未找到/);
  assert.equal(collectionFinished(s), true);
});
test('slow lookup waits on planted feet until the done event', () => {
  const d = new OfficeDirector();
  let s = reduceEvent(state(), event('lists', 'start'));
  for (let i = 0; i < 1500; i++) d.tick(40, s);
  assert.equal(d.action.id, 'research');
  assert.equal(d.sample().motion.distance, 0);
  assert.equal(d.sample().motion.frame, 0);
  const pos = d.sample().motion.position;
  s = reduceEvent(s, event('lists'));
  d.tick(40, s);
  assert.deepEqual(d.sample().motion.position, pos);
});
test('fast result stays at the desk and archives before presenting without replaying old visits', () => {
  const d = new OfficeDirector();
  let s = state();
  for (const step of s.steps) s = reduceEvent(s, event(step.id));
  s = { ...s, connection: 'saved' };
  let prior = d.sample().motion.position;
  const seen = [];
  for (let i = 0; i < 5000 && !d.finished; i++) {
    d.tick(20, s);
    const current = d.sample();
    assert.ok(
      Math.hypot(
        (current.motion.position.x - prior.x) * 16.72,
        (current.motion.position.y - prior.y) * 9.41,
      ) < 10,
      'teleport',
    );
    if (seen.at(-1) !== current.phase.id) seen.push(current.phase.id);
    prior = current.motion.position;
    if (current.phase.id === 'sort')
      assert.ok(
        current.seated === 1,
        'a finished task is archived at the desk',
      );
  }
  assert.equal(d.finished, true);
  assert.ok(seen.indexOf('sort') < seen.indexOf('bind-report'));
  assert.ok(!seen.includes('research'));
  assert.ok(!seen.includes('walk'));
  assert.deepEqual(d.sample().motion.position, SEAT);
});
test('all waypoint routes stay outside the desk footprint', () => {
  const points = [
    SEAT,
    { x: 24, y: 44 },
    { x: 15, y: 62 },
    { x: 70, y: 43 },
    { x: 76, y: 67 },
    { x: 45, y: 42 },
    { x: 24, y: 98 },
    { x: 76, y: 98 },
  ];
  for (const from of points)
    for (const to of points) {
      const p = {
        from,
        to,
        start: 0,
        end: 1000,
        route: routeBetween(from, to),
      };
      for (let t = 0; t <= 1000; t += 5) {
        const { x, y } = motionAt(p, t).position;
        assert.ok(
          !(x > 28 && x < 72 && y > 70 && y < 95),
          `desk collision ${x},${y}`,
        );
        assert.ok(Number.isFinite(x) && Number.isFinite(y));
      }
    }
});
test('NDJSON parser tolerates split UTF8, CRLF, final line and validates real terminal result', async () => {
  const c = { id: 'abc', current: 1, versions: [{ no: 1 }] };
  const text =
    JSON.stringify(begin) +
    '\r\n' +
    JSON.stringify(event('lists')) +
    '\n' +
    JSON.stringify({ type: 'case', case: c });
  const bytes = new TextEncoder().encode(text),
    events = [];
  const fetchImpl = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          for (let i = 0; i < bytes.length; i += 7)
            controller.enqueue(bytes.slice(i, i + 7));
          controller.close();
        },
      }),
    );
  assert.deepEqual(
    await readCaseStream(
      '/api/cases/stream',
      {},
      { onEvent: (e) => events.push(e), fetchImpl },
    ),
    c,
  );
  assert.equal(events.length, 2);
});
test('disconnect and backend errors cannot synthesize saved reports', async () => {
  for (const text of [
    JSON.stringify(begin) + '\n',
    JSON.stringify({ type: 'error', message: '数据源失败' }) + '\n',
  ])
    await assert.rejects(
      readCaseStream(
        '/api/cases/stream',
        {},
        { onEvent: () => {}, fetchImpl: async () => new Response(text) },
      ),
    );
  assert.throws(() =>
    validateCase({ id: 'x', current: 2, versions: [{ no: 1 }] }),
  );
});
test('interrupted lookups are uncertain, and not-found results never get a success check', () => {
  let s = reduceEvent(state(), event('web', 'start'));
  for (const connection of ['disconnected', 'error'])
    assert.equal(
      stationState({ ...s, connection }, 'news').label,
      '状态待确认',
    );
  s = reduceEvent(s, event('web', 'done', 'not_found'));
  assert.equal(stationState(s, 'news').successful, false);
  s = reduceEvent(s, event('web', 'done', 'found'));
  assert.equal(stationState(s, 'news').successful, true);
});
test('paused animation does not own progress state; resume uses new results without snapping', () => {
  const d = new OfficeDirector();
  let s = reduceEvent(state(), event('lists', 'start'));
  d.tick(1000, s);
  d.tick(300, s);
  const before = d.sample();
  for (const step of s.steps) s = reduceEvent(s, event(step.id));
  s = { ...s, connection: 'saved' };
  assert.deepEqual(d.sample(), before);
  d.tick(16, s);
  const after = d.sample();
  assert.ok(
    Math.hypot(
      after.motion.position.x - before.motion.position.x,
      after.motion.position.y - before.motion.position.y,
    ) < 1,
  );
});

test('the desk stays clear until all sources finish and the actor brings the papers back', () => {
  let s = state();
  for (const step of s.steps.slice(0, -1)) s = reduceEvent(s, event(step.id));
  const candidate = { id: 'early', current: 1, versions: [{ no: 1 }] };
  for (const phase of ['research', 'walk', 'sort', 'sit', 'report']) {
    assert.equal(reports.reportPresentation(s, phase).visible, false);
    assert.equal(
      reports.reportPresentation(
        { ...s, candidate, saveStatus: 'unconfirmed' },
        phase,
      ).visible,
      false,
    );
  }
  s = reduceEvent(s, event(s.steps.at(-1).id));
  const saved = { ...s, connection: 'saved', result: candidate };
  const d = new OfficeDirector();
  let sawDossier = false;
  for (let i = 0; i < 6000 && !d.finished; i++) {
    d.tick(40, saved);
    const scene = d.sample();
    const report = reports.reportPresentation(saved, scene.phase.id);
    assert.equal(
      report.canOpen,
      true,
      'early reports remain immediately accessible, including while paused',
    );
    if (report.visible) {
      sawDossier = true;
      assert.equal(
        scene.sorting,
        1,
        'the dossier appeared before papers were sorted',
      );
      assert.deepEqual(scene.motion.position, SEAT);
    }
  }
  assert.equal(sawDossier, true);
  assert.equal(
    reports.reportPresentation(emptyResearch(), 'complete').visible,
    false,
    'switching company clears the old prop',
  );
});

test('a returned report is not clickable before independent save confirmation', () => {
  const candidate = {
    id: 'a/b',
    current: 1,
    versions: [{ no: 1 }],
    case: { company_name: '测试公司' },
  };
  const returned = { ...state(), candidate, verifying: true };
  assert.equal(reports.reportPresentation?.(returned).canOpen, false);
  assert.equal(
    reports.reportPresentation?.({
      ...returned,
      verifying: false,
      saveStatus: 'unconfirmed',
    }).label,
    '保存未确认，点击重试',
  );
  assert.equal(
    lifecycleLabel({
      ...returned,
      verifying: false,
      saveStatus: 'unconfirmed',
    }),
    '报告保存未确认',
  );
  const saved = {
    ...returned,
    verifying: false,
    connection: 'saved',
    result: candidate,
  };
  assert.equal(reports.reportPresentation?.(saved).canOpen, true);
  assert.equal(reports.reportPresentation?.(saved).href, '/xray/#/case/a%2Fb');
  assert.equal(
    reports.reportPresentation?.({ ...state(), connection: 'saved' }).canOpen,
    false,
    'connection alone cannot invent a report',
  );
});

test('a known save failure is retryable but cannot open a dossier', () => {
  const failed = {
    ...state(),
    connection: 'error',
    saveStatus: 'failed',
    error: '报告保存失败',
  };
  assert.equal(reports.reportPresentation?.(failed).canOpen, false);
  assert.equal(
    reports.reportPresentation?.(failed).label,
    '保存失败，点击重试',
  );
  assert.equal(reports.reportPresentation?.(failed).canRetry, true);
});

test('report prose completion waits for saving, and a disconnected report never looks active or saved', () => {
  let s = reduceEvent(emptyResearch(), {
    ...begin,
    steps: [
      { id: 'lists', label: '名单', lookup: true },
      { id: 'rules', label: '分析', lookup: false },
      { id: 'plain', label: '报告', lookup: false },
    ],
  });
  s = reduceEvent(s, event('lists'));
  s = reduceEvent(s, { ...event('rules'), coverage: undefined });
  s = reduceEvent(s, { ...event('plain'), coverage: undefined });
  assert.equal(reports.reportPresentation(s).label, '正在保存报告');
  assert.equal(reports.reportPresentation(s).canOpen, false);
  assert.equal(lifecycleLabel(s), '报告已生成 · 等待保存确认');
  assert.equal(
    reports.reportPresentation({ ...s, connection: 'disconnected' }).label,
    '连接中断，状态待确认',
  );
  assert.equal(
    reports.reportPresentation({ ...s, connection: 'error' }).label,
    '生成或保存失败',
  );
});

test('save confirmation reads the same case and rejects mismatched company or revision', async () => {
  const candidate = {
    id: 'saved',
    current: 1,
    versions: [{ no: 1 }],
    case: { company_name: '测试公司' },
  };
  const requests = [];
  const fetchImpl = async (url, init) => {
    requests.push([url, init?.method ?? 'GET']);
    return new Response(JSON.stringify(candidate));
  };
  const confirmed = await reports.confirmSavedCase?.(
    candidate,
    '测试公司',
    fetchImpl,
  );
  assert.deepEqual(confirmed, candidate);
  assert.deepEqual(requests, [['/api/cases/saved', 'GET']]);
  for (const value of [
    { ...candidate, case: { company_name: '旧公司' } },
    { ...candidate, id: 'old' },
    { ...candidate, current: 2, versions: [{ no: 2 }] },
  ])
    await assert.rejects(
      reports.confirmSavedCase(
        candidate,
        '测试公司',
        async () => new Response(JSON.stringify(value)),
      ),
    );
  await assert.rejects(
    reports.confirmSavedCase(
      candidate,
      '测试公司',
      async () => new Response('', { status: 503 }),
    ),
  );
});

test('binding waits for saved confirmation and closes and pushes continuously after sitting', () => {
  const d = new OfficeDirector();
  let s = state();
  for (const step of s.steps) s = reduceEvent(s, event(step.id));
  // An indefinitely slow report must leave its cover open, with planted feet at the desk.
  for (let i = 0; i < 3000; i++) d.tick(40, s);
  assert.equal(d.sample().binding, 0);
  assert.equal(d.sample().finished, false);
  assert.equal(d.sample().motion.distance, 0);
  assert.deepEqual(d.sample().motion.position, SEAT);
  s = {
    ...s,
    connection: 'saved',
    result: { id: 'saved', current: 1, versions: [{ no: 1 }] },
  };
  let lastBinding = 0,
    lastPush = 0,
    lastWing = 0;
  const seen = [];
  for (let i = 0; i < 400 && !d.finished; i++) {
    d.tick(20, s);
    const sample = d.sample();
    assert.ok(
      sample.binding >= lastBinding && sample.binding - lastBinding < 0.08,
      'cover snapped',
    );
    assert.ok(
      sample.pushing >= lastPush && sample.pushing - lastPush < 0.09,
      'folder teleported',
    );
    assert.ok(
      Math.abs(sample.wingReach - lastWing) < 0.14,
      'wing flashed between closing, pushing and presenting',
    );
    if (seen.at(-1) !== sample.phase.id) seen.push(sample.phase.id);
    lastBinding = sample.binding;
    lastPush = sample.pushing;
    lastWing = sample.wingReach;
  }
  assert.ok(seen.indexOf('bind-report') < seen.indexOf('push-report'));
  assert.ok(seen.includes('present-report'));
  assert.equal(lastBinding, 1);
  assert.equal(lastPush, 1);
  assert.equal(d.finished, true);
  assert.equal(lastWing, 0);
});
