/* 企er 前端：原生 JS，不打包。契约以 backend/app/models.py 为准。
 *
 * 壳子分三个分区，顶栏一排按钮：查企（#/check）、案卷（#/cases）、我的（#/me）。
 * 报告不占分区，它属于案卷：#/case/<id> 最新版报告；#/case/<id>/v/<n> 第 n 版。
 * 右侧一栏是小企（AI）。三个分区里都在，没开案卷时它只说明自己能答什么、不能答什么，不假装能答。
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
const STATUS = { bad: '有问题', warn: '要留意', miss: '该有的没有', none: '没查', ok: '没问题' };
const FLAG = new Set(['bad', 'warn', 'miss']);   // 要看的；ok、none 默认折叠
const CHANGE = { new_concern: '新疑点', worse: '更严重', clarified: '疑点减轻', unchanged: '没变', added: '新增', removed: '这版没有了', updated: '事实更新', unavailable: '证据不足' };
const MODE = { model: '模型回答', replay: '离线回放', template: '模板回答', guard: '已拦截' };
// 判断页先收起来（地址带 ?judg=1 才显示）：它的逐条比对在"只改需求"时也会报"需要重新核实"，
// 和"事实没变"打架；记录里查到的官方文书也不该一键撤掉。后端照常存判断，修好再放出来。
const SHOW_JUDGMENTS = /[?&]judg=1/.test(location.search);
const TABS = { judgments: '判断', changes: '变化', signals: '四个信号', claims: '宣称 vs 记录', questions: '该问对方的', raw: '原始数据', reviews: '评价' };
// 用户评价只作参考时（不够集中），既不算"没问题"，也不算"没查"
const isRef = i => i.source === 'user_reviews' && !FLAG.has(i.status);
const stLabel = i => (isRef(i) ? '只作参考' : STATUS[i.status] || '');
// 三个分区。顺序就是顶栏顺序，也是第一次用的人该走的顺序
const NAV = [['check', '查企', '输入公司全称和一句需求，出新报告'], ['cases', '案卷', '查过的公司和它们的每一版'], ['me', '我的', '状态、名单、名词表、这几条底线']];
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
  const init = { method: opts.method || 'GET', headers: {} };
  if (opts.body instanceof FormData) init.body = opts.body;
  else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; }
  let r;
  try { r = await fetch(path, init); } catch { throw new Error('连不上后端服务，请确认它在运行'); }
  let data = null;
  try { data = await r.json(); } catch { /* 非 JSON */ }
  if (!r.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('；') : `请求失败（${r.status}）`);
  }
  return data;
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
const srcOf = id => (S.case && S.case.sources[id]) || S.sources.find(s => s.id === id);
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
function termPop(el, id) {
  const t = termOf(id);
  if (!t) return;
  const src = t.basis && srcOf(t.basis);
  const basis = src ? src.name : t.law;
  const note = t.origin === 'model' ? 'AI 解释：词表里没有这个词，报告生成时由模型补充，没有经过人工核对。' : (basis ? `依据：${basis}` : '');
  popAt(el, `<h5>${esc(t.term)}</h5><p>${esc(t.plain)}</p>${t.why ? `<p class="pw">${esc(t.why)}</p>` : ''}${note ? `<p class="pb">${esc(note)}</p>` : ''}`);
}
const askBtn = id => `<button type="button" class="ask" data-act="sel" data-id="${esc(id)}" aria-pressed="${S.selected.has(id)}" title="选中这一条，去问小企">${S.selected.has(id) ? '已选' : '问'}</button>`;
const goLink = (id, version = null) => {
  const target = parseRef(id, version);
  const terms = target.version == null ? S.terms : (S.case?.versions.find(v => v.no === target.version)?.terms || S.terms);
  const t = target.id.startsWith('term.') && terms.find(t => t.id === target.id.slice(5));
  return `<button type="button" class="cite${t ? ' term-cite' : ''}" data-act="goto" data-id="${esc(id)}"${target.version == null ? '' : ` data-version="${target.version}"`}>${esc(t ? `名词·${t.term}` : target.id)}</button>`;
};
const refLinks = refs => (refs || []).map(r => `<button type="button" class="rf" data-act="goto" data-id="${esc(r)}">${esc(r)}</button>`).join('');
const selCls = id => (S.selected.has(id) ? ' is-sel' : '');

