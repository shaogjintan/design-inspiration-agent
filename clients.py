"""
Client identity and saved briefs, backed by a JSON file.

No passwords: a client is identified by their email alone. That's enough to
let someone leave and come back to a half-finished brief, which is the whole
point — an interior design conversation spans several meetings.

Storage is deliberately behind _load/_save. Swapping the JSON file for
DynamoDB later means rewriting those two functions and nothing else.
"""
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data.json"
EMPTY = {"clients": {}, "briefs": {}}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(raw):
    """Trim and lowercase, so 'Tan@Gmail.com ' and 'tan@gmail.com' are one client."""
    return (raw or "").strip().lower()


def is_valid_email(email):
    """Loose on purpose. The only real test of an address is sending to it."""
    return bool(email) and len(email) <= 254 and bool(EMAIL_RE.fullmatch(email))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load():
    if not DATA_FILE.exists():
        return json.loads(json.dumps(EMPTY))
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(EMPTY))
    data.setdefault("clients", {})
    data.setdefault("briefs", {})
    return data


def _save(data):
    """Write to a temp file and swap it in, so a crash mid-write can't leave
    a truncated data.json behind."""
    tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def find_or_create_client(email):
    """-> (client dict, is_new). Email must already be normalised."""
    data = _load()
    existing = data["clients"].get(email)

    if existing:
        existing["last_active_at"] = _now()
        data["clients"][email] = existing
        _save(data)
        return existing, False

    client = {
        "client_id":      "c_" + uuid.uuid4().hex[:10],
        "email":          email,
        "created_at":     _now(),
        "last_active_at": _now(),
    }
    data["clients"][email] = client
    _save(data)
    return client, True


def load_brief(client_id):
    """-> the saved brief dict, or {} if this client has never saved one."""
    return _load()["briefs"].get(client_id, {})


def save_brief(client_id, brief):
    data = _load()
    brief = dict(brief)
    brief["updated_at"] = _now()
    data["briefs"][client_id] = brief
    _save(data)


def brief_progress(brief):
    """Short human summary for the 'welcome back' panel."""
    done = []
    if brief.get("step1"):        done.append("your space")
    if brief.get("requirements"): done.append("room requirements")
    if brief.get("inspiration"):  done.append("inspiration")
    rooms = brief.get("ai_rooms") or []
    return {
        "done": done,
        "room_count": len(rooms),
        "updated_at": brief.get("updated_at", ""),
    }
