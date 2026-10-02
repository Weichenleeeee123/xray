'use client';
import { useEffect, useState } from 'react';
import { officeImages, previewSources, upgradeImages } from './progressive-images';

function decodeImage(url: string, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      signal.removeEventListener('abort', cancel);
      if (error) {
        image.removeAttribute('src');
        reject(error);
      } else resolve();
    };
    const cancel = () => finish(new Error('Image upgrade cancelled'));
    const timeout = setTimeout(() => finish(new Error('Image upgrade timed out')), 45_000);
    signal.addEventListener('abort', cancel, { once: true });
    if (signal.aborted) { cancel(); return; }
    image.fetchPriority = 'low';
    image.decoding = 'async';
    image.src = url;
    void image.decode().then(() => finish(), () => finish(new Error('Image decode failed')));
  });
}

export function useProgressiveImages(previewReady: boolean) {
  const [sources, setSources] = useState(previewSources);
  useEffect(() => {
    if (!previewReady) return;
    const controller = new AbortController();
    let frame = 0, idle = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let paintObserver: PerformanceObserver | undefined;
    const upgrade = () => {
      void upgradeImages(officeImages, decodeImage, ({ id, full }) => {
        setSources((previous) => ({ ...previous, [id]: full }));
      }, controller.signal);
    };
    const schedule = () => {
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => {
          if ('requestIdleCallback' in window) {
            idle = window.requestIdleCallback(upgrade, { timeout: 1500 });
          } else timer = globalThis.setTimeout(upgrade, 200);
        });
      });
    };
    // Two animation frames alone do not guarantee a contentful paint under load.
    const start = () => {
      if (typeof PerformanceObserver !== 'undefined' &&
          PerformanceObserver.supportedEntryTypes.includes('paint') &&
          !performance.getEntriesByName('first-contentful-paint').length) {
        paintObserver = new PerformanceObserver((list) => {
          if (list.getEntries().some(({ name }) => name === 'first-contentful-paint')) {
            paintObserver?.disconnect();
            schedule();
          }
        });
        paintObserver.observe({ type: 'paint', buffered: true });
      } else schedule();
    };
    if (document.readyState === 'complete') start();
    else window.addEventListener('load', start, { once: true });
    return () => {
      controller.abort();
      paintObserver?.disconnect();
      window.removeEventListener('load', start);
      cancelAnimationFrame(frame);
      if (idle) window.cancelIdleCallback(idle);
      clearTimeout(timer);
    };
  }, [previewReady]);
  return sources;
}
