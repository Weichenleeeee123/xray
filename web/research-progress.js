/* Shared by the native main site and animation adapters. No model or risk decisions here. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ResearchProgress = api;
})(globalThis, function () {
  'use strict';

  async function readCaseStream(url, body, { onEvent = () => {}, signal, fetchImpl = fetch } = {}) {
    const response = await fetchImpl(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = Array.isArray(error.detail)
        ? error.detail.map(e => `${(e.loc || []).join('.')}: ${e.msg || '输入不合格'}`).join('；')
        : error.detail;
      throw new Error(typeof detail === 'string' ? detail : `请求失败（${response.status}）`);
    }
    if (!response.body) throw new Error('浏览器没有收到进度流，请到案卷列表确认结果');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let buffer = '';
    function event(line) {
      if (!line.trim()) return null;
      const e = JSON.parse(line);
      if (!e || typeof e !== 'object') throw new Error('进度事件格式不正确');
      if (e.type === 'error') throw new Error(e.message || '生成失败，请到案卷列表确认结果');
      if (e.type === 'case') {
        const c = e.case;
        if (!c || typeof c.id !== 'string' || !c.id || !Number.isInteger(c.current)
          || !Array.isArray(c.versions) || !c.versions.some(v => v.no === c.current)) {
          throw new Error('未收到完整案卷，请到案卷列表确认结果');
        }
        return c;
      }
      if (!['begin', 'step', 'prebuilt'].includes(e.type)) throw new Error('收到未知进度事件');
      onEvent(e);
      return null;
    }
    try {
      for (;;) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        let i;
        while ((i = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, i); buffer = buffer.slice(i + 1);
          const c = event(line);
          if (c) return c;
        }
        if (done) {
          const c = event(buffer);
          if (c) return c;
          throw new Error('连接已结束，但未收到案卷。后端可能仍在处理，请到「案卷」查看，避免重复提交');
        }
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  function progressState() { return { company: '', steps: [] }; }

  function updateProgress(state, event) {
    if (event.type === 'prebuilt') {
      state.prebuilt = { demo_id: event.demo_id, built_at: event.built_at };
    } else if (event.type === 'begin') {
      state.company = event.company;
      state.steps = event.steps.map(s => ({ ...s, phase: 'waiting', coverage: null, counts: null, text: '' }));
    } else if (event.type === 'step') {
      const step = state.steps.find(s => s.id === event.id);
      if (!step || !['start', 'done'].includes(event.phase)) throw new Error('进度步骤与计划不一致');
      Object.assign(step, { phase: event.phase });
      if (event.phase === 'done') Object.assign(step, { coverage: event.coverage, counts: event.counts, text: event.text });
    }
    return state;
  }

  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const stamps = { found: '查到', not_found: '查了没有', not_covered: '没查', failed: '没查成' };
  const stations = {
    intake: { name: 'door', x: 46, y: 34, pose: '66.666667% 100%' },
    lists: { name: 'company', x: 25, y: 34, pose: '0% 0%' },
    amac: { name: 'data', x: 83, y: 66, pose: '0% 0%' },
    registry: { name: 'data', x: 83, y: 66, pose: '0% 0%' },
    finance: { name: 'data', x: 83, y: 66, pose: '0% 0%' },
    pack: { name: 'library', x: 13, y: 60, pose: '66.666667% 0%' },
    web: { name: 'news', x: 77, y: 33, pose: '33.333333% 0%' },
    opinion: { name: 'door', x: 46, y: 34, pose: '66.666667% 100%' },
    reviews: { name: 'door', x: 46, y: 34, pose: '66.666667% 100%' },
    rules: { name: 'desk', x: 50, y: 74, pose: '100% 0%' },
    plain: { name: 'desk', x: 50, y: 74, pose: '0% 50%' },
  };
  function stationFor(state) {
    const active = state.steps.find(s => s.phase === 'start');
    return stations[active?.id] || stations.plain;
  }
  function progressHtml(state) {
    return `<h2>${escape(state.company)}</h2>${state.prebuilt ? `<aside class="report-provenance"><strong>预制示例快照</strong><p>正在回放生成过程，本次未重新联网查询。${state.prebuilt.built_at ? `预制包生成时间：${escape(state.prebuilt.built_at)}。` : ''}各条资料日期见出处。</p></aside>` : ''}<ol class="research-steps">${state.steps.map(step => {
      const label = step.phase === 'waiting' ? '等待' : step.phase === 'start' ? state.prebuilt ? '回放中' : '进行中' : `${state.prebuilt ? '当时：' : ''}${stamps[step.coverage] || '完成'}`;
      return `<li class="rp-${escape(step.phase)}"><strong>${escape(step.label)}</strong>
        <span class="rp-stamp rp-${escape(step.coverage || step.phase)}">${label}</span>
        <p>${escape(step.text)}</p></li>`;
    }).join('')}</ol>`;
  }
  function mount(host, company) {
    const state = progressState(); state.company = company;
    host.innerHTML = `<section class="research-wait" aria-busy="true">
      <p class="kicker">小企正在整理案卷</p>
      <div class="research-scene" aria-hidden="true"><div class="research-avatar"></div></div>
      <p role="status" class="research-current">正在连接后端…</p>
      <p class="small muted">已用 <span class="research-elapsed">0</span> 秒 · 动画用于展示过程，查询状态与资料来源见下方。</p>
      <div class="research-results">${progressHtml(state)}</div>
      <p class="small muted">若连接断开，后端仍可能生成案卷，可到「案卷」查看，避免重复提交。</p>
    </section>`;
    const avatar = host.querySelector('.research-avatar');
    const current = host.querySelector('.research-current');
    const results = host.querySelector('.research-results');
    const clock = host.querySelector('.research-elapsed');
    const started = Date.now();
    const timer = setInterval(() => { clock.textContent = Math.floor((Date.now() - started) / 1000); }, 500);
    return {
      onEvent(event) {
        updateProgress(state, event);
        results.innerHTML = progressHtml(state);
        const active = state.steps.find(s => s.phase === 'start');
        current.textContent = active ? `${state.prebuilt ? '正在回放' : '正在处理'}：${active.label}` : state.prebuilt ? '正在准备预制示例…' : '正在整理结果…';
        const station = stationFor(state);
        avatar.style.left = `${station.x}%`; avatar.style.top = `${station.y}%`;
        avatar.style.backgroundPosition = station.pose;
      },
      stop() { clearInterval(timer); },
    };
  }
  return { readCaseStream, progressState, updateProgress, progressHtml, stationFor, mount };
});
