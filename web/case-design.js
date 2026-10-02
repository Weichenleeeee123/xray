/* Local design review, 2026-10-02. Uses the existing case contract and actions.
 * ?classic=1 retains the original report. No generated scores or financial facts. */
const isDesignReview = () => !new URLSearchParams(location.search).has('classic');
const researchIcon = (kind = 'arrow') => {
  const paths = { arrow:'M7 17 17 7M7 7h10v10', print:'M7 9V3h10v6M7 17H4v-8h16v8h-3M7 14h10v7H7v-7Z', camera:'M8 6l2-3h4l2 3h4v14H4V6h4Zm8 7a4 4 0 1 0-8 0 4 4 0 0 0 8 0', scan:'M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5M7 12h10', spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z' };
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[kind] || paths.arrow}"/></svg>`;
};
function researchHeading(n, title, sub) { return `<div class="research-heading"><div><span class="research-eyebrow">${n}</span><h2>${title}</h2></div>${sub ? `<p>${sub}</p>` : ''}</div>`; }
function researchHero(c,v) {
  const steps=[['overview','企业概况','六维雷达','基本面 · 资金面 · 风险'],['signals','四个信号','风险 · 财务','信用 · 口碑'],['inquiry','问询与复核','拍照复核',`${(v.questions||[]).length} 个待询问题`],['details','详细信息','时间线 · 股东 · 资本','用户评价']];
  return `<header class="research-hero">
    <div class="research-topline"><a href="/" class="back-study">← 回到小企研究室</a><div class="research-actions"><button class="research-button ghost" data-act="print-open" aria-haspopup="dialog" aria-controls="printDlg">${researchIcon('print')}打印</button><button class="research-button ghost" data-act="supplement">＋ 补充信息</button><button class="research-button" data-act="section" data-section="photo">${researchIcon('camera')}拍照 · 二次查询</button></div></div>
    <div class="hero-title"><span class="research-eyebrow"><i></i> 小企查资料 / 企业研究档案</span><h1>${esc(c.case.company_name)}</h1><div class="hero-meta"><span>案卷 ${esc(c.id.slice(0,8).toUpperCase())}</span><span>${esc(v.created_at.slice(0,10))} 更新</span><span>第 ${v.no} 版</span><button data-act="tab" data-tab="raw">${v.raw_ids.length} 条来源记录 ${researchIcon()}</button></div></div>
    <nav class="research-flow" aria-label="报告章节导航"><svg class="flow-wire" viewBox="0 0 1200 110" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="flowGradient"><stop stop-color="#dfb477" stop-opacity="0"/><stop offset=".6" stop-color="#dfb477"/><stop offset="1" stop-color="#ddbf9a"/></linearGradient></defs><path class="wire-base" d="M0 26H270Q300 26 300 56Q300 86 330 86H640Q670 86 670 56Q670 26 700 26H920Q950 26 950 56Q950 86 980 86H1200"/><path class="wire-light" pathLength="100" d="M0 26H270Q300 26 300 56Q300 86 330 86H640Q670 86 670 56Q670 26 700 26H920Q950 26 950 56Q950 86 980 86H1200"/></svg>${steps.map(([id,label,desc,detail],i)=>`<button class="flow-stop ${i<2?'flow-primary':'flow-secondary'}" style="--order:${i}" data-act="section" data-section="${id}"><span class="flow-label"><b>0${i+1}</b>${label}<span>↗</span></span><span class="flow-preview"><strong>${id==='inquiry'?researchIcon('camera'):''}${desc}</strong><small>${detail}</small><span class="mini-trace"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span></span></button>`).join('')}</nav>
    <div class="hero-foot"><button data-act="motion" aria-pressed="false">暂停动效 Ⅱ</button><button data-act="section" data-section="overview">向下阅读 ↓</button></div>
  </header>`;
}
// Every signal item belongs to exactly one axis, so the radar never drops a backend record.
// Items not listed here fall back to their signal: risk → 经营资格, finance → 资金面, credit → 风险稳定性, reputation → 消息面.
const RADAR_AXES = [['qualify','经营资格'],['basics','基本面'],['funds','资金面'],['stability','风险稳定性'],['news','消息面'],['claims','宣传承诺']];
const RADAR_ITEM_AXIS = {
  'credit.status':'basics','credit.abnormal':'basics','finance.paid_capital':'basics','finance.insured':'basics','finance.jobs':'basics',
  'finance.amac_scale':'basics','risk.controller':'basics','risk.changes':'basics',
  'risk.promise':'claims','risk.benchmark':'claims','risk.disclosure':'claims','risk.pressure':'claims',
  'risk.payee':'claims','risk.refund':'claims','risk.upfront_fee':'claims'
};
const RADAR_SIGNAL_AXIS = {risk:'qualify',finance:'funds',credit:'stability',reputation:'news'};
// An axis takes the most severe status among the items actually checked; it is uncovered only when nothing was checked.
function researchRadarAxes(v) {
  const axes=Object.fromEntries(RADAR_AXES.map(([id,label])=>[id,{id,label,status:'none',checked:0,unchecked:0}]));
  for(const sig of v.signals || []) for(const it of sig.items || []){
    const axis=axes[RADAR_ITEM_AXIS[`${sig.key}.${it.key}`] || RADAR_SIGNAL_AXIS[sig.key]];
    if(!axis) continue;
    if(it.status==='none'){axis.unchecked++;continue;}
    axis.checked++;
    if(axis.status==='none' || (SEV[it.status]||0)>(SEV[axis.status]||0)) axis.status=it.status;
  }
  return RADAR_AXES.map(([id])=>axes[id]);
}
function researchRadar(v) {
  const dimensions = researchRadarAxes(v);
  const pt=(i,r)=>[230+Math.sin(i*Math.PI/3)*r,205-Math.cos(i*Math.PI/3)*r];
  const coords=p=>p.map(n=>n.toFixed(1)).join(',');
  const level={ok:115,warn:78,miss:62,bad:46};
  const dots=dimensions.map((d,i)=>d.status==='none'?null:pt(i,level[d.status]||46));
  const title = {ok:'未见异常',warn:'有待关注',bad:'有异常记录',miss:'缺应有记录',none:'未覆盖'};
  const count = d => d.status==='none' ? '这一维没有查到数据' : `查了 ${d.checked} 项${d.unchecked?`，另有 ${d.unchecked} 项没查`:''}`;
  return `<div class="research-radar"><div class="radar-caption"><span>企业六维轮廓</span><span>定性示意 · 不设评分</span></div><svg viewBox="0 0 460 410" role="img" aria-label="六维雷达：${dimensions.map(d=>`${d.label}${title[d.status]}（${count(d)}）`).join('，')}" >${[.25,.5,.75,1].map(f=>`<polygon points="${dimensions.map((_,i)=>coords(pt(i,132*f))).join(' ')}" fill="none" stroke="#b29a80" stroke-opacity=".17"/>`).join('')}${dimensions.map((d,i)=>`<line x1="230" y1="205" x2="${pt(i,132)[0]}" y2="${pt(i,132)[1]}" stroke="#b29a80" stroke-opacity=".22" ${d.status==='none'?'stroke-dasharray="3 6"':''}/>`).join('')}${dots.map((p,i)=>p?`<path d="M230 205L${coords(p)}${dots[(i+1)%6]?'L'+coords(dots[(i+1)%6]):''}Z" fill="#dfb477" fill-opacity=".12" stroke="#dfb477" stroke-width="1.6"/>`:'').join('')}${dimensions.map((d,i)=>{ const p=pt(i,175);return `<g data-axis="${d.id}" data-status="${d.status}"><title>${d.label}：${title[d.status]}，${count(d)}</title><text x="${p[0]}" y="${p[1]-3}" text-anchor="middle" fill="#f4e6d2" font-size="16">${d.label}</text><text x="${p[0]}" y="${p[1]+17}" text-anchor="middle" fill="${d.status==='none'?'#ac9781':d.status==='bad'?'#ed9b89':'#d4b38b'}" font-size="12">${title[d.status]}</text>${dots[i]?`<circle cx="${dots[i][0]}" cy="${dots[i][1]}" r="4" fill="#f1cd91"/>`:''}</g>`;}).join('')}</svg><p>依据现有记录作定性展示：越靠外越没发现问题，越靠里问题越多。虚线为未覆盖维度，不代表能力低；不用于比较投资表现。</p></div>`;
}
function researchOverview(v) {
  const html=document.createElement('div'); html.innerHTML=glanceHtml(v);
  const first=html.querySelector('.gl-first')?.outerHTML || '<p>现有记录尚不足以形成结论。</p>';
  html.querySelectorAll('[data-act="sigtile"]').forEach(el=>{el.setAttribute('aria-haspopup','dialog');el.setAttribute('aria-controls','signalDlg');});
  const tiles=html.querySelector('.tiles')?.innerHTML || '';
  return `<section id="research-overview" class="research-section">${researchHeading('01','企业概况','')}<div class="overview-grid">${researchRadar(v)}<div class="overview-summary"><span class="research-eyebrow">初步结论</span>${first}<div class="overview-note"><span>查询需求</span><p>${esc(v.need || v.scenario_label)}</p></div><button class="research-text-link" data-act="tab" data-tab="raw">查看资料来源 ${researchIcon()}</button></div></div></section>
    <section id="research-signals" class="research-section">${researchHeading('02','四个信号','')}<div class="research-signals">${tiles}</div></section>`;
}

