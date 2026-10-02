'use client';

import type { CSSProperties, SyntheticEvent } from 'react';
import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import {
  ArrowRight,
  BookOpen,
  Building2,
  CheckCircle2,
  Check,
  CirclePause,
  CirclePlay,
  Database,
  MessageCircle,
  Newspaper,
  RotateCcw,
  Search,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type ResearchStatus = 'idle' | 'running' | 'paused' | 'complete';
type WalkPose = 'back' | 'front' | 'right' | 'left';
type ActionPose = 'desk' | 'research' | 'door';
type Point = { x: number; y: number };

type Phase = {
  id: string;
  start: number;
  end: number;
  label: string;
  detail: string;
  mode: 'walk' | 'action';
  visual: WalkPose | ActionPose;
  from: Point;
  to: Point;
  route?: Point[];
  papers: number;
};

type WebMcpContext = {
  registerTool: (
    tool: {
      name: string;
      title?: string;
      description: string;
      inputSchema: object;
      annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
      execute: (input: unknown) => unknown;
    },
    options?: { signal?: AbortSignal },
  ) => void | Promise<void>;
};

declare global {
  interface Document {
    readonly modelContext?: WebMcpContext;
  }
}

const DURATION = 30_000;
const DESK = { x: 50, y: 75 };
const DESK_LEFT = { x: 25, y: 69 };
const DESK_RIGHT = { x: 74, y: 69 };
const ARCHIVE = { x: 23, y: 34 };
const LIBRARY = { x: 12, y: 56 };
const NEWS = { x: 70, y: 32 };
const DATA = { x: 76.5, y: 57 };
const DOOR = { x: 49, y: 31 };
const walkPoses: WalkPose[] = ['back', 'right', 'front', 'left'];

const phases: Phase[] = [
  { id: 'brief', start: 0, end: 1_300, label: '建立研究任务', detail: '小企先在工位确认公司名称与研究范围', mode: 'action', visual: 'desk', from: DESK, to: DESK, papers: 0 },
  { id: 'desk-exit', start: 1_300, end: 2_100, label: '离开工位', detail: '小企推开椅子，从桌子左侧起身', mode: 'action', visual: 'desk', from: DESK, to: DESK_LEFT, route: [DESK, { x: 40, y: 73 }, { x: 32, y: 70 }, DESK_LEFT], papers: 0 },
  { id: 'walk-archive', start: 2_100, end: 4_300, label: '前往企业档案区', detail: '从桌外通道步行到主体档案柜', mode: 'walk', visual: 'back', from: DESK_LEFT, to: ARCHIVE, route: [DESK_LEFT, { x: 23, y: 52 }, ARCHIVE], papers: 0 },
  { id: 'archive', start: 4_300, end: 6_100, label: '查阅企业档案', detail: '逐项确认股权、高管与历史变更', mode: 'action', visual: 'research', from: ARCHIVE, to: ARCHIVE, papers: 0 },
  { id: 'walk-library', start: 6_100, end: 7_300, label: '前往窗下图书架', detail: '沿左侧通道走向年报与行业目录', mode: 'walk', visual: 'front', from: ARCHIVE, to: LIBRARY, route: [ARCHIVE, { x: 18, y: 44 }, { x: 14, y: 52 }, LIBRARY], papers: 1 },
  { id: 'library', start: 7_300, end: 9_200, label: '翻阅书籍资料', detail: '取书、翻页、摘录，再把书放回原位', mode: 'action', visual: 'research', from: LIBRARY, to: LIBRARY, papers: 1 },
  { id: 'walk-news', start: 9_200, end: 13_000, label: '前往新闻资料架', detail: '沿空旷通道穿过办公室，不横跨任何工位', mode: 'walk', visual: 'right', from: LIBRARY, to: NEWS, route: [LIBRARY, { x: 18, y: 48 }, { x: 39, y: 42 }, { x: 57, y: 42 }, { x: 66, y: 38 }, NEWS], papers: 2 },
  { id: 'news', start: 13_000, end: 14_600, label: '比对新闻摘要', detail: '圈出公告时间、媒体事件和潜在风险词', mode: 'action', visual: 'research', from: NEWS, to: NEWS, papers: 2 },
  { id: 'walk-data', start: 14_600, end: 15_700, label: '前往数据终端', detail: '从桌外侧接近终端，不穿过显示器和座椅', mode: 'walk', visual: 'front', from: NEWS, to: DATA, route: [NEWS, { x: 72, y: 42 }, { x: 75, y: 50 }, DATA], papers: 3 },
  { id: 'data', start: 15_700, end: 17_200, label: '核验经营数据', detail: '检查收入、利润、行业与市场变化', mode: 'action', visual: 'research', from: DATA, to: DATA, papers: 3 },
  { id: 'knock', start: 17_200, end: 18_000, label: '门外传来敲门声', detail: '一位社会观察员带来了新的舆情线索', mode: 'action', visual: 'research', from: DATA, to: DATA, papers: 4 },
  { id: 'walk-door', start: 18_000, end: 20_300, label: '去开门', detail: '小企转身背对使用者，沿中央通道走向门口', mode: 'walk', visual: 'back', from: DATA, to: DOOR, route: [DATA, { x: 69, y: 48 }, { x: 59, y: 40 }, { x: 53, y: 34 }, DOOR], papers: 4 },
  { id: 'open-door', start: 20_300, end: 21_300, label: '打开办公室门', detail: '抓住原门把手，让门沿原门框打开', mode: 'action', visual: 'door', from: DOOR, to: DOOR, papers: 4 },
  { id: 'talk', start: 21_300, end: 23_100, label: '核对社会舆情', detail: '小企留在门内，与门外访客确认来源和影响', mode: 'action', visual: 'door', from: { x: 48.5, y: 31 }, to: { x: 48.5, y: 31 }, papers: 4 },
  { id: 'close-door', start: 23_100, end: 23_900, label: '结束访谈并关门', detail: '舆情记录已经带回研究室', mode: 'action', visual: 'door', from: DOOR, to: DOOR, papers: 5 },
  { id: 'walk-desk', start: 23_900, end: 26_200, label: '回到工位', detail: '绕过右侧桌角，在桌外停步', mode: 'walk', visual: 'front', from: DOOR, to: DESK_RIGHT, route: [DOOR, { x: 49, y: 43 }, { x: 61, y: 50 }, { x: 72, y: 58 }, DESK_RIGHT], papers: 5 },
  { id: 'desk-sit', start: 26_200, end: 27_200, label: '坐回原来的椅子', detail: '小企从桌侧进入工位并调整坐姿', mode: 'action', visual: 'desk', from: DESK_RIGHT, to: DESK, route: [DESK_RIGHT, { x: 65, y: 73 }, { x: 57, y: 76 }, DESK], papers: 5 },
  { id: 'report', start: 27_200, end: 30_000, label: '撰写研究报告', detail: '在原工位阅读、整理、输入并完成报告', mode: 'action', visual: 'desk', from: DESK, to: DESK, papers: 5 },
];

const sourceMarkers = [
  { title: '企业资料', caption: '主体 · 股权 · 高管', icon: Building2, readyAt: 6_100, activeIds: ['walk-archive', 'archive'], className: 'source-enterprise' },
  { title: '图书年报', caption: '年报 · 行业 · 沿革', icon: BookOpen, readyAt: 9_200, activeIds: ['walk-library', 'library'], className: 'source-library' },
  { title: '新闻摘要', caption: '公告 · 媒体 · 事件', icon: Newspaper, readyAt: 14_600, activeIds: ['walk-news', 'news'], className: 'source-news' },
  { title: '经营数据', caption: '财务 · 行业 · 市场', icon: Database, readyAt: 17_200, activeIds: ['walk-data', 'data'], className: 'source-data' },
  { title: '社会舆情', caption: '访谈 · 口碑 · 反馈', icon: MessageCircle, readyAt: 23_900, activeIds: ['knock', 'walk-door', 'open-door', 'talk', 'close-door'], className: 'source-social' },
];

const settledPapers = [
  { level: 1, x: 42.5, y: 74.2, rotate: -7, frame: 0 },
  { level: 1, x: 57.8, y: 74.8, rotate: 8, frame: 1 },
  { level: 2, x: 62.3, y: 83.2, rotate: -13, frame: 2 },
  { level: 2, x: 36.7, y: 82.5, rotate: 15, frame: 3 },
  { level: 3, x: 68.7, y: 90.2, rotate: 9, frame: 0 },
  { level: 3, x: 31.8, y: 90.8, rotate: -18, frame: 1 },
  { level: 4, x: 58.2, y: 91.5, rotate: 17, frame: 2 },
  { level: 4, x: 43.3, y: 94.1, rotate: -8, frame: 3 },
  { level: 5, x: 64.4, y: 95.2, rotate: -4, frame: 0 },
  { level: 5, x: 35.1, y: 95.4, rotate: 11, frame: 2 },
];

const breezeItems = [
  { kind: 'leaf', frame: 0, x: 4.5, y: 28, delay: 0 },
  { kind: 'leaf', frame: 1, x: 7.5, y: 37, delay: 420 },
  { kind: 'leaf', frame: 2, x: 10, y: 44, delay: 830 },
  { kind: 'paper', frame: 1, x: 17, y: 54, delay: 160 },
  { kind: 'paper', frame: 3, x: 24, y: 65, delay: 760 },
];

function phaseAt(elapsed: number) {
  return phases.find((phase) => elapsed >= phase.start && elapsed < phase.end) ?? phases.at(-1)!;
}

function easeInOut(value: number) {
  const clamped = Math.max(0, Math.min(1, value));
  return clamped * clamped * (3 - 2 * clamped);
}

function walkStateFor(phase: Phase, elapsed: number) {
  if (!phase.route) return { position: phase.to, facing: 'back' as WalkPose };
  const points = phase.route;
  const segments = points.slice(0, -1).map((point, index) => {
    const next = points[index + 1];
    const screenDx = (next.x - point.x) * 1.776833;
    const dy = next.y - point.y;
    return { from: point, to: next, length: Math.hypot(screenDx, dy), screenDx, dy };
  });
  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0);
  const routeProgress = easeInOut((elapsed - phase.start) / (phase.end - phase.start));
  let remaining = totalLength * routeProgress;
  const segment = segments.find((candidate) => {
    if (remaining <= candidate.length) return true;
    remaining -= candidate.length;
    return false;
  }) ?? segments.at(-1)!;
  const segmentProgress = segment.length ? Math.min(1, remaining / segment.length) : 1;
  const facing: WalkPose = Math.abs(segment.screenDx) > Math.abs(segment.dy)
    ? segment.screenDx >= 0 ? 'right' : 'left'
    : segment.dy >= 0 ? 'front' : 'back';
  return {
    position: {
      x: segment.from.x + (segment.to.x - segment.from.x) * segmentProgress,
      y: segment.from.y + (segment.to.y - segment.from.y) * segmentProgress,
    },
    facing,
  };
}

