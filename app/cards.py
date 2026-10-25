"""Card, comment and column mutations for llm-monitor."""
from __future__ import annotations

from . import model
from .model import (PRIORITIES, UNSET, actor_of, clean_tags, clean_text,
                    now_iso, priority_of)


CARD_FIELDS = ("title", "body", "column", "project", "tags", "priority")


def _label(card, limit=70):
    title = card.get("title") or "Untitled"
    return title[:limit] + ("…" if len(title) > limit else "")


def _field_names(changes):
    names = [change["field"] for change in changes]
    text = ", ".join(names[:4])
    return text + ("…" if len(names) > 4 else "")


def _auto_timer(data, actor, card, old_column, new_column):
    """AI starts the project timer on Doing; any close stops that card's timer."""
    from . import projects

    active = model.active_sessions(data)
    if new_column["closed"]:
        if any(session.get("card_id") == card["id"] for session in active):
            projects.stop_timer(data, actor, "Card closed — timer stopped")
        return
    if actor != "ai" or new_column["title"].strip().lower() != "doing":
        return
    if not card.get("project"):
        return
    if any(session.get("card_id") == card["id"] for session in active):
        return
    if active:
        return
    projects.start_timer(data, actor, card["project"], card["id"],
                         "Auto timer — card moved to Doing")


def _auto_progress(data, actor, project_refs):
    """Recompute stored progress after a card count or closed-state change."""
    from . import projects

    projects.recalculate_progress(data, actor, project_refs)


def _apply_card_update(data, card, actor, *, title=UNSET, body=UNSET,
                       column=UNSET, project=UNSET, tags=UNSET,
                       priority=UNSET, note=""):
    old = {field: card.get(field) for field in CARD_FIELDS}
    ts = now_iso()
    if title is not UNSET:
        value = clean_text(title, 200).strip()
        if not value:
            raise ValueError("title cannot be empty")
        card["title"] = value
    if body is not UNSET:
        card["body"] = clean_text(body)
    if tags is not UNSET:
        card["tags"] = clean_tags(tags)
    if priority is not UNSET:
        if priority not in PRIORITIES:
            raise ValueError("priority must be one of %s" % ", ".join(PRIORITIES))
        card["priority"] = priority
    if project is not UNSET:
        if project is None:
            card["project"] = None
        else:
            card["project"] = model.project_by_ref(data, project)["id"]
    column_changed = column is not UNSET and column != card["column"]
    new_column = None
    if column is not UNSET:
        new_column = model.column_by_id(data, column)
        card["column"] = new_column["id"]
        if new_column["closed"]:
            card["closed_at"] = card.get("closed_at") or ts
            card["closed_by"] = actor
            card["close_note"] = clean_text(note, 500)
        else:
            card["closed_at"] = None
            card["closed_by"] = None
            card["close_note"] = ""
    changes = model.diff_changes(old, card, CARD_FIELDS)
    if not changes and not note:
        return card
    if column_changed:
        old_column = model.column_by_id(data, old["column"])
        if new_column["closed"] and not old_column["closed"]:
            action, text = "closed", "Closed in %s" % new_column["title"]
        elif not new_column["closed"] and old_column["closed"]:
            action, text = "reopened", "Reopened to %s" % new_column["title"]
        else:
            action, text = "moved", "Moved %s → %s" % (old_column["title"], new_column["title"])
    elif changes:
        action, text = "edited", "Edited %s" % _field_names(changes)
    else:
        action, text = "noted", "Note added"
    if note:
        text += ": " + clean_text(note, 300)
    card["updated_by"] = actor
    card["updated_at"] = ts
    model.append_history(card, actor=actor, action=action, summary=text, changes=changes)
    model.record_event(data, actor=actor, kind=action,
                       summary="%s — %s" % (_label(card), text),
                       card_id=card["id"], project_id=card.get("project"))
    if column_changed:
        _auto_timer(data, actor, card, old_column, new_column)
    if column_changed or old["project"] != card.get("project"):
        _auto_progress(data, actor, [old["project"], card.get("project")])
    return card


