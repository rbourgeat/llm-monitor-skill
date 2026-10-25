"""Project registry, progress, time tracking and aggregate metrics."""
from __future__ import annotations

import datetime as dt
import os

from . import model
from .model import (UNSET, actor_of, clamp_progress, clean_text, now_iso,
                    parse_iso)


def _epoch(value):
    moment = parse_iso(value)
    return moment.timestamp() if moment else None


def _day_start_epoch():
    local = dt.datetime.now().astimezone()
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _week_start_epoch():
    local = dt.datetime.now().astimezone()
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - dt.timedelta(days=local.weekday())).timestamp()


def _session_span(session, now_epoch=None):
    start = _epoch(session.get("start"))
    end = _epoch(session.get("end"))
    if start is None:
        return None
    end = end if end is not None else (now_epoch or dt.datetime.now(dt.timezone.utc).timestamp())
    return start, max(start, end)


def tracked_seconds(session, now_epoch=None):
    span = _session_span(session, now_epoch)
    return int(span[1] - span[0]) if span else 0


def tracked_total(data, project_id=None, since_epoch=None, now_epoch=None):
    now_epoch = now_epoch or dt.datetime.now(dt.timezone.utc).timestamp()
    total = 0
    for session in data["sessions"]:
        if project_id is not None and session.get("project_id") != project_id:
            continue
        span = _session_span(session, now_epoch)
        if not span:
            continue
        start, end = span
        if since_epoch is not None:
            start = max(start, since_epoch)
        if end > start:
            total += int(end - start)
    return total


def auto_progress(data, project):
    """Percentage of this project's cards that sit in closed columns."""
    closed_ids = {col["id"] for col in data["columns"] if col["closed"]}
    cards = [card for card in data["cards"] if card.get("project") == project["id"]]
    if not cards:
        return 0
    closed = len([card for card in cards if card["column"] in closed_ids])
    return int(round(closed * 100.0 / len(cards)))


def recalculate_progress(data, actor, project_refs):
    """Update stored progress after card counts or closed-column membership change."""
    actor = actor_of(actor)
    if isinstance(project_refs, str):
        project_refs = [project_refs]
    seen = set()
    for project_ref in project_refs or []:
        if not project_ref or project_ref in seen:
            continue
        seen.add(project_ref)
        project = model.project_by_ref(data, project_ref)
        value = auto_progress(data, project)
        if value != project["progress"]:
            update_project(data, actor, project["id"], progress=value)


def project_metrics(data, project):
    closed_ids = {col["id"] for col in data["columns"] if col["closed"]}
    cards = [card for card in data["cards"] if card.get("project") == project["id"]]
    open_cards = [card for card in cards if card["column"] not in closed_ids]
    closed_cards = [card for card in cards if card["column"] in closed_ids]
    last_note = max((card["updated_at"] for card in cards), default=None)
    sessions = [session for session in data["sessions"] if session.get("project_id") == project["id"]]
    active = [session for session in sessions if not session.get("end")]
    return {
        "project_id": project["id"],
        "cards_total": len(cards),
        "cards_open": len(open_cards),
        "cards_closed": len(closed_cards),
        "last_note_at": last_note,
        "tracked_today": tracked_total(data, project["id"], _day_start_epoch()),
        "tracked_week": tracked_total(data, project["id"], _week_start_epoch()),
        "tracked_total": tracked_total(data, project["id"]),
        "session_count": len(sessions),
        "active_timer": active[-1] if active else None,
    }


def overview(data):
    closed_ids = {col["id"] for col in data["columns"] if col["closed"]}
    active = model.active_sessions(data)
    day_start = _day_start_epoch()
    events_today = {"ai": 0, "human": 0}
    for event in data["events"]:
        epoch = _epoch(event.get("ts"))
        if epoch is not None and epoch >= day_start:
            events_today[event["actor"]] = events_today.get(event["actor"], 0) + 1
    return {
        "projects": len(data["projects"]),
        "cards_open": len([card for card in data["cards"] if card["column"] not in closed_ids]),
        "cards_closed": len([card for card in data["cards"] if card["column"] in closed_ids]),
        "cards_total": len(data["cards"]),
        "tracked_today": tracked_total(data, None, day_start),
        "tracked_week": tracked_total(data, None, _week_start_epoch()),
        "tracked_total": tracked_total(data, None),
        "active_timer": active[-1] if active else None,
        "events_today": events_today,
        "last_event": data["events"][-1] if data["events"] else None,
    }


def add_project(data, actor, path, name=None):
    actor = actor_of(actor)
    value = clean_text(path, 1000).strip()
    if not value:
        raise ValueError("project path is required")
    if not os.path.isabs(os.path.expanduser(value)):
        raise ValueError("project path must be absolute")
    absolute = os.path.abspath(os.path.expanduser(value))
    if not os.path.isdir(absolute):
        raise ValueError("project path is not a directory: %s" % absolute)
    real = os.path.realpath(absolute)
    for project in data["projects"]:
        if os.path.realpath(project["path"]) == real:
            raise ValueError("project already registered: %s (%s)" %
                             (project["name"], project["id"]))
    label = clean_text(name, 120).strip() or os.path.basename(absolute) or absolute
    project = {
        "id": model.new_id("p"),
        "name": label,
        "path": absolute,
        "progress": 0,
        "progress_note": "",
        "progress_updated_at": None,
        "progress_updated_by": actor,
        "added_by": actor,
        "created_at": now_iso(),
        "color": model.COLORS[len(data["projects"]) % len(model.COLORS)],
    }
    data["projects"].append(project)
    model.record_event(data, actor=actor, kind="project_added",
                       summary="Project added: %s (%s)" % (label, absolute),
                       project_id=project["id"])
    return project


