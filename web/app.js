/* 企er 前端：原生 JS，不打包。契约以 backend/app/models.py 为准。
 *
 * 功能导航：查企（研究室首页 /）、案卷（#/cases）、资料库（#/library）、我的（#/me）、使用说明（#/guide）。
 * 报告不占分区，它属于案卷：#/case/<id> 最新版报告；#/case/<id>/v/<n> 第 n 版。
 * 右侧一栏是小企（AI）。没开案卷时它只说明自己能答什么、不能答什么，不假装能答。
 * 报告页：一页结论在最上面；四个信号、宣称 vs 记录、该问对方的、原始数据放在下面的标签页里，按需展开。
 * 页面里所有可点的东西都用 data-act 声明，统一在 onClick 里分发。
 * 条目 id：A1 说法、M1 缺项、risk.bank_list 信号条目、Q1 问题、R1 原始数据。R 开头的打开原始数据，其余跳到所在标签页里那一条。
 * 报告条目的锚点用 data-item；按钮要去的目标用 data-id，两者不要混用。
 * 用户评价按公司存（/api/reviews），不属于某一版报告；"放进报告"才会出一版新的，把当时的评价记成一条原始数据。
 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const KIND = { none: '没有数据', official: '官方记录', collected: '人工采集', commercial: '商业数据', regulation: '法规', parameter: '参数',
  demo: '演示·虚构', user_material: '用户材料', web: '网络公开', user_review: '用户评价' };
const COVERAGE = { found: '查到了', not_found: '查了没有', not_covered: '没查', failed: '查询失败' };
const STATUS = { bad: '需重点核实', warn: '要留意', miss: '缺应有记录', none: '未覆盖', ok: '暂未见异常' };
const FLAG = new Set(['bad', 'warn', 'miss']);   // 要看的；ok、none 默认折叠
const CHANGE = { new_concern: '新疑点', worse: '更严重', clarified: '疑点减轻', unchanged: '没变', added: '新增', removed: '这版没有了', updated: '事实更新', unavailable: '证据不足' };
const MODE = { model: '模型回答', replay: '离线回放', template: '模板回答', guard: '已拦截' };
// 判断页先收起来（地址带 ?judg=1 才显示）：它的逐条比对在"只改需求"时也会报"需要重新核实"，
// 和"事实没变"打架；记录里查到的官方文书也不该一键撤掉。后端照常存判断，修好再放出来。
const SHOW_JUDGMENTS = /[?&]judg=1/.test(location.search);
const TABS = { judgments: '判断', changes: '变化', signals: '四个信号', claims: '宣称 vs 记录', questions: '该问对方的', raw: '原始数据', reviews: '评价' };
// 用户评价只作参考时（不够集中），既不算"没问题"，也不算"没查"
const isRef = i => i.source === 'user_reviews' && !FLAG.has(i.status);
// status 是 none 时为什么不知道（后端 models.Gap）。没查成和没查分开说，用户才知道该重查、该补材料，还是本来就不适用
const GAP = { failed: '没查成', not_found: '查无记录', not_covered: '没查', needs_input: '待补材料', not_applicable: '不适用',
  undisclosed: '未公开', partial: '部分明细', reference: '只作参考', listed: '已在上面列出' };
const QUIET_GAPS = new Set(['listed', 'reference', 'not_applicable']);   // 不算缺口：已在别处列出、只作参考、不适用
const gapOf = i => (i.status === 'none' ? (i.gap || 'not_covered') : null);
const isOpen = i => i.status === 'none' && !QUIET_GAPS.has(gapOf(i));   // 还缺的：没查成、没查、待补材料、未公开……
function pendingNote(list) {   // "2 项没查成、1 项待补材料"，没查成排最前
  const n = {};
  for (const i of list) if (isOpen(i)) n[gapOf(i)] = (n[gapOf(i)] || 0) + 1;
  return Object.entries(n).sort(([a], [b]) => (b === 'failed') - (a === 'failed')).map(([g, c]) => `${c} 项${GAP[g]}`).join('、');
}
const stLabel = i => (isRef(i) ? '只作参考' : (i.status === 'none' && GAP[i.gap]) || STATUS[i.status] || '');
// 与研究室首页的功能列表保持相同顺序。
const NAV = [['check', '企业', '输入公司全称和一句需求，出新报告'], ['cases', '案卷', '查过的公司和它们的每一版'], ['library', '知识库', '收藏的名词，回头复习'], ['me', '我的', '个人主页'], ['guide', '使用说明', '使用方法、服务与资料覆盖']];
const QI_SUG = ['它有没有资格收这笔钱？', '还有哪些没查到？', '我该先问对方什么？'];
const SUP_KIND = {
  material: { label: '新材料', help: '宣传单、合同、聊天记录的文字。可以上传图片、PDF、Word，读出来的文字会填进下面，你可以改。' },
  reply: { label: '对方的回复', help: '对方怎么回答你的问题。会记为"对方说的，未核实"，只用来对照，不当作事实。' },
  need: { label: '改需求', help: '换一句需求。事实不会变，变的是看的重点和措辞；变化清单会写明这一点。' },
};
// 名词解释来自后端的固定词表（/api/glossary，backend/app/glossary.json），不在前端写死
const S = {
  health: null, scenarios: [], sources: [], demos: [], cases: [],
  terms: [], termById: new Map(), termByName: new Map(), termRe: null,
  case: null, viewNo: null, selected: new Set(), busy: false, busyCaseId: null, audience: 'family', opCache: {},
  tab: 'signals', openRest: new Set(), showText: false,
  reviews: null, rvStars: 0, rvRel: null,   // 这家公司现在的评价（不随版本变）；写评价表单里选的星级和身份
  form: { userScenario: null, showScen: false, dirty: {}, intake: null },
};

// ---------- 接口 ----------

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {...(opts.headers || {})}, credentials: 'same-origin' };
  if (opts.body instanceof FormData) init.body = opts.body;
  else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  const reading = init.method === 'GET';
  const timeoutMs = opts.timeoutMs ?? (reading ? 12000 : 0);
  const controller = timeoutMs ? new AbortController() : null;
  const relay = () => controller?.abort(opts.signal?.reason || 'cancelled');
  if (opts.signal?.aborted) relay();
  else opts.signal?.addEventListener('abort', relay, {once:true});
  init.signal = controller?.signal || opts.signal;
  const timer = controller ? setTimeout(() => controller.abort('timeout'), timeoutMs) : null;
  try {
    let r;
    try { r = await fetch(path, init); } catch (e) {
      if (init.signal?.aborted) throw e;
      throw new Error('暂时连接不上服务，请检查网络后重试');
    }
    let data = null;
    try { data = await r.json(); } catch (e) { if (init.signal?.aborted) throw e; }
    if (!r.ok) {
      const d = data && data.detail;
      const error = new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('；') : `请求失败（${r.status}）`);
      error.status = r.status; throw error;
    }
    if (data == null) throw new Error('后端返回的内容格式不正确，请稍后恢复结果');
    return data;
  } catch (e) {
    if (init.signal?.aborted && reading) throw new Error(init.signal.reason === 'timeout'
      ? '读取时间较长，请重试。已保存的案卷仍会保留。' : '已取消这次读取');
    if (init.signal?.aborted) throw new Error(init.signal.reason === 'timeout'
      ? '等待时间较长，已停止等待。后台可能仍在处理，可以恢复回答，无需重复提交。'
      : '已停止等待。后台可能仍在处理，可以稍后恢复回答。');
    throw e;
  } finally {
    if (timer != null) clearTimeout(timer);
    opts.signal?.removeEventListener('abort', relay);
  }
}

// ---------- 小工具 ----------

function toast(msg, bad = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast on' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.className = 'toast'; }, bad ? 5200 : 2800);
}
const fmtTime = s => (s ? String(s).replace('T', ' ').slice(0, 16) : '');
function fmtMoney(n) {
  if (n == null || isNaN(n)) return '';
  if (n >= 1e8) return `${+(n / 1e8).toFixed(2)} 亿`;
  if (n >= 1e4) return `${+(n / 1e4).toFixed(2)} 万`;
  return `${n} 元`;
}
function parseAmount(s) {
  const m = String(s || '').replace(/[,，\s]/g, '').match(/^([\d.]+)(亿|万|w|W|千|元)?$/);
  if (!m) return null;
  const n = parseFloat(m[1]) * ({ 亿: 1e8, 万: 1e4, w: 1e4, W: 1e4, 千: 1e3 }[m[2]] || 1);
  return n > 0 ? n : null;
}
const ver = () => S.case && (S.case.versions.find(v => v.no === S.viewNo) || S.case.versions[S.case.versions.length - 1]);
const rawById = id => S.case && S.case.raw.find(r => r.id === id);
const srcOf = id => (ver()?.sources || S.case?.sources || {})[id] || S.sources.find(s => s.id === id);
// 没查到的记录（not_covered）会带上演示数据源的类型；只有真查到了演示数据，才算演示案例
const rawKind = r => (r.coverage === 'not_covered' && r.kind === 'demo' ? 'none' : r.kind);
const isDemoCase = () => S.case && S.case.raw.some(r => r.kind === 'demo' && r.coverage === 'found');
function parseRef(ref, version) {
  const m = String(ref).match(/^v:([1-9]\d*):(assertion|missing|question|signal):(.+)$/);
  if (!m) return { id: ref, version: version == null ? null : Number(version) };
  return { id: m[2] === 'signal' ? m[3].replace(':', '.') : m[3], version: Number(m[1]) };
}
const isId = s => /^(R\d+|A\d+|M\d+|Q\d+|term\.[a-z0-9_]+|[a-z]+\.[a-z0-9_]+)$/.test(parseRef(s).id);
function chatRef(id, version) {
  if (/^A\d+$/.test(id)) return `v:${version}:assertion:${id}`;
  if (/^M\d+$/.test(id)) return `v:${version}:missing:${id}`;
  if (/^Q\d+$/.test(id)) return `v:${version}:question:${id}`;
  if (/^[a-z]+\.[a-z0-9_]+$/.test(id)) return `v:${version}:signal:${id.replace('.', ':')}`;
  return id;
}
const versionRaws = v => v.raw_ids.map(rawById).filter(Boolean);

// 名词标注：在一段文字里认出名词，点开看解释。seen 让同一块内容里每个词只标第一次，免得满屏虚线。
// 报告页用这一版报告生成时整理好的名词（v.terms，含模型补的"AI 解释"）；旧案卷没有，就用固定词表
function setGlossary(terms) {
  S.terms = terms || [];
  S.termById = new Map(S.terms.map(t => [t.id, t]));
  useTerms(S.terms);
}
function useTerms(list) {
  S.vTermById = new Map(list.map(t => [t.id, t]));
  S.termByName = new Map();
  for (const t of list) for (const n of [t.term, ...(t.aliases || [])]) if (!S.termByName.has(n)) S.termByName.set(n, t);
  const names = [...S.termByName.keys()].sort((a, b) => b.length - a.length)   // 长的优先："失信被执行人"不会被认成"被执行人"
    .map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  S.termRe = names.length ? new RegExp(names.join('|'), 'g') : null;
}
const termOf = id => (S.vTermById && S.vTermById.get(id)) || S.termById.get(id);
function termText(text, seen = new Set()) {
  text = String(text ?? '');
  if (!S.termRe) return esc(text);
  let out = '', last = 0;
  for (const m of text.matchAll(S.termRe)) {
    const t = S.termByName.get(m[0]);
    if (!t || seen.has(t.id)) continue;
    seen.add(t.id);
    out += esc(text.slice(last, m.index)) + `<button type="button" class="term" data-act="term" data-term="${esc(t.id)}">${esc(m[0])}</button>`;
    last = m.index + m[0].length;
  }
  return out + esc(text.slice(last));
}
const termify = label => termText(label);
const termBasis = t => { const src = t.basis && srcOf(t.basis); return (src ? src.name : t.law) || ''; };
function termPopHtml(t) {
  const basis = termBasis(t);
  const note = t.origin === 'model' ? 'AI 解释：词表里没有这个词，报告生成时由模型补充，没有经过人工核对。' : (basis ? `依据：${basis}` : '');
  return `<h5>${esc(t.term)}</h5><p>${esc(t.plain)}</p>${t.why ? `<p class="pw">${esc(t.why)}</p>` : ''}${note ? `<p class="pb">${esc(note)}</p>` : ''}${libBtn(t.id)}`;
}
function termPop(el, id) {
  const t = termOf(id);
  if (!t) return;
  libNote(id);
  popAt(el, termPopHtml(t));
}

// ---------- 知识库：看不懂的名词收藏起来，回头复习 ----------
// 只存在这个浏览器里（和案卷一个口径）。存的是收藏当时的解释快照：AI 词条只在那一版报告里有，
// 固定词表以后改了措辞，复习时看到的也还是当时那一版。seen 记在哪几份报告里碰到过，按案卷去重。
const LIB_KEY = 'xray.library';
function libRead() {
  try { const list = JSON.parse(localStorage.getItem(LIB_KEY) || '[]'); return Array.isArray(list) ? list : []; }
  catch { return []; }
}
function libWrite(list, push = true) {
  try { localStorage.setItem(LIB_KEY, JSON.stringify(list)); } catch { return false; }
  if (push) libPush();
  return true;
}
// 登录了就以账号里的为准：每次改动推上去；本地这份是缓存。
// LIB_OWNER 记着本地这份属于哪个账号——没有记号的是未登录时收的，第一次登录时并进账号。
const LIB_OWNER = 'xray.library.owner';
function libPush() {
  if (!S.session?.account) return;
  clearTimeout(libPush.t);
  libPush.t = setTimeout(() => api('/api/me/library', {method: 'PUT', body: libRead()})
    .catch(() => toast('知识库没同步到账号，下次打开会再试', true)), 400);
}
function libMerge(a, b) {
  const byId = new Map();
  for (const e of [...a, ...b]) {
    const old = byId.get(e.id);
    if (!old) { byId.set(e.id, e); continue; }
    const [keep, other] = (e.savedAt || '') > (old.savedAt || '') ? [e, old] : [old, e];
    byId.set(e.id, {...keep, seen: [...(other.seen || []).filter(s => !(keep.seen || []).some(k => k.caseId === s.caseId)), ...(keep.seen || [])]});
  }
  return [...byId.values()].sort((x, y) => (y.savedAt || '').localeCompare(x.savedAt || ''));
}
async function libSync() {
  const email = S.session?.account?.email;
  if (!email) return;
  let remote;
  try { remote = await api('/api/me/library'); } catch { return; }
  let owner = null;
  try { owner = localStorage.getItem(LIB_OWNER); } catch {}
  const list = owner ? remote : libMerge(libRead(), remote);   // 别的账号留下的缓存不并
  libWrite(list, false);
  try { localStorage.setItem(LIB_OWNER, email); } catch {}
  if (JSON.stringify(list) !== JSON.stringify(remote)) libPush();
  if ($('#libList')) $('#libList').innerHTML = libraryHtml(libRead());
}
function libForget() {
  try { localStorage.removeItem(LIB_KEY); localStorage.removeItem(LIB_OWNER); } catch {}
}
const libHas = id => libRead().some(e => e.id === id);
// 正在看的那份报告；不在案卷页（比如「我的」里的词表）就不记
function libHere() {
  if (!S.case || !/^#\/case\//.test(location.hash)) return null;
  return { caseId: S.case.id, version: ver()?.no ?? null, company: S.case.case.company_name };
}
const libSeen = (seen, here) => here ? [...seen.filter(s => s.caseId !== here.caseId), here] : seen;
// 收藏或取消；返回 true 已收藏、false 已取消、null 存不了
function libToggle(id) {
  const list = libRead();
  if (list.some(e => e.id === id)) return libWrite(list.filter(e => e.id !== id)) ? false : null;
  const t = termOf(id);
  if (!t) return null;
  const entry = { id: t.id, term: t.term, plain: t.plain, why: t.why || '', basis: termBasis(t), origin: t.origin || '',
    savedAt: new Date().toISOString(), seen: libSeen([], libHere()) };
  return libWrite([entry, ...list]) ? true : null;
}
// 已收藏的词在另一份报告里又碰到了：把这份报告记进 seen
function libNote(id) {
  const here = libHere(), list = libRead(), e = here && list.find(x => x.id === id);
  if (!e || e.seen.some(s => s.caseId === here.caseId && s.version === here.version)) return;
  e.seen = libSeen(e.seen || [], here);
  libWrite(list);
}
const libBtn = id => { const on = libHas(id); return `<button type="button" class="lib-tog" data-act="lib-toggle" data-term="${esc(id)}" aria-pressed="${on}">${on ? '★ 已收藏' : '☆ 收藏复习'}</button>`; };
// Collection controls affect only the current view; saved records remain untouched.
const collectionView = {caseQuery:'',caseFilter:'all',caseSort:'newest',libraryQuery:'',libraryFilter:'all',study:false};
function collectionMatches(value, query) {
  const words = String(query || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const haystack = String(value || '').toLocaleLowerCase();
  return words.every(word => haystack.includes(word));
}
function visibleTerms(list) {
  return list.filter(e => collectionMatches([e.term,e.plain,...(e.seen || []).map(x => x.company)].join(' '), collectionView.libraryQuery))
    .filter(e => collectionView.libraryFilter === 'all' || (collectionView.libraryFilter === 'report' ? (e.seen || []).length > 0 : !(e.seen || []).length));
}
function libraryCards(list) {
  if (!list.length) return '<div class="collection-empty"><span class="collection-empty-mark">⌕</span><h3>没有找到匹配的名词</h3><p>试试简短的关键词，或查看全部收藏。</p><button class="collection-button" data-act="library-reset">清除筛选</button></div>';
  return list.map((e,i) => `<article class="term-file">
    <div class="term-index"><span>名词索引 <b>${String(i+1).padStart(2,'0')}</b></span><span class="term-bookmark" aria-hidden="true">${collectionIcon('bookmark')}</span></div>
    <div class="term-sheet"><div class="term-heading"><h3>${esc(e.term)}</h3>${e.origin === 'model' ? '<span class="lib-ai">AI 解释·未经人工核对</span>' : '<span class="term-type">名词解释</span>'}</div>
    <details class="term-reading"${collectionView.study ? '' : ' open'}><summary><span class="term-reading-closed">想好了吗？展开解释</span><span class="term-reading-open">一句话看懂</span><span class="term-read-symbol" aria-hidden="true">＋</span></summary><p class="term-plain">${esc(e.plain)}</p>
    ${e.why || (e.origin !== 'model' && e.basis) ? `<details class="term-context"><summary>继续看 · ${e.why ? '为什么要留意' : '解释依据'} <span>↗</span></summary><div>${e.why ? `<p>${esc(e.why)}</p>` : ''}${e.origin !== 'model' && e.basis ? `<p class="lib-basis">依据：${esc(e.basis)}</p>` : ''}</div></details>` : ''}</details>
    <div class="term-origins"><span>${collectionIcon('file')} ${(e.seen || []).length ? '在这些报告里遇见' : '从词表里收藏'}</span>${(e.seen || []).map(x => `<a href="#/case/${esc(encodeURIComponent(x.caseId))}${x.version == null ? '' : `/v/${esc(x.version)}`}"><span>${esc(x.company)}</span><small>${x.version == null ? '查看案卷' : `第 ${esc(x.version)} 版`} ↗</small></a>`).join('')}</div>
    <div class="term-bottom"><span>${e.savedAt ? `${esc(String(e.savedAt).slice(0,10))} 收藏` : '已收藏'}</span><button type="button" class="term-remove" data-act="lib-remove" data-term="${esc(e.id)}">移出</button></div></div>
  </article>`).join('');
}
function libraryHtml(list) {
  const where = S.session?.account ? `已同步到账号 ${esc(S.session.account.email)}，换设备登录也能看到。` : '收藏保存在此浏览器；登录后可以同步到账号。清除浏览器数据会丢失未同步的收藏。';
  if (!list.length) return `<div class="collection-empty library-empty">${collectionArt('library')}<h3>把没看懂的词，收进自己的知识库。</h3><p>在报告里点开带虚线的名词，再点「☆ 收藏复习」。<br>解释、依据和遇到它的报告，会一起留在这里。</p><a class="collection-button solid" href="#/cases">去看案卷 ↗</a></div><p class="collection-storage">${where}</p>`;
  const rows = visibleTerms(list);
  return `<div class="collection-toolbar"><label class="collection-search">${collectionIcon('search')}<input id="librarySearch" type="search" placeholder="搜索名词、解释或公司" aria-label="搜索收藏的名词" value="${esc(collectionView.libraryQuery)}" autocomplete="off"></label><button class="collection-button study-toggle" data-act="library-study" aria-pressed="${collectionView.study}">${collectionIcon('cards')}<span>${collectionView.study ? '结束复习' : '复习一下'}</span></button></div>
    <div class="collection-list-label"><div class="collection-filters" role="group" aria-label="名词来源筛选">${[['all','全部收藏'],['report','来自报告'],['glossary','词表收藏']].map(([key,label]) => `<button data-act="library-filter" data-filter="${key}" aria-pressed="${collectionView.libraryFilter === key}">${label}</button>`).join('')}</div><span id="libraryMatches" role="status">显示 ${rows.length} / ${list.length} 个词</span></div>
    <p class="study-hint" id="studyHint"${collectionView.study ? '' : ' hidden'}>先想想这个词是什么意思，再展开卡片核对。解释和出处都在原处。</p>
    <div class="knowledge-cards" id="knowledgeCards">${libraryCards(rows)}</div>
    <p class="collection-storage">共 ${list.length} 个词。${where}</p>`;
}
function refreshLibraryCards() {
  const list = libRead(), rows = visibleTerms(list);
  if ($('#knowledgeCards')) $('#knowledgeCards').innerHTML = libraryCards(rows);
  if ($('#libraryMatches')) $('#libraryMatches').textContent = `显示 ${rows.length} / ${list.length} 个词`;
}
const askBtn = (id, label = '问') => `<button type="button" class="ask" data-act="sel" data-id="${esc(id)}"${label !== '问' ? ` data-idle-label="${esc(label)}"` : ''} aria-pressed="${S.selected.has(id)}" title="选中这一条，去问小企">${S.selected.has(id) ? '已选' : esc(label)}</button>`;
// Keep raw record IDs for navigation, but use readable labels in the review UI.
const hideRecordIds = () => typeof isDesignReview === 'function' && isDesignReview();
const recordRefText = ref => hideRecordIds() && /^R\d+$/.test(ref) ? '查看出处' : ref;
// Readable name for a cited id (record title, signal item, claim kind); the id itself stays in data-id.
function refLabel(id, version = null) {
  const target = parseRef(id, version), rid = target.id;
  if (!hideRecordIds()) return rid;
  const cut = s => {   // 去掉末尾的括号说明（"（共 5 条）"），太长再截断
    s = String(s || '').trim().replace(/\s*[（(][^（）()]*[）)]$/, '') || String(s || '').trim();
    return s.length > 14 ? `${s.slice(0, 13).replace(/[\s（(·、，,：:]+$/, '')}…` : s;
  };
  if (/^R\d+$/.test(rid)) { const r = rawById(rid); return r ? cut(r.title) : '查看出处'; }
  const v = (target.version != null && S.case?.versions.find(x => x.no === target.version)) || ver();
  if (!v) return '查看出处';
  if (/^A\d+$/.test(rid)) { const a = v.assertions.find(x => x.id === rid); return a ? `它说的·${a.kind_label}` : '它说的'; }
  if (/^M\d+$/.test(rid)) { const m = v.missing.find(x => x.id === rid); return m ? `该写没写·${cut(m.text)}` : '该写没写'; }
  if (/^Q\d+$/.test(rid)) { const i = v.questions.findIndex(x => x.id === rid); return i >= 0 ? `第 ${i + 1} 个问题` : '该问的问题'; }
  const [sk, ik] = rid.split('.');
  const it = v.signals.find(s => s.key === sk)?.items.find(x => x.key === ik);
  return it ? cut(it.label) : '查看出处';
}
const goLink = (id, version = null, label = null) => {
  const target = parseRef(id, version);
  const terms = target.version == null ? S.terms : (S.case?.versions.find(v => v.no === target.version)?.terms || S.terms);
  const t = target.id.startsWith('term.') && terms.find(t => t.id === target.id.slice(5));
  return `<button type="button" class="cite${t ? ' term-cite' : ''}" data-act="goto" data-id="${esc(id)}"${target.version == null ? '' : ` data-version="${target.version}"`}>${esc(label || (t ? `名词·${t.term}` : refLabel(id, version)))}</button>`;
};
const refLinks = refs => (refs || []).map(r => `<button type="button" class="rf" data-act="goto" data-id="${esc(r)}">${esc(refLabel(r))}</button>`).join('');
const selCls = id => (S.selected.has(id) ? ' is-sel' : '');

// Source metadata opens the original record; internal record IDs stay in data attributes.
function srcLink(sourceId, ref, separateAction = false) {
  const s = srcOf(sourceId), r = ref && rawById(ref);
  const kind = (r && rawKind(r)) || (s && s.kind) || '';
  const date = kind === 'none' ? null : (r && r.as_of) || (s && s.as_of);
  const title = s ? s.name : sourceId;
  const metadata = `<span class="k-${esc(kind)}">${esc(KIND[kind] || '来源')}</span>${date ? ` · ${esc(date)}` : ''}`;
  const inner = separateAction
    ? `<span class="signal-source-meta">${metadata}</span><span class="signal-source-action">${ref ? '查看出处 ↗' : '来源说明 ↗'}</span>`
    : `${metadata}${ref ? hideRecordIds() ? ' · 查看出处 ↗' : ` · <b>${esc(ref)}</b>` : ''}`;
  return ref
    ? `<button type="button" class="src" data-act="raw" data-ref="${esc(ref)}" title="${esc(title)} · 点开看原始数据">${inner}</button>`
    : `<button type="button" class="src" data-act="src" data-src="${esc(sourceId)}" title="${esc(title)}">${inner}</button>`;
}

function changeMap(v) {
  const m = {};
  if (v && v.no > 1) for (const c of v.changes) if (c.kind !== 'unchanged') m[c.target] = c.kind;
  return m;
}
const chgTag = (id, cm) => (cm[id] ? `<span class="chg-tag ${cm[id]}" title="和上一版比">${CHANGE[cm[id]]}</span>` : '');

// ---------- 顶栏 ----------

function renderTop() {
  const onCase = S.case && location.hash.startsWith('#/case/');
  const sec = onCase ? 'cases' : /^#\/reset\b/.test(location.hash) ? 'me' : (location.hash.match(/^#\/(check|cases|library|me|guide)\/?$/) || [])[1] || 'check';
  $('#shellNav').innerHTML = NAV.map(([k, label, hint]) =>
    `<button type="button" class="snav-b" data-act="go" data-sec="${k}" aria-current="${k === sec}" title="${esc(hint)}">${label}</button>`).join('');
  $('#caseStrip').innerHTML = onCase ? `<span title="${esc(S.case.case.company_name)}">${esc(S.case.case.company_name)}</span>` : sec === 'cases' ? '我的案卷' : '';
  const llm = S.health && S.health.llm;
  let b = '';
  if (llm) {
    if (!llm.configured || llm.mode === 'off') b += '<span class="tb off" title="没接模型：需求识别用关键词，小企用模板回答">未接模型</span>';
    else if (llm.mode === 'replay') b += '<span class="tb replay" title="断网演示：只用录好的模型响应">离线回放</span>';
    else b += `<span class="tb live" title="${esc(llm.model || '')}；本版来源与单次回答模式另行标注">模型服务已配置</span>`;
  }
  if (onCase && isDemoCase()) b += '<span class="tb demo" title="这家公司和它的记录都是编的，只用来演示">演示数据 · 公司为虚构</span>';
  $('#topBadges').innerHTML = b;
}

// ---------- 壳子：功能分区 + 小企栏 ----------

// 每个分区都长这样：左边是这一区的内容，右边一栏是小企。报告页用的也是这套结构（.case-layout），
// 所以窄屏下小企栏会像报告页那样收成右下角一个球，不用另写一套。
function shellHtml(main) {
  return `<div class="case-layout">
    <main class="report" id="report">${main}</main>
    <aside class="assist" id="assist" aria-label="小企（AI 栏）">${qibarHtml()}</aside>
  </div>
  ${qiLauncherHtml()}`;
}

// 小企栏：开着案卷就是问答，没开案卷就说清楚它现在答不了、以及它能答什么
function qibarHtml() {
  if (S.case && /^#\/case\//.test(location.hash)) return assistHtml();
  const llm = S.health && S.health.llm;
  const line = !llm ? '模型服务状态暂未读到，请刷新页面再试。'
    : llm.configured && llm.mode !== 'off' ? '理解你的顾虑，结合案卷核对事实。' : '模型暂不可用，提供基础核对建议。';
  return `<div class="as-head"><div class="as-heading"><h3>小企 <span class="qi-role">报告助手</span></h3><p class="small muted">${esc(line)}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="收起小企">×</button></div>
  <div class="as-body">
    <div class="qi-welcome">${qiSpriteHtml()}</div>
    <p class="qi-lede">先打开一份案卷。小企可以帮你理解资料、梳理顾虑和下一步；未核实的公司情况不会当作事实。</p>
    <p class="small muted">打开一份案卷后，可以这样问它：</p>
    <div class="chips">${QI_SUG.map(q => `<button type="button" class="chip" data-act="qi-nudge" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <ul class="qi-what">
      <li>关键企业事实有出处，能点开看原始记录和日期</li>
      <li>数据里没有的，它说没查到</li>
      <li>它不会改报告；新情况要点"加入案卷"才会重新判断</li>
      <li>它不给公司定性，也不打安全分</li>
    </ul>
    <div class="qi-go"><a class="btn sm" href="#/check">去查一家公司</a><a class="linkish small" href="#/cases">看案卷</a></div>
  </div>`;
}

// 官方名单那一行（查企页和我的页共用）
function listLine(h) {
  const SHORT = { nfra_insurance: '保险', csrc_futures: '期货', pbc_payment: '支付', amac_managers: '私募' };
  const lists = [];
  if (h?.licensed_count != null || h?.licensed_as_of) lists.push({ title: '银行业', count: h.licensed_count, as_of: h.licensed_as_of });
  for (const [key, list] of Object.entries(h?.official_lists || {})) {
    if (list) lists.push({ title: SHORT[key] || list.title || '官方名单', count: list.count, as_of: list.as_of });
  }
  if (!lists.length) return '官方名单资料暂未读到，请刷新页面再试。';
  return `可按名称核对的官方名单：${lists.map(l => `${esc(l.title)} ${Number.isFinite(l.count) && l.count >= 0 ? `${l.count.toLocaleString('zh-CN')} 家` : '数量暂未读到'}（${l.as_of ? `截至 ${esc(l.as_of)}` : '资料日期未提供'}）`).join('、')}。名单只反映其收录范围和标注日期，不代表对公司或产品的完整核验。`;
}

// ---------- 分区二：案卷 ----------

function archiveIcon(kind) {
  const paths = {
    file: 'M5 3h9l5 5v13H5V3ZM14 3v6h5M9 13h6M9 17h4',
    arrow: 'M6 18 18 6M6 6h12v12',
    chat: 'M4 5h16v12H9l-5 4V5ZM8 9h8M8 13h5',
  };
  return `<svg class="archive-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[kind] || paths.file}"/></svg>`;
}

function archiveAssistantHtml() {
  return `<div class="as-head"><div class="as-heading"><h3>小企 <span class="qi-role">报告助手</span></h3><p>理解你的顾虑，结合案卷核对事实。</p></div><button class="as-x" type="button" data-act="close-assist" aria-label="收起小企">×</button></div>
    <div class="as-body archive-assistant-body">
      <div class="archive-qi-welcome">${qiSpriteHtml()}<span>等你选一份案卷</span></div>
      <h2>接着上次，<br>一起把疑问弄清楚。</h2>
      <p class="archive-assistant-lede">打开左边的一份案卷，我就能结合对应报告，帮你理解记录、核对新材料。</p>
      <div class="archive-prompt-label">你可以从这些问题开始</div>
      <div class="chips archive-chips">${['为什么这一条需要留意？','新材料改变了哪些判断？','下一步该向对方确认什么？'].map(q => `<button class="chip" type="button" data-act="qi-nudge">${esc(q)}<span aria-hidden="true">↗</span></button>`).join('')}</div>
      <div class="archive-assistant-note">${archiveIcon('chat')}<p>关键事实可以回看出处。<br>还没核实的，会和已知信息分开说。</p></div>
    </div>
    <div class="archive-assistant-bottom"><span class="archive-status-dot"></span>尚未选择案卷 · 暂不读取具体材料</div>`;
}

function collectionIcon(kind) {
  const paths = {search:'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 6 6',file:'M5 3h10l4 4v14H5V3Zm10 0v5h4M9 12h6M9 16h4',bookmark:'M6 3h12v18l-6-4-6 4V3Z',cards:'M7 3h13v15H7V3ZM4 7H2v15h13v-2M11 8h5m-5 4h5',folder:'M3 6h7l3 3h8v12H3V6Z',arrow:'M4 12h15m-6-6 6 6-6 6'};
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[kind] || paths.file}"/></svg>`;
}
function collectionArt(kind) {
  return `<svg class="collection-art" viewBox="0 0 210 140" fill="none" aria-hidden="true"><path d="M22 114h168" stroke="#8b795a" opacity=".4"/><g class="collection-art-pages"><path d="m62 31 87-10 10 88-87 10Z" fill="#efe5cd" stroke="#b89a62"/><path d="M49 33h92v87H49Z" fill="#faf6e9" stroke="#bfa776"/><path d="M62 53h63M62 63h39M62 75h63M62 86h51" stroke="#b7a47a"/><path d="M106 33v30l10-7 10 7V33" fill="#9d7743"/></g>${kind === 'cases' ? '<path d="M25 76V58h41l12 14h101v54H25V76Z" fill="#d5bb87" stroke="#a58754"/><path d="M25 80h154v46H25Z" fill="#dec99f" stroke="#a58754"/><path d="M47 94h61v19H47Z" fill="#f7f0dd" stroke="#b59b6c"/><path d="M55 101h42m-42 6h29" stroke="#a18b68"/><circle cx="160" cy="104" r="6" fill="#233845" stroke="#b39966"/>' : '<path d="m127 99 45-64 8 6-45 64-11 7 3-13Z" fill="#223845" stroke="#b89960"/><path d="m127 99 8 6-11 7 3-13Z" fill="#d6bc85"/><path d="m166 44 8 6" stroke="#d6bc85"/>'}</svg>`;
}
function collectionHeader(kind) {
  const library = kind === 'library';
  return `<section class="collection-heading archive-heading"><div class="collection-heading-main"><div class="collection-kicker"><span>${library ? 'KNOWLEDGE INDEX' : 'CASE ARCHIVE'}</span><i></i>${library ? '知识库' : '企业研究档案'}</div><h1>${library ? '收藏的名词' : '查过的公司'}</h1><p>${library ? '把报告里遇到的陌生词，变成自己的理解。' : '从上次的疑问继续，每次核实都有迹可循。'}</p><div class="collection-header-actions"><a class="collection-button solid" href="${library ? '#/cases' : '/'}">${collectionIcon(library ? 'folder' : 'search')}${library ? '回到案卷' : '查一家公司'}</a><span>${library ? '解释 · 依据 · 对应报告' : '报告 · 补充材料 · 历次变化'}</span></div></div><div class="collection-header-art">${collectionArt(kind)}<span>${library ? '把理解留下来' : '你的私人档案'}</span></div></section>`;
}
function caseCollectionRows(cases) {
  return cases.filter(c => collectionMatches([c.company_name,c.need,c.scenario_label].join(' '),collectionView.caseQuery))
    .filter(c => collectionView.caseFilter !== 'multiple' || Number(c.versions) > 1)
    .sort((a,b) => collectionView.caseSort === 'oldest' ? String(a.created_at || '').localeCompare(String(b.created_at || '')) : String(b.created_at || '').localeCompare(String(a.created_at || '')));
}
function renderCaseCollection() {
  const all = S.cases || [], rows = caseCollectionRows(all);
  $('#caseCount').textContent = String(all.length).padStart(2,'0');
  $('#caseCompanies').textContent = String(new Set(all.map(c => c.company_name)).size).padStart(2,'0');
  $('#caseVersions').textContent = String(all.reduce((n,c) => n + (Number(c.versions) || 0),0)).padStart(2,'0');
  $('#caseMatches').textContent = `显示 ${rows.length} / ${all.length} 份案卷`;
  $('#caseList').innerHTML = rows.length ? rows.map((c,i) => caseRow(c,i)).join('') : all.length ? '<div class="collection-empty"><span class="collection-empty-mark">⌕</span><h3>没有找到匹配的案卷</h3><p>试试公司简称、关注事项，或查看全部案卷。</p><button class="collection-button" data-act="cases-reset">清除筛选</button></div>' : '<div class="collection-empty empty-case"><h3>还没有案卷</h3><p>查一家公司，报告会保存在这里。之后可以继续补材料、看变化。</p><a class="collection-button solid" href="/">去查一家公司 ↗</a></div>';
}
async function renderCases(request = routeRequest) {
  S.case = null; useTerms(S.terms); renderTop();
  document.body.classList.add('research-mode', 'cases-mode', 'collections-mode');
  collectionView.caseQuery = ''; collectionView.caseFilter = 'all';
  $('#view').innerHTML = `<div class="case-layout"><main class="report collection-page" id="report">${collectionHeader('cases')}
    <div class="collection-ledger" aria-label="案卷统计"><div><strong id="caseCount" aria-label="当前列表案卷数量">—</strong><span>份案卷</span></div><div><strong id="caseCompanies">—</strong><span>家公司</span></div><div><strong id="caseVersions">—</strong><span>版报告</span></div><p>每一版都保留<br><span>新材料，接着原来的线索核实。</span></p></div>
    <section aria-labelledby="archive-list-title"><div class="collection-toolbar"><label class="collection-search">${collectionIcon('search')}<input type="search" id="caseSearch" disabled aria-label="搜索案卷" placeholder="搜索公司名称或关注事项" autocomplete="off"></label><label class="collection-sort"><span>排列</span><select id="caseSort" disabled aria-label="案卷排列顺序"><option value="newest"${collectionView.caseSort === 'newest' ? ' selected' : ''}>最近新建</option><option value="oldest"${collectionView.caseSort === 'oldest' ? ' selected' : ''}>最早新建</option></select></label></div>
    <div class="collection-list-label"><div class="collection-filters" role="group" aria-label="案卷筛选"><button data-act="cases-filter" disabled data-filter="all" aria-pressed="true" id="archive-list-title">全部案卷</button><button data-act="cases-filter" disabled data-filter="multiple" aria-pressed="false">有多个版本</button></div><span id="caseMatches" role="status">读取案卷…</span></div>
    <div class="archive-list folder-grid" id="caseList" aria-busy="true"><div class="collection-empty" role="status">读取案卷…</div></div></section>
    <footer class="collection-footer">${collectionIcon('file')}<p>拿到新合同或对方回复？<span>打开对应案卷，补充材料后继续核实，旧版报告仍可回看。</span></p></footer>
    </main><aside class="assist" id="assist" aria-label="小企助手">${archiveAssistantHtml()}</aside></div>`;
  try {
    const cases = await api('/api/cases', {signal: request?.signal});
    if (!currentRoute(request)) return;
    if (!Array.isArray(cases)) throw new Error('列表内容格式不正确，请重试');
    S.cases = cases; renderCaseCollection();
    $('#caseSearch').disabled=false; $('#caseSort').disabled=false;
    $$('[data-act="cases-filter"]').forEach(button => {button.disabled=false;});
  } catch (e) {
    if (!currentRoute(request)) return;
    $('#caseList').innerHTML = `<div class="collection-empty"><p class="err" role="alert">读不到案卷列表：${esc(e.message)}</p><p>已保存的案卷不会因此清空。</p><button class="collection-button" type="button" data-act="retry-read">重试</button></div>`;
    $('#caseMatches').textContent = '读取暂未完成';
  } finally {
    if (currentRoute(request)) $('#caseList')?.setAttribute('aria-busy','false');
  }
}
function caseRow(c, index = 0) {
  return `<a class="archive-row folder-card" href="#/case/${esc(encodeURIComponent(c.id))}">
    <span class="folder-card-tab"><span>${esc(c.scenario_label || '企业核验')}</span><small>${String(index+1).padStart(2,'0')}</small></span>
    <span class="folder-card-back" aria-hidden="true"></span><div class="folder-card-front"><div class="folder-card-top"><span>企er / 企业研究案卷</span><span class="archive-versions">${esc(c.versions)} 个版本</span></div>
    <div class="folder-card-title"><h3>${esc(c.company_name)}</h3><span class="folder-seal" aria-hidden="true">${collectionIcon('file')}</span></div>
    <div class="folder-question"><span>本次关注</span><p>${esc(c.need || '了解这家公司的公开资料')}</p></div>
    <div class="folder-card-foot"><span>${c.created_at ? `<time datetime="${esc(c.created_at)}">${esc(fmtTime(c.created_at))} 新建</time>` : '新建时间未记录'}</span><span class="archive-open">打开报告 ${collectionIcon('arrow')}</span></div></div>
  </a>`;
}
function renderLibrary() {
  document.body.classList.add('research-mode','dossier-shell','collections-mode','knowledge-mode');
  S.case = null; useTerms(S.terms); renderTop();
  collectionView.libraryQuery = ''; collectionView.libraryFilter = 'all'; collectionView.study = false;
  $('#view').innerHTML = shellHtml(`<div class="collection-page">${collectionHeader('library')}<div class="knowledge-intro"><span>${collectionIcon('bookmark')} 收藏，是为了下次看懂</span></div><div id="libList">${libraryHtml(libRead())}</div></div>`);
}

// ---------- 分区四：我的 ----------

async function renderMe(request = routeRequest) {
  // Keep the account panel and its actions on the personal-home route.
  await renderGuide(request, true);
}

// ---------- 使用说明：独立于个人主页 ----------

async function renderGuide(request = routeRequest, showAccount = false) {
  document.body.classList.add('research-mode', 'dossier-shell');
  if (showAccount) document.body.classList.add('me-mode');
  S.case = null; useTerms(S.terms); renderTop();
  $('#view').innerHTML = '<div class="home"><p class="muted">读取服务状态…</p></div>';
  let cases = null;
  const caseRead = api('/api/cases', {signal: request?.signal}).then(value => {if (Array.isArray(value)) cases = value;}).catch(() => {});
  // 次数和未并入的案卷随时会变，每次进来都重读；不挡着页面，读到了只重画账号这一块
  api('/api/session', {signal: request?.signal}).then(value => {
    if (!currentRoute(request) || !value) return;
    S.session = value;
    const box = $('#acct');
    if (box) box.innerHTML = acctHtml();
  }).catch(() => {});
  await Promise.all([startupReady, caseRead]);
  if (!currentRoute(request)) return;
  if (cases) S.cases = cases;
  const h = S.health, llm = h?.llm, com = h?.commercial;
  const model = !llm || (typeof llm.configured !== 'boolean' && !['off', 'replay'].includes(llm.mode))
    ? '模型服务状态暂未读到，请刷新页面再试。'
    : llm.mode === 'replay'
      ? '当前使用已保存的模型回答回放；回放内容不能代表刚刚完成了查询。'
      : !llm.configured || llm.mode === 'off'
        ? '当前未启用模型辅助，需求用关键词识别，小企提供基础解释和核对步骤。'
        : '已启用模型辅助，用于理解需求、整理材料和解释报告；本次是否成功，以实际回答为准。';
  const commercial = typeof com?.configured !== 'boolean'
    ? '商业资料服务状态暂未读到，请刷新页面再试。'
    : com.configured
      ? '已启用商业资料服务。具体取得了哪些登记、年报等资料，以本次报告的来源和覆盖状态为准。'
      : '当前未启用商业资料服务；可用的公开记录和已收集资料仍会用于核对，缺少的部分会在报告中说明。';
  const caseStatus = cases
    ? cases.length ? `${cases.length} 份，可在「案卷」查看` : S.session?.account ? '账号里还没有案卷' : '本浏览器还没有案卷'
    : '<span class="err">案卷列表暂未读到，已保存的案卷不会因此清空。</span> <button class="btn sm" data-act="retry-read">重试读取案卷</button>';
  const terms = S.terms.slice(0, 8);
  $('#view').innerHTML = shellHtml(`
  <div class="home">
    <section class="home-hero">
      ${showAccount ? '' : '<div class="kicker">使用说明</div>'}
      <h1>${showAccount ? '我的' : '使用说明'}</h1>
      <p>了解当前可用的资料、案卷如何保存，以及阅读报告时需要留意的范围。</p>
    </section>

    ${showAccount ? `<section class="me-sec acct" id="acct">${acctHtml()}</section>
      <p class="me-p"><a href="#/guide">查看使用说明 →</a></p>` : ''}

    <section class="me-sec"><h2>服务与资料覆盖</h2>
      <dl class="kv-me">
        <dt>模型辅助</dt><dd>${esc(model)}</dd>
        <dt>商业资料服务</dt><dd>${esc(commercial)}</dd>
        <dt>${S.session?.account ? '账号里的案卷' : '本浏览器案卷'}</dt><dd>${caseStatus}</dd>
      </dl>
    </section>

    <section class="me-sec"><h2>来源与日期</h2>
      <p class="me-p">${listLine(h)}</p>
      <p class="me-p">资料的发布日期、记录日期和采集时间可能不同。请点开报告中的原始记录，核对来源、日期和适用范围；旧版报告保留的是当时取得的资料。</p>
      <p class="me-p">公开资料、第三方数据、你提交的材料和用户评价会标明来源。需要登录或验证码才能取得、且本次未能取得的资料，会如实标注覆盖状态；缺少记录不能说明公司没有问题。</p>
    </section>

    <section class="me-sec"><h2>名词解释</h2>
      <p class="me-p">报告里带虚线的词可以点开解释，不熟的可以收藏到「知识库」复习；模型补充的解释会标注为“AI 解释”，需要结合原文核对。这里是固定词表中的几个：</p>
      ${terms.length ? `<div class="chips">${terms.map(t => `<button type="button" class="chip" data-act="term" data-term="${esc(t.id)}">${esc(t.term)}</button>`).join('')}</div>` : '<p class="muted small">词表暂未读到，请刷新页面再试。</p>'}
    </section>

    <section class="me-sec"><h2>材料和案卷</h2>
      <ul class="me-ul">
        <li>${S.session?.account ? '材料、案卷和聊天只有登录这个账号才能看到，换设备登录同一账号即可找回。' : '材料、案卷和聊天仅此浏览器可见，不会自动跨设备同步；清除浏览器数据后不能自动恢复。登录后可以换设备找回。'}</li>
        <li>提交到案卷的材料文字会保留在原始记录中，便于回看核对。补材料、加入对方回复或修改需求会生成新版本，旧版本也会保留。</li>
        <li>上传材料不会自动变成公开评价。只有你主动发布的评价会公开；发布前请自行检查内容，避免写入个人敏感信息。</li>
      </ul>
    </section>

    <section class="me-sec"><h2>怎样使用报告</h2>
      <ul class="me-ul">
        <li>报告按已取得的资料和核对规则整理线索，模型辅助读材料和解释；来源或识别有误时，仍需回到原文核实。</li>
        <li>公司资料不能替代对具体产品和合同的核对。不打安全分，也不给公司定性；“没查”“查了没有”和“查询失败”含义不同。</li>
        <li>用户评价是个人观点，未经核实，不能单凭评价判断一家公司。</li>
        <li>聊天不会悄悄改报告；新情况要明确点"加入案卷"才会重新判断。</li>
        <li>虚构的演示案例全程挂着"演示数据 · 公司为虚构"。</li>
      </ul>
    </section>
  </div>`);
}

// ---------- 账号（可选）：登录了换设备也能找回案卷和知识库 ----------

const quotaLine = q => !q ? '' : q.limit ? `今天已新建 ${q.used} / ${q.limit} 次研究` : '研究次数不限额';
function acctHtml() {
  const ses = S.session, a = ses?.account;
  if (!ses) return '<h2>账号</h2><p class="me-p muted">账号状态暂未读到，请刷新页面再试。</p>';
  if (a) return `<h2>${a.role === 'admin' ? '管理员账号' : '账号'}</h2>
    <dl class="kv-me"><dt>邮箱</dt><dd>${esc(a.email)}</dd><dt>额度</dt><dd>${quotaLine(ses.quota)}（示例不计次）</dd></dl>
    ${ses.guest_cases ? `<div class="acct-merge"><p>这个浏览器上还有 ${ses.guest_cases} 份未登录时查的案卷。是你自己查的，就并进账号；在别人的电脑上，就别并。</p>
      <button type="button" class="btn sm" data-act="acct-merge">并进账号</button></div>` : ''}
    <div class="acct-acts"><button type="button" class="btn sm ghost" data-act="acct-logout">退出登录</button></div>
    <details class="acct-more"><summary>修改密码</summary>
      <form class="acct-form" id="acctPw"><label>原密码 <input type="password" name="old" required autocomplete="current-password"></label>
        <label>新密码 <input type="password" name="new" required minlength="8" maxlength="128" autocomplete="new-password"></label>
        <button class="btn sm" type="submit">修改</button><p class="small muted">改完后，其他设备上的登录会失效。</p></form></details>
    <details class="acct-more"><summary>注销账号</summary>
      <form class="acct-form" id="acctDel"><p class="small">注销后账号和知识库会删除，账号里的案卷也再打不开，不能恢复。</p>
        <label>密码 <input type="password" name="password" required autocomplete="current-password"></label>
        <button class="btn sm danger" type="submit">确认注销</button></form></details>`;
  const mode = S.acctMode || 'login';
  const tabs = [['login', '登录'], ['register', '注册']].map(([k, l]) =>
    `<button type="button" class="acct-tab" data-act="acct-mode" data-mode="${k}" aria-pressed="${mode === k}">${l}</button>`).join('');
  const intro = `<h2>账号</h2><p class="me-p">不登录也能用。登录后，换手机或电脑也能找回案卷和知识库。${ses.quota ? `未登录${quotaLine(ses.quota)}，登录后每天额度更多。` : ''}</p>`;
  if (mode === 'forgot') return `${intro}
    <form class="acct-form" id="acctForgot"><label>注册时的邮箱 <input type="email" name="email" required autocomplete="email"></label>
      <button class="btn sm" type="submit">发送重设密码邮件</button>
      <button type="button" class="linkish small" data-act="acct-mode" data-mode="login">返回登录</button>
      ${ses.mail ? '' : '<p class="small err">找回邮件暂时发不出去，请稍后再试。</p>'}</form>`;
  return `${intro}<div class="acct-tabs">${tabs}</div>
    <form class="acct-form" id="acctForm" data-mode="${mode}">
      <label>邮箱 <input type="email" name="email" required autocomplete="${mode === 'login' ? 'username' : 'email'}"></label>
      <label>密码 <input type="password" name="password" required ${mode === 'register' ? 'minlength="8" ' : ''}maxlength="128" autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}"></label>
      <button class="btn sm" type="submit">${mode === 'login' ? '登录' : '注册并登录'}</button>
      ${mode === 'login' ? '<button type="button" class="linkish small" data-act="acct-mode" data-mode="forgot">忘记密码</button>'
        : '<p class="small muted">密码至少 8 位。我们只存邮箱和加密后的密码；邮箱填错了就没法找回密码。</p>'}
    </form>`;
}
async function acctRefresh(msg) {
  S.acctMode = 'login';
  try { S.session = await api('/api/session'); } catch {}
  if (msg) toast(msg);
  await libSync();
  if (/^#\/me/.test(location.hash)) await renderMe(); else void route();
}
async function acctSignedOut(msg) {
  libForget(); S.cases = []; S.case = null;
  await acctRefresh(msg);
}
async function acctSubmit(form) {
  const btn = form.querySelector('button[type="submit"]'), f = Object.fromEntries(new FormData(form));
  btn.disabled = true;
  try {
    if (form.id === 'acctForm') {
      const login = form.dataset.mode === 'login';
      await api(login ? '/api/auth/login' : '/api/auth/register', {method: 'POST', body: {email: f.email, password: f.password}});
      await acctRefresh(login ? '已登录' : '已注册并登录');
    } else if (form.id === 'acctForgot') {
      const r = await api('/api/auth/forgot', {method: 'POST', body: {email: f.email}});
      S.acctMode = 'login'; toast(r.message); $('#acct').innerHTML = acctHtml();
    } else if (form.id === 'acctPw') {
      await api('/api/auth/password', {method: 'POST', body: {old: f.old, new: f.new}});
      await acctRefresh('密码已修改，其他设备需要重新登录');
    } else if (form.id === 'acctDel') {
      await api('/api/auth/delete', {method: 'POST', body: {password: f.password}});
      await acctSignedOut('账号已注销');
    } else if (form.id === 'resetForm') {
      if (f.password !== f.again) { toast('两次输入的密码不一样', true); return; }
      await api('/api/auth/reset', {method: 'POST', body: {token: form.dataset.token, password: f.password}});
      history.replaceState(null, '', '#/me');
      await acctRefresh('密码已重设，已登录');
    }
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}
function renderReset() {
  S.case = null; useTerms(S.terms); renderTop();
  const token = new URLSearchParams(location.hash.split('?')[1] || '').get('t') || '';
  $('#view').innerHTML = shellHtml(`<div class="home">
    <section class="home-hero"><div class="kicker">账号</div><h1>重设密码</h1><p>邮件里的链接 30 分钟内有效，只能用一次。</p></section>
    <section class="me-sec acct">${token ? `<form class="acct-form" id="resetForm" data-token="${esc(token)}">
      <label>新密码 <input type="password" name="password" required minlength="8" maxlength="128" autocomplete="new-password"></label>
      <label>再输一遍 <input type="password" name="again" required minlength="8" maxlength="128" autocomplete="new-password"></label>
      <button class="btn sm" type="submit">重设并登录</button></form>`
      : '<p class="me-p">链接不完整。请从邮件里重新打开，或者到「我的」重新申请找回。</p><a class="btn sm" href="#/me">去「我的」</a>'}</section>
  </div>`);
}

function formHtml() {
  const demos = S.demos.filter(d => d.ready);
  return `<form class="ask-card" id="caseForm" autocomplete="off">
    <div class="f-row"><label class="f-l" for="fCompany">公司名称</label>
      <input class="big-inp" id="fCompany" name="company" required minlength="2" placeholder="全称或简称都行，例如：杭州银行" title="简称也行：开查前会先找到营业执照上的全称，有几家同名的会让你选">
      <div class="name-cands" id="nameCands" role="group" aria-label="同名的公司" hidden></div></div>
    <div class="f-row"><label class="f-l" for="fNeed">你要做什么</label>
      <textarea class="big-inp" id="fNeed" name="need" rows="2" placeholder="例如：我妈想在这家公司存 20 万理财，最怕急用时取不出来"></textarea>
      <div class="intake" id="intake">${intakeHtml()}</div></div>
    <div class="facts"><label>替 <input name="for_whom" placeholder="谁"> 看</label><label>金额 <input name="amount" class="mono" placeholder="可不填"></label><span class="muted small" id="amtHint"></span></div>
    <p class="small muted">先了解公司。报告生成后，可在「问询与复核」补充合同、宣传单或对方回复。</p>
    <div class="submit-row"><button class="btn" type="submit" id="fSubmit">生成报告</button>
      ${demos.length ? `<span class="muted small">或填入演示案例：${demos.map(d => `<button type="button" class="linkish" data-act="demo-fill" data-id="${esc(d.id)}">${esc(d.label)}</button>`).join('、')}</span>` : ''}</div>
    <div class="err" id="formErr" role="alert"></div>
  </form>`;
}

function intakeHtml() {
  const f = S.form, it = f.intake;
  const chosen = f.userScenario || (it && it.scenario);
  const sc = S.scenarios.find(s => s.id === chosen);
  const how = f.userScenario ? '你选的' : it ? (it.method === 'model' ? '模型识别' : '关键词识别') : '';
  const line = sc
    ? `<span class="muted">识别为</span> <b>${esc(sc.label)}</b> <span class="muted small">（${esc(how)}）</span> <button type="button" class="linkish" data-act="scen-toggle">${f.showScen ? '收起' : '换一个'}</button>
       <div class="first-q">先回答：${esc(sc.first_question)}${it && it.focus && it.focus.length ? `<span class="muted">；你最担心：${it.focus.map(esc).join('、')}</span>` : ''}</div>`
    : `<span class="muted small">写完会自动识别场景，也可以</span> <button type="button" class="linkish" data-act="scen-toggle">${f.showScen ? '收起' : '直接选'}</button>`;
  return `${line}${f.showScen ? `<div class="chips scen-chips">${S.scenarios.map(s => `<button type="button" class="chip" data-act="scenario" data-id="${esc(s.id)}" aria-pressed="${s.id === chosen}">${esc(s.label)}</button>`).join('')}</div>` : ''}`;
}

function bindForm() {
  const form = $('#caseForm');
  if (!form) return;
  let timer = null, seq = 0, last = '';
  const runIntake = async () => {
    const need = form.need.value.trim();
    if (need === last) return;
    last = need;
    if (!need) { S.form.intake = null; $('#intake').innerHTML = intakeHtml(); return; }
    const mine = ++seq;
    $('#intake').classList.add('busy');
    try {
      const r = await api('/api/intake', { method: 'POST', body: { need, company_name: form.company.value.trim() || null } });
      if (mine !== seq) return;
      S.form.intake = r;
      if (!S.form.dirty.for_whom && r.for_whom) form.for_whom.value = r.for_whom;
      if (!S.form.dirty.amount && r.amount) { form.amount.value = fmtMoney(r.amount).replace(/\s/g, ''); amtHint(); }
      $('#intake').innerHTML = intakeHtml();
    } catch (e) { /* 识别失败不挡路：用户可以手动选场景 */ }
    finally { if (mine === seq) $('#intake').classList.remove('busy'); }
  };
  const amtHint = () => {
    const n = parseAmount(form.amount.value);
    $('#amtHint').textContent = form.amount.value.trim() ? (n ? `= ${n.toLocaleString()} 元` : '没看懂，写成 200000 或 20万') : '';
  };
  form.need.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runIntake, 800); });
  form.need.addEventListener('blur', () => { clearTimeout(timer); runIntake(); });
  form.company.addEventListener('input', () => { $('#nameCands').hidden = true; });
  form.for_whom.addEventListener('input', () => { S.form.dirty.for_whom = true; });
  form.amount.addEventListener('input', () => { S.form.dirty.amount = true; amtHint(); });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    let company = form.company.value.trim();
    if (company.length < 2) { $('#formErr').textContent = '请填公司名称'; return; }
    const amount = parseAmount(form.amount.value);
    if (form.amount.value.trim() && !amount) { $('#formErr').textContent = '金额没看懂，写成 200000 或 20万，或者留空'; return; }
    $('#formErr').textContent = '';
    company = await resolveCompany(company);
    if (!company) return;
    form.company.value = company;
    await createCase({
      company_name: company, need: form.need.value.trim(),
      scenario: S.form.userScenario || null,
      for_whom: form.for_whom.value.trim() || null, amount,
    });
  });
}

