/* Saved, grounded material appendices and event-driven progress. No replay timer. */
(function(root,factory){
  if(typeof module==='object'&&module.exports) module.exports=factory();
  else root.MaterialAnalysis=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=v=>String(v||'').replace('T',' ').slice(0,16);
  const source=(id,label)=>`<button type="button" class="ma-link" data-act="material-raw" data-ref="${esc(id)}">${esc(label)} ↗</button>`;
  function list(c){
    const records=[...(c.material_analyses||[])].sort((a,b)=>b.report_version-a.report_version);
    if(!records.length) return '';
    return `<section class="ma-archive" aria-label="已完成的材料分析"><div class="ma-archive-head"><h3>材料分析 <small>${records.length} 份</small></h3><p>补充的材料与回复，分析后归入本案卷。</p></div><div class="ma-archive-list">${records.map((a,i)=>`<button type="button" class="ma-record" data-act="material-open" data-analysis="${esc(a.id)}"><span class="ma-folder" aria-hidden="true">${String(records.length-i).padStart(2,'0')}</span><span class="ma-record-copy"><strong>${esc(a.title)}</strong><span>${esc(a.summary)}</span></span><span class="ma-record-meta"><small>${esc(date(a.created_at))}</small><b>查看材料分析 ↗</b></span></button>`).join('')}</div></section>`;
  }
  function shell(company,titleId,body,footer){
    return `<div class="dlg-in ma-shell"><header class="dlg-head ma-head"><div><span class="ma-eyebrow">企er / 案卷附页</span><h3 id="${titleId}">材料分析</h3></div><button type="button" class="dlg-x" data-act="close-dlg" aria-label="收起材料分析">×</button></header><div class="dlg-body ma-body"><p class="ma-company">${esc(company)}</p>${body}</div><footer class="dlg-foot ma-foot">${footer}</footer></div>`;
  }
  function result(c,a,titleId='materialTitle'){
    const fs=a.findings||[], observations=a.observations||[], changes=a.changes||[];
    const labels={red:'需重点核实',amber:'需要留意',grey:'尚待核实',green:'记录相符'};
    return shell(c.case.company_name,titleId,`<div class="ma-context"><h4>${esc(a.title)}</h4><span>已完成 · ${esc(date(a.created_at))}</span></div>${a.need?`<p class="ma-need"><small>这次你想确认</small>${esc(a.need)}</p>`:''}<div class="ma-pocket"><span class="ma-tab">材料分析 / 核对摘要</span><div class="ma-summary"><span class="ma-eyebrow">本次材料 · ${fs.length+observations.length} 项核对要点</span><h4>${esc(a.summary)}</h4><p>结合材料原文与案卷中已有记录核对。未识别的条款、材料真实性及实际履约仍需另行确认。</p><div class="ma-source-list">${(a.raw_ids||[]).map(id=>source(id,'查看提交原文')).join('')}</div></div></div><div class="ma-findings">${fs.length?fs.map((f,i)=>`<details class="ma-finding"><summary><span class="ma-number">${String(i+1).padStart(2,'0')}</span><strong>${esc(f.kind_label)} · ${esc(f.text)}</strong><span class="ma-status ma-${esc(f.color)}">${labels[f.color]||'待核实'}</span><span aria-hidden="true">＋</span></summary><div class="ma-finding-body"><p>${esc(f.plain)}</p>${(f.quotes||[]).map(q=>`<blockquote>${esc(q)}</blockquote>`).join('')}<div class="ma-source-list">${(f.refs||[]).map(id=>source(id,'材料出处')).join('')}</div>${(f.checks||[]).map(check=>`<div class="ma-check"><strong>${esc(check.label)}</strong><span>${esc(check.result)}</span>${check.ref?source(check.ref,'查看依据'):''}</div>`).join('')}</div></details>`).join(''):observations.length?'':'<div class="ma-empty"><strong>这份材料还不能形成具体核对结论</strong><p>可以补充清晰、完整的合同条款，或包含主体名称、金额与条件的原文。未识别到说法，不代表材料没有问题。</p></div>'}${observations.map((o,i)=>`<details class="ma-finding"><summary><span class="ma-number">${String(fs.length+i+1).padStart(2,'0')}</span><strong>${esc(o.text)}</strong><span class="ma-status">${esc(o.state_label||'待核实')}</span><span aria-hidden="true">＋</span></summary><div class="ma-finding-body"><p>${esc(o.plain)}</p>${(o.basis||[]).map(b=>`${b.quote?`<blockquote>${esc(b.quote)}</blockquote>`:''}${b.ref?source(b.ref,b.label||'查看依据'):''}`).join('')}${(o.unknown||[]).map(t=>`<p>仍需核实：${esc(t)}</p>`).join('')}${(o.cannot||[]).map(t=>`<p class="ma-before">不能据此认定：${esc(t)}</p>`).join('')}</div></details>`).join('')}</div><details class="ma-impact"><summary>对原有判断的影响 <span>${changes.length?`${changes.length} 项变化`:'暂无可归因于本次材料的变化'} ＋</span></summary><div>${changes.map(change=>`<article><strong>${esc(change.label)}</strong><p>${esc(change.text)}</p>${change.before?`<p class="ma-before">原判断：${esc(change.before)}</p>`:''}${change.after?`<p>本次核对：${esc(change.after)}</p>`:''}${change.plain?`<p>${esc(change.plain)}</p>`:''}</article>`).join('')||'<p>原有判断仍保留，新增材料没有提供足以改变这些判断的依据。</p>'}<button type="button" class="ma-link" data-act="material-report" data-version="${a.report_version}">查看对应公司报告记录 ↗</button></div></details>${a.questions?.length?`<section class="ma-questions"><h4>建议后续询问</h4>${a.questions.map(q=>`<details><summary>${esc(q.ask)}</summary><p>${esc(q.why)}</p><p>${esc(q.check_where)}</p></details>`).join('')}</section>`:''}`,`<span>已保存到「问询与复核」底部</span><button type="button" class="btn sm" data-act="material-collapse" data-analysis="${esc(a.id)}">收起材料分析</button>`);
  }
  const stages=['读取材料','核对记录','整理分析'];
  function progressShell(c,record){
    return shell(c.case.company_name,'supTitle',`<div class="ma-context"><h4>${esc(record.body.title||(record.body.kind==='reply'?'对方回复':'补充材料'))}</h4><span>正在分析</span></div><div id="supProgress" class="ma-progress" aria-busy="true"><div class="ma-progress-main"><div class="ma-paper-art" aria-hidden="true"><span class="ma-paper-back">企业记录</span><span class="ma-paper-front">材料原文<i></i><i></i><i></i><i></i></span><b class="ma-scan"></b><span class="ma-lens">⌕</span></div><div class="ma-progress-copy"><span class="ma-eyebrow">小企正在核对</span><h4 data-ma-title>材料已提交，等待分析</h4><p data-ma-detail role="status" aria-live="polite">结果生成后会在这里展示，也会保存在本案卷中。</p></div></div><ol class="ma-stages">${stages.map((s,i)=>`<li data-ma-stage="${i}" ${i===0?'aria-current="step"':''}><b>${i+1}</b><span>${s}</span><small>${i===0?'进行中':'待开始'}</small></li>`).join('')}</ol></div><p class="ma-persist-note">可以收起或离开页面。回到本案卷，可继续查看同一次分析。</p><p id="supErr" class="err" role="status" aria-live="polite"></p>`,`<button type="button" class="btn ghost sm" data-act="close-dlg">暂时收起</button><button type="button" id="supResume" class="btn sm" data-act="sup-resume" hidden>恢复进度 / 结果</button><button type="button" id="supEdit" class="btn sm" data-act="sup-edit" hidden>检查材料并重新提交</button>`);
  }
  function mount(host){
    let current=0, stopped=false;
    function onEvent(event){
      if(stopped) return;
      if(event.type==='step'){
        const stage=event.id==='plain'?2:1;
        current=Math.max(current,stage);
        host.querySelector('[data-ma-title]').textContent=stages[current];
        host.querySelector('[data-ma-detail]').textContent=event.text||`${event.label||'核对材料'}${event.phase==='done'?'已完成':'，请稍候…'}`;
        host.querySelectorAll('[data-ma-stage]').forEach((el,i)=>{
          const active=i===current;
          el.classList.toggle('is-done',i<current);
          if(active)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');
          el.querySelector('small').textContent=i<current?'已完成':active?'进行中':'待开始';
        });
      }
    }
    return {onEvent,stop(){stopped=true;host.setAttribute('aria-busy','false');},error(terminal){
      host.classList.add('ma-stopped');host.setAttribute('aria-busy','false');
      host.querySelectorAll('[data-ma-stage]').forEach((el,i)=>{el.removeAttribute('aria-current');if(i===current)el.querySelector('small').textContent=terminal?'未完成':'待确认';});
      host.querySelector('[data-ma-title]').textContent=terminal?'分析未完成':'连接中断，进度待确认';
      host.querySelector('[data-ma-detail]').textContent='已保留本次任务与材料，可恢复查看结果。';
    }};
  }
  return {list,result,progressShell,mount};
});
