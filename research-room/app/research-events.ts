// Adapter for X-Ray's existing web/research-progress.js NDJSON contract.
export type Coverage = 'found' | 'not_found' | 'not_covered' | 'failed';
export type Step = {
  id: string;
  label: string;
  lookup: boolean;
  phase: 'waiting' | 'start' | 'done';
  coverage?: Coverage;
  counts?: Partial<Record<Coverage, number>>;
  text?: string;
};
export type CaseResult = {
  id: string;
  created_at?: string;
  current: number;
  versions: Array<{ no: number; [key: string]: unknown }>;
  case?: { company_name?: string; need?: string; [key: string]: unknown };
  [key: string]: unknown;
};
export type CaseReference = Pick<CaseResult, 'id' | 'created_at'> &
  Partial<Pick<CaseResult, 'current'>>;
export type ResearchInput = { company_name: string; need: string; [key: string]: unknown };
export type ProgressEvent =
  | {
      type: 'begin';
      company: string;
      steps: Array<Pick<Step, 'id' | 'label' | 'lookup'>>;
    }
  | {
      type: 'step';
      id: string;
      label: string;
      phase: 'start' | 'done';
      coverage?: Coverage;
      counts?: Step['counts'];
      text?: string;
    };
export type ResearchState = {
  steps: Step[];
  company: string;
  connection:
    | 'idle'
    | 'connecting'
    | 'live'
    | 'disconnected'
    | 'error'
    | 'saved';
  result?: CaseResult;
  candidate?: CaseReference;
  saveStatus?: 'unconfirmed' | 'failed';
  saveError?: string;
  error?: string;
  verifying: boolean;
};
export const emptyResearch = (): ResearchState => ({
  steps: [],
  company: '',
  connection: 'idle',
  verifying: false,
});
export const stations = [
  {
    id: 'enterprise',
    title: '企业资料',
    caption: '持牌名单 · 工商登记',
    steps: ['lists', 'registry'],
  },
  {
    id: 'library',
    title: '图书年报',
    caption: '人工摘录文书 · 证据包',
    steps: ['pack'],
  },
  {
    id: 'news',
    title: '政府公告',
    caption: '监管 · 法院 · 政府网站',
    steps: ['web'],
  },
  {
    id: 'data',
    title: '经营数据',
    caption: '私募登记 · 财务数据',
    steps: ['amac', 'finance'],
  },
  {
    id: 'social',
    title: '社会舆情',
    caption: '新闻舆情 · 网上投诉 · 用户评价',
    steps: ['opinion', 'reviews'],
  },
] as const;
export type Station = (typeof stations)[number]['id'];
export const coverageLabels: Record<Coverage, string> = {
  found: '已查到',
  not_found: '未找到',
  not_covered: '未查询',
  failed: '查询失败',
};
export function reduceEvent(
  state: ResearchState,
  event: ProgressEvent,
): ResearchState {
  if (event.type === 'begin')
    return {
      ...state,
      connection: 'live',
      company: event.company,
      steps: event.steps.map((s) => ({ ...s, phase: 'waiting' })),
    };
  const current = state.steps.find((s) => s.id === event.id);
  if (!current) throw new Error('后端步骤不在任务计划中');
  // Duplicate/out-of-order starts must never erase a terminal result.
  if (current.phase === 'done' && event.phase === 'start') return state;
  if (
    event.phase === 'done' &&
    current.lookup &&
    !['found', 'not_found', 'not_covered', 'failed'].includes(
      event.coverage ?? '',
    )
  )
    throw new Error('查询结果缺少有效覆盖状态');
  return {
    ...state,
    connection: 'live',
    steps: state.steps.map((s) => (s.id === event.id ? { ...s, ...event } : s)),
  };
}
export const collectionFinished = (state: ResearchState) =>
  state.steps.some((s) => s.lookup) &&
  state.steps.filter((s) => s.lookup).every((s) => s.phase === 'done');
