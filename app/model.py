"""Constants, normalization and lookup helpers for llm-monitor.

Stdlib only, Python 3.9+. The JSON document is the single source of truth shared
by the CLI (AI actor by default) and the local web server (human actor).
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import re
import secrets

DATA_VERSION = 1
ACTORS = ("ai", "human")
PRIORITIES = ("low", "normal", "high", "urgent")
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ec4899", "#06b6d4",
          "#8b5cf6", "#f97316", "#84cc16", "#ef4444", "#14b8a6"]
DEFAULT_COLUMNS = [
    {"id": "open", "title": "Open", "color": "#6366f1", "closed": False, "order": 0},
    {"id": "doing", "title": "Doing", "color": "#f59e0b", "closed": False, "order": 1},
    {"id": "done", "title": "Done", "color": "#10b981", "closed": True, "order": 2},
]
UNSET = object()


def now_iso(epoch=None):
    moment = (dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
              if epoch is not None else dt.datetime.now(dt.timezone.utc))
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def new_id(prefix):
    return "%s-%s" % (prefix, secrets.token_hex(3))


def slugify(text, fallback="col"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def clamp_progress(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        raise ValueError("progress must be an integer between 0 and 100")


def clean_text(value, limit=20000):
    text = "" if value is None else str(value)
    return text[:limit]


def clean_tags(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        return []
    tags, seen = [], set()
    for item in value:
        tag = str(item).strip()[:24]
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags[:8]


def actor_of(value, default=None):
    if value in ACTORS:
        return value
    if default is not None:
        return default
    raise ValueError("actor must be 'ai' or 'human'")


def priority_of(value):
    return value if value in PRIORITIES else "normal"


def default_data():
    return {
        "version": DATA_VERSION,
        "meta": {"created_at": now_iso()},
        "columns": copy.deepcopy(DEFAULT_COLUMNS),
        "cards": [],
        "projects": [],
        "sessions": [],
        "events": [],
    }


def card_by_ref(data, ref):
    ref = str(ref or "").strip()
    exact = [card for card in data["cards"] if card["id"] == ref]
    if exact:
        return exact[0]
    prefix = [card for card in data["cards"] if card["id"].startswith(ref)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        raise LookupError("card id prefix %r is ambiguous (%d matches)" % (ref, len(prefix)))
    raise LookupError("card %r not found" % ref)


def project_by_ref(data, ref):
    ref = str(ref or "").strip()
    for project in data["projects"]:
        if project["id"] == ref or project["path"] == os.path.abspath(os.path.expanduser(ref)):
            return project
    named = [project for project in data["projects"] if project["name"].casefold() == ref.casefold()]
    if len(named) == 1:
        return named[0]
    raise LookupError("project %r not found" % ref)


def column_by_id(data, cid):
    for column in data["columns"]:
        if column["id"] == cid:
            return column
    needle = str(cid).casefold().strip()
    matches = [column for column in data["columns"]
               if column["title"].casefold() == needle]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise LookupError("column title %r is ambiguous; use an id" % cid)
    raise LookupError("column %r not found" % cid)


def first_closed_column(data):
    for column in sorted(data["columns"], key=lambda item: item["order"]):
        if column["closed"]:
            return column
    return None


def first_open_column(data):
    for column in sorted(data["columns"], key=lambda item: item["order"]):
        if not column["closed"]:
            return column
    return None


def active_sessions(data):
    return [session for session in data["sessions"] if not session.get("end")]


def record_event(data, *, actor, kind, summary, card_id=None, project_id=None):
    event = {
        "id": new_id("e"),
        "ts": now_iso(),
        "actor": actor,
        "kind": kind,
        "summary": clean_text(summary, 400),
        "card_id": card_id,
        "project_id": project_id,
    }
    data["events"].append(event)
    data["events"] = data["events"][-500:]
    return event


def append_history(card, *, actor, action, summary, changes=None):
    entry = {
        "ts": now_iso(),
        "actor": actor,
        "action": action,
        "summary": clean_text(summary, 300),
        "changes": (changes or [])[:20],
    }
    card["history"].append(entry)
    card["history"] = card["history"][-50:]
    return entry


def diff_changes(old, new, fields):
    """Build a compact field-level change list for history entries."""
    changes = []
    for field in fields:
        before, after = old.get(field), new.get(field)
        if before == after:
            continue
        if isinstance(before, str) and isinstance(after, str) and len(before) > 80:
            before, after = "%d chars" % len(before), "%d chars" % len(after)
        changes.append({"field": field, "from": before, "to": after})
    return changes