// 简称很正常，但名单和企查查都按全称核对：开查前先把名字定成全称。精确对上直接查；有几家同名就列出来让用户选，不替他挑
async function resolveCompany(q) {
  if (S.form.resolved === q) return q;
  const box = $('#nameCands'), go = $('#fSubmit');
  let r;
  go.disabled = true;
  try { r = await api(`/api/companies/resolve?q=${encodeURIComponent(q)}`); }
  catch { return q; }   // 找名字这一步连不上不挡路，按原样查，报告里会写明名字对没对上
  finally { go.disabled = false; }
  if (r.exact) { S.form.resolved = r.name; box.hidden = true; return r.name; }
  box.innerHTML = r.candidates.length
    ? `<p>${esc(r.note || '请选一家')}</p>${r.candidates.map(c => `<button type="button" class="name-cand" data-act="pick-company" data-name="${esc(c.name)}">
        <b>${esc(c.name)}</b><small>${[c.status, c.founded && `成立于 ${c.founded}`, c.code].filter(Boolean).map(esc).join(' · ')}</small></button>`).join('')}`
    : `<p class="err">${esc(r.note || '没找到这家公司，请输入营业执照上的全称')}</p>`;
  box.hidden = false;
  box.querySelector('button')?.focus();
  return null;
}

