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
import { DURATION, phases, phaseAt, phaseProgress, motionAt, doorAt, ease } from './office-motion';

type ResearchStatus = 'idle' | 'running' | 'paused' | 'complete';
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

export default function Home() {
  const [query, setQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [status, setStatus] = useState<ResearchStatus>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [inspector, setInspector] = useState(false);
  const [speed, setSpeed] = useState(1);
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
        description: '输入公司名称，关闭首页输入框，并启动小企在办公室内约 37 秒的连续资料收集与报告撰写动画。',
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
          return { status: 'running', company: company.trim(), durationSeconds: DURATION / 1000 };
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
      const delta = Math.min(100, now - previous) * speed;
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
  }, [status, speed]);

  const phase = status === 'idle'
    ? { ...phases[0], id: 'idle', label: '等待查询', detail: '输入公司名称或研究问题，让小企开始工作' }
    : status === 'complete'
      ? { ...phases.at(-1)!, id: 'complete', label: '研究报告已生成', detail: '公开资料、经营信号与社会舆情已经整理完成' }
      : phaseAt(elapsed);
  const motion = motionAt(phase, elapsed);
  const localProgress = phaseProgress(phase, elapsed);
  const seated = phase.visual === 'desk' ? 1 : phase.visual === 'stand' ? 1-ease(localProgress) : phase.visual === 'sit' ? ease(localProgress) : 0;
  const isWalking = phase.mode === 'walk';
  const frame = motion.frame;
  const progress = status === 'idle' ? 0 : Math.min(100, elapsed / DURATION * 100);
  const doorProgress = status === 'idle' ? 0 : doorAt(elapsed);
  const showGuest = doorProgress > .12;
  const knocking = phase.id === 'knock' || phase.id === 'walk-door';
  const paperLevel = status === 'complete' ? 5 : phase.papers;
  const actionFrame = phase.visual === 'research' ? [1,2,2,1][Math.floor((elapsed-phase.start)/450)%4] : phase.visual === 'door' ? Math.min(1,Math.floor(localProgress*2)) : phase.visual === 'talk' ? 2 : phase.visual === 'desk' ? Math.floor(Math.max(0,elapsed-phase.start)/600)%4 : 1;
  const research = phase.visual === 'research';
  const actorStyle = { '--actor-x': motion.position.x+'%', '--actor-y': motion.position.y+'%', '--walk-frame': frame*100/3+'%', '--seated': seated, '--seated-mix': seated > .85 ? (seated-.85)/.15 : 0, '--action-frame': actionFrame*100/3+'%', '--gesture': Math.sin((elapsed-phase.start)/220)*1.5+'deg' } as CSSProperties;
  const doorStyle = { '--door-progress': doorProgress } as CSSProperties;
  const seek = (time:number) => { elapsedRef.current=Math.max(0,Math.min(DURATION,time)); setElapsed(elapsedRef.current); setStatus('paused'); };

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
            const readyAt = phases.find(p => p.id === source.activeIds.at(-1))!.end;
            const done = status === 'complete' || (status !== 'idle' && elapsed >= readyAt);
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
          <figure className="visitor-goose" style={{opacity:Math.min(1,doorProgress*3)}} aria-label="站在门外提供社会舆情线索的访客鹅">
            <span className="visitor-sprite" aria-hidden="true" />
          </figure>
        )}

        {knocking && (
          <div className="knock-effect" aria-label="门外传来敲门声">
            <span /><span /><span /><strong>咚 · 咚</strong>
          </div>
        )}

        <figure
          className={`xiaoqi-actor ${isWalking ? 'walking' : 'stationary'} facing-${motion.facing} action-${phase.visual}`}
          style={actorStyle}
          data-phase={phase.id}
          data-distance={motion.distance.toFixed(2)}
          aria-label={`穿西装的小企正在${phase.label}`}
        >
          <span className="seated-body" aria-hidden="true" />
          <span className="standing-body" aria-hidden="true">
            {isWalking ? (['back','front','left','right'] as const).map(direction => <span key={direction} className={`distance-walk walk-${direction}`} style={{opacity:direction === motion.facing ? 1 : 0}} />) : <>
              <span className={`planted-feet ${research ? 'research-feet' : ''}`} />
              <span className={`gesture-body ${research ? 'research-body' : ''}`} />
            </>}
          </span>
        </figure>
        <div className="chair-foreground" style={{opacity:seated > .85 ? 1 : 0}} aria-hidden="true" />

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
                <button type="button" onClick={() => setInspector(v=>!v)} aria-label="动作检查">⌕</button>
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

        {inspector && status !== 'idle' && <div className="motion-inspector">
          <label>动作检查 <select aria-label="播放速度" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>正常速度</option><option value={.25}>四分之一速度</option></select></label>
          <label>检查时间 <input aria-label="检查时间（秒）" type="number" min={0} max={DURATION/1000} step={.04} value={Number((elapsed/1000).toFixed(2))} onChange={e=>seek(Number(e.target.value)*1000)} /></label>
          <input aria-label="动画时间" type="range" min={0} max={DURATION} step={40} value={elapsed} onChange={e=>seek(Number(e.target.value))} />
          <button onClick={()=>seek(elapsed-40)} type="button">上一帧</button><span>{(elapsed/1000).toFixed(2)} 秒 · {phase.label}</span><button onClick={()=>seek(elapsed+40)} type="button">下一帧</button>
        </div>}
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
