"""Normalization and migration of the llm-monitor JSON document."""
from __future__ import annotations

import copy
import os

from .model import (COLORS, DATA_VERSION, DEFAULT_COLUMNS, actor_of,
                    clamp_progress, clean_tags, clean_text, default_data,
                    new_id, now_iso, priority_of, slugify)


def _list(value):
    return value if isinstance(value, list) else []


def _normalize_columns(raw):
    columns, seen = [], set()
    for index, col in enumerate(_list(raw.get("columns"))):
        if not isinstance(col, dict):
            continue
        title = str(col.get("title") or "").strip()
        base = slugify(str(col.get("id") or title))
        cid, n = base, 2
        while cid in seen:
            cid, n = "%s-%d" % (base, n), n + 1
        seen.add(cid)
        columns.append({
            "id": cid,
            "title": title or cid.replace("-", " ").title(),
            "color": str(col.get("color") or COLORS[index % len(COLORS)]),
            "closed": bool(col.get("closed")),
            "order": int(col.get("order", index)) if isinstance(col.get("order"), int) else index,
        })
    if not columns:
        columns = copy.deepcopy(DEFAULT_COLUMNS)
    columns.sort(key=lambda item: item["order"])
    for index, col in enumerate(columns):
        col["order"] = index
    return columns


def _normalize_projects(raw):
    projects, ids, paths = [], set(), set()
    for item in _list(raw.get("projects")):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        path = os.path.abspath(os.path.expanduser(path))
        if path in paths:
            continue
        paths.add(path)
        pid = str(item.get("id") or new_id("p"))
        while pid in ids:
            pid = new_id("p")
        ids.add(pid)
        try:
            progress = clamp_progress(item.get("progress", 0))
        except ValueError:
            progress = 0
        projects.append({
            "id": pid,
            "name": str(item.get("name") or os.path.basename(path)).strip()[:120] or os.path.basename(path),
            "path": path,
            "progress": progress,
            "progress_note": clean_text(item.get("progress_note"), 2000),
            "progress_updated_at": item.get("progress_updated_at") or None,
            "progress_updated_by": actor_of(item.get("progress_updated_by"), "human"),
            "added_by": actor_of(item.get("added_by"), "human"),
            "created_at": item.get("created_at") or now_iso(),
            "color": str(item.get("color") or COLORS[len(projects) % len(COLORS)]),
        })
    return projects


def _normalize_cards(raw, columns, projects):
    column_ids = {col["id"] for col in columns}
    closed_ids = {col["id"] for col in columns if col["closed"]}
    project_ids = {proj["id"] for proj in projects}
    default_column = next((col["id"] for col in columns if not col["closed"]), columns[0]["id"])
    cards, ids = [], set()
    for item in _list(raw.get("cards")):
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or new_id("c"))
        while cid in ids:
            cid = new_id("c")
        ids.add(cid)
        column = item.get("column") if item.get("column") in column_ids else default_column
        created_at = item.get("created_at") or now_iso()
        updated_at = item.get("updated_at") or created_at
        closed_at = item.get("closed_at") if column in closed_ids else None
        if column in closed_ids and not closed_at:
            closed_at = updated_at
        project = item.get("project")
        if project not in project_ids:
            project = None
        history = []
        for entry in _list(item.get("history")):
            if not isinstance(entry, dict):
                continue
            history.append({
                "ts": entry.get("ts") or updated_at,
                "actor": actor_of(entry.get("actor"), "human"),
                "action": str(entry.get("action") or "edited"),
                "summary": clean_text(entry.get("summary"), 300),
                "changes": _list(entry.get("changes"))[:20],
            })
        comments = []
        for comment in _list(item.get("comments")):
            if not isinstance(comment, dict):
                continue
            comments.append({
                "id": str(comment.get("id") or new_id("m")),
                "ts": comment.get("ts") or updated_at,
                "actor": actor_of(comment.get("actor"), "human"),
                "text": clean_text(comment.get("text"), 4000),
            })
        attachments = []
        for attachment in _list(item.get("attachments")):
            if not isinstance(attachment, dict):
                continue
            stored = attachment.get("stored_as")
            if not stored:
                continue
            attachments.append({
                "id": str(attachment.get("id") or new_id("a")),
                "name": str(attachment.get("name") or "file")[:160],
                "mime": str(attachment.get("mime") or "application/octet-stream")[:100],
                "size": max(0, int(attachment.get("size") or 0)),
                "stored_as": str(stored),
                "ts": attachment.get("ts") or updated_at,
                "actor": actor_of(attachment.get("actor"), "human"),
            })
        cards.append({
            "id": cid,
            "title": str(item.get("title") or "Untitled").strip()[:200] or "Untitled",
            "body": clean_text(item.get("body")),
            "column": column,
            "project": project,
            "tags": clean_tags(item.get("tags")),
            "priority": priority_of(item.get("priority")),
            "created_by": actor_of(item.get("created_by"), "human"),
            "created_at": created_at,
            "updated_by": actor_of(item.get("updated_by"), "human"),
            "updated_at": updated_at,
            "closed_at": closed_at,
            "closed_by": actor_of(item.get("closed_by"), None) if closed_at else None,
            "close_note": clean_text(item.get("close_note"), 500) if closed_at else "",
            "comments": comments[-200:],
            "attachments": attachments[-20:],
            "history": history[-50:],
        })
    return cards


def _normalize_sessions(raw):
    sessions = []
    for item in _list(raw.get("sessions")):
        if not isinstance(item, dict):
            continue
        sessions.append({
            "id": str(item.get("id") or new_id("s")),
            "project_id": item.get("project_id") or None,
            "card_id": item.get("card_id") or None,
            "actor": actor_of(item.get("actor"), "human"),
            "start": item.get("start") or now_iso(),
            "end": item.get("end") or None,
            "note": clean_text(item.get("note"), 1000),
        })
    return sessions


def _normalize_events(raw):
    events = []
    for item in _list(raw.get("events")):
        if not isinstance(item, dict):
            continue
        events.append({
            "id": str(item.get("id") or new_id("e")),
            "ts": item.get("ts") or now_iso(),
            "actor": actor_of(item.get("actor"), "human"),
            "kind": str(item.get("kind") or "edit"),
            "summary": clean_text(item.get("summary"), 400),
            "card_id": item.get("card_id") or None,
            "project_id": item.get("project_id") or None,
        })
    return events[-500:]


def ensure_data(raw):
    """Normalize an arbitrary JSON document into the current shape."""
    if not isinstance(raw, dict):
        return default_data()
    data = raw
    data["version"] = DATA_VERSION
    data.setdefault("meta", {})
    if not isinstance(data["meta"], dict):
        data["meta"] = {}
    data["projects"] = _normalize_projects(data)
    data["columns"] = _normalize_columns(data)
    data["cards"] = _normalize_cards(data, data["columns"], data["projects"])
    data["sessions"] = _normalize_sessions(data)
    data["events"] = _normalize_events(data)
    return data
