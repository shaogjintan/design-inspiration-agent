"""
style_match.py — match a homeowner's taste to FORMA's reference library.

The library (forma-library-handover/forma-library.json) holds interior photos
tagged with one fixed vocabulary: style, palette family, materials, lighting,
texture, furniture style, mood, layout, budget tier and housing fit. The
homeowner's own inspiration photos are read into that same vocabulary (by the
model, in app.py), so the two can be compared directly: this module ranks the
library for each room and describes the pictures the homeowner picks, for the
brief. Pure Python — no Flask, no model.

Library photos are references for choosing a style. They are never the
homeowner's room, and the page says so.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

LIBRARY_PATH = Path(__file__).parent / "forma-library-handover" / "forma-library.json"

# Tag fields in the library's vocabulary, and how much each counts when a
# library photo is compared with the homeowner's taste. Style and palette are
# what a homeowner recognises first; the rest refine among close matches.
WEIGHTS = {
    "style": 4.0,
    "palette_family": 2.5,
    "materials": 1.2,          # per shared value
    "lighting": 0.6,           # per shared value
    "texture": 1.0,
    "furniture_style": 1.0,
    "mood": 1.2,
    "layout": 0.4,
    "housing_fit": 0.8,
    "budget_tier": 0.6,
}
LIST_FIELDS = ("materials", "lighting")
SINGLE_FIELDS = ("palette_family", "texture", "furniture_style", "mood", "layout")


@lru_cache(maxsize=1)
def load_library() -> dict:
    """The library file, or an empty library if it is missing or unreadable —
    the style page then says there is nothing to pick from rather than
    failing."""
    try:
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"images": [], "tag_vocabulary": {}}
    data.setdefault("images", [])
    data.setdefault("tag_vocabulary", {})
    return data


def vocabulary() -> dict[str, list[str]]:
    return load_library()["tag_vocabulary"]


def images_by_id() -> dict[str, dict]:
    return {img["id"]: img for img in load_library()["images"]}


# ── The homeowner's choices, in the library's vocabulary ─────────────────────
# Page 3's style keys. Two have no set of their own in the library; they map
# to the texture, materials and mood that carry them, and the page names the
# gap rather than pretending there is a match.
STYLE_MAP = {
    "minimalist":   {"style": ["modern minimalist"]},
    "scandinavian": {"style": ["Scandinavian"]},
    "japandi":      {"style": ["Japandi"]},
    "industrial":   {"style": ["industrial"]},
    "contemporary": {"style": ["contemporary"]},
    "tropical":     {"style": ["tropical"]},
    "bohemian":     {"style": [], "texture": "woven", "materials": ["rattan", "fabric-heavy"],
                     "mood": "cosy",
                     "gap": "The library has no bohemian set, so these are the closest in "
                            "texture, materials and mood."},
    "classical":    {"style": ["modern luxe"], "materials": ["marble"],
                     "furniture_style": "statement piece",
                     "gap": "The library has no classical set; modern luxe is the closest."},
}

# Page 3's palettes, by name.
PALETTE_MAP = {
    "warm neutral": "warm neutral",
    "cool greige": "cool neutral",
    "dark & moody": "monochrome",
    "earthy tone": "earthy",
    "sage & green": "earthy",
    "dusty blue": "cool neutral",
    "blush": "pastel",
    "midnight": "bold",
}

HOUSING_MAP = {
    "hdb_2room": "HDB", "hdb_3room": "HDB", "hdb_4room": "HDB", "hdb_5room": "HDB",
    "condo": "condo", "studio": "condo", "landed": "landed", "shophouse": "landed",
}

BUDGET_MAP = {"economy": "Essential", "mid": "Mid-range",
              "premium": "Premium", "luxury": "Premium"}


def default_tags(style_key: str, colour_name: str) -> dict:
    """The homeowner's page 3 style and palette as library tags — the theme
    used when there are no inspiration photos to read."""
    base = dict(STYLE_MAP.get((style_key or "").lower().strip(), {"style": []}))
    tags = {k: v for k, v in base.items() if k != "gap"}
    family = PALETTE_MAP.get((colour_name or "").lower().strip())
    if family:
        tags["palette_family"] = family
    return clean_tags(tags)


def style_gap(style_key: str) -> str:
    return STYLE_MAP.get((style_key or "").lower().strip(), {}).get("gap", "")


def clean_tags(raw) -> dict:
    """Keep only values in the library's vocabulary, in the right shape.
    style is a list (strongest first); list fields are lists; the rest hold
    one value. Anything else the model invents is dropped."""
    vocab = vocabulary()
    if not isinstance(raw, dict):
        return {}

    def pick(field, value, vocab_key=None):
        allowed = vocab.get(vocab_key or field, [])
        lookup = {a.lower(): a for a in allowed}
        return lookup.get(str(value).strip().lower())

    out: dict = {}
    styles = raw.get("style") or []
    if isinstance(styles, str):
        styles = [styles]
    out["style"] = [s for s in (pick("style", v) for v in styles[:3]) if s]
    for field in LIST_FIELDS:
        values = raw.get(field) or []
        if isinstance(values, str):
            values = [values]
        out[field] = list(dict.fromkeys(v for v in (pick(field, x) for x in values[:4]) if v))
    for field in SINGLE_FIELDS:
        value = raw.get(field)
        if isinstance(value, list):
            value = value[0] if value else None
        key = "palette_family" if field == "palette_family" else field
        chosen = pick(field, value, key) if value else None
        if chosen:
            out[field] = chosen
    return {k: v for k, v in out.items() if v}


def merge_tags(primary: dict, fallback: dict) -> dict:
    """primary's tags, with fallback filling any field primary lacks."""
    out = dict(fallback)
    out.update({k: v for k, v in primary.items() if v})
    return out


