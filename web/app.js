/* 企er 前端：原生 JS，不打包。契约以 backend/app/models.py 为准。
 *
 * 路由：#/ 输入页；#/case/<id> 最新版报告；#/case/<id>/v/<n> 第 n 版。
 * 报告页：一页结论在最上面；四个信号、宣称 vs 记录、该问对方的、原始数据放在下面的标签页里，按需展开。
 * 页面里所有可点的东西都用 data-act 声明，统一在 onClick 里分发。
 * 条目 id：A1 说法、M1 缺项、risk.bank_list 信号条目、Q1 问题、R1 原始数据。R 开头的打开原始数据，其余跳到所在标签页里那一条。
 * 报告条目的锚点用 data-item；按钮要去的目标用 data-id，两者不要混用。
 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const KIND = { none: '没有数据', official: '官方记录', collected: '人工采集', commercial: '商业数据', regulation: '法规', parameter: '参数',
  demo: '演示·虚构', user_material: '用户材料', web: '网络公开' };
const COVERAGE = { found: '查到了', not_found: '查了没有', not_covered: '没查', failed: '查询失败' };
const STATUS = { bad: '有问题', warn: '要留意', miss: '该有的没有', none: '没查', ok: '没问题' };
const FLAG = new Set(['bad', 'warn', 'miss']);   // 要看的；ok、none 默认折叠
const CHANGE = { new_concern: '新疑点', worse: '更严重', clarified: '疑点减轻', unchanged: '没变', added: '新增', removed: '这版没有了' };
const MODE = { model: '模型回答', replay: '离线回放', template: '模板回答', guard: '已拦截' };
const TABS = { changes: '变化', signals: '四个信号', claims: '宣称 vs 记录', questions: '该问对方的', raw: '原始数据' };
const SUP_KIND = {
  material: { label: '新材料', help: '宣传单、合同、聊天记录的文字。可以上传图片、PDF、Word，读出来的文字会填进下面，你可以改。' },
  reply: { label: '对方的回复', help: '对方怎么回答你的问题。会记为"对方说的，未核实"，只用来对照，不当作事实。' },
  need: { label: '改需求', help: '换一句需求。事实不会变，变的是看的重点和措辞；变化清单会写明这一点。' },
};
// 名词解释来自后端的固定词表（/api/glossary，backend/app/glossary.json），不在前端写死
const S = {
  health: null, scenarios: [], sources: [], demos: [], cases: [],
  terms: [], termById: new Map(), termByName: new Map(), termRe: null,
  case: null, viewNo: null, selected: new Set(), busy: false, audience: 'family', opCache: {},
  tab: 'signals', openRest: new Set(), showText: false,
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
const isId = s => /^(R\d+|A\d+|M\d+|Q\d+|[a-z]+\.[a-z0-9_]+)$/.test(s);
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
const askBtn = id => `<button type="button" class="ask" data-act="sel" data-id="${esc(id)}" aria-pressed="${S.selected.has(id)}" title="选中这一条，去问助手">${S.selected.has(id) ? '已选' : '问'}</button>`;
const goLink = id => {
  const t = id.startsWith('term.') && termOf(id.slice(5));
  return `<button type="button" class="cite${t ? ' term-cite' : ''}" data-act="goto" data-id="${esc(id)}">${esc(t ? `名词·${t.term}` : id)}</button>`;
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
  $('#caseStrip').innerHTML = onCase ? `<span title="${esc(S.case.case.company_name)}">${esc(S.case.case.company_name)}</span>` : '';
  const llm = S.health && S.health.llm;
  let b = '';
  if (llm) {
    if (!llm.configured || llm.mode === 'off') b += '<span class="tb off" title="没接模型：需求识别用关键词，助手用模板回答">未接模型</span>';
    else if (llm.mode === 'replay') b += '<span class="tb replay" title="断网演示：只用录好的模型响应">离线回放</span>';
    else b += `<span class="tb live" title="${esc(llm.model || '')}">模型在线</span>`;
  }
  if (onCase && isDemoCase()) b += '<span class="tb demo" title="这家公司和它的记录都是编的，只用来演示">演示数据 · 公司为虚构</span>';
  $('#topBadges').innerHTML = b;
}

// ---------- 首页 ----------

async function renderHome() {
  S.case = null; useTerms(S.terms); renderTop();
  S.form = { userScenario: null, showScen: false, dirty: {}, intake: null };
  const h = S.health;
  const SHORT = { nfra_insurance: '保险', csrc_futures: '期货', pbc_payment: '支付', amac_managers: '私募' };
  const lists = h ? [{ title: '银行业', count: h.licensed_count },
    ...Object.entries(h.official_lists || {}).map(([k, l]) => ({ title: SHORT[k] || l.title, count: l.count }))] : [];
  $('#view').innerHTML = `
  <div class="home">
    <section class="home-hero">
      <div class="kicker">企er · 透视·真相</div>
      <h1>把钱交给一家公司之前，先看清它。</h1>
      <p>输入公司全称，说一句你要做什么。官方记录会汇到一起，对照它的说法，给你一份看得懂的报告。</p>
    </section>
    <div id="formWrap">${formHtml()}</div>
    <section class="recent" id="recent"></section>
    ${lists.length ? `<p class="lists-line">每家公司都查 ${lists.length} 份官方名单：${lists.map(l => `${esc(l.title)} ${(l.count || 0).toLocaleString()} 家`).join('、')}。要过验证码的网站（企业登记、被执行、裁判文书）我们不绕过，查不到的写"没查"。</p>` : ''}
  </div>`;
  bindForm();
  try {
    S.cases = await api('/api/cases');
    if (S.cases.length) $('#recent').innerHTML = `<h2>最近的案卷</h2>${S.cases.slice(0, 5).map(c => `<a href="#/case/${esc(c.id)}"><b>${esc(c.company_name)}</b><span>${esc(c.scenario_label)} · ${c.versions} 版 · ${esc(fmtTime(c.created_at).slice(5))}</span></a>`).join('')}`;
  } catch (e) { /* 列表读不到不影响新建 */ }
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
  const wrap = $('#formWrap');
  const keep = wrap.innerHTML;
  // 只列这次真的会查的：虚构的演示公司不联网搜，没接网关也不搜
  const h = S.health || {};
  const llmOn = h.llm && h.llm.configured && h.llm.mode !== 'off';
  const fictional = S.demos.some(d => !d.real && d.input && d.input.company_name === body.company_name);
  const names = ['银行业金融机构法人名单', ...Object.values(h.official_lists || {}).map(l => l.title),
    '企业登记和年报（证据包、商业接口、演示数据，有哪个用哪个）', '投诉记录'];
  if (llmOn && !fictional) names.push('监管、法院、政府网站上点名它的文件（联网搜索）', '公开报道和投诉（联网搜索）');
  if (body.material_text) names.push('你给的材料');
  wrap.innerHTML = `<section class="ask-card collecting" aria-busy="true">
    <div class="kicker">正在汇集</div>
    <h2>${esc(body.company_name)}</h2>
    <p class="small muted">正在查下面这些来源，查完一起出结果：</p>
    <ul>${names.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
    ${llmOn ? '<p class="small muted">查完后，规则先出结论，再由 AI 把结论缩成一眼能看懂的短句、补上名词解释（程序会逐条核对）。</p>' : ''}
    <div class="bar"></div>
    <p class="small muted" style="margin:10px 0 0">已用 <span class="mono" id="elapsed">0</span> 秒。联网查证的公司大约要 10 秒。</p>
  </section>`;
  const t0 = Date.now();
  const tick = setInterval(() => { const el = $('#elapsed'); if (el) el.textContent = Math.round((Date.now() - t0) / 1000); }, 500);
  try {
    const c = await api('/api/cases', { method: 'POST', body });
    S.case = c; S.viewNo = c.current; S.selected.clear(); S.opCache = {}; S.tab = 'signals'; S.openRest.clear();
    location.hash = `#/case/${c.id}`;
  } catch (e) {
    wrap.innerHTML = keep; bindForm();
    const f = $('#caseForm');
    f.company.value = body.company_name; f.need.value = body.need;
    f.for_whom.value = body.for_whom || ''; f.amount.value = body.amount ? fmtMoney(body.amount).replace(/\s/g, '') : '';
    f.material_text.value = body.material_text || ''; f.material_title.value = body.material_title || '';
    $('#intake').innerHTML = intakeHtml();
    $('#formErr').textContent = '没生成出来：' + e.message;
  } finally { clearInterval(tick); }
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
  }
  S.viewNo = no && S.case.versions.some(v => v.no === no) ? no : S.case.current;
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
      ${v.no > 1 ? `<button type="button" class="chg-banner" data-act="tab" data-tab="changes"><b>第 ${v.no} 版 · ${esc(v.trigger_label)}</b><span>${esc(v.change_summary || '')}</span><em>看变化 →</em></button>` : ''}
      ${tabsHtml(v)}
      <div class="panel" id="panel" role="tabpanel">${panelHtml(v)}</div>
      <footer class="foot">结论来自公开记录和固定规则，AI 只负责读材料和说人话。这里不打安全分，也不给公司定性；"没查"不等于没问题，"查了没有"也只代表在那份数据里没有。</footer>
    </div>
    <aside class="assist${assistOpen ? ' open' : ''}" id="assist" aria-label="AI 助手">${assistHtml()}</aside>
  </div>
  <button type="button" class="fab" data-act="open-assist">问助手${S.selected.size ? `<em>${S.selected.size}</em>` : ''}</button>`;
  loadOnepager(v);
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
      <button type="button" class="btn sm ghost" data-act="supplement">＋ 补充信息</button>
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
    const nOk = s.items.filter(i => i.status === 'ok').length, nNone = s.items.length - flagged.length - nOk;
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
  const changed = v.changes.filter(x => x.kind !== 'unchanged').length;
  const counts = { changes: [changed, changed > 0], signals: [flagged, flagged > 0], claims: [v.assertions.length + v.missing.length, (v.tally.red || 0) > 0],
    questions: [v.questions.length, false], raw: [v.raw_ids.length, false] };
  const tabs = Object.keys(TABS).filter(k => k !== 'changes' || v.no > 1);
  return `<nav class="tabs" role="tablist" aria-label="报告的各层">${tabs.map(k => `<button type="button" class="tab" role="tab" data-act="tab" data-tab="${k}" aria-selected="${S.tab === k}">${TABS[k]}<span class="n${counts[k][1] ? ' hot' : ''}">${counts[k][0]}</span></button>`).join('')}</nav>`;
}
function panelHtml(v) {
  const cm = changeMap(v);
  switch (S.tab) {
    case 'changes': return changesPanel(v);
    case 'claims': return claimsPanel(v, cm);
    case 'questions': return questionsPanel(v);
    case 'raw': return rawPanel(v);
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

function changesPanel(v) {
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
  const nOk = rest.filter(i => i.status === 'ok').length, nNone = rest.length - nOk;
  const restLabel = [nOk && `${nOk} 项没问题`, nNone && `${nNone} 项没查`].filter(Boolean).join('、');
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
    <div class="it-h"><span class="it-l">${termText(it.label, seen)}</span>${it.value === STATUS[it.status] ? '' : `<span class="it-s">${STATUS[it.status] || ''}</span>`}${chgTag(id, cm)}${askBtn(id)}</div>
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
  return out;
}

// 第三层：宣称 vs 记录
function claimsPanel(v, cm) {
  const t = v.tally || {};
  const parts = [['red', '条与记录不符或不合规'], ['amber', '条有误导或要留意'], ['grey', '条无法核验'], ['green', '条与记录相符']]
    .filter(([k]) => t[k]).map(([k, l]) => `<span class="t ${k}"><b>${t[k]}</b>${l}</span>`);
  if (t.missing) parts.push(`<span class="t amber"><b>${t.missing}</b>处该写没写</span>`);
  if (!v.assertions.length && !v.missing.length) {
    return `<div class="empty"><p>还没有这家公司的说法。上传宣传材料、合同或聊天记录，就能拿它的每句话去对照官方记录。</p><button type="button" class="btn sm" data-act="supplement" data-kind="material">补充材料</button></div>`;
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
  if (S.selected.has(id) && window.matchMedia('(max-width:1280px)').matches) toast(`已选中 ${id}，点右下角"问助手"提问`);
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
  if (fab) fab.innerHTML = `问助手${S.selected.size ? `<em>${S.selected.size}</em>` : ''}`;
}
function tabFor(id) {
  if (/^[AM]\d+$/.test(id)) return 'claims';
  if (/^Q\d+$/.test(id)) return 'questions';
  if (id.includes('.')) return 'signals';
  return null;
}
function gotoItem(id) {
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

// ---------- AI 助手 ----------

function modeLine() {
  const llm = S.health && S.health.llm;
  if (!llm) return '';
  if (!llm.configured || llm.mode === 'off') return '没接模型：用模板回答，只摘报告里的原话。';
  if (llm.mode === 'replay') return '离线回放：只用录好的模型回答。';
  return '只用这份案卷里的数据回答，关键事实标出处；没查到就直说。';
}
function assistHtml() {
  return `<div class="as-head"><div><h3>问助手</h3><p class="small muted">${esc(modeLine())}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="关闭助手">×</button></div>
  <div class="as-body" id="asBody">${chatHtml()}</div>
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
    <p class="small muted">助手不会改报告。你在对话里说的新情况，要点"加入案卷"，系统才会重新判断。</p></div>`;
  return (chat.length ? '' : intro) + chat.map((m, i) => msgHtml(m, chat[i - 1])).join('') + (S.busy ? '<div class="typing" aria-label="正在回答"><i></i><i></i><i></i></div>' : '');
}
function citeText(text) {
  return esc(text).replace(/\[([A-Za-z0-9_.,，、\s]+)\]/g, (all, inner) => {
    const ids = inner.split(/[,，、\s]+/).filter(Boolean);
    return ids.length && ids.every(isId) ? ids.map(goLink).join('') : all;
  });
}
function msgHtml(m, prev) {
  if (m.role === 'user') {
    return `<div class="msg me"><div class="bubble">${esc(m.text)}</div>
      ${m.refs && m.refs.length ? `<div class="msg-refs">针对 ${m.refs.map(goLink).join('')}</div>` : ''}</div>`;
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
    <div class="ans">${citeText(m.text)}</div>
    ${m.quotes.length ? `<div class="quotes"><div class="ql">原文（程序逐字核对过）</div>${m.quotes.map(q => `<blockquote>${esc(q.text)} ${/^R\d+$/.test(q.ref)
      ? `<button type="button" class="cite" data-act="raw" data-ref="${esc(q.ref)}" data-hl="${esc(JSON.stringify([q.text]))}">${esc(q.ref)}</button>` : goLink(q.ref)}</blockquote>`).join('')}</div>` : ''}
    ${other.length ? `<div class="sugg"><span>可以补充：</span>${other.map(s => `<button type="button" class="chip" data-act="supplement" data-kind="material" data-title="${esc(s)}">${esc(s)}</button>`).join('')}</div>` : ''}
    ${add.length && prev && prev.role === 'user' ? `<div class="add-case">你提到的像是新情况。<button type="button" class="btn sm" data-act="supplement" data-kind="reply" data-text="${esc(prev.text)}">加入案卷，重新判断</button></div>` : ''}
    <div class="msg-meta">${mode}${m.not_found ? '<span>数据里没有</span>' : ''}${m.dropped ? `<span>丢掉了 ${m.dropped} 条对不上的出处或引文</span>` : ''}${vNote}</div>
    ${rewrite}
  </div>`;
}
function refreshChat() {
  const body = $('#asBody');
  if (body) { body.innerHTML = chatHtml(); scrollChat(); }
}
function scrollChat() { const b = $('#asBody'); if (b) b.scrollTop = b.scrollHeight; }

