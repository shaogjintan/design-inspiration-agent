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

import re

# ── General design standards ─────────────────────────────────────────────────
# Sizes and clearances from common residential guides (Neufert; NKBA kitchen
# guidelines; typical Singapore HDB furnishing). Used to fill anything the
# model leaves out, and as the whole plan when the model is unavailable.
# keywords, name, w, d, place, anchor, clearance, side, align, rule
STANDARDS = [
    (("bedside", "nightstand"), "Bedside table", 0.45, 0.40, "beside", "bed", 0.0, 0.0, "",
     "Beside the bed, at mattress height"),
    (("king bed",), "King bed", 1.83, 2.03, "wall", "", 0.6, 0.6, "centre",
     "Headboard on a solid wall, 600 mm clear on each side"),
    (("queen bed",), "Queen bed", 1.52, 2.03, "wall", "", 0.6, 0.6, "centre",
     "Headboard on a solid wall, 600 mm clear on each side"),
    (("single bed", "super single"), "Single bed", 1.07, 1.9, "wall", "", 0.6, 0.0, "end",
     "Along a wall to free floor space"),
    (("bunk", "loft bed"), "Bunk bed", 1.0, 2.0, "wall", "", 0.6, 0.0, "end",
     "Along a wall to free floor space"),
    (("bed",), "Bed", 1.52, 2.03, "wall", "", 0.6, 0.6, "centre",
     "Headboard on a solid wall, 600 mm clear on each side"),
    (("wardrobe", "closet"), "Wardrobe", 1.8, 0.6, "wall", "", 0.9, 0.0, "end",
     "Against a long wall, 900 mm clear to open the doors"),
    (("dresser", "dressing table", "chest of drawers", "vanity table"), "Dresser", 1.0, 0.5, "wall", "", 0.8, 0.0, "end",
     "Against a wall, 800 mm clear to open drawers"),
    (("desk", "study table", "workstation"), "Desk", 1.2, 0.6, "wall", "", 0.9, 0.0, "end",
     "Against a wall, 900 mm for the chair to pull out"),
    (("sofa bed",), "Sofa bed", 2.0, 0.95, "wall", "", 0.45, 0.0, "centre",
     "Against a wall, facing the room"),
    (("sectional", "l-shaped sofa"), "Sectional sofa", 2.6, 1.6, "wall", "", 0.45, 0.0, "centre",
     "Against a wall, facing the TV"),
    (("sofa", "couch", "settee"), "Sofa", 2.1, 0.9, "wall", "", 0.45, 0.0, "centre",
     "Against a wall, facing the TV"),
    (("coffee table",), "Coffee table", 1.1, 0.6, "front", "sofa", 0.0, 0.0, "centre",
     "450 mm in front of the sofa, within reach"),
    (("tv console", "tv cabinet", "media console", "tv"), "TV console", 1.8, 0.45, "facing", "sofa", 0.0, 0.0, "centre",
     "Opposite the sofa, 2-3 m viewing distance"),
    (("armchair", "accent chair", "reading chair", "lounge chair"), "Armchair", 0.85, 0.85, "corner", "", 0.45, 0.0, "end",
     "In a corner, angled towards the seating group"),
    (("side table", "end table"), "Side table", 0.5, 0.5, "beside", "sofa", 0.0, 0.0, "",
     "At the arm of the sofa"),
    (("dining table", "dining set"), "Dining table", 1.6, 0.9, "centre", "", 0.9, 0.0, "centre",
     "900 mm all round to pull chairs out"),
    (("dining chair", "chairs"), "", 0, 0, "", "", 0, 0, "", ""),   # drawn with the table
    (("sideboard", "buffet", "bar cabinet", "display cabinet", "console table"), "Sideboard", 1.6, 0.45, "wall", "", 0.9, 0.0, "end",
     "Against a wall, 900 mm to open doors"),
    (("bookshelf", "bookcase", "shelving", "shelf", "display shelving"), "Shelving", 1.2, 0.35, "wall", "", 0.6, 0.0, "end",
     "Against a wall, clear of walkways"),
    (("rug", "carpet"), "Rug", 2.0, 1.4, "under", "coffee table", 0.0, 0.0, "centre",
     "Under the seating group, anchoring it"),
    (("floor lamp",), "Floor lamp", 0.4, 0.4, "corner", "", 0.0, 0.0, "end",
     "In a corner, lighting the seating"),
    (("plant",), "Plant", 0.45, 0.45, "corner", "", 0.0, 0.0, "end",
     "In a corner, out of the walkway"),
    (("island", "breakfast bar"), "Island", 1.8, 0.9, "centre", "", 1.0, 0.0, "centre",
     "1 m clear all round for the work aisle"),
    (("refrigerator", "fridge"), "Fridge", 0.75, 0.7, "wall", "", 1.0, 0.0, "end",
     "At the end of the counter run, 1 m to open the door"),
    (("hob", "cooktop", "stove", "oven", "cooker"), "Hob", 0.9, 0.6, "wall", "", 1.0, 0.0, "centre",
     "On the counter run, 1 m work aisle in front"),
    (("kitchen sink", "sink"), "Sink", 0.8, 0.6, "wall", "", 1.0, 0.0, "centre",
     "On the counter run, near the hob — the work triangle"),
    (("dishwasher",), "Dishwasher", 0.6, 0.6, "wall", "", 1.0, 0.0, "end",
     "Beside the sink"),
    (("pantry", "tall cabinet", "kitchen cabinet", "cabinet", "storage"), "Storage", 1.2, 0.6, "wall", "", 0.9, 0.0, "end",
     "Against a wall, 900 mm to open doors"),
    (("washing machine", "washer", "dryer"), "Washing machine", 0.6, 0.6, "wall", "", 0.9, 0.0, "end",
     "Against a wall, 900 mm to load it"),
    (("drying rack", "laundry rack", "clothes rack"), "Drying rack", 1.2, 0.5, "wall", "", 0.6, 0.0, "end",
     "Along a wall, clear of the washer"),
    (("double vanity",), "Double vanity", 1.5, 0.55, "wall", "", 0.75, 0.0, "centre",
     "Against a wall, 750 mm clear in front"),
    (("vanity", "basin", "wash basin"), "Vanity", 0.8, 0.5, "wall", "", 0.75, 0.0, "end",
     "Against a wall, 750 mm clear in front"),
    (("toilet", "wc", "water closet"), "Toilet", 0.4, 0.7, "wall", "", 0.6, 0.2, "end",
     "Against a wall, 600 mm clear in front"),
    (("bathtub", "tub"), "Bathtub", 1.7, 0.75, "wall", "", 0.7, 0.0, "end",
     "Along the end wall"),
    (("shower",), "Shower", 0.9, 0.9, "corner", "", 0.6, 0.0, "end",
     "In a corner, 600 mm clear to step out"),
]

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

        w, d = num("w", sw, 0.2, 4.0), num("d", sd, 0.2, 3.0)
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
            "clearance": num("clearance", sclear, 0.0, 1.5),
            "side": num("side", sside, 0.0, 1.0),
            "align": salign if p.get("align") not in ("centre", "end") else p["align"],
            "rule": str(p.get("rule") or srule)[:90],
            # A size the table does not vouch for is the model's estimate.
            "estimated": std is None,
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
        for wall in WALLS:
            L = _wall_len(wall, W, D)
            if place == "corner":
                ts = [0.0, L - w] if L - w >= 0 else []
            else:
                ts = _steps(side, L - w - side)
            for t in ts:
                body, zone, sides, rot = _wall_rects(wall, t, w, d, c, side, W, D)
                if p["align"] == "centre":
                    score = abs(t + w / 2 - L / 2)
                    score -= 0.3 * L                 # big pieces want the long wall
                else:
                    score = min(t, L - w - t)        # near a corner
                if p["side"] and wall in room.door_walls:
                    # A bed wants a solid wall: not the one the door is in,
                    # where it would sit beside the swing and face nothing.
                    score += 2.0
                yield score, body, (zone, sides), rot, wall

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