// Preserve every signal item; only long, repetitive record lists have a disclosure.
function researchDetailParts(detail) {
  const text=String(detail || '').trim();
  const start=text.match(/(^|[。；;\n]\s*)(?=\d{4}-\d{2}-\d{2}[，,\s]|日期未公示)/);
  const dated=start?start.index+start[1].length:-1;
  if(dated>=0){
    const intro=text.slice(0,dated).trim();
    const records=text.slice(dated).split(/[；;]\s*|\n+/).map(s=>s.trim()).filter(Boolean);
    return {intro,records};
  }
  const rows=text.split(/\n+/).map(s=>s.trim()).filter(Boolean);
  if(rows.length>1) return {intro:'',records:rows};
  return {intro:text,records:[]};
}
function researchRecordRow(text,seen) {
  const match=text.match(/^(\d{4}-\d{2}-\d{2}|日期未公示)[，,：:]?\s*/);
  return `<li>${match?`<span class="signal-record-date">${esc(match[1])}</span>`:''}<span>${termText(match?text.slice(match[0].length):text,seen)}</span></li>`;
}
function researchItemDetail(detail,seen) {
  const {intro,records}=researchDetailParts(detail);
  return `${intro?`<p class="signal-explanation">${termText(intro,seen)}</p>`:''}${records.length?`<div class="signal-records"><span class="signal-records-label">记录明细 · ${records.length} 条</span><ul>${records.slice(0,3).map(t=>researchRecordRow(t,seen)).join('')}</ul>${records.length>3?`<details class="signal-records-more"><summary><span class="when-closed">展开其余 ${records.length-3} 条记录</span><span class="when-open">收起其余记录</span><span aria-hidden="true">＋</span></summary><ul>${records.slice(3).map(t=>researchRecordRow(t,seen)).join('')}</ul></details>`:''}</div>`:''}`;
}
function researchItemValue(value,seen) {
  const parts=String(value || '').split('、');
  const metrics=parts.map(t=>t.match(/^(.+?)\s+(\d+(?:\.\d+)?(?:\s*[%％笔条项万元亿]*)?)$/));
  if(parts.length>=3 && metrics.every(Boolean)) return `<dl class="signal-metrics">${metrics.map(m=>`<div><dt>${termText(m[1],seen)}</dt><dd>${esc(m[2])}</dd></div>`).join('')}</dl>`;
  return `<div class="signal-value${String(value).length>32?' signal-value-long':''}">${termText(value,seen)}</div>`;
}
function researchSignalCard(sig,cm,v) {
  const items=[...sig.items].sort((a,b)=>(SEV[b.status]||0)-(SEV[a.status]||0));
  const flagged=items.filter(it=>FLAG.has(it.status)).length;
  return `<section class="sig research-signal-content" aria-labelledby="sig-${sig.key}"><header><h3 id="sig-${sig.key}">${esc(sig.title)}</h3><span class="signal-total">${items.length} 项记录${flagged?`<b>${flagged} 项要看</b>`:''}</span></header><p class="sig-lede">${esc(sig.lede)}</p><div class="signal-items">${items.map(it=>{
    const id=`${sig.key}.${it.key}`,seen=new Set();
    return `<article class="signal-item s-${esc(it.status)}${selCls(id)}" data-item="${esc(id)}"><div class="signal-item-head"><h4>${termText(it.label,seen)}</h4><span class="signal-status">${stLabel(it)}</span>${chgTag(id,cm)}${askBtn(id)}</div>${researchItemValue(it.value,seen)}${researchItemDetail(it.detail,seen)}<div class="signal-source">${srcLink(it.source,it.ref)}</div></article>`;
  }).join('')}</div>${sigExtra(sig,v)}</section>`;
}
function renderResearchSignal(key) {
  const v=ver(), sig=v.signals.find(s=>s.key===key), dlg=$('#signalDlg');
  if(!sig || !dlg) return false;
  const pop=$('#pop');
  if(dlg.contains(pop)){closePop();document.body.append(pop);}
  dlg.dataset.key=key;
  dlg.setAttribute('aria-labelledby',`sig-${key}`);
  dlg.innerHTML=`<div class="dlg-in"><div class="dlg-head"><span class="research-eyebrow">信号详情</span><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭信号详情" autofocus>×</button></div><div class="dlg-body" tabindex="0" aria-label="可滚动的信号记录">${researchSignalCard(sig,changeMap(v),v)}${key==='reputation'?(v.charts||[]).filter(c=>c.id==='complaints').map(c=>chartCard(c,v)).join(''):''}</div></div>`;
  return true;
}
function openResearchSignal(key, itemId) {
  const dlg=$('#signalDlg');
  if(!renderResearchSignal(key)) return;
  if(!dlg.open) dlg.showModal();
  if(itemId){
    const item=dlg.querySelector(`[data-item="${CSS.escape(itemId)}"]`);
    item?.scrollIntoView({block:'center'});
    item?.classList.add('flash');
  } else $('.dlg-body',dlg).scrollTop=0;
}
document.querySelector('#signalDlg')?.addEventListener('close',()=>{
  const dlg=$('#signalDlg'), pop=$('#pop');
  if(dlg.contains(pop)){closePop();document.body.append(pop);}
  dlg.innerHTML='';
});
function researchShortQuestion(q) {
  const text=q.ask.replace(/（[^）]*）|\([^)]*\)/g,'').trim();
  if(/政府网站.*点名.*处理完/.test(text)) return '监管点名的事项，处理完了吗？';
  if(/全称.*统一社会信用代码/.test(text)) return '公司全称和信用代码是什么？';
  if(/钱或资料交给谁/.test(text)) return '钱和资料交给谁？';
  if(/出了问题找谁.*合同/.test(text)) return '出了问题找谁，合同写了吗？';
  return text.length>25 ? text.slice(0,24)+'…' : text.replace(/[？?]?$/,'？');
}
function researchQuestions(v) {
  const questions=v.questions || [];
  return `<div id="research-questions" class="question-cloud${questions.length>5?' question-cloud-many':''}"><span class="column-label">该问对方的 <span>${questions.length} 个问题</span></span>${questions.map((q,i)=>`<button type="button" class="question-float" style="--order:${i};--tilt:${i%2?1:-1}deg" data-act="question-detail" data-question="${i}" aria-haspopup="dialog" aria-controls="questionDlg"><span class="question-no">${String(i+1).padStart(2,'0')}</span><strong>${esc(researchShortQuestion(q))}</strong><span class="question-open" aria-hidden="true">↗</span></button>`).join('') || '<p class="research-empty">暂无需要追问的问题。</p>'}</div>`;
}
function openResearchQuestion(index) {
  const q=ver().questions[index], dlg=$('#questionDlg');
  if(!q || !dlg) return;
  dlg.innerHTML=`<div class="dlg-in"><div class="dlg-head"><span class="research-eyebrow">该问对方的 · ${String(index+1).padStart(2,'0')}</span><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭问题详情" autofocus>×</button></div><div class="dlg-body"><h3 id="research-question-title">${esc(q.ask)}</h3><div class="question-detail-grid"><div><span class="column-label">为什么要问</span><p>${esc(q.why)}</p>${q.linked.length?`<button class="research-text-link" data-act="goto" data-id="${esc(q.linked[0])}">查看相关线索 →</button>`:''}</div><div><span class="column-label">如何核对</span><p>${esc(q.check_where)}</p></div></div><div class="question-detail-actions"><button class="research-button ghost" data-act="copy-question" data-question="${index}">复制问题 ${researchIcon()}</button><button class="research-button" data-act="supplement" data-kind="reply" data-title="对 ${esc(q.id)} 的回复">填写回复 →</button></div></div></div>`;
  if(!dlg.open) dlg.showModal();
}
// The printable one-pager reuses the classic audience switch and /onepager endpoint.
function openResearchPrint() {
  const v=ver(), dlg=$('#printDlg');
  if(!v || !dlg) return;
  dlg.innerHTML=`<div class="dlg-in"><div class="dlg-head"><div><span class="research-eyebrow">一页结论 · 第 ${v.no} 版</span><h3 id="printTitle">打印一页结论</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="关闭打印预览" autofocus>×</button></div><div class="dlg-body"><div class="op-tools"><div class="seg" role="group" aria-label="给谁看"><button type="button" data-act="aud" data-aud="family" aria-pressed="${S.audience==='family'}">给家人</button><button type="button" data-act="aud" data-aud="teller" aria-pressed="${S.audience==='teller'}">给网点柜员</button></div></div><article class="onepager" id="onepager">${opBody(currentOp(v),v)}</article></div><div class="dlg-foot"><button type="button" class="btn ghost sm" data-act="close-dlg">取消</button><button type="button" class="btn sm" data-act="print">打印</button></div></div>`;
  if(!dlg.open) dlg.showModal();
  loadOnepager(v);
}
document.querySelector('#printDlg')?.addEventListener('close',()=>{ $('#printDlg').innerHTML=''; });
function researchCapital(v) {
  const charts=(v.charts||[]).filter(c=>c.id==='capital');
  return `<div class="research-data-charts">${charts.map(c=>chartCard(c,v)).join('') || '<p class="research-empty">这份案卷尚无资本数据。</p>'}</div>`;
}
function researchShareholders(v) {
  const charts=(v.charts||[]).filter(c=>c.kind==='share');
  return `<div class="research-data-charts">${charts.map(researchHolders).join('') || '<p class="research-empty">这份案卷尚无股东数据。</p>'}</div>`;
}
function researchHolders(c) {
  const total=c.points.reduce((n,p)=>n+(p.value||0),0);
  return `<figure class="vcard research-holders"><figcaption><b>股东结构</b><span>已列出 ${c.points.length} 位股东</span></figcaption><div class="holder-bar" aria-label="已列股东合计 ${total.toFixed(2)}%">${c.points.map((p,i)=>`<button style="width:${Math.max(0,p.value||0)}%;--holder-hue:${22+i*2.3}" data-act="raw" data-ref="${esc(p.ref)}" title="${esc(p.label)} ${esc(p.display)}" aria-label="${esc(p.label)} ${esc(p.display)}"></button>`).join('')}<span style="flex:1" title="未在此列出的部分"></span></div><div class="holder-key">已列股东 ${total.toFixed(2)}% <span>其余部分未在此列出</span></div><div class="holder-list">${c.points.map((p,i)=>`<button data-act="raw" data-ref="${esc(p.ref)}"><span class="holder-no">${String(i+1).padStart(2,'0')}</span><span>${esc(p.label)}</span><b>${esc(p.display)}</b><em>↗</em></button>`).join('')}</div><button class="research-text-link" data-act="goto" data-id="${esc(c.item)}">查看股权出质记录与原文 →</button></figure>`;
}
function researchTimeline(v) {
  const c=(v.charts||[]).find(c=>c.kind==='timeline');const events=c?.events||[];
  return `<section id="research-timeline"><p class="research-fine">悬停或点击节点查看记录</p><div class="timeline-toolbar"><span>${events.length?esc(events[0].date.slice(0,4)):'—'} — ${esc(v.created_at.slice(0,4))}</span><small>按事件顺序排列 · 非等距时间刻度</small></div><div class="research-timeline" role="group" aria-label="公司事件时间线">${events.map((e,i)=>`<button class="research-event ${e.tone}${i===0?' active':''}" data-act="timeline-event" data-event="${i}" aria-pressed="${i===0}"><span class="event-year">${esc(e.date.slice(0,4))}</span><span class="event-stem"></span><svg class="event-wave" viewBox="0 0 96 24" preserveAspectRatio="none" aria-hidden="true"><path d="M0 20 C25 20 28 2 48 2 C68 2 71 20 96 20"/></svg><span class="event-dot"></span><span class="event-date">${esc(e.date.slice(5))}</span><span class="event-short">${esc(e.label.split('：')[0])}</span></button>`).join('')}</div><div id="research-event-detail" class="event-detail" aria-live="polite">${events.length?researchEventDetail(events[0]):'暂无有日期的事件记录。'}</div><p class="research-fine">${esc(c?.note||'只显示已查到的事件。')}</p></section>`;
}
function researchEventDetail(e) { return `<time>${esc(e.date)}</time><p>${esc(e.label)}</p>${e.ref?`<button class="research-text-link" data-act="raw" data-ref="${esc(e.ref)}">查看出处 ${researchIcon()}</button>`:''}`; }
function researchPhoto(v) {
  return `<div id="research-photo" class="photo-focus"><button type="button" class="photo-launch" data-act="contract" aria-label="拍照或选择照片复核"><svg class="camera-illustration" viewBox="0 0 240 190" fill="none" aria-hidden="true"><rect class="camera-paper" x="144" y="14" width="65" height="98" rx="8" transform="rotate(12 144 14)"/><path class="camera-paper-line" d="m155 38 31 7m-34 8 24 5m-28 10 29 6"/><path class="camera-body" d="M40 65h39l12-20h47l12 20h46a16 16 0 0 1 16 16v73a16 16 0 0 1-16 16H40a16 16 0 0 1-16-16V81a16 16 0 0 1 16-16Z"/><circle class="camera-lens-outer" cx="118" cy="115" r="35"/><circle class="camera-lens-inner" cx="118" cy="115" r="23"/><path class="camera-reflection" d="M103 111a16 16 0 0 1 13-12"/><rect class="camera-flash" x="173" y="82" width="19" height="8" rx="3"/><path class="camera-scan" d="M41 115h154"/></svg><span class="photo-launch-label">拍照复核 <span>↗</span></span></button><p>合同、宣传页、聊天记录</p><button class="research-text-link" data-act="supplement">或补充文字、PDF、Word →</button></div>`;
}
const researchTabs = {
  details: [['timeline','时间线'],['holders','股东'],['capital','资本'],['reviews','用户评价']]
};
const researchActiveTab = {details:'timeline'};
function researchTabBar(group) {
  return `<nav class="research-tabs" role="tablist" aria-label="${group==='details'?'详细信息分类':'问询与复核分类'}">${researchTabs[group].map(([key,label])=>`<button type="button" id="research-${group}-tab-${key}" role="tab" aria-controls="research-${group}-panel-${key}" aria-selected="${researchActiveTab[group]===key}" tabindex="${researchActiveTab[group]===key?0:-1}" data-act="research-tab" data-group="${group}" data-key="${key}">${label}</button>`).join('')}</nav>`;
}
function researchTabPanel(group,key,content) {
  return `<div class="research-tab-panel" id="research-${group}-panel-${key}" role="tabpanel" aria-labelledby="research-${group}-tab-${key}" tabindex="0"${researchActiveTab[group]===key?'':' hidden'}>${content}</div>`;
}
function researchNotes(c,v) {
  return `<details class="research-notes"><summary>版本与阅读说明</summary><div class="research-versions">${c.versions.map(x=>`<button class="research-button ghost" data-act="ver" data-no="${x.no}" aria-current="${x.no===v.no}">第 ${x.no} 版 · ${esc(x.trigger_label)}</button>`).join('')}</div><ul>${(v.notes||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details>`;
}
function researchReviews(v) {
  return `<div class="research-reviews" id="research-reviews-body">${reviewsPanel(v)}</div>`;
}
function researchVerification(v) {
  const extraCharts=(v.charts||[]).filter(c=>!['capital','complaints'].includes(c.id) && !['share','timeline'].includes(c.kind));
  const claims=v.assertions.length || v.missing.length;
  return `${claims || extraCharts.length ? `<div class="research-verification" id="research-claims"><h3>材料核对结果</h3>${extraCharts.length?`<div class="research-data-charts">${extraCharts.map(c=>chartCard(c,v)).join('')}</div>`:''}${claims?claimsPanel(v,changeMap(v)):''}</div>`:''}${SHOW_JUDGMENTS && v.judgments?.length?`<details class="research-notes" id="research-judgments"><summary>核实记录</summary>${judgmentsPanel(v)}</details>`:''}${v.no>1?`<details class="research-notes" id="research-changes"><summary>第 ${v.no} 版变化</summary>${changesPanel(v)}</details>`:''}`;
}
function researchSources(v) {
  const groups=new Map();
  for(const record of versionRaws(v)){
    const source=srcOf(record.source_id) || {name:record.source_id,kind:record.kind};
    const key=[source.name,source.kind,source.url || ''].join('|');
    if(!groups.has(key)) groups.set(key,{source,records:[]});
    groups.get(key).records.push(record);
  }
  const entries=[...groups.values()].map(({source,records})=>`<details class="source-entry"><summary><span class="source-kind">${esc(KIND[source.kind] || source.kind)}</span><span class="source-name">${esc(source.name)}</span><span class="source-count">${records.length} 条记录</span><span class="source-expand" aria-hidden="true">＋</span></summary><div class="source-entry-body">${source.note?`<p>${esc(source.note)}</p>`:''}<div class="source-meta">${source.as_of?`<span>数据截至 ${esc(source.as_of)}</span>`:''}${/^https?:\/\//i.test(source.url || '')?`<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">来源网站 ↗</a>`:''}</div><ul>${records.map(r=>`<li><button type="button" data-act="raw" data-ref="${esc(r.id)}"><span>${esc(r.title)}</span><small>${esc(COVERAGE[r.coverage] || r.coverage)}</small><span aria-hidden="true">↗</span></button></li>`).join('')}</ul></div></details>`);
  return `<section id="research-sources" class="research-section research-sources"><details class="source-collection"><summary><h2>资料来源</h2><span class="source-total">${groups.size} 项来源 · ${versionRaws(v).length} 条记录</span><span class="source-toggle-hint"><span class="source-open-label">点击展开</span><span class="source-close-label">收起</span><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 8 5 5 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></summary><div class="source-directory">${entries.join('') || '<p class="research-empty">暂无来源记录。</p>'}</div></details></section>`;
}
function researchReport(c,v) {
  return `${researchHero(c,v)}${v.no !== c.current ? `<div class="old-banner">正在查看第 ${v.no} 版。<button data-act="ver" data-no="${c.current}" class="research-text-link">回到最新第 ${c.current} 版 →</button></div>` : ''}${researchOverview(v)}
    <section id="research-inquiry" class="research-section research-inquiry">${researchHeading('03','问询与复核','')}<div class="inquiry-stage">${researchPhoto(v)}${researchQuestions(v)}</div>${researchVerification(v)}</section>
    <section id="research-details" class="research-section research-detail-group">${researchHeading('04','详细信息','')}${researchTabBar('details')}${researchTabPanel('details','timeline',researchTimeline(v))}${researchTabPanel('details','holders',researchShareholders(v))}${researchTabPanel('details','capital',researchCapital(v))}${researchTabPanel('details','reviews',researchReviews(v))}</section>
    ${researchSources(v)}${researchNotes(c,v)}`;
}

function activateResearchTab(group,key,focus=false) {
  if(!researchTabs[group]?.some(t=>t[0]===key)) return;
  closePop();
  researchActiveTab[group]=key;
  researchTabs[group].forEach(([id])=>{
    const button=$(`#research-${group}-tab-${id}`), panel=$(`#research-${group}-panel-${id}`);
    if(!button || !panel) return;
    const selected=id===key;
    button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;panel.hidden=!selected;
  });
  if(focus) $(`#research-${group}-tab-${key}`)?.focus({preventScroll:true});
}
function researchNavigate(key,scroll=true) {
  let target;
  if(key==='raw') key='sources';
  if(researchTabs.details.some(t=>t[0]===key)){activateResearchTab('details',key);target=$('#research-details');}
  else if(['questions','photo','claims','changes','judgments'].includes(key)){
    target=$(`#research-${key}`) || $('#research-inquiry');
    if(target.tagName==='DETAILS') target.open=true;
    if(key==='questions' || key==='photo') target=$('#research-inquiry');
  } else target=$(`#research-${key}`);
  if(key==='sources'){const list=$('.source-collection',target||document);if(list)list.open=true;}
  if(scroll) target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
}

function researchDisclaimer() {
  return `<footer class="foot research-disclaimer" aria-labelledby="research-disclaimer-title"><h2 id="research-disclaimer-title">免责声明</h2><p>本页面用于资料汇总与辅助核验，仅供参考，不构成投资、交易或法律建议，也不对企业的信用、安全性、收益或履约能力作出保证。</p><p>公开资料、第三方数据及 AI 辅助整理可能存在更新延迟、遗漏或错误，请以主管部门公示及来源原文为准。“未查到”或“未覆盖”不代表不存在相关风险；作出决定前，请结合最新资料独立核实。</p></footer>`;
}

function researchFlowPulse(progress, entry, exit) {
  const ease=t=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
  // Start at first contact, ease in for ~300 ms, then follow the trailing light out.
  return ease((progress-entry)/3.2)*(1-ease((progress-exit)/12));
}
// A single clock drives both the travelling light and each node's response.
// Measure the actual labels so the light still meets them after a resize.
function initResearchFlow() {
  const flow=$('.research-flow'), svg=$('.flow-wire'), light=$('.wire-light');
  if(!flow || !svg || !light) return () => {};
  const base=$('.wire-base',svg), gradient=$('#flowGradient',svg);
  const stops=$$('.flow-stop',flow), labels=stops.map(s=>$('.flow-label',s));
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let positions=[],length=0,frame=0,elapsed=0,last=0,visible=true,disposed=false;
  function measure() {
    const bounds=flow.getBoundingClientRect(), width=flow.clientWidth;
    const points=stops.map((stop,i)=>{
      const rect=stop.getBoundingClientRect();
      return {x:rect.left-bounds.left+labels[i].offsetWidth/2,y:rect.top-bounds.top+labels[i].offsetHeight/2,half:labels[i].offsetWidth/2};
    });
    if(!width || !points.length) return;
    svg.setAttribute('viewBox',`0 0 ${width} 160`);
    let path=`M-20 ${points[0].y}H${points[0].x}`;
    for(let i=1;i<points.length;i++){
      const a=points[i-1],b=points[i],mid=(a.x+a.half+b.x-b.half)/2;
      const direction=Math.sign(b.y-a.y),radius=Math.min(22,Math.abs(b.y-a.y)/2,Math.max(0,(b.x-b.half-a.x-a.half)/3));
      path+=`H${mid-radius}Q${mid} ${a.y} ${mid} ${a.y+direction*radius}V${b.y-direction*radius}Q${mid} ${b.y} ${mid+radius} ${b.y}H${b.x}`;
    }
    path+=`H${width+20}`;
    base.setAttribute('d',path);light.setAttribute('d',path);
    length=light.getTotalLength();
    const progressAtX=x=>{
      let lo=0,hi=length;
      for(let i=0;i<20;i++){const mid=(lo+hi)/2;if(light.getPointAtLength(mid).x<x)lo=mid;else hi=mid;}
      return (lo+hi)/2/length*100;
    };
    // Include the 7 px outline that masks the wire around each label.
    positions=points.map(point=>({entry:progressAtX(point.x-point.half-7),exit:progressAtX(point.x+point.half+7)}));
    gradient.setAttribute('gradientUnits','userSpaceOnUse');
  }
  function draw() {
    const progress=(elapsed%11000)/11000*116;
    light.style.strokeDashoffset=String(12-progress);
    const head=light.getPointAtLength(Math.min(length,length*progress/100));
    const tail=light.getPointAtLength(Math.max(0,length*(progress-12)/100));
    gradient.setAttribute('x1',String(tail.x));gradient.setAttribute('x2',String(Math.max(tail.x+1,head.x)));
    stops.forEach((stop,i)=>{
      const {entry,exit}=positions[i];
      stop.style.setProperty('--pass',String(researchFlowPulse(progress,entry,exit)));
    });
  }
  function tick(now) {
    frame=0;
    if(disposed) return;
    const paused=document.body.classList.contains('motion-paused');
    if(!reduced.matches && !document.hidden && visible && !paused) elapsed+=last?Math.min(now-last,64):0;
    last=now;
    if(length && !reduced.matches) draw();
    if(!reduced.matches && visible && !document.hidden) frame=requestAnimationFrame(tick);
  }
  function resume() {
    if(reduced.matches){cancelAnimationFrame(frame);frame=0;stops.forEach(s=>s.style.setProperty('--pass','0'));return;}
    if(!frame && visible && !document.hidden){last=0;frame=requestAnimationFrame(tick);}
  }
  const resize=new ResizeObserver(()=>{measure();resume();});resize.observe(flow);labels.forEach(el=>resize.observe(el));
  const intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;resume();});intersection.observe(flow);
  reduced.addEventListener('change',resume);document.addEventListener('visibilitychange',resume);
  measure();resume();
  return ()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();intersection.disconnect();reduced.removeEventListener('change',resume);document.removeEventListener('visibilitychange',resume);};
}
let researchCleanup = () => {};
function initResearchDesign() {
  researchCleanup();
  if($('#signalDlg')?.open) $('#signalDlg').close();
  if($('#questionDlg')?.open) $('#questionDlg').close();
  if($('#printDlg')?.open) $('#printDlg').close();
  document.body.classList.toggle('research-mode',isDesignReview());
  if(!isDesignReview()) return;
  const sections=$$('.research-section');
  const observer=new IntersectionObserver(entries=>entries.forEach(e=>e.target.classList.toggle('in-view',e.isIntersecting)),{threshold:.06});
  sections.forEach(el=>observer.observe(el));
  const timeline=$('.research-timeline');
  const activate=el=>{ if(!el)return;const idx=Number(el.dataset.event);const event=ver().charts.find(c=>c.kind==='timeline')?.events[idx];if(!event)return; $$('.research-event').forEach(b=>{b.classList.toggle('active',b===el);b.setAttribute('aria-pressed',b===el);});$('#research-event-detail').innerHTML=researchEventDetail(event);};
  timeline?.addEventListener('pointerover',e=>activate(e.target.closest('.research-event')));
  timeline?.addEventListener('focusin',e=>activate(e.target.closest('.research-event')));
  const cleanupFlow=initResearchFlow();
  const motion=$('[data-act="motion"]'), paused=document.body.classList.contains('motion-paused');
  if(motion){motion.setAttribute('aria-pressed',String(paused));motion.textContent=paused?'播放动效 ▷':'暂停动效 Ⅱ';}
  researchCleanup=()=>{observer.disconnect();cleanupFlow();};
}
document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-act]');if(!el)return;
  if(el.dataset.act==='section') researchNavigate(el.dataset.section);
  if(el.dataset.act==='question-detail') openResearchQuestion(Number(el.dataset.question));
  if(el.dataset.act==='print-open') openResearchPrint();
  if(el.dataset.act==='research-tab') activateResearchTab(el.dataset.group,el.dataset.key);
  if(el.dataset.act==='motion'){const paused=document.body.classList.toggle('motion-paused');el.setAttribute('aria-pressed',paused);el.textContent=paused?'播放动效 ▷':'暂停动效 Ⅱ';}
  if(el.dataset.act==='timeline-event') { const event=ver().charts.find(c=>c.kind==='timeline')?.events[Number(el.dataset.event)];if(event){ $$('.research-event').forEach(b=>{const active=b===el;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}); $('#research-event-detail').innerHTML=researchEventDetail(event); } }
  if(el.dataset.act==='copy-question'){const q=ver().questions[Number(el.dataset.question)];try{await navigator.clipboard.writeText(q.ask);const label=el.innerHTML;el.textContent='已复制';setTimeout(()=>{if(el.isConnected)el.innerHTML=label;},1800);toast('问题已复制');}catch{toast('复制未成功，请选中问题文字复制');}}
});

document.addEventListener('keydown',e=>{
  const tab=e.target.closest('[data-act="research-tab"]');
  if(!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
  e.preventDefault();
  const keys=researchTabs[tab.dataset.group].map(t=>t[0]), current=keys.indexOf(tab.dataset.key);
  const next=e.key==='Home'?0:e.key==='End'?keys.length-1:(current+(e.key==='ArrowRight'?1:-1)+keys.length)%keys.length;
  activateResearchTab(tab.dataset.group,keys[next],true);
});