// 来源：一行灰字"类型 · 日期 · 编号"，点开是原始记录（法规、参数类没有编号，点开是出处说明）
function srcLink(sourceId, ref) {
  const s = srcOf(sourceId), r = ref && rawById(ref);
  const kind = (r && rawKind(r)) || (s && s.kind) || '';
  const date = kind === 'none' ? null : (r && r.as_of) || (s && s.as_of);
  const title = s ? s.name : sourceId;
  const inner = `<span class="k-${esc(kind)}">${esc(KIND[kind] || '来源')}</span>${date ? ` · ${esc(date)}` : ''}${ref ? ` · <b>${esc(ref)}</b>` : ''}`;
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
  const sec = onCase ? 'cases' : (location.hash.match(/^#\/(check|cases|me)/) || [])[1] || 'check';
  $('#shellNav').innerHTML = NAV.map(([k, label, hint]) =>
    `<button type="button" class="snav-b" data-act="go" data-sec="${k}" aria-current="${k === sec}" title="${esc(hint)}">${label}</button>`).join('');
  $('#caseStrip').innerHTML = onCase ? `<span title="${esc(S.case.case.company_name)}">${esc(S.case.case.company_name)}</span>` : '';
  const llm = S.health && S.health.llm;
  let b = '';
  if (llm) {
    if (!llm.configured || llm.mode === 'off') b += '<span class="tb off" title="没接模型：需求识别用关键词，小企用模板回答">未接模型</span>';
    else if (llm.mode === 'replay') b += '<span class="tb replay" title="断网演示：只用录好的模型响应">离线回放</span>';
    else b += `<span class="tb live" title="${esc(llm.model || '')}">模型在线</span>`;
  }
  if (onCase && isDemoCase()) b += '<span class="tb demo" title="这家公司和它的记录都是编的，只用来演示">演示数据 · 公司为虚构</span>';
  $('#topBadges').innerHTML = b;
}

// ---------- 壳子：三个分区 + 小企栏 ----------

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
  const line = llm && llm.configured && llm.mode !== 'off' ? '只答案卷里的数据，每句带出处。' : '没接模型，只摘案卷里的原话。';
  return `<div class="as-head"><div class="as-heading"><h3>小企 <span class="qi-role">报告助手</span></h3><p class="small muted">${esc(line)}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="收起小企">×</button></div>
  <div class="as-body">
    <div class="qi-welcome">${qiSpriteHtml()}</div>
    <p class="qi-lede">现在没有打开的案卷。小企只答案卷里有的东西，数据里没有就说没查到，不凭常识猜。</p>
    <p class="small muted">打开一份案卷后，可以这样问它：</p>
    <div class="chips">${QI_SUG.map(q => `<button type="button" class="chip" data-act="qi-nudge" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <ul class="qi-what">
      <li>每句都带出处，能点开看原始记录和日期</li>
      <li>数据里没有的，它说没查到</li>
      <li>它不会改报告；新情况要点"加入案卷"才会重新判断</li>
      <li>它不给公司定性，也不打安全分</li>
    </ul>
    <div class="qi-go"><a class="btn sm" href="#/check">去查一家公司</a><a class="linkish small" href="#/cases">看案卷</a></div>
  </div>`;
}

// 官方名单那一行（查企页和我的页共用）
function listLine(h) {
  if (!h) return '名单没读到，先确认后端在跑。';
  const SHORT = { nfra_insurance: '保险', csrc_futures: '期货', pbc_payment: '支付', amac_managers: '私募' };
  const lists = [{ title: '银行业', count: h.licensed_count },
    ...Object.entries(h.official_lists || {}).map(([k, l]) => ({ title: SHORT[k] || l.title, count: l.count }))];
  return `每家公司都查 ${lists.length} 份官方名单：${lists.map(l => `${esc(l.title)} ${(l.count || 0).toLocaleString()} 家`).join('、')}。要过验证码的网站（企业登记、被执行、裁判文书）我们不绕过，查不到的写"没查"。`;
}

// ---------- 分区一：查企 ----------

async function renderCheck() {
  S.case = null; useTerms(S.terms); renderTop();
  S.form = { userScenario: null, showScen: false, dirty: {}, intake: null };
  $('#view').innerHTML = shellHtml(`
  <div class="home">
    <section class="home-hero">
      <div class="kicker">查企</div>
      <h1>把钱交给一家公司之前，先看清它。</h1>
      <p>输入公司全称，说一句你要做什么。官方记录会汇到一起，对照它的说法，给你一份看得懂的报告。</p>
    </section>
    <div id="formWrap">${formHtml()}</div>
    <p class="check-more" id="checkMore"></p>
    <p class="lists-line">${listLine(S.health)}</p>
  </div>`);
  bindForm();
  try {
    S.cases = await api('/api/cases');
    if (S.cases.length) $('#checkMore').innerHTML = `<a href="#/cases">你查过 ${S.cases.length} 家，都在「案卷」里 →</a>`;
  } catch (e) { /* 列表读不到不影响新建 */ }
}

// ---------- 分区二：案卷 ----------

async function renderCases() {
  S.case = null; useTerms(S.terms); renderTop();
  $('#view').innerHTML = shellHtml(`
  <div class="home">
    <section class="home-hero">
      <div class="kicker">案卷</div>
      <h1>查过的公司</h1>
      <p>每查一家就留一份案卷。补材料、贴对方的回复、改需求，都记在同一份里，按版排下去，改动逐条列出。点开就是那份报告。</p>
    </section>
    <div class="cases" id="caseList"><p class="muted">读取案卷…</p></div>
    <p class="lists-line">这一页按新建时间排。要按"最后一次变化的时间"排，需要在列表接口里多一个字段，现在还没有，所以这里只写新建时间。</p>
  </div>`);
  try {
    S.cases = (await api('/api/cases')) || [];
    $('#caseList').innerHTML = S.cases.length
      ? S.cases.map(caseRow).join('')
      : '<div class="empty-case"><p>还没有案卷。查一家公司，这里就会留一份。</p><a class="btn sm" href="#/check">去查一家公司</a></div>';
  } catch (e) {
    $('#caseList').innerHTML = `<p class="err">读不到案卷列表：${esc(e.message)}</p>`;
  }
}

function caseRow(c) {
  return `<a class="case-row" href="#/case/${esc(c.id)}">
    <div class="cr-h"><b>${esc(c.company_name)}</b><span class="cr-n">${c.versions} 版</span></div>
    ${c.need ? `<div class="cr-need">“${esc(c.need)}”</div>` : ''}
    <div class="cr-m"><span>${esc(c.scenario_label)}</span><span>${esc(fmtTime(c.created_at))} 新建</span><span class="cr-go">打开 →</span></div>
  </a>`;
}

// ---------- 分区三：我的 ----------

async function renderMe() {
  S.case = null; useTerms(S.terms); renderTop();
  try { S.cases = (await api('/api/cases')) || []; } catch (e) { /* 读不到就不显示份数 */ }
  const h = S.health || {}, llm = h.llm || {}, com = h.commercial || {};
  const model = !llm.configured || llm.mode === 'off'
    ? '没接模型。需求识别用关键词，小企用模板回答，只摘报告里的原话。'
    : llm.mode === 'replay'
      ? `离线回放。只用录好的模型回答（已录 ${llm.cached_replies || 0} 条），界面上会标出录于什么时候。`
      : `模型在线（${llm.model || ''}）。需求识别、报告短句、小企的回答都走它；数字和措辞由程序逐条核对。`;
  const commercial = com.configured
    ? `已接（${com.provider || ''}）。这次演示最多调用 ${com.max_calls || 0} 次，已用 ${com.calls || 0} 次。`
    : '没接。企业登记、年报这类数据，现在只能靠证据包、人工采集或演示数据顶上。';
  const terms = S.terms.slice(0, 8);
  $('#view').innerHTML = shellHtml(`
  <div class="home">
    <section class="home-hero">
      <div class="kicker">我的</div>
      <h1>这一版查得到什么，查不到什么</h1>
      <p>这里是这套东西的底账：接没接模型、有没有商业数据源、名词怎么解释、材料放在哪，还有几条我们自己守着的规矩。</p>
    </section>

    <section class="me-sec"><h2>现在是什么状态</h2>
      <dl class="kv-me">
        <dt>模型</dt><dd>${esc(model)}</dd>
        <dt>商业数据源</dt><dd>${esc(commercial)}</dd>
        <dt>案卷</dt><dd>${S.cases.length ? `${S.cases.length} 份，在「案卷」里` : '这台上还没有案卷'}</dd>
        <dt>名单版本</dt><dd>银行名单截至 ${esc(h.licensed_as_of || '—')}；企业登记截至 ${esc(h.registry_as_of || '—')}</dd>
      </dl>
    </section>

    <section class="me-sec"><h2>查什么，不查什么</h2>
      <p class="me-p">${listLine(h)}</p>
      <p class="me-p">${(h.evidence_packs || []).length ? `已备好的证据包：${h.evidence_packs.map(esc).join('、')}。` : ''}没接商业数据源的时候，企业登记和年报只能用证据包、人工采集或演示数据顶上；缺的部分写成"没查"，不会写成"没问题"。</p>
    </section>

    <section class="me-sec"><h2>名词解释</h2>
      <p class="me-p">报告里带虚线的词点一下就有解释，解释来自固定词表。这里是其中几个：</p>
      ${terms.length ? `<div class="chips">${terms.map(t => `<button type="button" class="chip" data-act="term" data-term="${esc(t.id)}">${esc(t.term)}</button>`).join('')}</div>` : '<p class="muted small">词表没读到。</p>'}
    </section>

    <section class="me-sec"><h2>材料和数据放在哪</h2>
      <ul class="me-ul">
        <li>案卷存在跑后端的那台机器上（backend/data/cases），不进代码仓库。</li>
        <li>你贴的宣传单、合同、聊天记录只用在这一次判断里，会原样留在案卷的原始数据中，随时能点开核对。</li>
        <li>要过验证码的网站（企业登记、被执行、裁判文书）不绕过，查不到就写"没查"。</li>
        <li>模型密钥只在后端的 .env 里，按 gitignore 处理，不进仓库，也不进前端。</li>
      </ul>
    </section>

    <section class="me-sec"><h2>几条我们自己守着的规矩</h2>
      <ul class="me-ul">
        <li>结论由固定规则推出来，模型不判对错，只负责读材料和说人话。</li>
        <li>每条结论都能点进原始数据和它的日期。</li>
        <li>不打安全分，也不给公司定性；"没查"不等于没问题。</li>
        <li>小企不知道就说没查到，不凭常识补。</li>
        <li>聊天不会悄悄改报告；新情况要明确点"加入案卷"才会重新判断。</li>
        <li>虚构的演示案例全程挂着"演示数据 · 公司为虚构"。</li>
      </ul>
    </section>
  </div>`);
}

function formHtml() {
  const demos = S.demos.filter(d => d.ready);
  return `<form class="ask-card" id="caseForm" autocomplete="off">
    <div class="f-row"><label class="f-l" for="fCompany">公司全称</label>
      <input class="big-inp" id="fCompany" name="company" required minlength="2" placeholder="例如：杭州银行股份有限公司" title="写营业执照上的全称，名单按全称核对"></div>
    <div class="f-row"><label class="f-l" for="fNeed">你要做什么</label>
      <textarea class="big-inp" id="fNeed" name="need" rows="2" placeholder="例如：我妈想在这家公司存 20 万理财，最怕急用时取不出来"></textarea>
      <div class="intake" id="intake">${intakeHtml()}</div></div>
    <div class="facts"><label>替 <input name="for_whom" placeholder="谁"> 看</label><label>金额 <input name="amount" class="mono" placeholder="可不填"></label><span class="muted small" id="amtHint"></span></div>
    <details class="mat" id="matBox"><summary>有宣传单、合同或聊天记录？贴进来就能逐条对照它的说法</summary>
      <div class="mat-tools"><span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="fFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="muted small" id="readNote"></span></div>
      <input class="big-inp sm" name="material_title" placeholder="材料名称，例如：业务员发的宣传单">
      <textarea class="big-inp sm" name="material_text" rows="5" placeholder="把材料上的文字贴在这里"></textarea>
    </details>
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
  form.for_whom.addEventListener('input', () => { S.form.dirty.for_whom = true; });
  form.amount.addEventListener('input', () => { S.form.dirty.amount = true; amtHint(); });
  $('#fFile').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    const note = $('#readNote');
    note.textContent = `正在读 ${file.name}…`;
    try {
      const r = await readFile(file);
      if (r.method === 'failed') { note.innerHTML = `<span class="err">读不出来：${esc(r.note || '')}请把文字手动贴进下面。</span>`; return; }
      form.material_text.value = r.text;
      if (!form.material_title.value) form.material_title.value = file.name;
      note.textContent = `已读出 ${r.text.length} 字（${{ text: '文本', pdf: 'PDF', vision: '看图识别' }[r.method] || r.method}），请核对一遍。`;
    } catch (err) { note.innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    finally { e.target.value = ''; }
  });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const company = form.company.value.trim();
    if (company.length < 2) { $('#formErr').textContent = '请填公司全称'; return; }
    const amount = parseAmount(form.amount.value);
    if (form.amount.value.trim() && !amount) { $('#formErr').textContent = '金额没看懂，写成 200000 或 20万，或者留空'; return; }
    await createCase({
      company_name: company, need: form.need.value.trim(),
      scenario: S.form.userScenario || null,
      for_whom: form.for_whom.value.trim() || null, amount,
      material_text: form.material_text.value.trim() || null,
      material_title: form.material_title.value.trim() || null,
    });
  });
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
    f.material_text.value = body.material_text || ''; f.material_title.value = body.material_title || '';
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
  f.material_text.value = d.input.material_text || ''; f.material_title.value = d.input.material_title || '';
  if (d.input.material_text) $('#matBox').open = true;
  S.form.userScenario = d.input.scenario || null;
  f.need.dispatchEvent(new Event('blur'));
  toast(`已填入演示案例 ${d.id}，点"生成报告"`);
}

