"""
FORMA — Design Inspiration Agent
Flask backend with AWS Bedrock (Claude Sonnet 4.5) stub.
"""

import os
import json
import uuid
import base64
import textwrap
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, send_file, has_request_context
)
from werkzeug.utils import secure_filename

import clients

# ─────────────────────────────────────────────────────────────────────────────
# App config
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv(".env.local")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "forma-dev-secret-2026")

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

# LLM Gateway config
LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL")
LLM_GATEWAY_API_KEY = os.environ.get("LLM_GATEWAY_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL")

# ─────────────────────────────────────────────────────────────────────────────
# Room definitions — keyed by housing type
# ─────────────────────────────────────────────────────────────────────────────
ROOM_CATALOGUE = {
    # HDB flat naming counts LIVING + BEDROOMS (kitchen and bathrooms are extra):
    #   2-room = living + 1 bedroom      4-room = living + 3 bedrooms
    #   3-room = living + 2 bedrooms     5-room = living + dining + 3 bedrooms
    "hdb_2room": ["Living Room", "Bedroom", "Kitchen", "Bathroom",
                  "Service Yard"],
    "hdb_3room": ["Living Room", "Master Bedroom", "Bedroom 2", "Kitchen",
                  "Master Bathroom", "Bathroom", "Service Yard"],
    "hdb_4room": ["Living Room", "Master Bedroom", "Bedroom 2", "Bedroom 3",
                  "Kitchen", "Master Bathroom", "Bathroom", "Service Yard",
                  "Household Shelter"],
    "hdb_5room": ["Living Room", "Dining Room", "Master Bedroom", "Bedroom 2",
                  "Bedroom 3", "Kitchen", "Master Bathroom", "Bathroom",
                  "Service Yard", "Household Shelter"],
    "condo":     ["Living Room", "Dining Room", "Kitchen", "Master Bedroom",
                   "Bedroom 2", "Master Bathroom", "Bathroom", "Study",
                   "Balcony"],
    "landed":    ["Living Room", "Dining Room", "Kitchen", "Master Bedroom",
                   "Bedroom 2", "Bedroom 3", "Master Bathroom", "Bathroom",
                   "Study", "Garage", "Garden / Outdoor", "Utility Room"],
    "studio":    ["Open Living / Sleeping Area", "Kitchen", "Bathroom"],
    "shophouse": ["Living Room", "Kitchen", "Master Bedroom", "Bedroom 2",
                   "Bathroom", "Ground-Floor Space"],
}

# Items per room for checklist
ROOM_ITEMS = {
    "Living Room":          ["Sofa", "Coffee Table", "TV Console", "Display Shelving",
                              "Armchair", "Side Table", "Floor Lamp", "Carpet / Rug", "Curtains"],
    "Dining Room":          ["Dining Table", "Dining Chairs", "Sideboard / Buffet",
                              "Bar Cabinet", "Pendant Light", "Feature Wall"],
    "Kitchen":              ["Refrigerator", "Oven", "Microwave", "Dishwasher", "Hob",
                              "Hood", "Island / Breakfast Bar", "Pantry Storage",
                              "Wine Chiller", "Washing Machine"],
    "Master Bedroom":       ["King Bed", "Wardrobe", "Dresser", "Bedside Tables",
                              "Study Desk", "TV", "Walk-in Closet", "Ceiling Fan"],
    "Bedroom":              ["Queen / Single Bed", "Wardrobe", "Study Desk",
                              "Bedside Table", "Ceiling Fan"],
    "Bedroom 2":            ["Queen Bed", "Wardrobe", "Study Desk", "Bedside Table"],
    "Bedroom 3":            ["Single Bed", "Wardrobe", "Study Desk"],
    "Bedroom 4":            ["Single Bed", "Wardrobe"],
    "Bathroom":             ["Shower", "Bathtub", "Vanity", "Storage Cabinet", "Mirror"],
    "Master Bathroom":      ["Rainfall Shower", "Freestanding Bathtub", "Double Vanity",
                              "Heated Towel Rail", "Smart Mirror"],
    "Study":                ["Desk", "Bookshelf", "Ergonomic Chair", "Monitor Arm",
                              "Storage Cabinets"],
    "Balcony":              ["Outdoor Sofa", "Dining Set", "Planters", "Louvres"],
    "Garage":               ["Storage Cabinets", "Workbench", "EV Charger"],
    "Garden / Outdoor":     ["Decking", "Outdoor Furniture", "BBQ Pit", "Pool",
                              "Landscaping", "Pergola"],
    "Utility Room":         ["Washer / Dryer", "Ironing Station", "Storage Shelves"],
    "Ground-Floor Space":   ["Reception Desk", "Display Shelving", "POS Counter"],
    "Open Living / Sleeping Area": ["Loft Bed / Murphy Bed", "Sofa", "Kitchen Bar",
                                     "Storage Ottoman", "Wardrobe"],
    "Service Yard": ["Washing machine", "Dryer", "Laundry rack",
                     "Utility sink", "Storage shelving", "Water heater"],
    "Household Shelter": ["Shelving system", "Storage boxes", "Bicycle rack",
                          "Ventilation cover", "Door organiser"],
}

