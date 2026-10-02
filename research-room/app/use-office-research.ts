'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BackendError,
  emptyResearch,
  readCaseStream,
  reduceEvent,
  validateCase,
} from './research-events';
import type { ResearchState } from './research-events';
import { OfficeDirector } from './office-director';
import { fixtureFetch, testNames } from './research-fixtures';
import type { TestName } from './research-fixtures';

export function useOfficeResearch() {
  const [state, setState] = useState<ResearchState>(emptyResearch),
    [paused, setPaused] = useState(false),
    [speed, setSpeed] = useState(1),
    [testMode, setTestMode] = useState<TestName | null>(null);
  const stateRef = useRef(state),
    director = useRef(new OfficeDirector()),
    request = useRef<AbortController | null>(null),
    generation = useRef(0),
    lastInput = useRef({
      company_name: '',
      need: '了解这家公司的登记、资质与公开资料',
    });
  const [scene, setScene] = useState(() => new OfficeDirector().sample());
  const idle = state.connection === 'idle';
  const publish = useCallback((next: ResearchState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  useEffect(() => {
    const name = new URLSearchParams(location.search).get('animationTest');
    if (
      ['localhost', '127.0.0.1'].includes(location.hostname) &&
      testNames.includes(name as TestName)
    )
      queueMicrotask(() => setTestMode(name as TestName));
  }, []);
  useEffect(
    () => () => {
      generation.current++;
      request.current?.abort();
    },
    [],
  );
  const begin = useCallback(
    async (company: string, need?: string) => {
      if (!company.trim()) return;
      const token = ++generation.current;
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      lastInput.current = {
        company_name: company.trim(),
        need: need?.trim() || '了解这家公司的登记、资质与公开资料',
      };
      director.current = new OfficeDirector();
      setScene(director.current.sample());
      setPaused(false);
      publish({
        ...emptyResearch(),
        company: company.trim(),
        connection: 'connecting',
      });
      const fetchImpl = testMode ? fixtureFetch(testMode) : fetch;
      try {
        const c = await readCaseStream('/api/cases/stream', lastInput.current, {
          signal: controller.signal,
          fetchImpl,
          onEvent: (event) => {
            if (token === generation.current)
              publish(reduceEvent(stateRef.current, event));
          },
        });
        if (token !== generation.current) return;
        publish({ ...stateRef.current, verifying: true });
        const saved = await fetchImpl(
          '/api/cases/' + encodeURIComponent(c.id),
          { signal: controller.signal, cache: 'no-store' },
        );
        if (!saved.ok)
          throw new Error('报告已返回，但暂时无法确认保存，请检查案卷列表');
        const confirmed = validateCase(await saved.json());
        if (
          confirmed.id !== c.id ||
          confirmed.current !== c.current ||
          confirmed.case?.company_name !== lastInput.current.company_name
        )
          throw new Error('案卷保存校验不一致');
        if (token !== generation.current) return;
        publish({
          ...stateRef.current,
          connection: 'saved',
          verifying: false,
          result: confirmed,
          error: undefined,
        });
      } catch (error) {
        if (token !== generation.current || controller.signal.aborted) return;
        publish({
          ...stateRef.current,
          verifying: false,
          connection: error instanceof BackendError ? 'error' : 'disconnected',
          error: error instanceof Error ? error.message : '研究连接失败',
        });
      }
    },
    [publish, testMode],
  );
  const reset = useCallback(() => {
    generation.current++;
    request.current?.abort();
    director.current = new OfficeDirector();
    setScene(director.current.sample());
    setPaused(false);
    publish(emptyResearch());
  }, [publish]);
  useEffect(() => {
    if (paused || idle) return;
    let handle = 0,
      last = performance.now();
    const tick = (now: number) => {
      director.current.tick(Math.min(80, now - last) * speed, stateRef.current);
      last = now;
      setScene(director.current.sample());
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [paused, speed, idle]);
  const step = () => {
    if (paused) {
      director.current.tick(40, stateRef.current);
      setScene(director.current.sample());
    }
  };
  return {
    state,
    scene,
    paused,
    setPaused,
    speed,
    setSpeed,
    testMode,
    begin,
    reset,
    step,
    retry: () => begin(lastInput.current.company_name, lastInput.current.need),
  };
}
