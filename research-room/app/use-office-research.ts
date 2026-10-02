'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BackendError,
  emptyResearch,
  followRun,
  startRun,
  readCaseStream,
  reduceEvent,
  confirmSavedCase,
} from './research-events';
import type { ResearchState, CaseReference } from './research-events';
import { OfficeDirector } from './office-director';
import { fixtureFetch, testNames } from './research-fixtures';
import type { TestName } from './research-fixtures';
import { researchInput } from './research-input';
import type { ResearchInput } from './research-input';

const RUN_ID = /^[0-9a-f]{24}$/;
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
    transport = useRef<typeof fetch>(fetch),
    activeRun = useRef<string | null>(null),
    generation = useRef(0),
    lastInput = useRef<ResearchInput>({
      company_name: '',
      need: '了解这家公司的登记、资质与公开资料',
    });
  const [scene, setScene] = useState(() => new OfficeDirector().sample());
  const fetchImpl = useMemo(
    () => (testMode ? fixtureFetch(testMode) : fetch),
    [testMode],
  );
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
  const verifySaved = useCallback(
    async (
      candidate: CaseReference,
      token: number,
      controller: AbortController,
      fetchImpl: typeof fetch,
      company: string,
    ) => {
      if (token !== generation.current) return;
      publish({
        ...stateRef.current,
        candidate,
        verifying: true,
        saveStatus: undefined,
        saveError: undefined,
        error: undefined,
      });
      try {
        const confirmed = await confirmSavedCase(
          candidate,
          company,
          fetchImpl,
          controller.signal,
        );
        if (token !== generation.current || controller.signal.aborted) return;
        lastInput.current = {
          ...lastInput.current,
          company_name: confirmed.case?.company_name ?? company,
          need: confirmed.case?.need ?? lastInput.current.need,
        };
        publish({
          ...stateRef.current,
          connection: 'saved',
          verifying: false,
          result: confirmed,
          saveStatus: undefined,
          saveError: undefined,
        });
      } catch (error) {
        if (token !== generation.current || controller.signal.aborted) return;
        publish({
          ...stateRef.current,
          verifying: false,
          saveStatus: 'unconfirmed',
          saveError: error instanceof Error ? error.message : '保存暂未确认',
        });
      }
    },
    [publish],
  );
  const run = useCallback(
    async (company: string, need?: string, resumeId: string | null = null, preset?: ResearchInput) => {
      if (!company.trim() && !resumeId) return;
      const token = ++generation.current;
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      if (!resumeId)
        lastInput.current = researchInput(company, need, preset);
      activeRun.current = resumeId;
      director.current = new OfficeDirector();
      setScene(director.current.sample());
      setPaused(false);
      publish({
        ...emptyResearch(),
        company: company.trim(),
        connection: 'connecting',
      });
      transport.current = fetchImpl;
      try {
        const onEvent = (event: import('./research-events').ProgressEvent) => {
          if (token !== generation.current) return;
          if (resumeId && event.type === 'begin')
            lastInput.current = {
              ...lastInput.current,
              company_name: event.company,
            };
          publish(reduceEvent(stateRef.current, event));
        };
        let candidate: CaseReference;
        if (testMode) {
          candidate = await readCaseStream(
            '/api/cases/stream',
            lastInput.current,
            {
              signal: controller.signal,
              fetchImpl,
              onEvent,
            },
          );
        } else {
          const runId =
            resumeId ?? (await startRun(lastInput.current, fetchImpl, {
              signal: controller.signal,
              requestKey: crypto.randomUUID(),
            }));
          if (token !== generation.current || controller.signal.aborted) return;
          activeRun.current = runId;
          rememberRun(runId);
          const caseId = await followRun(runId, {
            signal: controller.signal,
            fetchImpl,
            onEvent,
          });
          candidate = { id: caseId };
        }
        if (token !== generation.current) return;
        await verifySaved(
          candidate,
          token,
          controller,
          fetchImpl,
          lastInput.current.company_name,
        );
      } catch (error) {
        if (token !== generation.current || controller.signal.aborted) return;
        publish({
          ...stateRef.current,
          verifying: false,
          connection: error instanceof BackendError ? 'error' : 'disconnected',
          saveStatus:
            error instanceof BackendError &&
            /保存失败|无法保存|保存出错/.test(error.message)
              ? 'failed'
              : undefined,
          error: error instanceof Error ? error.message : '研究连接失败',
        });
      }
    },
    [publish, fetchImpl, verifySaved, testMode],
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
      queueMicrotask(() => void run('', undefined, resume));
  }, [run]);
  const begin = useCallback(
    async (company: string, need?: string, preset?: ResearchInput) => {
      if (['connecting', 'live'].includes(stateRef.current.connection)) return;
      await run(company, need, null, preset);
    },
    [run],
  );
  const retrySave = useCallback(async () => {
    const candidate = stateRef.current.candidate;
    if (!candidate || stateRef.current.verifying) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    await verifySaved(
      candidate,
      generation.current,
      controller,
      transport.current,
      lastInput.current.company_name,
    );
  }, [verifySaved]);
  const reset = useCallback(() => {
    generation.current++;
    request.current?.abort();
    director.current = new OfficeDirector();
    setScene(director.current.sample());
    setPaused(false);
    activeRun.current = null;
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
    retry: () => begin(lastInput.current.company_name, lastInput.current.need, lastInput.current),
    retrySave,
    canReconnect: !!activeRun.current && state.connection === 'disconnected',
    reconnect: () => activeRun.current
      ? run(lastInput.current.company_name, lastInput.current.need, activeRun.current)
      : Promise.resolve(),
  };
}
