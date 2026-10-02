'use client';
import { useEffect, useRef, useState } from 'react';
import { imageUpgradePlan, previewSources, upgradeImages } from './progressive-images';
import type { ImageUpgradePhase } from './progressive-images';

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

export function useProgressiveImages(previewReady: boolean, phase: ImageUpgradePhase = 'idle') {
  const [sources, setSources] = useState(previewSources);
  const sourcesRef = useRef(sources);
  useEffect(() => {
    if (!previewReady || phase === 'research') return;
    const startVisibleQueue = () => {
      if (document.hidden) return;
      // Each visible interval owns its controller and pending callbacks. A
      // cancelled queue's finally cannot unlock a newer queue after resuming.
      const controller = new AbortController();
      let frame = 0, idle = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let paintObserver: PerformanceObserver | undefined;
      let upgrading = false;
      const upgrade = () => {
        if (document.hidden || controller.signal.aborted || upgrading) return;
        upgrading = true;
        void upgradeImages(imageUpgradePlan(phase, sourcesRef.current), decodeImage, ({ id, full }) => {
          sourcesRef.current = { ...sourcesRef.current, [id]: full };
          setSources(sourcesRef.current);
        }, controller.signal).finally(() => { upgrading = false; });
      };
      const schedule = () => {
        frame = requestAnimationFrame(() => {
          frame = requestAnimationFrame(() => {
            if ('requestIdleCallback' in window) {
              idle = window.requestIdleCallback(upgrade, { timeout: 3000 });
            } else timer = globalThis.setTimeout(upgrade, 500);
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
      // Let the first interaction and example data finish before cosmetic downloads.
      const delayedStart = () => {
        clearTimeout(timer);
        timer = globalThis.setTimeout(start, 2500);
      };
      if (document.readyState === 'complete') delayedStart();
      else window.addEventListener('load', delayedStart, { once: true });
      return () => {
        controller.abort();
        paintObserver?.disconnect();
        window.removeEventListener('load', delayedStart);
        cancelAnimationFrame(frame);
        if (idle) window.cancelIdleCallback(idle);
        clearTimeout(timer);
      };
    };
    let stopQueue = startVisibleQueue();
    const updateVisibility = () => {
      stopQueue?.();
      stopQueue = startVisibleQueue();
    };
    document.addEventListener('visibilitychange', updateVisibility);
    return () => {
      stopQueue?.();
      document.removeEventListener('visibilitychange', updateVisibility);
    };
  }, [previewReady, phase]);
  return sources;
}
