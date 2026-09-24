"""
furniture_layout.py — place furniture in a room by general interior design
rules. Pure Python, no Flask and no model: app.py asks the model WHAT goes in
each room and how big it is; this decides WHERE, the same way every time.

Units are metres. A room is its main rectangle, W wide and D deep, origin at
the top-left corner, x to the right and y down — the plan's own orientation.

Each piece is a dict:
    name       what to label it
    w, d       footprint: w along the wall it backs onto, d out into the room
    place      "wall" | "corner" | "centre" | "beside" | "front" | "facing" | "under"
    anchor     for beside / front / facing / under: the piece it relates to
    clearance  clear floor it needs in front (all round for "centre")
    side       clear floor it needs at each end (a bed's sides)
    align      "centre" to prefer the middle of a wall, "end" to prefer a corner
    rule       the design guide behind its placement, in a few words

Placed pieces gain x, y (top-left of the body, axis-aligned), bw, bd (body
size as laid out), rot (0 back on the top wall, 90 right, 180 bottom, 270
left) and wall.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date
from pathlib import Path

# ── General design standards ─────────────────────────────────────────────────
# Sizes and clearances from common residential guides (Neufert; NKBA kitchen
# guidelines; typical Singapore HDB furnishing), kept in furniture_sizes.json
# so they can be read and corrected without touching code. Pieces the model
# had to size itself are added there, so each is estimated once and then the
# same every time.
CATALOGUE_PATH = Path(__file__).parent / "furniture_sizes.json"
_catalogue_lock = threading.Lock()

# keywords, name, w, d, place, anchor, clearance, side, align, rule
STANDARDS: list[tuple] = []
MODEL_ESTIMATES: set[str] = set()      # names whose size the model supplied


def load_catalogue(path: Path | None = None) -> None:
    """(Re)load the size list into STANDARDS."""
    global CATALOGUE_PATH
    if path:
        CATALOGUE_PATH = Path(path)
    try:
        items = json.loads(CATALOGUE_PATH.read_text()).get("items", [])
    except (OSError, ValueError):
        items = []
    STANDARDS.clear()
    MODEL_ESTIMATES.clear()
    for it in items:
        keywords = tuple(str(k).lower() for k in it.get("match") or [])
        if not keywords:
            continue
        if it.get("skip"):
            STANDARDS.append((keywords, "", 0, 0, "", "", 0, 0, "", ""))
            continue
        STANDARDS.append((keywords, it["name"], float(it["w"]), float(it["d"]),
                          it.get("place", "wall"), it.get("anchor", ""),
                          float(it.get("clearance", 0.6)), float(it.get("side", 0)),
                          it.get("align", "end"), it.get("rule", "")))
        if it.get("source") == "model estimate":
            MODEL_ESTIMATES.add(it["name"])


def remember(pieces: list[dict]) -> list[str]:
    """Add every piece the size list does not know to it, with the size the
    model gave, so the next project uses the same size without asking.
    Returns the names added."""
    new = [p for p in pieces if p.get("estimated") and p.get("sized_by_model")]
    if not new:
        return []
    added = []
    with _catalogue_lock:
        try:
            doc = json.loads(CATALOGUE_PATH.read_text())
        except (OSError, ValueError):
            doc = {"items": []}
        known = {k for it in doc.get("items", []) for k in it.get("match", [])}
        for p in new:
            key = (p.get("label") or p["name"]).strip().lower()
            if not key or key in known:
                continue
            known.add(key)
            added.append(p.get("label") or p["name"])
            doc.setdefault("items", []).append({
                "name": p.get("label") or p["name"], "match": [key],
                "w": round(p["w"], 2), "d": round(p["d"], 2), "place": p["place"],
                "anchor": p.get("anchor", ""), "clearance": round(p["clearance"], 2),
                "side": round(p.get("side", 0), 2), "align": p.get("align", "end"),
                "rule": p.get("rule", ""), "source": "model estimate",
                "added": date.today().isoformat(),
            })
        if added:
            tmp = CATALOGUE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            tmp.replace(CATALOGUE_PATH)
            load_catalogue()
    return added


load_catalogue()

# Not floor furniture — nothing to place.
NOT_FLOOR = ("curtain", "blind", "drape", "pendant", "ceiling", "light", "lamp shade",
             "sconce", "feature wall", "wallpaper", "paint", "mirror", "towel rail",
             "fan", "hook", "downlight", "track")

GENERIC = ("Item", 0.8, 0.6, "wall", "", 0.6, 0.0, "end", "Against a wall, clear of walkways")

PLACES = {"wall", "corner", "centre", "beside", "front", "facing", "under"}

# Where a room with no traced plan gets its door: the bottom wall, towards
# one end — where its drawing shows it.
DEFAULT_DOOR = {"part": 0, "wall": "bottom", "at": 0.75}

STEP = 0.05          # search resolution along walls and across the floor
MIN_CLEARANCE = 0.67 # the minimum clearance, as a share of the recommended
GAP = 0.03           # a hair between neighbours, so outlines do not merge


def standard_for(name: str):
    """The standard entry whose keywords match an item name, or None."""
    n = name.lower()
    for keywords, *rest in STANDARDS:
        if any(k in n for k in keywords):
            return rest
    return None


def is_floor_item(name: str) -> bool:
    n = name.lower()
    if "floor lamp" in n:
        return True
    return not any(k in n for k in NOT_FLOOR)


def pieces_from_names(names: list[str]) -> list[dict]:
    """Pieces for a list of item names, from the standards table alone.
    The fallback when the model is unavailable. An item the table does not
    know becomes a generic block with an estimated size."""
    out = []
    for raw in names:
        name = " ".join(str(raw).split())
        if not name or not is_floor_item(name):
            continue
        std = standard_for(name)
        if std and not std[0]:
            continue                            # chairs: drawn with the table
        label, w, d, place, anchor, clearance, side, align, rule = std or GENERIC
        out.append({
            "name": name if not std else label, "label": name if not std else label,
            "w": w, "d": d, "place": place,
            "anchor": anchor, "clearance": clearance, "side": side, "align": align,
            "rule": rule, "estimated": std is None, "source": "ticked",
        })
    return _dedupe(out)


def clean_pieces(raw: list, fallback_names: list[str]) -> list[dict]:
    """Validate the model's pieces, filling gaps from the standards table.
    Anything unusable is dropped; if nothing usable is left, fall back to the
    ticked items."""
    out = []
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        name = " ".join(str(p.get("name", "")).split())[:40]
        if not name or not is_floor_item(name):
            continue
        std = standard_for(name)
        if std and not std[0]:
            continue
        label, sw, sd, splace, sanchor, sclear, sside, salign, srule = std or GENERIC

        def num(key, default, lo, hi):
            try:
                v = float(p.get(key, default))
            except (TypeError, ValueError):
                return default
            return v if lo <= v <= hi else default

        # A piece on the size list takes the listed size, so it is the same
        # every time. Only a piece the list does not know takes the model's.
        sized_by_model = std is None and all(
            isinstance(p.get(k), (int, float)) for k in ("w", "d"))
        w, d = (sw, sd) if std else (num("w", sw, 0.2, 4.0), num("d", sd, 0.2, 3.0))
        place = str(p.get("place", splace)).lower().strip()
        if place not in PLACES:
            place = splace
        # For a piece the standards know, their plain placement wins — a
        # drying rack goes on a wall, not free-standing mid-room. A relation
        # the model drew (a coffee table before the sofa) is kept.
        plain = ("wall", "corner", "centre")
        if std and place in plain and splace in plain:
            place = splace
        try:
            qty = min(max(int(p.get("qty", 1) or 1), 1), 4)
        except (TypeError, ValueError):
            qty = 1
        for n in range(qty):
            out.append({
            "name": name if n == 0 else f"{name} ({n + 1})", "label": name,
            "w": w, "d": d, "place": place,
            "anchor": str(p.get("anchor") or sanchor).strip().lower(),
            "clearance": sclear if std else num("clearance", sclear, 0.0, 1.5),
            "side": sside if std else num("side", sside, 0.0, 1.0),
            "align": salign if p.get("align") not in ("centre", "end") else p["align"],
            "rule": str(p.get("rule") or srule)[:90],
            # A size no standard vouches for is the model's estimate — new
            # now, or remembered from an earlier project.
            "estimated": std is None or label in MODEL_ESTIMATES,
            "sized_by_model": sized_by_model,
            "source": "described" if str(p.get("source", "")).lower().startswith("desc") else "ticked",
            })
    return _dedupe(out) or pieces_from_names(fallback_names)


def _dedupe(pieces: list[dict]) -> list[dict]:
    seen, out = set(), []
    for p in pieces:
        key = p["name"].lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


# ── Geometry ──────────────────────────────────────────────────────────────────
def _overlaps(a, b, tol=0.005):
    return (a[0] < b[0] + b[2] - tol and b[0] < a[0] + a[2] - tol and
            a[1] < b[1] + b[3] - tol and b[1] < a[1] + a[3] - tol)


def _inside(r, W, D, tol=0.001):
    return r[0] >= -tol and r[1] >= -tol and r[0] + r[2] <= W + tol and r[1] + r[3] <= D + tol


def _wall_rects(wall, t, w, d, c, side, W, D):
    """Body, clearance zone and rotation for a piece of footprint w x d whose
    back is on `wall`, starting t along it."""
    if wall == "top":
        body, rot = (t, 0, w, d), 0
        zone = (t - side, d, w + 2 * side, c) if c else None
        sides = (t - side, 0, w + 2 * side, d) if side else None
    elif wall == "bottom":
        body, rot = (t, D - d, w, d), 180
        zone = (t - side, D - d - c, w + 2 * side, c) if c else None
        sides = (t - side, D - d, w + 2 * side, d) if side else None
    elif wall == "left":
        body, rot = (0, t, d, w), 270
        zone = (d, t - side, c, w + 2 * side) if c else None
        sides = (0, t - side, d, w + 2 * side) if side else None
    else:
        body, rot = (W - d, t, d, w), 90
        zone = (W - d - c, t - side, c, w + 2 * side) if c else None
        sides = (W - d, t - side, d, w + 2 * side) if side else None
    return body, zone, sides, rot


WALLS = ("top", "right", "bottom", "left")


def _wall_len(wall, W, D):
    return W if wall in ("top", "bottom") else D


def _opposite(wall):
    return {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[wall]


def _centre(r):
    return (r[0] + r[2] / 2, r[1] + r[3] / 2)


def _steps(lo, hi):
    n = int(round((hi - lo) / STEP))
    return [lo + i * STEP for i in range(max(n, 0) + 1)] if hi >= lo - 1e-9 else []


class _Room:
    def __init__(self, W, D, doors=()):
        self.W, self.D = W, D
        self.bodies: list[tuple] = []      # (rect, name)
        self.zones: list[tuple] = []       # (rect, name) — clear floor to keep
        # A door's swing is clear floor from the start; nothing may enter it.
        self.door_walls = set()
        for d in doors:
            self.zones.append((tuple(d["zone"]), "door"))
            if d.get("wall"):
                self.door_walls.add(d["wall"])

    def fits(self, body, zones, ignore=()):
        if not _inside(body, self.W, self.D):
            return False
        for z in zones:
            if z and not _inside(z, self.W, self.D):
                return False
        for rect, name in self.bodies:
            if name in ignore:
                continue
            if _overlaps(body, rect):
                return False
            for z in zones:
                if z and _overlaps(z, rect):
                    return False
        for rect, name in self.zones:
            if name in ignore:
                continue
            if _overlaps(body, rect):
                return False
        return True


def _candidates(p, room: _Room, placed: dict):
    """(score, body, zones, rot, wall) for every position the rules allow;
    lower score is better."""
    W, D = room.W, room.D
    w, d, c, side = p["w"], p["d"], p["clearance"], p["side"]
    place, anchor = p["place"], placed.get(p["anchor"])

    if place in ("beside", "front", "facing", "under") and not anchor:
        # The piece it relates to is not in the room: fall back to a plain rule.
        place = "centre" if place == "under" else "wall"

    if place in ("wall", "corner"):
        # A bed may also lie with its long side to the wall, headboard in a
        # corner — how most small bedrooms fit one. Only when headboard-to-wall
        # does not fit: it scores worse.
        ways = [(w, d, side, 0, 0.0)]
        if p.get("is_bed"):
            ways.append((d, w, 0.0, 90, 1.5))
        for ww, dd, sd, turn, penalty in ways:
            for wall in WALLS:
                L = _wall_len(wall, W, D)
                if place == "corner":
                    ts = [0.0, L - ww] if L - ww >= 0 else []
                elif turn:
                    ts = [0.0, L - ww] if L - ww >= 0 else []     # headboard in a corner
                else:
                    ts = _steps(sd, L - ww - sd)
                for t in ts:
                    body, zone, sides, rot = _wall_rects(wall, t, ww, dd, c, sd, W, D)
                    if p["align"] == "centre" and not turn:
                        score = abs(t + ww / 2 - L / 2)
                        score -= 0.3 * L                 # big pieces want the long wall
                    else:
                        score = min(t, L - ww - t)        # near a corner
                    if p["side"] and wall in room.door_walls:
                        # A bed wants a solid wall: not the one the door is in,
                        # where it would sit beside the swing and face nothing.
                        score += 2.0
                    if turn:
                        # Headboard in the corner the bed starts from: the
                        # icon's headboard (its top) turned to face it.
                        at_start = t < 1e-9
                        rot = ((270 if at_start else 90) if wall in ("top", "bottom")
                               else (0 if at_start else 180))
                    yield score + penalty, body, (zone, sides), rot, wall

    elif place == "beside" and anchor.get("sideways"):
        # A bed lying side-on has its headboard in a corner: the bedside table
        # goes at the head, against the other wall of that corner, on the
        # bed's open side.
        b, a_rot, a_wall = anchor["rect"], anchor["rot"], anchor["wall"]
        if a_wall in ("left", "right"):
            corner = "top" if a_rot == 0 else "bottom"
            t = b[0] - GAP - w if a_wall == "right" else b[0] + b[2] + GAP
        else:
            corner = "left" if a_rot == 270 else "right"
            t = b[1] + b[3] + GAP if a_wall == "top" else b[1] - GAP - w
        if 0 <= t <= _wall_len(corner, W, D) - w:
            body, zone, sides, rot = _wall_rects(corner, t, w, d, c, 0, W, D)
            yield 0.0, body, (zone,), rot, corner

    elif place == "beside":
        a_body, a_rot, a_wall = anchor["rect"], anchor["rot"], anchor["wall"]
        if a_wall is None:
            return
        L = _wall_len(a_wall, W, D)
        a_t = a_body[0] if a_wall in ("top", "bottom") else a_body[1]
        a_len = a_body[2] if a_wall in ("top", "bottom") else a_body[3]
        for t in (a_t - w - GAP, a_t + a_len + GAP):
            if 0 <= t <= L - w:
                body, zone, sides, rot = _wall_rects(a_wall, t, w, d, c, 0, W, D)
                yield 0.0, body, (zone,), rot, a_wall

    elif place == "front":
        a_body, a_wall = anchor["rect"], anchor["wall"]
        gap = max(p.get("gap", 0.45), 0.35)
        cx, cy = _centre(a_body)
        if a_wall == "top":
            body, rot = (cx - w / 2, a_body[1] + a_body[3] + gap, w, d), 0
        elif a_wall == "bottom":
            body, rot = (cx - w / 2, a_body[1] - gap - d, w, d), 180
        elif a_wall == "left":
            body, rot = (a_body[0] + a_body[2] + gap, cy - w / 2, d, w), 270
        elif a_wall == "right":
            body, rot = (a_body[0] - gap - d, cy - w / 2, d, w), 90
        else:
            return
        yield 0.0, body, (), rot, None

    elif place == "facing":
        a_wall = anchor["wall"]
        if a_wall is None:
            return
        wall = _opposite(a_wall)
        L = _wall_len(wall, W, D)
        a_c = _centre(anchor["rect"])[0 if wall in ("top", "bottom") else 1]
        for t in _steps(0, L - w):
            body, zone, sides, rot = _wall_rects(wall, t, w, d, c, 0, W, D)
            yield abs(t + w / 2 - a_c), body, (zone,), rot, wall

    elif place == "under":
        cx, cy = _centre(anchor["rect"])
        if anchor["rot"] in (90, 270):
            w, d = d, w
        body = (min(max(cx - w / 2, 0), max(W - w, 0)), min(max(cy - d / 2, 0), max(D - d, 0)),
                min(w, W), min(d, D))
        yield 0.0, body, (), 0, None

    else:                                          # centre
        for rot in (0, 90):
            bw, bd = (w, d) if rot == 0 else (d, w)
            for x in _steps(c, W - bw - c):
                for y in _steps(c, D - bd - c):
                    body = (x, y, bw, bd)
                    zone = (x - c, y - c, bw + 2 * c, bd + 2 * c) if c else None
                    cx, cy = _centre(body)
                    # Middle of the free floor, long side along the room.
                    score = abs(cx - W / 2) + abs(cy - D / 2)
                    if (bw >= bd) != (W >= D):
                        score += 0.2
                    yield score, body, (zone,), rot, None


def _order(pieces):
    """Big independent pieces first, each followed at once by the pieces that
    relate to it — a sofa, then its coffee table and TV, before a dining
    table can take the middle of the room. Corner pieces after, rugs last,
    since they lie under everything."""
    names = {p["name"].lower() for p in pieces}
    relates = lambda p: p["place"] in ("beside", "front", "facing") and p["anchor"] in names
    roots = [p for p in pieces if not relates(p) and p["place"] != "under"]
    roots.sort(key=lambda p: (p["place"] == "corner", -p["w"] * p["d"]))
    out = []

    def add(p):
        out.append(p)
        for q in pieces:
            if relates(q) and q["anchor"] == p["name"].lower() and q not in out:
                add(q)

    for p in roots:
        add(p)
    return out + [p for p in pieces if p not in out]


def _match_anchor(pieces):
    """Point each piece's anchor at a piece that is actually in the room
    ("sofa" finds "Sectional sofa")."""
    names = [p["name"].lower() for p in pieces]
    for p in pieces:
        a = p.get("anchor", "")
        if not a or a in names:
            continue
        hit = next((n for n in names if a in n or n in a), None)
        if not hit:
            base = a.split()[-1]
            hit = next((n for n in names if re.search(rf"\b{re.escape(base)}\b", n)), None)
        p["anchor"] = hit or ""


def _min_clearance(c: float) -> float:
    """The minimum clear floor the guides accept for a recommended c: two
    thirds of it, but never under 500 mm (or c itself, if that is less)."""
    return max(c * MIN_CLEARANCE, min(0.5, c)) if c else 0.0


def _zone_rects(body, rot, wall, c, side, W, D):
    """Clearance zones for a placed body at clearance c — recomputed at the
    minimum once placed, which is all later pieces must leave clear."""
    if wall is None:
        if not c:
            return ()
        return ((body[0] - c, body[1] - c, body[2] + 2 * c, body[3] + 2 * c),)
    if wall in ("top", "bottom"):
        t, w, d = body[0], body[2], body[3]
    else:
        t, w, d = body[1], body[3], body[2]
    _b, zone, sides, _r = _wall_rects(wall, t, w, d, c, side, W, D)
    return tuple(z for z in (zone, sides) if z)


def _between(a, b):
    """The floor between two facing bodies, as wide as the narrower one."""
    if a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]:            # one above the other
        x0 = max(a[0], b[0]); x1 = min(a[0] + a[2], b[0] + b[2])
        y0 = min(a[1] + a[3], b[1] + b[3]); y1 = max(a[1], b[1])
    else:                                                       # side by side
        y0 = max(a[1], b[1]); y1 = min(a[1] + a[3], b[1] + b[3])
        x0 = min(a[0] + a[2], b[0] + b[2]); x1 = max(a[0], b[0])
    return (x0, y0, max(x1 - x0, 0), max(y1 - y0, 0))


# Bed sizes, largest first: a bed that will not fit tries the next one down.
BED_LADDER = ("King bed", "Queen bed", "Super single bed", "Single bed")


def _is_bed(name: str) -> bool:
    n = name.lower()
    return bool(re.search(r"\bbed\b", n)) and not any(
        k in n for k in ("bedside", "sofa bed", "bed frame storage", "flower bed", "garden bed"))


def _smaller_beds(p: dict) -> list[dict]:
    """The standard beds smaller than this one, largest first, as pieces."""
    out = []
    for name in BED_LADDER:
        std = standard_for(name)
        if not std or std[1] >= p["w"] - 1e-6:
            continue
        label, w, d, place, anchor, clearance, side, align, rule = std
        out.append(dict(p, label=label, w=w, d=d, clearance=clearance, side=side,
                        align=align, rule=rule))
    return out


def _greedy(W, D, ordered, first_wall=None, doors=()):
    room = _Room(W, D, doors)
    placed: dict[str, dict] = {}
    out, skipped, total = [], [], 0.0

    for i, p in enumerate(ordered):
        key = p["name"].lower()
        best = None
        # Recommended clearance first; then the minimum the guides allow; then
        # a bed a size down, and down again; only then a smaller piece.
        tries = [(p, 1.0, False), (p, 1.0, True)]
        if p.get("is_bed"):
            tries += [(smaller, 1.0, relax) for smaller in _smaller_beds(p)
                      for relax in (False, True)]
        tries.append((p, 0.85, True))
        for base, size, relax in tries:
            c = _min_clearance(base["clearance"]) if relax else base["clearance"]
            side = _min_clearance(base["side"]) if relax else base["side"]
            q = dict(base, w=base["w"] * size, d=base["d"] * size, clearance=c, side=side)
            ignore = (q["anchor"],) if q["place"] in ("front", "beside") else ()
            for score, body, zones, rot, wall in _candidates(q, room, placed):
                if i == 0 and first_wall and wall != first_wall:
                    continue
                if q["place"] == "under" or room.fits(body, zones, ignore=ignore):
                    if best is None or score < best[0] - 1e-9:
                        best = (score, body, rot, wall, size, relax, base)
            if best:
                break
        if not best:
            skipped.append(p.get("label", p["name"]))
            continue
        score, body, rot, wall, size, relax, base = best
        if base is not p:
            # Placed a size down: say so on the drawing.
            p = dict(p, label=f"{base['label']} (smaller, to fit)", resized=True)
        total += score
        if p["place"] != "under":
            room.bodies.append((body, key))
            for z in _zone_rects(body, rot, wall, _min_clearance(p["clearance"]),
                                 _min_clearance(p["side"]), W, D):
                room.zones.append((z, key))
        if p["place"] == "facing" and p["anchor"] in placed:
            # Keep the sightline between the pair clear of anything placed
            # later — no dining table between the sofa and the TV.
            room.zones.append((_between(placed[p["anchor"]]["rect"], body), key))
        facing_wall = {"top": 0, "right": 90, "bottom": 180, "left": 270}.get(wall)
        placed[key] = {"rect": body, "rot": rot, "wall": wall,
                       "sideways": bool(p.get("is_bed")) and wall is not None and rot != facing_wall}
        out.append({
            **p, "x": body[0], "y": body[1], "bw": body[2], "bd": body[3],
            "rot": rot, "wall": wall, "scaled": size < 1.0, "tight": relax,
        })
    return out, skipped, total


def place_room(W: float, D: float, pieces: list[dict], doors: list[dict] = ()) -> dict:
    """Lay out pieces in a W x D room. Returns {"placed": [...], "skipped": [...]}.

    Deterministic. Pieces go in order, each at its best-scoring position that
    keeps clear of what is placed and of the minimum floor those pieces need;
    a piece tries its recommended clearance, then the minimum, then 85% size,
    and is otherwise left out and reported rather than squeezed in. The
    largest piece decides how the rest can fit, so it is tried on each wall
    and the layout that fits the most — then needs the least relaxing — wins.

    doors: [{"zone": (x, y, w, h), "wall": "top" | ... | None}] — each door's
    swing, kept clear, and the wall it is in."""
    pieces = [dict(p) for p in pieces]
    for p in pieces:
        p["is_bed"] = _is_bed(p.get("label") or p["name"])
        p.setdefault("label", p["name"])
    _match_anchor(pieces)
    ordered = _order(pieces)
    if not ordered:
        return {"placed": [], "skipped": []}

    starts = [None]
    if ordered[0]["place"] in ("wall", "corner"):
        starts = list(WALLS)
    best = None
    for first_wall in starts:
        out, skipped, total = _greedy(W, D, ordered, first_wall, doors)
        rank = (len(skipped), sum(q["scaled"] for q in out),
                sum(q["tight"] for q in out), total)
        if best is None or rank < best[0]:
            best = (rank, out, skipped)
    _rank, out, skipped = best
    # Rugs first when drawn, so everything else sits on top of them.
    out.sort(key=lambda q: q["place"] != "under")
    return {"placed": out, "skipped": skipped}


def door_zone(point: tuple, wall: str, width: float) -> tuple:
    """A door's swing as clear floor: as wide as the door, as deep as it is
    wide, on the room side of the wall it is in. point is the door's centre."""
    x, y = point
    half = width / 2
    return {"top":    (x - half, y, width, width),
            "bottom": (x - half, y - width, width, width),
            "left":   (x, y - half, width, width),
            "right":  (x - width, y - half, width, width)}[wall]


