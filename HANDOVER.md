# FORMA — Design Inspiration Agent · Developer Handover

> Read this end-to-end before changing anything. It explains what the app is, how it is
> wired, where every feature lives, what is real vs. mocked, and the rules to keep it working.
> Built for the **NUS-ISS "Show Me Your Agents" Hackathon** (Team: Shaken Not Stirred).

---

## 1. What FORMA is (in one paragraph)

FORMA is an AI **agent** that turns a homeowner's messy renovation inputs — a floor-plan
photo, room requirements, budget, and inspiration images — into a coherent, designer-ready
brief. It is **not** a form that fires one prompt at an LLM. There is an explicit reasoning
loop (`agent.py`) that loads project state, decides which tools to run, calls them, detects
conflicts, asks the homeowner to resolve important ambiguities, and only then generates the
brief + room concepts + visuals. The homeowner can then refine in plain language.

---

## 2. Tech stack & how to run

| Layer | Choice |
|---|---|
| Backend | Python 3 / Flask (single app, server-rendered Jinja templates) |
| AI | Claude Sonnet 4.5 via an **Ollama-compatible LLM gateway** (text + vision) |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Persistence | Local JSON (`data.json`) via `clients.py` |
| Uploads | Local filesystem (`uploads/`) |

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\Activate.ps1     # Windows PowerShell
pip install -r requirements.txt
# credentials live in .env.local (gitignored) — copy .env.example, see section 9
python app.py                 # http://localhost:5000
python test_api.py            # verify the gateway (text + JSON + vision)
python evals/run_evals.py     # 7-case evaluation suite (should be 7/7)
```

On Windows, set `$env:PYTHONIOENCODING="utf-8"` before running the evals, or the
✓/✗ symbols crash the console with a `UnicodeEncodeError`.

Without gateway credentials the app still runs — every LLM call falls back to
`_mock_bedrock_response()` so you can develop/demo offline.

---

## 3. File map (what lives where)

```
app.py            ~2600 lines. Flask routes + ALL tool implementations + SVG renderers.
agent.py          run_agent() — the reasoning loop. Pure logic, no Flask.
clients.py        Email identity + JSON load/save (swap-for-DynamoDB seam).
tools/            Thin re-export wrappers (floorplan.py, inspiration.py, design.py).
                  agent.py actually imports app directly; these exist for clean structure.
evals/            cases.json (7 scenarios) + run_evals.py (runner, forces mock mode).
test_api.py       Standalone gateway diagnostic (text / JSON / vision).
templates/        base, index, start, step1..step4 (Jinja).
static/css/main.css, static/js/main.js
uploads/          floorplans/ and inspo/<roomkey>/ images (gitignored).
data.json         Saved clients + briefs (gitignored).
.env.local        Gateway URL/key/model (+ FLASK_SECRET_KEY for deploy). Gitignored, DO NOT COMMIT.
                  app.py also accepts _env.local or .env.
