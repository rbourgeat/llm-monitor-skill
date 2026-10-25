"""CLI implementations for projects, timers, activity, events and briefs."""
from __future__ import annotations

from . import brief, gitinfo, model, projects
from .commands import emit_json, rel_time


def _duration(seconds):
    return projects._duration_text(seconds)


def cmd_projects_list(args, store):
    data = store.read()
    payload = []
    for project in data["projects"]:
        metrics = projects.project_metrics(data, project)
        activity = gitinfo.project_activity(project["path"]) if args.git else None
        payload.append({"project": project, "metrics": metrics, "activity": activity})
    if args.json:
        emit_json(payload)
        return
    if not payload:
        print("No projects registered. Add one with: project add /absolute/path --name NAME")
        return
    for item in payload:
        project, metrics = item["project"], item["metrics"]
        line = "[%s] %s · %d%% · open %d / closed %d · tracked today %s / total %s · %s" % (
            project["id"], project["name"], project["progress"],
            metrics["cards_open"], metrics["cards_closed"],
            _duration(metrics["tracked_today"]), _duration(metrics["tracked_total"]),
            project["path"])
        print(line)
        if project.get("progress_note"):
            print("  note: %s" % project["progress_note"])
        if item["activity"]:
            print("  git: %s" % gitinfo.format_activity(item["activity"]))
        if metrics["active_timer"]:
            print("  timer running (%s)" % _duration(projects.tracked_seconds(metrics["active_timer"])))


def cmd_projects_add(args, store):
    actor = model.actor_of(args.actor)
    project = store.mutate(lambda data: projects.add_project(data, actor, args.path, args.name))
    print("Added project [%s] %s → %s" % (project["id"], project["name"], project["path"])) if not args.json else emit_json(project)


def cmd_projects_edit(args, store):
    actor = model.actor_of(args.actor)
    def operation(data):
        kwargs = {}
        if args.name is not None:
            kwargs["name"] = args.name
        if args.path is not None:
            kwargs["path"] = args.path
        if args.progress is not None:
            kwargs["progress"] = args.progress
        if args.note is not None:
            kwargs["progress_note"] = args.note
        if args.color is not None:
            kwargs["color"] = args.color
        if not kwargs:
            raise ValueError("nothing to change")
        return projects.update_project(data, actor, args.project, **kwargs)
    project = store.mutate(operation)
    print("Updated project [%s] %s · %d%%" % (project["id"], project["name"], project["progress"])) if not args.json else emit_json(project)


def cmd_projects_rm(args, store):
    actor = model.actor_of(args.actor)
    result = store.mutate(lambda data: projects.delete_project(data, actor, args.project))
    print("Removed project [%s] %s (%d cards detached)" % (result["id"], result["name"], result["detached"])) if not args.json else emit_json(result)


def cmd_projects_reorder(args, store):
    actor = model.actor_of(args.actor)
    ordered = store.mutate(lambda data: projects.reorder_projects(data, actor, args.ids))
    if args.json:
        emit_json(ordered)
        return
    print("Project order: %s" % " → ".join(project["name"] for project in ordered))


def cmd_timer_start(args, store):
    actor = model.actor_of(args.actor)
    session = store.mutate(lambda data: projects.start_timer(
        data, actor, args.project, args.card, args.note or ""))
    print("Timer started [%s] on project · %s" % (session["id"], session["start"])) if not args.json else emit_json(session)


def cmd_timer_stop(args, store):
    actor = model.actor_of(args.actor)
    session = store.mutate(lambda data: projects.stop_timer(data, actor, args.note or ""))
    elapsed = projects.tracked_seconds(session)
    print("Timer stopped [%s] · %s" % (session["id"], _duration(elapsed))) if not args.json else emit_json(
        {"session": session, "elapsed": elapsed})


def cmd_timer_status(args, store):
    data = store.read()
    entries = projects.timer_status(data)
    payload = [{"session": entry["session"], "elapsed": entry["elapsed"],
                "project": entry["project"]} for entry in entries]
    if args.json:
        emit_json(payload)
        return
    if not entries:
        print("No active timer.")
        return
    for entry in entries:
        project = entry["project"]
        print("Running [%s] · %s · %s" % (
            entry["session"]["id"], project["name"] if project else "unknown project",
            _duration(entry["elapsed"])))


def cmd_activity(args, store):
    data = store.read()
    if args.project:
        project = model.project_by_ref(data, args.project)
        targets = [project]
    else:
        targets = data["projects"]
    payload = []
    for project in targets:
        info = gitinfo.project_activity(project["path"], timeout=args.timeout)
        payload.append({"project": project, "activity": info})
    if args.json:
        emit_json(payload)
        return
    if not payload:
        print("No projects registered.")
        return
    for item in payload:
        print("[%s] %s · %s" % (item["project"]["id"], item["project"]["name"],
                               gitinfo.format_activity(item["activity"])))


def cmd_events(args, store):
    data = store.read()
    events = data["events"][-args.limit:][::-1]
    if args.json:
        emit_json(events)
        return
    if not events:
        print("No events.")
        return
    for event in events:
        print("[%s] %s %s — %s" % (rel_time(event["ts"]), event["actor"], event["kind"], event["summary"]))


def cmd_brief(args, store):
    data = store.read()
    print(brief.build_brief(data, budget=args.budget, project_ref=args.project, include_git=args.git))


def cmd_status(args, store):
    data = store.read()
    overview = projects.overview(data)
    active = projects.timer_status(data)
    payload = {"overview": overview, "timer": [
        {"session": entry["session"], "elapsed": entry["elapsed"],
         "project": entry["project"]} for entry in active]}
    if args.json:
        emit_json(payload)
        return
    print("Projects %d · open cards %d · closed %d" % (
        overview["projects"], overview["cards_open"], overview["cards_closed"]))
    print("Tracked: today %s · week %s · total %s" % (
        _duration(overview["tracked_today"]), _duration(overview["tracked_week"]),
        _duration(overview["tracked_total"])))
    for entry in active:
        project = entry["project"]
        print("Active timer: %s · %s" % (project["name"] if project else "unknown",
                                         _duration(entry["elapsed"])))
    if overview["last_event"]:
        event = overview["last_event"]
        print("Last event: [%s] %s %s — %s" % (rel_time(event["ts"]), event["actor"],
                                                event["kind"], event["summary"]))
