import type { ResearchState } from './research-events';
import { researchProvenance } from './research-events.ts';

// Presentation only: neither elapsed animation time nor returned prose proves saving.
export function sceneNotice(state: ResearchState) {
  if (state.connection === 'idle') return null;
  if (state.verifying) return { kind: 'running', label: '正在确认报告保存', key: 'verifying' };
  if (state.saveStatus === 'failed') return { kind: 'attention', label: '报告保存失败', key: 'save-failed' };
  if (state.saveStatus === 'unconfirmed') return { kind: 'attention', label: '报告保存待确认', key: 'save-unconfirmed' };
  if (state.connection === 'disconnected') return { kind: 'attention', label: '连接中断，进度待确认', key: 'disconnected' };
  if (state.connection === 'error') return { kind: 'attention', label: '调研暂未完成', key: 'error' };
  if (state.connection === 'saved' && state.result)
    return { kind: 'complete', label: '报告已完成', key: `saved:${state.result.id}:${state.result.current}` };
  return { kind: 'running', label: researchProvenance(state) ? '报告整理中' : '报告生成中', key: 'running' };
}

// Keep the legal suffix together without abbreviating or dropping any character.
export function coverNameParts(company: string): string[] {
  const suffix = company.match(/(股份有限公司|有限责任公司|集团有限公司|有限公司)$/)?.[0];
  return suffix && company.length > suffix.length
    ? [company.slice(0, -suffix.length), suffix] : [company];
}
