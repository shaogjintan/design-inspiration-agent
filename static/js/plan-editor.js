/* FORMA — page 2's plan editor: the rooms placed on the floor plan, for the
   homeowner to confirm by their edges before anything is drawn from them.

   A room is confirmed by its walls: every edge is a handle, and dragging one
   moves the wall — together with the edge of any room on the other side of
   it, so shared walls stay shared. A room the trace did not find is marked out
   corner to corner. Edges snap to the walls found in the plan image itself.

   Rooms are keyed by the room card they belong to (data-uid), not by name, so
   renaming a room in the list keeps its place. Everything is in plan-image
   pixels, the units of the server's trace. The result goes into the hidden
   "plan_edit" input, which autosave and submit carry to the server. */
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
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const GRIP = matchMedia('(pointer: coarse)').matches ? 26 : 12;   // a finger needs more
  const walls = cfg.walls || { x: [], y: [] };

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

  // uid -> { from: the name it was traced under (or null), parts: [[x, y, w, h]] }
  let rooms = new Map();
  let detected = {};            // the trace as it came back, for Reset
  let outline = cfg.outline || [];
  let selected = null;
  let marking = null;           // { uid, mode: 'new' | 'redraw' | 'extend' } while marking out
  let touched = false;
  let hint = '';

  const SIDES = ['left', 'right', 'top', 'bottom'];
  const cards = () => Array.from(acc.querySelectorAll('.accordion-item'));
  const labelOf = card => card.querySelector('input[name="kept_rooms"]').value;
  const cardOf = uid => cards().find(c => c.dataset.uid === uid);
  const nameOf = uid => { const c = cardOf(uid); return c ? labelOf(c) : ''; };
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const round = v => Math.round(v * 10) / 10;
  const q = uid => `.pe-room[data-uid="${CSS.escape(uid)}"]`;

  // One screen pixel in plan pixels, so handles and snapping feel the same
  // size whatever the plan's resolution.
  function unit() {
    const m = svg.getScreenCTM();
    return m && m.a ? 1 / m.a : 1;
  }

  function fromTrace(byLabel) {
    rooms = new Map();
    cards().forEach(card => {
      const label = card.dataset.uid;          // a card's uid is the name it loaded with
      if (byLabel[label]) {
        rooms.set(card.dataset.uid, { from: label, parts: byLabel[label].map(p => p.slice()) });
      }
    });
  }

  // ── Edges ──────────────────────────────────────────────────────────────────
  // An edge: which room and part, which side, where it sits and what it spans.
  function edgeOf(uid, part, side) {
    const [x, y, w, h] = rooms.get(uid).parts[part];
    const vertical = side === 'left' || side === 'right';
    const pos = side === 'left' ? x : side === 'right' ? x + w : side === 'top' ? y : y + h;
    const span = vertical ? [y, y + h] : [x, x + w];
    return { uid, part, side, vertical, pos, span };
  }

  function allEdges() {
    const out = [];
    rooms.forEach((room, uid) => room.parts.forEach((_p, i) =>
      SIDES.forEach(side => out.push(edgeOf(uid, i, side)))));
    return out;
  }

  // The edges that are the same wall as this one: same line, overlapping span.
  function linkedTo(edge) {
    const near = 2.5 * unit();
    return allEdges().filter(e => e.vertical === edge.vertical
      && Math.abs(e.pos - edge.pos) <= near
      && e.span[0] < edge.span[1] - near && edge.span[0] < e.span[1] - near);
  }

  function setEdge(e, pos) {
    const p = rooms.get(e.uid).parts[e.part];
    if (e.side === 'left')  { p[2] += p[0] - pos; p[0] = pos; }
    if (e.side === 'right') { p[2] = pos - p[0]; }
    if (e.side === 'top')   { p[3] += p[1] - pos; p[1] = pos; }
    if (e.side === 'bottom'){ p[3] = pos - p[1]; }
  }

  // Where a set of edges may go without turning any part inside out.
  function limits(edges) {
    const least = 14 * unit();
    let lo = 0, hi = Infinity;
    edges.forEach(e => {
      const [x, y, w, h] = rooms.get(e.uid).parts[e.part];
      const max = e.vertical ? W : H;
      hi = Math.min(hi, max);
      if (e.side === 'left')   hi = Math.min(hi, x + w - least);
      if (e.side === 'right')  lo = Math.max(lo, x + least);
      if (e.side === 'top')    hi = Math.min(hi, y + h - least);
      if (e.side === 'bottom') lo = Math.max(lo, y + least);
    });
    return [lo, hi];
  }

  // Lines an edge snaps to: the plan's own walls first, then other rooms'
  // edges and the flat's outline.
  function snapTo(vertical, except) {
    const lines = (vertical ? walls.x : walls.y).map(v => ({ at: v, wall: true }));
    rooms.forEach((room, uid) => room.parts.forEach((p, i) => {
      if (except.some(e => e.uid === uid && e.part === i)) return;
      (vertical ? [p[0], p[0] + p[2]] : [p[1], p[1] + p[3]]).forEach(at => lines.push({ at }));
    }));
    outline.forEach(o => (vertical ? [o[0], o[0] + o[2]] : [o[1], o[1] + o[3]])
      .forEach(at => lines.push({ at })));
    return lines;
  }

  function snap(value, lines) {
    const reach = 9 * unit();
    let best = null;
    lines.forEach(l => {
      const d = Math.abs(l.at - value) - (l.wall ? reach * 0.35 : 0);   // walls pull harder
      if (Math.abs(l.at - value) <= reach && (!best || d < best.d)) best = { d, at: l.at };
    });
    return best ? best.at : null;
  }

  // ── Drawing ────────────────────────────────────────────────────────────────
  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function colourOf(uid) {
    const i = cards().findIndex(c => c.dataset.uid === uid);
    return cfg.colours[(i < 0 ? 0 : i) % cfg.colours.length];
  }

  function render(active) {
    svg.querySelectorAll('.pe-room, .pe-guide, .pe-marking').forEach(n => n.remove());
    const u = unit();
    const activeKeys = new Set((active || []).map(e => `${e.uid}|${e.part}|${e.side}`));

    rooms.forEach((room, uid) => {
      const name = nameOf(uid);
      if (!name) return;
      const on = uid === selected;
      const g = el('g', {
        class: 'pe-room' + (on ? ' is-selected' : ''),
        'data-uid': uid, tabindex: 0, role: 'button',
        'aria-label': `${name}. Arrow keys push that side's wall out; with Shift they pull it in.`,
        'aria-pressed': String(on),
      }, svg);
      g.style.setProperty('--room', colourOf(uid));

      room.parts.forEach((p, i) => {
        el('rect', { class: 'pe-part', x: p[0], y: p[1], width: p[2], height: p[3] }, g);
      });

      // The name sits in the largest part: one size on screen for every room,
      // smaller only where a name would not fit its room.
      const main = room.parts.reduce((a, b) => (b[2] * b[3] > a[2] * a[3] ? b : a));
      const size = Math.max(Math.min(12.5 * u, main[2] / (name.length * 0.58), main[3] * 0.45), 8 * u);
      el('text', { class: 'pe-name', x: main[0] + main[2] / 2, y: main[1] + main[3] / 2,
                   'font-size': size }, g).textContent = name;

      // Every edge is a wall to drag: a thin visible line, a wide invisible grip.
      room.parts.forEach((p, i) => SIDES.forEach(side => {
        const e = edgeOf(uid, i, side);
        const pts = e.vertical ? { x1: e.pos, x2: e.pos, y1: e.span[0], y2: e.span[1] }
                               : { x1: e.span[0], x2: e.span[1], y1: e.pos, y2: e.pos };
        const hot = activeKeys.has(`${uid}|${i}|${side}`);
        el('line', { ...pts, class: 'pe-edge' + (hot ? ' is-active' : ''),
                     'stroke-width': (hot ? 3 : on ? 2 : 1.25) * u }, g);
        el('line', { ...pts, class: 'pe-grip pe-grip--' + (e.vertical ? 'x' : 'y'),
                     'data-part': i, 'data-side': side, 'stroke-width': GRIP * u }, g);
      }));
    });

    renderTray();
    renderTools();
    write();
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
      b.addEventListener('click', () => startMarking(card.dataset.uid, 'new'));
      list.appendChild(b);
    });
  }

  function renderTools() {
    const room = selected && rooms.get(selected);
    tools.hidden = !room || !!marking;
    if (!room) return;
    tools.querySelector('.pe-tools__name').textContent = nameOf(selected);
    tools.querySelector('[data-tool="extend"]').hidden = room.parts.length >= 3;
  }

  function say(text) {
    status.textContent = text;
  }

  // ── What goes to the server ────────────────────────────────────────────────
  function write() {
    if (cfg.status === 'pending' && !touched) { input.value = ''; return; }
    const out = { rooms: {}, from: {} };
    rooms.forEach((room, uid) => {
      const name = nameOf(uid);
      if (!name) return;
      out.rooms[name] = room.parts.map(p => p.map(round));
      if (room.from) out.from[name] = room.from;
    });
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

  // ── Selecting ──────────────────────────────────────────────────────────────
  function select(uid, fromList) {
    selected = uid;
    render();
    if (uid && !fromList) acc.dispatchEvent(new CustomEvent('plan:select', { detail: { uid } }));
  }

  // ── Marking a room out, corner to corner ───────────────────────────────────
  function startMarking(uid, mode) {
    marking = { uid, mode };
    root.classList.add('is-marking');
    say(`Drag from one corner of ${nameOf(uid)} to the opposite corner, along its walls. Esc to cancel.`);
    render();
  }

  function stopMarking(message) {
    marking = null;
    root.classList.remove('is-marking');
    say(message || hint);
    render();
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

  svg.addEventListener('pointerdown', e => {
    // Marking out: the drag draws the room.
    if (marking) {
      const [x, y] = point(e);
      const sx = snap(x, snapTo(true, [])), sy = snap(y, snapTo(false, []));
      drag = { kind: 'mark', from: [sx ?? x, sy ?? y], to: [sx ?? x, sy ?? y] };
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    const group = e.target.closest('.pe-room');
    if (!group) { select(null); return; }
    const uid = group.dataset.uid;
    const side = e.target.dataset && e.target.dataset.side;
    if (!side) { if (uid !== selected) select(uid); return; }

    // Grabbing a wall: it and every edge on the same wall move together;
    // Alt takes this room's edge alone.
    const edge = edgeOf(uid, Number(e.target.dataset.part), side);
    const edges = e.altKey ? [edge] : linkedTo(edge);
    drag = { kind: 'edge', uid, edge, edges, start: point(e), pos0: edge.pos,
             lines: snapTo(edge.vertical, edges), moved: false,
             orig: new Map(Array.from(rooms, ([k, r]) => [k, r.parts.map(p => p.slice())])) };
    if (uid !== selected) { selected = uid; }
    render(edges);
    svg.setPointerCapture(e.pointerId);     // the svg: every redraw replaces the room's nodes
    e.preventDefault();
  });

  svg.addEventListener('pointermove', e => {
    if (!drag) return;
    const [px, py] = point(e);

    if (drag.kind === 'mark') {
      const sx = snap(px, snapTo(true, [])), sy = snap(py, snapTo(false, []));
      drag.to = [sx ?? px, sy ?? py];
      render();
      const [x0, y0] = drag.from, [x1, y1] = drag.to;
      el('rect', { class: 'pe-marking', x: Math.min(x0, x1), y: Math.min(y0, y1),
                   width: Math.abs(x1 - x0), height: Math.abs(y1 - y0),
                   'stroke-width': 2 * unit() }, svg);
      if (sx !== null) guide(true, sx);
      if (sy !== null) guide(false, sy);
      return;
    }

    const delta = drag.edge.vertical ? px - drag.start[0] : py - drag.start[1];
    if (!drag.moved && Math.abs(delta) < 3 * unit()) return;
    drag.moved = true;
    // Back to where the drag began, then the wall to its new line.
    drag.orig.forEach((parts, k) => { if (rooms.has(k)) rooms.get(k).parts = parts.map(p => p.slice()); });
    let pos = drag.pos0 + delta;
    const snapped = snap(pos, drag.lines);
    if (snapped !== null) pos = snapped;
    const [lo, hi] = limits(drag.edges);
    pos = clamp(pos, lo, hi);
    drag.edges.forEach(e2 => setEdge(e2, pos));
    render(drag.edges.map(e2 => edgeOf(e2.uid, e2.part, e2.side)));
    if (snapped !== null && snapped === pos) guide(drag.edge.vertical, pos);
  });

  function endDrag() {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (d.kind === 'mark') {
      const [x0, y0] = d.from, [x1, y1] = d.to;
      const box = [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)];
      const uid = marking.uid, mode = marking.mode;
      if (box[2] < 14 * unit() || box[3] < 14 * unit()) {
        render();
        say(`Drag across the whole of ${nameOf(uid)}, from one corner to the opposite one.`);
        return;
      }
      const room = rooms.get(uid);
      if (mode === 'extend' && room) room.parts.push(box);
      else rooms.set(uid, { from: room ? room.from : null, parts: [box] });
      selected = uid;
      stopMarking();
      const node = svg.querySelector(q(uid));
      if (node && !calm) node.classList.add('is-arriving');
      changed(`${nameOf(uid)} marked out.`);
      return;
    }
    render();
    if (d.moved) {
      const others = new Set(d.edges.map(e2 => e2.uid));
      changed(`${nameOf(d.uid)}'s wall moved` + (others.size > 1 ? ', with the room next to it.' : '.'));
    }
  }
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', () => { drag = null; render(); });

  // ── Keyboard ───────────────────────────────────────────────────────────────
  // Arrow keys push the wall on that side out; with Shift they pull it in.
  // The wall moves with any room sharing it, as when dragged.
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && marking) { e.preventDefault(); stopMarking(); }
  });

  svg.addEventListener('keydown', e => {
    const group = e.target.closest && e.target.closest('.pe-room');
    if (!group) return;
    const uid = group.dataset.uid;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(uid); refocus(uid); return; }
    if (e.key === 'Escape') { select(null); return; }
    const sides = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'top', ArrowDown: 'bottom' };
    const side = sides[e.key];
    if (!side) return;
    e.preventDefault();
    selected = uid;
    const room = rooms.get(uid);
    // The part whose edge is furthest out on that side.
    const pick = room.parts.reduce((best, p, i) => {
      const at = edgeOf(uid, i, side).pos;
      const better = side === 'left' || side === 'top' ? at < best.at : at > best.at;
      return best.i < 0 || better ? { i, at } : best;
    }, { i: -1, at: 0 });
    const edge = edgeOf(uid, pick.i, side);
    const edges = e.altKey ? [edge] : linkedTo(edge);
    const outward = side === 'left' || side === 'top' ? -1 : 1;
    const step = Math.max(W, H) * 0.005 * (e.shiftKey ? -outward : outward);
    const [lo, hi] = limits(edges);
    const pos = clamp(edge.pos + step, lo, hi);
    edges.forEach(e2 => setEdge(e2, pos));
    render(edges.map(e2 => edgeOf(e2.uid, e2.part, e2.side)));
    refocus(uid);
    changed(`${nameOf(uid)}: ${side} wall moved.`);
  });

  function refocus(uid) {
    const node = svg.querySelector(q(uid));
    if (node) node.focus({ preventScroll: true });
  }

  // ── Tools for the selected room ────────────────────────────────────────────
  tools.addEventListener('click', e => {
    const b = e.target.closest('[data-tool]');
    if (!b || !selected) return;
    if (b.dataset.tool === 'redraw') startMarking(selected, 'redraw');
    if (b.dataset.tool === 'extend') startMarking(selected, 'extend');
    if (b.dataset.tool === 'remove') {
      const name = nameOf(selected);
      rooms.delete(selected);
      selected = null;
      render();
      changed(`${name} taken off the plan. Mark it out again from the list below the plan.`);
    }
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
      if (rooms.has(card.dataset.uid)) { selected = card.dataset.uid; render(); }
      return;
    }
    render();                // renames and additions redraw names and the tray
    if (type === 'rename') changed();
  });

  resetBtn.addEventListener('click', () => {
    fromTrace(detected);
    selected = null;
    if (marking) stopMarking();
    render();
    changed('Rooms put back where FORMA found them.');
    resetBtn.hidden = true;
  });

  // Grips and snapping follow the plan's size on screen.
  if ('ResizeObserver' in window) new ResizeObserver(() => { if (!drag) render(); }).observe(svg);

  // ── Start ──────────────────────────────────────────────────────────────────
  function ready(byLabel, lines) {
    detected = byLabel;
    if (lines && lines.length) outline = lines;
    cfg.status = 'ready';
    root.dataset.status = 'ready';
    if (!touched) fromTrace(byLabel);
    hint = rooms.size
      ? 'Check each room’s walls line up with the plan. Drag an edge to move that wall; rooms that share it move too.'
      : 'FORMA could not match your rooms on the plan. Mark each one out below.';
    say(hint);
    render();
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
        ready(d.rooms || {}, d.outline);
      })
      .catch(failed);
  }

  function failed() {
    cfg.status = 'failed';
    root.dataset.status = 'failed';
    hint = 'We couldn’t find your rooms automatically. Mark them out yourself, or leave it — FORMA will try again at the end.';
    say(hint + ' ');
    const again = document.createElement('button');
    again.type = 'button';
    again.className = 'pe-link';
    again.textContent = 'Try again';
    again.addEventListener('click', trace);
    status.appendChild(again);
    render();
  }

  if (cfg.status === 'ready') ready(cfg.rooms, cfg.outline);
  else if (cfg.status === 'failed') failed();
  else trace();

  document.querySelector('form[data-autosave]').addEventListener('submit', write);
})();
