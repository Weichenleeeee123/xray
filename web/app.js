/* X-Ray 前端：原生 JS，不打包。契约以 backend/app/models.py 为准。
 *
 * 路由：#/ 输入页；#/case/<id> 最新版报告；#/case/<id>/v/<n> 第 n 版。
 * 页面里所有可点的东西都用 data-act 声明，统一在 onClick 里分发。
 * 条目 id：A1 说法、M1 缺项、risk.bank_list 信号条目、Q1 问题、R1 原始数据。R 开头的打开原始数据，其余滚动到报告里那一条。
 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const KIND = { none: '没有数据', official: '官方记录', collected: '人工采集', commercial: '商业数据', regulation: '法规', parameter: '参数',
  demo: '演示·虚构', user_material: '用户材料', web: '网络公开' };
const COVERAGE = { found: '查到了', not_found: '查了没有', not_covered: '没查', failed: '查询失败' };
const STATUS = { bad: '有问题', warn: '要留意', miss: '该有的没有', none: '没查', ok: '没问题' };
const STATUS_CLS = { bad: 'red', warn: 'amber', miss: 'miss', none: 'none', ok: 'green' };
const CHANGE = { new_concern: '新疑点', worse: '更严重', clarified: '疑点减轻', unchanged: '没变', added: '新增', removed: '这版没有了' };
const SIGNAL_EN = { risk: 'RISK', finance: 'FINANCE', credit: 'CREDIT', reputation: 'REPUTATION' };
const MODE = { model: '模型回答', replay: '离线回放', template: '模板回答', guard: '已拦截' };
const SUP_KIND = {
  material: { label: '新材料', help: '宣传单、合同、聊天记录的文字。可以上传图片、PDF、Word，读出来的文字会填进下面，你可以改。' },
  reply: { label: '对方的回复', help: '对方怎么回答你的问题。会记为"对方说的，未核实"，只用来对照，不当作事实。' },
  need: { label: '改需求', help: '换一句需求。事实不会变，变的是看的重点和措辞；变化清单会写明这一点。' },
};
const TERMS = {
  '持牌机构名单': '金融监管部门公布的持牌金融机构名单。吸收存款、卖理财、做保险、做支付都要持牌。这几份名单里查不到它，说明它至少不是这几类持牌机构。',
  '私募基金管理人登记': '在中国证券投资基金业协会（中基协）登记过的机构才能发私募基金。登记只是备案，不代表协会为它担保。',
  '理财产品登记编码': '正规理财产品都有登记编码，可以在中国理财网（chinawealth.com.cn）查到。',
  '实缴资本': '股东实际已经拿出来的钱。注册资本多数是"认缴"，也就是承诺将来出，可能一分都还没出。',
  '注册资本': '股东承诺出资的总额。多数是认缴，不等于公司账上真有这么多钱。',
  '经营范围': '营业执照上写的公司能做的业务。卖理财、吸收存款这类金融业务，必须持牌才能做。',
  '参保人数': '公司给多少人交了社保，来自年报，能侧面看出公司实际有多少员工。',
  '股权出质': '股东把股权质押出去借钱。出质多，可能说明股东缺钱。',
  '风险提示语': '正规理财销售材料必须写的提醒，例如"理财非存款、产品有风险、投资须谨慎"。',
  '收益承诺': '承诺保本保息、固定高收益。正规理财产品不允许这样承诺。',
  '收款信息': '钱打到哪个账户、户名是谁。户名应当就是和你签约的这家公司。',
  '退款承诺': '"随时可退""随时取出"这类说法。要写进合同才作数。',
};

const S = {
  health: null, scenarios: [], sources: [], demos: [], cases: [],
  case: null, viewNo: null, selected: new Set(), busy: false, audience: 'family', opCache: {},
  form: { userScenario: null, dirty: {}, intake: null, read: null },
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

const termify = label => (TERMS[label] ? `<button type="button" class="term" data-act="term" data-term="${esc(label)}">${esc(label)}</button>` : esc(label));
const stBadge = st => `<span class="st ${STATUS_CLS[st] || 'none'}">${STATUS[st] || st}</span>`;
const selBtn = id => `<button type="button" class="selbtn" data-act="sel" data-id="${esc(id)}" aria-pressed="${S.selected.has(id)}" title="选中这一条，再去问助手">${S.selected.has(id) ? '已选中' : '选中提问'}</button>`;
const goLink = id => `<button type="button" class="cite" data-act="goto" data-id="${esc(id)}">${esc(id)}</button>`;
const refLinks = refs => (refs || []).map(r => `<button type="button" class="rf" data-act="goto" data-id="${esc(r)}">${esc(r)}</button>`).join('');

function srcTag(sourceId, ref) {
  const s = srcOf(sourceId), r = ref && rawById(ref);
  const kind = (r && rawKind(r)) || (s && s.kind) || '';
  const date = kind === 'none' ? null : (r && r.as_of) || (s && s.as_of);
  const title = s ? s.name : sourceId;
  const inner = `<span class="k-${esc(kind)}">${esc(KIND[kind] || '来源')}</span>${date ? `<time>${esc(date)}</time>` : ''}${ref ? `<b>${esc(ref)}</b>` : ''}`;
  return ref
    ? `<button type="button" class="src" data-act="raw" data-ref="${esc(ref)}" title="${esc(title)} · 点开看原始数据">${inner}</button>`
    : `<button type="button" class="src" data-act="src" data-src="${esc(sourceId)}" title="${esc(title)}">${inner}</button>`;
}

function changeMap(v) {
  const m = {};
  if (v && v.no > 1) for (const c of v.changes) if (c.kind !== 'unchanged') m[c.target] = c.kind;
  return m;
}
function chgTag(id, cm) {
  const k = cm[id];
  return k ? `<span class="chg-tag ${k}" title="和上一版比">${CHANGE[k]}</span>` : '';
}

// ---------- 顶栏 ----------

function renderTop() {
  const strip = $('#caseStrip'), badges = $('#topBadges');
  const v = ver();
  strip.innerHTML = S.case && location.hash.startsWith('#/case/')
    ? `<span title="${esc(S.case.case.company_name)}">${esc(S.case.case.company_name)}</span><span>案卷 ${esc(S.case.id)}</span><span>第 ${v.no} 版 / 共 ${S.case.versions.length} 版</span>`
    : '';
  const llm = S.health && S.health.llm;
  let b = '';
  if (llm) {
    if (!llm.configured || llm.mode === 'off') b += '<span class="tb off" title="没接模型：需求识别用关键词，助手用模板回答">未接模型</span>';
    else if (llm.mode === 'replay') b += '<span class="tb replay" title="断网演示：只用录好的模型响应">离线回放</span>';
    else b += `<span class="tb live" title="${esc(llm.model || '')}">模型在线</span>`;
  }
  if (S.case && location.hash.startsWith('#/case/') && isDemoCase()) b += '<span class="tb demo" title="这家公司和它的记录都是编的，只用来演示">演示数据 · 公司为虚构</span>';
  badges.innerHTML = b;
}

// ---------- 首页 ----------

async function renderHome() {
  S.case = null; renderTop();
  S.form = { userScenario: null, dirty: {}, intake: null, read: null };
  const lists = S.health ? [{ title: '银行业金融机构法人名单', count: S.health.licensed_count, as_of: S.health.licensed_as_of },
    ...Object.values(S.health.official_lists || {})] : [];
  $('#view').innerHTML = `
  <div class="home">
    <section class="hero">
      <div>
        <div class="kicker">杭州银行赛题 · X-RAY 透视·真相</div>
        <h1>把钱或信任交给一家公司之前，<br>先看清它。</h1>
        <p>输入公司全称，说一句你要做什么。我们把散在各处的官方记录汇到一起，对照它的说法，交给你一份看得懂的报告；每条结论都能点开原始数据。看不懂就问助手，有了新情况就补进来。</p>
      </div>
      <div class="film-mini" aria-hidden="true"><svg viewBox="0 0 40 50"><path d="M20 2v46M9 10c5.5 3 16.5 3 22 0M6 19c7 3.6 21 3.6 28 0M8 28c6 3 18 3 24 0M11 37c4.6 2.4 13.4 2.4 18 0" stroke="#c4f0ff" stroke-width="1.4" fill="none" stroke-linecap="round" opacity=".85"/></svg><div class="scan"></div></div>
    </section>
    <div class="home-grid">
      <div id="formWrap">${formHtml()}</div>
      <div class="side">
        <section class="card"><h2>演示案例</h2><ul class="demo-list" id="demoList">${demoListHtml()}</ul></section>
        <section class="card"><h2>最近的案卷</h2><ul class="case-list" id="caseList"><li class="muted small">读取中…</li></ul></section>
        <section class="card"><h2>每家公司都查这些名单</h2>
          <ul class="lists">${lists.map(l => `<li><span>${esc(l.title)}</span><span class="mono">${(l.count || 0).toLocaleString()} 家 · ${esc(l.as_of || '')}</span></li>`).join('') || '<li class="muted">读取中…</li>'}</ul>
          <p class="hint">全部是官方公布的整份名单，已入库。企业登记、处罚、被执行等要过验证码的网站，我们不绕过：配了模型网关就联网搜监管和法院网站上点名它的文件，其余写"没查"。</p>
        </section>
      </div>
    </div>
  </div>`;
  bindForm();
  try {
    S.cases = await api('/api/cases');
    $('#caseList').innerHTML = S.cases.length
      ? S.cases.slice(0, 8).map(c => `<li><a href="#/case/${esc(c.id)}"><b>${esc(c.company_name)}</b><span>${esc(c.scenario_label)} · ${c.versions} 版 · ${esc(fmtTime(c.created_at))}</span></a></li>`).join('')
      : '<li class="muted small">还没有案卷。</li>';
  } catch (e) { $('#caseList').innerHTML = `<li class="err">${esc(e.message)}</li>`; }
}

function demoListHtml() {
  if (!S.demos.length) return '<li class="muted small">没有演示案例。</li>';
  return S.demos.map(d => `<li>
    <div class="dl-h"><b>${esc(d.id)} · ${esc(d.label)}</b>${d.ready ? `<button type="button" class="btn sm ghost" data-act="demo-fill" data-id="${esc(d.id)}">填入</button>` : '<span class="small muted">未准备好</span>'}</div>
    ${d.note ? `<div class="hint">${esc(d.note)}</div>` : ''}</li>`).join('');
}

function formHtml() {
  return `<form class="card" id="caseForm" autocomplete="off">
    <h2>看一家公司</h2>
    <div class="field"><label for="fCompany">公司全称</label>
      <div><input class="inp" id="fCompany" name="company" required minlength="2" placeholder="例如：杭州银行股份有限公司">
      <div class="hint">写营业执照上的全称。名单按全称核对，简称容易对错公司。</div></div></div>
    <div class="field"><label for="fNeed">一句需求</label>
      <div><textarea class="box" id="fNeed" name="need" rows="2" placeholder="例如：我妈想在这家公司存 20 万理财，最怕急用时取不出来"></textarea>
      <div class="intake" id="intake">${intakeHtml()}</div></div></div>
    <div class="field"><span class="lab">替谁看</span>
      <div class="pair"><input class="inp" name="for_whom" placeholder="例如：妈妈（可不填）"><div><input class="inp mono" name="amount" placeholder="金额，例如 20万（可不填）"><div class="hint" id="amtHint"></div></div></div></div>
    <div class="field mat"><span class="lab">材料<br><small>可选</small></span>
      <div><details id="matBox"><summary>有宣传单、合同或聊天记录？贴进来就能逐条对照它的说法</summary>
        <div class="mat-tools"><span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="fFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="read-note muted" id="readNote"></span></div>
        <input class="inp" name="material_title" placeholder="材料名称，例如：业务员发的宣传单" style="font-size:14px;margin-bottom:8px">
        <textarea class="box" name="material_text" rows="6" placeholder="把材料上的文字贴在这里"></textarea>
      </details></div></div>
    <div class="submit-row"><button class="btn" type="submit" id="fSubmit">生成报告</button><span class="small muted">只填公司和需求也能出报告。</span></div>
    <div class="err" id="formErr" role="alert"></div>
  </form>`;
}

function intakeHtml() {
  const f = S.form, it = f.intake;
  const chosen = f.userScenario || (it && it.scenario);
  const sc = S.scenarios.find(s => s.id === chosen);
  const how = f.userScenario ? '你选的' : it ? (it.method === 'model' ? '模型识别' : `关键词识别${it.matched && it.matched.length ? '：' + it.matched.join('、') : ''}`) : '';
  return `<div class="hint" style="margin-top:8px">${it || f.userScenario ? `场景（${esc(how)}，可以改）` : '写完需求会自动识别场景，也可以直接选：'}</div>
    <div class="chips" style="margin-top:4px">${S.scenarios.map(s => `<button type="button" class="chip" data-act="scenario" data-id="${esc(s.id)}" aria-pressed="${s.id === chosen}">${esc(s.label)}</button>`).join('')}</div>
    ${sc ? `<div class="first-q">先回答这一问：<b>${esc(sc.first_question)}</b></div>` : ''}
    ${it && it.focus && it.focus.length ? `<div class="hint" style="margin-top:6px">你最担心的：</div><ul class="focus-list">${it.focus.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}`;
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
    $('#amtHint').textContent = form.amount.value.trim() ? (n ? `= ${n.toLocaleString()} 元` : '没看懂这个金额，写成 200000 或 20万') : '';
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
      note.textContent = `已读出 ${r.text.length} 字（${{ text: '文本', pdf: 'PDF', vision: '看图识别' }[r.method] || r.method}）${r.note ? '。' + r.note : ''}。请核对一遍。`;
    } catch (err) { note.innerHTML = `<span class="err">${esc(err.message)}</span>`; }
    finally { e.target.value = ''; }
  });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const company = form.company.value.trim();
    if (company.length < 2) { $('#formErr').textContent = '请填公司全称'; return; }
    const amount = parseAmount(form.amount.value);
    if (form.amount.value.trim() && !amount) { $('#formErr').textContent = '金额没看懂，写成 200000 或 20万，或者留空'; return; }
    const body = {
      company_name: company, need: form.need.value.trim(),
      scenario: S.form.userScenario || null,
      for_whom: form.for_whom.value.trim() || null, amount,
      material_text: form.material_text.value.trim() || null,
      material_title: form.material_title.value.trim() || null,
    };
    await createCase(body);
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
  wrap.innerHTML = `<section class="card collecting" aria-busy="true">
    <div class="kicker">正在汇集</div>
    <h2>${esc(body.company_name)}</h2>
    <p class="small">正在查下面这些来源，查完一起出结果。每个来源查到了、查了没有、没查、查询失败，会在报告顶部分开标出来。</p>
    <ul>${names.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
    <div class="bar"></div>
    <p class="small muted" style="margin:10px 0 0">已用 <span class="mono" id="elapsed">0</span> 秒。联网查证的公司大约要 5–10 秒。</p>
  </section>`;
  const t0 = Date.now();
  const tick = setInterval(() => { const el = $('#elapsed'); if (el) el.textContent = Math.round((Date.now() - t0) / 1000); }, 500);
  try {
    const c = await api('/api/cases', { method: 'POST', body });
    S.case = c; S.viewNo = c.current; S.selected.clear(); S.opCache = {};
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
  f.company.focus();
  toast(`已填入演示案例 ${d.id}，点"生成报告"`);
}

// ---------- 报告页 ----------

async function openCase(id, no) {
  if (!S.case || S.case.id !== id) {
    $('#view').innerHTML = '<div class="home"><p class="muted">读取案卷…</p></div>';
    try { S.case = await api(`/api/cases/${encodeURIComponent(id)}`); }
    catch (e) {
      $('#view').innerHTML = `<div class="home"><div class="card"><h2>打不开这个案卷</h2><p class="err">${esc(e.message)}</p><a class="btn sm" href="#/">回到首页</a></div></div>`;
      return;
    }
    S.selected.clear(); S.opCache = {};
  }
  S.viewNo = no && S.case.versions.some(v => v.no === no) ? no : S.case.current;
  renderCase();
}

function renderCase() {
  const c = S.case, v = ver(), cm = changeMap(v);
  const assistOpen = $('#assist') && $('#assist').classList.contains('open');
  renderTop();
  $('#view').innerHTML = `
  <div class="case-layout">
    <div class="report" id="report">
      ${caseHead(c, v)}
      ${coverageHtml(c, v)}
      ${v.no > 1 ? changesHtml(v) : ''}
      <nav class="layer-nav" aria-label="报告分层">
        ${v.no > 1 ? '<a href="#L0" data-act="jump"><i>Δ</i>变化清单</a>' : ''}
        <a href="#L1" data-act="jump"><i>1</i>一页结论</a><a href="#L2" data-act="jump"><i>2</i>四个信号</a>
        <a href="#L3" data-act="jump"><i>3</i>宣称 vs 记录</a><a href="#LQ" data-act="jump"><i>?</i>该问对方的</a><a href="#L4" data-act="jump"><i>4</i>原始数据</a>
      </nav>
      ${onepagerHtml(v)}
      ${signalsHtml(v, cm)}
      ${claimsHtml(v, cm)}
      ${questionsHtml(v)}
      ${rawsHtml(c, v)}
      <footer class="foot">结论来自公开记录和固定规则，AI 只负责读材料和说人话。这里不打安全分，也不给公司定性；"没查"不等于没问题，"查了没有"也只代表在那份数据里没有。</footer>
    </div>
    <aside class="assist${assistOpen ? ' open' : ''}" id="assist" aria-label="AI 助手">${assistHtml()}</aside>
  </div>
  <button type="button" class="fab" data-act="open-assist">问助手${S.selected.size ? `<em>${S.selected.size}</em>` : ''}</button>`;
  loadOnepager(v);
  scrollChat();
}

function caseHead(c, v) {
  const latest = v.no === c.current;
  const scen = S.scenarios.find(s => s.id === v.scenario);
  return `<header class="case-head">
    <div class="kicker">案卷 ${esc(c.id)} · 第 ${v.no} 版 · ${esc(v.trigger_label)} · ${esc(fmtTime(v.created_at))}</div>
    <h1>${esc(c.case.company_name)}</h1>
    ${v.need ? `<p class="need">${esc(v.need)}</p>` : ''}
    <div class="meta-line">
      <span><span class="lab">场景</span> <b>${esc(v.scenario_label)}</b></span>
      ${scen ? `<span><span class="lab">第一问</span> ${esc(scen.first_question)}</span>` : ''}
      ${v.for_whom ? `<span><span class="lab">替谁看</span> ${esc(v.for_whom)}</span>` : ''}
      ${v.amount ? `<span><span class="lab">金额</span> <span class="mono">${esc(fmtMoney(v.amount))}</span></span>` : ''}
      ${v.focus && v.focus.length ? `<span><span class="lab">最担心</span> ${v.focus.map(esc).join('；')}</span>` : ''}
    </div>
    <div class="vers" role="group" aria-label="版本">
      ${c.versions.map(x => `<button type="button" class="ver" data-act="ver" data-no="${x.no}" aria-current="${x.no === v.no}"><b>v${x.no}</b><small>${esc(x.trigger_label)}</small></button>`).join('')}
      <button type="button" class="btn sm" data-act="supplement">补充信息 · 生成第 ${c.versions.length + 1} 版</button>
    </div>
    ${latest ? '' : `<div class="old-banner">你在看第 ${v.no} 版（${esc(v.trigger_label)}），不是最新的。最新是第 ${c.current} 版。<button type="button" class="linkish" data-act="ver" data-no="${c.current}">回到最新</button></div>`}
    ${v.notes && v.notes.length ? `<div class="notes">${v.notes.map(n => `<div class="note-line${/演示|虚构/.test(n) ? ' demo' : ''}">${esc(n)}</div>`).join('')}</div>` : ''}
  </header>`;
}

function coverageHtml(c, v) {
  const raws = v.raw_ids.map(rawById).filter(Boolean);
  const n = k => raws.filter(r => r.coverage === k).length;
  return `<section class="coverage" aria-label="数据汇集结果">
    <div class="cov-head"><h2>这次汇集了 ${raws.length} 条原始数据</h2>
      <div class="cov-sum"><span>查到了 ${n('found')}</span><span>查了没有 ${n('not_found')}</span><span>没查 ${n('not_covered')}</span><span>查询失败 ${n('failed')}</span></div></div>
    <div class="cov-list">${raws.map(r => {
      const s = srcOf(r.source_id);
      return `<button type="button" class="cov ${esc(r.coverage)}" data-act="raw" data-ref="${esc(r.id)}" title="${esc(r.title)}"><i>${esc(r.id)}</i><span>${esc(s ? s.name : r.title)}</span><em>${COVERAGE[r.coverage] || ''}</em></button>`;
    }).join('')}</div>
  </section>`;
}

function changesHtml(v) {
  const changed = v.changes.filter(x => x.kind !== 'unchanged');
  const same = v.changes.filter(x => x.kind === 'unchanged');
  return `<section class="card changes" id="L0">
    <div class="kicker">变化清单 · 第 ${v.no} 版（${esc(v.trigger_label)}）和第 ${v.no - 1} 版比</div>
    <h2>${esc(v.change_summary || (changed.length ? `${changed.length} 项有变化` : '没有影响判断的变化'))}</h2>
    ${changed.length ? `<div class="chg-list">${changed.map(x => `<div class="chg ${x.kind}">
        <div class="chg-h"><span class="chg-k">${CHANGE[x.kind]}</span><button type="button" class="linkish" data-act="goto" data-id="${esc(x.target)}">${esc(x.label)}</button></div>
        <div class="ba">${x.before ? `<s>${esc(x.before)}</s> → ` : ''}<b>${esc(x.after || '这版没有了')}</b></div>
        ${x.after && x.plain.includes(x.after.slice(0, 12)) ? '' : `<p>${esc(x.plain)}</p>`}
        ${x.quote ? `<blockquote>${esc(x.quote)}</blockquote>` : ''}
        ${x.because.length ? `<div class="msg-meta">依据 ${x.because.map(r => `<button type="button" class="cite" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(x.quote ? [x.quote] : []))}">${esc(r)}</button>`).join('')}</div>` : ''}
      </div>`).join('')}</div>` : `<p class="small">${v.trigger === 'need' ? '公司的记录和它的说法都没变，每条判定也没变；变的是信号的排序、"第一问"和报告措辞。' : '新信息没有改变任何一条判断。'}</p>`}
    ${same.length ? `<details class="same"><summary>没变的 ${same.length} 项（展开看）</summary><ul>${same.map(x => `<li><button type="button" class="linkish" data-act="goto" data-id="${esc(x.target)}">${esc(x.label)}</button>：${esc(x.after || x.before || '')}</li>`).join('')}</ul></details>` : ''}
  </section>`;
}

// 第一层：一页结论
function onepagerHtml(v) {
  return `<section class="layer" id="L1">
    <div class="layer-head"><div><span class="kicker">第一层</span><h2>一页结论</h2></div>
      <div class="tools">
        <div class="seg" role="group" aria-label="给谁看"><button type="button" data-act="aud" data-aud="family" aria-pressed="${S.audience === 'family'}">给家人</button><button type="button" data-act="aud" data-aud="teller" aria-pressed="${S.audience === 'teller'}">给网点柜员</button></div>
        <button type="button" class="btn sm ghost" data-act="print">打印这一页</button>
      </div></div>
    <article class="onepager" id="onepager">${opBody(currentOp(v), v)}</article>
  </section>`;
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
  const col = (title, lines, cls, empty) => `<div class="op-col ${cls}"><h4>${title}</h4>${lines.length
    ? `<ul>${lines.map(l => `<li>${esc(l.text)}${refLinks(l.refs)}</li>`).join('')}</ul>` : `<p class="small muted">${empty}</p>`}</div>`;
  const noClaims = !v.assertions.length;
  return `<div class="op-head"><div><h3>${esc(op.title)}</h3><p>${esc(op.subject)}</p></div>
      <div class="stamp">X-Ray 案卷 ${esc(S.case.id)}<br>第 ${v.no} 版 · ${esc(fmtTime(v.created_at))}${isDemoCase() ? '<br><b class="demo-mark">演示数据 · 公司为虚构</b>' : ''}</div></div>
    <p class="headline">${esc(op.headline)}</p>
    <div class="op-cols">
      ${col('查到了什么', op.found, 'found', '还没查到具体记录。')}
      ${col('哪里对不上', op.mismatch, 'mismatch', noClaims ? '还没有它的说法可以对照。' : '它的说法和记录没有对不上的地方。')}
      ${col('还不知道什么', op.unknown, 'unknown', '没有列出来的未知项。')}
    </div>
    ${op.next_steps.length ? `<div class="op-next"><h4>在下一步之前，先确认这几件事</h4><ol>${op.next_steps.map(l => `<li>${esc(l.text)}${refLinks(l.refs)}</li>`).join('')}</ol></div>` : ''}
    <p class="op-foot">${esc(op.footer)}</p>`;
}

// 第二层：四个信号
function signalsHtml(v, cm) {
  return `<section class="layer" id="L2">
    <div class="layer-head"><div><span class="kicker">第二层</span><h2>四个信号</h2></div></div>
    <p class="layer-lede">排序跟着你的需求走。每一行右边是状态，下面是来源角标：来源类型、数据日期、原始数据编号，点开就是原始记录。</p>
    <div class="signals">${v.signals.map(sig => signalCard(sig, cm)).join('')}</div>
  </section>`;
}
function signalCard(sig, cm) {
  const rows = sig.items.map(it => {
    const id = `${sig.key}.${it.key}`;
    return `<div class="row${S.selected.has(id) ? ' is-sel' : ''}" data-item="${esc(id)}">
      <div class="k">${termify(it.label)}</div>
      <div class="v">${esc(it.value)}${it.detail ? `<small>${esc(it.detail)}</small>` : ''}<div class="meta">${srcTag(it.source, it.ref)}${chgTag(id, cm)}</div></div>
      <div class="s">${stBadge(it.status)}${selBtn(id)}</div>
    </div>`;
  }).join('');
  return `<section class="card sig" aria-labelledby="sig-${sig.key}">
    <div class="sig-head"><h3 id="sig-${sig.key}">${esc(sig.title)}<span>${SIGNAL_EN[sig.key] || ''}</span></h3>
      ${sig.flags ? `<span class="flags">${sig.flags} 项要看</span>` : '<span class="flags zero">没有标记</span>'}</div>
    <p class="sig-lede">${esc(sig.lede)}</p>
    ${rows}${sigExtra(sig)}
  </section>`;
}
function sigExtra(sig) {
  const x = sig.extra;
  if (!x) return '';
  let out = '';
  if (Array.isArray(x.months) && Array.isArray(x.counts) && x.counts.length) {
    const max = Math.max(1, ...x.counts), w = 300, h = 74, bw = w / x.counts.length;
    out += `<svg class="chart" viewBox="0 0 ${w} ${h + 14}" role="img" aria-label="近 12 个月投诉数">${x.counts.map((n, i) => {
      const bh = Math.round((n / max) * (h - 12));
      return `<rect x="${i * bw + 3}" y="${h - bh}" width="${bw - 6}" height="${bh}" fill="${i >= x.counts.length - 3 ? 'var(--red)' : 'var(--ink-2)'}" opacity=".85"/>`
        + `<text class="cv" x="${i * bw + bw / 2}" y="${h - bh - 2}" text-anchor="middle">${n}</text>`
        + `<text x="${i * bw + bw / 2}" y="${h + 11}" text-anchor="middle">${esc(String(x.months[i] || '').slice(5))}</text>`;
    }).join('')}</svg><div class="hint">红色是最近 3 个月。</div>`;
  }
  if (Array.isArray(x.web) && x.web.length) {
    out += `<details class="webhits"><summary>搜到的 ${x.web.length} 条公开报道和投诉</summary><ul>${x.web.map(hh => `<li>
      <span class="kind k-web">${esc(hh.category || '其他')}</span> <a href="${esc(hh.url)}" target="_blank" rel="noopener noreferrer">${esc(hh.title)}</a>
      <div class="wm">${esc(hh.site || '')}${hh.date ? ' · ' + esc(hh.date) : ''}${hh.ref ? ` · <button type="button" class="cite" data-act="raw" data-ref="${esc(hh.ref)}">${esc(hh.ref)}</button>` : ''}</div>
      ${hh.excerpt ? `<div class="small">${esc(hh.excerpt)}</div>` : ''}</li>`).join('')}</ul></details>`;
  }
  return out;
}

// 第三层：宣称 vs 记录
function claimsHtml(v, cm) {
  const t = v.tally || {};
  const body = v.assertions.length
    ? `<div class="tally"><span class="tr"><b>${t.red || 0}</b>处与记录不符或不合规</span><span class="ta"><b>${t.amber || 0}</b>处有误导或要留意</span><span class="tg"><b>${t.grey || 0}</b>处无法核验</span><span class="tgr"><b>${t.green || 0}</b>处与记录相符</span>${t.missing ? `<span class="ta"><b>${t.missing}</b>处该写没写</span>` : ''}</div>
       <div class="claims">${v.assertions.map(a => claimCard(a, cm)).join('')}</div>`
    : `<div class="empty"><p>还没有这家公司的说法。上传宣传材料、合同或聊天记录，就能逐条对照。</p><button type="button" class="btn sm" data-act="supplement" data-kind="material">补充材料</button></div>`;
  return `<section class="layer" id="L3">
    <div class="layer-head"><div><span class="kicker">第三层</span><h2>宣称 vs 记录</h2></div></div>
    <p class="layer-lede">对方的每条说法，都拿官方记录和法规对一遍。判定由固定规则给出，不由 AI 决定。</p>
    ${body}
    ${v.missing.length ? `<div class="missing"><h3>该写却没写</h3>${v.missing.map(m => `<div class="miss-item${S.selected.has(m.id) ? ' is-sel' : ''}" data-item="${esc(m.id)}">
        <div class="ctext"><span class="cid mono small muted">${esc(m.id)}</span><q>${esc(m.text)}</q>${chgTag(m.id, cm)}</div>
        <p>${esc(m.plain)}</p><div class="cfoot">${srcTag(m.source)}${m.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}">看材料 ${esc(r)}</button>`).join('')}${selBtn(m.id)}</div></div>`).join('')}</div>` : ''}
  </section>`;
}
function claimCard(a, cm) {
  return `<article class="claim ${esc(a.color)}${S.selected.has(a.id) ? ' is-sel' : ''}" data-item="${esc(a.id)}">
    <div class="cid">${esc(a.id)}</div>
    <div>
      <div class="ctext"><span class="ckind">${termify(a.kind_label)}</span><q>${esc(a.text)}</q><span class="badge ${esc(a.color)}">${esc(a.verdict_label)}</span>${chgTag(a.id, cm)}</div>
      <p class="plain">${esc(a.plain)}</p>
      <details${a.color === 'red' ? ' open' : ''}><summary>怎么查的 · ${a.checks.length} 项</summary><ul class="checks">${a.checks.map(ck => `<li>
        ${stBadge(ck.status)}<span class="cl">${termify(ck.label)}</span><span class="cr">${esc(ck.result)} ${srcTag(ck.source, ck.ref)}</span></li>`).join('')}</ul></details>
      <div class="cfoot">${a.refs.map(r => `<button type="button" class="linkish" data-act="raw" data-ref="${esc(r)}" data-hl="${esc(JSON.stringify(a.quotes))}">原文在 ${esc(r)}</button>`).join('')}${selBtn(a.id)}</div>
    </div>
  </article>`;
}

function questionsHtml(v) {
  return `<section class="layer" id="LQ">
    <div class="layer-head"><div><span class="kicker">下一步</span><h2>该问对方的问题</h2></div></div>
    ${v.questions.length ? `<ol class="qs">${v.questions.map(q => `<li data-item="${esc(q.id)}" class="${S.selected.has(q.id) ? 'is-sel' : ''}">
      <span class="qid">${esc(q.id)}</span>
      <div><div class="ask">${esc(q.ask)}</div><div class="why">${esc(q.why)} ${q.linked.map(goLink).join('')}</div><div class="where">${esc(q.check_where)}</div></div>
      ${selBtn(q.id)}</li>`).join('')}</ol>
      <p class="small muted">问到回复后，点上面的"补充信息"，选"对方的回复"贴进来，系统会重新判断。</p>`
      : '<p class="muted">暂时没有要追问的。</p>'}
  </section>`;
}

// 第四层：原始数据
function rawsHtml(c, v) {
  const raws = v.raw_ids.map(rawById).filter(Boolean);
  return `<section class="layer" id="L4">
    <div class="layer-head"><div><span class="kicker">第四层</span><h2>原始数据</h2></div></div>
    <p class="layer-lede">每次取数据都留一条原样的记录。报告里任何一条结论都能点进来；真实还是演示、哪天采的，都写在这里。</p>
    <div class="raws">${raws.map(r => {
      const s = srcOf(r.source_id);
      return `<div class="raw-row" data-item="${esc(r.id)}">
        <span class="rid">${esc(r.id)}</span>
        <div><div class="rt">${esc(r.title)}</div>
          <div class="rm"><span class="kind k-${esc(rawKind(r))}">${esc(KIND[rawKind(r)] || r.kind)}</span><span class="covl ${esc(r.coverage)}">${COVERAGE[r.coverage] || ''}</span>
            ${s ? `<span>${esc(s.name)}</span>` : ''}${r.as_of ? `<span>数据截至 ${esc(r.as_of)}</span>` : ''}<span>采集于 ${esc(fmtTime(r.retrieved_at))}</span></div>
          ${r.note ? `<div class="rn">${esc(r.note)}</div>` : ''}</div>
        <button type="button" class="btn sm ghost" data-act="raw" data-ref="${esc(r.id)}">查看</button>
      </div>`;
    }).join('')}</div>
  </section>`;
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
  const s = srcOf(r.source_id), back = backRefs(rid);
  const dlg = $('#rawDlg');
  dlg.innerHTML = `<div class="dlg-in">
    <div class="dlg-head"><div><div class="kicker">原始数据 ${esc(r.id)} · <span class="kind k-${esc(rawKind(r))}">${esc(KIND[rawKind(r)] || r.kind)}</span> · <span class="covl ${esc(r.coverage)}">${COVERAGE[r.coverage] || ''}</span></div>
      <h3 id="rawTitle">${esc(r.title)}</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭">×</button></div>
    <div class="dlg-body">
      <dl class="kv">
        <dt>来源</dt><dd>${esc(s ? s.name : r.source_id)}${s && s.note ? `<div class="small muted">${esc(s.note)}</div>` : ''}</dd>
        ${r.as_of ? `<dt>数据截至</dt><dd class="mono">${esc(r.as_of)}</dd>` : ''}
        <dt>采集时间</dt><dd class="mono">${esc(fmtTime(r.retrieved_at))}</dd>
        ${r.url ? `<dt>原文链接</dt><dd><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)}</a></dd>` : ''}
        ${r.screenshot ? `<dt>截图</dt><dd>${esc(r.screenshot)}</dd>` : ''}
      </dl>
      ${rawKind(r) === 'demo' ? '<div class="raw-note">演示数据：这家公司和这条记录都是编的，只用来演示。</div>' : ''}
      ${r.note ? `<div class="raw-note">${esc(r.note)}</div>` : ''}
      <div class="raw-content">${contentHtml(r.content, quotes)}</div>
      ${back.length ? `<div class="backrefs"><h4>报告里用到这条数据的地方</h4><div class="chips">${back.map(([id, label]) => `<button type="button" class="chip" data-act="goto" data-id="${esc(id)}">${esc(id)} · ${esc(label)}</button>`).join('')}</div></div>` : ''}
    </div></div>`;
  if (!dlg.open) dlg.showModal();
  const m = $('mark', dlg);
  if (m) m.scrollIntoView({ block: 'center' });
}
function showSource(el, id) {
  const s = srcOf(id);
  if (!s) return;
  popAt(el, `<h5>${esc(s.name)}</h5><p><span class="kind k-${esc(s.kind)}">${esc(KIND[s.kind] || s.kind)}</span>${s.as_of ? ` · ${esc(s.as_of)}` : ''}</p>${s.note ? `<p style="margin-top:6px">${esc(s.note)}</p>` : ''}${s.url ? `<p style="margin-top:6px"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">打开出处</a></p>` : ''}<p class="small" style="margin-top:6px;opacity:.75">这一条依据的是法规或参数，不是一次查询，所以没有原始数据编号。</p>`);
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
}
function refreshSel() {
  $$('.selbtn').forEach(b => {
    const on = S.selected.has(b.dataset.id);
    b.setAttribute('aria-pressed', on); b.textContent = on ? '已选中' : '选中提问';
  });
  $$('#report [data-item]').forEach(el => el.classList.toggle('is-sel', S.selected.has(el.dataset.item) && !el.classList.contains('raw-row')));
  const box = $('#asSel');
  if (box) box.innerHTML = selHtml();
  const fab = $('.fab');
  if (fab) fab.innerHTML = `问助手${S.selected.size ? `<em>${S.selected.size}</em>` : ''}`;
}
function gotoItem(id) {
  if (/^R\d+$/.test(id)) { openRaw(id); return; }
  if ($('#rawDlg').open) $('#rawDlg').close();
  if (window.matchMedia('(max-width:1280px)').matches) $('#assist') && $('#assist').classList.remove('open');
  const el = $(`#report [data-item="${CSS.escape(id)}"]`);
  if (!el) { toast(`这一版报告里没有 ${id}`); return; }
  const det = el.closest('details');
  if (det) det.open = true;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
}

// ---------- AI 助手 ----------

function modeLine() {
  const llm = S.health && S.health.llm;
  if (!llm) return '';
  if (!llm.configured || llm.mode === 'off') return '没接模型：用模板回答，只摘报告里的原话。';
  if (llm.mode === 'replay') return '离线回放：只用录好的模型回答。';
  return '只用这份案卷里的数据回答，每个关键事实标出处；没查到就直说。';
}
function assistHtml() {
  return `<div class="as-head"><div><div class="kicker">AI 助手</div><h3>只根据这份案卷回答</h3><p class="small muted">${esc(modeLine())}</p></div>
    <button type="button" class="as-x" data-act="close-assist" aria-label="关闭助手">×</button></div>
  <div class="as-body" id="asBody">${chatHtml()}</div>
  <div class="as-sel" id="asSel">${selHtml()}</div>
  <form class="as-input" id="asForm"><textarea class="box" name="q" rows="2" maxlength="2000" placeholder="问这份报告里的任何一条…（Enter 发送）" aria-label="提问"></textarea><button class="btn sm" type="submit">问</button></form>`;
}
function selHtml() {
  if (!S.selected.size) return '<span class="muted">在报告里点"选中提问"，可以针对某几条问。</span>';
  return `<span class="muted">针对：</span>${[...S.selected].map(id => `<span class="sel-chip">${esc(id)}<button type="button" data-act="unsel" data-id="${esc(id)}" aria-label="取消选中 ${esc(id)}">×</button></span>`).join('')}`;
}
function chatHtml() {
  const chat = S.case.chat;
  const sugg = ['它有没有资格收这笔钱？', '还有哪些没查到？', '我该先问对方什么？', '它被处罚或点名过吗？'];
  const intro = `<div class="as-intro"><p style="margin:0">可以这样问：</p><div class="chips" style="margin-top:6px">${sugg.map(q => `<button type="button" class="chip" data-act="ask" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <p class="small muted" style="margin-top:10px">助手不会改报告。你在对话里说的新情况，要点"加入案卷"，系统才会重新判断，并标出哪里变了。</p></div>`;
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
    <div class="msg-meta">${mode}${m.not_found ? '<span>数据里没有</span>' : ''}${m.dropped ? `<span>程序丢掉了 ${m.dropped} 条对不上的出处或引文</span>` : ''}${vNote}</div>
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
      <div class="sup-kinds seg" role="radiogroup" aria-label="补充什么">${Object.entries(SUP_KIND).map(([k, o]) => `<button type="button" data-act="sup-kind" data-kind="${k}" aria-pressed="${k === kind}">${o.label}</button>`).join('')}</div>
      <p class="sup-help" id="supHelp">${esc(SUP_KIND[kind].help)}</p>
      <div id="supMat"${kind === 'material' ? '' : ' hidden'}><div class="mat-tools"><span class="btn sm ghost file-btn">上传图片 / PDF / Word<input type="file" id="supFile" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp"></span><span class="read-note muted" id="supRead"></span></div></div>
      <div id="supScen"${kind === 'need' ? '' : ' hidden'}><div class="hint">场景（不选就从新需求里识别）</div><div class="chips" style="margin:4px 0 10px">${S.scenarios.map(s => `<button type="button" class="chip" data-act="sup-scen" data-id="${esc(s.id)}" aria-pressed="false">${esc(s.label)}</button>`).join('')}</div></div>
      <input class="inp" name="title" id="supTitleIn" placeholder="${kind === 'reply' ? '例如：业务员的微信回复' : '材料名称，例如：认购协议'}" value="${esc(opt.title || '')}" style="font-size:14px;margin-bottom:10px"${kind === 'need' ? ' hidden' : ''}>
      <textarea class="box" name="text" rows="8" required placeholder="${kind === 'need' ? '例如：我收到这家公司的 offer，让我去做理财顾问' : '把文字贴在这里'}">${esc(opt.text || '')}</textarea>
      ${demo && demo.supplements.length ? `<div class="sup-demo"><span class="muted">演示案例 ${esc(demo.id)} 准备好的补充：</span><div class="chips">${demo.supplements.map((s, i) => `<button type="button" class="chip" data-act="sup-fill" data-i="${i}">${esc(SUP_KIND[s.kind].label)}：${esc(s.title || s.text.slice(0, 18))}</button>`).join('')}</div></div>` : ''}
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
    S.case = c; S.opCache = {};
    dlg.close();
    const target = `#/case/${c.id}/v/${c.current}`;
    if (location.hash === target) { S.viewNo = c.current; renderCase(); } else location.hash = target;
    setTimeout(() => { const l0 = $('#L0'); if (l0) l0.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
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
  if (!pop.hidden && !e.target.closest('#pop') && !(el && ['term', 'src'].includes(el.dataset.act))) closePop();
  if (!el) {
    if (e.target.tagName === 'DIALOG') e.target.close(); // 点遮罩关闭
    return;
  }
  const d = el.dataset;
  switch (d.act) {
    case 'raw': openRaw(d.ref, d.hl ? JSON.parse(d.hl) : []); break;
    case 'goto': gotoItem(d.id); break;
    case 'sel': toggleSel(d.id); break;
    case 'unsel': S.selected.delete(d.id); refreshSel(); break;
    case 'ver': location.hash = `#/case/${S.case.id}/v/${d.no}`; break;
    case 'jump': e.preventDefault(); { const t = $(el.getAttribute('href')); if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' }); } break;
    case 'aud': S.audience = d.aud; $$('[data-act="aud"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.aud === d.aud));
      $('#onepager').innerHTML = opBody(currentOp(ver()), ver()); loadOnepager(ver()); break;
    case 'print': printOnepager(); break;
    case 'term': popAt(el, `<h5>${esc(d.term)}</h5><p>${esc(TERMS[d.term] || '')}</p>`); break;
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
    case 'scenario': { S.form.userScenario = S.form.userScenario === d.id ? null : d.id; $('#intake').innerHTML = intakeHtml(); } break;
  }
});
document.addEventListener('keydown', e => {
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
  const [health, scenarios, sources, demos] = await Promise.allSettled([
    api('/api/health'), api('/api/scenarios'), api('/api/sources'), api('/api/demo/cases')]);
  S.health = health.value || null;
  S.scenarios = scenarios.value || [];
  S.sources = sources.value || [];
  S.demos = demos.value || [];
  if (!S.health) toast('连不上后端：先启动 backend（uvicorn app.main:app --port 8000）', true);
  window.addEventListener('hashchange', route);
  route();
}
boot();