def update_project(data, actor, project_ref, *, name=UNSET, path=UNSET,
                   progress=UNSET, progress_note=UNSET, color=UNSET):
    actor = actor_of(actor)
    project = model.project_by_ref(data, project_ref)
    changes = []
    if name is not UNSET:
        value = clean_text(name, 120).strip()
        if not value:
            raise ValueError("project name cannot be empty")
        if value != project["name"]:
            changes.append({"field": "name", "from": project["name"], "to": value})
            project["name"] = value
    if path is not UNSET:
        value = clean_text(path, 1000).strip()
        if not os.path.isabs(os.path.expanduser(value)):
            raise ValueError("project path must be absolute")
        absolute = os.path.abspath(os.path.expanduser(value))
        if not os.path.isdir(absolute):
            raise ValueError("project path is not a directory: %s" % absolute)
        if absolute != project["path"]:
            changes.append({"field": "path", "from": project["path"], "to": absolute})
            project["path"] = absolute
    if progress is not UNSET:
        value = clamp_progress(progress)
        if value != project["progress"]:
            changes.append({"field": "progress", "from": project["progress"], "to": value})
            project["progress"] = value
            project["progress_updated_at"] = now_iso()
            project["progress_updated_by"] = actor
    if progress_note is not UNSET:
        value = clean_text(progress_note, 2000).strip()
        if value != project["progress_note"]:
            changes.append({"field": "progress_note", "from": project["progress_note"], "to": value})
            project["progress_note"] = value
            project["progress_updated_at"] = now_iso()
            project["progress_updated_by"] = actor
    if color is not UNSET and color != project["color"]:
        changes.append({"field": "color", "from": project["color"], "to": color})
        project["color"] = color
    if changes:
        fields = ", ".join(change["field"] for change in changes)
        model.record_event(data, actor=actor, kind="project_updated",
                           summary="Project %s updated: %s" % (project["name"], fields),
                           project_id=project["id"])
    return project


def reorder_projects(data, actor, order_ids):
    actor = actor_of(actor)
    current = [project["id"] for project in data["projects"]]
    requested = [str(item).strip() for item in order_ids or []]
    if len(requested) != len(current) or set(requested) != set(current):
        raise ValueError("order must list every project exactly once")
    if requested == current:
        return data["projects"]
    ordered = [model.project_by_ref(data, project_id) for project_id in requested]
    data["projects"] = ordered
    model.record_event(data, actor=actor, kind="project_order_updated",
                       summary="Project order updated: %s" %
                       ", ".join(project["name"] for project in ordered))
    return ordered


def delete_project(data, actor, project_ref):
    actor = actor_of(actor)
    project = model.project_by_ref(data, project_ref)
    ts = now_iso()
    affected = 0
    for card in data["cards"]:
        if card.get("project") == project["id"]:
            card["project"] = None
            card["updated_by"] = actor
            card["updated_at"] = ts
            model.append_history(card, actor=actor, action="project_removed",
                                 summary="Project %s removed from registry" % project["name"])
            affected += 1
    for session in data["sessions"]:
        if session.get("project_id") == project["id"]:
            session["project_id"] = None
            if not session.get("end"):
                session["end"] = ts
    data["projects"] = [item for item in data["projects"] if item["id"] != project["id"]]
    model.record_event(data, actor=actor, kind="project_deleted",
                       summary="Project deleted: %s (%d cards detached)" %
                       (project["name"], affected))
    return {"id": project["id"], "name": project["name"], "detached": affected}


def start_timer(data, actor, project_ref, card_ref=None, note=""):
    actor = actor_of(actor)
    project = model.project_by_ref(data, project_ref)
    card = model.card_by_ref(data, card_ref) if card_ref else None
    ts = now_iso()
    for session in model.active_sessions(data):
        session["end"] = ts
        model.record_event(data, actor=actor, kind="timer_auto_stopped",
                           summary="Timer auto-stopped (new timer started)",
                           project_id=session.get("project_id"))
    session = {
        "id": model.new_id("s"),
        "project_id": project["id"],
        "card_id": card["id"] if card else None,
        "actor": actor,
        "start": ts,
        "end": None,
        "note": clean_text(note, 1000).strip(),
    }
    data["sessions"].append(session)
    model.record_event(data, actor=actor, kind="timer_started",
                       summary="Timer started on %s%s" %
                       (project["name"], (" — " + card["title"]) if card else ""),
                       project_id=project["id"], card_id=card["id"] if card else None)
    return session


def stop_timer(data, actor, note=""):
    actor = actor_of(actor)
    active = model.active_sessions(data)
    if not active:
        raise ValueError("no active timer")
    ts = now_iso()
    stopped = []
    for session in active:
        session["end"] = ts
        stopped.append(session)
        project = next((item for item in data["projects"] if item["id"] == session.get("project_id")), None)
        model.record_event(data, actor=actor, kind="timer_stopped",
                           summary="Timer stopped on %s (%s)" %
                           (project["name"] if project else "unknown project",
                            _duration_text(tracked_seconds(session))),
                           project_id=session.get("project_id"))
    if note:
        stopped[-1]["note"] = (stopped[-1].get("note") or "") + (" " if stopped[-1].get("note") else "") + clean_text(note, 500)
    return stopped[-1]


def _duration_text(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "%dh %dm" % (hours, minutes)
    if minutes:
        return "%dm %ds" % (minutes, secs)
    return "%ds" % secs


def timer_status(data):
    active = model.active_sessions(data)
    return [{
        "session": session,
        "elapsed": tracked_seconds(session),
        "project": next((item for item in data["projects"] if item["id"] == session.get("project_id")), None),
    } for session in active]