// Completed processing steps, not a prediction of time or a company safety score.
// Reading the saved case back is one final, real step.
export function researchProgress(state: ResearchState) {
  const saved = state.connection === 'saved' && !!state.result;
  const completed = state.steps.filter((step) => step.phase === 'done').length + Number(saved);
  const total = state.steps.length + 1;
  return { completed, total, percent: saved ? 100 : Math.floor(completed / total * 100) };
}
export function stationState(state: ResearchState, id: Station) {
  const definition = stations.find((s) => s.id === id)!;
  const tasks = state.steps.filter((s) =>
    (definition.steps as readonly string[]).includes(s.id),
  );
  const active = tasks.some((s) => s.phase === 'start');
  const done = tasks.filter((s) => s.phase === 'done');
  const counts: Partial<Record<Coverage, number>> = {};
  for (const task of done) {
    for (const key of Object.keys(coverageLabels) as Coverage[])
      counts[key] = (counts[key] ?? 0) + (task.counts?.[key] ?? 0);
  }
  const outcomes = [
    ...new Set([
      ...done.map((s) => s.coverage).filter(Boolean),
      ...Object.keys(counts).filter((k) => (counts[k as Coverage] ?? 0) > 0),
    ]),
  ] as Coverage[];
  const label = active
    ? ['disconnected', 'error'].includes(state.connection)
      ? '状态待确认'
      : '查询中'
    : !tasks.length
      ? state.steps.length
        ? '未查询'
        : '等待任务'
      : !done.length
        ? '等待查询'
        : outcomes.map((c) => coverageLabels[c]).join(' · ') +
          (done.length < tasks.length ? ' · 仍有待查' : '');
  const complete = done.length === tasks.length && tasks.length > 0;
  return {
    tasks,
    active,
    done: complete,
    successful: complete && outcomes.length === 1 && outcomes[0] === 'found',
    label,
    counts,
    failed: outcomes.includes('failed'),
    details: tasks
      .map(
        (s) =>
          `${s.label}：${s.phase === 'waiting' ? '等待查询' : s.phase === 'start' ? label : (coverageLabels[s.coverage!] ?? '已结束')}${s.text ? '；' + s.text : ''}`,
      )
      .join('\n'),
  };
}
export function lifecycleLabel(state: ResearchState) {
  if (state.saveStatus === 'failed') return '报告保存失败';
  if (state.saveStatus === 'unconfirmed' && !state.verifying)
    return '报告保存未确认';
  if (state.connection === 'disconnected') return '连接中断 · 进度待确认';
  if (state.connection === 'error') return '研究中断';
  if (state.connection === 'saved') return '报告已保存';
  if (state.verifying) return '报告已返回 · 确认保存中';
  if (state.steps.some((s) => s.id === 'plain' && s.phase === 'done'))
    return '报告已生成 · 等待保存确认';
  if (state.steps.some((s) => s.id === 'plain' && s.phase === 'start'))
    return '报告生成中';
  if (state.steps.some((s) => s.id === 'rules' && s.phase === 'start'))
    return '整理分析中';
  if (collectionFinished(state)) return '资料收集结束';
  if (state.steps.some((s) => s.lookup && s.phase === 'start'))
    return '查询资料中';
  return state.steps.length ? '理解研究需求' : '连接后端中';
}
// Backend truth controls availability; the scene clock controls only the physical cover.
export function reportPresentation(state: ResearchState, scenePhase?: string) {
  const canOpen = state.connection === 'saved' && !!state.result;
  const canRetry = !state.verifying && !!state.saveStatus;
  const plain = state.steps.find((s) => s.id === 'plain');
  const rules = state.steps.find((s) => s.id === 'rules');
  let status = 'collecting',
    label = '正在收集资料';
  if (canOpen) {
    status = 'saved';
    label = '查看报告';
  } else if (state.verifying) {
    status = 'verifying';
    label = '正在确认保存';
  } else if (state.saveStatus === 'failed') {
    status = 'failed';
    label = '保存失败，点击重试';
  } else if (state.saveStatus === 'unconfirmed') {
    status = 'unconfirmed';
    label = '保存未确认，点击重试';
  } else if (state.connection === 'disconnected') {
    status = 'interrupted';
    label = '连接中断，状态待确认';
  } else if (state.connection === 'error') {
    status = 'interrupted';
    label = '生成或保存失败';
  } else if (plain?.phase === 'done') {
    status = 'saving';
    label = '正在保存报告';
  } else if (plain?.phase === 'start') {
    status = 'generating';
    label = '正在生成报告';
  } else if (
    (rules && rules.phase !== 'waiting') ||
    collectionFinished(state)
  ) {
    status = 'analyzing';
    label = '正在整理分析';
  }
  return {
    canOpen,
    canRetry,
    status,
    label,
    // A saved result may arrive while the actor is still at a source station.
    // Keep access independent, but place the prop only after bringing papers back.
    visible:
      collectionFinished(state) &&
      [
        'sit',
        'report',
        'bind-report',
        'push-report',
        'present-report',
        'complete',
      ].includes(scenePhase ?? ''),
    href: canOpen
      ? `/xray/#/case/${encodeURIComponent(state.result!.id)}`
      : undefined,
  };
}

