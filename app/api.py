"""JSON API for the local llm-monitor web app (UI mutations are human)."""
from __future__ import annotations

import os
import time
from urllib.parse import parse_qs, urlparse

from . import attachments, cards, docinfo, folder_picker, gitinfo, model, projects
from .model import now_iso
from .store import StoreError

SKILL_VERSION = "1.0"
ACTIVITY_TTL = 45.0
WATCH_TIMEOUT = 20.0
WATCH_POLL = 0.35


def cached_activity(path, cache):
    now = time.time()
    entry = cache.get(path)
    if entry and now - entry[0] < ACTIVITY_TTL:
        return entry[1]
    info = gitinfo.project_activity(path)
    info["docs"] = docinfo.project_docs(path)
    cache[path] = (now, info)
    return info


def build_state(store, cache, port):
    data = store.read()
    project_payload = []
    for project in data["projects"]:
        project_payload.append(dict(
            project,
            metrics=projects.project_metrics(data, project),
            activity=cached_activity(project["path"], cache),
        ))
    active = projects.timer_status(data)
    return {
        "server": {"pid": os.getpid(), "port": port, "time": now_iso(),
                   "home": store.home, "version": SKILL_VERSION,
                   "signature": store.signature()},
        "overview": projects.overview(data),
        "columns": data["columns"],
        "cards": data["cards"],
        "projects": project_payload,
        "sessions": data["sessions"][-50:],
        "events": data["events"][-80:][::-1],
        "active_timer": ({
            "session": active[-1]["session"],
            "elapsed": active[-1]["elapsed"],
            "project": active[-1]["project"],
        } if active else None),
    }


def _dict(body):
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    return body


def _pick(body, keys):
    return {key: body[key] for key in keys if key in body}