HOUSING_LABELS = {
    "hdb_2room": "2-Room HDB", "hdb_3room": "3-Room HDB",
    "hdb_4room": "4-Room HDB", "hdb_5room": "5-Room HDB",
    "condo": "Condominium",    "landed": "Landed Property",
    "studio": "Studio Apartment", "shophouse": "Shophouse",
}

# Colours for the 2D floor plan SVG
ROOM_COLOURS = [
    "#C9D4E0", "#D4C5B0", "#B8D4C8", "#E8D5C4",
    "#D5C9E0", "#C8D4B8", "#E0D4C9", "#C9E0D4",
    "#E0C9D4", "#D4E0C9", "#C9D4B8", "#B8C9D4",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_obj, subfolder: str = "") -> str | None:
    if not file_obj or file_obj.filename == "":
        return None
    if allowed_file(file_obj.filename):
        fname = f"{uuid.uuid4().hex}_{secure_filename(file_obj.filename)}"
        dest = UPLOAD_FOLDER / subfolder
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / fname
        file_obj.save(str(path))
        return str(path)
    return None


def get_rooms_for_type(housing_type: str) -> list[dict]:
    """Return list of {key, label, items} dicts for the given housing type."""
    # Prefer the room list the model identified in step 1; fall back to the
    # static catalogue when there is none (or outside a request context).
    ai_rooms = session.get("ai_rooms") if has_request_context() else None
    room_names = ai_rooms or ROOM_CATALOGUE.get(housing_type, ROOM_CATALOGUE["hdb_4room"])
    rooms = []
    for name in room_names:
        key = name.lower().replace(" ", "_").replace("/", "_")
        rooms.append({
            "key":   key,
            "label": name,
            "items": ROOM_ITEMS.get(name, []),
        })
    return rooms


def image_to_base64(path: str) -> tuple[str, str]:
    """Read an image file and return (base64_data, media_type)."""
    ext = Path(path).suffix.lower().lstrip(".")
    media_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
    media_type = media_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, media_type


