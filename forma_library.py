"""Forma reference library — curated sample images for Stage 3.

Stage 3 lets the homeowner pick sample images per room from this curated
library, filtered to the design style they chose. Those picks are copied into
their own uploads and read for real by the Stage 4 vision analysis, exactly
like an image they uploaded themselves.

The library is a STYLE reference only: its images are never shown as the
client's own room, and every record carries Unsplash attribution so the UI can
credit the photographer.
"""
from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).parent
_LIBRARY_PATH = _HERE / "forma_library.json"
# Local copies of every library image, named by id (FL-0001.jpg …). Served
# through /uploads/library/<id>.jpg like any other upload.
_IMAGE_DIR = _HERE / "uploads" / "library"

_CACHE: dict | None = None
_BY_ID: dict[str, dict] | None = None


def _load() -> dict:
    global _CACHE, _BY_ID
    if _CACHE is None:
        try:
            _CACHE = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _CACHE = {"images": [], "tag_vocabulary": {}, "budget_tiers": []}
        _BY_ID = {r.get("id"): r for r in _CACHE.get("images", []) if r.get("id")}
    return _CACHE


# ── Style / room mapping ─────────────────────────────────────────────────────
# The Stage 3 form posts one of these style keys. Map each to the library's
# controlled style vocabulary. A key may map to several library styles when the
# homeowner's label is broader than any single library style (e.g. "minimalist"
# spans the library's "modern minimalist" and "Japandi").
_STYLE_KEY_TO_LIBRARY: dict[str, list[str]] = {
    "minimalist":   ["modern minimalist", "Japandi"],
    "scandinavian": ["Scandinavian"],
    "japandi":      ["Japandi", "Scandinavian"],
    "industrial":   ["industrial"],
    "bohemian":     ["tropical", "mid-century"],   # library has no boho; nearest
    "contemporary": ["contemporary", "modern luxe"],
    "classical":    ["modern luxe", "contemporary"],  # library has no classical
    "tropical":     ["tropical"],
}

# Confirmed-room label -> library room key. Substring match, specific first.
# The key is the room's PREFERRED library room (its own type shown first).
_ROOM_LABEL_TO_LIBRARY: list[tuple[str, str]] = [
    # Bathrooms/toilets first — "Master Bathroom" must not match the "master"
    # bedroom rule below.
    ("bath", "bathroom"),
    ("toilet", "bathroom"),
    ("wc", "bathroom"),
    ("powder", "bathroom"),
    # Bedrooms. "ensuite" alone (no "bath") reads as a master bedroom.
    ("master", "master bedroom"),
    ("ensuite", "master bedroom"),
    ("bedroom", "secondary bedroom"),
    ("living", "living"),
    ("dining", "dining"),
    ("kitchen", "kitchen"),
    ("study", "study"),
    ("office", "study"),
    ("balcony", "balcony"),
    ("entry", "entryway"),
    ("foyer", "entryway"),
]

# Room "families": interchangeable library rooms for room types that come in
# multiples. When a style is thin for the exact room, any sibling in the same
# family stands in — a master-bedroom shot works for Bedroom 2, a bathroom
# shot for any toilet. Every library room in a family is pooled, with the
# room's own preferred type shown first.
_ROOM_FAMILIES: list[set[str]] = [
    {"master bedroom", "secondary bedroom"},
    {"bathroom"},   # single library key today, but grouped for clarity
]

# When a room has no matching library room (e.g. Service Yard, Household
# Shelter), fall back to these general rooms so the tab still shows the style.
_ROOM_FALLBACK = ["living", "dining"]


def library_room_key(room_label: str) -> str | None:
    """Map a confirmed-room label onto a library room key, or None."""
    low = (room_label or "").lower()
    for needle, key in _ROOM_LABEL_TO_LIBRARY:
        if needle in low:
            return key
    return None


def _family_of(library_room: str) -> list[str]:
    """The interchangeable library rooms for a room, its own type first."""
    for fam in _ROOM_FAMILIES:
        if library_room in fam:
            siblings = [r for r in fam if r != library_room]
            return [library_room] + sorted(siblings)
    return [library_room]


