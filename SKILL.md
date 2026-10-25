---
name: llm-monitor
description: Manage a local kanban board of open notes with AI and human provenance, custom columns, project git activity, progress and time tracking through a portable CLI and a tiny local web UI.
---

# LLM MONITOR

A self-contained, local-first kanban for notes, tasks and project follow-up. It ships a Python
stdlib CLI, a shared JSON store, a tiny HTTP server and a dependency-free web UI. Every mutation is
attributed to **AI** or **human**, so humans can see what an agent changed and agents can see what
humans changed.

Use this skill when you need to track open work, report progress across local projects, or keep a
durable context of what remains to be done.

## Provenance rules (non-negotiable)

- CLI mutations default to `--actor ai`. That is the actor you must use. Do not pass
  `--actor human` from an AI session.
- Do **not** call the HTTP API or automate the web UI to perform mutations. API/UI mutations are
  hard-coded as `human`; using them from an AI would fake human provenance.
- The web UI is for the human. You may read its URL, state or health, but the human performs UI
  actions.
- Never edit `data.json` by hand. Use the CLI so history and events stay consistent.
- Never delete a human-authored card without explicit permission in the current conversation.
- Ask before destructive board operations: deleting a column with cards, marking a column closed
  (it closes all its cards), or changing a registered project path.
- Preserve human content when possible: add a comment or an edit note instead of silently rewriting
  it. Every edit can carry a `--note`; use it to explain why.

## Work one card at a time

Do not batch-move every open card to Doing, and do not batch-move cards between any columns. Work
one issue at a time:

1. Pick the single next card by priority: `urgent` before `high`, `high` before `normal`, then
   `normal` before `low`. Among equal priorities prefer the most recently updated card (the order used
   by `list` and the brief), ties by lowest id. With a project filter, apply the same rule within that
   project. `list` groups cards by column, so compare priorities across all open columns instead of
   taking its first row.
2. Move **only that card** to Doing with a short note naming the work.
3. Implement, test and inspect it.
4. Close that card with a note containing concrete evidence.
5. Then pick the next card by the same priority rule.

Before step 3, read the card's project documentation when present: `README.md`, `AGENTS.md`,
`SKILL.md` and `docs/` (or `Docs/`). Follow those instructions over generic habits; a project may
require specific deliverables (for example a music video alongside the audio track). The brief
lists found and missing docs; the project detail card shows red **README.md not found** /
**AGENTS.md not found** warnings. When closing, name the docs that informed the result or state
that none exist.

Same rule for other columns: no bulk close, reopen or move unless the human explicitly asks for a
bulk operation in the current conversation. A human asking "do all issues" means complete each one
in sequence, not move the whole set into Doing simultaneously.

## Resolve the skill root

All commands below use `$SKILL_ROOT`, the directory containing this `SKILL.md`. Resolve it from the
skill installation path, then define:

```bash
SKILL_ROOT=/absolute/path/to/llm-monitor
KANBAN="$SKILL_ROOT/kanban.py"
python3 "$KANBAN" doctor
```

No packages are required. Python 3.9+ is sufficient. Git is optional and only read for project
activity.

## Quick start

```bash
# Initialize the default data home (~/.kanban), unless it already exists.
python3 "$KANBAN" init

# Compact context brief for an agent: focus cards, projects, recent events, next step.
python3 "$KANBAN" brief

# Start the human web UI in the background, then print its authoritative URL.
python3 "$KANBAN" serve --daemon
python3 "$KANBAN" url
```

The server binds `127.0.0.1` (default port 8787, falling back to the next free ports) and writes
`server.json` / `server.log` in the data home. Use `serve --status` and `serve --stop` to manage it.
`serve` without `--daemon` runs in the foreground. The UI keeps a long-poll request on
`/api/watch`; the server compares the data file's atomic-replace signature and wakes the UI when it
changes. CLI and API edits therefore appear within about half a second, without a fixed timer poll
or a server restart. The server also re-reads `data.json` on every state request.

Data location precedence: `--home` global flag, then `$KANBAN_HOME`, then `~/.kanban`. Put global
flags **before** the subcommand:

```bash
python3 "$KANBAN" --home "$HOME/.kanban-test" --json list
```

## Cards

Card references accept an exact id or a unique id prefix. Prefer full ids such as `c-fcc888` in
reports and commands.

```bash
python3 "$KANBAN" add "Ship the onboarding screen" \
  --body "Acceptance criteria…" --project "/abs/path/to/app" --priority high --tags "ui,onboarding"
python3 "$KANBAN" list                       # all cards, sorted by column (closed included)
python3 "$KANBAN" list --touched-by ai       # created, edited or closed by AI
python3 "$KANBAN" list --search onboarding
python3 "$KANBAN" show c-fcc888              # full card, project docs summary, history
python3 "$KANBAN" edit c-fcc888 --body "New context" --note "Clarified scope"
python3 "$KANBAN" move c-fcc888 doing --note "Ready to implement"
python3 "$KANBAN" close c-fcc888 --note "Merged in commit abc123"
python3 "$KANBAN" reopen c-fcc888 --column open
python3 "$KANBAN" comment c-fcc888 --text "Tests pass on main"
python3 "$KANBAN" delete c-fcc888            # only with human permission when human-authored
```

`add` defaults to the first open column but always requires `--project`. Register the project first
(`projects add`); `add` refuses an unregistered path or name. `close` defaults to the first closed
column; always pass a note that contains the evidence or reason. `edit` supports `--title`, `--body`,
`--body-file`, `--column`, `--project`, `--no-project`, `--tags`, `--priority` and `--note`; creation
enforces a project, while an edit can detach one. `--body -` reads stdin. `--json` before the
subcommand gives machine-readable output.

Card attachments are a human-only UI feature: card details and the create/edit card form accept up to
20 images/files (5 MB each); files chosen in the form upload when the card is saved. They are stored
under `<data home>/attachments/<card-id>/<attachment-id><ext>` and served from loopback.
There is no CLI attachment mutation; an AI must not upload through the HTTP API to fake human
provenance. File attachment rows link to the local server; images render inline.

## Columns

Columns are fully editable: title, color, closed/open state and order. A closed column is what
"closing a card" means; moving a card into it closes the card, moving out reopens it.

```bash
python3 "$KANBAN" columns list
python3 "$KANBAN" columns add "QA" --color "#f59e0b"
python3 "$KANBAN" columns edit qa --title "Verification" --closed
python3 "$KANBAN" columns edit qa --open
python3 "$KANBAN" columns rm qa --move-to open
python3 "$KANBAN" columns reorder open doing done
```

`columns rm` refuses to delete a column that still has cards unless `--move-to` names another
column. Marking a column closed closes every card in it; use it deliberately, not as a shortcut.

## Projects, progress and time

Register a project by absolute path for a global dashboard of progress, git activity and tracked
time. Git data is read-only: branch, last commit, dirty flag and commits in the last 7 days. In the
UI, the **Browse…** button beside *Absolute path* opens the host's native folder chooser and fills
the path; the browser cannot reveal an absolute path by itself.

```bash
python3 "$KANBAN" projects add "/abs/path/to/project" --name "Display name"
python3 "$KANBAN" projects list --git
python3 "$KANBAN" projects edit "Child Learning Game" --note "Core loop works"
python3 "$KANBAN" projects reorder "Music" "Child Learning Game"  # every project exactly once
python3 "$KANBAN" timer start "Child Learning Game" --note "Implementing scene 2"
python3 "$KANBAN" timer status
python3 "$KANBAN" timer stop --note "Paused"
python3 "$KANBAN" activity --project "Child Learning Game"
```

Progress is automatic: `int(round(closed_cards * 100 / all_cards))` (0 when there are no cards),
stored on the project with provenance from the triggering mutation. It recalculates when a card is
created, deleted, moved, closed, reopened or changes project, and when a column's closed state
changes. `projects edit --progress N` stores a temporary manual override; the next relevant mutation
recalculates it. Do not invent progress; the agent should let the board calculate it.