// ---------- 报告页 ----------

async function openCase(id, no) {
  if (!S.case || S.case.id !== id) {
    $('#view').innerHTML = '<div class="home"><p class="muted">读取案卷…</p></div>';
    try { S.case = await api(`/api/cases/${encodeURIComponent(id)}`); }
    catch (e) {
      $('#view').innerHTML = `<div class="home"><div class="ask-card"><h2>打不开这个案卷</h2><p class="err">${esc(e.message)}</p><a class="btn sm" href="#/">回到首页</a></div></div>`;
      return;
    }
    S.selected.clear(); S.opCache = {}; S.tab = 'signals'; S.openRest.clear();
    S.reviews = null; S.rvStars = 0; S.rvRel = null;
  }
  const next = no && S.case.versions.some(v => v.no === no) ? no : S.case.current;
  if (S.viewNo !== next) S.selected.clear();
  S.viewNo = next;
  renderCase();
}

function renderCase() {
  const c = S.case, v = ver();
  if (S.tab === 'changes' && v.no === 1) S.tab = 'signals';
  const assistOpen = $('#assist') && $('#assist').classList.contains('open');
  useTerms(v.terms && v.terms.length ? v.terms : S.terms);
  renderTop();
  $('#view').innerHTML = `
  <div class="case-layout">
    <div class="report" id="report">
      ${caseHead(c, v)}
      ${conclusionHtml(v)}
      ${chartsHtml(v)}
      ${v.no > 1 ? `<button type="button" class="chg-banner" data-act="tab" data-tab="changes"><b>第 ${v.no} 版 · ${esc(v.trigger_label)}</b><span>${esc((SHOW_JUDGMENTS && v.judgment_summary) || v.change_summary || '')}</span><em>看变化 →</em></button>` : ''}
      ${tabsHtml(v)}
      <div class="panel" id="panel" role="tabpanel">${panelHtml(v)}</div>
      <footer class="foot">结论来自公开记录和固定规则，AI 只负责读材料和说人话。这里不打安全分，也不给公司定性；"没查"不等于没问题，"查了没有"也只代表在那份数据里没有。</footer>
    </div>
    <aside class="assist${assistOpen ? ' open' : ''}" id="assist" aria-label="小企（AI 栏）">${assistHtml()}</aside>
  </div>
  ${qiLauncherHtml()}`;
  loadOnepager(v);
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
    ${v.notes && v.notes.length ? `<ul class="notes">${v.notes.map(t => `<li${/演示|虚构/.test(t) ? ' class="demo"' : ''}>${esc(t)}</li>`).join('')}</ul>` : ''}
  </header>`;
}

// 第一层：一眼看懂（屏幕上）+ 一页结论（文字版，给家人看、打印）
function conclusionHtml(v) {
  return `<section class="conclusion" id="L1">
    <div class="cc-bar"><span class="kicker">一眼看懂</span>
      <button type="button" class="linkish" data-act="optext">${S.showText ? '收起文字版' : '文字版（给家人看）'}</button>
      <button type="button" class="linkish" data-act="print">打印</button></div>
    <div class="glance">${glanceHtml(v)}</div>
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
    ${refs.length || params.length ? `<div class="v-src">出处 ${refs.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(r)}</button>`).join('')}${params.map(s => srcLink(s)).join('')}</div>` : ''}
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
  for (const s of v.signals) for (const i of s.items) m[`${s.key}.${i.key}`] = { status: i.status, text: `${i.label}：${i.value}` };
  return m;
}
function answerOf(sts) {
  const worst = sts.reduce((w, s) => (SEV[s] > SEV[w] ? s : w), 'ok');
  if (worst === 'bad') return ['bad', '有问题'];
  if (worst === 'warn') return ['warn', '要留意'];
  if (worst === 'miss') return ['miss', '还缺证据'];
  const none = sts.filter(s => s === 'none').length;
  if (none === sts.length) return ['none', '没查到数据'];
  return none ? ['none', '查过的没问题', `另有 ${none} 项没查`] : ['ok', '查过，没发现问题'];
}
function glanceHtml(v) {
  const items = glanceItems(v), seen = new Set();
  const sc = S.scenarios.find(s => s.id === v.scenario);
  const firstIds = ((v.glance && v.glance.first.length) ? v.glance.first : (sc && sc.first_items) || []).filter(id => items[id]);
  const bySev = (a, b) => SEV[items[b].status] - SEV[items[a].status];

  // 第一问
  let first = '';
  if (sc && firstIds.length) {
    const [st, word, note] = answerOf(firstIds.map(id => items[id].status));
    // 下面"它说的 ⟷ 记录里的"已经列了说法，这里只列记录本身；没有记录条目才列说法
    const lines = firstIds.filter(id => !/^[AM]\d+$/.test(id));
    const show = lines.length ? lines : firstIds;
    first = `<div class="gl-first s-${st}">
      <div class="gl-q">第一问：${esc(sc.first_question)}？</div>
      <div class="gl-a"><span class="mk">${MARK[st]}</span><span>${esc(word)}${note ? `<small>${esc(note)}</small>` : ''}</span></div>
      <ul>${[...show].sort(bySev).slice(0, 4).map(id => `<li class="s-${items[id].status}" data-act="goto" data-id="${esc(id)}" tabindex="0" role="link"><span class="mk">${MARK[items[id].status]}</span><span>${termText(shortOf(v, id, items[id].text), seen)}</span></li>`).join('')}</ul>
    </div>`;
  }

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
    const nOk = s.items.filter(i => i.status === 'ok').length, nNone = s.items.filter(i => !isRef(i)).length - flagged.length - nOk;
    const st = flagged.length ? flagged[0].status : (nOk && !nNone ? 'ok' : 'none');
    const phrase = flagged.length ? shortOf(v, `${s.key}.${flagged[0].key}`, `${flagged[0].label}：${flagged[0].value}`)
      : !nOk ? '没查到数据' : nNone ? `查过的没问题，${nNone} 项没查` : '查过的没问题';
    return `<button type="button" class="tile s-${st}" data-act="sigtile" data-key="${s.key}">
      <span class="t-h"><b>${esc(s.title)}</b><span class="mk">${MARK[st]}</span></span>
      <span class="t-p">${esc(phrase)}</span>${flagged.length > 1 ? `<span class="t-n">共 ${flagged.length} 项要看</span>` : ''}</button>`;
  }).join('');

  const q = v.questions[0];
  const ai = v.glance && ['model', 'replay'].includes(v.glance.mode);
  return `${first}
    <div class="gl-grid">
      <div><h4 class="gl-h">它说的 <span>⟷</span> 记录里的</h4>${pairs}</div>
      <div><h4 class="gl-h">四个信号</h4><div class="tiles">${tiles}</div></div>
    </div>
    ${q ? `<div class="gl-next"><span class="kicker">下一步，先问对方</span><p>${termText(q.ask, seen)}</p>
      <span class="small muted">${termText(q.check_where, seen)}</span>
      ${v.questions.length > 1 ? ` <button type="button" class="linkish small" data-act="tab" data-tab="questions">全部 ${v.questions.length} 个问题 →</button>` : ''}</div>` : ''}
    ${ai ? '<p class="gl-ai">短句由 AI 按规则结论缩写，程序核对过数字和措辞；点任一行看完整原句和出处。</p>' : ''}`;
}
const currentOp = v => (S.audience === 'family' && v.onepager) || S.opCache[`${v.no}:${S.audience}`] || null;
async function loadOnepager(v) {
  if (currentOp(v)) return;
  const key = `${v.no}:${S.audience}`;
  try {
    S.opCache[key] = await api(`/api/cases/${encodeURIComponent(S.case.id)}/onepager?audience=${S.audience}&version=${v.no}`);
    if (ver() === v) $('#onepager').innerHTML = opBody(S.opCache[key], v);
  } catch (e) { $('#onepager').innerHTML = `<p class="err">一页结论没生成出来：${esc(e.message)}</p>`; }
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
    <p class="op-foot">${esc(op.footer)}</p>`;
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
  const tabs = Object.keys(TABS).filter(k => (k !== 'changes' || v.no > 1) && (k !== 'judgments' || (SHOW_JUDGMENTS && jug.length)));
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
      ${refs.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(r)}</button>`).join('')}
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
            ${(c.because || []).length ? `<div class="chg-src">依据 ${c.because.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}">${esc(r)}</button>`).join('')}</div>` : ''}
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
        ${x.because.length ? `<div class="chg-src">依据 ${x.because.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(x.quote ? [x.quote] : []))}">${esc(r)}</button>`).join('')}</div>` : ''}
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
  const nOk = rest.filter(i => i.status === 'ok').length, nRef = rest.filter(isRef).length, nNone = rest.length - nOk - nRef;
  const restLabel = [nOk && `${nOk} 项没问题`, nNone && `${nNone} 项没查`, nRef && '用户评价只作参考'].filter(Boolean).join('、');
  // 没查不等于没问题：有没查的项就不用绿色
  const head = flagged.length ? ['', `${flagged.length} 项要看`]
    : !nOk ? [' none', '没查到数据'] : nNone ? [' none', `查过的没问题，${nNone} 项没查`] : [' zero', '查过的没问题'];
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
      <div class="wm">${esc(hh.category || '其他')} · ${esc(hh.site || '')}${hh.date ? ' · ' + esc(hh.date) : ''}${hh.ref ? ` · <button type="button" class="cite" data-act="raw" data-ref="${esc(hh.ref)}">${esc(hh.ref)}</button>` : ''}</div>
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
      <div class="wm">${esc(hh.category || '其他')} · ${esc(hh.site || '')}${hh.date ? ' · ' + esc(hh.date) : ''}${hh.ref ? ` · <button type="button" class="cite" data-act="raw" data-ref="${esc(hh.ref)}">${esc(hh.ref)}</button>` : ''}</div>
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
        <div class="cl-f">${srcLink(m.source)}${m.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}">看材料 ${esc(r)}</button>`).join('')}</div></article>`; }).join('')}</div>` : ''}`;
}
function claimCard(a, cm) {
  const seen = new Set();   // 对方原话里的词（"保本保息""资金存管"）最需要解释，先标
  return `<article class="claim ${esc(a.color)}${selCls(a.id)}" data-item="${esc(a.id)}">
    <div class="cl-h"><q>${termText(a.text, seen)}</q><span class="verdict">${esc(a.verdict_label)}</span>${chgTag(a.id, cm)}${askBtn(a.id)}</div>
    <p class="cl-p"><span class="ckind">${termText(a.kind_label, seen)}</span>${termText(a.plain, seen)}</p>
    <div class="cl-f">
      ${a.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(a.quotes))}">看原文 ${esc(r)}</button>`).join('')}
      <details><summary>怎么查的（${a.checks.length} 项）</summary><ul class="checks">${a.checks.map(ck => `<li class="s-${esc(ck.status)}">
        <span class="ck-l">${termText(ck.label, seen)}</span><span class="ck-s">${STATUS[ck.status] || ''}</span><div>${termText(ck.result, seen)}</div>${srcLink(ck.source, ck.ref)}</li>`).join('')}</ul></details>
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
        <span class="rid">${esc(r.id)}</span>
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
  if (S.tab === 'reviews' && rerender) renderPanel();
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
  return `<form class="rv-form" id="rvForm" novalidate>
    <h4>写一条评价</h4>
    <div class="rv-row"><span class="lbl">打几星</span><span class="stars" role="group" aria-label="星级">${[1, 2, 3, 4, 5].map(n => `<button type="button" class="star" data-act="rv-star" data-n="${n}" aria-pressed="${n <= S.rvStars}" aria-label="${n} 星">★</button>`).join('')}</span><span class="small muted" id="rvStarTxt">${S.rvStars ? `${S.rvStars} 星` : ''}</span></div>
    <div class="rv-row"><span class="lbl">你是它的</span><span class="seg">${Object.entries(REL).map(([k, l]) => `<button type="button" data-act="rv-rel" data-rel="${k}" aria-pressed="${S.rvRel === k}">${l}</button>`).join('')}</span></div>
    <textarea class="big-inp sm" name="text" rows="4" maxlength="500" placeholder="写你遇到的事：对方怎么说的、钱打到哪、能不能取出来。10–500 字。手机号、身份证号会自动遮掉。"></textarea>
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
  const btn = f.querySelector('[type="submit"]');
  btn.disabled = true; btn.textContent = '正在发布…';
  try {
    S.reviews = await api('/api/reviews', { method: 'POST', body: { company: S.case.case.company_name, stars: S.rvStars,
      relation: S.rvRel, text, nickname: f.nickname.value.trim() || null, author: AUTHOR } });
    S.rvStars = 0; S.rvRel = null;
    refreshReviewTab();
    toast('已发布。报告要算进这条，点"放进报告"');
  } catch (e) {
    err.textContent = '没发出去：' + e.message;
    btn.disabled = false; btn.textContent = '发布评价';
  }
}
async function refreshReviews(el) {
  el.disabled = true; el.textContent = '正在重新判断…';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(S.case.id)}/reviews`, { method: 'POST' });
    S.case = c; S.opCache = {}; S.tab = 'changes';
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    setTimeout(() => { const t = $('.chg-banner'); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    toast(`已生成第 ${c.current} 版`);
  } catch (e) {
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
  let html = esc(text);
  for (const q of quotes || []) {
    const e = esc(q).trim();
    if (e.length >= 2) html = html.split(e).join(`<mark>${e}</mark>`);
  }
  return html;
}
function valHtml(val) {
  if (val == null || val === '') return '<span class="muted">—</span>';
  if (typeof val === 'boolean') return val ? '是' : '否';
  if (typeof val === 'object') return `<pre class="json">${esc(JSON.stringify(val, null, 2))}</pre>`;
  return esc(val);
}
function contentHtml(content, quotes) {
  if (content == null) return '<p class="muted">这条记录没有内容（没查或查询失败）。</p>';
  if (typeof content === 'string') return `<pre>${markText(content, quotes)}</pre>`;
  const table = obj => `<table>${Object.entries(obj).map(([k, val]) => `<tr><th>${esc(k)}</th><td>${valHtml(val)}</td></tr>`).join('')}</table>`;
  if (Array.isArray(content)) {
    if (!content.length) return '<p class="muted">空列表。</p>';
    return content.map(it => `<div class="item">${it && typeof it === 'object' && !Array.isArray(it) ? table(it) : valHtml(it)}</div>`).join('');
  }
  return table(content);
}
function openRaw(rid, quotes) {
  const r = rawById(rid);
  if (!r) { toast(`案卷里没有 ${rid}`, true); return; }
  const s = srcOf(r.source_id), back = backRefs(rid), kind = rawKind(r);
  const dlg = $('#rawDlg');
  dlg.innerHTML = `<div class="dlg-in">
    <div class="dlg-head"><div><div class="kicker">原始数据 ${esc(r.id)} · <span class="k-${esc(kind)}">${esc(KIND[kind] || r.kind)}</span> · <span class="covl ${esc(r.coverage)}">${COVERAGE[r.coverage] || ''}</span></div>
      <h3 id="rawTitle">${esc(r.title)}</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <dl class="kv">
        <dt>来源</dt><dd>${esc(s ? s.name : r.source_id)}${s && s.note ? `<div class="small muted">${esc(s.note)}</div>` : ''}</dd>
        ${r.as_of ? `<dt>数据截至</dt><dd class="mono">${esc(r.as_of)}</dd>` : ''}
        <dt>采集时间</dt><dd class="mono">${esc(fmtTime(r.retrieved_at))}</dd>
        ${r.url ? `<dt>原文链接</dt><dd><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a></dd>` : ''}
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
    b.setAttribute('aria-pressed', on); b.textContent = on ? '已选' : '问';
  });
  $$('#panel [data-item]').forEach(el => el.classList.toggle('is-sel', S.selected.has(el.dataset.item) && !el.classList.contains('raw-row')));
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
}

function modeLine() {
  const llm = S.health && S.health.llm;
  if (!llm) return '';
  if (!llm.configured || llm.mode === 'off') return '没接模型：用模板回答，只摘报告里的原话。';
  if (llm.mode === 'replay') return '离线回放：只用录好的模型回答。';
  return '只用这份案卷里的数据回答，关键事实标出处；没查到就直说。';
}
function assistHtml() {
  return `<div class="as-head"><div class="as-heading"><h3>小企 <span class="qi-role">报告助手</span></h3><p class="small muted">${esc(modeLine())}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="收起小企">×</button></div>
  <div class="as-body" id="asBody">${chatHtml()}</div>
  <div class="qi-perch">${qiAvatarHtml()}</div>
  <div class="as-sel" id="asSel">${selHtml()}</div>
  <form class="as-input" id="asForm"><textarea class="box" name="q" rows="2" maxlength="2000" placeholder="问这份报告里的任何一条…（Enter 发送）" aria-label="提问"></textarea><button class="btn sm" type="submit">问</button></form>`;
}
function selHtml() {
  if (!S.selected.size) return '<span class="muted">想问某一条？点报告里那一条右边的"问"。</span>';
  return `<span class="muted">针对：</span>${[...S.selected].map(id => `<span class="sel-chip">${esc(id)}<button type="button" data-act="unsel" data-id="${esc(id)}" aria-label="取消选中 ${esc(id)}">×</button></span>`).join('')}`;
}
function chatHtml() {
  const chat = S.case.chat;
  const sugg = ['它有没有资格收这笔钱？', '还有哪些没查到？', '我该先问对方什么？', '它被处罚或点名过吗？'];
  const intro = `<div class="as-intro"><div class="chips">${sugg.map(q => `<button type="button" class="chip" data-act="ask" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <p class="small muted">小企不会改报告。你在对话里说的新情况，要点"加入案卷"，系统才会重新判断。</p></div>`;
  return (chat.length ? '' : intro) + chat.map((m, i) => msgHtml(m, chat[i - 1])).join('') + (qiThinking() ? '<div class="typing" role="status"><span>小企正在思考</span><i aria-hidden="true"></i><i aria-hidden="true"></i><i aria-hidden="true"></i></div>' : '');
}
function citeText(text, version) {
  return esc(text).replace(/\[([A-Za-z0-9_.:,，、\s]+)\]/g, (all, inner) => {
    const ids = inner.split(/[,，、\s]+/).filter(Boolean);
    return ids.length && ids.every(isId) ? ids.map(id => goLink(id, version)).join('') : all;
  });
}
function msgHtml(m, prev) {
  if (m.role === 'user') {
    return `<div class="msg me"><div class="bubble">${esc(m.text)}</div>
      ${m.refs && m.refs.length ? `<div class="msg-refs">针对 ${m.refs.map(id => goLink(id, m.version)).join('')}</div>` : ''}</div>`;
  }
  const add = m.suggest.filter(s => s.includes('加入案卷'));
  const other = m.suggest.filter(s => !s.includes('加入案卷'));
  const vNote = S.case && m.version !== ver().no ? `<span>基于第 ${m.version} 版</span>` : '';
  const mode = m.mode ? `<span class="mode ${m.mode}">${MODE[m.mode]}${m.mode === 'replay' && m.recorded_at ? `（录于 ${esc(fmtTime(m.recorded_at))}）` : ''}</span>` : '';
  const blocked = (m.blocked || []).map(b => `“${esc(b)}”`).join('、');
  const rewrite = m.rewrites ? `<details class="rw"><summary>${m.mode === 'template'
    ? `模型的回答越界，重写 ${m.rewrites} 次没成功，改用模板回答` : `程序拦下了越界说法，让模型重写了 ${m.rewrites} 次`}</summary>
    被拦下的：${blocked}。这些是推测或定性，记录和规则里没有这样写。</details>` : '';
  return `<div class="msg ai${m.not_found ? ' nf' : ''}${m.mode === 'guard' ? ' guard' : ''}">
    <div class="ans">${citeText(m.text, m.version)}</div>
    ${(m.citations || []).length ? `<div class="msg-refs">出处 ${m.citations.map(id => goLink(id, m.version)).join('')}</div>` : ''}
    ${m.quotes.length ? `<div class="quotes"><div class="ql">原文（程序逐字核对过）</div>${m.quotes.map(q => `<blockquote>${esc(q.text)} ${/^R\d+$/.test(q.ref)
      ? `<button type="button" class="cite" data-act="raw" data-ref="${esc(q.ref)}" data-version="${m.version}" data-hl="${esc(JSON.stringify([q.text]))}">${esc(q.ref)}</button>` : goLink(q.ref, m.version)}</blockquote>`).join('')}</div>` : ''}
    ${other.length ? `<div class="sugg"><span>可以补充：</span>${other.map(s => `<button type="button" class="chip" data-act="supplement" data-kind="material" data-title="${esc(s)}">${esc(s)}</button>`).join('')}</div>` : ''}
    ${add.length && prev && prev.role === 'user' ? `<div class="add-case">你提到的像是新情况。<button type="button" class="btn sm" data-act="supplement" data-kind="reply" data-text="${esc(prev.text)}">加入案卷，重新判断</button></div>` : ''}
    <div class="msg-meta">${mode}${m.not_found ? '<span>数据里没有</span>' : ''}${m.dropped ? `<span>丢掉了 ${m.dropped} 条对不上的出处或引文</span>` : ''}${vNote}</div>
    ${rewrite}
  </div>`;
}
function refreshChat() {
  refreshQiState();
  const body = $('#asBody');
  if (body) { body.innerHTML = chatHtml(); scrollChat(); }
}
function scrollChat() { const b = $('#asBody'); if (b) b.scrollTop = b.scrollHeight; }

async function ask(q) {
  q = (q || '').trim();
  if (!q || S.busy || !S.case) return;
  const caseData = S.case, id = caseData.id, version = ver().no, selected = [...S.selected];
  const refs = selected.map(ref => chatRef(ref, version));
  S.busy = true;
  S.busyCaseId = id;
  const message = { role: 'user', text: q, refs, citations: [], quotes: [], suggest: [], version, created_at: new Date().toISOString() };
  caseData.chat.push(message);
  // 切走再回来可能重新加载了同一案卷；同步当前对象，但不触碰别的案卷。
  const targets = () => S.case && S.case.id === id && S.case !== caseData ? [caseData, S.case] : [caseData];
  const sameMessage = (a, b) => a === b || (a.role === b.role && a.version === b.version && a.text === b.text && a.created_at === b.created_at);
  S.selected.clear(); refreshSel(); refreshChat();
  $('#assist').classList.add('open');
  try {
    const reply = await api(`/api/cases/${encodeURIComponent(id)}/chat`, { method: 'POST', body: { text: q, refs, version } });
    const savedUser = { ...message, created_at: reply.created_at || message.created_at };
    for (const target of targets()) {
      const index = target.chat.findIndex(m => sameMessage(m, message) || sameMessage(m, savedUser));
      if (index === -1) target.chat.push(savedUser);
      else target.chat[index] = savedUser;
      if (!target.chat.some(m => sameMessage(m, reply))) target.chat.push(reply);
    }
  } catch (e) {
    for (const target of targets()) {
      const index = target.chat.findIndex(m => sameMessage(m, message));
      if (index !== -1) target.chat.splice(index, 1);
    }
    if (S.case && S.case.id === id && ver().no === version) {
      selected.forEach(r => S.selected.add(r)); refreshSel();
      const ta = $('#asForm textarea'); if (ta) ta.value = q;
    }
    toast('小企没答上来：' + e.message, true);
  } finally { S.busy = false; S.busyCaseId = null; refreshChat(); }
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
  const go = $('#resGo'); go.disabled = true; go.textContent = '正在出新版本…';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(S.case.id)}/resolve`, { method: 'POST',
      body: { judgment_id: dlg.dataset.jid, action: dlg.dataset.kind, note, by: '我' } });
    S.case = c; S.opCache = {}; S.tab = 'judgments'; dlg.close();
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    toast(`已记下，新增第 ${c.current} 版`);
  } catch (err) {
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
  const kind = opt.kind || 'material';
  const photo = !!opt.photo;                 // 拍合同进来：只收照片，手机直接开相机
  const dlg = $('#supDlg');
  const demo = demoForCase();
  const camOn = kind === 'material';
  dlg.innerHTML = `<form class="dlg-in" id="supForm" method="dialog">
    <div class="dlg-head"><div><div class="kicker">二次分析 · 将生成第 ${S.case.versions.length + 1} 版</div><h3 id="supTitle">${photo ? '拍合同 · 二次审核' : '补充信息'}</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <div class="seg sup-kinds" role="radiogroup" aria-label="补充什么">${Object.entries(SUP_KIND).map(([k, o]) => `<button type="button" data-act="sup-kind" data-kind="${k}" aria-pressed="${k === kind}">${o.label}</button>`).join('')}</div>
      <p class="sup-help" id="supHelp">${esc(photo ? '拍合同、补充协议、聊天里发的合同照片。合同有好几页就一次拍完，系统按张读成文字，读完你核对。' : SUP_KIND[kind].help)}</p>
      ${photo ? `<p class="sup-note">照片只证明你手上确实有这份纸。写了什么要看读出来的文字；签没签、对方认不认、照片有没有被改过，都不算验证过。所以这一版里，合同上的说法会记成「材料里写的」，和查询结果分开列。</p>` : ''}
      <div id="supMat"${kind === 'material' ? '' : ' hidden'}><div class="mat-tools">${camOn ? `<span class="btn sm cam file-btn">📷 拍照 / 选照片（可多张）<input type="file" id="supCam" accept="image/*" capture="environment" multiple></span>` : ''}<span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="supFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="muted small" id="supRead"></span></div></div>
      <div id="supScen"${kind === 'need' ? '' : ' hidden'}><div class="small muted">场景（不选就从新需求里识别）</div><div class="chips" style="margin:4px 0 10px">${S.scenarios.map(s => `<button type="button" class="chip" data-act="sup-scen" data-id="${esc(s.id)}" aria-pressed="false">${esc(s.label)}</button>`).join('')}</div></div>
      <input class="big-inp sm" name="title" id="supTitleIn" placeholder="${kind === 'reply' ? '例如：业务员的微信回复' : '材料名称，例如：认购协议'}" value="${esc(opt.title || '')}"${kind === 'need' ? ' hidden' : ''}>
      <textarea class="big-inp sm" name="text" rows="8" required placeholder="${kind === 'need' ? '例如：我收到这家公司的 offer，让我去做理财顾问' : '把文字贴在这里'}">${esc(opt.text || '')}</textarea>
      ${demo && demo.supplements.length ? `<div class="sup-demo"><span class="muted">演示案例准备好的补充：</span><div class="chips">${demo.supplements.map((s, i) => `<button type="button" class="chip" data-act="sup-fill" data-i="${i}">${esc(SUP_KIND[s.kind].label)}：${esc(s.title || s.text.slice(0, 18))}</button>`).join('')}</div></div>` : ''}
      <div class="err" id="supErr" role="alert"></div>
    </div>
    <div class="dlg-foot"><button type="button" class="btn ghost sm" data-act="close-dlg">取消</button><button type="submit" class="btn sm" id="supGo">生成新版报告</button></div>
  </form>`;
  dlg.dataset.kind = kind; dlg.dataset.scen = '';
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
  $('#supMat').hidden = kind !== 'material';
  $('#supScen').hidden = kind !== 'need';
  $('#supTitleIn').hidden = kind === 'need';
}
async function submitSupplement(e) {
  e.preventDefault();
  if (S.supplementBusy) { toast('已有补充信息正在处理，请稍候或到「案卷」查看'); return; }
  const dlg = $('#supDlg'), f = e.target;
  const kind = dlg.dataset.kind, text = f.text.value.trim();
  if (!text) { $('#supErr').textContent = '请填写内容'; return; }
  const body = { kind, text, title: kind === 'need' ? null : (f.title.value.trim() || null), scenario: kind === 'need' ? (dlg.dataset.scen || null) : null };
  const go = $('#supGo');
  const caseId = S.case.id, route = location.hash;
  const host = document.createElement('div'), scrollBody = f.querySelector('.dlg-body');
  scrollBody.append(host);
  const waiting = ResearchProgress.mount(host, S.case.case.company_name);
  scrollBody.scrollTop = scrollBody.scrollHeight;
  S.supplementBusy = true;
  go.disabled = true; go.textContent = '正在重新判断…';
  try {
    const c = await ResearchProgress.readCaseStream(`/api/cases/${encodeURIComponent(caseId)}/supplements/stream`, body, { onEvent: waiting.onEvent });
    if (!S.case || S.case.id !== caseId || location.hash !== route || !f.isConnected || !dlg.open) {
      toast('新版报告已生成，可以在「案卷」查看'); return;
    }
    S.case = c; S.opCache = {}; S.tab = 'changes';
    S.selected.clear(); S.reviews = null;
    dlg.close();
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    setTimeout(() => { const t = $('.chg-banner'); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    toast(`已生成第 ${c.current} 版`);
  } catch (err) {
    if (f.isConnected && dlg.open && S.case?.id === caseId) $('#supErr').textContent = '没生成出来：' + err.message;
    else toast('补充信息的连接已结束，请到「案卷」确认结果', true);
  } finally {
    waiting.stop(); host.remove(); S.supplementBusy = false;
    go.disabled = false; go.textContent = '生成新版报告';
  }
}

// ---------- 打印 ----------

function printOnepager() {
  if (!$('#onepager') || !currentOp(ver())) { toast('一页结论还没生成好'); return; }
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
    case 'go': location.hash = `#/${d.sec}`; break;
    case 'qi-nudge': toast('先打开一份案卷，小企才有数据可答'); break;
    case 'raw': if (selectRefVersion(d.version == null ? null : Number(d.version))) openRaw(d.ref, d.hl ? JSON.parse(d.hl) : []); break;
    case 'goto': gotoItem(d.id, d.version == null ? null : Number(d.version), el); break;
    case 'sel': toggleSel(d.id); break;
    case 'unsel': S.selected.delete(d.id); refreshSel(); break;
    case 'ver': location.hash = `#/case/${S.case.id}/v/${d.no}`; break;
    case 'tab': showTab(d.tab); break;
    case 'sigtile': S.tab = 'signals'; renderPanel(); { const c = $(`#sig-${d.key}`); if (c) { c.closest('.sig').scrollIntoView({ behavior: 'smooth', block: 'center' }); c.closest('.sig').classList.add('flash'); } } break;
    case 'optext': S.showText = !S.showText; $('.op-wrap').hidden = !S.showText; el.textContent = S.showText ? '收起文字版' : '文字版（给家人看）'; break;
    case 'rest': if (S.openRest.has(d.key)) S.openRest.delete(d.key); else S.openRest.add(d.key); renderPanel(); break;
    case 'aud': S.audience = d.aud; $$('[data-act="aud"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.aud === d.aud));
      $('#onepager').innerHTML = opBody(currentOp(ver()), ver()); loadOnepager(ver()); break;
    case 'print': printOnepager(); break;
    case 'term': termPop(el, d.term); break;
    case 'src': showSource(el, d.src); break;
    case 'close-pop': closePop(); break;
    case 'ask': ask(d.q); break;
    case 'open-assist': $('#assist').classList.add('open'); setTimeout(() => { const t = $('#asForm textarea'); if (t) t.focus(); }, 50); break;
    case 'close-assist': $('#assist').classList.remove('open'); break;
    case 'contract': openContract(); break;
    case 'supplement': openSupplement({ kind: d.kind, text: d.text, title: d.title }); break;
    case 'sup-kind': setSupKind(d.kind); break;
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
});
window.addEventListener('scroll', closePop, { passive: true });

// ---------- 路由与启动 ----------

async function route() {
  // The research room owns the homepage. The old full-material form remains at #/new.
  if (!location.hash || /^#\/(?:check)?\/?$/.test(location.hash)) {
    location.replace('/');
    return;
  }
  closePop();
  $$('dialog[open]').forEach(d => d.close());
  const m = location.hash.match(/^#\/case\/([\w-]+)(?:\/v\/(\d+))?/);
  if (m) {
    const sameCase = S.case && S.case.id === m[1];
    await openCase(m[1], m[2] ? +m[2] : null);
    if (!sameCase) window.scrollTo(0, 0);
    return;
  }
  // 三个分区。#/check、#/cases、#/me，其余（含空 hash）都当查企
  const sec = (location.hash.match(/^#\/(check|cases|me)/) || [])[1] || 'check';
  if (sec === 'cases') await renderCases();
  else if (sec === 'me') await renderMe();
  else await renderCheck();
  window.scrollTo(0, 0);
}

async function boot() {
  const [health, scenarios, sources, demos, glossary] = await Promise.allSettled([
    api('/api/health'), api('/api/scenarios'), api('/api/sources'), api('/api/demo/cases'), api('/api/glossary')]);
  S.health = health.value || null;
  S.scenarios = scenarios.value || [];
  S.sources = sources.value || [];
  S.demos = demos.value || [];
  setGlossary(glossary.value);
  if (!S.health) toast('连不上后端：先启动 backend（uvicorn app.main:app --port 8000）', true);
  window.addEventListener('hashchange', route);
  route();
}
boot();
