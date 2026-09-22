/* FORMA — shared JS */

// Iris transition. Starting a project closes to black from the centre, and the
// arriving page opens back out of the same point. The flag is set just before
// navigating and consumed on arrival, so a normal visit is unaffected.
(function () {
  const KEY = 'forma:iris';
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  try {
    if (sessionStorage.getItem(KEY)) {
      sessionStorage.removeItem(KEY);
      if (!calm) {
        document.documentElement.classList.add('is-opening');
        // Leave no clip-path behind: it would trap fixed children later.
        addEventListener('DOMContentLoaded', () => {
          const body = document.body;
          body.addEventListener('animationend', function done() {
            document.documentElement.classList.remove('is-opening');
            body.removeEventListener('animationend', done);
          });
        });
      }
    }
  } catch (e) { /* private mode — just skip the effect */ }

  addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-iris]').forEach(link => {
      link.addEventListener('click', e => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        try { sessionStorage.setItem(KEY, '1'); } catch (err) { /* noop */ }
        if (calm) { window.location.href = link.href; return; }

        // Hard cut: the cover is opaque the moment it lands. The short hold is
        // there so the black registers as a beat before the next page opens
        // out of it — without it the cut is invisible.
        const cover = document.createElement('div');
        cover.className = 'iris-cover';
        document.body.appendChild(cover);
        setTimeout(() => { window.location.href = link.href; }, 200);
      });
    });
  });
})();

// Smooth scroll reveal for any .reveal elements
document.addEventListener('DOMContentLoaded', () => {
  // Auto-select tile if radio is already checked (e.g. after back navigation)
  document.querySelectorAll('.tile input[type=radio]:checked').forEach(r => {
    r.closest('.tile')?.classList.add('tile--selected');
  });

  document.querySelectorAll('.colour-swatch input:checked').forEach(r => {
    r.closest('.colour-swatch')?.classList.add('colour-swatch--selected');
  });

  // Same for item checkboxes, which were missed — a saved selection rendered
  // as unselected and a click would have cleared it rather than restored it.
  document.querySelectorAll('.check-tile input[type=checkbox]:checked').forEach(cb => {
    cb.closest('.check-tile')?.classList.add('check-tile--checked');
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

// The mover jumps when you click anywhere on the page. Retriggerable: the
// class is removed and the node reflowed so a second click restarts it rather
// than being swallowed mid-animation.
document.addEventListener('DOMContentLoaded', () => {
  const figures = document.querySelectorAll('.mover__figure');
  if (!figures.length) return;

  document.addEventListener('click', () => {
    figures.forEach(fig => {
      fig.classList.remove('is-hopping');
      void fig.offsetWidth;            // force reflow so the animation restarts
      fig.classList.add('is-hopping');
    });
  });

  figures.forEach(fig => {
    fig.addEventListener('animationend', e => {
      if (e.animationName === 'mover-hop') fig.classList.remove('is-hopping');
    });
  });
});

// Autosave. The step pages are plain forms, so leaving one by its Back link
// used to throw away everything typed since the page loaded. Edits are posted
// as you work; uploads still need a real submit, because script cannot read a
// file input back.
document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('form[data-autosave]');
  if (!form) return;

  const endpoint = '/autosave/' + form.dataset.autosave;
  const status = document.getElementById('autosave-status');
  let timer = null, dirty = false;

  function send(useBeacon) {
    if (!dirty) return;
    dirty = false;
    const data = new FormData(form);
    for (const [k, v] of [...data.entries()]) {
      if (v instanceof File) data.delete(k);   // files travel on submit only
    }
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(endpoint, data);    // survives the page unloading
      return;
    }
    fetch(endpoint, { method: 'POST', body: data })
      .then(r => r.ok && status && (status.textContent = 'Saved'))
      .catch(() => { dirty = true; });
  }

  form.addEventListener('input', () => {
    dirty = true;
    if (status) status.textContent = 'Saving…';
    clearTimeout(timer);
    timer = setTimeout(() => send(false), 700);
  });
  form.addEventListener('change', () => {
    dirty = true;
    clearTimeout(timer);
    timer = setTimeout(() => send(false), 300);
  });

  // Leaving the page — by the Back link, a nav click or closing the tab.
  addEventListener('pagehide', () => send(true));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') send(true);
  });
  form.addEventListener('submit', () => { dirty = false; clearTimeout(timer); });
});
