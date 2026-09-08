"""
FORMA — Design Inspiration Agent
Flask backend with AWS Bedrock (Claude Sonnet 4.5) stub.
"""

import os
import json
import uuid
import base64
import textwrap
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, send_file
)
from werkzeug.utils import secure_filename

# ── Optional: real Bedrock client (comment out if SDK not installed) ──────────
try:
    import boto3
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# App config
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "forma-dev-secret-2026")

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}

# AWS Bedrock config — set these env vars when you have the API
AWS_REGION        = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID  = "us.anthropic.claude-sonnet-4-5-20251001-v1:0"

# ─────────────────────────────────────────────────────────────────────────────
# Room definitions — keyed by housing type
# ─────────────────────────────────────────────────────────────────────────────
ROOM_CATALOGUE = {
    "hdb_2room": ["Living Room", "Kitchen", "Bedroom", "Bathroom"],
    "hdb_3room": ["Living Room", "Kitchen", "Master Bedroom", "Bedroom", "Bathroom"],
    "hdb_4room": ["Living Room", "Dining Room", "Kitchen", "Master Bedroom",
                   "Bedroom 2", "Bedroom 3", "Bathroom", "Master Bathroom"],
    "hdb_5room": ["Living Room", "Dining Room", "Kitchen", "Master Bedroom",
                   "Bedroom 2", "Bedroom 3", "Bedroom 4", "Bathroom",
                   "Master Bathroom", "Study"],
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
    room_names = ROOM_CATALOGUE.get(housing_type, ROOM_CATALOGUE["hdb_4room"])
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
# AWS Bedrock wrapper
# ─────────────────────────────────────────────────────────────────────────────
def call_bedrock(messages: list, system: str = "", max_tokens: int = 2048) -> str:
    """
    Call Claude Sonnet 4.5 via AWS Bedrock.
    Falls back to a mock response when credentials are unavailable.
    """
    if BEDROCK_AVAILABLE:
        try:
            client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system:
                body["system"] = system

            response = client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
        except Exception as e:
            app.logger.warning(f"Bedrock call failed: {e} — using mock response")

    # ── STUB: mock response when Bedrock is unavailable ──────────────────────
    return _mock_bedrock_response(messages)


def _mock_bedrock_response(messages: list) -> str:
    """Return a realistic-looking stub response for demo purposes."""
    last = messages[-1]["content"]
    text = last if isinstance(last, str) else (last[0].get("text", "") if last else "")

    if "rooms" in text.lower() or "segregate" in text.lower():
        return json.dumps({
            "rooms": ["Living Room", "Dining Room", "Kitchen",
                      "Master Bedroom", "Bedroom 2", "Master Bathroom", "Bathroom"],
            "summary": "Based on your 4-Room HDB at approximately 95 sqm, I've identified 7 distinct spaces. The open-plan living and dining area flows naturally into the kitchen — a typical layout that gives excellent flexibility for your design. The master suite includes a dedicated bathroom, while a second bedroom and shared bathroom complete the private zone."
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


def generate_room_summary(housing_type: str, floor_size: str, notes: str) -> dict:
    """Ask AI to identify rooms from housing type."""
    prompt = textwrap.dedent(f"""
        Housing type: {HOUSING_LABELS.get(housing_type, housing_type)}
        Approximate size: {floor_size or 'unknown'} sqm
        Additional notes: {notes or 'none'}

        Segregate this home into its individual rooms and provide:
        1. A JSON list of room names under the key "rooms"
        2. A brief human-readable "summary" of the layout (2–3 sentences)

        Respond ONLY with valid JSON in this exact format:
        {{"rooms": ["Room 1", "Room 2", ...], "summary": "..."}}
    """)

    raw = call_bedrock([{"role": "user", "content": prompt}],
                       system="You are an expert interior design consultant specialising in Singapore residential spaces.")
    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
        rooms = ROOM_CATALOGUE.get(housing_type, ROOM_CATALOGUE["hdb_4room"])
        return {"rooms": rooms, "summary": raw}


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

    return call_bedrock(
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

    return call_bedrock(
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
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    session.clear()
    return render_template("index.html", current_step=0)


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

        return redirect(url_for("step2"))

    return render_template("step1.html", current_step=1,
                           form_data=session.get("step1"))


# ── Step 2: Inspiration ───────────────────────────────────────────────────────
@app.route("/step2", methods=["GET", "POST"])
def step2():
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

        # overall
        overall_files = request.files.getlist("inspo_overall")
        saved_inspo["overall"] = [
            save_upload(f, "inspo/overall") for f in overall_files if f and f.filename
        ]

        session["step2"] = {
            "design_style":  style,
            "colour_palette": palette,
            "colour_hex":    colour_hex.strip(),
            "colour_name":   colour_name.strip() or "Custom",
            "custom_colour": request.form.get("custom_colour", ""),
            "inspo_paths":   saved_inspo,
            "vibes":         {r["key"]: request.form.get(f"vibe_{r['key']}", "") for r in rooms},
        }
        session.modified = True
        return redirect(url_for("step3"))

    ai_summary = session.get("ai_room_summary", "")
    return render_template("step2.html", current_step=2,
                           rooms=rooms, ai_room_summary=ai_summary)


# ── Step 3: Requirements ──────────────────────────────────────────────────────
@app.route("/step3", methods=["GET", "POST"])
def step3():
    if "step1" not in session:
        return redirect(url_for("step1"))

    housing_type = session["step1"]["housing_type"]
    rooms = get_rooms_for_type(housing_type)

    if request.method == "POST":
        req_data = {}
        for room in rooms:
            key = room["key"]
            req_data[f"{key}_prompt"]      = request.form.get(f"{key}_prompt", "")
            req_data[f"{key}_items"]       = request.form.getlist(f"{key}_items")
            req_data[f"{key}_budget"]      = request.form.get(f"{key}_budget", "")
            req_data[f"{key}_priority"]    = request.form.get(f"{key}_priority", "medium")
            req_data[f"{key}_constraints"] = request.form.get(f"{key}_constraints", "")

        req_data["project_notes"] = request.form.get("project_notes", "")
        session["step3"] = req_data
        session.modified = True
        return redirect(url_for("step4"))

    return render_template("step3.html", current_step=3, rooms=rooms)


# ── Step 4: Results ────────────────────────────────────────────────────────────
@app.route("/step4")
def step4():
    for step in ("step1", "step2", "step3"):
        if step not in session:
            return redirect(url_for(step.replace("step", "step")))

    s1, s2, s3 = session["step1"], session["step2"], session["step3"]
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

    s1, s2, s3 = session.get("step1", {}), session.get("step2", {}), session.get("step3", {})
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
