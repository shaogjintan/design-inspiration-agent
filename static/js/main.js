/* FORMA — shared JS */

// Smooth scroll reveal for any .reveal elements
document.addEventListener('DOMContentLoaded', () => {
  // Auto-select tile if radio is already checked (e.g. after back navigation)
  document.querySelectorAll('.tile input[type=radio]:checked').forEach(r => {
    r.closest('.tile')?.classList.add('tile--selected');
  });

  document.querySelectorAll('.colour-swatch input:checked').forEach(r => {
    r.closest('.colour-swatch')?.classList.add('colour-swatch--selected');
  });

  // Prevent double-submit on all forms
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', e => {
      if (form.dataset.submitted) { e.preventDefault(); return; }
      form.dataset.submitted = '1';
      if (form.dataset.loading) showLoading(form.dataset.loading);
    });
  });
});

// Coming back with the browser's Back button can restore this page from cache
// with the overlay still up and forms still locked — reset both.
window.addEventListener('pageshow', e => {
  if (!e.persisted) return;
  document.querySelector('.loading-overlay')?.remove();
  document.querySelectorAll('form[data-submitted]').forEach(f => delete f.dataset.submitted);
});

// Full-screen progress screen for forms whose next page waits on the AI
// (data-loading="message"). Call it right before the request is sent: it puts
// a random token in the "forma_progress" cookie, the server reports each AI
// task against that token, and we poll /progress/<token> to draw one bar per
// task plus an overall bar. The page is replaced when the server answers, so
// there is nothing to tear down.
function showLoading(message) {
  if (document.querySelector('.loading-overlay')) return;

  const token = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2);
  document.cookie = 'forma_progress=' + token + '; path=/; SameSite=Lax';

  const el = document.createElement('div');
  el.className = 'loading-overlay';
  el.innerHTML =
    '<div class="loading-overlay__card" role="status" aria-live="polite">' +
      '<p class="loading-overlay__msg"></p>' +
      '<div class="progress progress--overall" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">' +
        '<div class="progress__fill"></div></div>' +
      '<p class="loading-overlay__meta"><span class="loading-overlay__pct">0%</span>' +
        '<span class="loading-overlay__time">0s</span></p>' +
      '<ul class="loading-overlay__tasks"></ul>' +
    '</div>';
  el.querySelector('.loading-overlay__msg').textContent = message;
  document.body.appendChild(el);

  const overall = el.querySelector('.progress--overall');
  const overallFill = overall.querySelector('.progress__fill');
  const pct = el.querySelector('.loading-overlay__pct');
  const time = el.querySelector('.loading-overlay__time');
  const list = el.querySelector('.loading-overlay__tasks');
  const started = Date.now();
  const rows = {};   // label -> row element

  // A running task fills towards 95% over its usual duration, easing off so a
  // slow call never looks finished; it snaps to 100% when the server says so.
  function taskFraction(t) {
    if (t.status === 'done' || t.status === 'failed') return 1;
    if (t.status !== 'running') return 0;
    return 0.95 * (1 - Math.exp(-t.elapsed / Math.max(t.expected, 1)));
  }

  function render(tasks) {
    let sum = 0;
    tasks.forEach(t => {
      let row = rows[t.label];
      if (!row) {
        row = document.createElement('li');
        row.className = 'loading-task';
        row.innerHTML = '<span class="loading-task__label"></span>' +
          '<div class="progress progress--task"><div class="progress__fill"></div></div>';
        row.querySelector('.loading-task__label').textContent = t.label;
        list.appendChild(row);
        rows[t.label] = row;
      }
      const f = taskFraction(t);
      sum += f;
      row.dataset.status = t.status;
      row.querySelector('.progress__fill').style.width = (f * 100).toFixed(1) + '%';
    });
    // Before the server has announced any task, creep slowly so it's clearly alive.
    const secs = (Date.now() - started) / 1000;
    const frac = tasks.length ? sum / tasks.length : Math.min(0.08, secs * 0.02);
    const p = Math.round(frac * 100);
    overallFill.style.width = p + '%';
    overall.setAttribute('aria-valuenow', p);
    pct.textContent = p + '%';
  }

  async function poll() {
    try {
      const res = await fetch('/progress/' + encodeURIComponent(token), { cache: 'no-store' });
      if (res.ok) render((await res.json()).tasks || []);
    } catch (_) { /* keep polling; the real page is on its way */ }
    time.textContent = Math.round((Date.now() - started) / 1000) + 's';
    setTimeout(poll, 600);
  }
  render([]);
  setTimeout(poll, 300);
}
