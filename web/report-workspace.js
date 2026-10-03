/* Report navigation and assistant layout; application actions stay in app.js. */
(() => {
  const sidebar = document.createElement('aside');
  sidebar.className = 'workspace-sidebar';
  sidebar.setAttribute('aria-label', '功能导航');
  const icons = {
    overview:'M4 20V9l8-5 8 5v11H4ZM9 20v-7h6v7M8 9h.01M16 9h.01',
    signals:'M5 18V9m7 9V4m7 14v-6M3 21h18',
    inquiry:'M5 7h3l2-3h4l2 3h3a2 2 0 0 1 2 2v10H3V9a2 2 0 0 1 2-2ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    details:'M5 3h10l4 4v14H5V3Zm10 0v5h4M9 12h6m-6 4h6',
  };
  const icon = key => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[key]}"/></svg>`;
  sidebar.innerHTML = `<div class="workspace-nav-label">工作空间</div><div class="workspace-global-nav"></div><div class="workspace-nav-label workspace-chapter-label">本份报告</div><nav class="workspace-chapters" aria-label="报告目录">${[['overview','企业概况'],['signals','四个信号'],['inquiry','问询与复核'],['details','详细信息']].map(([key,label],i)=>`<button type="button" class="workspace-chapter${i<2?' is-primary':''}" data-act="section" data-section="${key}" ${i===0?'aria-current="location"':''}>${icon(key)}<span>${label}</span><small aria-hidden="true">0${i+1}</small></button>`).join('')}</nav><div class="workspace-sidebar-foot"><i></i><span>小企研究室</span></div>`;
  document.body.append(sidebar);
  const archiveNote = document.createElement('div');
  archiveNote.className = 'archive-sidebar-note';
  archiveNote.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></svg><b>你的私人档案</b><p>上传的材料和对话<br>不会自动公开。</p>';
  sidebar.insertBefore(archiveNote, sidebar.querySelector('.workspace-sidebar-foot'));
  const shellNav = document.getElementById('shellNav');
  const topbar = document.getElementById('topbar');
  const assistantButton = document.createElement('button');
  assistantButton.type = 'button';
  assistantButton.className = 'workspace-assistant-toggle';
  assistantButton.dataset.act = 'open-assist';
  assistantButton.setAttribute('aria-controls','assist');
  assistantButton.setAttribute('aria-expanded','false');
  assistantButton.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 5h16v12H9l-5 4V5Z"/><path d="M8 9h8M8 13h5"/></svg><span>小企助手</span>';
  topbar.append(assistantButton);

  function syncLayout() {
    const enabled = document.body.classList.contains('research-mode');
    if (document.body.classList.contains('report-workspace') !== enabled) document.body.classList.toggle('report-workspace', enabled);
    if (enabled && shellNav.parentElement !== sidebar.querySelector('.workspace-global-nav')) sidebar.querySelector('.workspace-global-nav').append(shellNav);
    if (!enabled && shellNav.parentElement !== topbar) topbar.insertBefore(shellNav, document.getElementById('caseStrip'));
  }
  syncLayout();
  new MutationObserver(syncLayout).observe(document.body, {attributes:true, attributeFilter:['class']});

  let previousAssist;
  const assistObserver = new MutationObserver(syncAssistant);
  function syncAssistant() {
    const assist = document.getElementById('assist');
    const open = !!assist?.classList.contains('open');
    assistantButton.dataset.act = open ? 'close-assist' : 'open-assist';
    assistantButton.setAttribute('aria-expanded', String(open));
    assistantButton.setAttribute('aria-label', open ? '收起助手' : '小企助手');
    assistantButton.querySelector('span').textContent = open ? '收起助手' : '小企助手';
    if (previousAssist !== assist) {
      assistObserver.disconnect();
      if (assist) assistObserver.observe(assist, {attributes:true, attributeFilter:['class']});
      previousAssist = assist;
    }
  }
  new MutationObserver(() => { syncAssistant(); syncChapter(); }).observe(document.getElementById('view'), {childList:true});
  syncAssistant();

  let scrollFrame;
  function syncChapter() {
    scrollFrame = 0;
    const buttons = [...sidebar.querySelectorAll('[data-section]')];
    let current = buttons[0];
    buttons.forEach(button => {
      if (document.getElementById(`research-${button.dataset.section}`)?.getBoundingClientRect().top <= 180) current = button;
    });
    buttons.forEach(button => button === current ? button.setAttribute('aria-current','location') : button.removeAttribute('aria-current'));
  }
  window.addEventListener('scroll', () => {if (!scrollFrame) scrollFrame = requestAnimationFrame(syncChapter);}, {passive:true});
  sidebar.addEventListener('click', event => {
    const button = event.target.closest('[data-section]');
    if (!button) return;
    event.stopPropagation();
    const section = document.getElementById(`research-${button.dataset.section}`);
    if (section) window.scrollTo({top:window.scrollY + section.getBoundingClientRect().top - 80,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    sidebar.querySelectorAll('[data-section]').forEach(b => b === button ? b.setAttribute('aria-current','location') : b.removeAttribute('aria-current'));
  });
  // At narrow widths the assistant becomes a separate full-width row, never an overlay.
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-act="open-assist"]');
    if (button && document.body.classList.contains('report-workspace') && matchMedia('(max-width: 1099px)').matches) {
      requestAnimationFrame(() => document.getElementById('assist')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}));
    }
  }, true);
})();