The timer normally follows AI card work. Moving a card into a column titled `Doing` starts the
project timer tied to that card; closing the card stops the matching session. Auto-start happens only
on an AI move and only when no timer is active; custom active columns need manual `timer start`.
Starting a timer on another project auto-stops the active timer and records the event. Tracked time is
summed into today, week and total metrics. Project references accept id, name or absolute path.
Removing a project detaches its cards and leaves the folder untouched; it does not delete cards.

## Brief, audit and status

```bash
python3 "$KANBAN" brief                 # compact; no git probes by default
python3 "$KANBAN" brief --git --project "Child Learning Game"
python3 "$KANBAN" status                # global overview
python3 "$KANBAN" events --limit 20     # newest-first audit trail
python3 "$KANBAN" doctor                # environment/data/server health
```

Start an agent turn with `brief`. It prioritizes urgent/high cards, active projects, recent events
and a next step, staying near a character budget (`--budget`, default 1600). It always states the
docs rule and project docs gaps near the top, before the focus cards, so missing README/AGENTS
guidance is visible even when the brief truncates. Use `show` for details (it prints the card
project's docs summary) and `list` for targeted filters. Use `events` to prove who changed what.

## What the human sees in the UI

The local board shows: filters (All, Human, AI, Touched by AI), a project filter, search, drag-drop
between columns, provenance badges on every card, comment/close/reopen/details modals with per-card
history and human attachments, custom-column management with a per-column sort control, and a compact
left **Projects** list. The **All projects** row at its top clears the filter; selecting a project row
filters the board to that project's cards, tints the selected row with the project color and shows its
details (automatic progress, git pills, notes and automatic timer status) below, with **Remove from
registry** instead of delete. A new card defaults to the selected project. The **Events** topbar
button opens the recent audit trail popup. The **Settings** topbar menu holds the light/dark theme
toggle (showing the current theme) and the server status (`Server on`/`Server off` with a green/gray
dot), replacing the old header Theme button and dot; Escape or a click outside closes it. Project
registration has a **Browse…** button beside
*Absolute path* that opens the host's native folder chooser. Failed git probes show a hoverable
**git unavailable** warning instead of fatal stderr text. The board refreshes
automatically when the data file changes, so CLI and API mutations appear live.

The UI is English-only, light/dark themed, and fully offline: no remote scripts, fonts, styles or
imports. All icons are local inline SVG, with no emoji or pictographic Unicode glyphs. Dropdowns are a
custom local trigger/menu pair, and scroll shadows are CSS gradients on scroll containers. The UI has
no timer controls; the automatic timer follows card moves and closes. Keep it on loopback.

## Data and recovery

The data home contains `data.json`, `data.json.bak`, `data.corrupt-<stamp>.json` on recovery,
`server.json`, `server.log` and `kanban.lock`. Saves are atomic (temp file + fsync + `os.replace`)
and guarded by an advisory file lock where available. If the main file is corrupt, the store
recovers from the backup or defaults and preserves the corrupt file. Per-card history is capped at
50 entries; the global event log is capped at 500. Back up the whole data home before bulk changes.

## Portability to another harness

Copy the **entire** directory (`SKILL.md`, `kanban.py`, `app/`, `ui/`, `tests/`, `README.md`) into
that harness's skill root. Keep `kanban.py` and `app/` together: the entrypoint inserts the skill
root into `sys.path` and imports `app.cli`. No installation step, virtualenv or package manager is
needed. If the harness expects a different manifest schema, keep the YAML `name` and `description`
and adapt extra fields; the runtime logic is independent of the harness. Do not install the same
skill twice (for example, a copy plus a symlink) or the catalog may show duplicates. The data home is
independent of the harness, so the same board can be read by different agents on the same machine.

## Files

- `kanban.py` — portable entrypoint; run it with Python 3.
- `app/` — model, normalization, store, cards, projects, git/docs probes, native folder chooser, brief, CLI and HTTP API/server.
- `ui/` — static HTML/CSS/JS; served by the local server.
- `tests/smoke.py` — stdlib smoke test; run `python3 tests/smoke.py`.
- `README.md` — user-facing overview and examples.

Keep the server on loopback. It has no authentication and is not meant to be exposed to a network.