def add_card(data, actor, *, title, body="", column=None, project=None,
             tags=None, priority="normal"):
    actor = actor_of(actor)
    value = clean_text(title, 200).strip()
    if not value:
        raise ValueError("title is required")
    column_obj = model.column_by_id(data, column) if column else model.first_open_column(data)
    if column_obj is None:
        raise ValueError("no usable column; add an open column first")
    if not project:
        raise ValueError("project is required")
    project_obj = model.project_by_ref(data, project)
    if priority not in PRIORITIES:
        raise ValueError("priority must be one of %s" % ", ".join(PRIORITIES))
    ts = now_iso()
    card = {
        "id": model.new_id("c"),
        "title": value,
        "body": clean_text(body),
        "column": column_obj["id"],
        "project": project_obj["id"] if project_obj else None,
        "tags": clean_tags(tags),
        "priority": priority_of(priority),
        "created_by": actor,
        "created_at": ts,
        "updated_by": actor,
        "updated_at": ts,
        "closed_at": ts if column_obj["closed"] else None,
        "closed_by": actor if column_obj["closed"] else None,
        "close_note": "",
        "comments": [],
        "attachments": [],
        "history": [],
    }
    model.append_history(card, actor=actor, action="created",
                         summary="Created in %s" % column_obj["title"])
    data["cards"].append(card)
    model.record_event(data, actor=actor, kind="created",
                       summary="%s — Created in %s" % (_label(card), column_obj["title"]),
                       card_id=card["id"], project_id=card.get("project"))
    _auto_progress(data, actor, [card.get("project")])
    return card


def update_card(data, actor, card_ref, *, title=UNSET, body=UNSET, column=UNSET,
                project=UNSET, tags=UNSET, priority=UNSET, note=""):
    actor = actor_of(actor)
    card = model.card_by_ref(data, card_ref)
    return _apply_card_update(data, card, actor, title=title, body=body, column=column,
                              project=project, tags=tags, priority=priority, note=note)


def move_card(data, actor, card_ref, column_id, note=""):
    return update_card(data, actor, card_ref, column=column_id, note=note)


def close_card(data, actor, card_ref, note="", column=None):
    actor = actor_of(actor)
    target = model.column_by_id(data, column) if column else model.first_closed_column(data)
    if target is None:
        raise ValueError("no closed column configured; mark a column as closed first")
    return update_card(data, actor, card_ref, column=target["id"], note=note)


def reopen_card(data, actor, card_ref, column=None):
    actor = actor_of(actor)
    target = model.column_by_id(data, column) if column else model.first_open_column(data)
    if target is None:
        raise ValueError("no open column configured")
    return update_card(data, actor, card_ref, column=target["id"])


def add_comment(data, actor, card_ref, text):
    actor = actor_of(actor)
    card = model.card_by_ref(data, card_ref)
    value = clean_text(text, 4000).strip()
    if not value:
        raise ValueError("comment text is required")
    ts = now_iso()
    comment = {"id": model.new_id("m"), "ts": ts, "actor": actor, "text": value}
    card["comments"].append(comment)
    card["comments"] = card["comments"][-200:]
    card["updated_by"] = actor
    card["updated_at"] = ts
    preview = value[:160] + ("…" if len(value) > 160 else "")
    model.append_history(card, actor=actor, action="commented",
                         summary="Comment: " + preview)
    model.record_event(data, actor=actor, kind="commented",
                       summary="%s — Comment: %s" % (_label(card), preview),
                       card_id=card["id"], project_id=card.get("project"))
    return comment


def add_attachment(data, actor, card_ref, attachment):
    actor = actor_of(actor)
    card = model.card_by_ref(data, card_ref)
    card.setdefault("attachments", [])
    card["attachments"].append(attachment)
    card["attachments"] = card["attachments"][-20:]
    ts = now_iso()
    card["updated_by"] = actor
    card["updated_at"] = ts
    label = _label(card)
    model.append_history(card, actor=actor, action="attached",
                         summary="Attached %s" % attachment.get("name", "file"))
    model.record_event(data, actor=actor, kind="attachment_added",
                       summary="%s — Attached %s" % (label, attachment.get("name", "file")),
                       card_id=card["id"], project_id=card.get("project"))
    return attachment


