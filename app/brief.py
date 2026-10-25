"""Compact context brief that lets an LLM pick work without reading everything."""
from __future__ import annotations

import datetime as dt

from . import docinfo, gitinfo, model, projects


def _ago(value):
    moment = model.parse_iso(value)
    if not moment:
        return "unknown"
    seconds = max(0, int((dt.datetime.now(dt.timezone.utc) - moment).total_seconds()))
    if seconds < 60:
        return "%ds ago" % seconds
    minutes = seconds // 60
    if minutes < 60:
        return "%dm ago" % minutes
    hours = minutes // 60
    if hours < 24:
        return "%dh ago" % hours
    return "%dd ago" % (hours // 24)


def _dur(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return "%dh%02dm" % (hours, minutes)
    return "%dm" % minutes


def _card_line(card, data, closed_ids):
    project = next((item for item in data["projects"] if item["id"] == card.get("project")), None)
    column = next((item for item in data["columns"] if item["id"] == card["column"]), None)
    parts = [
        "- [%s] %s" % (card["id"], card["title"]),
        "col=%s" % (column["title"] if column else card["column"]),
        "project=%s" % (project["name"] if project else "none"),
        "prio=%s" % card["priority"],
        "by=%s>%s" % (card["created_by"], card["updated_by"]),
        "updated=%s" % _ago(card["updated_at"]),
    ]
    if card.get("comments"):
        parts.append("comments=%d" % len(card["comments"]))
    return " · ".join(parts)


def build_brief(data, budget=1600, project_ref=None, include_git=False):
    """Return a markdown-ish brief capped near `budget` characters."""
    lines = []
    now = dt.datetime.now().astimezone()
    lines.append("# Kanban brief — %s" % now.strftime("%Y-%m-%d %H:%M"))
    overview = projects.overview(data)
    lines.append("Projects %d · open cards %d · closed %d · tracked today %s · week %s" % (
        overview["projects"], overview["cards_open"], overview["cards_closed"],
        _dur(overview["tracked_today"]), _dur(overview["tracked_week"])))
    active = projects.timer_status(data)
    if active:
        entry = active[-1]
        label = entry["project"]["name"] if entry["project"] else "unknown"
        lines.append("Active timer: %s (%s)" % (label, _dur(entry["elapsed"])))
    if overview["last_event"]:
        event = overview["last_event"]
        lines.append("Last event: %s [%s] %s" % (_ago(event["ts"]), event["actor"], event["summary"]))

    gaps = []
    for project in data["projects"]:
        docs = docinfo.project_docs(project["path"])
        if docs["warnings"]:
            gaps.append("%s — %s" % (project["name"], ", ".join(docs["warnings"])))
    lines.append("Docs rule: before implementing a card, read its project's README.md, AGENTS.md, "
                 "SKILL.md and docs/.")
    lines.append("Docs gaps: %s" % (" · ".join(gaps) if gaps else
                                   "none; every project has README.md and AGENTS.md"))
    lines.append("Priority rule: pick urgent > high > normal > low; within a priority, newest update "
                 "first.")

    project_id = None
    if project_ref:
        project = model.project_by_ref(data, project_ref)
        project_id = project["id"]
        lines.append("Filtered project: %s (%s)" % (project["name"], project["id"]))

    closed_ids = {col["id"] for col in data["columns"] if col["closed"]}
    focus = [card for card in data["cards"]
             if card["column"] not in closed_ids
             and (project_id is None or card.get("project") == project_id)]
    focus.sort(key=lambda card: (model.PRIORITY_RANK.get(card["priority"], 9),
                                 model.parse_iso(card["updated_at"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
    focus.reverse()
    focus.sort(key=lambda card: model.PRIORITY_RANK.get(card["priority"], 9))
    lines.append("")
    lines.append("## Focus cards (%d open%s)" % (
        len(focus), "" if project_id is None else " in project"))
    for card in focus[:12]:
        lines.append(_card_line(card, data, closed_ids))
    if len(focus) > 12:
        lines.append("- … %d more open cards (use list --column)" % (len(focus) - 12))

    lines.append("")
    lines.append("## Projects")
    visible = [project for project in data["projects"]
               if project_id is None or project["id"] == project_id]
    for project in visible[:12]:
        metrics = projects.project_metrics(data, project)
        lines.append("- %s [%s] %d%% · open %d / closed %d · tracked %s (today %s) · %s" % (
            project["name"], project["id"], project["progress"],
            metrics["cards_open"], metrics["cards_closed"],
            _dur(metrics["tracked_total"]), _dur(metrics["tracked_today"]),
            project["path"]))
        if project.get("progress_note"):
            lines.append("  progress note: %s" % project["progress_note"][:180])
        docs = docinfo.project_docs(project["path"])
        lines.append("  docs: %s" % docinfo.format_docs(docs))
        if include_git:
            activity = gitinfo.project_activity(project["path"], timeout=1.5)
            lines.append("  git: %s" % gitinfo.format_activity(activity))
    if len(visible) > 12:
        lines.append("- … %d more projects" % (len(visible) - 12))

    lines.append("")
    lines.append("## Recent events")
    for event in data["events"][-6:][::-1]:
        lines.append("- %s [%s] %s: %s" % (_ago(event["ts"]), event["actor"], event["kind"], event["summary"]))

    lines.append("")
    lines.append("Next: pick the highest-priority open card (urgent > high > normal > low; newest "
                 "update first on ties), read the project's README.md, AGENTS.md, SKILL.md and docs/ "
                 "before implementing, comment evidence, close when verified. "
                 "Use `show <id>` or `list --project` for details.")
    text = "\n".join(lines)
    if len(text) > budget:
        text = text[:max(200, budget - 80)].rstrip() + "\n… (brief truncated; use list/show for full detail)"
    return text
