"""Command-line interface for llm-monitor (harness-agnostic entry point)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request

from . import commands, commands_projects, server
from .store import Store, StoreError


def _health(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def cmd_url(args, store):
    info = store.read_server_info()
    if not info:
        raise ValueError("server is not running; start it with `serve --daemon`")
    url = info.get("url") or "http://127.0.0.1:%s" % info.get("port")
    health = _health(url)
    if not health:
        raise ValueError("server.json exists but %s is not responding; try `serve --daemon`" % url)
    print(url) if not args.json else commands.emit_json({"url": url, "health": health})


def cmd_init(args, store):
    data = store.initialize()
    payload = {"home": store.home, "data": store.data_path,
               "cards": len(data["cards"]), "projects": len(data["projects"]),
               "columns": len(data["columns"])}
    print("Initialized %s\nData: %s\nCards %d · projects %d · columns %d" % (
        store.home, store.data_path, payload["cards"], payload["projects"],
        payload["columns"])) if not args.json else commands.emit_json(payload)


def cmd_doctor(args, store):
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("python", sys.version_info >= (3, 9), platform.python_version())
    add("data-home", os.path.isdir(store.home) and os.access(store.home, os.W_OK), store.home)
    try:
        data = store.read()
        add("data-file", True, "%s · %d cards · %d projects" %
            (store.data_path, len(data["cards"]), len(data["projects"])))
    except Exception as error:
        add("data-file", False, str(error))
    add("git", bool(shutil.which("git")), shutil.which("git") or "not found")
    info = store.read_server_info()
    if info:
        url = info.get("url") or "http://127.0.0.1:%s" % info.get("port")
        health = _health(url)
        add("server", bool(health), "%s (%s)" % (url, "responding" if health else "stale"))
    else:
        add("server", False, "not running (optional; UI needs it)")
    if args.json:
        commands.emit_json(checks)
        return
    for check in checks:
        print("%s %s — %s" % ("OK  " if check["ok"] else "WARN", check["check"], check["detail"]))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="kanban", description="Project kanban CLI with AI/human provenance.")
    parser.add_argument("--home", default=None, help="data directory (default ~/.kanban or $KANBAN_HOME)")
    parser.add_argument("--actor", choices=("ai", "human"), default="ai",
                        help="who performs this mutation (CLI defaults to ai)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run/stop the local web app")
    serve.add_argument("--port", type=int, default=int(os.environ.get("KANBAN_PORT", "8787")))
    serve.add_argument("--daemon", action="store_true", help="start detached in the background")
    serve.add_argument("--stop", action="store_true", help="stop a daemon server")
    serve.add_argument("--status", action="store_true", help="show server status")
    serve.add_argument("--open", action="store_true", help="open the UI in the default browser")

    sub.add_parser("init", help="create the data file")
    sub.add_parser("url", help="print the running web app URL")
    sub.add_parser("doctor", help="check environment and data health")

    add = sub.add_parser("add", help="create a card")
    add.add_argument("title")
    add.add_argument("--body", default=None, help="body text; '-' reads stdin")
    add.add_argument("--body-file", default=None)
    add.add_argument("--column", default=None)
    add.add_argument("--project", default=None, help="project id, name or absolute path")
    add.add_argument("--tags", default=None, help="comma-separated tags")
    add.add_argument("--priority", choices=("low", "normal", "high", "urgent"), default="normal")

    listing = sub.add_parser("list", help="list cards")
    listing.add_argument("--column", default=None)
    listing.add_argument("--project", default=None)
    listing.add_argument("--created-by", choices=("ai", "human"), default=None)
    listing.add_argument("--touched-by", choices=("ai", "human"), default=None)
    listing.add_argument("--search", default=None)

    show = sub.add_parser("show", help="show one card in detail")
    show.add_argument("card")

    edit = sub.add_parser("edit", help="edit a card")
    edit.add_argument("card")
    edit.add_argument("--title", default=None)
    edit.add_argument("--body", default=None, help="'-' reads stdin")
    edit.add_argument("--body-file", default=None)
    edit.add_argument("--column", default=None)
    edit.add_argument("--project", default=None)
    edit.add_argument("--no-project", action="store_true", help="detach from project")
    edit.add_argument("--tags", default=None)
    edit.add_argument("--priority", choices=("low", "normal", "high", "urgent"), default=None)
    edit.add_argument("--note", default=None)

    move = sub.add_parser("move", help="move a card to another column")
    move.add_argument("card")
    move.add_argument("column")
    move.add_argument("--note", default=None)

    close = sub.add_parser("close", help="close a card (move to a closed column)")
    close.add_argument("card")
    close.add_argument("--note", default=None)
    close.add_argument("--column", default=None)

    reopen = sub.add_parser("reopen", help="reopen a card")
    reopen.add_argument("card")
    reopen.add_argument("--column", default=None)

    comment = sub.add_parser("comment", help="append a comment")
    comment.add_argument("card")
    comment.add_argument("--text", default=None, help="'-' reads stdin")
    comment.add_argument("--text-file", default=None)

    delete = sub.add_parser("delete", help="delete a card")
    delete.add_argument("card")

    columns = sub.add_parser("columns", help="manage board columns")
    columns_sub = columns.add_subparsers(dest="columns_command", required=True)
    columns_sub.add_parser("list")
    col_add = columns_sub.add_parser("add")
    col_add.add_argument("title")
    col_add.add_argument("--closed", action="store_true")
    col_add.add_argument("--color", default=None)
    col_edit = columns_sub.add_parser("edit")
    col_edit.add_argument("column")
    col_edit.add_argument("--title", default=None)
    col_edit.add_argument("--color", default=None)
    col_edit.add_argument("--closed", action="store_true")
    col_edit.add_argument("--open", action="store_true")
    col_edit.add_argument("--order", type=int, default=None)
    col_rm = columns_sub.add_parser("rm")
    col_rm.add_argument("column")
    col_rm.add_argument("--move-to", default=None)
    col_order = columns_sub.add_parser("reorder")
    col_order.add_argument("ids", nargs="+")

    projects = sub.add_parser("projects", help="manage the project registry")
    projects_sub = projects.add_subparsers(dest="projects_command", required=True)
    proj_list = projects_sub.add_parser("list")
    proj_list.add_argument("--git", action="store_true")
    proj_add = projects_sub.add_parser("add")
    proj_add.add_argument("path")
    proj_add.add_argument("--name", default=None)
    proj_edit = projects_sub.add_parser("edit")
    proj_edit.add_argument("project")
    proj_edit.add_argument("--name", default=None)
    proj_edit.add_argument("--path", default=None)
    proj_edit.add_argument("--progress", type=int, default=None)
    proj_edit.add_argument("--note", default=None)
    proj_edit.add_argument("--color", default=None)
    proj_rm = projects_sub.add_parser("rm")
    proj_rm.add_argument("project")
    proj_order = projects_sub.add_parser("reorder")
    proj_order.add_argument("ids", nargs="+")

    timer = sub.add_parser("timer", help="time tracking")
    timer_sub = timer.add_subparsers(dest="timer_command", required=True)
    timer_start = timer_sub.add_parser("start")
    timer_start.add_argument("project")
    timer_start.add_argument("--card", default=None)
    timer_start.add_argument("--note", default=None)
    timer_stop = timer_sub.add_parser("stop")
    timer_stop.add_argument("--note", default=None)
    timer_sub.add_parser("status")

    activity = sub.add_parser("activity", help="git activity per project")
    activity.add_argument("--project", default=None)
    activity.add_argument("--timeout", type=float, default=2.5)

    events = sub.add_parser("events", help="recent audit events")
    events.add_argument("--limit", type=int, default=20)

    brief = sub.add_parser("brief", help="compact context brief for an LLM")
    brief.add_argument("--budget", type=int, default=1600, help="approx character cap")
    brief.add_argument("--project", default=None)
    brief.add_argument("--git", action="store_true", help="include git probes (slower)")

    sub.add_parser("status", help="global overview")
    return parser


def dispatch(args, store):
    if args.command == "serve":
        return server.cli_serve(args, store)
    if args.command == "init":
        return cmd_init(args, store)
    if args.command == "url":
        return cmd_url(args, store)
    if args.command == "doctor":
        return cmd_doctor(args, store)
    if args.command == "add":
        return commands.cmd_add(args, store)
    if args.command == "list":
        return commands.cmd_list(args, store)
    if args.command == "show":
        return commands.cmd_show(args, store)
    if args.command == "edit":
        return commands.cmd_edit(args, store)
    if args.command == "move":
        return commands.cmd_move(args, store)
    if args.command == "close":
        return commands.cmd_close(args, store)
    if args.command == "reopen":
        return commands.cmd_reopen(args, store)
    if args.command == "comment":
        return commands.cmd_comment(args, store)
    if args.command == "delete":
        return commands.cmd_delete(args, store)
    if args.command == "columns":
        mapping = {"list": commands.cmd_columns_list, "add": commands.cmd_columns_add,
                   "edit": commands.cmd_columns_edit, "rm": commands.cmd_columns_rm,
                   "reorder": commands.cmd_columns_reorder}
        return mapping[args.columns_command](args, store)
    if args.command == "projects":
        mapping = {"list": commands_projects.cmd_projects_list,
                   "add": commands_projects.cmd_projects_add,
                   "edit": commands_projects.cmd_projects_edit,
                   "rm": commands_projects.cmd_projects_rm,
                   "reorder": commands_projects.cmd_projects_reorder}
        return mapping[args.projects_command](args, store)
    if args.command == "timer":
        mapping = {"start": commands_projects.cmd_timer_start,
                   "stop": commands_projects.cmd_timer_stop,
                   "status": commands_projects.cmd_timer_status}
        return mapping[args.timer_command](args, store)
    if args.command == "activity":
        return commands_projects.cmd_activity(args, store)
    if args.command == "events":
        return commands_projects.cmd_events(args, store)
    if args.command == "brief":
        return commands_projects.cmd_brief(args, store)
    if args.command == "status":
        return commands_projects.cmd_status(args, store)
    raise ValueError("unknown command: %s" % args.command)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store(args.home)
    try:
        dispatch(args, store)
        return 0
    except (ValueError, LookupError, StoreError, OSError) as error:
        if args.json:
            commands.emit_json({"error": str(error)})
        else:
            print("error: %s" % error, file=sys.stderr)
        return 2
