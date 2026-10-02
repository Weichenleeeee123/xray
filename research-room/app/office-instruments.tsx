'use client';
import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { lifecycleLabel, researchProgress } from './research-events';
import type { ResearchState } from './research-events';

export function OfficeInstruments({ state }: { state: ResearchState }) {
  const progress = researchProgress(state);
  const viewport = useRef<HTMLDivElement>(null);
  const lettering = useRef<HTMLSpanElement>(null);
  const [overflow, setOverflow] = useState(0);
  useEffect(() => {
    const measure = () => setOverflow(Math.max(0, (lettering.current?.scrollWidth ?? 0) - (viewport.current?.clientWidth ?? 0)));
    const observer = new ResizeObserver(measure);
    if (viewport.current) observer.observe(viewport.current);
    if (lettering.current) observer.observe(lettering.current);
    measure();
    return () => observer.disconnect();
  }, [state.company]);
  const interrupted = ['disconnected', 'error'].includes(state.connection) || !!state.saveStatus;
  return <>
    <div className="monitor-display" aria-label={`正在调研：${state.company}`} title={state.company}>
      <div className="monitor-caption"><i /> 小企 · 企业调研</div>
      <div ref={viewport} className={`monitor-company ${overflow > 1 ? 'name-overflow' : ''}`} tabIndex={0}
        style={{ '--name-shift': `${-overflow}px`, '--name-duration': `${Math.max(12, overflow / 18 + 7)}s` } as CSSProperties}>
        <span ref={lettering}>{state.company || '正在恢复研究任务'}</span>
      </div>
      <div className="monitor-scanline" aria-hidden="true" />
    </div>
    <div className={`clock-progress ${interrupted ? 'clock-interrupted' : ''}`}
      role="progressbar" aria-label="调研环节完成进度" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={progress.percent}
      aria-valuetext={`${progress.percent}%，${progress.completed}/${progress.total} 个环节完成。${lifecycleLabel(state)}`}
      title={`已完成 ${progress.completed}/${progress.total} 个环节（含保存确认）；不代表剩余时间或企业可靠程度。${lifecycleLabel(state)}`}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="clock-track" cx="50" cy="50" r="44" />
        <circle className="clock-ring" cx="50" cy="50" r="44" pathLength="100" strokeDasharray={`${progress.percent} 100`} />
      </svg>
      <span className="clock-number">{progress.percent}<small>%</small></span>
      <span className="clock-caption">{interrupted ? '待确认' : state.connection === 'saved' ? '已完成' : '调研进度'}</span>
    </div>
  </>;
}
