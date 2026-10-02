'use client';
import type { CSSProperties, SyntheticEvent } from 'react';
import { useEffect, useState } from 'react';
import {
  BookOpen,
  Building2,
  Check,
  CirclePause,
  CirclePlay,
  Database,
  Menu,
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
  researchProgress,
} from './research-events';
import { ReportDossier } from './report-dossier';
import { OfficeInstruments } from './office-instruments';
import { SceneStatus } from './scene-status';
import { DemoExamples } from './demo-examples';
import { useProgressiveImages } from './use-progressive-images';
import type { DemoCase } from './research-input';
import type { Station } from './research-events';
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
  const [previewReady, setPreviewReady] = useState(false);
  const images = useProgressiveImages(previewReady);
  const [query, setQuery] = useState(''),
    [need, setNeed] = useState(''),
    [selectedDemo, setSelectedDemo] = useState<DemoCase | null>(null),
    [inspector, setInspector] = useState(false),
    [inspectorSource, setInspectorSource] = useState<Station | null>(null),
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
    reconnect,
    canReconnect,
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
  const progress = researchProgress(state);
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
    if (query.trim().length < 2) return;
    void begin(query, need, selectedDemo?.input);
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
        style={{
          '--door-progress': door,
          ...Object.fromEntries(Object.entries(images).map(([id, url]) => [
            `--image-${id}`, `url("${url}")`,
          ])),
        } as CSSProperties}
      >
        <img
          className="office-background"
          src={images.background}
          onLoad={() => setPreviewReady(true)}
          onError={() => setPreviewReady(true)}
          alt="企业研究室全景，包含图书架、企业档案、新闻资料、中央门和研究工位"
          width={1672}
          height={941}
          fetchPriority="high"
        />
        <div className="door-portal" aria-hidden="true" />
        <div className="door-leaf" aria-hidden="true" />
        <div className="ambient-vignette" aria-hidden="true" />
        <div className="window-breeze" aria-hidden="true" />
        {!idle && <OfficeInstruments state={state} />}
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
                className={`source-marker source-${source.id} ${s.active ? 'active' : ''} ${s.done ? 'done' : ''} ${s.failed ? 'failed' : ''} ${s.progress === 'unknown' ? 'unknown' : ''}`}
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
                {!idle && <button type="button" className="source-detail-trigger"
                  aria-label={`${source.title}：${s.label}，查看详情`}
                  onClick={() => { setInspectorSource(source.id); setInspector(true); }} />}
                {s.done && !s.failed ? (
                  <Check aria-hidden="true" />
                ) : s.failed || s.progress === 'unknown' ? (
                  <em aria-hidden="true">!</em>
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
            (s.id === 'reviews' || s.id === 'opinion') && s.phase === 'done' && s.coverage === 'found',
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
            artSrc={images.dossier}
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
          <img src="/research-assets/qier-icon.png" width={43} height={43} alt="" />
          <div>
            <strong>企er</strong>
            <small>小企研究室</small>
          </div>
        </div>
        <details className="office-menu">
          <summary aria-label="打开站点菜单" title="菜单"><Menu aria-hidden="true" /></summary>
          <nav className="office-nav" aria-label="站点导航">
            <a href="/xray/#/cases">案卷</a>
            <a href="/xray/#/new">附带材料查询</a>
            <a href="/xray/#/me">使用说明</a>
          </nav>
        </details>
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
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setSelectedDemo(null);
                  }}
                  placeholder="输入公司全称"
                  autoComplete="organization"
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229))
                      event.preventDefault();
                  }}
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
              <DemoExamples selected={selectedDemo} onSelect={(demo) => {
                setQuery(demo.input.company_name);
                setNeed(demo.input.need);
                setSelectedDemo(demo);
              }} onRemove={() => setSelectedDemo(null)} />
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
                  onClick={() => { setInspectorSource(null); setInspector((v) => !v); }}
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
            <SceneStatus state={state} />
            {!report.visible && (report.canOpen || report.canRetry) && (
              <div className="scene-report-actions">
                {report.canOpen ? <button className="report-ready-link" onClick={openReport} disabled={!!opening}>
                  {opening ? '正在打开报告' : '报告已就绪 · 查看报告'}
                </button> : <>
                  <p role="alert">{state.saveError ?? state.error ?? '保存状态需要确认'}</p>
                  <button onClick={() => {
                    if (state.candidate) void retrySave();
                    else setRetryConfirm(true);
                  }}>{report.label}</button>
                </>}
              </div>
            )}
            <output className="live-status">
              <strong>{life}</strong>
              <span className="current-task">{progress.current}</span>
              <ol className="stage-progress" aria-label="研究阶段">
                {progress.stages.map(stage => <li key={stage.id} data-state={stage.status}>
                  <b>{stage.title}</b><small>{stage.label}{stage.detail ? ` ${stage.detail}` : ''}</small>
                </li>)}
              </ol>
              <span>
                {collectionDone ? '资料收集结束' : '资料收集中'} ·{' '}
                {knownRecords} 条已找到记录
              </span>
              {paused && <small>动画已暂停，后台继续处理</small>}
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
                <a href="/xray/#/cases">
                  查看已保存案卷
                </a>
                {canReconnect && <button onClick={() => void reconnect()}>继续查看本次查询</button>}
                <button onClick={() => setRetryConfirm(true)}>重新查询</button>
              </div>
            )}
            {inspector && (
              <aside className="live-inspector">
                <strong>{inspectorSource ? `${stations.find(s => s.id === inspectorSource)?.title} · 查询明细` : '真实任务进度'}{testMode ? '（测试事件）' : ''}</strong>
                <button type="button" onClick={() => setInspector(false)} aria-label="关闭任务详情">关闭</button>
                <p>{progress.current}。多个资料点可能同时查询。</p>
                {!inspectorSource && <>
                  <p>{life} · {knownRecords} 条已找到记录</p>
                  <ol className="stage-progress" aria-label="研究阶段">
                    {progress.stages.map(stage => <li key={stage.id} data-state={stage.status}>
                      <b>{stage.title}</b><small>{stage.label}{stage.detail ? ` ${stage.detail}` : ''}</small>
                    </li>)}
                  </ol>
                  {paused && <p>动画已暂停，后台继续处理</p>}
                </>}
                {inspectorSource && <p>{stationState(state, inspectorSource).resultLabel}</p>}
                <ol>
                  {state.steps.filter(s => !inspectorSource || (stations.find(station => station.id === inspectorSource)!.steps as readonly string[]).includes(s.id)).map((s) => (
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
                              ? `已结束 · ${coverageLabels[s.coverage!]}`
                              : '已结束'}
                      </span>
                      <small>{s.text}</small>
                    </li>
                  ))}
                </ol>
                {inspectorSource && <button type="button" onClick={() => setInspectorSource(null)}>查看全部阶段</button>}
                <small>小企动作：{phase.label}</small>
                <label>
                  动画速度
                  <select
                    aria-label="播放速度"
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    <option value={1}>跟随任务</option>
                    <option value={2}>加速</option>
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
