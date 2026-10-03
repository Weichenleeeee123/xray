/* Preview-only interactions. No requests, writes or fake report results. */
const assist = document.querySelector('#assist');
const toggle = document.querySelector('#toggle-assist');
function setAssistant(open) {
  assist.classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.querySelector('span').textContent = open ? '收起助手' : '小企助手';
}
toggle.addEventListener('click', () => setAssistant(!assist.classList.contains('open')));
document.querySelector('#close-assist').addEventListener('click', () => setAssistant(false));
let toastTimer;
document.querySelectorAll('[data-preview-action]').forEach(button => button.addEventListener('click', event => {
  event.preventDefault();
  const toast = document.querySelector('.preview-toast');
  toast.textContent = `布局预览：${button.dataset.previewAction}。确认布局后再接入实际功能。`;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2600);
}));