# ── Rooms ─────────────────────────────────────────────────────────────────────
def library_rooms(label: str) -> list[str]:
    """The library room types that can stand in for one of the homeowner's
    rooms, best first. Utility spaces the library does not cover map to none."""
    n = label.lower()
    if any(k in n for k in ("shelter", "store", "storage", "yard", "utility", "laundry", "bunker")):
        return []
    if any(k in n for k in ("master bed", "main bed")):
        return ["master bedroom"]
    if re.search(r"\bbed(room)?\b", n):
        # Only five secondary bedrooms: master bedrooms stand in.
        return ["secondary bedroom", "master bedroom"]
    if any(k in n for k in ("bath", "wc", "toilet", "powder", "ensuite")):
        return ["bathroom"]
    if "kitchen" in n:
        return ["kitchen"]
    if "living" in n and "dining" in n:
        return ["living", "dining"]
    if any(k in n for k in ("living", "family", "lounge")):
        return ["living"]
    if "dining" in n:
        return ["dining"]
    if any(k in n for k in ("study", "office")):
        return ["study"]
    if "balcony" in n:
        return ["balcony"]
    if any(k in n for k in ("entry", "foyer")):
        return ["entryway"]
    return []


# ── Ranking ───────────────────────────────────────────────────────────────────
def score(img: dict, tags: dict, housing: str | None = None,
          tier: str | None = None) -> tuple[float, list[str]]:
    """How well one library photo fits, and the shared tags that say why."""
    total, why = 0.0, []
    styles = tags.get("style") or []
    if img.get("style") in styles:
        # The strongest style counts fully, a second one less.
        total += WEIGHTS["style"] * (1.0 if styles[0] == img["style"] else 0.6)
        why.append(img["style"])
    if tags.get("palette_family") and img.get("palette", {}).get("family") == tags["palette_family"]:
        total += WEIGHTS["palette_family"]
        why.append(f"{tags['palette_family']} palette")
    for field in LIST_FIELDS:
        shared = [v for v in tags.get(field, []) if v in (img.get(field) or [])]
        total += WEIGHTS[field] * len(shared)
        why += shared
    for field in ("texture", "furniture_style", "mood", "layout"):
        if tags.get(field) and img.get(field) == tags[field]:
            total += WEIGHTS[field]
            why.append(tags[field])
    if housing and housing in (img.get("housing_fit") or []):
        total += WEIGHTS["housing_fit"]
    if tier and img.get("budget_tier") == tier:
        total += WEIGHTS["budget_tier"]
    return total, why


