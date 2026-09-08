# FORMA — Design Inspiration Agent

> Interior design inspiration platform that bridges the gap between homeowners and designers.  
> Built for the **AWS "Show Me Your Agents" Hackathon** · Powered by AWS Bedrock / Claude Sonnet 4.5

---

## Workflow

| Step | What happens |
|------|-------------|
| **1 · Space** | User selects housing type + uploads floor plan → AI segments rooms |
| **2 · Inspiration** | Upload reference images per room + choose colour palette & style |
| **3 · Requirements** | Dropdown per room with checklist of fixtures/items + open prompt |
| **4 · Vision** | AI-generated design brief, room concepts, 2D floor plan schematic, exportable brief |

---

## Quick Start

### 1. Install dependencies

```bash
cd "design-inspiration-agent"
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your AWS credentials (optional — app works without them using mock responses)
```

### 3. Run the app

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

---

## AWS Bedrock Setup

When you have your API credentials:

1. Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`
2. Ensure your IAM role has `bedrock:InvokeModel` permission
3. The model used is: `us.anthropic.claude-sonnet-4-5-20251001-v1:0`
4. Region: `us-east-1` (change `AWS_REGION` if needed)

**Without credentials** the app runs fully on mock/stub responses — perfect for demo and development.

---

## Project Structure

```
design-inspiration-agent/
├── app.py                  # Flask app — routes, AI calls, session state
├── requirements.txt
├── .env.example
├── templates/
│   ├── base.html           # Shared layout, nav, step indicator
│   ├── index.html          # Landing / hero page
│   ├── step1.html          # Housing type + floor plan
│   ├── step2.html          # Inspiration images + colour/style
│   ├── step3.html          # Room requirements
│   └── step4.html          # AI results page
├── static/
│   ├── css/main.css        # Premium ID aesthetic styles
│   └── js/main.js          # Shared JS
└── uploads/                # User uploads (gitignored)
```

---

## Tech Stack

- **Backend**: Python / Flask
- **AI**: AWS Bedrock — Claude Sonnet 4.5 (`anthropic.claude-sonnet-4-5`)
- **Frontend**: Vanilla HTML/CSS/JS — no framework dependencies
- **Fonts**: Cormorant Garamond (serif) + Inter (sans)
- **Storage**: Local filesystem (uploads folder)

---

## Future Enhancements

- Real image generation via AWS Bedrock image models (Stability AI / Amazon Titan Image)
- Iteration flow with cost controls (step 4 regenerate with diff tracking)
- Designer portal to receive and annotate briefs
- PDF export with rendered floor plan
- S3 integration for image storage
