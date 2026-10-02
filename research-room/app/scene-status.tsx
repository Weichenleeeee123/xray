'use client';
import type { ResearchState } from './research-events';
import { sceneNotice } from './scene-feedback';

export function SceneStatus({ state }: { state: ResearchState }) {
  const notice = sceneNotice(state);
  if (!notice) return null;
  return <output key={notice.key} className={`scene-status scene-status-${notice.kind}`}
    aria-live="polite" aria-atomic="true" data-notice={notice.kind}>
    <span className="sr-only">{notice.label}</span>
    <span className="scene-message-type" aria-hidden="true">{notice.label}
      {notice.kind === 'running' && <span className="scene-message-dots"><i>.</i><i>.</i><i>.</i></span>}
    </span>
  </output>;
}
