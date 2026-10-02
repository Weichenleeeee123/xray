'use client';
import type { CSSProperties, SyntheticEvent } from 'react';
import { useEffect, useState } from 'react';
import Image from 'next/image';
import {
  BookOpen,
  Building2,
  Check,
  CirclePause,
  CirclePlay,
  Database,
  MessageCircle,
  Newspaper,
  Search,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useOfficeResearch } from './use-office-research';
import {
  stations,
  stationState,
  lifecycleLabel,
  collectionFinished,
  coverageLabels,
  reportPresentation,
} from './research-events';
import { ReportDossier } from './report-dossier';
const icons = {
  enterprise: Building2,
  library: BookOpen,
  news: Newspaper,
  data: Database,
  social: MessageCircle,
};
const papers = [
  { x: 42.5, y: 74.2, rotate: -7, frame: 0 },
  { x: 57.8, y: 74.8, rotate: 8, frame: 1 },
  { x: 62.3, y: 83.2, rotate: -13, frame: 2 },
  { x: 36.7, y: 82.5, rotate: 15, frame: 3 },
  { x: 68.7, y: 90.2, rotate: 9, frame: 0 },
  { x: 31.8, y: 90.8, rotate: -18, frame: 1 },
  { x: 58.2, y: 91.5, rotate: 17, frame: 2 },
  { x: 43.3, y: 94.1, rotate: -8, frame: 3 },
  { x: 64.4, y: 95.2, rotate: -4, frame: 0 },
  { x: 35.1, y: 95.4, rotate: 11, frame: 2 },
];
const breeze = [
  { kind: 'leaf', frame: 0, x: 4.5, y: 28, delay: 0 },
  { kind: 'leaf', frame: 1, x: 7.5, y: 37, delay: 420 },
  { kind: 'leaf', frame: 2, x: 10, y: 44, delay: 830 },
  { kind: 'paper', frame: 1, x: 17, y: 54, delay: 160 },
  { kind: 'paper', frame: 3, x: 24, y: 65, delay: 760 },
];
const clamp = (n: number) => Math.max(0, Math.min(1, n));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export default function Home() {
  const [query, setQuery] = useState(''),
    [need, setNeed] = useState(''),
    [inspector, setInspector] = useState(false),
    [retryConfirm, setRetryConfirm] = useState(false),
    [testResult, setTestResult] = useState(false),
    [opening, setOpening] = useState<{ id: string; href: string } | null>(null);
  const {
    state,
    scene,
    paused,
    setPaused,
    speed,
    setSpeed,
    testMode,
    begin,
    reset,
    step,
    retry,
    retrySave,
  } = useOfficeResearch();
  const idle = state.connection === 'idle',
    status = idle
      ? 'idle'
      : paused
        ? 'paused'
        : scene.finished
          ? 'complete'
          : 'running';
  const { phase, motion, seated, local, door } = scene;
  const walking = phase.mode === 'walk',
    research = phase.visual === 'research';
  const actionFrame = research
    ? [1, 2, 2, 1][Math.floor(local / 400) % 4]
    : phase.visual === 'door'
      ? Math.min(1, Math.floor(local / 450))
      : phase.visual === 'talk'
        ? 2
        : phase.visual === 'desk'
          ? Math.floor(local / 600) % 4
          : phase.visual === 'gather' || phase.visual === 'sort'
            ? Math.floor(local / 550) % 2
            : 1;
  const actorStyle = {
    '--actor-x': motion.position.x + '%',
    '--actor-y': motion.position.y + '%',
    '--walk-frame': (motion.frame * 100) / 3 + '%',
    '--seated': seated,
    '--seated-mix': seated > 0.85 ? (seated - 0.85) / 0.15 : 0,
    '--action-frame': (actionFrame * 100) / 3 + '%',
    '--gesture': Math.sin(local / 220) * 1.5 + 'deg',
  } as CSSProperties;
  const knownRecords = state.steps
    .filter((s) => s.lookup && s.phase === 'done')
    .reduce((n, s) => n + (s.counts?.found ?? 0), 0);
  const visiblePaperCount = Math.min(10, knownRecords),
    collectionDone = collectionFinished(state),
    life = lifecycleLabel(state);
  const report = reportPresentation(state, phase.id);
  const openReport = () => {
    if (report.canOpen && report.href && state.result && !opening)
      setOpening({ id: state.result.id, href: report.href });
  };
  useEffect(() => {
    if (!opening) return;
    if (opening.id !== state.result?.id || state.connection !== 'saved') {
      queueMicrotask(() => setOpening(null));
      return;
    }
    const timer = setTimeout(() => {
      if (testMode) {
        setTestResult(true);
        setOpening(null);
      } else window.location.assign(opening.href);
    }, 400);
    return () => clearTimeout(timer);
  }, [opening, state.result?.id, state.connection, testMode]);
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    void begin(query, need);
  };
  useEffect(() => {
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: unknown,
            options: { signal: AbortSignal },
          ) => void;
        };
      }
    ).modelContext;
    if (!context) return;
    const controller = new AbortController();
    try {
      context.registerTool(
        {
          name: 'start_company_research',
          title: '开始企业研究',
          description: '调用真实后端进度流；动画不控制查询时长。',
          inputSchema: {
            type: 'object',
            properties: {
              company: { type: 'string', minLength: 2, maxLength: 80 },
            },
            required: ['company'],
            additionalProperties: false,
          },
          execute: (input: { company: string }) => {
            if (
              typeof input.company !== 'string' ||
              input.company.trim().length < 2
            )
              throw new Error('请输入公司名称');
            setQuery(input.company);
            void begin(input.company);
            return { status: 'connecting', company: input.company };
          },
        },
        { signal: controller.signal },
      );
    } catch {}
    return () => controller.abort();
  }, [begin]);
  return (
    <main className="office-page">
      <section
        className={`office-stage status-${status} breeze-active live-office ${opening ? 'report-opening' : ''}`}
        aria-label="小企企业研究室"
        style={{ '--door-progress': door } as CSSProperties}
      >
        <Image
          className="office-background"
          src="/office-panorama-closed.png"
          alt="企业研究室全景，包含图书架、企业档案、新闻资料、中央门和研究工位"
          fill
          priority
          sizes="100vw"
        />
        <div className="door-portal" aria-hidden="true" />
        <div className="door-leaf" aria-hidden="true" />
        <div className="ambient-vignette" aria-hidden="true" />
        <div className="window-breeze" aria-hidden="true" />
        {breeze.map((item, i) => (
          <span
            key={i}
            aria-hidden="true"
            className={`motion-sprite breeze-sprite ${item.kind} frame-${item.frame}`}
            style={
              {
                '--item-x': item.x + '%',
                '--item-y': item.y + '%',
                '--item-delay': item.delay + 'ms',
              } as CSSProperties
            }
          />
        ))}
        {papers.map((paper, i) => {
          const left = paper.x < 50,
            gather = left ? scene.gathering : scene.gatheringRight,
            pickup = clamp((gather - (i % 5) * 0.12) / 0.5),
            sort = clamp((scene.sorting - i * 0.045) / 0.55);
          const x = lerp(
              lerp(paper.x, motion.position.x + 3, pickup),
              i % 2 ? 42 : 39,
              sort,
            ),
            y = lerp(
              lerp(paper.y, motion.position.y - 13, pickup),
              76 - i * 0.16,
              sort,
            );
          return (
            <span
              key={i}
              aria-hidden="true"
              data-paper={i}
              className={`motion-sprite evidence-paper frame-${paper.frame} ${i < visiblePaperCount ? 'visible' : ''}`}
              style={
                {
                  '--paper-x': x + '%',
                  '--paper-y': y + '%',
                  '--paper-rotate': lerp(paper.rotate, 0, sort) + 'deg',
                  '--paper-delay': '0ms',
                } as CSSProperties
              }
            />
          );
        })}
        <ol
          className={`source-markers ${idle ? 'idle' : ''}`}
          aria-label="企业资料来源"
        >
          {stations.map((source) => {
            const s = stationState(state, source.id),
              Icon = icons[source.id];
            return (
              <li
                key={source.id}
                className={`source-marker source-${source.id} ${s.active ? 'active' : ''} ${s.successful ? 'done' : ''} ${s.failed ? 'failed' : ''}`}
                data-source={source.id}
                data-status={s.label}
                title={s.details || source.caption}
              >
                <span>
                  <Icon aria-hidden="true" />
                </span>
                <div>
                  <strong>{source.title}</strong>
                  <small>{idle ? source.caption : s.label}</small>
                </div>
                {s.successful ? (
                  <Check aria-hidden="true" />
                ) : (
                  <i aria-hidden="true" />
                )}
              </li>
            );
          })}
        </ol>
        {door > 0.12 && (
          <figure
            className="visitor-goose"
            style={{ opacity: Math.min(1, door * 3) }}
            aria-label="门外提供未经核实用户评价的访客鹅"
          >
            <span className="visitor-sprite" />
          </figure>
        )}
        {state.steps.some(
          (s) =>
            s.id === 'reviews' && s.phase === 'done' && s.coverage === 'found',
        ) &&
          !scene.socialHandled &&
          door === 0 && (
            <div className="knock-effect" aria-label="门外传来敲门声">
              <span />
              <span />
              <span />
              <strong>咚 · 咚</strong>
            </div>
          )}
        <figure
          className={`xiaoqi-actor ${walking ? 'walking' : 'stationary'} facing-${motion.facing} action-${phase.visual}`}
          style={actorStyle}
          data-phase={phase.id}
          data-distance={motion.distance.toFixed(2)}
          aria-label={`穿西装的小企正在${phase.label}`}
        >
          <span className="seated-body" aria-hidden="true" />
          <span className="standing-body" aria-hidden="true">
            {walking ? (
              (['back', 'front', 'left', 'right'] as const).map((direction) => (
                <span
                  key={direction}
                  className={`distance-walk walk-${direction}`}
                  style={{ opacity: direction === motion.facing ? 1 : 0 }}
                />
              ))
            ) : (
              <>
                <span
                  className={`planted-feet ${research ? 'research-feet' : ''}`}
                />
                <span
                  className={`gesture-body ${research ? 'research-body' : ''}`}
                />
              </>
            )}
          </span>
        </figure>
        <div
          className="chair-foreground"
          style={{ opacity: seated > 0.85 ? 1 : 0 }}
          aria-hidden="true"
        />
        {!idle && (
          <ReportDossier
            state={state}
            scene={scene}
            opening={!!opening}
            onOpen={openReport}
            onRetry={() => {
              if (state.candidate) void retrySave();
              else setRetryConfirm(true);
            }}
          />
        )}
        <div className="report-transition" aria-hidden="true" />
        <div className="scene-brand" aria-label="企er 小企研究室">
          <span>企</span>
          <div>
            <strong>企er</strong>
            <small>小企研究室</small>
          </div>
        </div>
        {idle && (
          <div className="query-layer visible">
            <form className="home-query" onSubmit={submit}>
              <span className="query-kicker">
                <Sparkles /> 查企业
              </span>
              <h1>想先查哪家公司？</h1>
              <label className="sr-only" htmlFor="company-query">
                公司全称
              </label>
              <div className="prompt-bar">
                <Search aria-hidden="true" />
                <Input
                  id="company-query"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="输入公司全称"
                  maxLength={80}
                />
                <Button type="submit" disabled={query.trim().length < 2}>
                  开始查询
                </Button>
              </div>
              <label className="need-field" htmlFor="research-need">
                研究需求（选填）
                <Input
                  id="research-need"
                  value={need}
                  onChange={(e) => setNeed(e.target.value)}
                  placeholder="例如：了解这家公司的登记、资质与公开资料"
                  maxLength={500}
                />
              </label>
              <p>资料覆盖情况来自真实后端，不代表安全评级。</p>
            </form>
          </div>
        )}
        {testMode && (
          <div className="test-mode-badge">
            测试事件 · {testMode} · 非真实查询
          </div>
        )}
        {!idle && (
          <>
            <div className="research-hud">
              <div className="research-subject">
                <i />
                <span>{state.company}</span>
              </div>
              <div className="research-controls">
                <button
                  type="button"
                  onClick={() => setInspector((v) => !v)}
                  aria-label="任务与动作详情"
                >
                  ⌕
                </button>
                <button
                  type="button"
                  onClick={() => setPaused((v) => !v)}
                  aria-label={paused ? '继续动画' : '暂停动画'}
                >
                  {paused ? <CirclePlay /> : <CirclePause />}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setOpening(null);
                    reset();
                  }}
                  aria-label="切换公司"
                >
                  换
                </button>
              </div>
            </div>
            <output className="live-status">
              <strong>{life}</strong>
              <span>
                {collectionDone ? '资料收集结束' : '资料查询尚未结束'} ·{' '}
                {knownRecords} 条已找到记录
              </span>
              <small>
                动画：{phase.label}
                {paused ? '（已暂停，后台继续）' : ''}
              </small>
              {report.canOpen && report.visible && (
                <span className="dossier-hint">
                  点击桌面上的发光卷宗，查看报告
                </span>
              )}
              {report.canOpen && !report.visible && (
                <button
                  className="report-ready-link"
                  onClick={openReport}
                  disabled={!!opening}
                >
                  {opening ? '正在打开报告' : '报告已就绪 · 查看报告'}
                </button>
              )}
              {report.canRetry && !report.visible && (
                <button
                  onClick={() => {
                    if (state.candidate) void retrySave();
                    else setRetryConfirm(true);
                  }}
                >
                  {report.label}
                </button>
              )}
            </output>
            {state.error && !state.saveStatus && (
              <div className="connection-notice" role="alert">
                <strong>{state.error}</strong>
                <p>
                  连接中断时，后端可能仍在处理。可先查看已保存案卷，避免重复查询。
                </p>
                <a href="/xray/#/cases" target="_blank" rel="noreferrer">
                  查看已保存案卷
                </a>
                <button onClick={() => setRetryConfirm(true)}>重新查询</button>
              </div>
            )}
            {inspector && (
              <aside className="live-inspector">
                <strong>真实任务进度{testMode ? '（测试事件）' : ''}</strong>
                <p>资料点可并行查询；动作队列不会阻塞后端。</p>
                <ol>
                  {state.steps.map((s) => (
                    <li key={s.id}>
                      <b>{s.label}</b>
                      <span>
                        {s.phase === 'waiting'
                          ? '等待查询'
                          : s.phase === 'start'
                            ? ['disconnected', 'error'].includes(
                                state.connection,
                              )
                              ? '状态待确认'
                              : '查询中'
                            : s.lookup
                              ? coverageLabels[s.coverage!]
                              : '已结束'}
                      </span>
                      <small>{s.text}</small>
                    </li>
                  ))}
                </ol>
                <label>
                  动画速度
                  <select
                    aria-label="播放速度"
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    <option value={1}>正常速度</option>
                    <option value={0.25}>四分之一速度</option>
                  </select>
                </label>
                <button disabled={!paused} onClick={step}>
                  下一帧
                </button>
                <small>仅控制动画；后台进度不暂停。</small>
              </aside>
            )}
          </>
        )}
        {retryConfirm && (
          <dialog
            open
            className="local-dialog"
            aria-modal="true"
            aria-label="确认重新查询"
          >
            <p>
              旧查询可能已在后台保存。重新查询会创建一份新案卷，并可能再次调用数据源。
            </p>
            <button onClick={() => setRetryConfirm(false)}>取消</button>
            <button
              onClick={() => {
                setRetryConfirm(false);
                void retry();
              }}
            >
              确认重新查询
            </button>
          </dialog>
        )}
        {testResult && (
          <dialog open className="local-dialog" aria-label="测试结果">
            <p>这是合成事件的保存确认，不是真实报告。</p>
            <button onClick={() => setTestResult(false)}>关闭</button>
          </dialog>
        )}
      </section>
    </main>
  );
}
