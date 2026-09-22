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
    });
  });
});
