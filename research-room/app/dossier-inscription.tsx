'use client';
import { useEffect, useRef, useState } from 'react';
import { coverNameParts } from './scene-feedback';

export function DossierInscription({ company }: { company: string }) {
  const area = useRef<HTMLSpanElement>(null);
  const name = useRef<HTMLElement>(null);
  const subtitle = useRef<HTMLSpanElement>(null);
  const [overflow, setOverflow] = useState(false);
  useEffect(() => {
    let disposed = false;
    const fit = () => {
      if (disposed || !area.current || !name.current || !subtitle.current) return;
      const stage = area.current.closest<HTMLElement>('.office-stage');
      let size = Math.min(13, Math.max(9, (stage?.clientWidth ?? 1440) * .0082));
      const available = Math.max(0, area.current.clientHeight - subtitle.current.offsetHeight
        - parseFloat(getComputedStyle(subtitle.current).marginTop) - 1);
      name.current.style.setProperty('--cover-name-size', `${size}px`);
      while (name.current.offsetHeight > available && size > 8.5) {
        size = Math.max(8.5, size - .25);
        name.current.style.setProperty('--cover-name-size', `${size}px`);
      }
      // Extreme names remain complete and scrollable; never make them microscopic.
      setOverflow(name.current.offsetHeight > available || name.current.scrollWidth > area.current.clientWidth);
    };
    const observer = new ResizeObserver(fit);
    if (area.current) observer.observe(area.current);
    fit();
    void document.fonts.ready.then(fit);
    return () => { disposed = true; observer.disconnect(); };
  }, [company]);
  const parts = coverNameParts(company);
  return <span ref={area} className="dossier-inscription">
    <span className={`dossier-name-field${overflow ? ' name-scrollable' : ''}`} title={company}>
      <strong ref={name}>{parts.map((part, index) => <span key={index}
        className={parts.length > 1 && index === 1 ? 'cover-name-suffix' : 'cover-name-main'}>{part}</span>)}</strong>
    </span>
    <span ref={subtitle} className="dossier-title">企业研究报告</span>
  </span>;
}