def _dispatch(method, raw_path, body, store, cache, port):
    parsed = urlparse(raw_path)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    query = parse_qs(parsed.query)

    if not parts or parts[0] != "api":
        return 404, {"error": "not found"}
    if parts == ["api", "health"] and method == "GET":
        return 200, {"ok": True, "pid": os.getpid(), "port": port,
                     "version": SKILL_VERSION, "home": store.home}
    if parts == ["api", "state"] and method == "GET":
        return 200, build_state(store, cache, port)
    if parts == ["api", "browse-folder"] and method == "POST":
        payload = _dict(body) if body is not None else {}
        start = payload.get("start")
        if start is not None and not isinstance(start, str):
            raise ValueError("start must be a string")
        path = folder_picker.pick_folder(start)
        return 200, {"path": path, "cancelled": path is None}
    if parts == ["api", "watch"] and method == "GET":
        since = (query.get("since") or [None])[0]
        deadline = time.monotonic() + WATCH_TIMEOUT
        current = store.signature()
        while current == since and time.monotonic() < deadline:
            time.sleep(WATCH_POLL)
            current = store.signature()
        return 200, {"signature": current, "changed": current != since}
    if parts == ["api", "events"] and method == "GET":
        limit = int((query.get("limit") or ["50"])[0])
        data = store.read()
        return 200, {"events": data["events"][-max(1, min(500, limit)):][::-1]}
    if parts == ["api", "activity"] and method == "GET":
        data = store.read()
        ref = (query.get("project") or [None])[0]
        project = model.project_by_ref(data, ref) if ref else None
        if project is None:
            raise ValueError("project query parameter is required")
        return 200, {"project": project, "activity": cached_activity(project["path"], cache)}

    if parts[:2] == ["api", "cards"]:
        if len(parts) == 2 and method == "POST":
            payload = _dict(body)
            card = store.mutate(lambda data: cards.add_card(
                data, "human", title=payload.get("title", ""), body=payload.get("body", ""),
                column=payload.get("column"), project=payload.get("project"),
                tags=payload.get("tags"), priority=payload.get("priority", "normal")))
            return 200, {"card": card}
        if len(parts) >= 3:
            card_id = parts[2]
            if len(parts) == 3 and method == "PATCH":
                payload = _dict(body)
                kwargs = _pick(payload, ("title", "body", "column", "tags", "priority", "note"))
                if "project" in payload:
                    kwargs["project"] = payload["project"]
                card = store.mutate(lambda data: cards.update_card(
                    data, "human", card_id, **kwargs))
                return 200, {"card": card}
            if len(parts) == 3 and method == "DELETE":
                return 200, store.mutate(lambda data: cards.delete_card(data, "human", card_id))
            if len(parts) == 4 and method == "POST":
                payload = _dict(body)
                action = parts[3]
                if action == "close":
                    card = store.mutate(lambda data: cards.close_card(
                        data, "human", card_id, payload.get("note", ""), payload.get("column")))
                    return 200, {"card": card}
                if action == "reopen":
                    card = store.mutate(lambda data: cards.reopen_card(
                        data, "human", card_id, payload.get("column")))
                    return 200, {"card": card}
                if action == "comment":
                    text = payload.get("text") or payload.get("note") or ""
                    comment = store.mutate(lambda data: cards.add_comment(
                        data, "human", card_id, text))
                    return 200, {"comment": comment}
                if action == "attachments":
                    attachment = attachments.save(
                        store, card_id, payload.get("name"), payload.get("mime"),
                        payload.get("data"))
                    return 200, {"attachment": attachment}

    if parts[:2] == ["api", "columns"]:
        if len(parts) == 2 and method == "POST":
            payload = _dict(body)
            column = store.mutate(lambda data: cards.add_column(
                data, "human", payload.get("title", ""), payload.get("color"),
                payload.get("closed", False)))
            return 200, {"column": column}
        if len(parts) == 3 and parts[2] == "reorder" and method == "POST":
            payload = _dict(body)
            ids = payload.get("ids")
            if not isinstance(ids, list):
                raise ValueError("ids must be a list")
            columns = store.mutate(lambda data: cards.reorder_columns(data, "human", ids))
            return 200, {"columns": columns}
        if len(parts) == 3:
            column_id = parts[2]
            if method == "PATCH":
                payload = _dict(body)
                column = store.mutate(lambda data: cards.update_column(
                    data, "human", column_id, **_pick(payload, ("title", "color", "closed", "order"))))
                return 200, {"column": column}
            if method == "DELETE":
                payload = _dict(body) if body else {}
                result = store.mutate(lambda data: cards.delete_column(
                    data, "human", column_id, payload.get("move_to")))
                return 200, result

    if parts[:2] == ["api", "projects"]:
        if len(parts) == 2 and method == "POST":
            payload = _dict(body)
            project = store.mutate(lambda data: projects.add_project(
                data, "human", payload.get("path", ""), payload.get("name")))
            return 200, {"project": project}
        if len(parts) == 3 and parts[2] == "reorder" and method == "POST":
            payload = _dict(body)
            order = payload.get("order")
            if not isinstance(order, list):
                raise ValueError("order must be a list of project ids")
            ordered = store.mutate(lambda data: projects.reorder_projects(
                data, "human", order))
            return 200, {"projects": ordered}
        if len(parts) == 3:
            project_id = parts[2]
            if method == "PATCH":
                payload = _dict(body)
                project = store.mutate(lambda data: projects.update_project(
                    data, "human", project_id,
                    **_pick(payload, ("name", "path", "progress", "progress_note", "color"))))
                return 200, {"project": project}
            if method == "DELETE":
                return 200, store.mutate(lambda data: projects.delete_project(
                    data, "human", project_id))

    return 404, {"error": "unknown API route"}


def handle(method, raw_path, body, store, cache, port):
    try:
        return _dispatch(method, raw_path, body, store, cache, port)
    except (ValueError, LookupError) as error:
        return 400, {"error": str(error)}
    except StoreError as error:
        return 500, {"error": str(error)}