async function ask(q) {
  q = (q || '').trim();
  if (!q || S.busy || !S.case) return;
  const id = S.case.id, refs = [...S.selected];
  S.busy = true;
  S.case.chat.push({ role: 'user', text: q, refs, citations: [], quotes: [], suggest: [], version: S.case.current, created_at: new Date().toISOString() });
  S.selected.clear(); refreshSel(); refreshChat();
  $('#assist').classList.add('open');
  try {
    const reply = await api(`/api/cases/${encodeURIComponent(id)}/chat`, { method: 'POST', body: { text: q, refs } });
    if (S.case && S.case.id === id) S.case.chat.push(reply);
  } catch (e) {
    if (S.case && S.case.id === id) {
      S.case.chat.pop(); refs.forEach(r => S.selected.add(r)); refreshSel();
      const ta = $('#asForm textarea'); if (ta) ta.value = q;
    }
    toast('助手没答上来：' + e.message, true);
  } finally { S.busy = false; refreshChat(); }
}

// ---------- 补充信息（二次分析） ----------

function demoForCase() {
  return S.case && S.demos.find(d => d.input && d.input.company_name === S.case.case.company_name);
}
function openSupplement(opt = {}) {
  const kind = opt.kind || 'material';
  const dlg = $('#supDlg');
  const demo = demoForCase();
  dlg.innerHTML = `<form class="dlg-in" id="supForm" method="dialog">
    <div class="dlg-head"><div><div class="kicker">二次分析 · 将生成第 ${S.case.versions.length + 1} 版</div><h3 id="supTitle">补充信息</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <div class="seg sup-kinds" role="radiogroup" aria-label="补充什么">${Object.entries(SUP_KIND).map(([k, o]) => `<button type="button" data-act="sup-kind" data-kind="${k}" aria-pressed="${k === kind}">${o.label}</button>`).join('')}</div>
      <p class="sup-help" id="supHelp">${esc(SUP_KIND[kind].help)}</p>
      <div id="supMat"${kind === 'material' ? '' : ' hidden'}><div class="mat-tools"><span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="supFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="muted small" id="supRead"></span></div></div>
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
  $('#supFile').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    const note = $('#supRead');
    note.textContent = `正在读 ${file.name}…`;
    try {
      const r = await readFile(file);
      if (r.method === 'failed') { note.innerHTML = `<span class="err">读不出来：${esc(r.note || '')}请手动贴文字。</span>`; return; }
      $('#supForm').text.value = r.text;
      if (!$('#supForm').title.value) $('#supForm').title.value = file.name;
      note.textContent = `已读出 ${r.text.length} 字，请核对。`;
    } catch (err) { note.innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    finally { e.target.value = ''; }
  });
  $('#supForm').addEventListener('submit', submitSupplement);
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
  const dlg = $('#supDlg'), f = e.target;
  const kind = dlg.dataset.kind, text = f.text.value.trim();
  if (!text) { $('#supErr').textContent = '请填写内容'; return; }
  const body = { kind, text, title: kind === 'need' ? null : (f.title.value.trim() || null), scenario: kind === 'need' ? (dlg.dataset.scen || null) : null };
  const go = $('#supGo');
  go.disabled = true; go.textContent = '正在重新判断…';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(S.case.id)}/supplements`, { method: 'POST', body });
    S.case = c; S.opCache = {}; S.tab = 'changes';
    dlg.close();
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    setTimeout(() => { const t = $('.chg-banner'); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    toast(`已生成第 ${c.current} 版`);
  } catch (err) {
    $('#supErr').textContent = '没生成出来：' + err.message;
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
    case 'raw': openRaw(d.ref, d.hl ? JSON.parse(d.hl) : []); break;
    case 'goto': if (d.id.startsWith('term.')) termPop(el, d.id.slice(5)); else gotoItem(d.id); break;
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
    case 'supplement': openSupplement({ kind: d.kind, text: d.text, title: d.title }); break;
    case 'sup-kind': setSupKind(d.kind); break;
    case 'sup-scen': { const dlg = $('#supDlg'); const on = dlg.dataset.scen !== d.id; dlg.dataset.scen = on ? d.id : '';
      $$('[data-act="sup-scen"]', dlg).forEach(b => b.setAttribute('aria-pressed', on && b.dataset.id === d.id)); } break;
    case 'sup-fill': { const s = demoForCase().supplements[+d.i]; setSupKind(s.kind); const f = $('#supForm'); f.text.value = s.text; f.title.value = s.title || ''; } break;
    case 'close-dlg': el.closest('dialog').close(); break;
    case 'demo-fill': fillDemo(d.id); break;
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
});
window.addEventListener('scroll', closePop, { passive: true });

// ---------- 路由与启动 ----------

async function route() {
  closePop();
  $$('dialog[open]').forEach(d => d.close());
  const m = location.hash.match(/^#\/case\/([\w-]+)(?:\/v\/(\d+))?/);
  if (m) {
    const sameCase = S.case && S.case.id === m[1];
    await openCase(m[1], m[2] ? +m[2] : null);
    if (!sameCase) window.scrollTo(0, 0);
  } else {
    await renderHome();
    window.scrollTo(0, 0);
  }
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