def rank_for_room(label: str, tags: dict, housing: str | None = None,
                  tier: str | None = None, count: int = 6, alternates: int = 2) -> list[dict]:
    """Library photos for one room, best fit first.

    The top of the list is the closest matches; the last `alternates` slots go
    to the best photos in OTHER styles, so a homeowner can still discover that
    something outside what they uploaded suits them. Each result carries its
    score and the tags it shares with the homeowner's taste."""
    types = library_rooms(label)
    if not types:
        return []
    pool = [img for img in load_library()["images"] if img.get("room") in types]
    # A stand-in room type (a master bedroom for a small second bedroom)
    # counts slightly less than the room itself.
    ranked = []
    for img in pool:
        s, why = score(img, tags, housing, tier)
        s -= 0.5 * types.index(img["room"])
        ranked.append({**img, "match_score": round(s, 2), "match_why": why})
    ranked.sort(key=lambda r: (-r["match_score"], r["id"]))

    styles = set(tags.get("style") or [])
    main = [r for r in ranked if not styles or r["style"] in styles]
    others = [r for r in ranked if styles and r["style"] not in styles]
    n_main = max(count - alternates, 1) if others else count
    picked = main[:n_main]
    # Alternates: one per other style, best first, for variety.
    seen = set()
    for r in others:
        if len(picked) >= count:
            break
        if r["style"] not in seen:
            seen.add(r["style"])
            picked.append({**r, "alternate": True})
    # Not enough of either: top up from what is left.
    for r in ranked:
        if len(picked) >= count:
            break
        if all(r["id"] != p["id"] for p in picked):
            picked.append({**r, "alternate": bool(styles) and r["style"] not in styles})
    return picked


# ── Describing picks ──────────────────────────────────────────────────────────
def describe(img: dict) -> str:
    """One reference photo, in plain words, for the brief."""
    palette = img.get("palette") or {}
    colours = ", ".join(palette.get("colours") or [])
    bits = [
        f"{img.get('style', '')} {img.get('room', '')}".strip(),
        f"{palette.get('family', '')} palette" + (f" ({colours})" if colours else ""),
    ]
    if img.get("materials"):
        bits.append(" and ".join(img["materials"]))
    if img.get("lighting"):
        bits.append(" and ".join(img["lighting"]) + " lighting")
    for field, word in (("texture", "texture"), ("furniture_style", "furniture"),
                        ("layout", "layout")):
        if img.get(field):
            bits.append(f"{img[field]} {word}")
    if img.get("mood"):
        bits.append(f"{img['mood']} mood")
    if img.get("fixtures"):
        bits.append("with " + " and ".join(img["fixtures"]))
    text = "; ".join(b for b in bits if b)
    if img.get("notes"):
        text += f" — {img['notes']}"
    return text


def picks_summary(picks: dict[str, list[str]], labels: dict[str, str]) -> dict[str, str]:
    """Each room's picked references as one paragraph for the brief,
    keyed by room key. Unknown ids are skipped."""
    lib = images_by_id()
    out = {}
    for key, ids in (picks or {}).items():
        described = [describe(lib[i]) for i in ids if i in lib]
        if described:
            out[key] = (f"For {labels.get(key, key)} the homeowner picked these reference "
                        "photos as what feels like them: " + " | ".join(described) + ".")
    return out