# ─────────────────────────────────────────────────────────────────────────────
# LLM Gateway wrapper
# ─────────────────────────────────────────────────────────────────────────────
def call_llm(messages: list, system: str = "", max_tokens: int = 2048) -> str:
    """
    Call the team's LLM Gateway.
    Falls back to the existing mock response if the gateway is unavailable.
    """

    if not LLM_GATEWAY_URL or not LLM_GATEWAY_API_KEY or not LLM_MODEL:
        app.logger.warning(
            "LLM Gateway configuration missing — using mock response"
        )
        return _mock_bedrock_response(messages)

    gateway_messages = []

    if system:
        gateway_messages.append({
            "role": "system",
            "content": system
        })

    gateway_messages.extend(messages)

    payload = {
        "model": LLM_MODEL,
        "messages": gateway_messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens
        }
    }

    req = urllib.request.Request(
        f"{LLM_GATEWAY_URL.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": LLM_GATEWAY_API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["message"]["content"]

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        app.logger.warning(
            f"LLM Gateway HTTP error {e.code}: {error_body} — using mock response"
        )

    except Exception as e:
        app.logger.warning(
            f"LLM Gateway call failed: {e} — using mock response"
        )

    return _mock_bedrock_response(messages)


def _mock_bedrock_response(messages: list) -> str:
    """Return a realistic-looking stub response for demo purposes."""
    last = messages[-1]["content"]
    text = last if isinstance(last, str) else (last[0].get("text", "") if last else "")

    # NOTE: the brief prompt also mentions "rooms", so exclude it here or the
    # brief request would be answered with the room-analysis JSON.
    if ("rooms" in text.lower() or "segregate" in text.lower()) \
            and "brief" not in text.lower():
        return json.dumps({
            "rooms": ["Living Room", "Dining Room", "Kitchen",
                      "Master Bedroom", "Bedroom 2", "Master Bathroom", "Bathroom"],
            "summary": "Based on your 4-Room HDB at approximately 95 sqm, I've identified 7 distinct spaces. The open-plan living and dining area flows naturally into the kitchen \u2014 a typical layout that gives excellent flexibility for your design. The master suite includes a dedicated bathroom, while a second bedroom and shared bathroom complete the private zone.",
            "observations": [
                "Living and dining read as one continuous space \u2014 treat them as a single visual zone.",
                "The kitchen sits at the service end of the flat, next to the yard.",
                "Both bedrooms share a wall, so acoustic separation is worth raising early."
            ],
            "source": "housing_type_only",
            "confidence": "medium",
        })

    if "brief" in text.lower() or "design brief" in text.lower():
        return """
<div class="ai-brief-content">
  <p><strong>Project Overview</strong><br/>
  This is a thoughtfully composed contemporary interior that draws on a warm neutral palette to create a sense of calm cohesion throughout. The brief centres on livability — every room should feel purposeful, uncluttered, and quietly luxurious.</p>

  <p><strong>Design Direction</strong><br/>
  The overarching aesthetic leans Japandi: a distillation of Japanese wabi-sabi restraint and Scandinavian warmth. Expect clean silhouettes softened by natural textures — raw linen, oiled oak, handmade ceramic. The palette moves from light greige in the social spaces to deeper, more enveloping tones in the sleeping areas.</p>

  <p><strong>Material Story</strong><br/>
  Primary: Warm white plaster walls with a matte finish. Secondary: Oiled white oak for joinery and flooring. Accents: Aged brass hardware, washi paper pendants, tactile linen upholstery. Avoid high-gloss surfaces throughout.</p>

  <p><strong>Lighting Strategy</strong><br/>
  Layer ambient, task, and accent lighting in every room. Prioritise dimmable circuits. Feature pendants over dining and bedside. Recessed strip lighting under joinery and behind feature walls creates depth without visual clutter.</p>

  <p><strong>Key Considerations</strong><br/>
  — Maximise natural light flow between living and dining<br/>
  — All storage to be integrated and concealed where possible<br/>
  — Ensure acoustic privacy between bedrooms<br/>
  — Sustainable and low-VOC materials preferred</p>
</div>
"""

    # generic room concept
    return "A serene, considered space that balances function with quiet beauty. Natural light is maximised, storage is integrated, and every element earns its place. The material palette echoes the home's overarching warmth — oiled oak, linen, and aged brass — while bespoke joinery provides the room's defining character."

SPACE_ANALYSIS_SYSTEM = (
    "You are an interior designer who reads residential floor plans for a living, "
    "working mainly with Singapore homes — HDB flats, condominiums and landed houses. "
    "You are precise about what you can actually see, and honest about what you cannot. "
    "You never invent measurements that are not legible in the plan."
)


def build_space_analysis_request(
    housing_type: str,
    floor_size: str,
    num_floors: str,
    notes: str,
    floor_plan_path: str | None = None,
) -> tuple[list, str]:
    """Build the (messages, system) pair for the step-1 space analysis.
    Makes no API call — print the result to inspect the prompt for free."""

    prompt = textwrap.dedent(f"""
        A homeowner has given us the following about their space.

        Housing type : {HOUSING_LABELS.get(housing_type, housing_type)}
        Approx. size : {floor_size or 'not given'} sqm
        Floors       : {num_floors or '1'}
        Their notes  : {notes or 'none'}
        Floor plan   : {'attached as an image' if floor_plan_path else 'not provided'}

        Task: list the individual rooms in this home, so we can ask about each one separately.

        If a floor plan is attached, read it. Use the room labels printed on the plan, and
        include service spaces that appear (Household Shelter, Service Yard, Balcony, Store, WC).
        If no plan is attached, infer a typical layout for this housing type and say so.

        Rules:
        - Use names a Singapore homeowner would recognise.
        - Split rooms only where a designer would treat them separately.
        - Do not invent measurements you cannot read from the plan.
        - Set "source" to "floorplan" ONLY if you actually read rooms off an attached plan.

        Respond with ONLY valid JSON, no prose before or after:
        {{"rooms": ["Living Room", "Kitchen"],
          "summary": "2-3 sentences the homeowner reads on the next page.",
          "observations": ["short note on layout, light or flow"],
          "source": "floorplan",
          "confidence": "high"}}
    """).strip()

    content = [{"type": "text", "text": prompt}]
    if floor_plan_path:
        data, media_type = image_to_base64(floor_plan_path)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })

    return [{"role": "user", "content": content}], SPACE_ANALYSIS_SYSTEM


