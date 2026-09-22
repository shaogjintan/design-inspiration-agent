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

  // Prevent double-submit, and say so. These forms carry image uploads, so
  // the gap between click and the next page is seconds of silence otherwise —
  // which reads as a dead button and invites a second click.
  document.querySelectorAll('form').forEach(form => {
    let submitted = false;
    form.addEventListener('submit', () => {
      if (submitted) return;
      submitted = true;

      const btn = form.querySelector('[type=submit]');
      if (!btn) return;

      // Not `disabled`: a disabled control can drop out of the submission in
      // some browsers. Block further clicks instead and mark it busy.
      btn.classList.add('is-busy');
      btn.setAttribute('aria-busy', 'true');
      btn.addEventListener('click', ev => ev.preventDefault());

      if (btn.dataset.busyLabel) btn.textContent = btn.dataset.busyLabel;
    });
  });
});