def delete_card(data, actor, card_ref):
    actor = actor_of(actor)
    card = model.card_by_ref(data, card_ref)
    label = _label(card)
    data["cards"] = [item for item in data["cards"] if item["id"] != card["id"]]
    model.record_event(data, actor=actor, kind="deleted",
                       summary="%s — Deleted" % label, card_id=card["id"],
                       project_id=card.get("project"))
    _auto_progress(data, actor, [card.get("project")])
    return {"id": card["id"], "title": label}


def add_column(data, actor, title, color=None, closed=False):
    actor = actor_of(actor)
    value = clean_text(title, 80).strip()
    if not value:
        raise ValueError("column title is required")
    base = model.slugify(value)
    cid, n = base, 2
    existing = {col["id"] for col in data["columns"]}
    while cid in existing:
        cid, n = "%s-%d" % (base, n), n + 1
    column = {
        "id": cid,
        "title": value,
        "color": color or model.COLORS[len(data["columns"]) % len(model.COLORS)],
        "closed": bool(closed),
        "order": len(data["columns"]),
    }
    data["columns"].append(column)
    model.record_event(data, actor=actor, kind="column_added",
                       summary="Column added: %s%s" % (value, " (closed)" if closed else ""))
    return column


def update_column(data, actor, column_id, *, title=UNSET, color=UNSET,
                  closed=UNSET, order=UNSET):
    actor = actor_of(actor)
    column = model.column_by_id(data, column_id)
    changes = []
    closed_changed = False
    if title is not UNSET:
        value = clean_text(title, 80).strip()
        if not value:
            raise ValueError("column title cannot be empty")
        if value != column["title"]:
            changes.append({"field": "title", "from": column["title"], "to": value})
            column["title"] = value
    if color is not UNSET and color != column["color"]:
        changes.append({"field": "color", "from": column["color"], "to": color})
        column["color"] = color
    if order is not UNSET and order != column["order"]:
        column["order"] = int(order)
    if closed is not UNSET and bool(closed) != column["closed"]:
        closed_changed = True
        column["closed"] = bool(closed)
        changes.append({"field": "closed", "from": not closed, "to": bool(closed)})
        ts = now_iso()
        affected = [card for card in data["cards"] if card["column"] == column["id"]]
        for card in affected:
            if column["closed"]:
                card["closed_at"] = card.get("closed_at") or ts
                card["closed_by"] = actor
            else:
                card["closed_at"] = None
                card["closed_by"] = None
                card["close_note"] = ""
            model.append_history(card, actor=actor, action="column_state",
                                 summary="Column %s marked %s" %
                                 (column["title"], "closed" if column["closed"] else "open"))
    if changes:
        model.record_event(data, actor=actor, kind="column_updated",
                           summary="Column %s updated: %s" %
                           (column["title"], _field_names(changes)))
    if closed_changed:
        _auto_progress(data, actor, [card.get("project") for card in affected])
    return column


def delete_column(data, actor, column_id, move_to=None):
    actor = actor_of(actor)
    column = model.column_by_id(data, column_id)
    cards = [card for card in data["cards"] if card["column"] == column["id"]]
    if cards and not move_to:
        raise ValueError("column has %d cards; pass move_to to relocate them" % len(cards))
    if move_to:
        target = model.column_by_id(data, move_to)
        if target["id"] == column["id"]:
            raise ValueError("move_to must be a different column")
        for card in cards:
            _apply_card_update(data, card, actor, column=target["id"],
                               note="Column %s removed" % column["title"])
    data["columns"] = [item for item in data["columns"] if item["id"] != column["id"]]
    for index, item in enumerate(sorted(data["columns"], key=lambda col: col["order"])):
        item["order"] = index
    model.record_event(data, actor=actor, kind="column_deleted",
                       summary="Column deleted: %s (%d cards moved)" %
                       (column["title"], len(cards)))
    return {"id": column["id"], "title": column["title"], "moved": len(cards)}


def reorder_columns(data, actor, order_ids):
    actor = actor_of(actor)
    ids = [str(item) for item in order_ids]
    existing = {col["id"] for col in data["columns"]}
    if set(ids) != existing or len(ids) != len(existing):
        raise ValueError("order_ids must list every column exactly once")
    for index, cid in enumerate(ids):
        model.column_by_id(data, cid)["order"] = index
    model.record_event(data, actor=actor, kind="columns_reordered",
                       summary="Columns reordered")
    return sorted(data["columns"], key=lambda col: col["order"])