# ─────────────────────────────────────────────────────────────────────────────
# STUB — stands in for the AI floor-plan read.
#
# Active whenever Bedrock is unavailable (or force it with USE_FLOORPLAN_STUB=1
# / disable with USE_FLOORPLAN_STUB=0). Returns exactly the same dict shape as
# generate_room_summary(), so swapping to the real read is deleting one early
# return — nothing downstream changes.
# ─────────────────────────────────────────────────────────────────────────────
USE_FLOORPLAN_STUB = os.environ.get("USE_FLOORPLAN_STUB", "auto").lower()


def _floorplan_stub_enabled() -> bool:
    if USE_FLOORPLAN_STUB in ("1", "true", "yes", "on"):
        return True
    if USE_FLOORPLAN_STUB in ("0", "false", "no", "off"):
        return False

    return True # temp


def stub_read_floorplan(housing_type, floor_size="", num_floors="1",
                        notes="", floor_plan_path=None) -> dict:
    """Derive the room list from the housing type alone. No model call."""
    rooms = list(ROOM_CATALOGUE.get(housing_type, ROOM_CATALOGUE["hdb_4room"]))
    label = HOUSING_LABELS.get(housing_type, housing_type)

    beds  = [r for r in rooms if "Bedroom" in r]
    baths = [r for r in rooms if "Bathroom" in r]

    def plural(n, word):
        return f"{n} {word}" + ("" if n == 1 else "s")

    summary = (
        f"Your {label}"
        + (f", around {floor_size} sqm," if floor_size else "")
        + f" works out to {len(rooms)} spaces: {plural(len(beds), 'bedroom')} "
        f"and {plural(len(baths), 'bathroom')}, plus the shared living areas."
    )
    if (num_floors or "1") not in ("1", ""):
        summary += f" Spread over {num_floors} floors."

    observations = [
        "Room list is derived from the housing type — upload a floor plan for a closer match.",
        "Remove any room you don't have, and it won't appear in your brief.",
    ]
    if notes:
        observations.append(f"Your note: {notes}")

    return {
        "rooms":        rooms,
        "summary":      summary,
        "observations": observations,
        "source":       "housing_type_only",
        "confidence":   "low",
    }