def place_parts(parts: list[tuple], pieces: list[dict], doors: list[dict] = ()) -> dict:
    """Lay out an L- or T-shaped room part by part: parts are (x, y, w, d) in
    metres from the room's top-left, largest first. Whatever does not fit in
    one part is tried in the next — a combined living/dining room gets its
    dining table in the dining end.

    doors: [{"point": (x, y), "wall": side, "width": m}] in the same frame."""
    remaining, placed = [dict(p) for p in pieces], []
    for ox, oy, w, d in parts:
        if not remaining:
            break
        local = []
        for dr in doors:
            zx, zy, zw, zh = door_zone(dr["point"], dr["wall"], dr["width"])
            px, py = dr["point"][0] - ox, dr["point"][1] - oy
            # The wall it is in, if that wall is one of this part's own.
            on = {"top": abs(py) < 0.05, "bottom": abs(py - d) < 0.05,
                  "left": abs(px) < 0.05, "right": abs(px - w) < 0.05}
            local.append({"zone": (zx - ox, zy - oy, zw, zh),
                          "wall": dr["wall"] if on[dr["wall"]] else None})
        res = place_room(w, d, remaining, local)
        for q in res["placed"]:
            placed.append({**q, "x": q["x"] + ox, "y": q["y"] + oy})
        done = {q["name"].lower() for q in res["placed"]}
        remaining = [p for p in remaining if p["name"].lower() not in done]
    placed.sort(key=lambda q: q["place"] != "under")
    return {"placed": placed, "skipped": [p.get("label", p["name"]) for p in remaining]}