```

**Important architectural note:** despite the `tools/` folder, the real implementations of
every tool live in `app.py`. `agent.py` does `import app as _app` and calls
`_app.generate_design_brief(...)` etc. If you move a tool, keep that in mind.

---

## 4. The user flow (4 steps) & routes

| Route | Purpose |
|---|---|
| `/` | Landing |
| `/start` | Email sign-in; "continue my brief" or "new project" |
| `/step1` | Space: housing type, floor size, #floors, notes, floor-plan upload → room detection |
| `/step2` | Requirements: per-room items / budget / priority / description / constraints + project notes |
| `/step3` | Inspiration: style, palette, custom palette, per-room images + vibe → inspiration analysis |
| `/step4` | Vision: runs the agent, shows everything (see section 6) |
| `/regenerate` | POST → redirects to `/step4` (re-runs the agent) |
| `/resolve-conflict` | POST (AJAX) — store homeowner's answer to a clarification question |
| `/refine` | POST (AJAX) — homeowner asks for a change; returns feasibility + proposal |
| `/apply-refinement` | POST (AJAX) — apply the proposal, then regenerate |
| `/export-brief` | Download the brief as .txt |
| `/uploads/<path>` | Safely serve an uploaded image (used to restore previews) |

---

## 5. Project state / memory (the single most important concept)

State lives in the Flask **session**; only `client_id`/`email` sit in the cookie. Everything
else is persisted to `data.json` through `persist_brief()` and reloaded by `hydrate_session()`.

The keys that persist are in **`BRIEF_KEYS`** (app.py). Currently:

```
step1, ai_rooms, ai_room_summary, ai_room_source, ai_room_confidence,
requirements, inspiration, inspiration_analysis, conflicts, agent_trace, refinements,
floor_layout
```

**RULE:** if you add a new piece of state that must survive "continue my brief",
add its key to `BRIEF_KEYS`. If you forget, it silently won't persist.

Shapes (roughly):
- `step1`: `{housing_type, housing_type_label, floor_size, num_floors, space_notes, floor_plan_path}`
- `ai_rooms`: `["Living/Dining", "Kitchen", ...]` (the confirmed room list; editable in step 2)
- `requirements`: flat dict keyed by room slug: `{key}_prompt, {key}_items, {key}_budget, {key}_priority, {key}_constraints`, plus `project_notes`
- `inspiration`: `{design_style, colour_palette, colour_hex, colour_name, custom_colour, inspo_paths:{roomkey:[paths]}, vibes:{roomkey:text}}`
- `inspiration_analysis`: `{dominant_styles, colours, materials, lighting, forms, common_patterns, possible_outliers, room_specific, summary, source, confidence, image_count}`
- `conflicts`: list of `{id, type, severity, title, description, question, options, resolved, decision}`
- `agent_trace`: list of `{timestamp, step, action, reason, status, summary, confidence}`
- `refinements`: list of `{request, proposal, applied_at}`
- `floor_layout`: cache of the AI room-position trace — `{plan, rooms:[labels], layout}` where
  `layout` is `{boxes:[{label, floor, x, y, w, h}], floor_labels, aspect, confidence, placed, total}`
  (x/y/w/h are % of the plan image) or `None` if the trace wasn't usable. Reused while the
  plan path and room list are unchanged; `/regenerate` clears it to force a re-trace.

A room's **slug** is `label.lower().replace(" ","_").replace("/","_")` — see `get_rooms_for_type()`.

---

## 6. The agent loop (`agent.py::run_agent`)

Called once per `/step4` load. It is the "OBSERVE → REASON → ACT → EVALUATE → RESPOND" loop:

1. **OBSERVE** — read state, count images, check for floor plan.
2. **Floor plan** — logs whether rooms came from the plan or housing type.
3. **Inspiration analysis** — calls `analyse_inspiration()` if new images/none cached.
4. **Conflict detection** — `detect_conflicts()`; merges with prior resolved decisions.
5. **EVALUATE** — `needs_input = any open conflict`.
6. **ACT** — `generate_design_brief()`, per-room `generate_room_concept()` + `generate_room_concept_visual()`.
7. **Room positions** — only if a floor plan was uploaded: `read_floor_plan_layout()` (cached, see
   `floor_layout`), then `generate_floor_plan_svg(rooms, layout)`. No plan / bad trace → schematic.
8. Returns a dict: `inspiration_analysis, conflicts, ai_brief, room_results, floor_plan_svg, floor_layout, agent_trace, needs_input, overall_confidence`.

Key behaviours that were bug-fixed and MUST be preserved:
- **Trace is rebuilt fresh each run** (`trace = []`). Do NOT re-introduce carrying
  `existing_trace` — it caused stale "waiting for homeowner" lines after questions were answered.
- **Resolved conflicts are kept forever** in the merge, even if not re-detected, so a
  decision is never lost and the same question is never asked twice.
- **Every trace entry has a confidence** (`_trace_entry` auto-fills from status:
  success→high, needs_input→medium, failed→low).
- Homeowner decisions + applied refinements are injected into the brief prompt as a
  "HOMEOWNER DECISIONS (MUST be honoured)" block.

---

## 7. Feature → code map (where to change things)

| Feature | Function(s) in app.py |
|---|---|
| LLM call + retry + mock fallback | `call_llm()`, `_mock_bedrock_response()` |
| Floor-plan room detection prompt | `build_space_analysis_request()` (has separate plan vs no-plan prompts; multi-floor block when `num_floors>=2`) |
| Room detection + JSON parsing | `generate_room_summary()` |
| Room checklist for any room name | `items_for_room()` (fuzzy keyword map; used by `get_rooms_for_type()`) |
| Memory-aware room banner text | `compose_room_analysis()` (deterministic, no LLM) |
| Inspiration image analysis | `analyse_inspiration()` (multimodal; takes `memory={step1,requirements}`) |
| Conflict detection (style/budget/spatial) | `detect_conflicts()` + `STYLE_CONFLICTS`, `BUDGET_WEIGHTS`, `LARGE_ITEMS` |
| Design brief | `generate_design_brief()` |
| Per-room concept text | `generate_room_concept()` |
| Per-room concept **visual** (2D SVG) | `generate_room_concept_visual()` |
| Floor-plan **overview** (2D SVG) | `generate_floor_plan_svg()` → `_traced_floor_plan_svg()` (AI layout) or `_schematic_rows_svg()` + `_room_weight()` (rules); both draw rooms via `_room_cell_svg()` + `_furniture_markers()` |
| Room-position trace (vision) | `build_layout_request()` + `read_floor_plan_layout()` — Claude returns a % bounding box per confirmed room; validated (≥60% of rooms placed, no heavy overlaps, confidence not low) or `None` |
| Refinement feasibility + proposal | route `/refine` |

### Furniture icon system (shared by BOTH visuals)
- `_ITEM_GLYPHS` — maps item keyword → `(label, icon, rel_w, rel_h)`. **More specific
  keywords first** (e.g. "bedside" before "bed").
- `_items_to_glyphs(items, room_name)` — dedups selected items → glyph specs; falls back
  to room-type inference if no items selected.
- `_ICON_DRAWERS` — dict of `icon name → drawer function`. Each `_icon_*` draws a
  recognisable 2D top-down piece (bed w/ pillows, dresser w/ drawers, sofa w/ arms, etc.),
  black-outlined.
- `_draw_glyph()` — places one icon + label. Used by the room visual AND the floor plan,
  so the two views stay consistent and both reflect the homeowner's actual selected items.

**To add a new furniture type:** add a keyword row to `_ITEM_GLYPHS`, write an `_icon_x`
drawer, register it in `_ICON_DRAWERS`. Both views pick it up automatically.

---

## 8. What is REAL vs MOCKED (be honest with judges)

| Capability | Status |
|---|---|
| Floor-plan reading (vision) | **Real** — Claude reads the uploaded image |
| Inspiration image analysis (vision) | **Real** — analyses each image + project memory |
| Conflict detection | **Real** — deterministic Python heuristics |
| Design brief + room concepts | **Real** — Claude, grounded in all inputs |
| Refinement feasibility | **Real** — Claude judges feasible/tradeoffs/not |
| Agent trace / confidence | **Real** — recorded per step |
| Room concept "visuals" | **Generated SVG diagrams**, NOT photoreal renders. The gateway has **no image-generation model** (confirmed). They are honest 2D top-down layouts driven by selected items + style palette. |
| 2D floor plan | With an uploaded image plan: **approximate AI trace** — Claude places each room as a rectangle roughly where it is on the plan; Python draws it. Not to scale, no walls/doors. Otherwise the rule-based **schematic**. The UI label switches between the two (`floor_plan_traced`). Neither is a CAD reconstruction. |
| Email login | Prototype identity only, **not** secure auth. |

Do not describe the SVG visuals as AI-generated photorealistic renders, and do not describe
the floor plan as a true reconstruction. Both are clearly labelled in the UI; keep it that way.

---

## 9. Security / safety rules (do not regress)

- `.env.local` and `data.json` are **gitignored**. Never commit credentials. The live key
  currently sits in `.env.local`.
- `FLASK_SECRET_KEY` should be set via env for deploy; app warns if missing.
- User content (notes, prompts, refinement text) is treated as **data, not instructions** —
  prompts explicitly tell the model to ignore embedded "ignore previous instructions" attempts.
  Eval `case_05_prompt_injection` guards this. Keep it passing.
- `/uploads/<path>` only serves files that resolve **inside** `UPLOAD_FOLDER` (path-escape safe).
- Uploads validated by extension + 50 MB limit.
- No unsupported renovation-cost claims; the model is instructed not to invent measurements
  or prices.

---

## 10. The evaluation suite (`evals/`)

`run_evals.py` runs 7 cases from `cases.json` directly against `run_agent` (forces mock mode
for speed/determinism). Run it after any agent/tool change — target is **7/7**.

1. Golden path (no conflicts) 2. Style conflict 3. Budget/scope tension
4. Poor floor plan (low confidence) 5. Prompt injection 6. No images (text-only)
7. API failure (graceful fallback)

`python test_api.py` separately confirms the live gateway can do text, JSON, and vision.

---

## 11. Known gateway quirks (learned the hard way)

- The gateway is **Ollama-format**: message `content` must be a **plain string**, and images
  go in a separate **`"images": [base64]`** array on the message. Sending Anthropic-style
  content-block lists causes **502 errors**. All multimodal calls already use the correct format.
- The model often wraps JSON in ```` ```json ... ``` ````. Every JSON-parsing path strips
  code fences before `json.loads`. Keep that when adding new structured-output calls.
- `call_llm` retries 502/503/429 up to 3× with backoff, then falls back to the mock.
- The correct model id is `sonnet4.5:latest` (the gateway maps it to the Bedrock model).

---

## 12. Working rules for the next developer / AI

1. **Keep the app runnable after every change** — `python -c "import app, agent"` then run evals.
2. **Don't rebuild working code to make it "cleaner."** Make small, testable edits.
3. **New persistent state → add to `BRIEF_KEYS`.**
4. **New structured LLM output → strip code fences + validate + provide a fallback.**
5. **Room-name matching is fuzzy** (rooms can be "Living/Dining", "L1 Master Bedroom",
   "Ensuite"…). Never assume exact catalogue names — use `items_for_room()` / keyword logic.
6. **Two SVG views share one glyph system** — change furniture in `_ITEM_GLYPHS`/`_ICON_DRAWERS`,
   never fork it per view.
7. **Preserve the agent-loop invariants** in section 6 (fresh trace, keep resolved conflicts,
   confidence on every step, decisions injected into the brief).
8. **Be honest in the UI** about what is a diagram vs a render, and schematic vs reconstruction.
9. **Run `evals/run_evals.py` and `test_api.py` before declaring done.**

---

## 13. Sensible next steps (not yet done)

- AWS deployment (Flask is deployable as-is); optionally migrate `clients.py` storage to
  DynamoDB and uploads to S3 (the load/save seam already isolates this).
- PDF export of the designer brief (currently .txt).
- Real image generation IF a vision-gen endpoint becomes available (today: none).
- True floor-plan geometry extraction (walls, doors, real dimensions) — today rooms are traced as
  approximate rectangles only. Large effort, low priority.
- Let inspiration images *suggest* furniture (today furniture comes only from Step 2 checkboxes).
