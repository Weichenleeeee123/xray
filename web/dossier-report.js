/* Approved dossier reading layer. All facts and actions use the live case contract. */
'use strict';
const dossierIcon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const dossierGoose = () => '<span class="qi-sprite" role="img" aria-label="小企"></span>';
const dossierHeading = (n, title, note = '') => `<div class="section-heading"><div><span>${n}</span><h2>${title}</h2></div><span class="section-note">${note}</span></div>`;

function dossierFindings(v) {
  const items = glanceItems(v);
  const scenario = S.scenarios.find(s => s.id === v.scenario);
  const selected = v.glance?.first?.length ? v.glance.first : scenario?.first_items || [];
  const ids = selected.length ? selected : Object.keys(items);
  return [...new Set(ids)].filter(id => items[id] && id !== 'reputation.user_reviews')
    .map(id => ({id, ...items[id]})).filter(item => item.status !== 'none' || isOpen(item));
}
function dossierGroups(v) {
  const items = dossierFindings(v);
  return {problem: items.filter(i => FLAG.has(i.status)), clear: items.filter(i => i.status === 'ok'), open: items.filter(isOpen)};
}
function dossierHero(c, v) {
  const demo = (c.raw || []).some(r => v.raw_ids.includes(r.id) && r.kind === 'demo' && r.coverage === 'found');
  return `<div class="masthead cover-masthead"><div class="cover-company"><div class="company-file-mark" aria-hidden="true">${dossierCompanyArt}</div><div class="cover-company-copy"><div class="cover-kicker">企业研究案卷 <span>${demo ? '演示数据 · 公司为虚构' : esc(v.scenario_label || '企业核验')}</span></div><h1>${esc(c.case.company_name)}</h1></div></div><div class="cover-tools"><div class="report-actions"><button class="button" data-act="print-open">${dossierIcon('print')}打印一页结论</button><button class="button" data-act="supplement">${dossierIcon('plus')}补充材料</button><button class="button primary" data-act="contract">${dossierIcon('camera')}拍照二次分析</button></div><div class="cover-report-meta"><time>${esc(v.created_at?.slice(0,10) || '')}</time><label class="version-selector"><span class="sr-only">报告版本</span><select id="dossier-version" aria-label="切换报告版本">${c.versions.map(x => `<option value="${x.no}"${x.no === v.no ? ' selected' : ''}>第 ${x.no} 版 · ${esc(x.trigger_label || '初次查询')}${x.no === c.current ? '（最新）' : ''}</option>`).join('')}</select></label></div></div></div><div class="purpose-strip cover-purpose"><span>你这次想确认</span><p>${esc(v.need || '了解这家公司的公开资料')}</p></div>${prebuiltNoticeHtml(v)}${v.no !== c.current ? `<div class="version-banner">正在查看第 ${v.no} 版。<button data-act="ver" data-no="${c.current}">返回最新报告 →</button></div>` : ''}`;
}
function dossierCompanyKeywords(v) {
  const keywords = (v.company_keywords || []).filter(item => item.label && v.raw_ids.includes(item.ref));
  return `<div class="company-keywords" aria-label="公司关键词"><span class="company-keywords-label">公司关键词：</span><div class="company-keyword-list">${keywords.length ? keywords.map(item => `<button type="button" class="company-keyword" data-act="raw" data-ref="${esc(item.ref)}" title="${esc(item.basis)} · 点击查看出处">${esc(item.label)}<span aria-hidden="true">↗</span></button>`).join('') : '<span class="company-keywords-empty">资料不足，暂无可提取的关键词</span>'}</div></div>`;
}
function dossierTrustAnswer(v) {
  // A company-wide question must include recorded issues outside the scenario's short list.
  const items = Object.entries(glanceItems(v)).filter(([id]) => id !== 'reputation.user_reviews').map(([,item]) => item);
  const [status] = answerOf(items);
  if (status === 'bad' || status === 'warn') return [status, '有异常，需注意风险'];
  if (status === 'ok') return ['ok', '可信度较高'];
  return [status, '资料较少，需警惕'];
}
function dossierOverview(v) {
  const findings = dossierFindings(v), groups = dossierGroups(v);
  const [status, word] = dossierTrustAnswer(v);
  const initial = groups.problem.length ? 'problem' : groups.open.length ? 'open' : 'clear';
  const co = v.company;
  return `<section id="research-overview" class="research-section report-section">${dossierHeading('01','企业概况','围绕这次需求，先看判断与依据')}<div class="decision-grid"><article class="decision-card decision-dossier" data-inspection="${initial}"><span class="summary-folder-tab">企er / 核验摘要</span><div class="decision-sheet"><div class="decision-eyebrow"><span>这家公司是否值得你的信任</span><span class="decision-state">初步判断</span></div><div class="decision-hero"><div class="decision-verdict-copy"><div class="verdict-answer s-${status}"><span class="verdict-mark" aria-hidden="true">${MARK[status]}</span><div><h2 id="verdict-title">${word.split(/(?<=，)/).map(phrase => `<span class="verdict-phrase">${esc(phrase)}</span>`).join('')}</h2></div></div>${dossierCompanyKeywords(v)}</div><div class="summary-art" aria-hidden="true">${dossierSummaryArt}</div></div><div class="inspection-heading"><span>${findings.length} 项关键核查</span><small>点击纸签，展开依据</small></div><div class="verdict-summary" role="group" aria-label="关键核查分类">${[['problem','问题 / 留意'],['clear','已查无异常'],['open','待补 / 未覆盖']].map(([key,label]) => `<button class="verdict-count ${key}" data-act="dossier-group" data-group="${key}" data-count="${groups[key].length}" aria-pressed="${key === initial}" aria-controls="dossier-inspection"><span>${label}</span><strong>${groups[key].length}<small> 项</small></strong>${dossierIcon('arrow')}</button>`).join('')}</div><div class="overview-inspection" id="dossier-inspection">${dossierInspection(v, initial)}</div><div class="decision-next"><span class="summary-camera-mark">${dossierIcon('camera')}</span><div><small>建议下一步</small><button data-act="contract">补充材料，继续核实 ${dossierIcon('arrow')}</button></div><button class="summary-ask" data-act="open-assist">问小企 ${dossierIcon('chat')}</button></div></div></article><aside class="radar-card">${researchRadar(v)}<button class="radar-help" data-act="open-assist">${dossierGoose()}<span><strong>让小企解释这份报告</strong><small>依据、疑点、下一步</small></span>${dossierIcon('arrow')}</button></aside></div><details class="company-basics"><summary><span>${dossierIcon('building')}<strong>公司基础信息</strong><small>${co ? esc([co.status,co.founded && `${co.founded} 成立`].filter(Boolean).join(' · ')) : '登记资料未覆盖'}</small></span><span class="expand-label">展开登记资料 ＋</span></summary><div class="company-panel">${co ? `<dl class="company-facts">${[['公司全称',co.name],['统一社会信用代码',co.code || '未覆盖'],['登记状态',co.status],['成立日期',co.founded],['注册资本',co.checked == null || co.checked.includes('reg_capital') ? fmtMoney(co.reg_capital) : '未覆盖'],['经营范围',co.scope]].map(([label,value]) => `<div><dt>${label}</dt><dd>${termText(value || '未覆盖')}</dd></div>`).join('')}</dl>` : '<p>本版没有可展示的登记资料，未覆盖不代表不存在。</p>'}<button class="text-button" data-act="tab" data-tab="raw">查看登记资料与来源 ↗</button></div></details></section>`;
}
function dossierInspection(v, group, open = false) {
  const rows = dossierGroups(v)[group] || [];
  const label = {problem:'需要留意与核实的事项',clear:'已查项暂未见异常',open:'仍需补齐或核实的资料'}[group];
  return `<details class="inspection-disclosure"${open ? ' open' : ''}><summary><span>${label} · ${rows.length} 项</span><span class="inspection-toggle">展开 / 收起依据 ${dossierIcon('chevron')}</span></summary><div class="inspection-contents">${rows.map(row => `<div class="inspection-row dossier-evidence-row"><span class="inspection-bullet">${MARK[row.status]}</span><div>${termText(shortOf(v,row.id,row.text))}<small>${esc(stLabel(row))}</small></div><button class="text-button" data-act="goto" data-id="${esc(row.id)}">查看依据 ↗</button></div>`).join('') || '<p class="inspection-empty">这一分类没有记录；请结合其他分类与资料覆盖范围阅读。</p>'}<p class="inspection-boundary">判断仅限本版已查记录；未覆盖的部分仍需核实。</p></div></details>`;
}
function dossierSignal(sig, index, v) {
  const flagged = sig.items.filter(i => FLAG.has(i.status)).sort((a,b) => SEV[b.status] - SEV[a.status]);
  const open = sig.items.filter(isOpen), ok = sig.items.filter(i => i.status === 'ok');
  const phrase = flagged.length ? shortOf(v,`${sig.key}.${flagged[0].key}`,`${flagged[0].label}：${flagged[0].value}`)
    : !ok.length ? (open.length && open.every(i => gapOf(i) === 'failed') ? '没查成，稍后重查' : '尚无可确认的记录')
    : open.length ? `已查项暂未见异常；${pendingNote(open)}` : '已查项暂未见异常';
  const label = flagged.length ? `${flagged.length} 项需要留意` : open.length ? `${open.length} 项待核实` : `${ok.length} 项已查`;
  const scope = {risk:'承诺与履约',finance:'披露与资金',credit:'主体与履约',reputation:'报道与经历'};
  return `<button class="signal-card signal-${sig.key}" data-act="sigtile" data-key="${sig.key}" aria-label="查看${esc(sig.title)}方向：${esc(phrase)}"><span class="folder-tab" aria-hidden="true"><span>企er / 研究资料</span><b>0${index+1}</b></span><span class="folder-cover"><span class="folder-head"><span class="folder-heading"><strong>${esc(sig.title)}</strong><small>${scope[sig.key]}</small></span><span class="dossier-scene"><svg viewBox="0 0 156 138" aria-hidden="true">${dossierScenes[sig.key]}</svg></span></span><span class="paper-stack"><span class="paper-back"></span><span class="folder-paper"><span class="folder-paper-heading"><small>核查摘要</small><span class="folder-staple"></span></span><span class="badge">${label}</span><h3>${esc(phrase)}</h3><p>${esc(sig.lede)}</p></span></span><span class="signal-bottom"><span>内含 ${sig.items.length} 项核查记录</span><span class="signal-open">打开卷宗 ${dossierIcon('arrow')}</span></span></span></button>`;
}
function dossierQuestions(v) {
  const questions = v.questions || [];
  return `<article id="research-questions" class="question-guide"><div class="question-guide-head"><span class="feature-label"><b>02</b> 带着问题，与企业沟通</span><h3>建议后续询问</h3><p>围绕你关心的事，帮你把关键细节问清楚。</p></div><ol class="followup-question-list" aria-label="建议后续询问">${questions.map((q,i) => `<li data-item="${esc(q.id)}"><button class="followup-question-row" data-act="question-detail" data-question="${i}"><span class="followup-question-number" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><span class="followup-question-title">${esc(q.ask)}</span><span class="followup-question-arrow" aria-hidden="true">↗</span></button></li>`).join('')}</ol>${questions.length ? '<p class="question-list-hint">点开问题，查看完整问法与核对依据 ↗</p>' : '<p class="question-list-hint">本版暂无需要追问的问题，可补充材料后继续核实。</p>'}<div class="question-guide-next">${dossierGoose()}<p>拿到对方回复，<strong>交给小企核实。</strong></p><button class="text-button" data-act="supplement" data-kind="reply" aria-label="补充对方回复，继续复核">${dossierIcon('arrow')}</button></div></article>`;
}
function dossierPhoto() {
  return `<article id="research-photo" class="photo-feature"><div class="photo-feature-copy"><span class="feature-label"><b>01</b> 用你的材料，继续核实</span><h3>拍照二次分析</h3><p>合同、宣传页、聊天记录，<br>拍下来，核对承诺与条款。</p></div><div class="photo-feature-actions"><button class="button gold-button" data-act="contract">${dossierIcon('camera')}拍照 / 选择照片</button><button class="photo-secondary" data-act="supplement">也可补充文字、PDF、Word ↗</button><span class="photo-action-note">新材料进来，判断接着更新。</span></div><button class="camera-trigger" data-act="contract" aria-label="打开相机，拍照或选择照片"><span class="camera-art">${dossierCameraArt}</span><span class="camera-trigger-hint">轻点相机，开始复核 ↗</span></button><div class="photo-workflow" aria-label="材料复核流程"><span><b>1</b>补充材料</span><i>→</i><span><b>2</b>对照原报告</span><i>→</i><span><b>3</b>看判断变化</span></div></article>`;
}
function dossierPanel(key, title, sub, html) {
  return `<div class="research-tab-panel detail-panel${key === 'reviews' ? ' review-experience-panel' : ''}" id="research-details-panel-${key}" role="tabpanel" aria-labelledby="research-details-tab-${key}"${researchActiveTab.details !== key ? ' hidden' : ''}><div class="detail-panel-intro"><h3>${title}</h3><p>${sub}</p><span class="archive-intro-art">${archiveSvg(key)}</span></div>${html}</div>`;
}
function dossierTimeline(v) {
  const chart = (v.charts || []).find(c => c.kind === 'timeline'), events = chart?.events || [];
  const years = events.map(e => String(e.date || '').slice(0,4)).filter(y => /^\d{4}$/.test(y)).sort();
  return `<div id="research-timeline" class="timeline-list"><div class="timeline-caption"><span>${esc(years[0] || '—')} — ${esc(years.at(-1) || '—')}</span><small>悬停或点击节点 · 按事件顺序排列，非等距时间刻度</small></div><div class="research-timeline timeline-strip" role="group" aria-label="公司事件时间线">${events.map((e,i) => `<button class="research-event timeline-stop ${e.tone}${i === 0 ? ' active' : ''}" data-act="dossier-event" data-event="${i}" aria-pressed="${i === 0}"><span class="timeline-year">${esc(e.date.slice(0,4))}</span><span class="timeline-axis" aria-hidden="true"><span class="timeline-wave"><svg viewBox="0 0 100 32" preserveAspectRatio="none"><path d="M0 20C24 20 30 12 50 12S76 20 100 20"/></svg></span><span class="timeline-dot"></span></span><span class="timeline-ticket"><span class="timeline-day">${esc(e.date.slice(5))}</span><span class="timeline-label">${esc(e.label)}</span></span></button>`).join('')}</div><div class="timeline-focus-card" id="research-event-detail" aria-live="polite">${events.length ? dossierEvent(events[0]) : '<p>暂无有日期的事件记录。</p>'}</div><p class="research-fine">${esc(chart?.note || '只显示已查到的事件。')}</p></div>`;
}
function dossierEvent(event) {
  return `<time datetime="${esc(event.date)}"><span>${esc(event.date.slice(0,4))}</span><strong>${esc(event.date.slice(5) || '—')}</strong></time><div class="timeline-detail-copy"><h3>${termText(event.label)}</h3></div>${event.ref ? `<button class="text-button" data-act="raw" data-ref="${esc(event.ref)}">查看对应资料 ↗</button>` : ''}`;
}
function dossierReviews(v) {
  const R = S.reviews;
  if (!R) return '<p role="status">读取评价…</p>';
  const mine = R.reviews.some(r => r.mine), max = Math.max(1, ...Object.values(R.dist || {}));
  const snap = versionRaws(v).find(r => r.source_id === 'user_reviews');
  const fresh = R.count - (Array.isArray(snap?.content) ? snap.content.length : 0);
  return `${R.error ? `<p class="err" role="alert">评价暂未读到：${esc(R.error)}</p>` : ''}<div class="review-experience-grid"><aside class="review-distribution"><div class="review-distribution-title"><span>大家的体验</span><strong><b>${R.count}</b> <small>条评价</small></strong></div><div class="review-bars">${[5,4,3,2,1].map(n => `<div class="experience-bar" data-stars="${n}" aria-label="${n} 星，${R.dist[n] || 0} 条评价"><span>${n} <i>★</i></span><span class="experience-bar-track"><i style="width:${(R.dist[n] || 0) / max * 100}%"></i></span><b>${R.dist[n] || 0}</b></div>`).join('')}</div><div class="review-participation">${dossierGoose()}<p>你经历过的细节，<br><strong>也能成为一条线索。</strong></p></div></aside><div>${mine ? '<p class="rv-done">你已给这家公司写过评价，可以在下面查看。</p>' : reviewFormHtml()}${fresh > 0 ? `<div class="rv-fresh"><span>${fresh} 条新评价可纳入报告</span>${v.no === S.case.current ? `<button class="button" data-act="rv-refresh">放进报告，出新一版</button>` : '<span>请切换至最新报告后更新。</span>'}</div>` : ''}</div></div><div class="rv-list">${R.reviews.map(reviewHtml).join('')}</div><p class="review-opinion-note">用户个人观点，未经核实。系统不判断真假，也不算平均分。报告只看差评是否集中：集中才在“口碑”里标“要留意”；好评再多，也不算放心的理由。</p>`;
}
function dossierDetails(v) {
  return `<section id="research-details" class="research-section report-section">${dossierHeading('04','详细信息','完整记录保留，需要时再深入')}<div class="details-shell"><nav class="research-tabs detail-tabs" role="tablist" aria-label="详细信息分类">${researchTabs.details.map(([key,label],i) => `<button id="research-details-tab-${key}" role="tab" aria-controls="research-details-panel-${key}" aria-selected="${researchActiveTab.details === key}" tabindex="${researchActiveTab.details === key ? 0 : -1}" data-act="research-tab" data-group="details" data-key="${key}"><span class="archive-tab-number">0${i+1}</span>${label}</button>`).join('')}</nav>${dossierPanel('timeline','公司事件与核验时间线','把资料放回时间里看，区分发生时间与本次查阅时间。',dossierTimeline(v))}${dossierPanel('holders','股东与出资关系','股东背景不能替代主体履约核验。',researchShareholders(v))}${dossierPanel('capital','资本信息','认缴、实缴与可用资金是不同的信息。',researchCapital(v))}${dossierPanel('reviews','用户评价','看看星级分布，也听听具体经历。',`<div id="research-reviews-body">${dossierReviews(v)}</div>`)}</div></section>`;
}
function dossierReport(c, v) {
  const hasMaterialAnalysis = c.material_analyses?.some(a => a.report_version === v.no);
  const extraCharts = (v.charts || []).filter(chart => !['capital','complaints'].includes(chart.id) && !['share','timeline'].includes(chart.kind));
  return `${dossierSymbols}<div class="report-container">${dossierHero(c,v)}${dossierOverview(v)}<section id="research-signals" class="research-section report-section">${dossierHeading('02','四个信号','风险 · 财务 · 信用 · 口碑')}<div class="signal-grid">${v.signals.map((s,i) => dossierSignal(s,i,v)).join('')}</div><p class="signal-foot">四份资料，四个核验方向。打开卷宗，查看记录、未覆盖范围和对应出处。</p></section><section id="research-inquiry" class="research-section report-section priority-inquiry">${dossierHeading('03','问询与复核','围绕这次需求，继续核实、问清细节')}<div class="inquiry-intro"><h3>材料拿来核实，<em>问题带去沟通。</em></h3><p>小企陪你把查到的信息，用到接下来的沟通里。</p></div><div class="recheck-grid">${dossierPhoto()}${dossierQuestions(v)}</div>${!hasMaterialAnalysis && (v.assertions.length || v.missing.length || extraCharts.length) ? `<details class="dossier-material-results" id="research-claims"><summary>材料核对结果 · ${v.assertions.length + v.missing.length} 项</summary>${extraCharts.map(chart => chartCard(chart,v)).join('')}${claimsPanel(v,changeMap(v))}</details>` : ''}${v.no > 1 && !hasMaterialAnalysis ? `<details class="dossier-material-results" id="research-changes"><summary>报告第 ${v.no-1} 版 → 第 ${v.no} 版：判断的变化</summary>${changesPanel(v)}</details>` : ''}${SHOW_JUDGMENTS && v.judgments?.length ? `<details class="dossier-material-results" id="research-judgments"><summary>逐项核实记录</summary>${judgmentsPanel(v)}</details>` : ''}${MaterialAnalysis.list(c)}</section>${dossierDetails(v)}${researchSources(v)}${researchNotes(c,v)}</div>`;
}