# ── Typical room sizes ────────────────────────────────────────────────────────
# Per HDB flat type, from room_sizes.json (sourced; editable). Used to size a
# room with no traced plan, and to keep a traced plan in proportion.
ROOM_SIZES_PATH = Path(__file__).parent / "room_sizes.json"
try:
    ROOM_SIZES = json.loads(ROOM_SIZES_PATH.read_text()).get("flat_types", {})
except (OSError, ValueError):
    ROOM_SIZES = {}

# When the flat type has no entry (condos, landed): a believable footprint.
TYPICAL_ROOM_M = [
    (("living", "dining", "family"), 4.5, 5.5),
    (("master bed", "main bed"), 3.4, 3.8),
    (("bed",), 3.0, 3.2),
    (("study", "office"), 2.6, 3.0),
    (("kitchen",), 2.4, 3.6),
    (("master bath", "ensuite"), 1.8, 2.4),
    (("bath", "wc", "toilet", "powder"), 1.6, 2.2),
    (("yard", "utility", "laundry"), 1.5, 2.4),
    (("shelter", "store", "storage"), 1.4, 1.8),
    (("balcony",), 1.5, 3.2),
]


def room_kind(label: str) -> str | None:
    """Which kind of room a label names, as room_sizes.json calls them."""
    n = label.lower()
    if any(k in n for k in ("master bath", "ensuite", "en suite", "en-suite")):
        return "master_bathroom"
    if any(k in n for k in ("bath", "wc", "toilet", "powder")):
        return "bathroom"
    if any(k in n for k in ("master bed", "main bed")):
        return "master_bedroom"
    if re.search(r"\bbed(room)?\b", n):
        return "bedroom"
    if any(k in n for k in ("living", "dining", "family", "lounge")):
        return "living"
    if "kitchen" in n:
        return "kitchen"
    if any(k in n for k in ("yard", "utility", "laundry")):
        return "service_yard"
    if any(k in n for k in ("shelter", "store", "storage", "bunker")):
        return "shelter"
    if any(k in n for k in ("study", "office")):
        return "study"
    return None


def typical_area(label: str, housing_type: str | None) -> float | None:
    """A room's typical floor area in m² for this flat type, or None."""
    entry = ROOM_SIZES.get(housing_type or "", {}).get(room_kind(label) or "")
    return float(entry["sqm"]) if entry else None


def typical_room_size(label: str, housing_type: str | None = None) -> tuple[float, float]:
    """A room's typical width and depth in metres: from its flat type's sizes
    when known, otherwise a believable footprint by kind."""
    entry = ROOM_SIZES.get(housing_type or "", {}).get(room_kind(label) or "")
    if entry:
        shape = float(entry.get("shape", 1.2))
        w = (float(entry["sqm"]) / shape) ** 0.5
        return round(w, 2), round(w * shape, 2)
    n = label.lower()
    for keywords, w, d in TYPICAL_ROOM_M:
        if any(k in n for k in keywords):
            return w, d
    return 3.0, 3.0