def _greedy(W, D, ordered, first_wall=None, doors=()):
    room = _Room(W, D, doors)
    placed: dict[str, dict] = {}
    out, skipped, total = [], [], 0.0

    for i, p in enumerate(ordered):
        key = p["name"].lower()
        best = None
        # Recommended clearance first; then the minimum the guides allow;
        # only then a smaller piece.
        for size, relax in ((1.0, False), (1.0, True), (0.85, True)):
            c = _min_clearance(p["clearance"]) if relax else p["clearance"]
            side = _min_clearance(p["side"]) if relax else p["side"]
            q = dict(p, w=p["w"] * size, d=p["d"] * size, clearance=c, side=side)
            ignore = (q["anchor"],) if q["place"] in ("front", "beside") else ()
            for score, body, zones, rot, wall in _candidates(q, room, placed):
                if i == 0 and first_wall and wall != first_wall:
                    continue
                if q["place"] == "under" or room.fits(body, zones, ignore=ignore):
                    if best is None or score < best[0] - 1e-9:
                        best = (score, body, rot, wall, size, relax)
            if best:
                break
        if not best:
            skipped.append(p.get("label", p["name"]))
            continue
        score, body, rot, wall, size, relax = best
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
        placed[key] = {"rect": body, "rot": rot, "wall": wall}
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
# For rooms with no traced plan to measure: a believable footprint by type.
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


def typical_room_size(label: str) -> tuple[float, float]:
    n = label.lower()
    for keywords, w, d in TYPICAL_ROOM_M:
        if any(k in n for k in keywords):
            return w, d
    return 3.0, 3.0