def generate_room_summary(housing_type, floor_size, notes,
                          num_floors="1", floor_plan_path=None) -> dict:
    """Identify the rooms in this home, reading the floor plan when one was uploaded.

    Always returns the same five keys so mock mode and real mode behave alike.
    """
    # ── STUB: delete these two lines once the real floor-plan read works ──
    if _floorplan_stub_enabled():
        return stub_read_floorplan(housing_type, floor_size, num_floors,
                                   notes, floor_plan_path)

    messages, system = build_space_analysis_request(
        housing_type, floor_size, num_floors, notes, floor_plan_path
    )
    raw = call_llm(messages, system=system)

    fallback_rooms = ROOM_CATALOGUE.get(housing_type, ROOM_CATALOGUE["hdb_4room"])

    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, ValueError, TypeError):
        app.logger.warning("Space analysis: model did not return JSON - using catalogue")
        return {
            "rooms":        fallback_rooms,
            "summary":      raw if isinstance(raw, str) else "",
            "observations": [],
            "source":       "housing_type_only",
            "confidence":   "low",
        }

    # A bad response must never empty out steps 2-4.
    raw_rooms = data.get("rooms")
    rooms = ([str(r).strip() for r in raw_rooms if str(r).strip()]
             if isinstance(raw_rooms, list) else [])
    if not rooms:
        rooms = fallback_rooms

    raw_obs = data.get("observations")
    observations = ([str(o).strip() for o in raw_obs if str(o).strip()]
                    if isinstance(raw_obs, list) else [])

    # The model cannot have read a plan we never sent it.
    source = data.get("source")
    if not floor_plan_path or source not in ("floorplan", "housing_type_only"):
        source = "floorplan" if floor_plan_path and source == "floorplan" else "housing_type_only"

    confidence = data.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    return {
        "rooms":        rooms,
        "summary":      str(data.get("summary", "")).strip(),
        "observations": observations,
        "source":       source,
        "confidence":   confidence,
    }


def generate_design_brief(project: dict) -> str:
    """Generate the overall design brief HTML."""
    rooms_text = ", ".join(r["label"] for r in project.get("rooms", []))
    requirements_text = ""
    for room in project.get("rooms", []):
        key = room["key"]
        prompt_val = project.get(f"{key}_prompt", "")
        items_val  = project.get(f"{key}_items", [])
        if prompt_val or items_val:
            requirements_text += f"\n{room['label']}: {prompt_val}. Items: {', '.join(items_val)}."

    prompt = textwrap.dedent(f"""
        Create a comprehensive interior design brief in HTML format for:
        - Housing: {project.get('housing_type_label', '')}
        - Style: {project.get('design_style', '')}
        - Colour palette: {project.get('colour_name', '')}
        - Rooms: {rooms_text}
        - Requirements:{requirements_text}

        Write a polished, editorial-quality design brief that an interior designer would be proud to present.
        Use <p> and <strong> tags. Cover: project overview, design direction, material story,
        lighting strategy, and key considerations. Keep it under 400 words.
        Respond with ONLY the HTML content, no surrounding tags.
    """)

    return call_llm(
        [{"role": "user", "content": prompt}],
        system="You are a senior interior designer writing a premium design brief.",
        max_tokens=1024
    )


def generate_room_concept(room: dict, style: str, palette: str, prompt_text: str) -> str:
    """Generate a short room concept paragraph."""
    msg = textwrap.dedent(f"""
        Room: {room['label']}
        Design style: {style}
        Colour palette: {palette}
        Client requirements: {prompt_text or 'not specified'}
        Items needed: {', '.join(room.get('items_selected', [])) or 'not specified'}

        Write a single evocative paragraph (80–120 words) describing the design concept for this room.
        Focus on mood, materials, lighting, and spatial flow. Be specific and design-forward.
    """)

    return call_llm(
        [{"role": "user", "content": msg}],
        system="You are a senior interior designer crafting room concept descriptions.",
        max_tokens=256
    )


