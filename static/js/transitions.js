/* FORMA — page transition direction. Loaded in <head>: pagereveal can fire
   before a script at the end of <body> has run. */

// Page transitions. The motion itself is CSS (@view-transition in main.css);
// this only tells it which way the user is travelling through the brief, so
// Next slides one way and Back the other. Pages not in the order (exports,
// uploads) fall through to the neutral rise.
(function () {
  const ORDER = {
    '/': 0, '/start': 0.5,
    '/step1': 1, '/step1/reading': 1.5,
    '/step2': 2, '/step2/reviewing': 2.5,
    '/step3': 3, '/step4': 4, '/step5': 5,
  };
  const KEY = 'forma:from';
  const root = document.documentElement;

  // No cross-document transitions here (Firefox): give the content a CSS
  // arrival instead so pages still ease in.
  if (!('onpagereveal' in window)) {
    root.classList.add('vt-fallback');
    return;
  }

  addEventListener('pageswap', () => {
    try { sessionStorage.setItem(KEY, location.pathname); } catch (e) { /* noop */ }
  });

  addEventListener('pagereveal', e => {
    if (!e.viewTransition) return;
    let from = null;
    try { from = sessionStorage.getItem(KEY); sessionStorage.removeItem(KEY); } catch (err) { /* noop */ }

    const a = ORDER[from], b = ORDER[location.pathname];
    let dir = '';
    if (from === '/' && b > 0)          dir = 'intro';
    else if (a != null && b != null)    dir = b > a ? 'forward' : b < a ? 'back' : '';
    // Set even when neutral: its presence also stops the landing stagger
    // from replaying underneath a transition.
    root.dataset.vt = dir;
  });
})();
