#!/usr/bin/env python3
"""
FORMA — does the gateway still drop attached images?

The gateway accepts image requests and answers them, but strips the image
first, so the reply is invented. This tells the two apart by cost: it sends
the same question twice, once without the image and once with it, and
compares prompt_eval_count. An image the model actually received is worth
hundreds of prompt tokens; a delta near zero means it never arrived.

A reference image (four black bars) is generated on first run. Its answer
is 4, which the model cannot guess from the wording — so the reply is a
second, independent check on the token maths.

Run:  python check_vision.py                 # built-in 4-bar reference image
      python check_vision.py uploads/plan.png  # or any image of your own
Exit: 0 if images get through, 1 if they are dropped or the call failed.

Costs two gateway calls of 16 output tokens each.
"""

import base64
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
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

REF_IMAGE = Path(__file__).parent / "test_vision_bars.png"
BARS      = 4                      # the answer only a model that sees it knows
W = H     = 320

# An image the model received costs far more than this many prompt tokens.
# Well below any real image's cost, well above per-request framing noise.
IMAGE_TOKEN_FLOOR = 100


# ── Reference image ───────────────────────────────────────────────────────────
def write_reference_image(path: Path) -> None:
    """White canvas, BARS thick black vertical bars. Hand-rolled so the
    diagnostic needs nothing that isn't already in requirements.txt."""
    rows = []
    for _y in range(H):
        row = bytearray(b"\xff" * (W * 3))
        for i in range(BARS):
            x0 = 30 + i * 70
            for x in range(x0, x0 + 34):
                row[x * 3:x * 3 + 3] = b"\x00\x00\x00"
        rows.append(b"\x00" + bytes(row))          # filter byte 0 per scanline

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


# ── Gateway call ──────────────────────────────────────────────────────────────
def call(prompt: str, b64: str | None, timeout: int = 120):
    """One gateway call. Returns (body_or_None, seconds, error_or_None).

    Ollama format: content is a plain string, images go in a separate array.
    The gateway 502s on list-valued content, so this is the only shape it takes.
    """
    message = {"role": "user", "content": prompt}
    if b64:
        message["images"] = [b64]

    payload = {
        "model": MODEL,
        "messages": [message],
        "stream": False,
        "options": {"num_predict": 16},
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
            return json.loads(r.read().decode("utf-8")), time.time() - t, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return None, time.time() - t, f"HTTP {e.code}: {body[:200]}"
    except Exception as e:                                    # noqa: BLE001
        return None, time.time() - t, f"{type(e).__name__}: {e}"


def run_pair(label: str, prompt: str, b64: str):
    """Control call then image call. Returns (control_tokens, image_tokens, reply)."""
    print(f"\n{DIM}{'─' * 62}{RST}")
    print(f"{label}")

    out = []
    for name, payload_b64 in (("text only ", None), ("with image", b64)):
        body, secs, err = call(prompt, payload_b64)
        if err:
            print(f"  {name}  {RED}call failed{RST} ({secs:.1f}s) — {err}")
            out.append(None)
            continue
        tokens = body.get("prompt_eval_count")
        reply  = (body.get("message") or {}).get("content", "").strip()
        print(f"  {name}  {secs:5.1f}s   prompt_eval_count={str(tokens):<6} "
              f"reply: {DIM}{reply[:60]!r}{RST}")
        out.append((tokens, reply))

    return out


def main() -> int:
    missing = [n for n, v in (("LLM_GATEWAY_URL", URL),
                              ("LLM_GATEWAY_API_KEY", KEY),
                              ("LLM_MODEL", MODEL)) if not v]
    if missing:
        print(f"{RED}Gateway not configured{RST} — missing {', '.join(missing)}")
        print(f"{DIM}Copy .env.example to .env.local and fill it in.{RST}")
        return 1

    # Which image?
    if len(sys.argv) > 1:
        img_path = Path(sys.argv[1])
        if not img_path.exists():
            print(f"{RED}No such image:{RST} {img_path}")
            return 1
        prompt = ("Describe what you see in this image in one short sentence.")
        expected = None
    else:
        if not REF_IMAGE.exists():
            write_reference_image(REF_IMAGE)
            print(f"{DIM}Wrote reference image: {REF_IMAGE.name} "
                  f"({W}x{H}, {BARS} black bars){RST}")
        img_path = REF_IMAGE
        prompt = ("How many black vertical bars are in this image? "
                  "Reply with only the digit.")
        expected = str(BARS)

    raw = img_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")

    print(f"\n{DIM}model {MODEL}{RST}")
    print(f"{DIM}host  {URL}{RST}")
    print(f"{DIM}image {img_path.name} — {len(raw):,} bytes, "
          f"{len(b64):,} base64 chars{RST}")

    results = run_pair("Sending the same question with and without the image",
                       prompt, b64)

    if any(r is None for r in results):
        print(f"\n{RED}INCONCLUSIVE{RST} — a call failed, see above.")
        return 1

    (control_tokens, _control_reply), (image_tokens, image_reply) = results

    if not isinstance(control_tokens, int) or not isinstance(image_tokens, int):
        print(f"\n{YEL}INCONCLUSIVE{RST} — the gateway did not report "
              f"prompt_eval_count, so cost can't be compared.")
        return 1

    delta = image_tokens - control_tokens
    print(f"\n  the image added {delta} prompt tokens "
          f"({control_tokens} -> {image_tokens})")

    if delta < IMAGE_TOKEN_FLOOR:
        print(f"\n{RED}DROPPED{RST} — the gateway is still stripping images.")
        print(f"  An image the model actually read could not cost {delta} tokens.")
        if expected:
            print(f"  Its answer {image_reply[:20]!r} is invented "
                  f"(the image shows {expected}).")
        print(f"{DIM}  app.py raises VisionUnavailable on this, so the app "
              f"fails loudly rather than\n  passing off the invented reply.{RST}")
        return 1

    print(f"\n{GREEN}REACHED THE MODEL{RST} — the image cost {delta} prompt "
          f"tokens, so it was forwarded.")
    if expected:
        ok = expected in image_reply
        mark = f"{GREEN}matches{RST}" if ok else f"{YEL}does not match{RST}"
        print(f"  Its answer {image_reply[:20]!r} {mark} the image "
              f"(which shows {expected}).")
        if not ok:
            print(f"{DIM}  Image got through but was misread — a model quality "
                  f"issue, not a gateway one.{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