def generate_floor_plan_svg(rooms: list[dict]) -> str:
    """Generate a simple schematic 2D floor plan as inline SVG."""
    n = len(rooms)
    cols = min(3, n)
    rows = -(-n // cols)  # ceiling division

    w, h   = 600, 400
    pad    = 20
    gutter = 10
    cell_w = (w - 2 * pad - gutter * (cols - 1)) // cols
    cell_h = (h - 2 * pad - gutter * (rows - 1)) // rows

    svg_parts = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;font-family:Inter,sans-serif;">',
        f'<rect width="{w}" height="{h}" fill="#F8F6F2" rx="4"/>',
    ]

    for i, room in enumerate(rooms):
        col = i % cols
        row = i // cols
        x = pad + col * (cell_w + gutter)
        y = pad + row * (cell_h + gutter)
        colour = room.get("colour", "#C9D4E0")

        svg_parts.append(
            f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" '
            f'fill="{colour}" fill-opacity="0.7" stroke="#888" stroke-width="1" rx="3"/>'
        )
        # Room label
        label = room["label"]
        if len(label) > 16:
            label = label[:14] + "…"
        svg_parts.append(
            f'<text x="{x + cell_w // 2}" y="{y + cell_h // 2 - 6}" '
            f'text-anchor="middle" font-size="11" fill="#333" font-weight="500">{label}</text>'
        )
        # Dimensions hint
        svg_parts.append(
            f'<text x="{x + cell_w // 2}" y="{y + cell_h // 2 + 10}" '
            f'text-anchor="middle" font-size="9" fill="#777">approx. area</text>'
        )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Session <-> saved brief
#
# The cookie holds only client_id/email. Everything else lives in the JSON
# store, so it survives a closed browser and the cookie stays small.
# ─────────────────────────────────────────────────────────────────────────────
BRIEF_KEYS = ("step1", "ai_rooms", "ai_room_summary", "requirements", "inspiration")


def persist_brief():
    """Copy the working session into the client's saved brief. No-op if the
    visitor never identified themselves, so the app still works without login."""
    cid = session.get("client_id")
    if not cid:
        return
    clients.save_brief(cid, {k: session[k] for k in BRIEF_KEYS if k in session})


def hydrate_session(client):
    """Load a client's saved brief back into the session."""
    brief = clients.load_brief(client["client_id"])
    for k in BRIEF_KEYS:
        session.pop(k, None)
        if k in brief:
            session[k] = brief[k]
    session["client_id"] = client["client_id"]
    session["email"] = client["email"]
    session.modified = True
    return brief


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    # Deliberately does NOT clear the session - landing on the logo used to
    # destroy a half-finished brief. Use /start to switch client or reset.
    return render_template("index.html", current_step=0,
                           signed_in_as=session.get("email"))


# ── Step 0: Who is this? ──────────────────────────────────────────────────────
@app.route("/start", methods=["GET", "POST"])
def start():
    """Email-only sign in. No password: an email is enough to reattach someone
    to their saved brief, and the code/magic-link step slots in here later."""
    if request.method == "POST":
        if request.form.get("action") == "new_project":
            for k in BRIEF_KEYS:
                session.pop(k, None)
            if session.get("client_id"):
                clients.save_brief(session["client_id"], {})
            session.modified = True
            return redirect(url_for("step1"))

        email = clients.normalise_email(request.form.get("email"))
        if not clients.is_valid_email(email):
            flash("That doesn't look like an email address.", "error")
            return render_template("start.html", current_step=0, email=email)

        client, is_new = clients.find_or_create_client(email)
        brief = hydrate_session(client)

        if is_new or not brief:
            return redirect(url_for("step1"))
        return render_template("start.html", current_step=0, email=email,
                               returning=True,
                               progress=clients.brief_progress(brief))

    return render_template("start.html", current_step=0,
                           email=session.get("email", ""))


# ── Step 1: Housing & Floor Plan ─────────────────────────────────────────────
@app.route("/step1", methods=["GET", "POST"])
def step1():
    if request.method == "POST":
        housing_type = request.form.get("housing_type")
        if not housing_type:
            flash("Please select a housing type.", "error")
            return redirect(url_for("step1"))

        floor_plan_path = None
        if "floor_plan" in request.files:
            floor_plan_path = save_upload(request.files["floor_plan"], "floorplans")

        # Ask AI to identify rooms
        room_data = generate_room_summary(
        housing_type,
        request.form.get("floor_size", ""),
        request.form.get("space_notes", ""),
        num_floors=request.form.get("num_floors", "1"),
        floor_plan_path=floor_plan_path,
        )

        session["step1"] = {
            "housing_type":       housing_type,
            "housing_type_label": HOUSING_LABELS.get(housing_type, housing_type),
            "floor_size":         request.form.get("floor_size", ""),
            "num_floors":         request.form.get("num_floors", "1"),
            "space_notes":        request.form.get("space_notes", ""),
            "floor_plan_path":    floor_plan_path,
        }
        session["ai_rooms"]        = room_data.get("rooms", ROOM_CATALOGUE.get(housing_type, []))
        session["ai_room_summary"] = room_data.get("summary", "")
        session.modified = True

        persist_brief()
        return redirect(url_for("step2"))

    return render_template("step1.html", current_step=1,
                           form_data=session.get("step1"))