async function readFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  return api('/api/read', { method: 'POST', body: fd });
}

async function createCase(body) {
  if (S.creating) { toast('已有案卷正在生成，请稍候或到案卷列表查看'); return; }
  const wrap = $('#formWrap'), keep = wrap.innerHTML;
  const route = location.hash, formState = S.form;
  const stillHere = () => wrap.isConnected && location.hash === route && S.form === formState;
  S.creating = true;
  const waiting = ResearchProgress.mount(wrap, body.company_name);
  try {
    const c = await ResearchProgress.readCaseStream('/api/cases/stream', body, { onEvent: waiting.onEvent });
    if (!stillHere()) { toast('报告已生成，可以在「案卷」查看'); return; }
    S.case = c; S.viewNo = c.current; S.selected.clear(); S.opCache = {}; S.tab = 'signals'; S.openRest.clear();
    S.reviews = null; S.rvStars = 0; S.rvRel = null;
    location.hash = `#/case/${c.id}`;
  } catch (e) {
    if (!stillHere()) { toast('查询连接已结束，请到「案卷」确认结果', true); return; }
    wrap.innerHTML = keep; bindForm();
    const f = $('#caseForm');
    f.company.value = body.company_name; f.need.value = body.need;
    f.for_whom.value = body.for_whom || ''; f.amount.value = body.amount ? fmtMoney(body.amount).replace(/\s/g, '') : '';
    $('#intake').innerHTML = intakeHtml();
    $('#formErr').textContent = '没生成出来：' + e.message;
  } finally { waiting.stop(); S.creating = false; }
}

function fillDemo(id) {
  const d = S.demos.find(x => x.id === id);
  const f = $('#caseForm');
  if (!d || !d.input || !f) return;
  f.company.value = d.input.company_name; f.need.value = d.input.need || '';
  f.for_whom.value = d.input.for_whom || ''; f.amount.value = d.input.amount ? fmtMoney(d.input.amount).replace(/\s/g, '') : '';
  S.form.userScenario = d.input.scenario || null;
  f.need.dispatchEvent(new Event('blur'));
  toast(`已填入演示案例 ${d.id}，点"生成报告"`);
}

// ---------- 报告页 ----------

async function openCase(id, no, request = routeRequest) {
  if (!S.case || S.case.id !== id) {
    S.case = null; S.viewNo = null;
    $('#view').innerHTML = '<div class="home"><p class="muted">读取案卷…</p></div>';
    try {
      const data = await api(`/api/cases/${encodeURIComponent(id)}`, {signal: request?.signal});
      if (!currentRoute(request)) return;
      S.case = data;
    }
    catch (e) {
      if (!currentRoute(request)) return;
      $('#view').innerHTML = `<div class="home"><div class="ask-card"><h2>打不开这个案卷</h2><p class="err">${esc(e.message)}</p><button class="btn sm" data-act="retry-read">重试</button><a class="btn sm" href="#/cases">返回案卷</a></div></div>`;
      return;
    }
    S.selected.clear(); S.opCache = {}; S.tab = 'signals'; S.openRest.clear();
    S.reviews = null; S.rvStars = 0; S.rvRel = null;
  }
  const next = no && S.case.versions.some(v => v.no === no) ? no : S.case.current;
  if (S.viewNo !== next) S.selected.clear();
  S.viewNo = next;
  renderCase();
  if (pendingSupplement(id)) void resumeSupplement();
}

function renderCase() {
  const c = S.case, v = ver();
  document.body.classList.toggle('dossier-live', isDesignReview());
  if (S.tab === 'changes' && v.no === 1) S.tab = 'signals';
  if (isDesignReview() && ['signals', 'reviews'].includes(S.tab)) S.tab = 'claims';
  const assistOpen = $('#assist') && $('#assist').classList.contains('open');
  useTerms(v.terms && v.terms.length ? v.terms : S.terms);
  renderTop();
  $('#view').innerHTML = `
  <div class="case-layout">
    <div class="report" id="report">
      <div id="supplementNotice">${supplementNoticeHtml()}</div>
      ${isDesignReview() ? dossierReport(c, v) : caseHead(c, v) + conclusionHtml(v) + chartsHtml(v)}
      ${!isDesignReview() ? `${v.no > 1 ? `<button type="button" class="chg-banner" data-act="tab" data-tab="changes"><b>第 ${v.no} 版 · ${esc(v.trigger_label)}</b><span>${esc((SHOW_JUDGMENTS && v.judgment_summary) || v.change_summary || '')}</span><em>看变化 →</em></button>` : ''}${tabsHtml(v)}<div class="panel" id="panel" role="tabpanel">${panelHtml(v)}</div>` : ''}
      ${isDesignReview() ? researchDisclaimer() : '<footer class="foot">结论来自公开记录和固定规则，AI 只负责读材料和说人话。这里不打安全分，也不给公司定性；"没查"不等于没问题，"查了没有"也只代表在那份数据里没有。</footer>'}
      ${prebuiltNoticeHtml(v)}
    </div>
    <aside class="assist${assistOpen ? ' open' : ''}" id="assist" aria-label="小企（AI 栏）">${assistHtml()}</aside>
  </div>
  ${qiLauncherHtml()}`;
  initResearchDesign();
  if (isDesignReview()) initDossierReport();
  if ($('#onepager')) loadOnepager(v);
  loadReviews();
  scrollChat();
}

