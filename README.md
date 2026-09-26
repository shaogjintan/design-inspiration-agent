# FORMA — Design Inspiration Agent

> An AI agent that translates a homeowner's messy ideas, inspiration images, and renovation requirements into a coherent, designer-ready brief.
> Built for the **NUS-ISS "Show Me Your Agents" Hackathon**

**Live demo:** http://13.250.211.152/ (AWS Lightsail, Singapore region)

FORMA works with either LLM backend, chosen at runtime by which keys are set:
a NUS **SOCLAAS / Qwen3.8 27B** endpoint (what the live demo runs) or an
**AWS Bedrock / Claude Sonnet 4.5** gateway. See [Configure environment](#2-configure-environment).

---

## What FORMA does

FORMA is not a form that calls an LLM. It is an agent with an explicit reasoning loop:

```
OBSERVE   → Load project state, check what exists and what's missing
REASON    → Decide which tools to run and in what order
ACT       → Analyse floor plan, analyse inspiration images, detect conflicts
EVALUATE  → Does the agent have enough to generate a brief, or does it need input?
RESPOND   → Generate brief + room concepts, or ask the homeowner a targeted question
```

The homeowner can then refine the result in plain language ("the living room feels too beige") and the agent proposes a targeted change, waits for approval, and updates only the affected parts.

---

## Application flow

| Step | What happens |
|------|-------------|
| **0 · Sign in** | Email-only identity — attaches to a saved project |
| **1 · Space** | Housing type + optional floor plan → agent identifies rooms (multimodal if plan provided) |
| **2 · Requirements** | Per-room items, budget, priority, constraints |
| **3 · Inspiration** | Style/palette selection + optional reference images → agent visually analyses them |
| **4 · Vision** | Agent produces: inspiration analysis, conflict flags, design brief, room concepts, agent trace, refinement loop |

---

## Agent features

- **Multimodal floor plan analysis** — reads room labels from uploaded floor plan images
- **Inspiration image analysis** — identifies dominant styles, colours, materials, lighting, forms, recurring patterns, and outliers across all uploaded images
- **Conflict detection** — flags style inconsistencies, budget/scope tension, and spatial concerns before generating the brief
- **Human-in-the-loop** — asks targeted clarification questions; stores homeowner decisions and incorporates them into the brief
- **Refinement loop** — homeowner can request changes in plain language; agent proposes, homeowner approves, brief updates
- **Agent trace** — every action the agent took is logged and shown in the UI
- **Graceful fallback** — works without images (text-only mode), without a floor plan (housing-type inference), and when the LLM is unavailable (mock responses)

---

## Quick start

**Requires Python 3.10 or newer.** The code annotates types as `str | None`,
which earlier versions evaluate at import and reject with
`TypeError: unsupported operand type(s) for |`. Check with `python3 -V`.

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Already have a `venv/` folder?** It is gitignored, so a pull never brings one
and never updates one. Recreate it rather than trusting it — a venv hardcodes
the absolute path of the interpreter that built it, so one copied between
machines (or built on an older Python) fails in confusing ways:

```bash
rm -rf venv && python3 -m venv venv
source venv/bin/activate && pip install -r requirements.txt
```

To check one in place instead: `venv/bin/python -V` must report 3.10+, then
re-run the `pip install` line to pick up anything new in `requirements.txt`.

### 2. Configure environment

Copy and edit the environment file:

```bash
cp .env.example .env.local
# Edit .env.local with your LLM credentials
```

(`_env.local` and `.env` are read too, in that order — all are gitignored.)

Pick **one** of the two backends. If the SOCLAAS values are all set, the app uses
SOCLAAS and ignores the gateway block.

**Option A — SOCLAAS / Qwen (what the live demo runs):**
```
SOCLAAS_BASE_URL=https://soclaas-api.comp.nus.edu.sg/v1
SOCLAAS_API_KEY=clsk_...
SOCLAAS_MODEL=qwen3.8:27b
FLASK_SECRET_KEY=a-long-random-string
```

**Option B — AWS Bedrock / Claude Sonnet 4.5 gateway:**
```
LLM_GATEWAY_URL=https://...
LLM_GATEWAY_API_KEY=...
LLM_MODEL=global.anthropic.claude-sonnet-4-5-20250929-v1:0
FLASK_SECRET_KEY=a-long-random-string
```

**Without credentials** the app runs on mock/stub responses — fully usable for demo and development.

### Deploying to AWS Lightsail

The full walkthrough (create the instance, install, add keys, update, back up) is in
[`deploy/LIGHTSAIL.md`](deploy/LIGHTSAIL.md). The server installs itself from
[`deploy/lightsail.sh`](deploy/lightsail.sh); the current live instance details are
recorded at the top of that guide.

### 3. Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

`uploads/` and `data.json` are created on first run — neither is in the repo.
A recent browser is assumed (Chrome 105+, Safari 15.4+, Firefox 121+).

---

## Run the evaluation suite

```bash
python evals/run_evals.py              # all 7 cases
python evals/run_evals.py case_02      # single case by ID prefix
python evals/run_evals.py --verbose    # show full agent trace per case
```

Cases covered:
1. Normal HDB project — golden path
2. Conflicting inspiration styles — style conflict detected
3. Budget/scope tension — flagged without exact price claims
4. Poor-quality floor plan — low confidence, no invented measurements
5. Prompt injection — treated as design content, no secrets leaked
6. No inspiration images — text-only fallback, correctly labelled
7. API failure — graceful degradation, no crash

---

## Project structure

```
app.py                  # Flask routes + all tool functions (LLM calls, analysis, etc.)
agent.py                # FORMA reasoning loop — run_agent() orchestrates all tools
clients.py              # Email identity + JSON persistence (easy to swap to DynamoDB)
data.json               # Local project store (gitignored — created at runtime)
requirements.txt
_env.local              # Your credentials (gitignored — never commit)
.env.example            # Template for env vars

templates/
  base.html             # Shared layout, nav, step indicator
  index.html            # Landing page
  start.html            # Sign in / return to project
  step1.html            # Space + floor plan upload
  step2.html            # Room requirements
  step3.html            # Inspiration images + style/palette
  step4.html            # Vision: analysis, conflicts, brief, refinement, trace

static/
  css/main.css          # All styles
  js/main.js            # Shared JS

evals/
  cases.json            # Evaluation case definitions
  run_evals.py          # Evaluation runner

uploads/                # User uploads (gitignored)
```

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python / Flask |
| AI | SOCLAAS / Qwen3.8 27B (live) or AWS Bedrock / Claude Sonnet 4.5 — selected by env |
| Multimodal | Base64 image encoding → vision model |
| Deployment | AWS Lightsail (Ubuntu + gunicorn + nginx), self-installing script |
| Frontend | Vanilla HTML/CSS/JS — no framework |
| Fonts | Cormorant Garamond + Inter |
| Persistence | Local JSON (designed to migrate to DynamoDB) |
| Uploads | Local filesystem (designed to migrate to S3) |

---

## Security notes

- `_env.local` is gitignored — never commit credentials
- `FLASK_SECRET_KEY` must be set in production — app warns if missing
- User content (prompts, notes, image descriptions) is treated as data, not instructions
- File uploads are validated by extension and size (50 MB limit)
- Agent outputs are sanitised before storage

---

## Hackathon team

**Team: Shaken Not Stirred (9RGSAV87)**
NUS-ISS "Show Me Your Agents" Hackathon