# ── Step 2: Inspiration ───────────────────────────────────────────────────────
@app.route("/step2", methods=["GET", "POST"])
def step2():
    """Step 2 — Room requirements. Runs BEFORE inspiration, so the client
    settles what rooms exist and what they need before picking a look."""
    if "step1" not in session:
        return redirect(url_for("step1"))

    housing_type = session["step1"]["housing_type"]
    rooms = get_rooms_for_type(housing_type)

    if request.method == "POST":
        # Each room card carries a hidden "kept_rooms" input holding its current
        # label, so removed cards vanish from this list and renamed/added ones
        # arrive with their new names. Order is DOM order.
        kept = [r.strip() for r in request.form.getlist("kept_rooms") if r.strip()]
        if kept:
            seen, unique = set(), []
            for label in kept:                      # guard against duplicates
                if label.lower() not in seen:
                    seen.add(label.lower())
                    unique.append(label)
            session["ai_rooms"] = unique
            session.modified = True
            rooms = get_rooms_for_type(housing_type)

        req_data = {}
        for room in rooms:
            key = room["key"]
            req_data[f"{key}_prompt"]      = request.form.get(f"{key}_prompt", "")
            req_data[f"{key}_items"]       = request.form.getlist(f"{key}_items")
            req_data[f"{key}_budget"]      = request.form.get(f"{key}_budget", "")
            req_data[f"{key}_priority"]    = request.form.get(f"{key}_priority", "medium")
            req_data[f"{key}_constraints"] = request.form.get(f"{key}_constraints", "")

        req_data["project_notes"] = request.form.get("project_notes", "")
        session["requirements"] = req_data
        session.modified = True
        persist_brief()
        return redirect(url_for("step3"))

    return render_template("step2.html", current_step=2, rooms=rooms,
                           ai_room_summary=session.get("ai_room_summary", ""),
                           saved=session.get("requirements", {}))


# ── Step 3: Inspiration ───────────────────────────────────────────────────────
@app.route("/step3", methods=["GET", "POST"])
def step3():
    """Step 3 — Inspiration images, style and palette, per confirmed room."""
    if "step1" not in session:
        return redirect(url_for("step1"))

    housing_type = session["step1"]["housing_type"]
    rooms = get_rooms_for_type(housing_type)

    if request.method == "POST":
        style   = request.form.get("design_style", "")
        palette = request.form.get("colour_palette", "")
        colour_hex, colour_name = (palette.split("|") + ["", ""])[:2]

        saved_inspo = {}
        for room in rooms:
            key = room["key"]
            files = request.files.getlist(f"inspo_{key}")
            paths = [save_upload(f, f"inspo/{key}") for f in files if f and f.filename]
            saved_inspo[key] = [p for p in paths if p]

        overall_files = request.files.getlist("inspo_overall")
        saved_inspo["overall"] = [
            save_upload(f, "inspo/overall") for f in overall_files if f and f.filename
        ]

        session["inspiration"] = {
            "design_style":   style,
            "colour_palette": palette,
            "colour_hex":     colour_hex.strip(),
            "colour_name":    colour_name.strip() or "Custom",
            "custom_colour":  request.form.get("custom_colour", ""),
            "inspo_paths":    saved_inspo,
            "vibes":          {r["key"]: request.form.get(f"vibe_{r['key']}", "") for r in rooms},
        }
        session.modified = True
        persist_brief()
        return redirect(url_for("step4"))

    return render_template("step3.html", current_step=3, rooms=rooms,
                           ai_room_summary=session.get("ai_room_summary", ""),
                           saved=session.get("inspiration", {}))


