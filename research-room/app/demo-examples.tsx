'use client';
import { useEffect, useState } from 'react';
import type { DemoCase } from './research-input';

export function DemoExamples({ selected, onSelect, onRemove }: {
  selected: DemoCase | null;
  onSelect: (demo: DemoCase) => void;
  onRemove: () => void;
}) {
  const [demos, setDemos] = useState<DemoCase[]>([]);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    setLoaded(false);
    fetch('/api/demo/cases', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('示例暂不可用');
        const data = await response.json();
        if (!Array.isArray(data)) throw new Error('示例格式错误');
        if (!controller.signal.aborted) {
          setDemos(data.filter(d => d.ready && d.input));
          setLoaded(true);
        }
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [attempt]);
  return <div className="demo-examples">
    <div className="demo-links" aria-label="查询示例">
      <span>试试示例</span>
      {demos.map(demo => <button key={demo.id} type="button"
        aria-pressed={selected?.id === demo.id}
        onClick={() => onSelect(demo)}>
        {demo.label.split('（')[0]}<small>{demo.real ? (demo.id === 'A' ? '理财' : demo.id === 'B' ? '求职' : '真实') : '虚构'}</small>
      </button>)}
      {failed && <button type="button" onClick={() => setAttempt(n => n + 1)}>示例加载失败，重试</button>}
      {!failed && !loaded && <span>加载中…</span>}
      {loaded && !demos.length && <span>暂无可用示例</span>}
    </div>
    {selected && <div className="demo-selection" key={selected.id}>
      <span className="sr-only" role="status">已填入{selected.real ? '示例' : '虚构示例'}，可修改后开始查询</span>
      {selected.input.material_text && <details className="demo-material">
        <summary>已附示例材料 · 查看</summary>
        <div><strong>{selected.input.material_title}</strong><p>{selected.input.material_text}</p></div>
      </details>}
      <button type="button" className="demo-remove" onClick={onRemove}>取消选用</button>
    </div>}
  </div>;
}
