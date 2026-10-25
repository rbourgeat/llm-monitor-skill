"""Stdlib smoke test for llm-monitor. Uses a temporary home; never touches real data."""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.request
from contextlib import redirect_stdout
from urllib.parse import quote

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import api, brief, cards, commands, docinfo, folder_picker, gitinfo, projects, server  # noqa: E402
from app.cli import build_parser  # noqa: E402
from app.store import Store  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    checks = 0

    def ok(condition, message):
        nonlocal checks
        check(condition, message)
        checks += 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    ok("## Install" in readme and "automatic install" in readme and
       "manual install" in readme and "Publishing to GitHub" in readme and
       'cp -R SKILL.md README.md kanban.py app ui tests "$DEST/"' in readme,
       "README documents agent install, human install and GitHub publishing")
    ok("__pycache__/" in ignore and "data.json" in ignore and "server.json" in ignore and
       "attachments/" in ignore and ".DS_Store" in ignore,
       ".gitignore excludes caches, local data, server files and attachments")

    with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as tmp:
        home = os.path.join(tmp, "kanban-home")
        os.makedirs(home)
        project_dir = os.path.join(tmp, "project")
        os.makedirs(project_dir)
        store = Store(home)
        store.initialize()
        data = store.read()
        ok(len(data["columns"]) == 3, "default columns")
        ok(any(column["closed"] for column in data["columns"]), "default closed column")

        parser = build_parser()
        ok(parser.parse_args(["add", "x"]).actor == "ai", "CLI defaults to ai")
        ok(parser.parse_args(["--actor", "human", "add", "x"]).actor == "human",
           "explicit human actor possible for human terminals")

        registered = store.mutate(lambda d: projects.add_project(
            d, "ai", project_dir, "Smoke project"))
        ok(registered["path"] == project_dir, "project registered for cards")
        docs = docinfo.project_docs(project_dir)
        ok(docs["found"] == [] and docs["missing"] == ["README.md", "AGENTS.md"] and
           docs["warnings"] == ["README.md not found", "AGENTS.md not found"],
           "empty project warns for missing README/AGENTS docs")
        with open(os.path.join(project_dir, "README.md"), "w") as handle:
            handle.write("# Smoke project\n")
        os.makedirs(os.path.join(project_dir, "Docs"))
        docs = docinfo.project_docs(project_dir)
        ok("README.md" in docs["found"] and "Docs/" in docs["found"] and
           docs["missing"] == ["AGENTS.md"] and docs["warnings"] == ["AGENTS.md not found"],
           "project docs probe finds README and docs folder, warns AGENTS")
        ok("README.md" in docinfo.format_docs(docs) and "missing AGENTS.md" in docinfo.format_docs(docs),
           "docs summary names found and missing docs")
        with open(os.path.join(project_dir, "AGENTS.md"), "w") as handle:
            handle.write("# Smoke agents\n")
        ok(docinfo.project_docs(project_dir)["warnings"] == [],
           "docs warnings clear when AGENTS exists")
        missing = docinfo.project_docs(os.path.join(tmp, "absent"))
        ok(missing["exists"] is False and missing["error"], "docs probe never throws on missing path")
        try:
            store.mutate(lambda d: cards.add_card(d, "ai", title="Orphan card"))
            raise AssertionError("card without project should fail")
        except ValueError as error:
            ok("project is required" in str(error), "cards require a project")
        first = store.mutate(lambda d: cards.add_card(
            d, "ai", title="AI smoke card", body="Created by the agent",
            project=registered["id"], priority="urgent", tags=["smoke", "ai"]))
        ok(first["created_by"] == "ai" and first["updated_by"] == "ai", "AI card provenance")

        store.mutate(lambda d: cards.update_card(
            d, "human", first["id"], body="Human clarified context",
            priority="high", note="Human edit"))
        updated = store.read()
        card = next(item for item in updated["cards"] if item["id"] == first["id"])
        ok(card["created_by"] == "ai" and card["updated_by"] == "human",
           "last editor is human")
        ok(any(entry["actor"] == "human" for entry in card["history"]),
           "human action in card history")

        status, payload = api.handle("POST", "/api/cards",
                                     {"title": "Human API card", "column": "open",
                                      "project": registered["id"]}, store, {}, 8787)
        ok(status == 200, "API card status")
        api_card = payload["card"]
        ok(api_card["created_by"] == "human", "API mutations are human")

        status, _ = api.handle("POST", "/api/timer/start", {"project": registered["id"]},
                               store, {}, 8787)
        ok(status == 404, "timer API route removed")

        status, payload = api.handle("GET", "/api/state", None, store, {}, 8787)
        ok(status == 200 and len(payload["cards"]) == 2, "API state")
        ok(payload["server"]["home"] == home, "API reports home")
        ok(bool(payload["server"]["signature"]), "API exposes data signature")
        state_docs = payload["projects"][0]["activity"]["docs"]
        ok("README.md" in state_docs["found"] and "AGENTS.md" in state_docs["found"] and
           state_docs["warnings"] == [], "API state carries project docs info")
        status, reordered = api.handle("POST", "/api/projects/reorder",
                                       {"order": [registered["id"]]}, store, {}, 8787)
        ok(status == 200 and reordered["projects"][0]["id"] == registered["id"],
           "project reorder API preserves the registry")

        original_pick = folder_picker.pick_folder
        folder_picker.pick_folder = lambda start=None: project_dir
        try:
            status, payload = api.handle("POST", "/api/browse-folder",
                                         {"start": tmp}, store, {}, 8787)
            ok(status == 200 and payload["path"] == project_dir and payload["cancelled"] is False,
               "folder browse API returns a path")
        finally:
            folder_picker.pick_folder = original_pick

        original_pick = folder_picker.pick_folder
        folder_picker.pick_folder = lambda start=None: None
        try:
            status, payload = api.handle("POST", "/api/browse-folder",
                                         {"start": tmp}, store, {}, 8787)
            ok(status == 200 and payload["path"] is None and payload["cancelled"] is True,
               "folder browse API reports cancellation")
        finally:
            folder_picker.pick_folder = original_pick

        original_run = folder_picker._run
        folder_picker._run = lambda command: subprocess.CompletedProcess(
            command, 0, stdout=project_dir + "/\n", stderr="")
        ok(folder_picker.pick_folder(project_dir) == project_dir,
           "native folder chooser parses selected path")
        folder_picker._run = lambda command: subprocess.CompletedProcess(
            command, 1, stdout="", stderr="execution error: User canceled. (-128)")
        ok(folder_picker.pick_folder(project_dir) is None, "native folder chooser cancel")
        folder_picker._run = original_run

        qa = store.mutate(lambda d: cards.add_column(d, "ai", "QA", "#f59e0b"))
        store.mutate(lambda d: cards.move_card(d, "ai", api_card["id"], qa["id"],
                                              note="API card to QA"))
        archive = store.mutate(lambda d: cards.add_column(d, "human", "Archive", closed=True))
        store.mutate(lambda d: cards.close_card(d, "ai", first["id"],
                                               note="Smoke close", column=archive["id"]))
        closed = store.read()
        closed_card = next(item for item in closed["cards"] if item["id"] == first["id"])
        ok(closed_card["closed_by"] == "ai" and closed_card["close_note"] == "Smoke close",
           "AI close provenance")
        store.mutate(lambda d: cards.reopen_card(d, "ai", first["id"], column="open"))
        reopened = store.read()
        reopened_card = next(item for item in reopened["cards"] if item["id"] == first["id"])
        ok(reopened_card["closed_by"] is None, "reopen clears closed_by")

        store.mutate(lambda d: cards.delete_column(d, "human", qa["id"], "open"))
        after_delete = store.read()
        moved = next(item for item in after_delete["cards"] if item["id"] == api_card["id"])
        ok(moved["column"] == "open", "column deletion relocates cards")

        order = [column["id"] for column in reversed(after_delete["columns"])]
        store.mutate(lambda d: cards.reorder_columns(d, "human", order))
        reordered = store.read()
        ok([column["order"] for column in reordered["columns"]] == list(range(len(order))),
           "column reorder")

        project = registered
        store.mutate(lambda d: projects.update_project(
            d, "human", project["id"], progress=35, progress_note="Core loop works"))
        store.mutate(lambda d: cards.update_card(d, "ai", first["id"],
                                                project=project["id"], note="Attach project"))
        store.mutate(lambda d: cards.move_card(d, "ai", api_card["id"], "doing",
                                              note="Start issue"))
        active = projects.timer_status(store.read())
        ok(len(active) == 1 and active[0]["project"]["id"] == project["id"] and
           active[0]["session"]["card_id"] == api_card["id"],
           "AI move to Doing auto-starts the timer")
        session = active[0]["session"]
        time.sleep(0.2)
        store.mutate(lambda d: cards.close_card(d, "ai", api_card["id"], note="Issue done",
                                               column=archive["id"]))
        ok(projects.timer_status(store.read()) == [],
           "AI close auto-stops the timer")

        final = store.read()
        project_final = next(item for item in final["projects"] if item["id"] == project["id"])
        ok(project_final["progress"] == 50 and project_final["progress_updated_by"] == "ai" and
           projects.auto_progress(final, project_final) == 50 and
           project_final["progress_note"] == "Core loop works",
           "progress automatically tracks closed cards with provenance")
        metrics = projects.project_metrics(final, project_final)
        ok(metrics["cards_total"] >= 1 and metrics["session_count"] == 1, "project metrics")
        overview = projects.overview(final)
        ok(overview["projects"] == 1 and overview["cards_total"] == 2, "overview")
        git_summary = gitinfo.format_activity({
            "exists": True, "git": True, "branch": "main", "dirty": 8,
            "last_commit": {"ts": "2026-10-24T17:00:00Z"}, "commits_7d": 3,
        })
        ok("8 uncommitted files" in git_summary and "dirty" not in git_summary,
           "git summary explains uncommitted files")
        ok(overview["events_today"]["ai"] > 0 and overview["events_today"]["human"] > 0,
           "AI and human events recorded")
        ok(session["id"] in {item["id"] for item in final["sessions"]}, "timer session persisted")

        text = brief.build_brief(final, budget=1400)
        ok("AI smoke card" in text and first["id"] in text, "brief contains actionable card")
        ok("docs: README.md, AGENTS.md, Docs/" in text, "brief lists project docs")
        ok(text.index("Docs rule:") < text.index("## Focus cards"),
           "brief puts the docs rule before focus cards")
        ok("Docs gaps: none; every project has README.md and AGENTS.md" in text,
           "brief reports no docs gaps when project docs are complete")
        ok("Priority rule: pick urgent > high > normal > low" in text,
           "brief states the priority-first selection rule before cards")
        ok("read the project's README.md" in text, "brief tells agents to read project docs first")
        ok("highest-priority open card" in text and "urgent > high > normal > low" in text,
           "brief tells agents to pick cards by priority")
        ok(len(text) <= 1600, "brief stays compact")

        show_args = parser.parse_args(["show", first["id"]])
        out = io.StringIO()
        with redirect_stdout(out):
            commands.cmd_show(show_args, store)
        ok("project docs: README.md, AGENTS.md, Docs/" in out.getvalue(),
           "show lists the card project's docs")

        status, events = api.handle("GET", "/api/events?limit=5", None, store, {}, 8787)
        ok(status == 200 and len(events["events"]) <= 5, "events endpoint")
        ok(events["events"][0]["ts"] >= events["events"][-1]["ts"], "events newest first")

        before_signature = store.signature()
        original_watch_timeout = api.WATCH_TIMEOUT
        api.WATCH_TIMEOUT = 0.2
        try:
            status, watch = api.handle("GET", "/api/watch?since=" + quote(before_signature),
                                       None, store, {}, 8787)
        finally:
            api.WATCH_TIMEOUT = original_watch_timeout
        ok(status == 200 and watch["changed"] is False, "watch reports unchanged data")
        ok(watch["signature"] == before_signature, "watch returns current signature")

        server_obj, _ = server._make_server(store, 0)
        port = server_obj.server_address[1]
        server_obj.port = port
        thread = threading.Thread(target=server_obj.serve_forever,
                                  kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%d" % port
            for _ in range(50):
                try:
                    with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                        health = json.loads(response.read().decode("utf-8"))
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("local server did not start")
            ok(health["ok"] is True, "server health")
            original_pick = folder_picker.pick_folder
            folder_picker.pick_folder = lambda start=None: project_dir
            try:
                request = urllib.request.Request(
                    base + "/api/browse-folder",
                    data=json.dumps({"start": tmp}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(request, timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                ok(payload["path"] == project_dir and payload["cancelled"] is False,
                   "folder browse HTTP endpoint")
            finally:
                folder_picker.pick_folder = original_pick
            with urllib.request.urlopen(base + "/", timeout=2) as response:
                html = response.read().decode("utf-8")
            ok("render.js" in html and "main.js" in html and "dropdowns.js" in html,
               "UI index served")
            head = html.split("</head>")[0]
            ok("kanban-theme" in head and
               head.index("kanban-theme") < head.index('rel="stylesheet"') and
               'html[data-theme="dark"] { background: #0e1117; }' in head,
               "UI applies saved theme before CSS paints (no flash)")
            ok('data-action="events"' in html and "project-detail" in html and
               "events-panel" not in html, "UI events moved to topbar popup")
            ok('id="settings-button"' in html and 'id="settings-menu"' in html and
               'id="settings-theme-value"' in html and 'id="settings-server-status"' in html and
               'id="settings-sync-dot"' in html,
               "UI settings menu holds theme and server status")
            ok('id="sync-dot"' not in html and
               html.index('data-action="theme"') > html.index('id="settings-menu"'),
               "UI theme toggle and status dot live inside the settings menu")
            ok("priority-filter" in html and "sort-order" in html,
               "UI priority filter and sort controls")
            columns_button = html.split('data-action="manage-columns"', 1)[1].split("</button>", 1)[0]
            ok('title="Manage columns"' in columns_button and
               "M6 2v12M10 2v12" in columns_button and "<circle" not in columns_button,
               "UI columns button uses an explicit columns icon")
            with urllib.request.urlopen(base + "/style.css", timeout=2) as response:
                style_css = response.read().decode("utf-8")
            with urllib.request.urlopen(base + "/components.css", timeout=2) as response:
                component_css = response.read().decode("utf-8")
            ok(".select-wrap::after" in style_css and "::file-selector-button" in component_css,
               "UI custom dropdown and file picker CSS")
            ok(".settings-menu" in style_css and ".settings-item" in style_css and
               "settings-server" in style_css,
               "UI settings menu styling")
            ok("display: inline-flex; align-items: center; gap: 3px" in component_css and
               ".card-actions button .icon" in component_css and
               "vertical-align: 0" in component_css,
               "UI card action icons align with their labels")
            ok(".git-warning {" in style_css and ".git-warning .icon" in style_css and
               "gap: 4px" in style_css,
               "UI git warning leaves a gap between icon and label")
            ok("bottom: -9px" in component_css and "bottom: -10px" in component_css and
               "modal-event-list.scroll-shadow::after" in component_css and
               "var(--panel) 24px" in component_css,
               "UI scroll shadows reach past the container padding")
            ok(".toast .icon" in component_css and ".toast.error .icon" in component_css and
               "display: inline-flex; align-items: center; gap: 8px" in component_css,
               "UI toast status icons align with their message")
            with urllib.request.urlopen(base + "/dropdowns.js", timeout=2) as response:
                dropdown_js = response.read().decode("utf-8")
            ok("enhanceSelects" in dropdown_js and "kb-option" in dropdown_js and
               ".kb-menu-layer" in style_css and ".kb-option" in style_css,
               "UI custom dropdown popup list CSS and behavior")
            ok(".overview > div" in style_css and "justify-content: space-between" in style_css,
               "UI overview label/count spacing")
            ok(".sidebar > .panel" in style_css and
               "flex: 1 1 auto; min-height: 120px" in style_css and
               "max-height: min(45vh, 440px)" not in style_css and
               "flex: 0 0 auto" in style_css and
               ".sidebar > .panel { height: auto; }" in component_css,
               "UI only the Projects list scrolls while detail and stats stay put")
            remote = []
            for asset in (ROOT / "ui").iterdir():
                if asset.suffix in (".html", ".css", ".js"):
                    text = asset.read_text(encoding="utf-8")
                    if "http://" in text or "https://" in text or "@import url(" in text:
                        remote.append(asset.name)
            ok(not remote, "UI has no remote assets or network imports")
            emoji = []
            for asset in (ROOT / "ui").iterdir():
                if asset.suffix in (".html", ".css", ".js"):
                    for char in asset.read_text(encoding="utf-8"):
                        if ord(char) > 127 and unicodedata.category(char) == "So":
                            emoji.append(asset.name + " U+" + format(ord(char), "04X"))
            ok(not emoji, "UI uses SVG icons instead of emoji or pictographic glyphs")
            with urllib.request.urlopen(base + "/icons.js", timeout=2) as response:
                icons_js = response.read().decode("utf-8")
            ok("KB.icon" in icons_js and "viewBox" in icons_js and "PATHS" in icons_js,
               "UI serves its local SVG icon set")
            ok("icons.js" in html and "<svg" in html, "UI loads local SVG icons")
            settings_button = html.split('id="settings-button"', 1)[1].split("</button>", 1)[0]
            ok("settings:" in icons_js and "M4 2v12M8 2v12M12 2v12" in settings_button and
               "gear:" not in icons_js and "M8 1.5v2" not in settings_button,
               "UI Settings button uses the sliders icon, not the gear")
            ok(".icon" in style_css and "stroke: currentColor" in style_css and
               ".kb-chevron .icon" in style_css and "▾" not in style_css,
               "UI styles SVG icons and CSS-only native select arrow")
            with urllib.request.urlopen(base + "/render.js", timeout=2) as response:
                js = response.read().decode("utf-8")
            ok("renderAll" in js, "UI render script served")
            ok('icon: "comment"' in js and "KB.icon(meta.icon)" in js and "💬" not in js and
               "comment-count" in js, "UI comments and event icons use SVG icons")
            ok("project-head-main" in js and 'aria-label="Edit project"' in js,
               "UI project card path/button markup")
            ok("project-row" in js and "git-warning" in js,
               "UI compact project rows and git warning")
            ok("project-all" in js and "All projects" in js and "KB.selectedProjectId" in js,
               "UI All projects row and selected-project accessor")
            ok("Cards from every registered project are shown." not in js and
               "Select a project above" in js,
               "UI All projects detail keeps the hint but drops the line under the name")
            ok(".project-row.all-projects" in style_css,
               "UI All projects row styling")
            ok("project-color-dot" in js and "--project-color" in js,
               "UI project rows carry their registered color")
            ok(".project-row.selected" in style_css and "--project-color" in style_css and
               style_css.index(".project-row.active") < style_css.index(".project-row.selected"),
               "UI selected project row takes the project color, not the default accent")
            ok("docs-line" in js and "doc-pill" in js and "doc-warning" in js and
               "activity.docs" in js,
               "UI project detail shows available docs and missing-doc warnings")
            ok(".docs-line" in style_css and ".doc-pill" in style_css and ".doc-warning" in style_css,
               "UI docs pills and warnings styling")
            ok("uncommittedLabel" in js and "uncommittedTitle" in js,
               "UI explains git changes instead of dirty jargon")
            ok("scroll-shadow" in component_css and
               ".card-list.scroll-shadow::after" in component_css and
               "refreshScrollShadows" in js,
               "UI scrollable boxes have bottom shadow gradients")
            ok("project-row-name" in js and "project-row-path" not in js,
               "UI project rows hide absolute paths")
            ok("data-column-sort" in js and "COLUMN_SORT_OPTIONS" in js and
               ".column-sort" in component_css, "UI per-column sort controls")
            ok("timer-toggle" not in js and "timer-stop" not in js and
               "Start timer" not in js and "Stop timer" not in js,
               "UI has no human timer controls")
            ok("auto timer" in js and "timer-card" in js, "UI shows automatic timer state")
            ok("attachment_added" in js, "UI attachment event icon")
            ok(".project-list" in style_css and "overflow-y: auto" in style_css,
               "UI project list has its own scroll")
            ok(".card-list" in component_css and "overflow-y: auto" in component_css,
               "UI card lists have their own scroll")
            with urllib.request.urlopen(base + "/modals_admin.js", timeout=2) as response:
                admin_js = response.read().decode("utf-8")
            ok("project-browse" in admin_js and "/api/browse-folder" in admin_js,
               "UI project modal includes folder browse button")
            ok("column-actions" in admin_js and ".column-actions" in component_css,
               "UI column Save/Delete controls have a gap")
            ok("Auto from closed cards" in admin_js and "Automatic progress" in js,
               "UI explains automatic progress percentage")
            ok("Remove from registry" in admin_js and "Delete project" not in admin_js and
               "folder is untouched" in admin_js,
               "UI project action says registry removal, not folder deletion")
            with urllib.request.urlopen(base + "/modals.js", timeout=2) as response:
                modal_js = response.read().decode("utf-8")
            ok("openEventsModal" in modal_js and "modal-event-list" in modal_js,
               "UI events modal helper")
            ok("attach-upload" in modal_js and "attachment-thumb" in modal_js,
               "UI card attachment upload")
            ok("card-attach-file" in modal_js and 'type="file" multiple' in modal_js and
               "uploadAttachments" in modal_js and "saveCard" in modal_js,
               "UI create/edit card forms accept attachments uploaded on save")
            ok("No project" not in modal_js and "Project is required" in modal_js,
               "UI requires a project when creating cards")
            ok("defaultProject" in modal_js and "KB.selectedProjectId" in modal_js,
               "UI new card defaults to the selected project")
            with urllib.request.urlopen(base + "/util.js", timeout=2) as response:
                util_js = response.read().decode("utf-8")
            ok("toast-message" in util_js and '"warning" : "check"' in util_js and
               "KB.icon" in util_js,
               "UI toast notifications show a status icon")
            ok("KB.elapsed" in util_js and "KB.finishedIn" in util_js and "Done in " in js and
               ".card-done-time" in component_css and ".done-time" in component_css and
               "doneIn" in modal_js,
               "UI shows completion time on done cards and in card details")
            with urllib.request.urlopen(base + "/main.js", timeout=2) as response:
                main_js = response.read().decode("utf-8")
            ok("watchChanges" in main_js and "KB.api.watch" in main_js,
               "UI live change watcher")
            ok("setSettingsOpen" in main_js and "KB.closeSettings" in main_js and
               "settings-sync-dot" in main_js and '"Server off"' in main_js and
               '"Server on"' in js,
               "UI settings menu toggles and reports server on/off")
            ok("settings-server-port" in html and "settings-server-port" in main_js and
               "settings-server-port" in js and '"port " + state.server.port' in js and
               ".settings-server-port" in style_css,
               "UI settings menu displays the server port beside Server on")
            ok("project-all" in main_js and "filters.project = project.id" in main_js and
               "KB.selectProject(filters.project" in main_js,
               "UI project selection drives the board filter")
            ok('draggable="true"' in js and "/api/projects/reorder" in main_js and
               ".project-row.drop-before" in style_css and
               "project_order_updated" in js,
               "UI project rows drag to reorder and persist order")
            ok("timer-toggle" not in main_js and "/api/timer" not in main_js,
               "UI cannot start or stop timers")
            with urllib.request.urlopen(base + "/api/state", timeout=2) as response:
                state = json.loads(response.read().decode("utf-8"))
            ok(len(state["cards"]) == 2, "server reads shared store")
            since = state["server"]["signature"]
            def trigger_watch_change():
                time.sleep(0.2)
                store.mutate(lambda d: cards.update_card(
                    d, "ai", first["id"], note="HTTP watch trigger"))
            watcher = threading.Thread(target=trigger_watch_change, daemon=True)
            watcher.start()
            with urllib.request.urlopen(base + "/api/watch?since=" + quote(since),
                                        timeout=25) as response:
                watch = json.loads(response.read().decode("utf-8"))
            watcher.join(1)
            ok(watch["changed"] is True and watch["signature"] != since,
               "HTTP watch wakes on data mutation")
            pixel = base64.b64encode(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
                b"\xf0\x1f\x00\x05\x00\x01\xff\xd8\x8f\xa9\x00\x00\x00\x00IEND\xaeB`\x82"
            ).decode("ascii")
            attachment_name = "Capture d’écran.png"
            upload = urllib.request.Request(
                base + "/api/cards/" + quote(first["id"]) + "/attachments",
                data=json.dumps({"name": attachment_name, "mime": "image/png",
                                 "data": pixel}).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(upload, timeout=5) as response:
                uploaded = json.loads(response.read().decode("utf-8"))
            ok(uploaded["attachment"]["name"] == attachment_name, "API stores attachment")
            with urllib.request.urlopen(base + "/api/state", timeout=5) as response:
                attached_state = json.loads(response.read().decode("utf-8"))
            attached_card = [card for card in attached_state["cards"]
                             if card["id"] == first["id"]][0]
            ok(len(attached_card["attachments"]) == 1, "card exposes attachment metadata")
            ok(attached_card["title"] == "AI smoke card" and
               attached_card["body"] == "Human clarified context",
               "normalization keeps card title and body beside attachments")
            url = base + "/attachments/" + quote(first["id"]) + "/" + \
                quote(uploaded["attachment"]["id"])
            with urllib.request.urlopen(url, timeout=5) as response:
                blob = response.read()
                content_type = response.headers.get("Content-Type")
                disposition = response.headers.get("Content-Disposition")
            ok(blob == base64.b64decode(pixel), "attachment endpoint serves bytes")
            ok(content_type == "image/png", "attachment endpoint serves image MIME")
            ok(disposition and "filename*=UTF-8''" in disposition and
               "Capture%20d%E2%80%99e%CC%81cran.png" in disposition,
               "attachment endpoint sends a safe UTF-8 filename header")
        finally:
            server_obj.shutdown()
            server_obj.server_close()
            thread.join(2)

        order_dir = os.path.join(tmp, "order-project")
        os.makedirs(order_dir)
        order_project = store.mutate(lambda d: projects.add_project(
            d, "human", order_dir, "Order test project"))
        reversed_ids = [order_project["id"], project["id"]]
        store.mutate(lambda d: projects.reorder_projects(d, "human", reversed_ids))
        reordered_projects = store.read()
        ok([item["id"] for item in reordered_projects["projects"]] == reversed_ids,
           "project order persists as the registry order")
        try:
            store.mutate(lambda d: projects.reorder_projects(
                d, "human", [order_project["id"]]))
            invalid_order = False
        except ValueError:
            invalid_order = True
        ok(invalid_order, "project reorder rejects incomplete order lists")
        store.mutate(lambda d: projects.delete_project(d, "human", order_project["id"]))

        with open(store.data_path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        recovered = store.read()
        ok(len(recovered["cards"]) == 2, "corruption recovery keeps cards")
        ok(recovered["meta"].get("recovered_from"), "corrupt copy recorded")
        ok(os.path.exists(recovered["meta"]["recovered_from"]), "corrupt file preserved")
        ok(os.path.exists(store.backup_path), "backup file exists")

    print("OK — %d smoke checks passed" % checks)


if __name__ == "__main__":
    main()
