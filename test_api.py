#!/usr/bin/env python3
"""
FORMA — API connectivity diagnostic.

Tests whether the LLM gateway is reachable and whether Claude actually
responds, across three capabilities:

  1. Plain text     — basic connectivity + auth
  2. Structured JSON — the format the app depends on
  3. Vision (image) — reading a floor plan

Run:  python test_api.py
Exit: 0 if all pass, 1 if any fail.
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
for _f in ("_env.local", ".env.local", ".env"):
    if Path(_f).exists():
        load_dotenv(_f)
        break

URL   = os.environ.get("LLM_GATEWAY_URL")
KEY   = os.environ.get("LLM_GATEWAY_API_KEY")
MODEL = os.environ.get("LLM_MODEL")

GREEN, RED, YEL, DIM, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def call(messages, num_predict=200, timeout=60):
    """Raw gateway call. Returns (ok, content_or_error, seconds)."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": num_predict},
    }
    req = urllib.request.Request(
        f"{URL.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": KEY},
        method="POST",
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return True, data["message"]["content"], time.time() - t
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body[:200]}", time.time() - t
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", time.time() - t


def strip_fences(s):
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    return s


def hdr(n, title):
    print(f"\n{DIM}{'─'*60}{RST}")
    print(f"TEST {n}: {title}")


def main():
    print(f"\nFORMA API Diagnostic")
    print(f"  URL   : {URL}")
    print(f"  MODEL : {MODEL}")
    print(f"  KEY   : {(KEY or '')[:8]}…" if KEY else "  KEY   : (missing)")

    if not (URL and KEY and MODEL):
        print(f"\n{RED}✗ Gateway config incomplete — set LLM_GATEWAY_URL, "
              f"LLM_GATEWAY_API_KEY, LLM_MODEL in _env.local{RST}")
        sys.exit(1)

    results = []

    # ── TEST 1: plain text ────────────────────────────────────────────────────
    hdr(1, "Plain text (connectivity + auth)")
    ok, out, secs = call(
        [{"role": "user", "content": "Reply with exactly the word: PONG"}],
        num_predict=10,
    )
    if ok and "PONG" in out.upper():
        print(f"  {GREEN}✓ PASS{RST} ({secs:.1f}s) — model replied: {out.strip()[:40]!r}")
        results.append(True)
    elif ok:
        print(f"  {YEL}~ PARTIAL{RST} ({secs:.1f}s) — replied but unexpected: {out.strip()[:60]!r}")
        results.append(True)
    else:
        print(f"  {RED}✗ FAIL{RST} ({secs:.1f}s) — {out}")
        results.append(False)

    # ── TEST 2: structured JSON ───────────────────────────────────────────────
    hdr(2, "Structured JSON (app depends on this)")
    ok, out, secs = call(
        [{"role": "user", "content":
          'List 3 rooms of an HDB flat. Respond with ONLY JSON: '
          '{"rooms": ["Living Room", "Kitchen", "Bedroom"]}'}],
        num_predict=150,
    )
    if ok:
        try:
            parsed = json.loads(strip_fences(out))
            rooms = parsed.get("rooms", [])
            print(f"  {GREEN}✓ PASS{RST} ({secs:.1f}s) — parsed JSON, rooms: {rooms}")
            results.append(True)
        except Exception as e:
            print(f"  {RED}✗ FAIL{RST} ({secs:.1f}s) — got response but not valid JSON: {e}")
            print(f"    Raw: {out[:120]!r}")
            results.append(False)
    else:
        print(f"  {RED}✗ FAIL{RST} ({secs:.1f}s) — {out}")
        results.append(False)

    # ── TEST 3: vision ────────────────────────────────────────────────────────
    hdr(3, "Vision — reading a floor plan image")
    # Find any uploaded floor plan to test with
    fp_dir = Path("uploads/floorplans")
    imgs = list(fp_dir.glob("*")) if fp_dir.exists() else []
    imgs = [p for p in imgs if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")]

    if not imgs:
        print(f"  {YEL}~ SKIP{RST} — no floor plan image found in uploads/floorplans/")
        print(f"    Upload a plan through the app once, then re-run this test.")
    else:
        img = imgs[0]
        print(f"  Using image: {img.name}")
        with open(img, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        # Ollama format: content is a string, images is a separate array
        ok, out, secs = call(
            [{"role": "user",
              "content": "How many distinct rooms/spaces can you see in this floor "
                         "plan? Reply with ONLY a number and a one-line list.",
              "images": [b64]}],
            num_predict=300, timeout=120,
        )
        if ok:
            print(f"  {GREEN}✓ PASS{RST} ({secs:.1f}s) — model can see the image:")
            print(f"    {DIM}{out.strip()[:300]}{RST}")
            results.append(True)
        else:
            print(f"  {RED}✗ FAIL{RST} ({secs:.1f}s) — {out}")
            results.append(False)

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{DIM}{'─'*60}{RST}")
    passed = sum(1 for r in results if r)
    total = len(results)
    if passed == total:
        print(f"{GREEN}All {total} tests passed — the API and AI are working.{RST}\n")
        sys.exit(0)
    else:
        print(f"{RED}{passed}/{total} passed — see failures above.{RST}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
