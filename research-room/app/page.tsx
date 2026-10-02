'use client';

import type { CSSProperties, FormEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import {
  Archive,
  BookOpen,
  Building2,
  Check,
  CirclePause,
  CirclePlay,
  Clock3,
  Database,
  FileCheck2,
  FileStack,
  Keyboard,
  MessageCircle,
  Newspaper,
  RefreshCcw,
  Search,
  Send,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';

type ResearchStatus = 'idle' | 'running' | 'paused' | 'complete';
type WalkFacing = 'right' | 'left' | 'back' | 'front';
type ActionPose =
  | 'magnify'
  | 'redpen'
  | 'readbook'
  | 'organize'
  | 'typeback'
  | 'typeside'
  | 'sitdesk'
  | 'lookpapers'
  | 'maintalk'
  | 'close';
type GuestPose = 'guestknock' | 'guesttalk';

type Phase = {
  id: string;
  start: number;
  end: number;
  label: string;
  detail: string;
  mode: 'walk' | 'action';
  visual: WalkFacing | ActionPose;
  x: number;
  y: number;
  step: number;
  papers: number;
  guest?: GuestPose;
  knock?: boolean;
};

type WebMcpContext = {
  registerTool: (
    tool: {
      name: string;
      title?: string;
      description: string;
      inputSchema: object;
      annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
      execute: (input: unknown) => unknown | Promise<unknown>;
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

const phases: Phase[] = [
  { id: 'to-company', start: 0, end: 1_800, label: '前往企业档案区', detail: '先核对公司身份与基础档案', mode: 'walk', visual: 'back', x: 25, y: 34, step: 0, papers: 0 },
  { id: 'company', start: 1_800, end: 3_200, label: '核验工商档案', detail: '放大镜检查登记、股权与高管线索', mode: 'action', visual: 'magnify', x: 25, y: 34, step: 0, papers: 0 },
  { id: 'company-return', start: 3_200, end: 4_600, label: '带回企业档案', detail: '第一份资料正在送回工位', mode: 'walk', visual: 'front', x: 50, y: 74, step: 0, papers: 0 },
  { id: 'to-library', start: 4_600, end: 6_000, label: '前往公司图书架', detail: '继续翻阅年报与行业目录', mode: 'walk', visual: 'left', x: 13, y: 60, step: 1, papers: 1 },
  { id: 'library', start: 6_000, end: 7_600, label: '翻阅参考书籍', detail: '查找业务沿革与行业背景', mode: 'action', visual: 'readbook', x: 13, y: 60, step: 1, papers: 1 },
  { id: 'library-return', start: 7_600, end: 9_000, label: '带回书籍线索', detail: '第二份资料正在送回工位', mode: 'walk', visual: 'right', x: 50, y: 74, step: 1, papers: 1 },
  { id: 'to-news', start: 9_000, end: 10_400, label: '前往新闻资料区', detail: '查找公告、报道与事件记录', mode: 'walk', visual: 'back', x: 77, y: 33, step: 2, papers: 2 },
  { id: 'news', start: 10_400, end: 11_900, label: '圈画关键报道', detail: '用红笔标出事件、时间与风险词', mode: 'action', visual: 'redpen', x: 77, y: 33, step: 2, papers: 2 },
  { id: 'news-return', start: 11_900, end: 13_300, label: '带回新闻资料', detail: '第三份资料正在送回工位', mode: 'walk', visual: 'front', x: 50, y: 74, step: 2, papers: 2 },
  { id: 'to-data', start: 13_300, end: 14_700, label: '前往数据终端', detail: '准备交叉核验经营数据', mode: 'walk', visual: 'right', x: 83, y: 66, step: 3, papers: 3 },
  { id: 'data', start: 14_700, end: 16_200, label: '核验经营信号', detail: '检查收入、利润、行业与市场变化', mode: 'action', visual: 'magnify', x: 83, y: 66, step: 3, papers: 3 },
  { id: 'data-return', start: 16_200, end: 17_600, label: '带回数据证据', detail: '第四份资料正在送回工位', mode: 'walk', visual: 'left', x: 50, y: 74, step: 3, papers: 3 },
  { id: 'knock', start: 17_600, end: 18_600, label: '门外传来敲门声', detail: '一位社会观察员带来了舆情线索', mode: 'action', visual: 'lookpapers', x: 50, y: 74, step: 4, papers: 4, guest: 'guestknock', knock: true },
  { id: 'to-door', start: 18_600, end: 20_100, label: '前去开门', detail: '小企放下资料，走向门口', mode: 'walk', visual: 'back', x: 46, y: 32, step: 4, papers: 4, guest: 'guestknock', knock: true },
  { id: 'conversation', start: 20_100, end: 22_000, label: '核对社会舆情', detail: '两只鹅正在确认来源与事件影响', mode: 'action', visual: 'maintalk', x: 45, y: 34, step: 4, papers: 4, guest: 'guesttalk' },
  { id: 'close-door', start: 22_000, end: 22_800, label: '结束访谈并关门', detail: '舆情线索已经记录', mode: 'action', visual: 'close', x: 49, y: 32, step: 4, papers: 4 },
  { id: 'social-return', start: 22_800, end: 24_400, label: '带回舆情记录', detail: '第五份资料正在送回工位', mode: 'walk', visual: 'front', x: 50, y: 74, step: 4, papers: 4 },
  { id: 'organize', start: 24_400, end: 25_800, label: '整理全部资料', detail: '用翅膀把散落证据按主题归档', mode: 'action', visual: 'organize', x: 50, y: 74, step: 5, papers: 5 },
  { id: 'type-back', start: 25_800, end: 27_300, label: '坐在工位撰写', detail: '小企背对使用者开始输入报告', mode: 'action', visual: 'typeback', x: 50, y: 74, step: 6, papers: 5 },
  { id: 'sit-desk', start: 27_300, end: 28_200, label: '坐上桌沿复核', detail: '重新查看一份关键证据', mode: 'action', visual: 'sitdesk', x: 50, y: 74, step: 6, papers: 5 },
  { id: 'look-papers', start: 28_200, end: 29_000, label: '查看旁边资料', detail: '核对纸面记录与屏幕结论', mode: 'action', visual: 'lookpapers', x: 50, y: 74, step: 6, papers: 5 },
  { id: 'type-side', start: 29_000, end: 30_000, label: '完成研究报告', detail: '补齐结论、依据与风险提示', mode: 'action', visual: 'typeside', x: 50, y: 74, step: 6, papers: 5 },
];

const idlePhase: Phase = { id: 'idle', start: 0, end: 0, label: '等待研究任务', detail: '输入公司名称，让小企出发', mode: 'action', visual: 'lookpapers', x: 50, y: 74, step: -1, papers: 0 };
const completePhase: Phase = { ...idlePhase, id: 'complete', label: '报告已经生成', detail: '全部证据与风险提示均已整理', visual: 'typeside', step: 6, papers: 5 };

const steps = [
  { title: '企业档案', caption: '登记 · 股权 · 高管', icon: Building2, doneAt: 4_600 },
  { title: '图书资料', caption: '年报 · 目录 · 沿革', icon: BookOpen, doneAt: 9_000 },
  { title: '新闻资料', caption: '公告 · 媒体 · 事件', icon: Newspaper, doneAt: 13_300 },
  { title: '经营数据', caption: '财务 · 行业 · 市场', icon: Database, doneAt: 17_600 },
  { title: '社会舆情', caption: '访谈 · 口碑 · 反馈', icon: MessageCircle, doneAt: 24_400 },
  { title: '资料归纳', caption: '整理 · 复核 · 串联', icon: FileStack, doneAt: 25_800 },
  { title: '研究报告', caption: '结论 · 依据 · 风险', icon: FileCheck2, doneAt: 30_000 },
];

const logs = [
  { at: 200, time: '00:00', text: '任务建立，小企从工位出发。' },
  { at: 1_900, time: '00:02', text: '开始核验主体、股权与高管线索。' },
  { at: 4_600, time: '00:05', text: '第一份企业档案已放回桌面。' },
  { at: 6_100, time: '00:06', text: '翻阅年报与行业参考书籍。' },
  { at: 9_000, time: '00:09', text: '第二份书籍线索已放回桌面。' },
  { at: 10_500, time: '00:11', text: '红笔标出关键报道与事件。' },
  { at: 13_300, time: '00:13', text: '第三份新闻资料已放回桌面。' },
  { at: 14_800, time: '00:15', text: '数据终端开始交叉核验经营指标。' },
  { at: 17_600, time: '00:18', text: '第四份数据证据已放回桌面。' },
  { at: 18_000, time: '00:18', text: '门外传来敲门声，社会观察员到访。' },
  { at: 20_200, time: '00:20', text: '开始核对舆情来源与事件影响。' },
  { at: 24_400, time: '00:24', text: '第五份舆情记录已带回工位。' },
  { at: 25_800, time: '00:26', text: '所有纸面证据完成主题归档。' },
  { at: 29_000, time: '00:29', text: '结论与风险提示进入最终校对。' },
  { at: 29_900, time: '00:30', text: '企业研究报告生成完毕。' },
];

const sourceCards = [
  { title: '企业档案', detail: '12 条主体线索', readyAt: 4_600, icon: Building2 },
  { title: '图书与年报', detail: '8 本参考资料', readyAt: 9_000, icon: BookOpen },
  { title: '新闻与公告', detail: '27 篇公开资料', readyAt: 13_300, icon: Newspaper },
  { title: '经营指标', detail: '18 项交叉校验', readyAt: 17_600, icon: Database },
  { title: '社会舆情', detail: '6 条访谈线索', readyAt: 24_400, icon: MessageCircle },
];

const actionPoses: ActionPose[] = ['magnify', 'redpen', 'readbook', 'organize', 'typeback', 'typeside', 'sitdesk', 'lookpapers', 'maintalk', 'close'];
const guestPoses: GuestPose[] = ['guestknock', 'guesttalk'];
const paperSpots = [
  { level: 1, left: 52, top: 69, rotate: -8 }, { level: 1, left: 57, top: 72, rotate: 5 }, { level: 1, left: 47, top: 72, rotate: -2 },
  { level: 2, left: 60, top: 77, rotate: 16 }, { level: 2, left: 42, top: 79, rotate: -13 }, { level: 2, left: 55, top: 82, rotate: 7 },
  { level: 3, left: 38, top: 85, rotate: 18 }, { level: 3, left: 64, top: 85, rotate: -9 }, { level: 3, left: 48, top: 88, rotate: -17 },
  { level: 4, left: 58, top: 89, rotate: 12 }, { level: 4, left: 44, top: 93, rotate: 6 }, { level: 4, left: 68, top: 91, rotate: -15 },
  { level: 5, left: 34, top: 91, rotate: -5 }, { level: 5, left: 53, top: 95, rotate: 19 }, { level: 5, left: 62, top: 95, rotate: -3 },
];

function phaseFor(elapsed: number, status: ResearchStatus) {
  if (status === 'idle') return idlePhase;
  if (status === 'complete') return completePhase;
  return phases.find((phase) => elapsed >= phase.start && elapsed < phase.end) ?? phases.at(-1)!;
}

export default function Home() {
  const [companyName, setCompanyName] = useState('宁德时代');
  const [activeCompany, setActiveCompany] = useState('宁德时代');
  const [status, setStatus] = useState<ResearchStatus>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [speed, setSpeed] = useState<1 | 2>(1);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(context.registerTool({
        name: 'start_company_research',
        title: '开始企业研究',
        description: '输入公司名称，启动小企约 30 秒的可视化资料收集、访谈与报告生成流程。',
        inputSchema: { type: 'object', properties: { company: { type: 'string', minLength: 1, maxLength: 80 } }, required: ['company'], additionalProperties: false },
        annotations: { readOnlyHint: false, untrustedContentHint: false },
        execute(input) {
          if (!input || typeof input !== 'object') throw new Error('输入必须是对象');
          const company = (input as { company?: unknown }).company;
          if (typeof company !== 'string' || !company.trim() || company.trim().length > 80) throw new Error('company 必须是 1 至 80 个字符的公司名称');
          const normalized = company.trim();
          setCompanyName(normalized);
          setActiveCompany(normalized);
          setElapsed(0);
          setStatus('running');
          return { status: 'running', company: normalized, durationSeconds: 30 };
        },
      }, { signal: lifecycle.signal })).catch(() => undefined);
    } catch {
      // The visible form remains available in browsers without WebMCP.
    }
    return () => lifecycle.abort();
  }, []);

  useEffect(() => {
    if (status !== 'running') return;
    const timer = window.setInterval(() => setElapsed((current) => Math.min(DURATION, current + 100 * speed)), 100);
    return () => window.clearInterval(timer);
  }, [speed, status]);

  useEffect(() => {
    if (elapsed >= DURATION && status === 'running') setStatus('complete');
  }, [elapsed, status]);

  const currentPhase = phaseFor(elapsed, status);
  const progress = status === 'idle' ? 0 : Math.min(100, (elapsed / DURATION) * 100);
  const visibleLogs = useMemo(() => logs.filter((entry) => entry.at <= elapsed), [elapsed]);
  const secondsLeft = Math.max(0, Math.ceil((DURATION - elapsed) / 1000));
  const moveDuration = Math.max(320, currentPhase.end - currentPhase.start);

  const startResearch = (event?: FormEvent) => {
    event?.preventDefault();
    const nextCompany = companyName.trim();
    if (!nextCompany) return;
    setActiveCompany(nextCompany);
    setElapsed(0);
    setStatus('running');
  };

  const restart = () => { setElapsed(0); setStatus('running'); };
  const togglePause = () => setStatus((current) => current === 'running' ? 'paused' : current === 'paused' ? 'running' : current);

  return (
    <main className="research-app">
      <header className="app-header">
        <a className="brand" href="#top" aria-label="企er 企业研究首页"><span className="brand-pixel">企</span><span><strong>企er</strong><small>企业研究工作台</small></span></a>
        <div className="header-badges"><span className="demo-pill"><i /> 交互演示</span><span className="duration-pill"><Clock3 /> 约 30 秒</span></div>
      </header>

      <section className="query-shell" id="top">
        <div><span className="query-kicker"><Sparkles /> 小企研究员</span><h1>输入一家公司，看小企如何把线索带回工位。</h1></div>
        <form className="query-form" onSubmit={startResearch}>
          <label htmlFor="company-search">查询公司</label>
          <div className="query-input-wrap"><Search aria-hidden="true" /><Input id="company-search" value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="例如：宁德时代" disabled={status === 'running' || status === 'paused'} /></div>
          <Button className="start-button" size="lg" type="submit"><Send data-icon="inline-start" />{status === 'idle' ? '开始调研' : '重新调研'}</Button>
        </form>
      </section>

      <section className="dashboard-grid" aria-label="小企企业研究工作台">
        <aside className="panel task-panel">
          <div className="panel-title"><span><Archive /> 任务执行流</span><small>{Math.round(progress)}%</small></div>
          <ol className="task-list">
            {steps.map((step, index) => {
              const done = elapsed >= step.doneAt || status === 'complete';
              const active = currentPhase.step === index && !done && status !== 'idle';
              const Icon = step.icon;
              return <li className={`${done ? 'done' : ''} ${active ? 'active' : ''}`} key={step.title}><span className="task-icon">{done ? <Check /> : <Icon />}</span><span><strong>{step.title}</strong><small>{step.caption}</small></span><i>{done ? '完成' : active ? '进行中' : '等待'}</i></li>;
            })}
          </ol>
          <div className="task-summary"><span>当前任务</span><strong>{activeCompany} · 企业深度研究</strong><small>公开资料演示 · 不构成投资建议</small></div>
        </aside>

        <section className="panel studio-panel" aria-labelledby="studio-title">
          <div className="studio-head"><div><span className="panel-kicker">LIVE RESEARCH</span><h2 id="studio-title">小企研究室</h2></div><div className={`live-status ${status}`}><i />{status === 'idle' && '等待任务'}{status === 'running' && '执行中'}{status === 'paused' && '已暂停'}{status === 'complete' && '报告完成'}</div></div>

          <div className={`research-stage ${status === 'paused' ? 'stage-paused' : ''}`} aria-live="polite">
            <Image className="room-art" src="/research-room-v2.png" alt="像素风企业研究室，包含企业档案、图书架、新闻资料、数据终端和小企工位" fill priority sizes="(max-width: 1100px) 100vw, 64vw" />
            <div className="stage-vignette" aria-hidden="true" />
            <span className="station-tag station-company"><Building2 /> 企业档案</span>
            <span className="station-tag station-library"><BookOpen /> 图书资料</span>
            <span className="station-tag station-news"><Newspaper /> 新闻资料</span>
            <span className="station-tag station-social"><MessageCircle /> 社会舆情</span>
            <span className="station-tag station-data"><Database /> 数据终端</span>
            <span className="station-tag station-desk"><Keyboard /> 小企工位</span>

            {paperSpots.map((paper, index) => <span className={`loose-paper ${currentPhase.papers >= paper.level ? 'visible' : ''}`} key={index} style={{ '--paper-left': `${paper.left}%`, '--paper-top': `${paper.top}%`, '--paper-rotate': `${paper.rotate}deg`, '--paper-delay': `${(index % 3) * 70}ms` } as CSSProperties}><i /><b /></span>)}

            {currentPhase.guest && (
              <div className="guest-character" role="img" aria-label="前来提供社会舆情线索的访客鹅">
                {guestPoses.map((pose) => <span aria-hidden="true" className={`action-sprite action-${pose} ${currentPhase.guest === pose ? 'active' : ''}`} key={pose} />)}
              </div>
            )}

            {currentPhase.knock && <div className="knock-effect" aria-label="敲门声"><span /><span /><span /><strong>咚 · 咚</strong></div>}

            <div className="goose-character" style={{ '--goose-x': `${currentPhase.x}%`, '--goose-y': `${currentPhase.y}%`, '--move-duration': `${moveDuration}ms` } as CSSProperties} role="img" aria-label={`穿西装的小企正在${currentPhase.label}`}>
              <span className="action-bubble"><strong>{currentPhase.label}</strong><small>{currentPhase.detail}</small></span>
              <span aria-hidden="true" className={`walk-sprite walk-${currentPhase.mode === 'walk' ? currentPhase.visual : 'right'} ${currentPhase.mode === 'walk' ? 'active' : ''}`} />
              {actionPoses.map((pose) => <span aria-hidden="true" className={`action-sprite action-${pose} ${currentPhase.mode === 'action' && currentPhase.visual === pose ? 'active' : ''}`} key={pose} />)}
            </div>

            {status === 'complete' && <div className="report-toast"><FileCheck2 /><span><strong>{activeCompany} 研究报告已生成</strong><small>五类证据、结论与风险提示均已整理</small></span></div>}
          </div>

          <div className="studio-progress">
            <Progress value={progress} className="research-progress"><ProgressLabel>{currentPhase.label}</ProgressLabel><ProgressValue>{Math.round(progress)}%</ProgressValue></Progress>
            <div className="studio-controls"><span className="time-left">{status === 'complete' ? '完成' : `${secondsLeft}s`}</span><div className="speed-switch" aria-label="播放速度">{[1, 2].map((option) => <button aria-pressed={speed === option} className={speed === option ? 'selected' : ''} key={option} onClick={() => setSpeed(option as 1 | 2)} type="button">{option}×</button>)}</div><Button className="icon-control" variant="outline" size="icon" onClick={togglePause} disabled={status === 'idle' || status === 'complete'} aria-label={status === 'paused' ? '继续研究' : '暂停研究'}>{status === 'paused' ? <CirclePlay /> : <CirclePause />}</Button><Button className="icon-control" variant="outline" size="icon" onClick={restart} aria-label="重新播放"><RefreshCcw /></Button></div>
          </div>
        </section>

        <aside className="right-column">
          <section className="panel evidence-panel">
            <div className="panel-title"><span><Search /> 已收集证据</span><small>{sourceCards.filter((source) => elapsed >= source.readyAt).length}/5</small></div>
            <div className="source-list">{sourceCards.map((source) => { const ready = elapsed >= source.readyAt || status === 'complete'; const Icon = source.icon; return <article className={ready ? 'ready' : ''} key={source.title}><span><Icon /></span><div><strong>{source.title}</strong><small>{ready ? source.detail : '等待小企带回'}</small></div>{ready ? <Check /> : <i />}</article>; })}</div>
            <div className={`report-preview ${status === 'complete' ? 'revealed' : ''}`}><span className="report-label"><FileCheck2 /> 报告摘要</span>{status === 'complete' ? <><h3>{activeCompany} 的证据链已整理完成</h3><p>主体档案、书籍年报、新闻事件、经营指标与社会舆情已完成交叉核验，并将不确定信息单独标记。</p></> : <p>小企完成访谈、回到工位并连续复核后，这里会出现报告摘要。</p>}</div>
          </section>
          <section className="panel log-panel"><div className="panel-title"><span><Clock3 /> 实时日志</span><small>{visibleLogs.length}</small></div><div className="log-list" aria-live="polite">{visibleLogs.length ? visibleLogs.slice(-6).reverse().map((entry) => <div key={`${entry.at}-${entry.text}`}><time>{entry.time}</time><p>{entry.text}</p></div>) : <div className="empty-log">开始任务后，小企的每一步都会记录在这里。</div>}</div></section>
        </aside>
      </section>

      <footer className="app-footer"><span>企er · 可视化企业研究过程</span><span>演示数据仅用于交互原型</span></footer>
    </main>
  );
}
