'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BackendError,
  emptyResearch,
  followRun,
  readCaseStream,
  reduceEvent,
  startRun,
  validateCase,
} from './research-events';
import type { ProgressEvent, ResearchState } from './research-events';
import { OfficeDirector } from './office-director';
import { fixtureFetch, testNames } from './research-fixtures';
import type { TestName } from './research-fixtures';

const RUN_ID = /^[0-9a-f]{24}$/;
// 任务编号放在地址栏（?run=…）：刷新、复制链接都能接着看同一次查询，不会重新提交
function rememberRun(runId: string | null) {
  const url = new URL(location.href);
  if (runId) url.searchParams.set('run', runId);
  else url.searchParams.delete('run');
  history.replaceState(history.state, '', url);
}

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
  useEffect(
    () => () => {
      generation.current++;
      request.current?.abort();
    },
    [],
  );
  // resumeId：刷新后接着看已经在跑（或跑完）的任务；没有就新建一次查询
  const run = useCallback(
    async (company: string, need: string | undefined, resumeId: string | null, mode: TestName | null) => {
      const token = ++generation.current;
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      if (!resumeId)
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
      const fetchImpl = mode ? fixtureFetch(mode) : fetch;
      const onEvent = (event: ProgressEvent) => {
        if (token === generation.current)
          publish(reduceEvent(stateRef.current, event));
      };
      try {
        let caseId: string, current: number | undefined;
        if (mode) {
          // 本地测试入口：合成事件走原来的进度流
          const c = await readCaseStream('/api/cases/stream', lastInput.current, {
            signal: controller.signal,
            fetchImpl,
            onEvent,
          });
          caseId = c.id;
          current = c.current;
        } else {
          const runId = resumeId ?? (await startRun(lastInput.current, fetchImpl));
          if (token === generation.current) rememberRun(runId);
          caseId = await followRun(runId, {
            signal: controller.signal,
            fetchImpl,
            onEvent,
          });
        }
        if (token !== generation.current) return;
        publish({ ...stateRef.current, verifying: true });
        const saved = await fetchImpl(
          '/api/cases/' + encodeURIComponent(caseId),
          { signal: controller.signal, cache: 'no-store' },
        );
        if (!saved.ok)
          throw new Error('报告已返回，但暂时无法确认保存，请检查案卷列表');
        const confirmed = validateCase(await saved.json());
        if (resumeId)
          lastInput.current = {
            company_name: confirmed.case?.company_name ?? stateRef.current.company,
            need: lastInput.current.need,
          };
        if (
          confirmed.id !== caseId ||
          (current !== undefined && confirmed.current !== current) ||
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
    [publish],
  );
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const name = params.get('animationTest');
    if (
      ['localhost', '127.0.0.1'].includes(location.hostname) &&
      testNames.includes(name as TestName)
    ) {
      queueMicrotask(() => setTestMode(name as TestName));
      return;
    }
    const resume = params.get('run');
    if (resume && RUN_ID.test(resume))
      queueMicrotask(() => void run('', undefined, resume, null));
  }, [run]);
  const begin = useCallback(
    async (company: string, need?: string) => {
      if (!company.trim()) return;
      await run(company, need, null, testMode);
    },
    [run, testMode],
  );
  const reset = useCallback(() => {
    generation.current++;
    request.current?.abort();
    director.current = new OfficeDirector();
    setScene(director.current.sample());
    setPaused(false);
    rememberRun(null);
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