function dossierSelectEvent(button) {
  const event = ver()?.charts.find(c => c.kind === 'timeline')?.events[Number(button.dataset.event)];
  if (!event) return;
  document.querySelectorAll('.timeline-stop').forEach(el => {el.classList.toggle('active',el === button);el.setAttribute('aria-pressed',String(el === button));});
  document.querySelector('#research-event-detail').innerHTML = dossierEvent(event);
}
function initDossierReport() {
  document.querySelector('#dossier-version')?.addEventListener('change', event => {location.hash = `#/case/${S.case.id}/v/${event.target.value}`;});
  const timeline = document.querySelector('.timeline-strip');
  timeline?.addEventListener('pointerover',event => {const button=event.target.closest('.timeline-stop');if(button)dossierSelectEvent(button);});
  timeline?.addEventListener('focusin',event => {const button=event.target.closest('.timeline-stop');if(button)dossierSelectEvent(button);});
  const camera = document.querySelector('.photo-feature');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const visibility = new IntersectionObserver(entries => entries.forEach(entry => entry.target.classList.toggle('motion-visible', entry.isIntersecting)), {threshold:.1});
  if (camera) visibility.observe(camera);
  const cleanup = researchCleanup;
  researchCleanup = () => { cleanup(); visibility.disconnect(); };
  document.querySelectorAll('.signal-card').forEach(card => {
    card.addEventListener('pointermove', event => {
      if (reduced.matches || event.pointerType === 'touch') return;
      const bounds=card.getBoundingClientRect();
      card.style.setProperty('--tilt-x', `${(.5-(event.clientY-bounds.top)/bounds.height)*5}deg`);
      card.style.setProperty('--tilt-y', `${((event.clientX-bounds.left)/bounds.width-.5)*5}deg`);
    });
    card.addEventListener('pointerleave', () => {card.style.removeProperty('--tilt-x');card.style.removeProperty('--tilt-y');});
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-act]');
  if (!button || !document.body.classList.contains('dossier-live')) return;
  if (button.dataset.act === 'dossier-event') dossierSelectEvent(button);
  if (button.dataset.act === 'dossier-group') {
    const group=button.dataset.group;
    document.querySelector('.decision-dossier').dataset.inspection=group;
    document.querySelectorAll('[data-act="dossier-group"]').forEach(b=>b.setAttribute('aria-pressed',String(b === button)));
    document.querySelector('#dossier-inspection').innerHTML=dossierInspection(ver(),group,true);
  }
});

// Scenario metadata can arrive after a saved report; refresh only its summary.
function refreshDossierScenario(v) {
  const current = document.querySelector('.decision-dossier');
  if (!current || !document.body.classList.contains('dossier-live')) return;
  const group = current.dataset.inspection;
  const wasOpen = !!current.querySelector('.inspection-disclosure')?.open;
  const template = document.createElement('template');
  template.innerHTML = dossierOverview(v);
  const updated = template.content.querySelector('.decision-dossier');
  if (wasOpen && group) {
    updated.dataset.inspection = group;
    updated.querySelector('#dossier-inspection').innerHTML = dossierInspection(v, group, true);
    updated.querySelectorAll('[data-act="dossier-group"]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.group === group)));
  }
  current.replaceWith(updated);
}
