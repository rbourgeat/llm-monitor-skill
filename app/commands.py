"""CLI implementations for cards, comments and columns."""
from __future__ import annotations

import json
import sys

from . import cards, docinfo, model
from .model import UNSET, parse_iso


def emit_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def rel_time(value):
    moment = parse_iso(value)
    if not moment:
        return "unknown"
    import datetime as dt
    seconds = max(0, int((dt.datetime.now(dt.timezone.utc) - moment).total_seconds()))
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        return "%dh" % (seconds // 3600)
    return "%dd" % (seconds // 86400)


def read_text(value=None, file_path=None):
    if file_path:
        with open(file_path, "r", encoding="utf-8") as handle:
            return handle.read()
    if value == "-":
        return sys.stdin.read()
    return value


def project_name(data, project_id):
    project = next((item for item in data["projects"] if item["id"] == project_id), None)
    return project["name"] if project else "none"


def column_title(data, column_id):
    column = next((item for item in data["columns"] if item["id"] == column_id), None)
    return column["title"] if column else column_id


def card_line(data, card):
    tags = (" #" + " #".join(card["tags"])) if card["tags"] else ""
    return "[%s] %s%s · %s · %s · %s · %s→%s · %s ago · %d comments" % (
        card["id"], card["title"], tags, column_title(data, card["column"]),
        project_name(data, card.get("project")), card["priority"],
        card["created_by"], card["updated_by"], rel_time(card["updated_at"]),
        len(card.get("comments") or []))


def cmd_add(args, store):
    actor = model.actor_of(args.actor)
    body = read_text(args.body, args.body_file)
    card = store.mutate(lambda data: cards.add_card(
        data, actor, title=args.title, body=body or "", column=args.column,
        project=args.project, tags=args.tags, priority=args.priority))
    data = store.read()
    if args.json:
        emit_json(card)
    else:
        print("Created %s" % card_line(data, card))


def cmd_list(args, store):
    data = store.read()
    selected = list(data["cards"])
    if args.column:
        column = model.column_by_id(data, args.column)
        selected = [card for card in selected if card["column"] == column["id"]]
    if args.project:
        project = model.project_by_ref(data, args.project)
        selected = [card for card in selected if card.get("project") == project["id"]]
    if args.created_by:
        selected = [card for card in selected if card["created_by"] == args.created_by]
    if args.touched_by:
        selected = [card for card in selected
                    if args.touched_by in (card["created_by"], card["updated_by"], card.get("closed_by"))]
    if args.search:
        needle = args.search.casefold()
        selected = [card for card in selected
                    if needle in (card["title"] + " " + card["body"] + " " + " ".join(card["tags"])).casefold()]
    order = {column["id"]: column["order"] for column in data["columns"]}
    selected.sort(key=lambda card: (order.get(card["column"], 99),
                                    model.PRIORITY_RANK.get(card["priority"], 9),
                                    -(parse_iso(card["updated_at"]).timestamp()
                                      if parse_iso(card["updated_at"]) else 0)))
    if args.json:
        emit_json({"cards": selected, "columns": data["columns"],
                   "projects": data["projects"]})
        return
    if not selected:
        print("No cards match.")
        return
    for card in selected:
        print(card_line(data, card))


def cmd_show(args, store):
    data = store.read()
    card = model.card_by_ref(data, args.card)
    if args.json:
        emit_json(card)
        return
    print("%s  [%s]" % (card["title"], card["id"]))
    print("column: %s · project: %s · priority: %s" % (
        column_title(data, card["column"]), project_name(data, card.get("project")),
        card["priority"]))
    project = next((item for item in data["projects"] if item["id"] == card.get("project")), None)
    if project:
        print("project docs: %s" % docinfo.format_docs(docinfo.project_docs(project["path"])))
    print("created: %s by %s · updated: %s by %s" % (
        card["created_at"], card["created_by"], card["updated_at"], card["updated_by"]))
    if card.get("closed_at"):
        print("closed: %s by %s%s" % (
            card["closed_at"], card["closed_by"],
            (" — " + card["close_note"]) if card.get("close_note") else ""))
    if card["tags"]:
        print("tags: %s" % ", ".join(card["tags"]))
    print("\n%s" % (card["body"] or "(no body)"))
    if card.get("comments"):
        print("\nComments:")
        for comment in card["comments"][-10:]:
            print("  [%s] %s — %s" % (comment["ts"], comment["actor"], comment["text"]))
    if card.get("history"):
        print("\nHistory (last 10):")
        for entry in card["history"][-10:]:
            print("  [%s] %s %s — %s" % (entry["ts"], entry["actor"], entry["action"], entry["summary"]))


def cmd_edit(args, store):
    if not any([args.title, args.body is not None, args.body_file, args.tags,
                args.priority, args.column, args.project, args.no_project]):
        raise ValueError("nothing to edit; pass --title/--body/--column/--project/--tags/--priority")
    body = read_text(args.body, args.body_file)
    actor = model.actor_of(args.actor)
    def operation(data):
        kwargs = {"note": args.note or ""}
        if args.title is not None:
            kwargs["title"] = args.title
        if body is not None:
            kwargs["body"] = body
        if args.tags is not None:
            kwargs["tags"] = args.tags
        if args.priority is not None:
            kwargs["priority"] = args.priority
        if args.column:
            kwargs["column"] = args.column
        if args.no_project:
            kwargs["project"] = None
        elif args.project:
            kwargs["project"] = args.project
        return cards.update_card(data, actor, args.card, **kwargs)
    card = store.mutate(operation)
    data = store.read()
    if args.json:
        emit_json(card)
    else:
        print("Updated %s" % card_line(data, card))


def cmd_move(args, store):
    actor = model.actor_of(args.actor)
    card = store.mutate(lambda data: cards.move_card(data, actor, args.card, args.column, args.note or ""))
    data = store.read()
    print(card_line(data, card)) if not args.json else emit_json(card)


def cmd_close(args, store):
    actor = model.actor_of(args.actor)
    card = store.mutate(lambda data: cards.close_card(data, actor, args.card, args.note or "", args.column))
    data = store.read()
    print("Closed %s" % card_line(data, card)) if not args.json else emit_json(card)


def cmd_reopen(args, store):
    actor = model.actor_of(args.actor)
    card = store.mutate(lambda data: cards.reopen_card(data, actor, args.card, args.column))
    data = store.read()
    print("Reopened %s" % card_line(data, card)) if not args.json else emit_json(card)


def cmd_comment(args, store):
    text = read_text(args.text, args.text_file)
    if not text:
        raise ValueError("comment text is required (--text or --text-file)")
    actor = model.actor_of(args.actor)
    comment = store.mutate(lambda data: cards.add_comment(data, actor, args.card, text))
    print("Comment %s added to [%s]" % (comment["id"], args.card)) if not args.json else emit_json(comment)


def cmd_delete(args, store):
    actor = model.actor_of(args.actor)
    result = store.mutate(lambda data: cards.delete_card(data, actor, args.card))
    print("Deleted [%s] %s" % (result["id"], result["title"])) if not args.json else emit_json(result)


def cmd_columns_list(args, store):
    data = store.read()
    counts = {}
    for card in data["cards"]:
        counts[card["column"]] = counts.get(card["column"], 0) + 1
    if args.json:
        emit_json([dict(column, cards=counts.get(column["id"], 0)) for column in data["columns"]])
        return
    for column in sorted(data["columns"], key=lambda item: item["order"]):
        print("[%s] %s · %s · %d cards" % (
            column["id"], column["title"], "closed" if column["closed"] else "open",
            counts.get(column["id"], 0)))


def cmd_columns_add(args, store):
    actor = model.actor_of(args.actor)
    column = store.mutate(lambda data: cards.add_column(data, actor, args.title, args.color, args.closed))
    print("Added column [%s] %s" % (column["id"], column["title"])) if not args.json else emit_json(column)


def cmd_columns_edit(args, store):
    actor = model.actor_of(args.actor)
    def operation(data):
        kwargs = {}
        if args.title is not None:
            kwargs["title"] = args.title
        if args.color is not None:
            kwargs["color"] = args.color
        if args.closed:
            kwargs["closed"] = True
        if args.open:
            kwargs["closed"] = False
        if args.order is not None:
            kwargs["order"] = args.order
        if not kwargs:
            raise ValueError("nothing to change")
        return cards.update_column(data, actor, args.column, **kwargs)
    column = store.mutate(operation)
    print("Updated column [%s] %s" % (column["id"], column["title"])) if not args.json else emit_json(column)


def cmd_columns_rm(args, store):
    actor = model.actor_of(args.actor)
    result = store.mutate(lambda data: cards.delete_column(data, actor, args.column, args.move_to))
    print("Deleted column [%s]; moved %d cards" % (result["id"], result["moved"])) if not args.json else emit_json(result)


def cmd_columns_reorder(args, store):
    actor = model.actor_of(args.actor)
    columns = store.mutate(lambda data: cards.reorder_columns(data, actor, args.ids))
    print("Columns: %s" % " → ".join(column["title"] for column in columns)) if not args.json else emit_json(columns)
