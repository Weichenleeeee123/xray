// Explicit localhost-only transport fixtures. Never presented as real research.
import type { ProgressEvent } from './research-events';
export const testNames = [
  'fast',
  'slow',
  'parallel',
  'failed',
  'disconnect',
  'switch',
  'social-found',
  'social-empty',
  'report-slow',
  'save-failed',
  'save-unconfirmed',
] as const;
export type TestName = (typeof testNames)[number];
const steps = [
  ['intake', '理解需求', false],
  ['lists', '持牌名单', true],
  ['registry', '工商登记', true],
  ['pack', '人工文书', true],
  ['web', '公开报道', true],
  ['amac', '私募登记', true],
  ['reviews', '用户评价', true],
  ['rules', '对照规则', false],
  ['plain', '写成短句', false],
].map(([id, label, lookup]) => ({
  id: String(id),
  label: String(label),
  lookup: Boolean(lookup),
}));
export function fixtureFetch(
  name: TestName,
  onLog?: (text: string) => void,
): typeof fetch {
  let result: Record<string, unknown>;
  let queries = 0,
    reads = 0;
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!init?.method || init.method === 'GET') {
      reads++;
      if (name === 'save-unconfirmed' && reads === 1)
        return new Response('测试：暂时无法读回案卷', { status: 503 });
      return new Response(JSON.stringify(result), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (typeof init.body !== 'string')
      throw new Error('测试接口需要 JSON 字符串');
    const body = JSON.parse(init.body);
    queries++;
    result = {
      id: 'fixture' + name + '-' + queries,
      created_at: new Date().toISOString(),
      current: 1,
      case: { company_name: body.company_name },
      versions: [{ no: 1 }],
      test: true,
    };
    const plan = name.startsWith('social-')
      ? steps.filter((s) => ['reviews', 'rules', 'plain'].includes(s.id))
      : steps;
    const events: Array<[number, unknown]> = [
      [
        0,
        {
          type: 'begin',
          company: body.company_name,
          steps: plan,
        } satisfies ProgressEvent,
      ],
    ];
    let t = 20;
    for (const [i, s] of plan.entries()) {
      const parallel = name === 'parallel';
      const start = parallel
        ? s.lookup
          ? 100
          : s.id === 'intake'
            ? 10
            : s.id === 'rules'
              ? 10500
              : 11000
        : t;
      const duration =
        name === 'report-slow' && s.id === 'plain'
          ? 80000
          : name.startsWith('social-') && s.lookup
            ? 5000
            : name === 'fast'
              ? 8
              : name === 'slow'
                ? s.lookup
                  ? 5000
                  : 500
                : parallel
                  ? 1500 + i * 1000
                  : 300;
      events.push([
        start,
        { type: 'step', id: s.id, label: s.label, phase: 'start' },
      ]);
      let coverage = s.lookup ? 'found' : null;
      if (name === 'social-empty' && s.lookup) coverage = 'not_found';
      if (name === 'failed' && s.lookup)
        coverage =
          s.id === 'web'
            ? 'failed'
            : s.id === 'reviews'
              ? 'not_found'
              : s.id === 'pack'
                ? 'not_covered'
                : 'found';
      events.push([
        start + duration,
        {
          type: 'step',
          id: s.id,
          label: s.label,
          phase: 'done',
          coverage,
          counts: s.lookup
            ? {
                found: coverage === 'found' ? 1 : 0,
                failed: coverage === 'failed' ? 1 : 0,
                not_found: coverage === 'not_found' ? 1 : 0,
                not_covered: coverage === 'not_covered' ? 1 : 0,
              }
            : null,
          text: '测试事件：' + (coverage ?? '处理完成'),
        },
      ]);
      t = start + duration + 20;
    }
    const end = Math.max(...events.map((e) => e[0])) + 100;
    events.push([
      end,
      name === 'save-failed' && queries === 1
        ? { type: 'error', status: 500, message: '测试事件：报告保存失败' }
        : { type: 'case', case: result },
    ]);
    events.sort((a, b) => a[0] - b[0]);
    let timers: ReturnType<typeof setTimeout>[] = [];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const stop = () => {
          timers.forEach(clearTimeout);
          timers = [];
        };
        init.signal?.addEventListener(
          'abort',
          () => {
            stop();
            controller.error(new DOMException('Aborted', 'AbortError'));
          },
          { once: true },
        );
        events.forEach(([delay, event]) => {
          if (name === 'disconnect' && delay > 1500) return;
          timers.push(
            setTimeout(() => {
              onLog?.(JSON.stringify(event));
              controller.enqueue(
                new TextEncoder().encode(JSON.stringify(event) + '\n'),
              );
            }, delay),
          );
        });
        timers.push(
          setTimeout(
            () => {
              controller.close();
              stop();
            },
            name === 'disconnect' ? 1501 : end + 30,
          ),
        );
      },
      cancel() {
        timers.forEach(clearTimeout);
      },
    });
    return new Response(stream, {
      headers: { 'Content-Type': 'application/x-ndjson' },
    });
  }) as typeof fetch;
}