function caseHead(c, v) {
  const raws = versionRaws(v);
  const n = k => raws.filter(r => r.coverage === k).length;
  const cov = [['found', '查到'], ['not_found', '查了没有'], ['not_covered', '没查'], ['failed', '查询失败']]
    .filter(([k]) => n(k)).map(([k, l]) => `${n(k)} ${l}`).join(' · ');
  return `<header class="case-head">
    <div class="ch-top">
      ${c.versions.length > 1 ? `<div class="vers" role="group" aria-label="版本">${c.versions.map(x => `<button type="button" class="ver" data-act="ver" data-no="${x.no}" aria-current="${x.no === v.no}"><b>v${x.no}</b>${esc(x.trigger_label)}</button>`).join('')}</div>` : '<span></span>'}
      <div class="head-acts">
        <button type="button" class="btn sm cam" data-act="contract">📷 拍合同 · 二次审核</button>
        <button type="button" class="btn sm ghost" data-act="supplement">＋ 补充信息</button>
      </div>
    </div>
    <h1>${esc(c.case.company_name)}</h1>
    ${v.need ? `<p class="need">“${esc(v.need)}”</p>` : ''}
    <div class="meta-line">
      <span>${esc(v.scenario_label)}</span>
      ${v.for_whom ? `<span>替${esc(v.for_whom)}看</span>` : ''}
      ${v.amount ? `<span class="mono">${esc(fmtMoney(v.amount))}</span>` : ''}
      <button type="button" class="linkish" data-act="tab" data-tab="raw">汇集了 ${raws.length} 条记录：${cov}</button>
    </div>
    ${v.no === c.current ? '' : `<div class="old-banner">你在看第 ${v.no} 版（${esc(v.trigger_label)}），最新是第 ${c.current} 版。<button type="button" class="linkish" data-act="ver" data-no="${c.current}">回到最新</button></div>`}
    ${reportReadingNotes(v).length ? `<ul class="notes">${reportReadingNotes(v).map(t => `<li${/演示|虚构/.test(t) ? ' class="demo"' : ''}>${esc(t)}</li>`).join('')}</ul>` : ''}
  </header>`;
}

// 第一层：一眼看懂（屏幕上）+ 一页结论（文字版，给家人看、打印）
function conclusionHtml(v, includeSignals = true) {
  return `<section class="conclusion" id="L1">
    <div class="cc-bar"><span class="kicker">一眼看懂</span>
      <button type="button" class="linkish" data-act="optext">${S.showText ? '收起文字版' : '文字版（给家人看）'}</button>
      <button type="button" class="linkish" data-act="print">打印</button></div>
    <div class="glance">${glanceHtml(v, includeSignals)}</div>
    <div class="op-wrap"${S.showText ? '' : ' hidden'}>
      <div class="op-tools"><div class="seg" role="group" aria-label="给谁看"><button type="button" data-act="aud" data-aud="family" aria-pressed="${S.audience === 'family'}">给家人</button><button type="button" data-act="aud" data-aud="teller" aria-pressed="${S.audience === 'teller'}">给网点柜员</button></div></div>
      <article class="onepager" id="onepager">${opBody(currentOp(v), v)}</article>
    </div>
  </section>`;
}

// 用图看：图里的数全部来自记录和规则（后端 app/analysis/charts.py），不经过模型。没查的画虚线框，不画成 0
const SIDE = { said: '它说的', record: '记录里的', reference: '参考值' };
function chartsHtml(v) {
  const cs = v.charts || [];
  if (!cs.length) return '';
  const small = cs.filter(c => c.kind !== 'timeline'), tl = cs.find(c => c.kind === 'timeline');
  return `<section class="viz" id="LV" aria-label="用图看">
    <div class="cc-bar"><span class="kicker">用图看</span><span class="small muted">图里的数全部来自记录，点图看出处</span></div>
    ${small.length ? `<div class="viz-grid">${small.map(c => chartCard(c, v)).join('')}</div>` : ''}
    ${tl ? chartCard(tl, v) : ''}
  </section>`;
}
function chartCard(c, v) {
  const body = c.kind === 'compare' ? compareHtml(c) : c.kind === 'share' ? shareHtml(c)
    : c.kind === 'series' ? seriesSvg(c.points.map(p => p.label), c.points.map(p => p.value || 0)) : timelineHtml(c, v);
  const refs = [...new Set([...c.points.map(p => p.ref), ...c.events.map(e => e.ref)].filter(Boolean))].sort((a, b) => +a.slice(1) - +b.slice(1));
  const params = [...new Set(c.points.filter(p => !p.ref && p.source && p.side === 'reference').map(p => p.source))];
  return `<figure class="vcard v-${c.kind}">
    <figcaption><b>${esc(c.title)}</b>${c.item ? `<button type="button" class="linkish small" data-act="goto" data-id="${esc(c.item)}">看这一条</button>` : ''}</figcaption>
    ${body}
    ${c.note ? `<p class="v-note">${termText(c.note)}</p>` : ''}
    ${refs.length || params.length ? `<div class="v-src">出处 ${refs.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(recordRefText(r))}</button>`).join('')}${params.map(s => srcLink(s)).join('')}</div>` : ''}
  </figure>`;
}
function compareHtml(c) {
  const max = Math.max(0, ...c.points.map(p => p.value ?? 0)) || 1;
  const sides = [...new Set(c.points.map(p => p.side))];
  return `<div class="cmp">${c.points.map(p => {
    const na = p.value == null, zero = !na && p.value === 0;
    const w = na ? 100 : Math.max((p.value / max) * 100, p.value > 0 ? 1.5 : 0);
    return `<div class="cmp-row ${p.side}${na ? ' na' : ''}${zero ? ' zero' : ''}">
      <span class="cmp-l">${esc(p.label)}</span>
      <span class="cmp-bar"><i style="width:${w}%"></i>${na ? '<em>没查</em>' : ''}</span><b class="cmp-v">${esc(p.display)}</b></div>`;
  }).join('')}</div>
  ${sides.length > 1 ? `<div class="cmp-legend">${sides.map(s => `<span class="lg ${s}"><i></i>${SIDE[s]}</span>`).join('')}</div>` : ''}`;
}
function shareHtml(c) {
  const fill = ['var(--ink)', 'var(--ink-3)', '#a9a294', 'var(--rule)'];
  return `<div class="share-bar">${c.points.map((p, i) => `<span style="width:${p.value}%;background:${fill[i % 4]};color:${i % 4 < 2 ? '#fff' : 'var(--ink)'}" title="${esc(p.label)} ${esc(p.display)}">${p.value >= 15 ? esc(p.display) : ''}</span>`).join('')}</div>
    <ul class="share-lg">${c.points.map((p, i) => `<li><i style="background:${fill[i % 4]}"></i>${esc(p.label)} <b>${esc(p.display)}</b></li>`).join('')}</ul>`;
}
function timelineHtml(c, v) {
  const t = d => Date.parse(d.length === 7 ? `${d}-15` : d.slice(0, 10));
  const today = t(v.created_at.slice(0, 10));
  const all = [...c.events.map(e => t(e.date)), today];
  const min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
  const pos = x => 3 + ((x - min) / span) * 94;
  const years = [];
  for (let y = new Date(min).getFullYear() + 1; y <= new Date(max).getFullYear(); y++) years.push(y);
  return `<div class="tl-track">
      ${years.map(y => `<span class="tl-tick" style="left:${pos(Date.parse(`${y}-01-01`))}%"><em>${y}</em></span>`).join('')}
      <span class="tl-today" style="left:${pos(today)}%"><em>查询日</em></span>
      ${c.events.map((e, i) => `<span class="tl-dot ${e.tone}" style="left:${pos(t(e.date))}%" title="${esc(e.date)} ${esc(e.label)}">${i + 1}</span>`).join('')}
    </div>
    <ol class="tl-list">${c.events.map((e, i) => `<li class="${e.tone}"${e.item ? ` data-act="goto" data-id="${esc(e.item)}" role="link" tabindex="0"` : ''}>
      <span class="tl-n">${i + 1}</span><time>${esc(e.date)}</time><span>${esc(e.label)}</span></li>`).join('')}</ol>`;
}

// 一眼看懂：判定、颜色、排序全部来自规则；短句是报告生成时 AI 按规则原句缩写的（v.glance.short），没有就用原句
const SEV = { bad: 4, warn: 3, miss: 2, none: 1, ok: 0 };
const MARK = { bad: '✗', warn: '!', miss: '?', none: '–', ok: '✓' };
const COLOR_ST = { red: 'bad', amber: 'warn', grey: 'miss', green: 'ok' };
const shortOf = (v, id, fallback) => (v.glance && v.glance.short[id]) || fallback;
function glanceItems(v) {
  const m = {};
  for (const a of v.assertions) m[a.id] = { status: COLOR_ST[a.color] || 'none', text: a.plain };
  for (const x of v.missing) m[x.id] = { status: 'miss', text: x.plain };
  for (const s of v.signals) for (const i of s.items) m[`${s.key}.${i.key}`] = { status: i.status, gap: i.gap, text: `${i.label}：${i.value}` };
  return m;
}
function answerOf(list) {
  const worst = list.reduce((w, i) => (SEV[i.status] > SEV[w] ? i.status : w), 'ok');
  if (worst === 'bad') return ['bad', '有问题'];
  if (worst === 'warn') return ['warn', '要留意'];
  if (worst === 'miss') return ['miss', '还缺证据'];
  const open = list.filter(isOpen), nOk = list.filter(i => i.status === 'ok').length;
  if (!nOk) return ['none', open.length && open.every(i => gapOf(i) === 'failed') ? '没查成，稍后重查' : '没查到数据'];
  return open.length ? ['none', '已查项暂未见异常', `另有 ${pendingNote(open)}`] : ['ok', '已查项暂未见异常'];
}
function glanceFirstHtml(v, seen = new Set()) {
  const items = glanceItems(v);
  const sc = S.scenarios.find(s => s.id === v.scenario);
  const firstIds = ((v.glance && v.glance.first.length) ? v.glance.first : (sc && sc.first_items) || []).filter(id => items[id]);
  const bySev = (a, b) => SEV[items[b].status] - SEV[items[a].status];

  // 第一问
  let first = '';
  if (firstIds.length) {
    const [st, word, note] = answerOf(firstIds.map(id => items[id]));
    // 下面"它说的 ⟷ 记录里的"已经列了说法，这里只列记录本身；没有记录条目才列说法
    const lines = firstIds.filter(id => !/^[AM]\d+$/.test(id));
    const show = lines.length ? lines : firstIds;
    first = `<div class="gl-first s-${st}">
      ${sc ? `<div class="gl-q">第一问：${esc(sc.first_question)}？</div>` : ''}
      <div class="gl-a"><span class="mk">${MARK[st]}</span><span>${esc(word)}${note ? `<small>${esc(note)}</small>` : ''}</span></div>
      <ul>${[...show].sort(bySev).slice(0, 4).map(id => `<li class="s-${items[id].status}" data-act="goto" data-id="${esc(id)}" tabindex="0" role="link"><span class="mk">${MARK[items[id].status]}</span><span>${termText(shortOf(v, id, items[id].text), seen)}</span></li>`).join('')}</ul>
    </div>`;
  }
  return first;
}

function glanceHtml(v, includeSignals = true) {
  const seen = new Set(), first = glanceFirstHtml(v, seen);

  // 它说的 ⟷ 记录里的
  const claims = [...v.assertions].sort((a, b) => SEV[COLOR_ST[b.color]] - SEV[COLOR_ST[a.color]]);
  const rows = [...claims.map(a => ({ id: a.id, said: a.text, rec: shortOf(v, a.id, a.plain), label: a.verdict_label, st: COLOR_ST[a.color] || 'none' })),
    ...v.missing.map(m => ({ id: m.id, said: `没写：${m.text}`, rec: shortOf(v, m.id, m.plain), label: '该写没写', st: 'miss' }))];
  const pairs = rows.length
    ? `${rows.slice(0, 6).map(r => `<div class="pair s-${r.st}" data-act="goto" data-id="${esc(r.id)}" tabindex="0" role="link">
        <q>${termText(r.said, seen)}</q><span class="mk">${MARK[r.st]}</span><span class="pr">${termText(r.rec, seen)}<small>${esc(r.label)}</small></span></div>`).join('')}
       ${rows.length > 6 ? `<button type="button" class="linkish more" data-act="tab" data-tab="claims">还有 ${rows.length - 6} 条 →</button>` : ''}`
    : `<p class="gl-empty">还没有它的说法可以对照。<button type="button" class="linkish" data-act="supplement" data-kind="material">上传宣传材料、合同或聊天记录</button>，就能逐条对照。</p>`;

  // 四个信号
  const tiles = v.signals.map(s => {
    const flagged = s.items.filter(i => FLAG.has(i.status)).sort((a, b) => SEV[b.status] - SEV[a.status]);
    const nOk = s.items.filter(i => i.status === 'ok').length, open = s.items.filter(isOpen);
    const st = flagged.length ? flagged[0].status : (nOk && !open.length ? 'ok' : 'none');
    const phrase = flagged.length ? shortOf(v, `${s.key}.${flagged[0].key}`, `${flagged[0].label}：${flagged[0].value}`)
      : !nOk ? (open.length && open.every(i => gapOf(i) === 'failed') ? '没查成，稍后重查' : '没查到数据')
      : open.length ? `已查项暂未见异常；${pendingNote(open)}` : '已查项暂未见异常';
    return `<button type="button" class="tile s-${st}" data-act="sigtile" data-key="${s.key}">
      <span class="t-h"><b>${esc(s.title)}</b><span class="mk">${MARK[st]}</span></span>
      <span class="t-p">${esc(phrase)}</span>${flagged.length > 1 ? `<span class="t-n">共 ${flagged.length} 项要看</span>` : ''}</button>`;
  }).join('');

  const q = v.questions[0];
  const ai = v.glance && ['model', 'replay'].includes(v.glance.mode);
  return `<div data-first-question>${first}</div>
    <div class="gl-grid${includeSignals ? '' : ' without-signals'}">
      <div><h4 class="gl-h">它说的 <span>⟷</span> 记录里的</h4>${pairs}</div>
      ${includeSignals ? `<div><h4 class="gl-h">四个信号</h4><div class="tiles">${tiles}</div></div>` : ''}
    </div>
    ${q ? `<div class="gl-next"><span class="kicker">下一步，先问对方</span><p>${termText(q.ask, seen)}</p>
      <span class="small muted">${termText(q.check_where, seen)}</span>
      ${v.questions.length > 1 ? ` <button type="button" class="linkish small" data-act="tab" data-tab="questions">全部 ${v.questions.length} 个问题 →</button>` : ''}</div>` : ''}
    ${ai ? '<p class="gl-ai">短句由 AI 按规则结论缩写，程序核对过数字和措辞；点任一行看完整原句和出处。</p>' : ''}`;
}
const currentOp = v => (S.audience === 'family' && v.onepager) || S.opCache[`${v.no}:${S.audience}`] || null;
async function loadOnepager(v) {
  const preview = $('#onepager'), load = {};
  if (preview) preview._onepagerLoad = load;
  if (currentOp(v)) return;
  const key = `${v.no}:${S.audience}`, caseId = S.case.id, request = routeRequest, cache = S.opCache;
  const stillHere = () => request === routeRequest && S.case?.id === caseId && ver() === v
    && key === `${v.no}:${S.audience}` && preview && $('#onepager') === preview && preview._onepagerLoad === load;
  try {
    cache[key] = await api(`/api/cases/${encodeURIComponent(caseId)}/onepager?audience=${S.audience}&version=${v.no}`, {signal: request?.signal});
    // 打印预览可能在请求回来之前就关了
    if (stillHere()) preview.innerHTML = opBody(cache[key], v);
  } catch (e) { if (stillHere()) preview.innerHTML = `<p class="err">一页结论没生成出来：${esc(e.message)}</p>`; }
}
function opBody(op, v) {
  if (!op) return '<p class="muted">正在生成…</p>';
  const seen = new Set();   // 整页每个词只标一次；打印时在页尾列出这些词的解释
  const line = l => `<li>${termText(l.text, seen)}${refLinks(l.refs)}</li>`;
  const col = (title, lines, cls, empty) => `<div class="op-col ${cls}"><h4>${title}</h4>${lines.length
    ? `<ul>${lines.map(line).join('')}</ul>` : `<p class="small muted">${empty}</p>`}</div>`;
  const noClaims = !v.assertions.length;
  const body = `<div class="op-head"><div><h3>${esc(op.title)}</h3><p>${esc(op.subject)}</p></div>
      <div class="stamp">案卷 ${esc(S.case.id)} · 第 ${v.no} 版<br>${esc(fmtTime(v.created_at))}${isDemoCase() ? '<br><b class="demo-mark">演示数据 · 公司为虚构</b>' : ''}</div></div>
    <p class="headline">${esc(op.headline)}</p>
    <div class="op-cols">
      ${col('哪里对不上', op.mismatch, 'mismatch', noClaims ? '还没有它的说法可以对照。' : '它的说法和记录没有对不上的地方。')}
      ${col('查到了什么', op.found, 'found', '还没查到具体记录。')}
      ${col('还不知道什么', op.unknown, 'unknown', '没有列出来的未知项。')}
    </div>
    ${op.next_steps.length ? `<div class="op-next"><h4>在下一步之前，先确认这几件事</h4><ol>${op.next_steps.map(line).join('')}</ol></div>` : ''}`;
  const used = [...seen].map(termOf).filter(Boolean).slice(0, 6);
  return `${body}
    ${used.length ? `<div class="op-terms"><h4>这页里的几个词</h4><dl>${used.map(t => `<div><dt>${esc(t.term)}</dt><dd>${esc(t.plain)}${t.origin === 'model' ? '（AI 解释）' : ''}</dd></div>`).join('')}</dl></div>` : ''}
    <p class="op-foot">${esc(op.footer)}</p>${prebuiltNoticeHtml(v)}`;
}

// 标签页：第二到第四层
function tabsHtml(v) {
  const flagged = v.signals.reduce((n, s) => n + s.items.filter(i => FLAG.has(i.status)).length, 0);
  // 变了多少条：材料那头和判断那头都要算。只数材料变化的话，补一份合同进来
  // （判断挪了三条、材料变化一条没有）标签上会写「变化 0」，而开头那句正说着有三条要重新核实。
  const mchg = v.changes.filter(x => x.kind !== 'unchanged').length;
  const jchg = (v.judgment_changes || []).filter(c => c.kind !== 'same').length;
  const changed = SHOW_JUDGMENTS ? Math.max(mchg, jchg) : mchg;
  const jug = v.judgments || [];
  const counts = { judgments: [jug.length, jug.some(j => j.state === 'needs_check')], changes: [changed, changed > 0], signals: [flagged, flagged > 0], claims: [v.assertions.length + v.missing.length, (v.tally.red || 0) > 0],
    questions: [v.questions.length, false], raw: [v.raw_ids.length, false],
    reviews: [S.reviews ? S.reviews.count : '…', !!(reviewItemOf(v) && reviewItemOf(v).status === 'warn')] };
  const tabs = Object.keys(TABS).filter(k => (!isDesignReview() || !['signals', 'reviews'].includes(k)) && (k !== 'changes' || v.no > 1) && (k !== 'judgments' || (SHOW_JUDGMENTS && jug.length)));
  return `<nav class="tabs" role="tablist" aria-label="报告的各层">${tabs.map(k => `<button type="button" class="tab" role="tab" data-act="tab" data-tab="${k}" aria-selected="${S.tab === k}">${TABS[k]}<span class="n${counts[k][1] ? ' hot' : ''}">${counts[k][0]}</span></button>`).join('')}</nav>`;
}
function panelHtml(v) {
  const cm = changeMap(v);
  switch (S.tab) {
    case 'judgments': return judgmentsPanel(v);
    case 'changes': return changesPanel(v);
    case 'claims': return claimsPanel(v, cm);
    case 'questions': return questionsPanel(v);
    case 'raw': return rawPanel(v);
    case 'reviews': return reviewsPanel(v);
    default: return signalsPanel(v, cm);
  }
}
function renderPanel() {
  const v = ver();
  $$('.tabs .tab').forEach(t => t.setAttribute('aria-selected', t.dataset.tab === S.tab));
  $('#panel').innerHTML = panelHtml(v);
}
function showTab(tab, scroll = true) {
  if ($('#signalDlg')?.open) $('#signalDlg').close();
  if (typeof researchNavigate === 'function' && isDesignReview()) {
    researchNavigate(tab, scroll); return;
  }
  if (tab === 'signals' && $('#research-signals')) {
    if (scroll) $('#research-signals').scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  if (tab === 'reviews' && $('#research-reviews')) {
    if (scroll) $('#research-reviews').scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  S.tab = tab; renderPanel();
  if (scroll) {
    const tabs = $('.tabs');
    const top = tabs.getBoundingClientRect().top;
    if (top < 0 || top > window.innerHeight * 0.6) tabs.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ---------- 判断：报告是某一版的样子，判断才是被追踪的东西 ----------
const LAYER_ORDER = [['said', '材料里写的', '照录。OCR 读对了只代表字读对了，不代表这份材料是真的。'],
                     ['confirmed', '记录里查到的', '查到的是这样。没查到不等于没问题。'],
                     ['inferred', '系统据此推断的', '推论，可以被依据推翻，也可以被人撤掉。']];
const JSTATE = { holds: 'ok', needs_check: 'warn', unconfirmed: 'grey', revised: 'warn', clarified: 'good', withdrawn: 'gone' };
// 五格：用户要看的是"哪些没变、哪些是新发现的、哪些要重新核实、哪些还不能确认、下一步问什么"
const FIVE = { same: ['保持不变', '这条没被新材料推翻'], found: ['新增发现', '新材料带出来的新情况'],
               recheck: ['需要重新核实', '这笔事要不要按原来那样办，得再确认'],
               unconfirmed: ['尚不能确认', '还没有任何东西能证明它'],
               next_question: ['下一步问题', '拿答案去核对，别自己猜'],
               dropped: ['这版没有了', '换了需求或换了材料，这条不再适用'],
               cleared: ['已经澄清', '有人核实过这件事，报告里那条提醒也跟着改了'] };

function judgmentsPanel(v) {
  const all = v.judgments || [];
  if (!all.length) return '<p class="empty-line">这一版没有留下判断记录。</p>';
  const groups = LAYER_ORDER.map(g => [g, all.filter(j => j.layer === g[0])]).filter(x => x[1].length);
  return `<p class="panel-lede">每一条判断都带着依据、前提、还没证明的事，和"不能因此推出什么"。材料真不真、账户归谁，材料本身证明不了。人对一条下过结论，往后几版不会把它悄悄翻回来。</p>
    ${groups.map(([[k, t, lede], list]) => `<section class="jgrp">
      <header><h3>${t}</h3><span class="jg-n">${list.length} 条</span></header>
      <p class="jgrp-lede">${lede}</p>
      ${list.map(j => judgCard(j)).join('')}
    </section>`).join('')}`;
}

function judgCard(j) {
  const st = JSTATE[j.state] || '';
  const ev = j.basis.filter(b => b.quote || b.locator);
  const refs = [...new Set(j.basis.filter(b => b.ref).map(b => b.ref))];
  return `<article class="judg ${st}" id="judg-${esc(j.id)}">
    ${ev.length ? `<div class="jg-slot"><span class="jg-k">材料摘录</span>${ev.map(b => `<blockquote>${esc(b.quote || b.label || '')}</blockquote>
      <span class="jg-loc">${[b.label, b.locator].filter(Boolean).map(esc).join(' · ')}</span>
      ${b.grade === 'material' ? '<span class="jg-loc">这是材料上的字，不是已核实的事实</span>' : ''}`).join('')}</div>` : ''}
    ${(j.dispute || []).length ? `<div class="jg-slot dis"><span class="jg-k">已知差异</span><ul>${j.dispute.map(d => `<li>${esc(d)}</li>`).join('')}</ul></div>` : ''}
    <div class="jg-slot cur"><span class="jg-k">当前判断</span><p class="jg-text">${esc(j.text)}</p>${j.plain ? `<p class="jg-plain">${esc(j.plain)}</p>` : ''}</div>
    ${(j.cannot || []).length ? `<div class="jg-slot no"><span class="jg-k">不能因此推出</span><ul>${j.cannot.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>` : ''}
    <footer class="jg-foot">
      <span class="jg-tag st-${st || 'ok'}">${esc(j.state_label)}</span>
      <span class="jg-scope">${esc(j.scope)}</span>
      ${j.since ? `<span class="jg-scope">第 ${j.since} 版起</span>` : ''}
      ${j.target ? `<button type="button" class="linkish" data-act="goto" data-id="${esc(j.target)}">报告里这一条</button>` : ''}
      ${refs.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(recordRefText(r))}</button>`).join('')}
    </footer>
    ${(j.premise || []).length ? `<details class="jg-more"><summary>什么前提下这条才成立</summary><ul>${j.premise.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>` : ''}
    ${(j.unknown || []).length ? `<details class="jg-more"><summary>还没证明的事</summary><ul>${j.unknown.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>` : ''}
    ${(j.history || []).length ? `<details class="jg-more"><summary>这条被改过 ${j.history.length} 次</summary><ul>${j.history.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>` : ''}
    ${j.state === 'needs_check' && !String(j.id).startsWith('ask.') ? `<div class="jg-act">
      <span class="muted small">你核实过之后，可以在这里给它下结论：</span>
      <button type="button" class="mini" data-act="resolve" data-id="${esc(j.id)}" data-do="clarified">核实过了，没问题</button>
      <button type="button" class="mini" data-act="resolve" data-id="${esc(j.id)}" data-do="withdrawn">是误判，撤掉这条</button>
    </div>` : ''}
  </article>`;
}

const FIVE_ORDER = ['cleared', 'found', 'recheck', 'unconfirmed', 'next_question', 'dropped', 'same'];

function fivePanel(v) {
  const cs = v.judgment_changes || [];
  const groups = FIVE_ORDER.map(k => [k, cs.filter(c => c.kind === k)]).filter(x => x[1].length);
  return `<p class="panel-lede">第 ${v.no} 版（${esc(v.trigger_label)}）和第 ${v.no - 1} 版按判断逐条比的，由程序算。新材料不会自动盖掉旧材料，对不上的两边都留着。</p>
    <div class="chg-why">${esc(v.judgment_summary || '')}</div>
    ${groups.map(([k, list]) => `<section class="f5 g-${k}">
      <header><span class="f5-k">${FIVE[k][0]}</span><span class="muted small">${FIVE[k][1]}</span><span class="jg-n">${list.length} 条</span></header>
      ${k === 'same'
        ? `<ul class="f5-same">${list.map(c => `<li><button type="button" class="linkish" data-act="goto" data-id="${esc(c.target)}">${esc(c.label)}</button></li>`).join('')}</ul>`
        : list.map(c => `<div class="chg">
            <div class="chg-h"><button type="button" class="linkish" data-act="goto" data-id="${esc(c.target)}">${esc(c.text || c.label)}</button></div>
            ${c.before && c.after && c.before !== c.after ? `<div class="ba"><s>${esc(c.before)}</s> → <b>${esc(c.after)}</b></div>` : ''}
            ${(c.because || []).length ? `<div class="chg-src">依据 ${c.because.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(recordRefText(r))}</button>`).join('')}</div>` : ''}
          </div>`).join('')}
    </section>`).join('')}`;
}

function changesPanel(v) {
  if (SHOW_JUDGMENTS && (v.judgment_changes || []).length) return fivePanel(v);
  const changed = v.changes.filter(x => x.kind !== 'unchanged');
  const same = v.changes.filter(x => x.kind === 'unchanged');
  return `<p class="panel-lede">第 ${v.no} 版（${esc(v.trigger_label)}）和第 ${v.no - 1} 版逐条比对的结果，由程序算出。</p>
    ${changed.length ? `<div class="chg-list">${changed.map(x => `<div class="chg ${x.kind}">
        <div class="chg-h"><span class="chg-k">${CHANGE[x.kind]}</span><button type="button" class="linkish" data-act="goto" data-id="${esc(x.target)}">${esc(x.label)}</button></div>
        <div class="ba">${x.before ? `<s>${esc(x.before)}</s> → ` : ''}<b>${esc(x.after || '这版没有了')}</b></div>
        ${x.after && x.plain.includes(x.after.slice(0, 12)) ? '' : `<p>${esc(x.plain)}</p>`}
        ${x.quote ? `<blockquote>${esc(x.quote)}</blockquote>` : ''}
        ${x.because.length ? `<div class="chg-src">依据 ${x.because.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(x.quote ? [x.quote] : []))}">${esc(recordRefText(r))}</button>`).join('')}</div>` : ''}
      </div>`).join('')}</div>`
      : `<p class="empty-line">${v.trigger === 'need' ? '公司的记录和它的说法都没变，每条判定也没变；变的是信号的排序、"第一问"和报告措辞。' : '新信息没有改变任何一条判断。'}</p>`}
    ${same.length ? `<details class="same"><summary>没变的 ${same.length} 项</summary><ul>${same.map(x => `<li><button type="button" class="linkish" data-act="goto" data-id="${esc(x.target)}">${esc(x.label)}</button>：${esc(x.after || x.before || '')}</li>`).join('')}</ul></details>` : ''}`;
}

