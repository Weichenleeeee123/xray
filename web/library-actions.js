/* Save exact assistant explanation snapshots. Rendering never performs writes. */
(function (root) {
  'use strict';
  let injected = {}, epoch = 0, queue = Promise.resolve();
  const results = new Map(), pending = new Map(), received = new Set(), controllers = new Set();
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const defaults = {
    getState: () => S,
    readRaw: () => localStorage.getItem('xray.library'),
    readOwner: () => localStorage.getItem('xray.library.owner'),
    writeOwner: email => { try { email == null ? localStorage.removeItem('xray.library.owner') : localStorage.setItem('xray.library.owner', email); return true; } catch { return false; } },
    readPending: email => localStorage.getItem(`xray.library.pending:${email}`) === '1',
    writePending: (email, dirty) => { try { dirty ? localStorage.setItem(`xray.library.pending:${email}`, '1') : localStorage.removeItem(`xray.library.pending:${email}`); return true; } catch { return false; } },
    readDeleted: email => JSON.parse(localStorage.getItem(`xray.library.deleted:${email}`) || '[]'),
    writeDeleted: (email, ids) => { try { ids.length ? localStorage.setItem(`xray.library.deleted:${email}`, JSON.stringify(ids)) : localStorage.removeItem(`xray.library.deleted:${email}`); return true; } catch { return false; } },
    write: list => libWrite(list, false),
    api: (path, options) => api(path, options),
    route: () => location.hash,
    now: () => new Date().toISOString(),
    beforeWrite: () => { if (typeof libPush === 'function') clearTimeout(libPush.t); },
    refresh: () => { if (typeof refreshChat === 'function') refreshChat(); },
    notify: message => { if (typeof toast === 'function') toast(message, true); },
  };
  const dep = name => injected[name] || defaults[name];
  const state = () => dep('getState')();
  function identity() {
    const account = state().session?.account;
    return account ? `account:${account.id || account.email || ''}` : 'guest';
  }
  function captureContext(options = {}) {
    const s = state();
    return {identity:identity(), account:!!s.session?.account, email:s.session?.account?.email, session:s.session, epoch,
      caseId:s.case?.id, version:s.viewNo ?? s.case?.current, route:dep('route')(), navigationEpoch:s.navigationEpoch || 0,
      requestId:options.requestId, autoEligible:options.autoEligible === true};
  }
  function active(context, includeView = true) {
    const current = captureContext();
    return !state().accountChanging && context.epoch === epoch && context.identity === current.identity && context.session === current.session
      && (!includeView || (context.caseId === current.caseId && context.version === current.version
        && context.route === current.route && context.navigationEpoch === current.navigationEpoch));
  }
  function invalidate() {
    epoch += 1;
    controllers.forEach(controller => controller.abort('identity changed'));
    controllers.clear();
  }
  function runExclusive(task) {
    const next = queue.then(task, task);
    queue = next.catch(() => {});
    return next;
  }
  const textFits = (value, max, required = false) => typeof value === 'string' && value.length <= max && (!required || value.length > 0);
  function validEntry(entry) {
    return entry && typeof entry === 'object' && !Array.isArray(entry)
      && textFits(entry.id, 80, true) && textFits(entry.term, 80)
      && textFits(entry.plain ?? '', 2000) && textFits(entry.why ?? '', 2000)
      && textFits(entry.basis ?? '', 300) && (entry.origin == null || textFits(entry.origin, 20))
      && textFits(entry.savedAt ?? '', 40) && Array.isArray(entry.seen ?? []) && (entry.seen ?? []).length <= 50
      && (entry.seen ?? []).every(seen => seen && textFits(seen.caseId, 40) && textFits(seen.company ?? '', 120)
        && (seen.version == null || (Number.isInteger(seen.version) && seen.version > 0)));
  }
  function checkedList(list) {
    if (!Array.isArray(list) || list.length > 500 || !list.every(validEntry)
        || new Set(list.map(entry => entry.id)).size !== list.length) throw new Error('corrupt');
    return list;
  }
  function read(context) {
    const owner = dep('readOwner')();
    const account = state().session?.account;
    if (owner && (!context.account || owner !== account?.email)) throw new Error('owner');
    const raw = dep('readRaw')();
    return checkedList(raw == null || raw === '' ? [] : JSON.parse(raw));
  }
  const accountHeaders = context => ({'X-Xray-Library-Owner':context.email});
  function markPending() {
    const context = captureContext();
    if (!context.account || !active(context, false)) return false;
    try { return dep('writePending')(context.email, true); } catch { return false; }
  }
  function deleted(context) {
    const ids = dep('readDeleted')(context.email);
    if (!Array.isArray(ids) || ids.length > 500 || ids.some(id => !textFits(id, 80, true))) throw new Error('corrupt');
    return ids;
  }
  function recordChange(before, after) {
    const context = captureContext();
    if (!context.account || !active(context, false)) return false;
    try {
      checkedList(before); checkedList(after);
      const tombstones = new Set(deleted(context)), beforeIds = new Set(before.map(entry => entry.id)), afterIds = new Set(after.map(entry => entry.id));
      beforeIds.forEach(id => { if (!afterIds.has(id)) tombstones.add(id); });
      afterIds.forEach(id => { if (!beforeIds.has(id)) tombstones.delete(id); });
      if (tombstones.size > 500 || !dep('writeDeleted')(context.email, [...tombstones])) throw new Error('failed');
      return markPending();
    } catch { notify('收藏改动的同步记录未保存，请保留当前页面并重试同步'); return false; }
  }
  function installLocal(list, context) {
    const previousOwner = dep('readOwner')();
    if (previousOwner === context.email) return dep('write')(list, false);
    let previous;
    try { previous = checkedList(JSON.parse(dep('readRaw')() || '[]')); } catch { previous = null; }
    // Quarantine first: if any later storage operation fails, a foreign
    // account's cache can never become labelled as the newly signed-in user.
    if (!dep('writeOwner')(`pending-owner:${context.email}`)) return false;
    if (!dep('write')(list, false)) { dep('writeOwner')(previousOwner); return false; }
    if (dep('writeOwner')(context.email)) return true;
    if (previous && dep('write')(previous, false)) dep('writeOwner')(previousOwner);
    return false;
  }
  function clearPendingIfUnchanged(context, submitted) {
    if (JSON.stringify(read(context)) !== JSON.stringify(submitted)) return;
    if (!dep('writeDeleted')(context.email, [])) return;
    dep('writePending')(context.email, false);
  }
  function candidates(message) {
    if (!message || message.role !== 'assistant' || !Number.isInteger(message.version)) return [];
    if (!state().case?.versions?.some(version => version.no === message.version)) return [];
    if (message.answer_kind === 'library_action') {
      const action = message.library_action;
      if (action?.operation !== 'save_terms' || action.source_version !== message.version) return [];
      return Array.isArray(action.terms) && action.terms.length <= 20 ? action.terms : [];
    }
    if (message.answer_kind !== 'glossary') return [];
    return Array.isArray(message.knowledge_terms) && message.knowledge_terms.length <= 20 ? message.knowledge_terms : [];
  }
  function snapshot(message, term) {
    const c = state().case, version = c?.versions.find(v => v.no === message.version);
    const company = version?.company?.name || c?.case?.company_name;
    if (!version || !textFits(c.id, 40, true) || !textFits(company, 120)) throw new Error('invalid');
    // Never resolve through termOf(), current view terms or the live glossary.
    const basis = term.law || (term.basis && version.sources?.[term.basis]?.name) || term.basis || '';
    const result = {id:term.id,term:term.term,plain:term.plain,why:term.why || '',basis,
      origin:term.origin || 'glossary',savedAt:dep('now')(),
      seen:[{caseId:c.id,version:message.version,company}]};
    if (!validEntry(result) || !result.plain) throw new Error('invalid');
    return result;
  }
  function sameSnapshot(left, right) {
    return ['id','term','plain','why','basis','origin'].every(field => (left[field] || '') === (right[field] || ''));
  }
  function containsSnapshot(saved, expected) {
    return sameSnapshot(saved, expected) && (expected.seen || []).every(item => (saved.seen || []).some(value =>
      value.caseId === item.caseId && value.version === item.version && (value.company || '') === (item.company || '')));
  }
  function acceptedList(accepted, expected) {
    return accepted.length === expected.length && expected.every(entry => accepted.some(saved => containsSnapshot(saved, entry)));
  }
  function key(message, termId, context = captureContext()) {
    return JSON.stringify([context.identity, context.caseId, message.version,
      message.request_id || message.created_at || message.text, termId]);
  }
  const status = (code, message) => ({status:code,message});
  const STATES = {
    saving: status('saving','正在保存…'),
    local: status('local','已保存到此浏览器'),
    synced: status('synced','已保存并同步到账号'),
    sync_failed: status('sync_failed','已保存到此浏览器，账号同步未完成；可重试'),
    conflict: status('conflict','知识库已有不同解释，已保留原收藏，未覆盖'),
    failed: status('failed','未能保存，请检查浏览器存储后重试'),
    corrupt: status('corrupt','知识库数据异常，未覆盖现有内容'),
    owner: status('owner','知识库身份尚未同步，请重新打开知识库后再试'),
    invalid: status('invalid','这条解释不完整或超出收藏长度限制，未保存'),
    changed: status('changed','页面或登录身份已变化，未继续保存'),
    limit: status('limit','知识库或来源记录已达上限，未覆盖现有收藏'),
    exists: status('exists','此解释已在知识库中'),
  };
  function refresh() { try { dep('refresh')(); } catch { /* UI updates do not change persistence outcome. */ } }
  function notify(message) { try { dep('notify')(message); } catch { /* Never reject an otherwise handled storage failure. */ } }
  function feedback(message, termId, context, result) {
    results.set(key(message, termId, context), result);
    refresh();
    return result;
  }
  function mergeEntry(list, entry) {
    const old = list.find(value => value.id === entry.id);
    if (!old) {
      if (list.length >= 500) throw new Error('limit');
      return {list:[entry,...list],existed:false,changed:true};
    }
    if (!sameSnapshot(old, entry)) throw new Error('conflict');
    const seen = old.seen || [], here = entry.seen[0];
    if (seen.some(value => value.caseId === here.caseId && value.version === here.version))
      return {list,existed:true,changed:false};
    if (seen.length >= 50) throw new Error('limit');
    return {list:list.map(value => value === old ? {...old,seen:[...seen,here]} : value),existed:true,changed:true};
  }
  function mergeRemote(local, remote, removed = []) {
    // The server copy prevents a new save from erasing another device's terms.
    // Differing explanations must be resolved explicitly, not last-write-wins.
    const out = remote.filter(entry => !removed.includes(entry.id));
    for (const entry of local) {
      const old = out.find(value => value.id === entry.id);
      if (!old) out.push(entry);
      else if (!sameSnapshot(old, entry)) throw new Error('conflict');
      else {
        const seen = [...(old.seen || [])];
        for (const item of entry.seen || []) if (!seen.some(x => x.caseId === item.caseId && x.version === item.version)) seen.push(item);
        if (seen.length > 50) throw new Error('limit');
        out[out.indexOf(old)] = {...old,seen};
      }
    }
    return checkedList(out);
  }
  async function save(message, termId, context) {
    if (!active(context)) return feedback(message, termId, context, STATES.changed);
    let wrote = false;
    const controller = new AbortController();
    controllers.add(controller);
    try {
      const matches = candidates(message).filter(term => term?.id === termId);
      if (matches.length !== 1) throw new Error('invalid');
      const entry = snapshot(message, matches[0]);
      let list = read(context);
      // Detect local conflicts before any account request or write.
      mergeEntry(list, entry);
      dep('beforeWrite')();
      if (context.account) {
        const remote = checkedList(await dep('api')('/api/me/library', {headers:accountHeaders(context),signal:controller.signal,timeoutMs:15000}));
        if (!active(context)) return feedback(message, termId, context, STATES.changed);
        const latest = read(context), removedDuringRead = list.filter(old => !latest.some(entry => entry.id === old.id)).map(entry => entry.id);
        list = mergeRemote(latest, remote, [...deleted(context),...removedDuringRead]);
      }
      const merged = mergeEntry(list, entry);
      if (!active(context)) return feedback(message, termId, context, STATES.changed);
      if (!context.account && merged.existed && !merged.changed) return feedback(message, termId, context, STATES.exists);
      if (context.account && !dep('writePending')(context.email, true)) throw new Error('failed');
      if (!(context.account ? installLocal(merged.list, context) : dep('write')(merged.list, false))) throw new Error('failed');
      wrote = true;
      if (!context.account) return feedback(message, termId, context, merged.existed ? STATES.exists : STATES.local);
      // Do not claim account sync until the server accepted this exact snapshot.
      const accepted = checkedList(await dep('api')('/api/me/library', {
        method:'PUT',body:merged.list,headers:accountHeaders(context),signal:controller.signal,timeoutMs:15000}));
      if (!active(context)) return feedback(message, termId, context, STATES.changed);
      const saved = accepted.find(item => item.id === entry.id);
      if (!saved || !containsSnapshot(saved, entry) || !acceptedList(accepted, merged.list)) throw new Error('sync_failed');
      clearPendingIfUnchanged(context, merged.list);
      return feedback(message, termId, context, STATES.synced);
    } catch (error) {
      const outcome = !active(context) ? STATES.changed : wrote && context.account ? STATES.sync_failed
        : STATES[error.message] || (error instanceof SyntaxError ? STATES.corrupt : STATES.failed);
      return feedback(message, termId, context, outcome);
    } finally { controllers.delete(controller); }
  }
  function handle(index, termId) {
    const message = state().case?.chat?.[index], context = captureContext();
    if (!message || typeof termId !== 'string' || !candidates(message).some(term => term?.id === termId)) return Promise.resolve(STATES.invalid);
    const id = key(message, termId, context);
    if (pending.has(id)) return pending.get(id);
    feedback(message, termId, context, STATES.saving);
    const result = runExclusive(() => save(message, termId, context)).finally(() => pending.delete(id));
    pending.set(id, result);
    return result;
  }
  async function receive(reply, context) {
    if (!context || context.autoEligible !== true || !context.requestId || reply?.request_id !== context.requestId
        || !active(context) || reply.version !== context.version || reply.answer_kind !== 'library_action'
        || reply.library_action?.auto_save !== true || reply.library_action.source_version !== reply.version) return [];
    const requestKey = JSON.stringify([context.identity, context.caseId, context.requestId]);
    if (received.has(requestKey)) return [];
    // Mark before awaiting so replayed responses cannot execute twice.
    received.add(requestKey);
    const found = state().case.chat.findIndex(message => message.role === 'assistant' && message.request_id === reply.request_id
      && message.version === reply.version);
    if (found < 0) return [];
    const outcomes = [];
    for (const term of candidates(reply)) {
      if (!active(context)) break;
      outcomes.push(await handle(found, term.id));
    }
    return outcomes;
  }
  function html(message, index) {
    const terms = candidates(message);
    if (!terms.length) return '';
    const context = captureContext();
    let list, readFailure;
    try { list = read(context); } catch (error) { readFailure = STATES[error.message] || STATES.corrupt; }
    const rows = terms.map(term => {
      let result = results.get(key(message, term?.id, context));
      try {
        const entry = snapshot(message, term), existing = list?.find(value => value.id === entry.id);
        if (existing && !sameSnapshot(existing, entry)) result = STATES.conflict;
        else if (existing && !result) result = STATES.exists;
        else if (!existing && ['synced','local','exists','sync_failed','conflict'].includes(result?.status)) result = null;
      } catch { result = STATES.invalid; }
      result = readFailure || result;
      const locked = ['saving','synced','local','exists','conflict','invalid','corrupt','owner'].includes(result?.status);
      const label = result?.status === 'sync_failed' ? '重试同步' : result?.status === 'saving' ? '正在保存…'
        : ['synced','local','exists'].includes(result?.status) ? '已收藏' : '收藏到知识库';
      return `<div class="chat-library-term"><span>${escape(term?.term)}</span> <button type="button" class="linkish" data-act="chat-lib-save" data-index="${escape(index)}" data-term="${escape(term?.id)}"${locked ? ' disabled' : ''}>${label}</button>${result ? `<p class="small muted" role="status">${escape(result.message)}</p>` : ''}</div>`;
    }).join('');
    return `<div class="chat-library-actions">${rows}<a class="linkish" href="#/library">查看知识库 ↗</a></div>`;
  }
  function syncLegacy() {
    const context = captureContext();
    if (!context.account) return Promise.resolve(false);
    return runExclusive(async () => {
      if (!active(context, false)) return false;
      const list = read(context), controller = new AbortController();
      controllers.add(controller);
      try {
        dep('beforeWrite')();
        if (!dep('writePending')(context.email, true)) throw new Error('failed');
        const accepted = checkedList(await dep('api')('/api/me/library', {method:'PUT',body:list,
          headers:accountHeaders(context),signal:controller.signal,timeoutMs:15000}));
        if (!active(context, false)) return false;
        if (!acceptedList(accepted, list)) throw new Error('sync_failed');
        clearPendingIfUnchanged(context, list);
        return true;
      } finally { controllers.delete(controller); }
    }).catch(() => { if (active(context, false)) notify('知识库尚未同步到账号，本地收藏已保留，可稍后重试'); return false; });
  }
  function syncInitial() {
    const context = captureContext();
    if (!context.account || !active(context, false)) return Promise.resolve(false);
    return runExclusive(async () => {
      if (!active(context, false)) return false;
      const controller = new AbortController();
      controllers.add(controller);
      try {
        dep('beforeWrite')();
        const remote = checkedList(await dep('api')('/api/me/library', {
          headers:accountHeaders(context),signal:controller.signal,timeoutMs:15000}));
        if (!active(context, false)) return false;
        const owner = dep('readOwner')(), pendingLocal = dep('readPending')(context.email);
        let list = remote;
        if (!owner || (owner === context.email && pendingLocal)) list = mergeRemote(read(context), remote, deleted(context));
        const changed = JSON.stringify(list) !== JSON.stringify(remote);
        if (changed && !dep('writePending')(context.email, true)) throw new Error('failed');
        if (!installLocal(list, context)) throw new Error('failed');
        if (changed) {
          const accepted = checkedList(await dep('api')('/api/me/library', {method:'PUT',body:list,
            headers:accountHeaders(context),signal:controller.signal,timeoutMs:15000}));
          if (!active(context, false)) return false;
          if (!acceptedList(accepted, list)) throw new Error('sync_failed');
        }
        if (!active(context, false)) return false;
        clearPendingIfUnchanged(context, list);
        return true;
      } finally { controllers.delete(controller); }
    }).catch(() => { if (active(context, false)) notify('知识库同步未完成，未将其他账号的收藏并入；请检查存储或稍后重试'); return false; });
  }
  function hasPending() {
    const context = captureContext();
    if (!context.account) return false;
    try { return dep('readPending')(context.email); } catch { return true; }
  }
  root.LibraryActions = Object.freeze({configure:options => { injected = {...injected,...options}; },
    captureContext, invalidate, runExclusive, html, handle, receive, syncLegacy, syncInitial, markPending, hasPending, recordChange});
})(globalThis);
