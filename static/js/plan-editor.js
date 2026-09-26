/* FORMA — page 2's plan editor: the rooms placed on the floor plan, for the
   homeowner to confirm by their edges before anything is drawn from them.

   Each room is its outline: a polygon whose walls run only across and down,
   so a plain room has four corners and an L-shaped one six. Every wall is a
   handle — dragging one moves it together with the wall of any room on the
   other side, so shared walls stay shared — and walls snap to the lines found
   in the plan image itself. A room is marked out by dragging corner to corner,
   by clicking round its corners, or made L-shaped by cutting a corner away.

   The server keeps rooms as rectangles (an L is two), so outlines are cut into
   rectangles on the way out and rebuilt from them on the way in. Rooms are
   keyed by their card in the list (data-uid), so renaming keeps their place.
   All coordinates are plan-image pixels. */
(function () {
  const root = document.getElementById('plan-editor');
  const acc = document.getElementById('room-accordion');
  if (!root || !acc) return;

  const cfg = JSON.parse(document.getElementById('plan-editor-data').textContent);
  const W = cfg.w, H = cfg.h;
  const NS = 'http://www.w3.org/2000/svg';
  const svg = root.querySelector('.pe-svg');
  const input = root.querySelector('input[name="plan_edit"]');
  const status = root.querySelector('.pe-status');
  const tray = root.querySelector('.pe-tray');
  const live = root.querySelector('.pe-live');
  const tools = root.querySelector('.pe-tools');
  const resetBtn = root.querySelector('.pe-reset');
  const doorTools = root.querySelector('.pe-door-tools');
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const GRIP = matchMedia('(pointer: coarse)').matches ? 26 : 12;   // a finger needs more
  const walls = cfg.walls || { x: [], y: [] };
  const MAX_PARTS = 4;

  // uid -> { from: the name it was traced under (or null), polys: [[[x, y], ...]] }
  let rooms = new Map();
  let detected = {};            // the trace as it came back, for Reset
  let outline = cfg.outline || [];
  let selected = null;
  let marking = null;           // { uid, mode: 'corners' | 'door', pts } while marking
  let freshDoor = -1;           // a door just added, shown off once
  let touched = false;
  let hint = '';
  // Doors in plan pixels: { x, y, axis: 'h' (in a wall running across) | 'v',
  // dir: +1 | -1 (the side the leaf swings to: down/right is +1),
  // hinge: 'low' | 'high' (the gap's top/left end or the other) }.
  let doors = (cfg.doors || []).map(d => ({ ...d }));
  let detectedDoors = doors.map(d => ({ ...d }));
  let selectedDoor = -1;
  let doorPx = cfg.door_px || Math.max(W, H) * 0.04;

  const cards = () => Array.from(acc.querySelectorAll('.accordion-item'));
  const labelOf = card => card.querySelector('input[name="kept_rooms"]').value;
  const cardOf = uid => cards().find(c => c.dataset.uid === uid);
  const nameOf = uid => { const c = cardOf(uid); return c ? labelOf(c) : ''; };
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const round = v => Math.round(v * 10) / 10;
  const q = uid => `.pe-room[data-uid="${CSS.escape(uid)}"]`;
  const uniq = vs => Array.from(new Set(vs.map(round))).sort((a, b) => a - b);

  // Show the flat, not the sheet around it: plans often come with wide white
  // margins. The view crops; coordinates stay in the plan image's pixels.
  function frame() {
    const xs = [...(walls.x || [])], ys = [...(walls.y || [])];
    (cfg.outline || []).forEach(o => { xs.push(o[0], o[0] + o[2]); ys.push(o[1], o[1] + o[3]); });
    Object.values(cfg.rooms || {}).flat().forEach(p => { xs.push(p[0], p[0] + p[2]); ys.push(p[1], p[1] + p[3]); });
    if (xs.length < 2 || ys.length < 2) return [0, 0, W, H];
    const pad = Math.max(W, H) * 0.06;
    const x0 = Math.max(0, Math.min(...xs) - pad), y0 = Math.max(0, Math.min(...ys) - pad);
    const x1 = Math.min(W, Math.max(...xs) + pad), y1 = Math.min(H, Math.max(...ys) + pad);
    return (x1 - x0) * (y1 - y0) < W * H * 0.15 ? [0, 0, W, H] : [x0, y0, x1 - x0, y1 - y0];
  }
  const view = frame();
  svg.setAttribute('viewBox', view.join(' '));
  svg.style.aspectRatio = `${view[2]} / ${view[3]}`;

  // One screen pixel in plan pixels, so grips and snapping feel the same size
  // whatever the plan's resolution or zoom.
  function unit() {
    const m = svg.getScreenCTM();
    return m && m.a ? 1 / m.a : 1;
  }

  // ── Outlines and rectangles ────────────────────────────────────────────────
  // The outline of what the rectangles in `adds` cover and those in `subs` do
  // not, found on the grid their edges make. Returns the outer loops, largest
  // first, and whether any hole was left inside.
  function outlineOf(adds, subs = []) {
    // Edges a hair apart are one edge — a cut that snapped to a wall line
    // beside the room's own edge must not leave a sliver. The room's own
    // edges win over the cut's.
    const eps = 3 * unit();
    const settle = own => {
      const keep = uniq(own);
      const at = v => keep.find(k => Math.abs(k - v) <= eps) ?? v;
      return at;
    };
    const atX = settle(adds.flatMap(r => [r[0], r[0] + r[2]]));
    const atY = settle(adds.flatMap(r => [r[1], r[1] + r[3]]));
    const fit = r => { const x0 = atX(r[0]), y0 = atY(r[1]), x1 = atX(r[0] + r[2]), y1 = atY(r[1] + r[3]);
                       return [x0, y0, x1 - x0, y1 - y0]; };
    adds = adds.map(fit);
    subs = subs.map(fit).filter(r => r[2] > 0 && r[3] > 0);
    const xs = uniq([...adds, ...subs].flatMap(r => [r[0], r[0] + r[2]]));
    const ys = uniq([...adds, ...subs].flatMap(r => [r[1], r[1] + r[3]]));
    const inside = (r, x, y) => x > r[0] && x < r[0] + r[2] && y > r[1] && y < r[1] + r[3];
    const cov = (i, j) => {
      if (i < 0 || j < 0 || i >= xs.length - 1 || j >= ys.length - 1) return false;
      const x = (xs[i] + xs[i + 1]) / 2, y = (ys[j] + ys[j + 1]) / 2;
      return adds.some(r => inside(r, x, y)) && !subs.some(r => inside(r, x, y));
    };
    // Each covered cell's open sides, walked with the room on the right.
    const next = new Map();
    const add = (a, b) => { const k = a.join(); (next.get(k) || next.set(k, []).get(k)).push(b); };
    for (let i = 0; i < xs.length - 1; i++) for (let j = 0; j < ys.length - 1; j++) {
      if (!cov(i, j)) continue;
      if (!cov(i, j - 1)) add([i, j], [i + 1, j]);
      if (!cov(i + 1, j)) add([i + 1, j], [i + 1, j + 1]);
      if (!cov(i, j + 1)) add([i + 1, j + 1], [i, j + 1]);
      if (!cov(i - 1, j)) add([i, j + 1], [i, j]);
    }
    const loops = [];
    while (next.size) {
      const startKey = next.keys().next().value;
      const pts = [];
      let key = startKey;
      for (let guard = 0; guard < 10000; guard++) {
        const outs = next.get(key);
        if (!outs) break;
        const to = outs.pop();
        if (!outs.length) next.delete(key);
        const [i, j] = key.split(',').map(Number);
        pts.push([xs[i], ys[j]]);
        key = to.join();
        if (key === startKey) break;
      }
      loops.push(simplify(pts));
    }
    const outer = loops.filter(p => p.length >= 4 && area(p) > 0).sort((a, b) => area(b) - area(a));
    return { loops: outer, holes: loops.some(p => p.length >= 4 && area(p) < 0) };
  }

  // Drop corners that sit on a straight run.
  function simplify(pts) {
    const out = [];
    pts.forEach((p, k) => {
      const a = pts[(k - 1 + pts.length) % pts.length], b = pts[(k + 1) % pts.length];
      if (!((a[0] === p[0] && p[0] === b[0]) || (a[1] === p[1] && p[1] === b[1]))) out.push(p);
    });
    return out;
  }

  // Signed area; positive for an outline walked clockwise on screen.
  function area(pts) {
    let s = 0;
    pts.forEach((p, k) => { const n = pts[(k + 1) % pts.length]; s += p[0] * n[1] - n[0] * p[1]; });
    return s / 2;
  }

  // An outline cut into rectangles, band by band from the top: an L is two.
  function rectsOf(poly) {
    const ys = uniq(poly.map(p => p[1]));
    const rects = [], open = [];
    for (let k = 0; k < ys.length - 1; k++) {
      const ya = ys[k], yb = ys[k + 1], ym = (ya + yb) / 2;
      const cross = [];
      poly.forEach((p, i) => {
        const n = poly[(i + 1) % poly.length];
        if (p[0] === n[0] && Math.min(p[1], n[1]) < ym && ym < Math.max(p[1], n[1])) cross.push(p[0]);
      });
      cross.sort((a, b) => a - b);
      const bands = [];
      for (let i = 0; i + 1 < cross.length; i += 2) bands.push([cross[i], cross[i + 1]]);
      bands.forEach(([x0, x1]) => {
        const run = open.find(r => r[0] === x0 && r[0] + r[2] === x1 && r[1] + r[3] === ya);
        if (run) run[3] = yb - run[1];
        else { const r = [x0, ya, x1 - x0, yb - ya]; rects.push(r); open.push(r); }
      });
    }
    return rects;
  }

  const rectsOfRoom = room => room.polys.flatMap(rectsOf);

  function fromTrace(byLabel) {
    rooms = new Map();
    cards().forEach(card => {
      const label = card.dataset.uid;          // a card's uid is the name it loaded with
      if (byLabel[label]) {
        const { loops } = outlineOf(byLabel[label]);
        if (loops.length) rooms.set(card.dataset.uid, { from: label, polys: loops });
      }
    });
  }

  // ── Walls ──────────────────────────────────────────────────────────────────
  // A wall is one side of a room's outline: where it sits and what it spans.
  function edgeOf(uid, pi, k) {
    const pts = rooms.get(uid).polys[pi];
    const a = pts[k], b = pts[(k + 1) % pts.length];
    const vertical = a[0] === b[0];
    return { uid, pi, k, vertical, pos: vertical ? a[0] : a[1],
             span: vertical ? [Math.min(a[1], b[1]), Math.max(a[1], b[1])]
                            : [Math.min(a[0], b[0]), Math.max(a[0], b[0])] };
  }

  function allEdges() {
    const out = [];
    rooms.forEach((room, uid) => room.polys.forEach((pts, pi) =>
      pts.forEach((_p, k) => out.push(edgeOf(uid, pi, k)))));
    return out;
  }

  // The walls that are the same wall as this one: same line, overlapping span.
  function linkedTo(edge) {
    const near = 2.5 * unit();
    return allEdges().filter(e => e.vertical === edge.vertical
      && Math.abs(e.pos - edge.pos) <= near
      && e.span[0] < edge.span[1] - near && edge.span[0] < e.span[1] - near);
  }

  function setEdge(e, pos) {
    const pts = rooms.get(e.uid).polys[e.pi];
    const c = e.vertical ? 0 : 1;
    pts[e.k][c] = pos;
    pts[(e.k + 1) % pts.length][c] = pos;
  }

  // Where a set of walls may go: never past the corners either side of them.
  function limits(edges) {
    const least = 12 * unit();
    let lo = 0, hi = Infinity;
    edges.forEach(e => {
      const pts = rooms.get(e.uid).polys[e.pi];
      const c = e.vertical ? 0 : 1, n = pts.length;
      hi = Math.min(hi, e.vertical ? W : H);
      [pts[(e.k - 1 + n) % n], pts[(e.k + 2) % n]].forEach(p => {
        if (p[c] < e.pos) lo = Math.max(lo, p[c] + least);
        else hi = Math.min(hi, p[c] - least);
      });
    });
    return [lo, hi];
  }

  // Lines a wall or corner snaps to: the plan's own walls first, then other
  // rooms' walls and the flat's outline.
  // The room whose corners are being traced: hidden, and its old walls no
  // longer pull — you are drawing it afresh.
  const tracing = uid => !!marking && marking.mode === 'corners' && marking.uid === uid;

  function snapLines(vertical, except = []) {
    const lines = (vertical ? walls.x : walls.y).map(v => ({ at: v, wall: true }));
    allEdges().forEach(e => {
      if (tracing(e.uid)) return;
      if (e.vertical === vertical && !except.some(x => x.uid === e.uid && x.pi === e.pi && x.k === e.k)) {
        lines.push({ at: e.pos });
      }
    });
    outline.forEach(o => (vertical ? [o[0], o[0] + o[2]] : [o[1], o[1] + o[3]])
      .forEach(at => lines.push({ at })));
    return lines;
  }

  function snap(value, lines) {
    const reach = 9 * unit();
    let best = null;
    lines.forEach(l => {
      const gap = Math.abs(l.at - value);
      const score = gap - (l.wall ? reach * 0.35 : 0);           // walls pull harder
      if (gap <= reach && (!best || score < best.score)) best = { score, at: l.at };
    });
    return best ? best.at : null;
  }

  function snapPoint(x, y) {
    const sx = snap(x, snapLines(true)), sy = snap(y, snapLines(false));
    return { p: [sx ?? x, sy ?? y], sx, sy };
  }

  // ── Drawing ────────────────────────────────────────────────────────────────
  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  const pathOf = pts => 'M' + pts.map(p => p.join(' ')).join('L') + 'Z';

  function colourOf(uid) {
    const i = cards().findIndex(c => c.dataset.uid === uid);
    return cfg.colours[(i < 0 ? 0 : i) % cfg.colours.length];
  }

  function render(active) {
    svg.querySelectorAll('.pe-room, .pe-door, .pe-guide, .pe-marking').forEach(n => n.remove());
    const u = unit();
    const hot = new Set((active || []).map(e => `${e.uid}|${e.pi}|${e.k}`));

    rooms.forEach((room, uid) => {
      const name = nameOf(uid);
      if (!name || tracing(uid)) return;           // out of the way of its own corners
      const on = uid === selected;
      const g = el('g', {
        class: 'pe-room' + (on ? ' is-selected' : ''),
        'data-uid': uid, tabindex: 0, role: 'button',
        'aria-label': `${name}. Arrow keys push that side's wall out; with Shift they pull it in.`,
        'aria-pressed': String(on),
      }, svg);
      g.style.setProperty('--room', colourOf(uid));
      g.style.setProperty('--i', rooms.size ? [...rooms.keys()].indexOf(uid) : 0);

      room.polys.forEach(pts => el('path', { class: 'pe-part', d: pathOf(pts) }, g));

      // The name sits in the largest rectangle: one size on screen for every
      // room, smaller only where a name would not fit its room.
      const main = rectsOfRoom(room).reduce((a, b) => (b[2] * b[3] > a[2] * a[3] ? b : a));
      const size = Math.max(Math.min(12.5 * u, main[2] / (name.length * 0.58), main[3] * 0.45), 8 * u);
      el('text', { class: 'pe-name', x: main[0] + main[2] / 2, y: main[1] + main[3] / 2,
                   'font-size': size }, g).textContent = name;

      // Every wall is a handle: a thin visible line, a wide invisible grip.
      room.polys.forEach((pts, pi) => pts.forEach((_p, k) => {
        const a = pts[k], b = pts[(k + 1) % pts.length];
        const vertical = a[0] === b[0];
        const line = { x1: a[0], y1: a[1], x2: b[0], y2: b[1] };
        const isHot = hot.has(`${uid}|${pi}|${k}`);
        el('line', { ...line, class: 'pe-edge' + (isHot ? ' is-active' : ''),
                     'stroke-width': (isHot ? 3 : on ? 2 : 1.25) * u }, g);
        el('line', { ...line, class: 'pe-grip pe-grip--' + (vertical ? 'x' : 'y'),
                     'data-poly': pi, 'data-k': k, 'stroke-width': GRIP * u }, g);
      }));
    });

    doors.forEach((d, i) => drawDoor(d, i));

    renderTray();
    renderTools();
    write();
  }

  // A door: the gap in the wall, the leaf from its hinge, the arc it sweeps.
  function doorGeometry(d) {
    const w = doorPx, h = w / 2;
    const [a, b] = d.axis === 'h' ? [[d.x - h, d.y], [d.x + h, d.y]] : [[d.x, d.y - h], [d.x, d.y + h]];
    const [hinge, latch] = d.hinge === 'high' ? [b, a] : [a, b];
    const leaf = d.axis === 'h' ? [hinge[0], hinge[1] + d.dir * w] : [hinge[0] + d.dir * w, hinge[1]];
    return { a, b, hinge, latch, leaf, w };
  }

  function drawDoor(d, i) {
    const u = unit();
    const { a, b, hinge, latch, leaf, w } = doorGeometry(d);
    const on = i === selectedDoor;
    const g = el('g', { class: 'pe-door' + (on ? ' is-selected' : '') + (i === freshDoor ? ' is-fresh' : ''),
                        'data-door': i, tabindex: 0,
                        role: 'button', 'aria-pressed': String(on),
                        'aria-label': 'Door. Drag along its wall to move it; T turns it, Delete removes it.' }, svg);
    const cross = (latch[0] - hinge[0]) * (leaf[1] - hinge[1]) - (latch[1] - hinge[1]) * (leaf[0] - hinge[0]);
    const sweep = cross > 0 ? 1 : 0;
    // The floor the door sweeps, shaded, so a door reads at a glance.
    el('path', { class: 'pe-door__swing',
                 d: `M${hinge[0]} ${hinge[1]} L${latch[0]} ${latch[1]} A${w} ${w} 0 0 ${sweep} ${leaf[0]} ${leaf[1]}Z` }, g);
    if (i === freshDoor) {
      el('circle', { class: 'pe-door__halo', cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2, r: w,
                     'stroke-width': 3.5 * u }, g);
    }
    el('line', { class: 'pe-door__gap', x1: a[0], y1: a[1], x2: b[0], y2: b[1], 'stroke-width': 3.5 * u }, g);
    el('line', { class: 'pe-door__leaf', x1: hinge[0], y1: hinge[1], x2: leaf[0], y2: leaf[1],
                 'stroke-width': (on ? 3 : 1.8) * u }, g);
    el('path', { class: 'pe-door__arc', d: `M${latch[0]} ${latch[1]} A${w} ${w} 0 0 ${sweep} ${leaf[0]} ${leaf[1]}`,
                 'stroke-width': (on ? 1.6 : 1.1) * u, 'stroke-dasharray': `${3 * u} ${3 * u}` }, g);
    const xs = [a[0], b[0], leaf[0]], ys = [a[1], b[1], leaf[1]];
    const pad = 3 * u;
    el('rect', { class: 'pe-door__hit', x: Math.min(...xs) - pad, y: Math.min(...ys) - pad,
                 width: Math.max(...xs) - Math.min(...xs) + 2 * pad, height: Math.max(...ys) - Math.min(...ys) + 2 * pad }, g);
  }

  // The stretch of wall a door sits in: every room wall on its line through it.
  function doorRun(d) {
    const near = 3 * unit();
    const runs = allEdges().filter(e => e.vertical === (d.axis === 'v')
      && Math.abs(e.pos - (d.axis === 'v' ? d.x : d.y)) <= near);
    const along = d.axis === 'h' ? d.x : d.y;
    const hit = runs.filter(e => e.span[0] - near <= along && along <= e.span[1] + near);
    if (!hit.length) return null;
    return [Math.min(...hit.map(e => e.span[0])), Math.max(...hit.map(e => e.span[1]))];
  }

  function renderTray() {
    const unplaced = cards().filter(c => !rooms.has(c.dataset.uid));
    tray.hidden = !unplaced.length || cfg.status === 'pending';
    const list = tray.querySelector('.pe-tray__list');
    list.textContent = '';
    unplaced.forEach(card => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'pe-chip' + (marking && marking.uid === card.dataset.uid ? ' is-on' : '');
      b.textContent = labelOf(card);
      b.setAttribute('aria-label', 'Mark out ' + labelOf(card) + ' on the plan');
      b.addEventListener('click', () => startMarking(card.dataset.uid, 'corners'));
      list.appendChild(b);
    });
  }

  function renderTools() {
    const room = selected && rooms.get(selected);
    tools.hidden = !room || !!marking || selectedDoor >= 0;
    doorTools.hidden = selectedDoor < 0 || !!marking;
    if (room) tools.querySelector('.pe-tools__name').textContent = nameOf(selected);
  }

  function say(text, action) {
    status.textContent = text;
    if (action) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'pe-link';
      b.textContent = action.label;
      b.addEventListener('click', action.run);
      status.append(' ', b);
    }
  }

  // ── What goes to the server ────────────────────────────────────────────────
  function write() {
    if (cfg.status === 'pending' && !touched) { input.value = ''; return; }
    const out = { rooms: {}, from: {} };
    rooms.forEach((room, uid) => {
      const name = nameOf(uid);
      if (!name) return;
      out.rooms[name] = rectsOfRoom(room).map(r => r.map(round));
      if (room.from) out.from[name] = room.from;
    });
    out.doors = doors.map(d => ({ x: round(d.x), y: round(d.y), axis: d.axis, dir: d.dir, hinge: d.hinge }));
    input.value = JSON.stringify(out);
  }

  // Autosave listens for input on the form.
  function changed(message) {
    touched = true;
    write();
    input.dispatchEvent(new Event('input', { bubbles: true }));
    if (message) live.textContent = message;
    resetBtn.hidden = !Object.keys(detected).length;
  }

  // A room's new outline, if it is one the rest of FORMA can use: in one
  // piece, no holes, a few rectangles at most.
  function accept(uid, loops, holes, what) {
    if (holes || loops.length !== 1) {
      say(`That would leave ${nameOf(uid)} in pieces. ${what}`);
      return false;
    }
    if (rectsOf(loops[0]).length > MAX_PARTS) {
      say(`That shape is too intricate. Keep ${nameOf(uid)} to a rectangle, an L or a T.`);
      return false;
    }
    const room = rooms.get(uid);
    rooms.set(uid, { from: room ? room.from : null, polys: loops });
    return true;
  }

  // ── Selecting ──────────────────────────────────────────────────────────────
  function select(uid, fromList) {
    selected = uid;
    selectedDoor = -1;
    render();
    if (uid && !fromList) acc.dispatchEvent(new CustomEvent('plan:select', { detail: { uid } }));
  }

  // ── Marking out ────────────────────────────────────────────────────────────
  const PROMPTS = {
    corners: n => `Click each corner of ${n} in turn, then click the first corner again to close it.`,
    door:    n => `Click the wall of ${n} where the door is.`,
  };

  function startMarking(uid, mode) {
    marking = { uid, mode, pts: [] };
    root.classList.add('is-marking');
    root.classList.toggle('is-tracing', mode === 'corners');
    say(PROMPTS[mode](nameOf(uid)) + ' Esc to cancel.');
    render();
  }

  function stopMarking(message) {
    marking = null;
    root.classList.remove('is-marking', 'is-tracing');
    say(message || hint);
    render();
  }

  function finishMarking(uid, verb) {
    selected = uid;
    stopMarking();
    const node = svg.querySelector(q(uid));
    if (node && !calm) node.classList.add('is-arriving');
    changed(`${nameOf(uid)} ${verb}.`);
  }

  // Corners mode: each new corner squares up with the last one, so every wall
  // runs straight across or straight down.
  function squared(pts, p) {
    if (!pts.length) return p;
    const last = pts[pts.length - 1];
    return Math.abs(p[0] - last[0]) >= Math.abs(p[1] - last[1]) ? [p[0], last[1]] : [last[0], p[1]];
  }

  function closeCorners() {
    const uid = marking.uid;
    let pts = marking.pts.slice();
    if (pts.length < 3) { say(`Click at least three corners of ${nameOf(uid)}.`); return; }
    // Square up the way back to the first corner.
    const first = pts[0], last = pts[pts.length - 1];
    if (first[0] !== last[0] && first[1] !== last[1]) {
      const prevVertical = pts[pts.length - 2][0] === last[0];
      pts.push(prevVertical ? [first[0], last[1]] : [last[0], first[1]]);
    }
    // Rebuild from the cells it covers: fixes the direction it was drawn in
    // and any corner clicked on a straight run.
    let poly = simplify(pts);
    if (area(poly) < 0) poly = poly.reverse();
    const rects = rectsOf(poly);
    if (!rects.length) {
      say(`That outline crosses itself. Try ${nameOf(uid)} again.`);
      marking.pts = []; render(); return;
    }
    const { loops, holes } = outlineOf(rects);
    if (!accept(uid, loops, holes, 'Try again, clicking the corners in order round the room.')) {
      marking.pts = []; render(); return;
    }
    finishMarking(uid, 'marked out');
  }

  // ── Pointer ────────────────────────────────────────────────────────────────
  function point(e) {
    const m = svg.getScreenCTM().inverse();
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
    return [clamp(p.x, 0, W), clamp(p.y, 0, H)];
  }

  function guide(vertical, at) {
    const [vx, vy, vw, vh] = view;
    el('line', vertical ? { class: 'pe-guide', x1: at, y1: vy, x2: at, y2: vy + vh, 'stroke-width': 1.5 * unit() }
                        : { class: 'pe-guide', x1: vx, y1: at, x2: vx + vw, y2: at, 'stroke-width': 1.5 * unit() }, svg);
  }

  let drag = null;

  function drawMarking(hover) {
    render();
    const u = unit();
    if (marking.mode === 'corners') {
      const pts = marking.pts.slice();
      if (hover) pts.push(squared(pts, hover.p));
      if (pts.length > 1) {
        el('path', { class: 'pe-marking pe-marking--line', d: 'M' + pts.map(p => p.join(' ')).join('L'),
                     'stroke-width': 2 * u }, svg);
      }
      marking.pts.forEach((p, i) => {
        const first = i === 0 && marking.pts.length > 2;
        el('circle', { class: 'pe-marking pe-corner' + (first ? ' is-first' : ''),
                       cx: p[0], cy: p[1], r: (first ? 6 : 3.5) * u }, svg);
      });
    }
    if (hover && hover.sx !== null) guide(true, hover.sx);
    if (hover && hover.sy !== null) guide(false, hover.sy);
  }

  svg.addEventListener('pointerdown', e => {
    if (marking && marking.mode === 'door') {
      placeDoor(marking.uid, point(e));
      e.preventDefault();
      return;
    }
    const doorNode = !marking && e.target.closest('.pe-door');
    if (doorNode) {
      const i = Number(doorNode.dataset.door);
      selectedDoor = i;
      selected = null;
      drag = { kind: 'door', i, start: point(e), orig: { ...doors[i] }, moved: false };
      render();
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    if (marking) {
      const hit = snapPoint(...point(e));
      if (marking.mode === 'corners') {
        const first = marking.pts[0];
        if (first && marking.pts.length > 2
            && Math.hypot(hit.p[0] - first[0], hit.p[1] - first[1]) < 10 * unit()) {
          closeCorners();
        } else {
          marking.pts.push(squared(marking.pts, hit.p));
          drawMarking(hit);
        }
        e.preventDefault();
        return;
      }
      return;
    }
    const group = e.target.closest('.pe-room');
    if (!group) { selectedDoor = -1; select(null); return; }
    const uid = group.dataset.uid;
    if (!e.target.classList.contains('pe-grip')) { if (uid !== selected) select(uid); return; }

    // Grabbing a wall: it and every wall on the same line move together;
    // Alt takes this room's wall alone.
    const edge = edgeOf(uid, Number(e.target.dataset.poly), Number(e.target.dataset.k));
    const edges = e.altKey ? [edge] : linkedTo(edge);
    drag = { kind: 'edge', uid, edge, edges, start: point(e), pos0: edge.pos,
             lines: snapLines(edge.vertical, edges), moved: false,
             orig: new Map(Array.from(rooms, ([k, r]) => [k, r.polys.map(p => p.map(v => v.slice()))])),
             origDoors: doors.map(d => ({ ...d })) };
    selected = uid;
    render(edges);
    svg.setPointerCapture(e.pointerId);     // the svg: every redraw replaces the room's nodes
    e.preventDefault();
  });

  svg.addEventListener('pointermove', e => {
    if (marking && !drag) {
      if (marking.mode === 'corners') drawMarking(snapPoint(...point(e)));
      return;
    }
    if (!drag) return;
    const [px, py] = point(e);

    if (drag.kind === 'door') {
      const d = doors[drag.i], o = drag.orig;
      const shift = o.axis === 'h' ? px - drag.start[0] : py - drag.start[1];
      if (!drag.moved && Math.abs(shift) < 3 * unit()) return;
      drag.moved = true;
      const run = doorRun(o) || [0, o.axis === 'h' ? W : H];
      const half = doorPx / 2;
      const along = clamp((o.axis === 'h' ? o.x : o.y) + shift, run[0] + half, Math.max(run[0] + half, run[1] - half));
      if (o.axis === 'h') d.x = along; else d.y = along;
      render();
      return;
    }

    const delta = drag.edge.vertical ? px - drag.start[0] : py - drag.start[1];
    if (!drag.moved && Math.abs(delta) < 3 * unit()) return;
    drag.moved = true;
    // Back to where the drag began, then the wall to its new line.
    drag.orig.forEach((polys, k) => {
      if (rooms.has(k)) rooms.get(k).polys = polys.map(p => p.map(v => v.slice()));
    });
    let pos = drag.pos0 + delta;
    const snapped = snap(pos, drag.lines);
    if (snapped !== null) pos = snapped;
    const [lo, hi] = limits(drag.edges);
    pos = clamp(pos, lo, hi);
    drag.edges.forEach(e2 => setEdge(e2, pos));
    // Doors in the wall ride with it.
    const near = 2.5 * unit();
    doors = drag.origDoors.map(d => {
      const inWall = (d.axis === 'v') === drag.edge.vertical
        && Math.abs((d.axis === 'v' ? d.x : d.y) - drag.pos0) <= near
        && drag.edges.some(e2 => { const a = d.axis === 'h' ? d.x : d.y; return a >= e2.span[0] - near && a <= e2.span[1] + near; });
      return inWall ? { ...d, [d.axis === 'v' ? 'x' : 'y']: pos } : { ...d };
    });
    render(drag.edges);
    if (snapped !== null && snapped === pos) guide(drag.edge.vertical, pos);
  });

  function endDrag() {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (d.kind === 'door') {
      render();
      if (d.moved) changed('Door moved.');
      refocusDoor(d.i);
      return;
    }
    if (d.moved) {
      // A wall pushed flush with the next one merges into one straight run.
      d.edges.forEach(e2 => { const r = rooms.get(e2.uid); r.polys = r.polys.map(simplify); });
      const others = new Set(d.edges.map(e2 => e2.uid));
      render();
      changed(`${nameOf(d.uid)}'s wall moved` + (others.size > 1 ? ', with the room next to it.' : '.'));
    } else {
      render();
    }
  }
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', () => { drag = null; render(); });

  // ── Keyboard ───────────────────────────────────────────────────────────────
  document.addEventListener('keydown', e => {
    if (!marking) {
      if (e.key === 'Escape' && selectedDoor >= 0) { selectedDoor = -1; render(); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); stopMarking(); }
    if (e.key === 'Enter' && marking.mode === 'corners') { e.preventDefault(); closeCorners(); }
    if (e.key === 'Backspace' && marking.mode === 'corners' && marking.pts.length) {
      e.preventDefault(); marking.pts.pop(); drawMarking();
    }
  });

  svg.addEventListener('keydown', e => {
    const node = e.target.closest && e.target.closest('.pe-door');
    if (!node || marking) return;
    const i = Number(node.dataset.door);
    const d = doors[i];
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectedDoor = i; selected = null; render(); refocusDoor(i); }
    else if (e.key.toLowerCase() === 't') { e.preventDefault(); doorAction('turn', i); }
    else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); doorAction('remove', i); }
    else if (e.key.startsWith('Arrow')) {
      e.preventDefault();
      const step = doorPx * 0.25 * (e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 1);
      const run = doorRun(d) || [0, d.axis === 'h' ? W : H];
      const half = doorPx / 2;
      if (d.axis === 'h') d.x = clamp(d.x + step, run[0] + half, Math.max(run[0] + half, run[1] - half));
      else d.y = clamp(d.y + step, run[0] + half, Math.max(run[0] + half, run[1] - half));
      selectedDoor = i;
      render(); refocusDoor(i); changed('Door moved.');
    }
    e.stopImmediatePropagation();
  });

  function refocusDoor(i) {
    const node = svg.querySelector(`.pe-door[data-door="${i}"]`);
    if (node) node.focus({ preventScroll: true });
  }

  function doorAction(what, i = selectedDoor) {
    const d = doors[i];
    if (!d) return;
    if (what === 'turn') {
      // The four ways a door can hang in its gap, one after another: hinge to
      // the other end, then swinging to the other side, and round again.
      if (d.hinge === 'low') d.hinge = 'high';
      else { d.hinge = 'low'; d.dir = -d.dir; }
      changed('Door turned.');
    }
    if (what === 'remove') {
      doors.splice(i, 1);
      selectedDoor = -1;
      render();
      changed('Door removed.');
      return;
    }
    selectedDoor = i;
    render();
    refocusDoor(i);
  }

  doorTools.addEventListener('click', e => {
    const b = e.target.closest('[data-door-tool]');
    if (b) doorAction(b.dataset.doorTool);
  });

  // A new door on the wall of a room nearest the click, swinging into it.
  function placeDoor(uid, [x, y]) {
    const room = rooms.get(uid);
    let best = null;
    room.polys.forEach((pts, pi) => pts.forEach((_p, k) => {
      const e = edgeOf(uid, pi, k);
      const along = clamp(e.vertical ? y : x, e.span[0], e.span[1]);
      const gap = Math.abs((e.vertical ? x : y) - e.pos);
      if (e.span[1] - e.span[0] >= doorPx && (!best || gap < best.gap)) best = { e, along, gap };
    }));
    if (!best || best.gap > 20 * unit()) {
      say(`Click on one of ${nameOf(uid)}'s walls — its outline — where the door is.`);
      return;
    }
    const { e } = best;
    const half = doorPx / 2;
    const along = clamp(best.along, e.span[0] + half, e.span[1] - half);
    // Which side of the wall the room is on: test just off it both ways.
    const probe = side => {
      const px = e.vertical ? e.pos + side * 2 : along, py = e.vertical ? along : e.pos + side * 2;
      return rectsOfRoom(room).some(r => px > r[0] && px < r[0] + r[2] && py > r[1] && py < r[1] + r[3]);
    };
    const d = e.vertical ? { x: e.pos, y: along, axis: 'v' } : { x: along, y: e.pos, axis: 'h' };
    doors.push({ ...d, dir: probe(1) ? 1 : -1, hinge: 'low' });
    selectedDoor = doors.length - 1;
    // Shown off once, so it is clear where it landed.
    freshDoor = selectedDoor;
    setTimeout(() => { freshDoor = -1; }, calm ? 0 : 1100);
    selected = null;
    stopMarking();
    refocusDoor(selectedDoor);
    changed(`Door added to ${nameOf(uid)}. Use Turn below if it hangs the other way.`);
  }

  // Arrow keys push the wall on that side out; with Shift they pull it in.
  // The wall moves with any room sharing it, as when dragged.
  svg.addEventListener('keydown', e => {
    if (marking) return;
    const group = e.target.closest && e.target.closest('.pe-room');
    if (!group) return;
    const uid = group.dataset.uid;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(uid); refocus(uid); return; }
    if (e.key === 'Escape') { select(null); return; }
    const sides = { ArrowLeft: ['x', -1], ArrowRight: ['x', 1], ArrowUp: ['y', -1], ArrowDown: ['y', 1] };
    if (!sides[e.key]) return;
    e.preventDefault();
    selected = uid;
    const [axis, outward] = sides[e.key];
    // The wall furthest out on that side.
    let edge = null;
    rooms.get(uid).polys.forEach((pts, pi) => pts.forEach((_p, k) => {
      const ed = edgeOf(uid, pi, k);
      if (ed.vertical !== (axis === 'x')) return;
      if (!edge || (outward > 0 ? ed.pos > edge.pos : ed.pos < edge.pos)) edge = ed;
    }));
    const edges = e.altKey ? [edge] : linkedTo(edge);
    const step = Math.max(W, H) * 0.005 * (e.shiftKey ? -outward : outward);
    const [lo, hi] = limits(edges);
    edges.forEach(e2 => setEdge(e2, clamp(edge.pos + step, lo, hi)));
    render(edges);
    refocus(uid);
    changed(`${nameOf(uid)}: wall moved.`);
  });

  function refocus(uid) {
    const node = svg.querySelector(q(uid));
    if (node) node.focus({ preventScroll: true });
  }

  // ── Tools for the selected room ────────────────────────────────────────────
  tools.addEventListener('click', e => {
    const b = e.target.closest('[data-tool]');
    if (!b || !selected) return;
    if (b.dataset.tool === 'corners') startMarking(selected, 'corners');
    if (b.dataset.tool === 'door') startMarking(selected, 'door');
  });

  // ── The room list ──────────────────────────────────────────────────────────
  acc.addEventListener('rooms:change', e => {
    const { type, card } = e.detail;
    if (type === 'remove') {
      rooms.delete(card.dataset.uid);
      if (selected === card.dataset.uid) selected = null;
      if (marking && marking.uid === card.dataset.uid) stopMarking();
      changed();
    }
    if (type === 'open') {
      if (rooms.has(card.dataset.uid) && !marking) { selected = card.dataset.uid; render(); }
      return;
    }
    render();                // renames and additions redraw names and the tray
    if (type === 'rename') changed();
  });

  resetBtn.addEventListener('click', () => {
    if (marking) stopMarking();
    fromTrace(detected);
    doors = detectedDoors.map(d => ({ ...d }));
    selected = null;
    selectedDoor = -1;
    render();
    changed('Rooms and doors put back where FORMA found them.');
    resetBtn.hidden = true;
  });

  // Grips and snapping follow the plan's size on screen.
  if ('ResizeObserver' in window) {
    new ResizeObserver(() => { if (!drag && !marking) render(); }).observe(svg);
  }

  // ── Start ──────────────────────────────────────────────────────────────────
  function ready(byLabel, lines, found, px) {
    const arriving = cfg.status === 'pending';        // found just now, not on load
    detected = byLabel;
    if (lines && lines.length) outline = lines;
    if (px) doorPx = px;
    if (found && !touched) {
      doors = found.map(d => ({ ...d }));
      detectedDoors = found.map(d => ({ ...d }));
    }
    cfg.status = 'ready';
    root.dataset.status = 'ready';
    if (!touched) fromTrace(byLabel);
    hint = rooms.size
      ? 'Check each room’s walls line up with the plan. Drag a wall to move it; rooms that share it move too.'
      : 'FORMA could not match your rooms on the plan. Mark each one out below.';
    say(hint);
    render();
    if (arriving && !calm) {
      // The rooms settle onto the plan one after another as FORMA finds them.
      svg.classList.add('is-settling');
      setTimeout(() => svg.classList.remove('is-settling'), 400 + rooms.size * 70);
    }
  }

  function trace() {
    cfg.status = 'pending';
    root.dataset.status = 'pending';
    say('Finding your rooms on the plan… Fill in the rooms below meanwhile.');
    render();
    fetch(cfg.trace_url, { method: 'POST', headers: { Accept: 'application/json' } })
      .then(r => r.json())
      .then(d => {
        if (!d.ok) throw new Error('trace failed');
        ready(d.rooms || {}, d.outline, d.doors, d.door_px);
      })
      .catch(failed);
  }

  function failed() {
    cfg.status = 'failed';
    root.dataset.status = 'failed';
    hint = 'We couldn’t find your rooms automatically. Mark them out yourself, or leave it — FORMA will try again at the end.';
    say(hint, { label: 'Try again', run: trace });
    render();
  }

  if (cfg.status === 'ready') ready(cfg.rooms, cfg.outline, cfg.doors, cfg.door_px);
  else if (cfg.status === 'failed') failed();
  else trace();

  document.querySelector('form[data-autosave]').addEventListener('submit', write);
})();