// 第二层：四个信号。每张卡只列要看的，其余折叠
function signalsPanel(v, cm) {
  return `<p class="panel-lede">财务、信用、风险、口碑，排序跟着你的需求走。每张卡只列要看的，没问题和没查的折叠在下面。</p>
    <div class="signals">${v.signals.map(sig => signalCard(sig, cm, v)).join('')}</div>`;
}
function signalCard(sig, cm, v) {
  const flagged = sig.items.filter(i => FLAG.has(i.status));
  const rest = sig.items.filter(i => !FLAG.has(i.status));
  const open = S.openRest.has(sig.key) || !flagged.length && rest.length <= 2;
  const nOk = rest.filter(i => i.status === 'ok').length, nRef = rest.filter(isRef).length, unknown = rest.filter(i => isOpen(i) && !isRef(i));
  const restLabel = [nOk && `${nOk} 项没问题`, unknown.length && pendingNote(unknown), nRef && '用户评价只作参考'].filter(Boolean).join('、');
  // 没查不等于没问题：有没查（成）的项就不用绿色
  const head = flagged.length ? ['', `${flagged.length} 项要看`]
    : !nOk ? [' none', unknown.length && unknown.every(i => gapOf(i) === 'failed') ? '没查成，稍后重查' : '没查到数据']
    : unknown.length ? [' none', `查过的没问题，${pendingNote(unknown)}`] : [' zero', '查过的没问题'];
  return `<section class="sig" aria-labelledby="sig-${sig.key}">
    <header><h3 id="sig-${sig.key}">${esc(sig.title)}</h3><span class="flags${head[0]}">${head[1]}</span></header>
    <p class="sig-lede">${esc(sig.lede)}</p>
    ${flagged.map(it => itemHtml(sig.key, it, cm)).join('')}
    ${rest.length ? (open
      ? `<div class="rest">${rest.map(it => itemHtml(sig.key, it, cm)).join('')}</div>${flagged.length || rest.length > 2 ? `<button type="button" class="rest-tog" data-act="rest" data-key="${sig.key}">收起</button>` : ''}`
      : `<button type="button" class="rest-tog" data-act="rest" data-key="${sig.key}">另外 ${restLabel} ▾</button>`) : ''}
    ${sigExtra(sig, v)}
  </section>`;
}
function itemHtml(sigKey, it, cm) {
  const id = `${sigKey}.${it.key}`, seen = new Set();
  return `<div class="it s-${esc(it.status)}${selCls(id)}" data-item="${esc(id)}">
    <div class="it-h"><span class="it-l">${termText(it.label, seen)}</span>${it.value === stLabel(it) ? '' : `<span class="it-s">${stLabel(it)}</span>`}${chgTag(id, cm)}${askBtn(id)}</div>
    <div class="it-v">${termText(it.value, seen)}</div>
    ${it.detail ? `<div class="it-d">${termText(it.detail, seen)}</div>` : ''}
    <div class="it-m">${srcLink(it.source, it.ref)}</div>
  </div>`;
}
function seriesSvg(months, counts) {
  const max = Math.max(1, ...counts), w = 300, h = 64, bw = w / counts.length;
  return `<svg class="chart" viewBox="0 0 ${w} ${h + 14}" role="img" aria-label="每月投诉数">${counts.map((n, i) => {
    const bh = Math.round((n / max) * (h - 12));
    return `<rect x="${i * bw + 3}" y="${h - bh}" width="${bw - 6}" height="${bh}" fill="${i >= counts.length - 3 ? 'var(--red)' : 'var(--ink-3)'}" opacity=".8"/>`
      + `<text class="cv" x="${i * bw + bw / 2}" y="${h - bh - 2}" text-anchor="middle">${n}</text>`
      + `<text x="${i * bw + bw / 2}" y="${h + 11}" text-anchor="middle">${esc(String(months[i] || '').slice(5))}</text>`;
  }).join('')}</svg>`;
}
function sigExtra(sig, v) {
  const x = sig.extra;
  if (!x) return '';
  let out = '';
  // 新报告的投诉趋势画在"用图看"里；旧案卷没有图表，才在卡片里画
  if (Array.isArray(x.months) && Array.isArray(x.counts) && x.counts.length && !(v.charts || []).some(c => c.id === 'complaints')) {
    out += `<div class="chart-wrap">${seriesSvg(x.months, x.counts)}<div class="small muted">近 12 个月投诉数，红色是最近 3 个月。</div></div>`;
  }
  if (Array.isArray(x.web) && x.web.length) {
    out += `<details class="webhits"><summary>搜到的 ${x.web.length} 条公开报道和投诉</summary><ul>${x.web.map(hh => `<li>
      <a href="${esc(hh.url)}" target="_blank" rel="noopener noreferrer">${esc(hh.title)}</a>
      <div class="wm">${esc(hh.category || '其他')} · ${esc(hh.site || '')}${hh.date ? ' · ' + esc(hh.date) : ''}${hh.ref ? ` · <button type="button" class="cite" data-act="raw" data-ref="${esc(hh.ref)}">${esc(recordRefText(hh.ref))}</button>` : ''}</div>
      ${hh.excerpt ? `<div class="small">${esc(hh.excerpt)}</div>` : ''}</li>`).join('')}</ul></details>`;
  }
  // 企查查新闻舆情：只列它标为负面的；倾向是平台标的，不是我们的判断
  if (Array.isArray(x.news) && x.news.length) {
    out += `<details class="webhits"><summary>企查查标为负面的 ${x.news.length} 条新闻</summary><ul>${x.news.map(n => `<li>
      ${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title || '（无标题）')}</a>` : esc(n.title || '（无标题）')}
      <div class="wm">${esc(n.source || '')}${n.date ? ' · ' + esc(n.date) : ''}</div></li>`).join('')}</ul>
      <div class="small muted">"负面"是企查查的模型标的，标题不等于事实，点开看原文。</div></details>`;
  }
  // 权威媒体报道：只搜人民网、新华网、财新、证券时报等网站
  if (Array.isArray(x.media) && x.media.length) {
    out += `<details class="webhits"><summary>权威媒体的 ${x.media.length} 篇报道</summary><ul>${x.media.map(hh => `<li>
      <a href="${esc(hh.url)}" target="_blank" rel="noopener noreferrer">${esc(hh.title)}</a>
      <div class="wm">${esc(hh.category || '其他')} · ${esc(hh.site || '')}${hh.date ? ' · ' + esc(hh.date) : ''}${hh.ref ? ` · <button type="button" class="cite" data-act="raw" data-ref="${esc(hh.ref)}">${esc(recordRefText(hh.ref))}</button>` : ''}</div>
      ${hh.excerpt ? `<div class="small">${esc(hh.excerpt)}</div>` : ''}</li>`).join('')}</ul></details>`;
  }
  // 巨潮资讯网：最近一年标题带处罚、诉讼、问询字样的公告
  if (Array.isArray(x.notices) && x.notices.length) {
    out += `<details class="webhits"><summary>交易所公告里的 ${x.notices.length} 条（巨潮资讯网）</summary><ul>${x.notices.map(n => `<li>
      <a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>
      <div class="wm">${esc(n.category_label || '')}${n.date ? ' · ' + esc(n.date) : ''}</div></li>`).join('')}</ul>
      <div class="small muted">按标题关键词挑出来的，标题不等于结论，点开看公告原文。</div></details>`;
  }
  // 企查查财务数据：近几年年报，只列数
  if (Array.isArray(x.reports) && x.reports.length) {
    out += `<table class="fin-t"><thead><tr><th>年报</th><th>营业收入</th><th>同比</th><th>净利润</th></tr></thead><tbody>${x.reports.map(r => `<tr>
      <td>${esc(r.period)}</td><td>${esc(r.revenue)}</td><td>${esc(r.revenue_yoy)}</td><td>${esc(r.net_profit)}</td></tr>`).join('')}</tbody></table>
      <div class="small muted">企查查汇总的定期报告数据，以公司公告原文为准。</div>`;
  }
  return out;
}

// 第三层：宣称 vs 记录
function claimsPanel(v, cm) {
  const t = v.tally || {};
  const parts = [['red', '条与记录不符或不合规'], ['amber', '条有误导或要留意'], ['grey', '条无法核验'], ['green', '条与记录相符']]
    .filter(([k]) => t[k]).map(([k, l]) => `<span class="t ${k}"><b>${t[k]}</b>${l}</span>`);
  if (t.missing) parts.push(`<span class="t amber"><b>${t.missing}</b>处该写没写</span>`);
  if (!v.assertions.length && !v.missing.length) {
    return `<div class="empty"><p>还没有这家公司的说法。拍一份它的合同、宣传单或聊天记录，就能拿它的每句话去对照官方记录。</p><div class="head-acts"><button type="button" class="btn sm cam" data-act="contract">📷 拍合同 · 二次审核</button><button type="button" class="btn sm ghost" data-act="supplement" data-kind="material">上传图片 / PDF / Word</button></div></div>`;
  }
  return `<p class="panel-lede">对方的每条说法，都拿官方记录和法规对一遍。判定由固定规则给出，不由 AI 决定。</p>
    <div class="tally-line">${parts.join('')}</div>
    <div class="claims">${v.assertions.map(a => claimCard(a, cm)).join('')}</div>
    ${v.missing.length ? `<h4 class="sub-h">该写却没写</h4><div class="claims">${v.missing.map(m => { const seen = new Set(); return `<article class="claim c-miss${selCls(m.id)}" data-item="${esc(m.id)}">
        <div class="cl-h"><q>${termText(m.text, seen)}</q><span class="verdict">该写没写</span>${chgTag(m.id, cm)}${askBtn(m.id)}</div>
        <p class="cl-p">${termText(m.plain, seen)}</p>
        <div class="cl-f">${srcLink(m.source)}${m.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}">看材料${hideRecordIds() ? '' : ` ${esc(r)}`}</button>`).join('')}</div></article>`; }).join('')}</div>` : ''}`;
}
function claimCard(a, cm) {
  const seen = new Set();   // 对方原话里的词（"保本保息""资金存管"）最需要解释，先标
  return `<article class="claim ${esc(a.color)}${selCls(a.id)}" data-item="${esc(a.id)}">
    <div class="cl-h"><q>${termText(a.text, seen)}</q><span class="verdict">${esc(a.verdict_label)}</span>${chgTag(a.id, cm)}${askBtn(a.id)}</div>
    <p class="cl-p"><span class="ckind">${termText(a.kind_label, seen)}</span>${termText(a.plain, seen)}</p>
    <div class="cl-f">
      ${a.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(a.quotes))}">看原文${hideRecordIds() ? '' : ` ${esc(r)}`}</button>`).join('')}
      <details><summary>怎么查的（${a.checks.length} 项）</summary><ul class="checks">${a.checks.map(ck => `<li class="s-${esc(ck.status)}">
        <span class="ck-l">${termText(ck.label, seen)}</span><span class="ck-s">${stLabel(ck)}</span><div>${termText(ck.result, seen)}</div>${srcLink(ck.source, ck.ref)}</li>`).join('')}</ul></details>
    </div>
  </article>`;
}

function questionsPanel(v) {
  if (!v.questions.length) return '<p class="empty-line">暂时没有要追问的。</p>';
  return `<p class="panel-lede">拿到回复后，点上面的"补充信息"，选"对方的回复"贴进来，系统会重新判断。</p>
    <ol class="qs">${v.questions.map(q => { const seen = new Set(); return `<li class="${selCls(q.id).trim()}" data-item="${esc(q.id)}">
      <div class="q-h"><span class="q-ask">${termText(q.ask, seen)}</span>${askBtn(q.id)}</div>
      <div class="q-why">${termText(q.why, seen)}</div>
      <div class="q-where">拿到答案后：${termText(q.check_where, seen)}</div></li>`; }).join('')}</ol>`;
}

// 第四层：原始数据
function rawPanel(v) {
  const raws = versionRaws(v);
  const n = k => raws.filter(r => r.coverage === k).length;
  return `<p class="panel-lede">每次取数据都原样留一条记录。点开看原文、来源链接、采集时间，以及报告里哪些结论用到了它。</p>
    <div class="cov-sum">共 ${raws.length} 条：${Object.entries(COVERAGE).map(([k, l]) => `<span class="covl ${k}">${l} ${n(k)}</span>`).join(' · ')}</div>
    <div class="raws">${raws.map(r => {
      const s = srcOf(r.source_id), kind = rawKind(r);
      return `<button type="button" class="raw-row" data-act="raw" data-ref="${esc(r.id)}" data-item="${esc(r.id)}">
        ${hideRecordIds() ? '' : `<span class="rid">${esc(r.id)}</span>`}
        <span class="rt">${esc(r.title)}<small>${esc(r.note || (s ? s.name : ''))}${r.as_of ? ` · 截至 ${esc(r.as_of)}` : ''}</small></span>
        <span class="k-${esc(kind)} rk">${esc(KIND[kind] || r.kind)}</span>
        <span class="covl ${esc(r.coverage)}">${COVERAGE[r.coverage] || ''}</span>
      </button>`;
    }).join('')}</div>`;
}

// ---------- 评价：按公司存，用户个人观点，未经核实 ----------
// 星级只给分布，不算平均分。报告只看差评是否集中：集中才在"口碑"里标"要留意"，好评不标绿。

const REL = { customer: '客户', employee: '员工', applicant: '求职者', other: '其他' };
// 浏览器里的匿名编号：同一个浏览器对同一家公司只能写一条。存不下来（隐私窗口）就每次打开页面换一个
const AUTHOR = (() => {
  let id = null;
  try { id = localStorage.getItem('xray.author'); } catch { /* 存不了 */ }
  if (!id) {
    id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try { localStorage.setItem('xray.author', id); } catch { /* 存不了 */ }
  }
  return id;
})();
const reviewItemOf = v => { for (const s of v.signals) for (const i of s.items) if (i.key === 'user_reviews') return i; return null; };
const starStr = n => '★'.repeat(n) + '☆'.repeat(5 - n);

async function loadReviews() {
  const company = S.case.case.company_name;
  let got;
  try { got = await api(`/api/reviews?company=${encodeURIComponent(company)}&author=${encodeURIComponent(AUTHOR)}`); }
  catch (e) { got = { company, count: 0, dist: {}, reviews: [], error: e.message }; }
  if (!S.case || S.case.case.company_name !== company) return;
  // 已经有数据时只更新标签上的数字，不重画面板，免得冲掉正在写的评价
  const first = !S.reviews;
  S.reviews = got;
  refreshReviewTab(first);
}
function refreshReviewTab(rerender = true) {
  const n = $('.tabs .tab[data-tab="reviews"] .n');
  if (n && S.reviews) n.textContent = S.reviews.count;
  const reviewBody = $('#research-reviews-body');
  if (reviewBody && rerender) reviewBody.innerHTML = document.body.classList.contains('dossier-live') ? dossierReviews(ver()) : reviewsPanel(ver());
  else if (S.tab === 'reviews' && rerender) renderPanel();
}

function reviewsPanel(v) {
  const R = S.reviews;
  if (!R) return '<p class="empty-line">读取评价…</p>';
  const snap = versionRaws(v).find(r => r.source_id === 'user_reviews');
  const inVer = snap && Array.isArray(snap.content) ? snap.content.length : 0;
  const fresh = R.count - inVer;
  const latest = v.no === S.case.versions[S.case.versions.length - 1].no;
  const max = Math.max(1, ...Object.values(R.dist || {}));
  const item = reviewItemOf(v);
  const mine = R.reviews.some(r => r.mine);
  const dist = [5, 4, 3, 2, 1].map(st => {
    const c = (R.dist || {})[st] || 0;
    return `<div class="rv-bar${st <= 2 ? ' low' : ''}"><span>${st} 星</span><i><b style="width:${(c / max) * 100}%"></b></i><em>${c}</em></div>`;
  }).join('');
  return `<div class="rv-note"><b>用户个人观点，未经核实。</b>系统不判断真假，也不算平均分。报告只看差评是否集中：集中才在"口碑"里标"要留意"；好评再多，也不算放心的理由。</div>
    ${R.error ? `<p class="err">评价没读出来：${esc(R.error)}</p>` : ''}
    <div class="rv-top">
      <div class="rv-dist" aria-label="星级分布">${dist}<p class="small muted">共 ${R.count} 条${R.count ? '' : '，还没有人写'}</p></div>
      <div class="rv-in"><span class="kicker">这一版报告里</span>${item
        ? `<div class="rv-in-v s-${esc(item.status)}"><b>${esc(item.value)}</b><span>${esc(stLabel(item))}</span></div><p class="small">${esc(item.detail || '')}</p><button type="button" class="linkish small" data-act="goto" data-id="reputation.user_reviews">看口碑里这一条 →</button>`
        : '<p class="small muted">还没有评价进这一版报告。评价进报告后，只出现在"口碑"里的一条，不进一页结论。</p>'}</div>
    </div>
    ${fresh > 0 ? `<div class="rv-fresh"><span>有 ${fresh} 条评价还没进这一版报告。</span>${latest
      ? `<button type="button" class="btn sm" data-act="rv-refresh">放进报告，出第 ${S.case.versions.length + 1} 版</button>`
      : '<span class="small muted">切到最新一版才能放进去。</span>'}</div>` : ''}
    ${mine ? '<p class="rv-done small">你已经给这家公司写过一条。同一个浏览器对同一家公司只能写一条。</p>' : reviewFormHtml()}
    <div class="rv-list">${R.reviews.map(reviewHtml).join('')}</div>`;
}
function reviewFormHtml() {
  return `<form class="rv-form experience-form" id="rvForm" novalidate>
    <h4>写一条评价</h4>
    <div class="rv-row"><span class="lbl">打几星</span><span class="stars" role="group" aria-label="星级">${[1, 2, 3, 4, 5].map(n => `<button type="button" class="star" data-act="rv-star" data-n="${n}" aria-pressed="${n <= S.rvStars}" aria-label="${n} 星">★</button>`).join('')}</span><span class="small muted" id="rvStarTxt">${S.rvStars ? `${S.rvStars} 星` : ''}</span></div>
    <div class="rv-row"><span class="lbl">你是它的</span><span class="seg">${Object.entries(REL).map(([k, l]) => `<button type="button" data-act="rv-rel" data-rel="${k}" aria-pressed="${S.rvRel === k}">${l}</button>`).join('')}</span></div>
    <textarea class="big-inp sm" name="text" rows="3" maxlength="500" placeholder="写你遇到的事：对方怎么说的、钱打到哪、能不能取出来。10–500 字。手机号、身份证号会自动遮掉。"></textarea>
    <div class="rv-row"><input class="big-inp sm" name="nickname" maxlength="20" placeholder="昵称（选填，不填显示匿名用户）"><button type="submit" class="btn sm">发布评价</button></div>
    <p class="small muted">没有账号，防不了刷：同一个浏览器对同一家公司只能写一条。发布后所有人都能看到。</p>
    <div class="err" id="rvErr" role="alert"></div>
  </form>`;
}
function reviewHtml(r) {
  return `<article class="rv${r.mine ? ' mine' : ''}">
    <div class="rv-h"><span class="rv-stars${r.stars <= 2 ? ' low' : ''}" aria-label="${r.stars} 星">${starStr(r.stars)}</span><b>${esc(r.nickname || '匿名用户')}</b><span class="rv-rel">${esc(r.relation_label)}</span>${r.demo ? '<span class="rv-tag demo">演示数据</span>' : ''}${r.mine ? '<span class="rv-tag mine">你写的</span>' : ''}<time>${esc(fmtTime(r.created_at).slice(0, 10))}</time></div>
    <p>${esc(r.text)}</p></article>`;
}
async function submitReview(f) {
  const err = $('#rvErr'), text = f.text.value.trim();
  err.textContent = '';
  if (!S.rvStars) { err.textContent = '先选几星'; return; }
  if (!S.rvRel) { err.textContent = '选一下你和这家公司的关系'; return; }
  if (text.length < 10) { err.textContent = '至少写 10 个字，说说具体遇到了什么事'; return; }
  const company = S.case.case.company_name, hash = location.hash, request = routeRequest;
  const stillHere = () => f.isConnected && request === routeRequest && S.case?.case.company_name === company && location.hash === hash;
  const btn = f.querySelector('[type="submit"]');
  btn.disabled = true; btn.textContent = '正在发布…';
  try {
    const reviews = await api('/api/reviews', { method: 'POST', body: { company, stars: S.rvStars,
      relation: S.rvRel, text, nickname: f.nickname.value.trim() || null, author: AUTHOR } });
    if (!stillHere()) { toast('原评价已发布，可在「案卷」查看'); return; }
    S.reviews = reviews;
    S.rvStars = 0; S.rvRel = null;
    refreshReviewTab();
    toast('已发布。报告要算进这条，点"放进报告"');
  } catch (e) {
    if (!stillHere()) { toast('原评价的发布未能确认，请到「案卷」查看', true); return; }
    err.textContent = '没发出去：' + e.message;
    btn.disabled = false; btn.textContent = '发布评价';
  }
}
async function refreshReviews(el) {
  const caseId = S.case.id, version = ver().no, hash = location.hash, request = routeRequest;
  const stillHere = () => el.isConnected && request === routeRequest && S.case?.id === caseId && ver()?.no === version && location.hash === hash;
  el.disabled = true; el.textContent = '正在重新判断…';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(caseId)}/reviews`, { method: 'POST' });
    if (!stillHere()) { toast(`原案卷已更新至第 ${c.current} 版，可在「案卷」查看`); return; }
    S.case = c; S.opCache = {}; S.tab = 'changes';
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    setTimeout(() => { if (location.hash !== target || S.case?.id !== c.id) return; const t = $('.chg-banner'); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    toast(`已生成第 ${c.current} 版`);
  } catch (e) {
    if (!stillHere()) { toast('原案卷的更新未能确认，请到「案卷」查看', true); return; }
    toast('没生成出来：' + e.message, true);
    el.disabled = false; el.textContent = '放进报告';
  }
}