export async function confirmSavedCase(
  candidate: CaseReference,
  company: string,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
) {
  const response = await fetchImpl(
    '/api/cases/' + encodeURIComponent(candidate.id),
    { signal, cache: 'no-store' },
  );
  if (!response.ok) throw new Error('报告已返回，但暂时无法读回案卷确认保存');
  const confirmed = validateCase(await response.json());
  if (
    confirmed.id !== candidate.id ||
    (candidate.current !== undefined &&
      confirmed.current !== candidate.current) ||
    confirmed.case?.company_name !== company
  )
    throw new Error('案卷保存校验不一致');
  return confirmed;
}
export function validateCase(c: unknown): CaseResult {
  const value = c as CaseResult;
  if (
    !value ||
    typeof value.id !== 'string' ||
    !value.id ||
    !Number.isInteger(value.current) ||
    !Array.isArray(value.versions) ||
    !value.versions.some((v) => v.no === value.current)
  )
    throw new Error('未收到完整案卷');
  return value;
}
export class BackendError extends Error {}
// Reuses the existing reader's incremental UTF-8 decoding, final-line and case validation.
export async function readCaseStream(
  url: string,
  body: unknown,
  {
    onEvent,
    signal,
    fetchImpl = fetch,
  }: {
    onEvent: (e: ProgressEvent) => void;
    signal?: AbortSignal;
    fetchImpl?: typeof fetch;
  },
) {
  const response = await fetchImpl(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    throw new BackendError(
      typeof error.detail === 'string'
        ? error.detail
        : `请求失败（${response.status}）`,
    );
  }
  if (!response.body) throw new Error('未收到进度流');
  const reader = response.body.getReader(),
    decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  function parse(line: string) {
    if (!line.trim()) return null;
    const e = JSON.parse(line);
    if (e.type === 'error') throw new BackendError(e.message || '后端研究失败');
    if (e.type === 'case') return validateCase(e.case);
    if (!['begin', 'step'].includes(e.type))
      throw new Error('收到未知进度事件');
    onEvent(e);
    return null;
  }
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let i;
      while ((i = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, i);
        buffer = buffer.slice(i + 1);
        const c = parse(line);
        if (c) return c;
      }
      if (done) {
        const c = parse(buffer);
        if (c) return c;
        throw new Error('连接结束但未收到报告，后端可能仍在运行');
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

// ---------- 刷新后能接着看：后端把每次查询记成一个任务（/api/runs），按编号取进度 ----------
export type RunStatus = 'running' | 'complete' | 'error' | 'interrupted';
export type RunPage = {
  run_id: string;
  status: RunStatus;
  case_id: string | null;
  events: Array<Record<string, unknown>>;
  next: number;
  version?: number | null;
  input?: { kind: string; body: ResearchInput } | null;
};
export async function startRun(
  body: unknown,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const response = await fetchImpl('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = (await response.json().catch(() => ({}))) as {
    run_id?: unknown;
    detail?: unknown;
  };
  if (!response.ok || typeof data.run_id !== 'string')
    throw new BackendError(
      typeof data.detail === 'string'
        ? data.detail
        : `请求失败（${response.status}）`,
    );
  return data.run_id;
}
// 轮询任务进度，把 begin/step 交给 onEvent；任务完成返回案卷编号。
// 页面刷新后用同一个编号再调一次，从头补齐事件，不会重新提交查询。
export async function followRun(
  runId: string,
  {
    onEvent,
    signal,
    fetchImpl = fetch,
    interval = 600,
    onInput,
    onComplete,
  }: {
    onEvent: (e: ProgressEvent) => void;
    signal?: AbortSignal;
    fetchImpl?: typeof fetch;
    interval?: number;
    onInput?: (input: ResearchInput) => void;
    onComplete?: (candidate: CaseReference) => void;
  },
): Promise<string> {
  let next = 0;
  for (;;) {
    const response = await fetchImpl(
      `/api/runs/${encodeURIComponent(runId)}?after=${next}`,
      { signal, cache: 'no-store' },
    );
    if (response.status === 404)
      throw new BackendError(
        '找不到这次查询，可能后端换了机器或数据被清理，请重新查询',
      );
    if (!response.ok) throw new Error(`进度查询失败（${response.status}）`);
    const page = (await response.json()) as RunPage;
    if (page.run_id !== undefined && page.run_id !== runId)
      throw new Error('任务编号校验不一致');
    if (!Array.isArray(page.events) || !Number.isInteger(page.next) || page.next < next)
      throw new Error('任务进度数据不完整');
    if (page.input?.kind === 'create') {
      const input = page.input.body;
      if (!input || typeof input.company_name !== 'string' || typeof input.need !== 'string')
        throw new Error('原始需求数据不完整');
      onInput?.(input);
    }
    for (const e of page.events) {
      if (e.type === 'begin' || e.type === 'step') onEvent(e as ProgressEvent);
      if (e.type === 'error')
        throw new BackendError(String(e.message || '后端研究失败'));
    }
    next = page.next;
    if (page.status === 'complete' && page.case_id) {
      const event = page.events.findLast((e) => e.type === 'complete');
      const version = page.version ?? event?.version;
      if (event?.case_id !== undefined && event.case_id !== page.case_id)
        throw new Error('任务案卷校验不一致');
      if (version !== undefined && version !== null && (!Number.isInteger(version) || Number(version) < 1))
        throw new Error('任务版本校验不一致');
      onComplete?.({ id: page.case_id, ...(version ? { current: Number(version) } : {}) });
      return page.case_id;
    }
    if (page.status === 'error') throw new BackendError('后端研究失败');
    if (page.status === 'interrupted')
      throw new BackendError('后端中途重启过，这次查询没有跑完，请重新查询');
    await new Promise((resolve, reject) => {
      const stop = () => {
        clearTimeout(timer);
        signal?.removeEventListener('abort', stop);
        reject(new DOMException('aborted', 'AbortError'));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener('abort', stop);
        resolve(undefined);
      }, interval);
      if (signal?.aborted) stop();
      else signal?.addEventListener('abort', stop, { once: true });
    });
  }
}