function doorProgressFor(elapsed: number, status: ResearchStatus) {
  if (status === 'idle' || status === 'complete') return 0;
  if (elapsed < 20_300) return 0;
  if (elapsed < 21_300) return easeInOut((elapsed - 20_300) / 1_000);
  if (elapsed < 23_100) return 1;
  if (elapsed < 23_900) return 1 - easeInOut((elapsed - 23_100) / 800);
  return 0;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [status, setStatus] = useState<ResearchStatus>('idle');
  const [elapsed, setElapsed] = useState(0);
  const elapsedRef = useRef(0);

  const beginResearch = (nextQuery: string) => {
    const normalized = nextQuery.trim();
    if (!normalized) return false;
    setQuery(normalized);
    setActiveQuery(normalized);
    elapsedRef.current = 0;
    setElapsed(0);
    setStatus('running');
    return true;
  };

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(context.registerTool({
        name: 'start_company_research',
        title: '开始企业研究',
        description: '输入公司名称，关闭首页输入框，并启动小企在办公室内约 30 秒的连续资料收集与报告撰写动画。',
        inputSchema: {
          type: 'object',
          properties: { company: { type: 'string', minLength: 1, maxLength: 80 } },
          required: ['company'],
          additionalProperties: false,
        },
        annotations: { readOnlyHint: false, untrustedContentHint: false },
        execute(input) {
          if (!input || typeof input !== 'object') throw new Error('输入必须是对象');
          const company = (input as { company?: unknown }).company;
          if (typeof company !== 'string' || !company.trim() || company.trim().length > 80) {
            throw new Error('company 必须是 1 至 80 个字符的公司名称');
          }
          beginResearch(company);
          return { status: 'running', company: company.trim(), durationSeconds: 30 };
        },
      }, { signal: lifecycle.signal })).catch(() => undefined);
    } catch {
      // The visible search form remains available when WebMCP is unsupported.
    }
    return () => lifecycle.abort();
  }, []);

  useEffect(() => {
    if (status !== 'running') return;
    let animationFrame = 0;
    let previous = performance.now();
    const tick = (now: number) => {
      const delta = Math.min(42, now - previous);
      previous = now;
      const nextElapsed = Math.min(DURATION, elapsedRef.current + delta);
      elapsedRef.current = nextElapsed;
      setElapsed(nextElapsed);
      if (nextElapsed >= DURATION) {
        setStatus('complete');
        return;
      }
      animationFrame = requestAnimationFrame(tick);
    };
    animationFrame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationFrame);
  }, [status]);

  const phase = status === 'idle'
    ? { ...phases[0], id: 'idle', label: '等待查询', detail: '输入公司名称或研究问题，让小企开始工作' }
    : status === 'complete'
      ? { ...phases.at(-1)!, id: 'complete', label: '研究报告已生成', detail: '公开资料、经营信号与社会舆情已经整理完成' }
      : phaseAt(elapsed);
  const walkState = walkStateFor(phase, elapsed);
  const actorPosition = status === 'idle' || status === 'complete' ? DESK : walkState.position;
  const actorFacing = phase.mode === 'walk' ? walkState.facing : 'back';
  const progress = status === 'idle' ? 0 : Math.min(100, (elapsed / DURATION) * 100);
  const doorProgress = doorProgressFor(elapsed, status);
  const showGuest = status !== 'idle' && elapsed >= 20_950 && elapsed < 23_450;
  const knocking = status !== 'idle' && elapsed >= 17_200 && elapsed < 20_000;
  const paperLevel = status === 'complete' ? 5 : phase.papers;
  const actorStyle = { '--actor-x': `${actorPosition.x}%`, '--actor-y': `${actorPosition.y}%` } as CSSProperties;
  const doorStyle = { '--door-progress': doorProgress } as CSSProperties;

  const visiblePaperCount = settledPapers.filter((paper) => paper.level <= paperLevel).length;

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    beginResearch(query);
  };

  const restart = () => {
    if (!activeQuery) return;
    elapsedRef.current = 0;
    setElapsed(0);
    setStatus('running');
  };

  const resetSearch = () => {
    elapsedRef.current = 0;
    setElapsed(0);
    setStatus('idle');
  };

  const togglePause = () => {
    setStatus((current) => current === 'running' ? 'paused' : current === 'paused' ? 'running' : current);
  };

  return (
    <main className="office-page">
      <section
        className={`office-stage status-${status} breeze-active`}
        aria-label="小企企业研究室"
        style={doorStyle}
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

        {breezeItems.map((item, index) => (
          <span
            aria-hidden="true"
            className={`motion-sprite breeze-sprite ${item.kind} frame-${item.frame}`}
            key={`${item.kind}-${index}`}
            style={{ '--item-x': `${item.x}%`, '--item-y': `${item.y}%`, '--item-delay': `${item.delay}ms` } as CSSProperties}
          />
        ))}

        {settledPapers.map((paper, index) => (
          <span
            aria-hidden="true"
            className={`motion-sprite evidence-paper frame-${paper.frame} ${paper.level <= paperLevel ? 'visible' : ''}`}
            key={`paper-${index}`}
            style={{ '--paper-x': `${paper.x}%`, '--paper-y': `${paper.y}%`, '--paper-rotate': `${paper.rotate}deg`, '--paper-delay': `${(index % 2) * 90}ms` } as CSSProperties}
          />
        ))}

        <ol className={`source-markers ${status === 'idle' ? 'idle' : ''}`} aria-label="企业资料来源">
          {sourceMarkers.map((source) => {
            const done = status === 'complete' || (status !== 'idle' && elapsed >= source.readyAt);
            const active = status !== 'idle' && status !== 'complete' && source.activeIds.includes(phase.id);
            const Icon = source.icon;
            return (
              <li
                className={`source-marker ${source.className} ${active ? 'active' : ''} ${done ? 'done' : ''}`}
                key={source.title}
                aria-current={active ? 'step' : undefined}
              >
                <span><Icon aria-hidden="true" /></span>
                <div><strong>{source.title}</strong><small>{done ? '资料已收集' : active ? '小企正在查找' : source.caption}</small></div>
                {done ? <Check aria-hidden="true" /> : <i aria-hidden="true" />}
              </li>
            );
          })}
        </ol>

        {showGuest && (
          <figure className="visitor-goose" aria-label="站在门外提供社会舆情线索的访客鹅">
            <span className="visitor-sprite" aria-hidden="true" />
          </figure>
        )}

        {knocking && (
          <div className="knock-effect" aria-label="门外传来敲门声">
            <span /><span /><span /><strong>咚 · 咚</strong>
          </div>
        )}

        <figure
          className={`xiaoqi-actor mode-${phase.mode} visual-${phase.visual}`}
          style={actorStyle}
          aria-label={`穿西装的小企正在${phase.label}`}
        >
          {walkPoses.map((pose) => (
            <span className={`walk-cycle walk-${pose} ${phase.mode === 'walk' && actorFacing === pose ? 'active' : ''}`} key={pose} aria-hidden="true" />
          ))}
          <span className={`action-cycle action-${phase.mode === 'action' ? phase.visual : 'desk'} ${phase.mode === 'action' ? 'active' : ''}`} aria-hidden="true" />
        </figure>

        <div className="desk-foreground" aria-hidden="true" />

        <div className="scene-brand" aria-label="企er 小企研究室">
          <span>企</span>
          <div><strong>企er</strong><small>小企研究室</small></div>
        </div>

        <div className={`query-layer ${status === 'idle' ? 'visible' : 'hidden'}`} aria-hidden={status !== 'idle'}>
          <form className="home-query" onSubmit={submit}>
            <span className="query-kicker"><Sparkles /> 查企业</span>
            <h1>想先查哪家公司？</h1>
            <label className="sr-only" htmlFor="company-query">输入公司名称或你想了解的问题</label>
            <div className="prompt-bar">
              <Search aria-hidden="true" />
              <Input
                id="company-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="输入公司名称或你想了解的问题"
                autoComplete="off"
                disabled={status !== 'idle'}
              />
              <Button type="submit" disabled={!query.trim() || status !== 'idle'}>
                开始查询 <ArrowRight data-icon="inline-end" />
              </Button>
            </div>
            <p>小企会在办公室内查阅档案、书籍、新闻、数据与社会舆情。</p>
          </form>
        </div>

        {status !== 'idle' && (
          <>
            <div className="research-hud">
              <div className="research-subject"><i /> <span>{activeQuery}</span></div>
              <div className="research-controls">
                <button type="button" onClick={togglePause} disabled={status === 'complete'} aria-label={status === 'paused' ? '继续动画' : '暂停动画'}>
                  {status === 'paused' ? <CirclePlay /> : <CirclePause />}
                </button>
                <button type="button" onClick={restart} disabled={!activeQuery} aria-label="重新播放"><RotateCcw /></button>
              </div>
            </div>

            <div className="phase-caption">
              <div className="phase-copy" aria-live="polite" aria-atomic="true"><strong>{phase.label}</strong><small>{phase.detail}</small></div>
              <div className="phase-meta"><span>{visiblePaperCount} 份资料</span><b aria-hidden="true">{Math.round(progress)}%</b></div>
              <progress
                className="progress-track"
                aria-label="企业研究进度"
                max={100}
                value={progress}
              />
            </div>
          </>
        )}

        {status === 'complete' && (
          <output className="complete-card">
            <CheckCircle2 />
            <div><strong>{activeQuery} 研究报告已生成</strong><small>所有证据已经回到工位并完成整理</small></div>
            <button type="button" onClick={resetSearch}>查另一家公司</button>
          </output>
        )}
      </section>
    </main>
  );
}
