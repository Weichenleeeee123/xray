'use client';
import type { CSSProperties } from 'react';
import type { ResearchState } from './research-events';
import { reportPresentation } from './research-events';
import type { OfficeDirector } from './office-director';

export function ReportDossier({
  state,
  scene,
  opening,
  onOpen,
  onRetry,
}: {
  state: ResearchState;
  scene: ReturnType<OfficeDirector['sample']>;
  opening: boolean;
  onOpen: () => void;
  onRetry: () => void;
}) {
  const report = reportPresentation(state, scene.phase.id);
  if (!report.visible) return null;
  const savedCase = state.result ?? state.candidate;
  const date = savedCase?.created_at?.slice(0, 10);
  const label = opening ? '正在打开报告' : report.label;
  const errorDetail = state.saveError ?? state.error;
  const finishing = ['bind-report', 'push-report', 'present-report'].includes(
    scene.phase.id,
  );
  const style = {
    '--dossier-x': 62 - scene.pushing * 2.2 + '%',
    '--cover-angle': -24 * (1 - scene.binding) + 'deg',
    '--binding': scene.binding,
    '--wing-reach': scene.wingReach,
    '--dossier-push': scene.pushing,
  } as CSSProperties;
  return (
    <div
      className={`desk-dossier dossier-${report.status} ${opening ? 'dossier-opening' : ''}`}
      style={style}
      data-report-status={report.status}
      data-binding={scene.binding.toFixed(3)}
      data-pushing={scene.pushing.toFixed(3)}
    >
      <button
        type="button"
        className="dossier-hit-area"
        disabled={opening || (!report.canOpen && !report.canRetry)}
        onClick={report.canOpen ? onOpen : onRetry}
        aria-label={report.canOpen ? `查看报告：${state.company}` : label}
        aria-describedby={
          errorDetail ? 'dossier-state dossier-error' : 'dossier-state'
        }
        title={errorDetail ?? `${state.company} · ${label}`}
      >
        <span className="dossier-halo" aria-hidden="true" />
        <span className="dossier-book" aria-hidden="true">
          <span className="dossier-pages">
            {Array.from({ length: 8 }, (_, i) => (
              <span key={i} style={{ '--sheet': i } as CSSProperties} />
            ))}
          </span>
          <span className="dossier-cover">
            <img
              className="dossier-art"
              src="/investigation-dossier.png"
              alt=""
              draggable={false}
            />
            <span className="dossier-inscription">
              <strong>{state.company}</strong>
              <span className="dossier-title">企业研究报告</span>
              <small>{date ?? '资料核对中'}</small>
            </span>
          </span>
        </span>
        <span className="dossier-label" id="dossier-state" aria-live="polite">
          <span className="dossier-label-icon" aria-hidden="true">
            {report.canOpen ? '✦' : '·'}
          </span>
          {label}
          {report.canOpen && !opening && <kbd aria-hidden="true">打开</kbd>}
        </span>
        {errorDetail && (
          <span className="sr-only" id="dossier-error">
            {errorDetail}
          </span>
        )}
      </button>
      {finishing && (
        <svg className="dossier-wing" viewBox="0 0 120 65" aria-hidden="true">
          <defs>
            <linearGradient id="wing-light" x2="0.7" y2="1">
              <stop stopColor="#fff8e1" />
              <stop offset="1" stopColor="#d4c5a9" />
            </linearGradient>
          </defs>
          <path
            d="M8 48 Q11 31 27 28 Q42 3 55 18 Q61 2 70 19 Q80 6 87 26 Q102 16 102 36 Q113 32 113 46 Q106 59 81 59 L28 57 Z"
            fill="url(#wing-light)"
            stroke="#675546"
            strokeWidth="3"
          />
          <path
            d="M11 35 Q24 32 34 51 L22 61 L3 58 Z"
            fill="#1b293b"
            stroke="#0d1524"
            strokeWidth="3"
          />
        </svg>
      )}
    </div>
  );
}
