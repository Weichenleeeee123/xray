/* Saved-source presentation only: never infer missing values or change evidence. */
const SourceRecords = (() => {
  const preferred = {
    qcc_labor: ['案由','日期','案号','机构','法院','它的角色','类型','被告'],
    qcc_hearings: ['案由','日期','案号','法院','它的角色','被告'],
    qcc_filings: ['案由','日期','案号','法院','它的角色','被告'],
    qcc_jobs: ['职位','月薪','地点','学历','日期'],
    qcc_changes: ['项目','日期','变更前','变更后'],
    qcc_licenses: ['名称','状态','编号','机关','有效期自','有效期至'],
    qcc_qualifications: ['名称','状态','发证日期','有效期至'],
    qcc_controller: ['名称','总持股比例','表决权比例','是自然人'],
    qcc_news: ['标题','日期','来源','平台情感标注','链接'],
  };
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function render(record, quotes = []) {
    const {content, source_id: source} = record;
    const text = value => markText(String(value), quotes);
    const scalar = (value, key) => {
      if (value === null || value === undefined || value === '') return '<span class="muted">未提供</span>';
      if (typeof value === 'boolean') return text(value ? '是' : '否');
      if (typeof value === 'string' && /^(链接|url|网址)$/i.test(key || '')) {
        const info = sourceLinkInfo(value, record);
        if (info) return `<a href="${esc(info.href)}" target="_blank" rel="noopener noreferrer">${text(info.label)} ↗</a><span class="sr-link-address">${text(value)}</span>${info.note ? `<span class="sr-link-note">${text(info.note)}</span>` : ''}`;
      }
      return text(value);
    };
    const order = obj => {
      const first = preferred[source] || ['企业名称','登记状态','成立日期','注册资本','实缴资本','统一社会信用代码'];
      return [...first.filter(key => Object.hasOwn(obj,key)), ...Object.keys(obj).filter(key => !first.includes(key))];
    };
    function fields(obj, depth) {
      return `<dl class="sr-fields">${order(obj).map(key => `<div class="sr-field${obj[key] !== null && typeof obj[key] === 'object' ? ' sr-field-group' : ''}"><dt>${esc(key)}</dt><dd>${value(obj[key],key,depth+1)}</dd></div>`).join('')}</dl>`;
    }
    function card(row, index, depth) {
      if (!object(row)) return `<li class="sr-card">${value(row,'',depth+1)}</li>`;
      const titleKey = order(row).find(key => ['职位','案由','项目','名称','标题','案号','决定文书号','决定书文号','股东名称','企业名称','报告期'].includes(key) && typeof row[key] === 'string' && row[key]);
      const rest = Object.fromEntries(Object.entries(row).filter(([key]) => key !== titleKey && !(source === 'qcc_changes' && ['变更前','变更后'].includes(key))));
      const compare = source === 'qcc_changes' && (Object.hasOwn(row,'变更前') || Object.hasOwn(row,'变更后'))
        ? `<div class="sr-compare">${['变更前','变更后'].map(key => `<div><h5>${key}</h5>${Object.hasOwn(row,key) ? value(row[key],key,depth+1) : '<span class="muted">未提供</span>'}</div>`).join('')}</div>` : '';
      return `<li class="sr-card"><div class="sr-card-heading"><span class="sr-number">${index+1}</span><h5>${titleKey ? `${esc(titleKey)} · ${text(row[titleKey])}` : `记录 ${index+1}`}</h5></div>${fields(rest,depth)}${compare}</li>`;
    }
    function list(rows, key, depth) {
      if (!rows.length) return '<p class="muted">本次返回的列表为空。</p>';
      if (rows.every(row => row === null || typeof row !== 'object')) return `<ul class="sr-values">${rows.map(row=>`<li>${scalar(row,key)}</li>`).join('')}</ul>`;
      const financial = source === 'qcc_finance' && key === '报告期' && rows.every(object) && rows.every(row => Object.values(row).every(v => v === null || typeof v !== 'object'));
      if (financial) {
        const keys = [...new Set(rows.flatMap(row => Object.keys(row)))];
        return `<p class="sr-scope">按来源报告期展示；不同报告期口径请分别核对，金额单位以各单元格为准。</p><div class="sr-table-scroll" tabindex="0" role="region" aria-label="财务报告期明细"><table class="sr-financial"><thead><tr>${keys.map(k=>`<th scope="col">${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${keys.map(k=>`<td>${scalar(row[k],k)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      }
      const html = rows.map((row,i)=>card(row,i,depth));
      // Keep the complete saved sample accessible without overwhelming the dialog.
      const hit = quotes.some(q => typeof q === 'string' && q.trim().length >= 2 && JSON.stringify(rows.slice(10)).includes(q));
      return `<ol class="sr-record-list">${html.slice(0,10).join('')}</ol>${html.length > 10 ? `<details class="sr-more"${hit ? ' open' : ''}><summary>展开其余 ${html.length-10} 条已保存明细</summary><ol class="sr-record-list" start="11">${html.slice(10).join('')}</ol></details>` : ''}`;
    }
    function value(v, key, depth = 0) {
      // Deep/novel payloads remain faithfully accessible in their saved form.
      if (depth > 12) return `<pre class="json">${text(JSON.stringify(v,null,2))}</pre>`;
      if (Array.isArray(v)) return list(v,key,depth);
      if (object(v)) return Object.keys(v).length ? `<section class="sr-group">${fields(v,depth)}</section>` : '<span class="muted">空对象</span>';
      return scalar(v,key);
    }
    if (content === null || content === undefined) return '<p class="muted">本次没有取得可展示的来源记录，请查看上方查询状态与说明。</p>';
    const sample = object(content) && Array.isArray(content['返回的明细']) ? content['返回的明细'].length
      : object(content) && Array.isArray(content['全部返回新闻']) ? content['全部返回新闻'].length : null;
    const total = object(content) ? content['平台记录总数'] : undefined;
    const scope = sample !== null ? `<div class="sr-scope">${Number.isInteger(total) && total >= 0 ? `平台记录总数 <strong>${total}</strong> 条 · ` : ''}本次取得 <strong>${sample}</strong> 条明细${Number.isInteger(total) && total > sample ? '；仅展示已取得的部分记录。' : '。'}</div>` : '';
    const extra = source === 'qcc_finance' && Array.isArray(content?.['报告期']) ? `<p class="sr-scope">本次已保存 ${content['报告期'].length} 个报告期的明细。</p>`
      : source === 'qcc_news' ? '<p class="sr-scope">新闻倾向为平台标注，仅描述返回样本，不代表企业整体评价。</p>' : '';
    const body = value(content,'');
    return `<div class="sr-readable" data-source="${esc(source || '')}">${scope}${extra}${body}</div><details class="sr-json"><summary>查看已保存 JSON</summary><pre class="json">${text(JSON.stringify(content,null,2))}</pre></details>`;
  }
  return {render};
})();
