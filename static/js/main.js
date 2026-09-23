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
    let submitted = false;
    form.addEventListener('submit', e => {
      if (submitted) { e.preventDefault(); return; }
      submitted = true;
      if (form.dataset.loading) showLoading(form.dataset.loading);
    });
  });
});

// Full-screen "working on it" overlay for forms whose next page waits on the
// AI (data-loading="message"). The page is replaced when the server answers,
// so there is nothing to hide afterwards.
function showLoading(message) {
  if (document.querySelector('.loading-overlay')) return;
  const el = document.createElement('div');
  el.className = 'loading-overlay';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  el.innerHTML = '<div class="loading-overlay__card">' +
    '<div class="loading-overlay__spinner" aria-hidden="true"></div>' +
    '<p class="loading-overlay__msg"></p>' +
    '<p class="loading-overlay__time">0s</p></div>';
  el.querySelector('.loading-overlay__msg').textContent = message;
  document.body.appendChild(el);
  const started = Date.now();
  const time = el.querySelector('.loading-overlay__time');
  setInterval(() => { time.textContent = Math.round((Date.now() - started) / 1000) + 's'; }, 1000);
}