def _present(rec: dict, image_url_fn=None) -> dict:
    """Flatten a record for the template / JSON response."""
    img = rec.get("image") or {}
    src = rec.get("source") or {}
    rid = rec.get("id", "")
    local = _IMAGE_DIR / f"{rid}.jpg"
    # Prefer the local served copy; fall back to the remote thumb if missing.
    url = ""
    if image_url_fn and local.exists():
        url = image_url_fn(str(local))
    if not url:
        url = img.get("thumb_url") or img.get("url", "")
    return {
        "id": rid,
        "style": rec.get("style", ""),
        "room": rec.get("room", ""),
        "url": url,
        "dominant_colour": img.get("dominant_colour", "#e9e2d4"),
        "photographer": src.get("photographer", ""),
        "photographer_url": src.get("photographer_url", ""),
        "page_url": src.get("page_url", ""),
    }


def samples_for_style(style_key: str, rooms: list, per_room: int = 6,
                      image_url_fn=None) -> list[dict]:
    """Per-room sample images for the chosen style.

    Returns a list of {room_key, room_label, library_room, images:[...]}, one
    entry per confirmed room (in the order given), so the Stage 3 tabs can show
    the right samples under each tab. `image_url_fn` turns a local path into a
    served URL (pass app.upload_url); when omitted, remote thumbs are used.
    """
    lib = _load()
    images = lib.get("images") or []
    if not images:
        return []

    wanted_styles = _STYLE_KEY_TO_LIBRARY.get(
        (style_key or "").lower(), ["contemporary"])

    def pool_for(library_room: str) -> list[dict]:
        # Build the pool room by room across the family, the room's own type
        # first, so a master bedroom shows master shots before borrowing a
        # secondary-bedroom one — but a thin style still fills up from siblings.
        family = _family_of(library_room)

        pool: list[dict] = []
        seen: set = set()

        def add(recs):
            for r in recs:
                rid = r.get("id")
                if rid not in seen:
                    seen.add(rid)
                    pool.append(r)

        # 1) chosen style, each family room in preference order
        for room in family:
            add(r for r in images
                if r.get("room") == room and r.get("style") in wanted_styles)
        # 2) any style, each family room in preference order
        for room in family:
            add(r for r in images if r.get("room") == room)
        # 3) last resort: any image in the chosen style so the tab is never empty
        add(r for r in images if r.get("style") in wanted_styles)
        return pool

    out = []
    for room in rooms:
        label = room["label"] if isinstance(room, dict) else str(room)
        key = room["key"] if isinstance(room, dict) else str(room)
        lib_room = library_room_key(label)
        if lib_room is None:
            # No library equivalent — show the style's living/dining as a guide.
            recs = []
            for fb in _ROOM_FALLBACK:
                recs += [r for r in images
                         if r.get("room") == fb and r.get("style") in wanted_styles]
            lib_room = ""
        else:
            recs = pool_for(lib_room)

        seen, images_out = set(), []
        for rec in recs:
            rid = rec.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            images_out.append(_present(rec, image_url_fn))
            if len(images_out) >= per_room:
                break

        out.append({
            "room_key": key,
            "room_label": label,
            "library_room": lib_room,
            "images": images_out,
        })
    return out


def record_by_id(image_id: str) -> dict | None:
    """The raw library record for an id, or None."""
    _load()
    return (_BY_ID or {}).get(image_id)


def local_image_path(image_id: str) -> Path | None:
    """Path to the downloaded local copy of a library image, if it exists."""
    p = _IMAGE_DIR / f"{image_id}.jpg"
    return p if p.exists() else None


def credit_for(image_id: str) -> dict:
    """Attribution fields for a library image id (empty strings if unknown)."""
    rec = record_by_id(image_id) or {}
    src = rec.get("source") or {}
    return {
        "photographer": src.get("photographer", ""),
        "photographer_url": src.get("photographer_url", ""),
        "page_url": src.get("page_url", ""),
    }