# ── Step 4: Results ────────────────────────────────────────────────────────────
@app.route("/step4")
def step4():
    for step, route in (("step1", "step1"), ("requirements", "step2"),
                        ("inspiration", "step3")):
        if step not in session:
            return redirect(url_for(route))

    s1 = session["step1"]
    s2 = session["inspiration"]      # style / palette / inspo images
    s3 = session["requirements"]     # per-room items, budget, prompts
    housing_type = s1["housing_type"]
    rooms_base   = get_rooms_for_type(housing_type)

    # Build project context dict for AI
    project = {**s1, **s2}
    project["rooms"] = rooms_base

    # Generate AI brief
    ai_brief = generate_design_brief({**project, **s3})

    # Generate per-room concepts + assign colours
    room_results = []
    for i, room in enumerate(rooms_base):
        key = room["key"]
        concept = generate_room_concept(
            {**room, "items_selected": s3.get(f"{key}_items", [])},
            style      = s2.get("design_style", ""),
            palette    = s2.get("colour_name", ""),
            prompt_text= s3.get(f"{key}_prompt", ""),
        )
        room_results.append({
            "key":      key,
            "label":    room["label"],
            "concept":  concept,
            "items":    s3.get(f"{key}_items", []),
            "priority": s3.get(f"{key}_priority", "medium"),
            "budget":   s3.get(f"{key}_budget", ""),
            "colour":   ROOM_COLOURS[i % len(ROOM_COLOURS)],
        })

    floor_plan_svg = generate_floor_plan_svg(room_results)

    return render_template("step4.html", current_step=4,
                           project=project,
                           ai_brief=ai_brief,
                           room_results=room_results,
                           floor_plan_svg=floor_plan_svg)


# ── Regenerate ────────────────────────────────────────────────────────────────
@app.route("/regenerate", methods=["POST"])
def regenerate():
    # Simply re-run step4 — session data is preserved
    return redirect(url_for("step4"))


# ── Export brief as plain text ─────────────────────────────────────────────────
@app.route("/export-brief")
def export_brief():
    if "step1" not in session:
        return redirect(url_for("index"))

    s1 = session.get("step1", {})
    s2 = session.get("inspiration", {})
    s3 = session.get("requirements", {})
    housing_type = s1.get("housing_type", "")
    rooms_base   = get_rooms_for_type(housing_type)

    lines = [
        "FORMA — INTERIOR DESIGN BRIEF",
        "=" * 60,
        f"Housing Type : {s1.get('housing_type_label', '')}",
        f"Floor Size   : {s1.get('floor_size', 'N/A')} sqm",
        f"Design Style : {s2.get('design_style', 'N/A')}",
        f"Colour Palette: {s2.get('colour_name', 'N/A')}",
        "",
        "ROOM REQUIREMENTS",
        "-" * 60,
    ]
    for room in rooms_base:
        key = room["key"]
        lines += [
            f"\n{room['label'].upper()}",
            f"  Prompt      : {s3.get(f'{key}_prompt', 'N/A')}",
            f"  Items       : {', '.join(s3.get(f'{key}_items', [])) or 'N/A'}",
            f"  Budget      : {s3.get(f'{key}_budget', 'N/A')}",
            f"  Priority    : {s3.get(f'{key}_priority', 'N/A')}",
            f"  Constraints : {s3.get(f'{key}_constraints', 'N/A')}",
        ]

    lines += [
        "",
        "PROJECT NOTES",
        "-" * 60,
        s3.get("project_notes", "None"),
        "",
        "Generated by FORMA — Powered by AWS Bedrock / Claude Sonnet 4.5",
    ]

    brief_text = "\n".join(lines)
    brief_path = UPLOAD_FOLDER / "design_brief.txt"
    brief_path.write_text(brief_text, encoding="utf-8")

    return send_file(str(brief_path), as_attachment=True,
                     download_name="FORMA_Design_Brief.txt",
                     mimetype="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