// ---------- 原始数据弹窗 ----------

function backRefs(rid) {
  const v = ver(), out = [];
  for (const a of v.assertions) if (a.refs.includes(rid) || a.checks.some(ck => ck.ref === rid)) out.push([a.id, `它说的"${a.kind_label}"`]);
  for (const m of v.missing) if (m.refs.includes(rid)) out.push([m.id, `该写没写：${m.text}`]);
  for (const sig of v.signals) for (const it of sig.items) if (it.ref === rid) out.push([`${sig.key}.${it.key}`, `${sig.title} · ${it.label}`]);
  return out;
}
function markText(text, quotes) {
  const source = String(text ?? '');
  const parts = [...new Set((quotes || []).filter(q => typeof q === 'string' && q.trim().length >= 2))]
    .sort((a, b) => b.length - a.length).map(q => q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!parts.length) return esc(source);
  let out = '', end = 0;
  for (const m of source.matchAll(new RegExp(parts.join('|'), 'g'))) {
    out += esc(source.slice(end, m.index)) + `<mark>${esc(m[0])}</mark>`;
    end = m.index + m[0].length;
  }
  return out + esc(source.slice(end));
}
function valHtml(val, quotes = []) {
  if (val == null || val === '') return '<span class="muted">—</span>';
  if (typeof val === 'boolean') return val ? '是' : '否';
  if (typeof val === 'object') return `<pre class="json">${markText(JSON.stringify(val, null, 2), quotes)}</pre>`;
  return markText(val, quotes);
}
function contentHtml(content, quotes) {
  if (content == null) return '<p class="muted">这条记录没有内容（没查或查询失败）。</p>';
  if (typeof content === 'string') return `<pre>${markText(content, quotes)}</pre>`;
  const table = obj => `<table>${Object.entries(obj).map(([k, val]) => `<tr><th>${esc(k)}</th><td>${valHtml(val, quotes)}</td></tr>`).join('')}</table>`;
  if (Array.isArray(content)) {
    if (!content.length) return '<p class="muted">空列表。</p>';
    return content.map(it => `<div class="item">${it && typeof it === 'object' && !Array.isArray(it) ? table(it) : valHtml(it, quotes)}</div>`).join('');
  }
  return table(content);
}
function sourceUrl(url) {
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}
function openRaw(rid, quotes) {
  const r = rawById(rid);
  if (!r) { toast(hideRecordIds() ? '这条来源记录暂不可用' : `案卷里没有 ${rid}`, true); return; }
  const s = srcOf(r.source_id), back = backRefs(rid), kind = rawKind(r);
  const dlg = $('#rawDlg');
  dlg.innerHTML = `<div class="dlg-in">
    <div class="dlg-head"><div><div class="kicker">${hideRecordIds() ? '来源原文' : `原始数据 ${esc(r.id)}`} · <span class="k-${esc(kind)}">${esc(KIND[kind] || r.kind)}</span> · <span class="covl ${esc(r.coverage)}">${COVERAGE[r.coverage] || ''}</span></div>
      <h3 id="rawTitle">${esc(r.title)}</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <dl class="kv">
        <dt>来源</dt><dd>${esc(s ? s.name : r.source_id)}${s && s.note ? `<div class="small muted">${esc(s.note)}</div>` : ''}</dd>
        ${r.as_of ? `<dt>数据截至</dt><dd class="mono">${esc(r.as_of)}</dd>` : ''}
        <dt>采集时间</dt><dd class="mono">${esc(fmtTime(r.retrieved_at))}</dd>
        ${sourceUrl(r.url) ? `<dt>原文链接</dt><dd><a href="${esc(sourceUrl(r.url))}" target="_blank" rel="noopener noreferrer">打开原文网站 ↗</a></dd>` : ''}
        ${r.screenshot ? `<dt>截图</dt><dd>${esc(r.screenshot)}</dd>` : ''}
      </dl>
      ${kind === 'demo' ? '<div class="raw-note">演示数据：这家公司和这条记录都是编的，只用来演示。</div>' : ''}
      ${r.note ? `<div class="raw-note">${esc(r.note)}</div>` : ''}
      <div class="raw-content">${contentHtml(r.content, quotes)}</div>
      ${back.length ? `<div class="backrefs"><h4>报告里用到这条数据的地方</h4><div class="chips">${back.map(([id, label]) => `<button type="button" class="chip" data-act="goto" data-id="${esc(id)}">${esc(label)}</button>`).join('')}</div></div>` : ''}
    </div></div>`;
  if (!dlg.open) dlg.showModal();
  const m = $('mark', dlg);
  if (m) m.scrollIntoView({ block: 'center' });
}
function showSource(el, id) {
  const s = srcOf(id);
  if (!s) return;
  popAt(el, `<h5>${esc(s.name)}</h5><p>${esc(KIND[s.kind] || s.kind)}${s.as_of ? ` · ${esc(s.as_of)}` : ''}</p>${s.note ? `<p style="margin-top:6px">${esc(s.note)}</p>` : ''}${s.url ? `<p style="margin-top:6px"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">打开出处</a></p>` : ''}<p class="small" style="margin-top:6px;opacity:.75">这一条依据的是法规或参数，不是一次查询，所以没有原始数据编号。</p>`);
}

// ---------- 浮层 ----------

function popAt(el, html) {
  const p = $('#pop');
  const host = el.closest('#signalDlg') || document.body;
  if (p.parentElement !== host) host.append(p);
  p.innerHTML = `<button type="button" class="x" data-act="close-pop" aria-label="关闭">×</button>${html}`;
  p.hidden = false;
  const r = el.getBoundingClientRect();
  const left = Math.min(Math.max(12, r.left), window.innerWidth - p.offsetWidth - 12);
  const below = r.bottom + 8 + p.offsetHeight < window.innerHeight;
  p.style.left = `${left}px`;
  p.style.top = `${below ? r.bottom + 8 : Math.max(12, r.top - p.offsetHeight - 8)}px`;
}
const closePop = () => { $('#pop').hidden = true; };

// ---------- 选中与跳转 ----------

function toggleSel(id) {
  if (S.selected.has(id)) S.selected.delete(id);
  else { if (S.selected.size >= 10) { toast('最多同时选 10 条'); return; } S.selected.add(id); }
  refreshSel();
  if (S.selected.has(id) && window.matchMedia('(max-width:1280px)').matches) toast(`已选中 ${id}，点右下角"小企"提问`);
}
function refreshSel() {
  $$('.ask').forEach(b => {
    const on = S.selected.has(b.dataset.id);
    b.setAttribute('aria-pressed', on); b.textContent = on ? '已选' : (b.dataset.idleLabel || '问');
  });
  $$('#panel [data-item], #signalDlg [data-item], #research-inquiry [data-item]').forEach(el => el.classList.toggle('is-sel', S.selected.has(el.dataset.item) && !el.classList.contains('raw-row')));
  const box = $('#asSel');
  if (box) box.innerHTML = selHtml();
  const fab = $('.fab');
  if (fab) fab.innerHTML = qiLauncherContent();
}
function tabFor(id) {
  if (/^[AM]\d+$/.test(id)) return 'claims';
  if (/^Q\d+$/.test(id)) return 'questions';
  if (id.includes('.')) return 'signals';
  return null;
}
function selectRefVersion(version) {
  if (version == null || version === ver().no) return true;
  if (!S.case.versions.some(v => v.no === version)) { toast(`案卷里没有第 ${version} 版`); return false; }
  S.viewNo = version; S.selected.clear(); S.openRest.clear();
  history.replaceState(null, '', `#/case/${S.case.id}/v/${version}`);
  renderCase();
  return true;
}
function gotoItem(ref, version = null, anchorEl = null) {
  const target = parseRef(ref, version);
  if (!selectRefVersion(target.version)) return;
  const id = target.id;
  if ($('#questionDlg')?.open) $('#questionDlg').close();
  if (/^Q\d+$/.test(id) && typeof openResearchQuestion === 'function' && isDesignReview()) {
    const index = ver().questions.findIndex(q => q.id === id);
    if (index < 0) { toast(`这一版报告里没有 ${id}`); return; }
    openResearchQuestion(index); return;
  }
  if (id.startsWith('term.')) {
    const anchor = anchorEl?.isConnected ? anchorEl : $('#assist');
    termPop(anchor, id.slice(5)); return;
  }
  if (/^R\d+$/.test(id)) { openRaw(id); return; }
  if ($('#rawDlg').open) $('#rawDlg').close();
  if (window.matchMedia('(max-width:1280px)').matches) $('#assist') && $('#assist').classList.remove('open');
  const tab = tabFor(id);
  if (!tab) { toast(`这一版报告里没有 ${id}`); return; }
  if (tab === 'signals') {   // 折叠着的条目先展开
    const key = id.split('.')[0];
    const sig = ver().signals.find(s => s.key === key);
    const it = sig && sig.items.find(i => `${key}.${i.key}` === id);
    if (it && !FLAG.has(it.status)) S.openRest.add(key);
    if (typeof isDesignReview === 'function' && isDesignReview()) {
      if (!it) { toast(`这一版报告里没有 ${id}`); return; }
      openResearchSignal(key, id); return;
    }
  }
  if ($('#signalDlg')?.open) $('#signalDlg').close();
  if (typeof researchNavigate === 'function' && isDesignReview()) {
    researchNavigate(tab, false);
    const item = $(`#research-inquiry [data-item="${CSS.escape(id)}"]`);
    if (!item) { toast(`这一版报告里没有 ${id}`); return; }
    for (let parent = item.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    item.scrollIntoView({ behavior: 'smooth', block: 'center' });
    item.classList.remove('flash'); void item.offsetWidth; item.classList.add('flash');
    return;
  }
  S.tab = tab; renderPanel();
  const el = $(`#panel [data-item="${CSS.escape(id)}"]`);
  if (!el) { toast(`这一版报告里没有 ${id}`); return; }
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
}

// ---------- 小企（AI 栏）----------

function qiThinking() {
  return S.busy && S.case?.id === S.busyCaseId && /^#\/case\//.test(location.hash);
}
function qiSpriteHtml() {
  return `<span class="qi-sprite" data-qi-state="${qiThinking() ? 'thinking' : 'idle'}" aria-hidden="true"></span>`;
}
function qiAvatarHtml() {
  return `<button type="button" class="qi-avatar" data-act="open-assist" aria-label="向小企提问" title="向小企提问">${qiSpriteHtml()}</button>`;
}
function qiLauncherContent() {
  return `${qiSpriteHtml()}<span class="qi-fab-caption"><b>小企</b><span data-qi-caption>${qiThinking() ? '思考中…' : '问问报告'}</span></span>${S.selected.size ? `<em aria-label="已选 ${S.selected.size} 条">${S.selected.size}</em>` : ''}`;
}
function qiLauncherHtml() {
  return `<button type="button" class="fab" data-act="open-assist" aria-label="打开小企，询问报告" aria-controls="assist">${qiLauncherContent()}</button>`;
}
function refreshQiState() {
  const thinking = qiThinking();
  $$('[data-qi-state]').forEach(el => { el.dataset.qiState = thinking ? 'thinking' : 'idle'; });
  $$('[data-qi-caption]').forEach(el => { el.textContent = thinking ? '思考中…' : '问问报告'; });
  const submit = $('#asForm button[type="submit"]');
  if (submit) { submit.disabled = thinking; submit.textContent = thinking ? '等待中' : '问'; }
}

function modeLine() {
  const llm = S.health && S.health.llm;
  if (!llm) return '';
  if (!llm.configured || llm.mode === 'off') return '模型未连接：暂时提供基础解释和核对步骤，企业事实仍以案卷为依据。';
  if (llm.mode === 'replay') return '离线回放：只用录好的模型回答。';
  return '帮你看懂资料，也一起梳理顾虑和下一步。企业事实有出处，未核实的会说明。';
}
function assistHtml() {
  return `<div class="as-head"><div class="as-heading"><h3>小企 <span class="qi-role">报告助手</span></h3><p class="small muted">${esc(modeLine())}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="收起小企">×</button></div>
  <div class="as-body" id="asBody">${chatHtml()}</div>
  <div class="qi-perch">${qiAvatarHtml()}</div>
  <div class="as-sel" id="asSel">${selHtml()}</div>
  <form class="as-input" id="asForm"><textarea class="box" name="q" rows="2" maxlength="2000" placeholder="想了解报告，或对下一步有顾虑？（Enter 发送）" aria-label="提问"></textarea><button class="btn sm" type="submit">问</button></form>`;
}
function selHtml() {
  if (!S.selected.size) return '<span class="muted">想问某一条？点报告里那一条右边的"问"。</span>';
  return `<span class="muted">针对：</span>${[...S.selected].map(id => `<span class="sel-chip">${esc(refLabel(id))}<button type="button" data-act="unsel" data-id="${esc(id)}" aria-label="取消选中 ${esc(refLabel(id))}">×</button></span>`).join('')}`;
}
function chatHtml() {
  const chat = S.case.chat;
  const sugg = ['它有没有资格收这笔钱？', '还有哪些没查到？', '我该先问对方什么？', '它被处罚或点名过吗？'];
  const intro = `<div class="as-intro"><div class="chips">${sugg.map(q => `<button type="button" class="chip" data-act="ask" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <p class="small muted">聊天和上传材料仅此浏览器可见。小企不会改报告；新情况要点“加入案卷”才会重新判断。</p></div>`;
  const pending = pendingChat(S.case.id);
  return (chat.length ? '' : intro) + chat.map((m, i) => msgHtml(m, chat[i - 1], i)).join('') + (qiThinking()
    ? '<div class="typing" role="status"><span>小企正在整理回答</span><i aria-hidden="true"></i><i aria-hidden="true"></i><i aria-hidden="true"></i><button type="button" class="linkish" data-act="cancel-chat">停止等待</button></div>'
    : pending ? '<div class="chat-recovery"><p>上次提问的结果尚待确认，不必重复提交。</p><button type="button" class="linkish" data-act="recover-chat">恢复回答</button></div>' : '');
}
function citeText(text, version) {
  return esc(text).replace(/\[([A-Za-z0-9_.:,，、\s]+)\]/g, (all, inner) => {
    const ids = inner.split(/[,，、\s]+/).filter(Boolean);
    return ids.length && ids.every(isId) ? ids.map(id => goLink(id, version)).join('') : all;
  });
}
function answerText(text) {
  return esc(String(text || '').replace(/\[([A-Za-z0-9_.:,，、\s]+)\]/g, (all, inner) => {
    const ids = inner.split(/[,，、\s]+/).filter(Boolean);
    return ids.length && ids.every(isId) ? '' : all;
  }).replace(/[ \t]+\n/g, '\n').trim());
}
function answerCitations(m) {
  const inline = [...String(m.text || '').matchAll(/\[([A-Za-z0-9_.:,，、\s]+)\]/g)]
    .flatMap(match => match[1].split(/[,，、\s]+/));
  return [...new Set([...(m.citations || []), ...(m.quotes || []).map(q => q.ref), ...inline])]
    .filter(id => isId(id) && (parseRef(id, m.version).version === m.version));
}
function chatSourcesHtml(m) {
  const v = S.case?.versions.find(v => v.no === m.version);
  if (!v) return '<p>这条回答对应的报告版本暂不可用。</p>';
  const rawIds = new Set(), extras = [];
  for (const ref of answerCitations(m)) {
    const id = parseRef(ref, m.version).id;
    if (/^R\d+$/.test(id)) { rawIds.add(id); continue; }
    if (id.startsWith('term.')) {
      // A new explanation may use a corrected definition absent from an older
      // report. Keep its saved knowledge snapshot with the answer; never rewrite
      // report-version terminology or silently display a different definition.
      const termId = id.slice(5);
      const term = (m.knowledge_terms || []).find(t => t.id === termId)
        || (v.terms || []).find(t => t.id === termId)
        || S.terms.find(t => t.id === termId);
      if (term) extras.push(`<section class="chat-source"><h4>名词解释 · ${esc(term.term)}</h4><p>${esc(term.plain)}</p>${term.why ? `<p>${esc(term.why)}</p>` : ''}<p class="small muted">通用名词解释，不代表企业情况。</p><p class="small muted">${term.origin === 'model' ? 'AI 解释，未经人工核对；不是企业事实证据。' : esc(term.law || '案卷名词表；不是企业事实证据。')}</p></section>`);
      continue;
    }
    const entry = [...(v.assertions || []), ...(v.missing || []), ...(v.questions || [])].find(x => x.id === id)
      || (v.signals || []).flatMap(s => s.items.map(i => ({...i, id: `${s.key}.${i.key}`}))).find(x => x.id === id);
    const refs = entry ? [...(entry.refs || []), entry.ref, ...(entry.checks || []).map(c => c.ref)].filter(Boolean) : [];
    refs.filter(r => /^R\d+$/.test(r)).forEach(r => rawIds.add(r));
    if (!refs.some(r => /^R\d+$/.test(r))) {
      const label = entry?.label || entry?.kind_label || entry?.ask || entry?.text;
      extras.push(`<section class="chat-source"><p>报告条目（可能包含规则判断或待核实问题，不等于外部原文）</p>${goLink(id, m.version, label ? `查看报告条目：${label}` : '查看对应报告条目')}</section>`);
    }
  }
  const records = [...rawIds].filter(id => (v.raw_ids || []).includes(id)).map(rawById).filter(Boolean);
  return records.map(r => {
    const source = (v.sources || S.case.sources || {})[r.source_id];
    const quotes = (m.quotes || []).filter(q => q.ref === r.id).map(q => q.text);
    return `<section class="chat-source"><h4>${esc(r.title)}</h4><p class="small muted">${esc(source?.name || r.source_id)} · ${esc(KIND[rawKind(r)] || r.kind)} · 第 ${v.no} 版</p>
      <p class="small muted">采集：${esc(fmtTime(r.retrieved_at))}${r.as_of ? ` · 数据截至：${esc(r.as_of)}` : ''}</p>
      ${quotes.map(q => `<blockquote>${markText(q, [q])}</blockquote>`).join('')}
      <button type="button" class="linkish" data-act="raw" data-ref="${esc(r.id)}" data-version="${v.no}" data-hl="${esc(JSON.stringify(quotes))}">查看完整记录</button>
      ${sourceUrl(r.url) ? `<a class="linkish" href="${esc(sourceUrl(r.url))}" target="_blank" rel="noopener noreferrer">原文网站 ↗</a>` : ''}</section>`;
  }).join('') + extras.join('');
}
function openChatSources(index) {
  const m = S.case?.chat[index];
  if (!m || m.role !== 'assistant') return;
  const dlg = $('#rawDlg');
  dlg.innerHTML = `<div class="dlg-in"><div class="dlg-head"><h3 id="rawTitle">原文出处 · 第 ${m.version} 版</h3><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div><div class="dlg-body">${chatSourcesHtml(m) || '<p>暂无可打开的原始记录。</p>'}</div></div>`;
  if (!dlg.open) dlg.showModal();
}
function msgHtml(m, prev, index = 0) {
  if (m.role === 'user') {
    return `<div class="msg me"><div class="bubble">${esc(m.text)}</div>
      ${m.refs && m.refs.length ? `<div class="msg-refs">针对 ${m.refs.map(id => goLink(id, m.version)).join('')}</div>` : ''}</div>`;
  }
  const add = (m.suggest || []).filter(s => s.includes('加入案卷'));
  const other = (m.suggest || []).filter(s => !s.includes('加入案卷'));
  const vNote = S.case && m.version !== ver().no ? `<span>基于第 ${m.version} 版</span>` : '';
  const answerKind = m.answer_kind === 'glossary' ? '<span>名词解释</span>' : m.answer_kind === 'clarification' ? '<span>先确认需求</span>' : '';
  const mode = answerKind + (m.mode === 'replay' ? `<span>离线回放${m.recorded_at ? ` · ${esc(fmtTime(m.recorded_at))}` : ''}</span>` : m.mode === 'template' && !answerKind ? '<span>当前为基础答复</span>' : '');
  const filtered = m.has_omitted_claims === true;
  return `<div class="msg ai${m.not_found ? ' nf' : ''}${m.mode === 'guard' ? ' guard' : ''}">
    <div class="ans">${answerText(m.text)}</div>
    ${other.length ? `<ul class="chat-next">${other.map(s => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}
    ${add.length && prev && prev.role === 'user' ? `<div class="add-case">你提到的像是新情况。<button type="button" class="btn sm" data-act="supplement" data-kind="reply" data-text="${esc(prev.text)}">加入案卷，重新判断</button></div>` : ''}
    <div class="msg-meta">${mode}${m.error_code ? '<span>本次材料处理未完成，不是企业风险结论</span>' : m.not_found ? '<span>部分信息仍待核实</span>' : filtered ? '<span>部分表述未获依据支持，已省略</span>' : ''}${m.context_mode === 'selective' ? '<span>按需核对相关材料</span>' : ''}${vNote}</div>
    ${answerCitations(m).length ? `<div class="msg-refs chat-source-footer"><button type="button" class="linkish" data-act="chat-sources" data-index="${index}" aria-label="查看这条回答的原文出处">原文出处 ↗</button></div>` : ''}
  </div>`;
}
function refreshChat() {
  refreshQiState();
  const body = $('#asBody');
  if (body) { body.innerHTML = chatHtml(); scrollChat(); }
}
function scrollChat() { const b = $('#asBody'); if (b) b.scrollTop = b.scrollHeight; }

const pendingChats = new Map();
function pendingChat(caseId) {
  if (pendingChats.has(caseId)) return pendingChats.get(caseId);
  try {
    const value = JSON.parse(sessionStorage.getItem(`qier-chat:${caseId}`) || 'null');
    if (value && typeof value.key === 'string' && value.body?.text && Number.isInteger(value.body.version)) return value;
  } catch { /* Storage can be disabled; the current page still keeps its request key. */ }
  return null;
}
function savePendingChat(caseId, value) {
  if (value) pendingChats.set(caseId, value); else pendingChats.delete(caseId);
  try {
    if (value) sessionStorage.setItem(`qier-chat:${caseId}`, JSON.stringify(value));
    else sessionStorage.removeItem(`qier-chat:${caseId}`);
  } catch { /* Guest ownership is in an HttpOnly cookie, never in this UI state. */ }
}
async function recoverChat() {
  if (!S.case || S.busy) return;
  const id = S.case.id, pending = pendingChat(id);
  if (!pending) return;
  try {
    const state = await api(`/api/cases/${encodeURIComponent(id)}/chat/requests/${encodeURIComponent(pending.key)}`, {timeoutMs:15000});
    if (state.status === 'complete') {
      const saved = await api(`/api/cases/${encodeURIComponent(id)}`, {timeoutMs:15000});
      savePendingChat(id, null);
      if (S.case?.id === id) { S.case = saved; refreshChat(); }
      toast('回答已恢复');
    } else if (state.status === 'failed') {
      savePendingChat(id, null); refreshChat();
      toast('上次提问未完成，可以修改问题后重新发送。', true);
    } else toast(state.status === 'interrupted' ? '暂时无法确认上次结果，请稍后恢复或查看案卷。' : '后台仍在处理，请稍后恢复回答。');
  } catch (e) {
    if (e.status === 404) { savePendingChat(id, null); refreshChat(); }
    toast('未能恢复：' + e.message, true);
  }
}

async function ask(q) {
  q = (q || '').trim();
  if (!q || S.busy || !S.case) return;
  const caseData = S.case, id = caseData.id, version = ver().no, selected = [...S.selected];
  const refs = selected.map(ref => chatRef(ref, version));
  const body = {text:q, refs, version};
  const previous = pendingChat(id);
  const key = previous && JSON.stringify(previous.body) === JSON.stringify(body) ? previous.key
    : (globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  savePendingChat(id, {key, body});
  const controller = new AbortController();
  S.chatAbort = controller;
  S.busy = true;
  S.busyCaseId = id;
  const message = { role: 'user', text: q, refs, citations: [], quotes: [], suggest: [], version, created_at: new Date().toISOString() };
  caseData.chat.push(message);
  // 切走再回来可能重新加载了同一案卷；同步当前对象，但不触碰别的案卷。
  const targets = () => S.case && S.case.id === id && S.case !== caseData ? [caseData, S.case] : [caseData];
  const sameMessage = (a, b) => a === b || (a.role === b.role && a.version === b.version && a.text === b.text && a.created_at === b.created_at);
  S.selected.clear(); refreshSel(); refreshChat();
  $('#assist')?.classList.add('open');
  try {
    const reply = await api(`/api/cases/${encodeURIComponent(id)}/chat`, { method: 'POST', body,
      headers:{'Idempotency-Key':key}, signal:controller.signal, timeoutMs:90000 });
    savePendingChat(id, null);
    const savedUser = { ...message, created_at: reply.created_at || message.created_at };
    for (const target of targets()) {
      const index = target.chat.findIndex(m => sameMessage(m, message) || sameMessage(m, savedUser));
      if (index === -1) target.chat.push(savedUser);
      else target.chat[index] = savedUser;
      if (!target.chat.some(m => sameMessage(m, reply))) target.chat.push(reply);
    }
  } catch (e) {
    if ([400, 401, 403, 404, 422].includes(e.status)) savePendingChat(id, null);
    for (const target of targets()) {
      const index = target.chat.findIndex(m => sameMessage(m, message));
      if (index !== -1) target.chat.splice(index, 1);
    }
    if (S.case && S.case.id === id && ver().no === version) {
      selected.forEach(r => S.selected.add(r)); refreshSel();
      const ta = $('#asForm textarea'); if (ta) ta.value = q;
    }
    toast('小企没答上来：' + e.message, true);
  } finally { S.busy = false; S.busyCaseId = null; if (S.chatAbort === controller) S.chatAbort = null; refreshChat(); }
}

// ---------- 补充信息（二次分析） ----------

function demoForCase() {
  return S.case && S.demos.find(d => d.input && d.input.company_name === S.case.case.company_name);
}
// ---------- 给一条判断下结论：澄清 / 撤回 / 继续查 ----------
const RES_KIND = { clarified: ['核实过了，没问题', '疑点解除。这条作为"材料摘录"仍然留在案卷里，材料本身真不真另说。'],
                   withdrawn: ['是误判，撤掉这条', '看错了、误识别，或者根本不适用。撤掉要署名。'],
                   recheck: ['还要继续查', '先放回"需要核实"，等有了新依据再说。'] };

function openResolve(jid, action) {
  const j = (ver().judgments || []).find(x => x.id === jid);
  if (!j) { toast('这一版里没有这条判断'); return; }
  const kind = action || 'clarified';
  const dlg = $('#resDlg');
  dlg.dataset.jid = jid; dlg.dataset.kind = kind;
  dlg.innerHTML = `<form class="dlg-in" id="resForm">
    <div class="dlg-head"><div><div class="kicker">核实一条判断 · 将生成第 ${S.case.versions.length + 1} 版</div><h3>给这条判断下结论</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <div class="jg-slot cur"><span class="jg-k">当前判断</span><p class="jg-text">${esc(j.text)}</p></div>
      <div class="seg" role="radiogroup" aria-label="结论">${Object.entries(RES_KIND).map(([k, o]) => `<button type="button" data-act="res-kind" data-kind="${k}" aria-pressed="${k === kind}">${o[0]}</button>`).join('')}</div>
      <p class="sup-help" id="resHelp">${esc(RES_KIND[kind][1])}</p>
      <textarea class="big-inp sm" name="note" rows="4" required placeholder="写清楚你是怎么核实的：跟谁确认的、看到了什么、材料哪里写错了"></textarea>
      <div class="err" id="resErr" role="alert"></div>
    </div>
    <div class="dlg-foot"><button type="button" class="btn ghost sm" data-act="close-dlg">取消</button><button type="submit" class="btn sm" id="resGo">记下结论，出新版本</button></div>
  </form>`;
  if (!dlg.open) dlg.showModal();
  $('#resForm textarea').focus();
  $('#resForm').addEventListener('submit', submitResolve);
}
async function submitResolve(e) {
  e.preventDefault();
  const dlg = $('#resDlg'), f = e.target;
  const note = f.note.value.trim();
  if (!note) { $('#resErr').textContent = '写一句说明，别只点按钮'; return; }
  const caseId = S.case.id, version = ver().no, hash = location.hash, request = routeRequest;
  const stillHere = () => request === routeRequest && S.case?.id === caseId && ver()?.no === version
    && location.hash === hash && f.isConnected && dlg.open;
  const go = $('#resGo'); go.disabled = true; go.textContent = '正在出新版本…';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(caseId)}/resolve`, { method: 'POST',
      body: { judgment_id: dlg.dataset.jid, action: dlg.dataset.kind, note, by: '我' } });
    if (!stillHere()) { toast(`原案卷已更新至第 ${c.current} 版，可在「案卷」查看`); return; }
    S.case = c; S.opCache = {}; S.tab = 'judgments'; dlg.close();
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    toast(`已记下，新增第 ${c.current} 版`);
  } catch (err) {
    if (!stillHere()) { toast('原案卷的更新未能确认，请到「案卷」查看', true); return; }
    $('#resErr').textContent = '没记上：' + err.message;
    go.disabled = false; go.textContent = '记下结论，出新版本';
  }
}

// 拍合同 = 二次审核的主入口：拍/选照片 → 读出文字 → 核对 → 出新版本，自动停在「变化」那一栏
function openContract() {
  if (!S.case) { toast('先开一个案卷，再拍合同'); return; }
  openSupplement({ kind: 'material', photo: true, title: '合同照片' });
}

function openSupplement(opt = {}) {
  if (pendingSupplement(S.case?.id)) { void resumeSupplement(); return; }
  const kind = opt.kind || 'material';
  const photo = !!opt.photo;                 // 拍合同进来：只收照片，手机直接开相机
  const dlg = $('#supDlg');
  dlg.classList.remove('material-mode');
  const demo = demoForCase();
  const camOn = kind === 'material';
  dlg.innerHTML = `<form class="dlg-in" id="supForm" method="dialog">
    <div class="dlg-head"><div><div class="kicker">补充核验 · 分析后保存在本案卷</div><h3 id="supTitle">${photo ? '拍合同 · 二次审核' : '补充信息'}</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <div class="seg sup-kinds" role="radiogroup" aria-label="补充什么">${Object.entries(SUP_KIND).map(([k, o]) => `<button type="button" data-act="sup-kind" data-kind="${k}" aria-pressed="${k === kind}">${o.label}</button>`).join('')}</div>
      <p class="sup-help" id="supHelp">${esc(photo ? '拍合同、补充协议、聊天里发的合同照片。合同有好几页就一次拍完，系统按张读成文字，读完你核对。' : SUP_KIND[kind].help)}</p>
      <p class="small muted">材料仅用于你的私人案卷，不会自动发布为评价。仅此浏览器可访问，清除浏览器数据后不能自动恢复。</p>
      ${photo ? `<p class="sup-note">照片只证明你手上确实有这份纸。写了什么要看读出来的文字；签没签、对方认不认、照片有没有被改过，都不算验证过。所以这一版里，合同上的说法会记成「材料里写的」，和查询结果分开列。</p>` : ''}
      <div id="supMat"${kind === 'material' ? '' : ' hidden'}><div class="mat-tools">${camOn ? `<span class="btn sm cam file-btn">📷 拍照 / 选照片（可多张）<input type="file" id="supCam" accept="image/*" capture="environment" multiple></span>` : ''}<span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="supFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="muted small" id="supRead"></span></div></div>
      <div id="supScen"${kind === 'need' ? '' : ' hidden'}><div class="small muted">场景（不选就从新需求里识别）</div><div class="chips" style="margin:4px 0 10px">${S.scenarios.map(s => `<button type="button" class="chip" data-act="sup-scen" data-id="${esc(s.id)}" aria-pressed="${s.id === opt.scenario}">${esc(s.label)}</button>`).join('')}</div></div>
      <input class="big-inp sm" name="title" id="supTitleIn" placeholder="${kind === 'reply' ? '例如：业务员的微信回复' : '材料名称，例如：认购协议'}" value="${esc(opt.title || '')}"${kind === 'need' ? ' hidden' : ''}>
      <textarea class="big-inp sm" name="text" rows="8" required placeholder="${kind === 'need' ? '例如：我收到这家公司的 offer，让我去做理财顾问' : '把文字贴在这里'}">${esc(opt.text || '')}</textarea>
      ${demo && demo.supplements.length ? `<div class="sup-demo"><span class="muted">演示案例准备好的补充：</span><div class="chips">${demo.supplements.map((s, i) => `<button type="button" class="chip" data-act="sup-fill" data-i="${i}">${esc(SUP_KIND[s.kind].label)}：${esc(s.title || s.text.slice(0, 18))}</button>`).join('')}</div></div>` : ''}
      <div class="err" id="supErr" role="alert"></div>
    </div>
    <div class="dlg-foot"><button type="button" class="btn ghost sm" data-act="close-dlg">取消</button><button type="submit" class="btn sm" id="supGo">${kind === 'need' ? '更新公司报告' : '生成材料分析'}</button></div>
  </form>`;
  dlg.dataset.kind = kind; dlg.dataset.scen = opt.scenario || '';
  if (!dlg.open) dlg.showModal();
  $('#supForm textarea').focus();
  const readIn = files => readMaterials([...files], { note: $('#supRead'), form: $('#supForm'),
    titleEl: $('#supTitleIn'), keepName: photo });
  const cam = $('#supCam'), file = $('#supFile');
  if (cam) cam.addEventListener('change', e => { readIn(e.target.files); e.target.value = ''; });
  file.addEventListener('change', e => { readIn(e.target.files); e.target.value = ''; });
  $('#supForm').addEventListener('submit', submitSupplement);
}

// 拍合同：照片按张读成文字，读完拼到文本框里让你核对。不覆盖你改过的文字，接着往后加。
async function readMaterials(files, opt) {
  if (!files.length) return;
  const note = opt.note, ta = opt.form.text, multi = files.length > 1;
  const done = [], bad = [];
  for (const f of files) {
    note.textContent = `正在读 ${f.name}…（${done.length + bad.length + 1}/${files.length}）`;
    try {
      const r = await readFile(f);
      if (r.method === 'failed') { bad.push(`${f.name}：${r.note || '读不出来'}`); continue; }
      done.push(multi ? `【${f.name}】\n${r.text}` : r.text);
      if (opt.titleEl && !opt.titleEl.value) opt.titleEl.value = opt.keepName ? '合同照片' : f.name;
    } catch (err) { bad.push(`${f.name}：${err.message}`); }
  }
  if (done.length) {
    const head = ta.value.trim();
    ta.value = (head ? head + '\n\n' : '') + done.join('\n\n');
  }
  const chars = done.join('').replace(/\s/g, '').length;
  note.innerHTML = done.length
    ? `已读出 ${chars} 字（${done.length} 张），请核对。${bad.length ? `<span class="err">这 ${bad.length} 张没读出来：${esc(bad.join('；'))}</span>` : ''}`
    : `<span class="err">都没读出来：${esc(bad.join('；'))}可以把文字手动贴进来。</span>`;
}
function setSupKind(kind) {
  const dlg = $('#supDlg');
  dlg.dataset.kind = kind;
  $$('[data-act="sup-kind"]', dlg).forEach(b => b.setAttribute('aria-pressed', b.dataset.kind === kind));
  $('#supHelp').textContent = SUP_KIND[kind].help;
  $('#supGo').textContent = kind === 'need' ? '更新公司报告' : '生成材料分析';
  $('#supMat').hidden = kind !== 'material';
  $('#supScen').hidden = kind !== 'need';
  $('#supTitleIn').hidden = kind === 'need';
}
// Pending data is scoped by case; no material or browser credentials go in the URL.
let supplementClient = null;
function supplementTasks() {
  if (!supplementClient) supplementClient = SupplementRuns.create({
    api: (path, opts) => api(path, opts), randomUUID: () => crypto.randomUUID(),
    storage: { getItem: key => localStorage.getItem(key), setItem: (key, value) => localStorage.setItem(key, value), removeItem: key => localStorage.removeItem(key) },
  });
  return supplementClient;
}
function pendingSupplement(id) {
  return id && typeof SupplementRuns !== 'undefined' ? supplementTasks().pending(id) : null;
}
function supplementNoticeHtml() {
  return pendingSupplement(S.case?.id) ? '<div class="old-banner" role="status">有一次补充分析待查看。<button type="button" class="linkish" data-act="sup-resume">查看任务进度 / 结果</button></div>' : '';
}
function refreshSupplementNotice() {
  const notice = $('#supplementNotice');
  if (notice) notice.innerHTML = supplementNoticeHtml();
}
function stopSupplementWatch() {
  S.supplementRequest?.abort();
  S.supplementRequest = null;
  S.supplementBusy = false;
}
async function submitSupplement(e) {
  e.preventDefault();
  if (S.supplementBusy) { toast('已有补充信息正在处理，请稍候或查看任务进度'); return; }
  if (pendingSupplement(S.case?.id)) return resumeSupplement();
  const dlg = $('#supDlg'), f = e.target;
  const kind = dlg.dataset.kind, text = f.text.value.trim();
  if (!text) { $('#supErr').textContent = '请填写内容'; return; }
  const body = { kind, text, title: kind === 'need' ? null : (f.title.value.trim() || null), scenario: kind === 'need' ? (dlg.dataset.scen || null) : null };
  try { supplementTasks().prepare(S.case.id, body); }
  catch (err) { $('#supErr').textContent = err.message; return; }
  return resumeSupplement();
}
async function resumeSupplement() {
  const record = pendingSupplement(S.case?.id);
  if (!record) return;
  if (record.body.kind !== 'need') return resumeMaterialSupplement(record);
  const dlg = $('#supDlg');
  dlg.classList.remove('material-mode');
  if (S.supplementBusy && S.supplementWatchCase === record.caseId) {
    if (!dlg.open) dlg.showModal();
    return;
  }
  stopSupplementWatch();
  const request = S.supplementRequest = new AbortController();
  S.supplementBusy = true; S.supplementWatchCase = record.caseId;
  S.supplementTerminal = null;
  const caseId = record.caseId, route = location.hash;
  dlg.innerHTML = `<div class="dlg-in">
    <div class="dlg-head"><div><div class="kicker">二次分析</div><h3 id="supTitle">补充分析进度</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body"><p>刷新页面或暂时离开后，回到本案卷会接着查看这次任务。</p>
      <p class="small muted">${esc(SUP_KIND[record.body.kind]?.label || '补充信息')} · ${esc(record.body.title || record.body.text.slice(0, 60))}</p>
      <div id="supProgress"></div><p id="supErr" class="err" role="status" aria-live="polite"></p></div>
    <div class="dlg-foot"><button type="button" class="btn ghost sm" data-act="close-dlg">暂时收起</button><button type="button" id="supResume" class="btn sm" data-act="sup-resume" hidden>恢复进度 / 结果</button><button type="button" id="supEdit" class="btn sm" data-act="sup-edit" hidden>检查材料并重新提交</button></div>
  </div>`;
  if (!dlg.open) dlg.showModal();
  refreshSupplementNotice();
  const waiting = ResearchProgress.mount($('#supProgress'), S.case.case.company_name);
  const stillHere = () => S.supplementRequest === request && !request.signal.aborted && S.case?.id === caseId && location.hash === route;
  try {
    const result = await supplementTasks().follow(record, { signal: request.signal, onEvent: event => { if (stillHere()) waiting.onEvent(event); } });
    if (!stillHere()) return;
    if (!dlg.open) { toast('新版报告已生成，点「查看任务进度 / 结果」打开'); return; }
    supplementTasks().clear(record);
    const c = result.case, version = result.version;
    S.case = c; S.opCache = {}; S.tab = 'changes';
    S.selected.clear(); S.reviews = null;
    dlg.close();
    const target = `#/case/${c.id}/v/${version}`;
    if (location.hash === target) { S.viewNo = version; renderCase(); } else location.hash = target;
    toast(`已生成第 ${version} 版`);
  } catch (err) {
    if (!stillHere()) return;
    $('#supProgress .research-current').textContent = err.terminal ? '任务已停止，请确认结果后再提交' : '连接中断，进度待确认';
    $('#supProgress .kicker').textContent = '补充分析 · 等待恢复';
    $('#supProgress .research-wait').setAttribute('aria-busy', 'false');
    $('#supErr').textContent = err.terminal ? err.message : '暂时无法确认结果：' + err.message + ' 恢复时会继续查看同一次任务。';
    $('#supResume').hidden = false;
    $('#supEdit').hidden = !err.terminal;
    if (err.terminal) S.supplementTerminal = record;
  } finally {
    waiting.stop();
    if (S.supplementRequest === request) {
      S.supplementRequest = null; S.supplementBusy = false;
      if (S.case?.id === caseId) refreshSupplementNotice();
    }
  }
}
function openMaterialAnalysis(id) {
  const analysis = S.case?.material_analyses?.find(a => a.id === id);
  if (!analysis) { toast('暂未读到这份材料分析，请刷新案卷后重试'); return; }
  const dlg = $('#materialDlg');
  dlg.innerHTML = MaterialAnalysis.result(S.case, analysis);
  if (!dlg.open) dlg.showModal();
}
async function resumeMaterialSupplement(record) {
  const dlg = $('#supDlg');
  if (S.supplementBusy && S.supplementWatchCase === record.caseId) {
    if (!dlg.open) dlg.showModal();
    return;
  }
  stopSupplementWatch();
  const request = S.supplementRequest = new AbortController();
  S.supplementBusy = true; S.supplementWatchCase = record.caseId; S.supplementTerminal = null;
  const route = location.hash, caseId = record.caseId;
  const stillHere = () => S.supplementRequest === request && !request.signal.aborted && S.case?.id === caseId && location.hash === route;
  dlg.classList.add('material-mode');
  dlg.innerHTML = MaterialAnalysis.progressShell(S.case, record);
  if (!dlg.open) dlg.showModal();
  refreshSupplementNotice();
  const waiting = MaterialAnalysis.mount($('#supProgress'));
  try {
    const result = await supplementTasks().follow(record, {signal:request.signal, onEvent:event=>{if(stillHere())waiting.onEvent(event);}});
    if (!stillHere()) return;
    const analysis = result.case.material_analyses?.find(a => a.report_version === result.version);
    if (!analysis) throw new Error('尚未读到已保存的材料分析，请恢复进度再次确认。');
    // Clear recovery only after both the saved company snapshot and appendix were read.
    supplementTasks().clear(record);
    S.case = result.case; S.opCache = {}; S.selected.clear(); S.reviews = null;
    renderCase();
    if (dlg.open) {
      dlg.innerHTML = MaterialAnalysis.result(S.case, analysis, 'supTitle');
      dlg.scrollTop = 0;
    } else toast('材料分析已完成，已保存到「问询与复核」底部');
  } catch (err) {
    if (!stillHere()) return;
    waiting.error(err.terminal);
    $('#supDlg .ma-context > span').textContent = err.terminal ? '分析未完成' : '进度待确认';
    $('#supErr').textContent = err.terminal ? err.message : '暂时无法确认结果：' + err.message + '。恢复时会继续查看同一次任务。';
    $('#supResume').hidden = false; $('#supEdit').hidden = !err.terminal;
    if (err.terminal) S.supplementTerminal = record;
  } finally {
    waiting.stop();
    if (S.supplementRequest === request) {
      S.supplementRequest = null; S.supplementBusy = false;
      if (S.case?.id === caseId) refreshSupplementNotice();
    }
  }
}

function editFailedSupplement() {
  const record = S.supplementTerminal;
  if (!record || record.caseId !== S.case?.id || S.supplementBusy) return;
  try { supplementTasks().clear(record); }
  catch (err) { $('#supErr').textContent = err.message; return; }
  S.supplementTerminal = null;
  openSupplement(record.body);
  refreshSupplementNotice();
}

// ---------- 打印 ----------

function printOnepager() {
  if (!$('#onepager') || !currentOp(ver())) { toast('一页结论还没生成好'); return; }
  if (!isDesignReview()) { window.print(); return; }
  // 新版报告页没有经典版的 #L1：把预览里的一页结论单独放进 #printSheet，打印时只印它
  $('#printSheet')?.remove();
  const sheet = document.createElement('div');
  sheet.id = 'printSheet';
  sheet.innerHTML = `<article class="onepager">${$('#onepager').innerHTML}</article>`;
  document.body.append(sheet);
  document.body.classList.add('printing-sheet');
  $('#printDlg')?.close();
  window.addEventListener('afterprint', () => { sheet.remove(); document.body.classList.remove('printing-sheet'); }, { once: true });
  window.print();
}

// ---------- 事件分发 ----------

document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]');
  const pop = $('#pop');
  if (!pop.hidden && !e.target.closest('#pop') && !(el && ['term', 'src', 'goto'].includes(el.dataset.act))) closePop();
  if (!el) {
    if (e.target.tagName === 'DIALOG') e.target.close(); // 点遮罩关闭
    return;
  }
  const d = el.dataset;
  switch (d.act) {
    case 'retry-read': void route(); break;
    case 'go': location.hash = `#/${d.sec}`; break;
    case 'qi-nudge': toast('先打开一份案卷，小企才有数据可答'); break;
    case 'chat-sources': openChatSources(Number(d.index)); break;
    case 'cancel-chat': S.chatAbort?.abort('cancelled'); break;
    case 'recover-chat': void recoverChat(); break;
    case 'raw': if (selectRefVersion(d.version == null ? null : Number(d.version))) openRaw(d.ref, d.hl ? JSON.parse(d.hl) : []); break;
    case 'goto': gotoItem(d.id, d.version == null ? null : Number(d.version), el); break;
    case 'sel': toggleSel(d.id); break;
    case 'unsel': S.selected.delete(d.id); refreshSel(); break;
    case 'ver': location.hash = `#/case/${S.case.id}/v/${d.no}`; break;
    case 'tab': showTab(d.tab); break;
    case 'sigtile':
      if (isDesignReview()) { openResearchSignal(d.key); break; }
      S.tab = 'signals'; renderPanel(); { const c = $(`#sig-${d.key}`); if (c) { c.closest('.sig').scrollIntoView({ behavior: 'smooth', block: 'center' }); c.closest('.sig').classList.add('flash'); } } break;
    case 'optext': S.showText = !S.showText; $('.op-wrap').hidden = !S.showText; el.textContent = S.showText ? '收起文字版' : '文字版（给家人看）'; break;
    case 'rest':
      if (S.openRest.has(d.key)) S.openRest.delete(d.key); else S.openRest.add(d.key);
      if (el.closest('#signalDlg')) {
        renderResearchSignal(d.key);
        $('#signalDlg .rest-tog')?.focus({ preventScroll: true });
      } else renderPanel();
      break;
    case 'aud': S.audience = d.aud; $$('[data-act="aud"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.aud === d.aud));
      $('#onepager').innerHTML = opBody(currentOp(ver()), ver()); loadOnepager(ver()); break;
    case 'print': printOnepager(); break;
    case 'term': termPop(el, d.term); break;
    case 'lib-toggle': {
      const on = libToggle(d.term);
      if (on === null) { toast('这个浏览器存不了收藏'); break; }
      el.setAttribute('aria-pressed', on); el.textContent = on ? '★ 已收藏' : '☆ 收藏复习';
      toast(on ? '已收藏到「知识库」' : '已移出知识库');
      break;
    }
    case 'cases-filter':
      collectionView.caseFilter = d.filter;
      $$('[data-act="cases-filter"]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.filter === d.filter)));
      renderCaseCollection(); break;
    case 'cases-reset':
      collectionView.caseQuery=''; collectionView.caseFilter='all'; $('#caseSearch').value='';
      $$('[data-act="cases-filter"]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.filter === 'all')));
      renderCaseCollection(); break;
    case 'library-filter':
      collectionView.libraryFilter=d.filter;
      $$('[data-act="library-filter"]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.filter === d.filter)));
      refreshLibraryCards(); break;
    case 'library-reset':
      collectionView.libraryQuery=''; collectionView.libraryFilter='all'; $('#librarySearch').value='';
      $$('[data-act="library-filter"]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.filter === 'all')));
      refreshLibraryCards(); break;
    case 'library-study':
      collectionView.study=!collectionView.study;
      el.setAttribute('aria-pressed',String(collectionView.study));
      el.querySelector('span').textContent=collectionView.study ? '结束复习' : '复习一下';
      $('#studyHint').hidden=!collectionView.study;
      refreshLibraryCards(); break;
    case 'lib-remove':
      if (libToggle(d.term) === null) { toast('这个浏览器存不了收藏'); break; }
      if ($('#libList')) $('#libList').innerHTML = libraryHtml(libRead());
      break;
    case 'src': showSource(el, d.src); break;
    case 'acct-mode': S.acctMode = d.mode; $('#acct').innerHTML = acctHtml(); $('#acct input')?.focus(); break;
    case 'acct-logout':
      api('/api/auth/logout', {method: 'POST'}).then(() => acctSignedOut('已退出登录')).catch(err => toast(err.message, true)); break;
    case 'acct-merge':
      el.disabled = true;
      api('/api/auth/merge', {method: 'POST'}).then(r => acctRefresh(`已把 ${r.moved} 份案卷并进账号`))
        .catch(err => { el.disabled = false; toast(err.message, true); }); break;
    case 'close-pop': closePop(); break;
    case 'ask': ask(d.q); break;
    case 'open-assist': $('#assist').classList.add('open'); setTimeout(() => { const t = $('#asForm textarea'); if (t) t.focus(); }, 50); break;
    case 'close-assist': $('#assist').classList.remove('open'); break;
    case 'contract': openContract(); break;
    case 'material-open': openMaterialAnalysis(d.analysis); break;
    case 'material-raw': openRaw(d.ref, []); break;
    case 'material-report': el.closest('dialog').close(); location.hash = `#/case/${S.case.id}/v/${d.version}`; break;
    case 'material-collapse': {
      el.closest('dialog').close();
      const entry = [...document.querySelectorAll('[data-act="material-open"]')].find(b => b.dataset.analysis === d.analysis);
      entry?.scrollIntoView({behavior:'smooth',block:'center'}); entry?.focus({preventScroll:true});
      break;
    }
    case 'sup-resume': void resumeSupplement(); break;
    case 'sup-edit': editFailedSupplement(); break;
    case 'supplement': openSupplement({ kind: d.kind, text: d.text, title: d.title }); break;
    case 'sup-kind': setSupKind(d.kind); break;
    case 'pick-company': { const f = $('#caseForm'); S.form.resolved = d.name; f.company.value = d.name; $('#nameCands').hidden = true; f.requestSubmit(); } break;
    case 'sup-scen': { const dlg = $('#supDlg'); const on = dlg.dataset.scen !== d.id; dlg.dataset.scen = on ? d.id : '';
      $$('[data-act="sup-scen"]', dlg).forEach(b => b.setAttribute('aria-pressed', on && b.dataset.id === d.id)); } break;
    case 'sup-fill': { const s = demoForCase().supplements[+d.i]; setSupKind(s.kind); const f = $('#supForm'); f.text.value = s.text; f.title.value = s.title || ''; } break;
    case 'resolve': openResolve(d.id, d.do); break;
    case 'res-kind': { const dl = $('#resDlg'); dl.dataset.kind = d.kind;
      $$('[data-act="res-kind"]', dl).forEach(b => b.setAttribute('aria-pressed', b.dataset.kind === d.kind));
      $('#resHelp').textContent = RES_KIND[d.kind][1]; } break;
    case 'close-dlg': el.closest('dialog').close(); break;
    case 'demo-fill': fillDemo(d.id); break;
    case 'rv-star': S.rvStars = +d.n; $$('[data-act="rv-star"]').forEach(b => b.setAttribute('aria-pressed', +b.dataset.n <= S.rvStars)); $('#rvStarTxt').textContent = `${S.rvStars} 星`; break;
    case 'rv-rel': S.rvRel = d.rel; $$('[data-act="rv-rel"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.rel === d.rel)); break;
    case 'rv-refresh': refreshReviews(el); break;
    case 'scen-toggle': S.form.showScen = !S.form.showScen; $('#intake').innerHTML = intakeHtml(); break;
    case 'scenario': S.form.userScenario = S.form.userScenario === d.id ? null : d.id; S.form.showScen = false; $('#intake').innerHTML = intakeHtml(); break;
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.matches('[role="link"][data-act]')) { e.preventDefault(); e.target.click(); }
  if (e.key === 'Escape') { closePop(); const a = $('#assist'); if (a && a.classList.contains('open') && !$('dialog[open]')) a.classList.remove('open'); }
  if (e.target.matches('#asForm textarea') && e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault(); const q = e.target.value; e.target.value = ''; ask(q);
  }
});
document.addEventListener('submit', e => {
  if (e.target.id === 'asForm') { e.preventDefault(); const t = e.target.q; const q = t.value; t.value = ''; ask(q); }
  if (e.target.id === 'rvForm') { e.preventDefault(); submitReview(e.target); }
  if (['acctForm', 'acctForgot', 'acctPw', 'acctDel', 'resetForm'].includes(e.target.id)) { e.preventDefault(); void acctSubmit(e.target); }
});
window.addEventListener('scroll', closePop, { passive: true });

// ---------- 路由与启动 ----------

// Metadata can arrive after the report. Refresh only the conclusion, preserving
// the radar, signal dialogs, current scroll position and the reader's chat draft.
function refreshScenarioParts() {
  const match = location.hash.match(/^#\/case\/([\w-]+)(?:\/v\/(\d+))?$/);
  const v = S.case && ver();
  if (!match || S.case?.id !== match[1] || !v || (match[2] && v.no !== +match[2])) return;
  if (typeof refreshDossierScenario === 'function') refreshDossierScenario(v);
  for (const el of $$('[data-first-question]')) {
    if (el.isConnected) el.innerHTML = glanceFirstHtml(v) || '<p>现有记录尚不足以形成结论。</p>';
  }
}

let routeRequest = null;
let startupReady = Promise.resolve();
const currentRoute = request => !request || (request === routeRequest && !request.signal.aborted);

async function route() {
  stopSupplementWatch();
  routeRequest?.abort('navigation');
  const request = routeRequest = new AbortController();
  researchCleanup();
  document.body.classList.remove('research-mode', 'cases-mode', 'dossier-live', 'dossier-shell', 'collections-mode', 'knowledge-mode', 'me-mode');
  // The research room is the only query homepage, including old #/new bookmarks.
  if (!location.hash || /^#\/(?:check|new)?\/?$/.test(location.hash)) {
    location.replace('/');
    return;
  }
  closePop();
  $$('dialog[open]').forEach(d => d.close());
  const m = location.hash.match(/^#\/case\/([\w-]+)(?:\/v\/(\d+))?/);
  if (m) {
    const sameCase = S.case && S.case.id === m[1];
    await openCase(m[1], m[2] ? +m[2] : null, request);
    if (currentRoute(request) && !sameCase) window.scrollTo(0, 0);
    return;
  }
  if (/^#\/reset\b/.test(location.hash)) { renderReset(); return; }
  const sec = (location.hash.match(/^#\/(cases|library|me|guide)\/?$/) || [])[1];
  if (sec === 'cases') await renderCases(request);
  else if (sec === 'library') renderLibrary();
  else if (sec === 'me') await renderMe(request);
  else if (sec === 'guide') await renderGuide(request);
  else { location.replace('/'); return; }
  if (currentRoute(request)) window.scrollTo(0, 0);
}

async function boot() {
  startupReady = Promise.allSettled([
    '/api/health', '/api/scenarios', '/api/sources', '/api/demo/cases', '/api/glossary', '/api/session'
  ].map(path => api(path, {timeoutMs: 6000}).then(value => {
    if (path === '/api/scenarios') {
      S.scenarios = Array.isArray(value) ? value : [];
      refreshScenarioParts();
    }
    return value;
  }))).then(([health, scenarios, sources, demos, glossary, session]) => {
    S.health = health.value || null;
    S.session = session.value || null;
    void libSync();
    S.scenarios = Array.isArray(scenarios.value) ? scenarios.value : [];
    S.sources = sources.value || [];
    S.demos = demos.value || [];
    setGlossary(glossary.value);
    const terms = ver()?.terms;
    if (terms?.length) useTerms(terms);
    // Refresh status only: never replace a report or a reader's draft question.
    renderTop();
    const mode = $('#assist .as-heading p');
    if (mode) mode.textContent = modeLine();
  });
  window.addEventListener('hashchange', route);
  const initialRoute = route();
  await startupReady;
  await initialRoute;
}
document.addEventListener('input', event => {
  if (event.isComposing) return;
  if (event.target.id === 'caseSearch') {collectionView.caseQuery=event.target.value;renderCaseCollection();}
  if (event.target.id === 'librarySearch') {collectionView.libraryQuery=event.target.value;refreshLibraryCards();}
});
document.addEventListener('compositionend', event => {
  if (event.target.id === 'caseSearch') {collectionView.caseQuery=event.target.value;renderCaseCollection();}
  if (event.target.id === 'librarySearch') {collectionView.libraryQuery=event.target.value;refreshLibraryCards();}
});
document.addEventListener('change', event => {
  if (event.target.id === 'caseSort') {collectionView.caseSort=event.target.value;renderCaseCollection();}
});
boot();
