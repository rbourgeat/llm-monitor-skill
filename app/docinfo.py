"""Read-only discovery of a project's own documentation files.

Agents working a card must consult the project's README/AGENTS/SKILL/docs
before implementing, so the board surfaces which docs exist and warns when
README.md or AGENTS.md is absent. Probes never throw and never recurse.
"""
from __future__ import annotations

import os

from .model import now_iso

FILE_DOCS = {
    "readme.md": "README.md",
    "readme": "README.md",
    "agents.md": "AGENTS.md",
    "skill.md": "SKILL.md",
    "skills.md": "SKILLS.md",
}
FILE_ORDER = ["readme.md", "readme", "agents.md", "skill.md", "skills.md"]
DIR_DOCS = {"docs", "doc"}
REQUIRED = ["README.md", "AGENTS.md"]


def project_docs(path):
    """Return a compact, never-throwing docs summary for one project path."""
    path = os.path.abspath(os.path.expanduser(path))
    info = {
        "path": path,
        "exists": os.path.isdir(path),
        "found": [],
        "missing": [],
        "warnings": [],
        "error": None,
        "checked_at": now_iso(),
    }
    if not info["exists"]:
        info["error"] = "path is missing or not a directory"
        return info
    try:
        entries = list(os.scandir(path))
    except OSError as error:
        info["error"] = str(error)
        return info
    files, dirs = {}, []
    for entry in entries:
        key = entry.name.lower()
        try:
            is_file = entry.is_file()
            is_dir = entry.is_dir()
        except OSError:
            continue
        if is_file and key in FILE_DOCS:
            files[key] = entry.name
        elif is_dir and key in DIR_DOCS:
            dirs.append(entry.name)
    found, seen = [], set()
    for key in FILE_ORDER:
        if key not in files:
            continue
        label = FILE_DOCS[key]
        if label not in seen:
            seen.add(label)
            found.append(label)
    for name in sorted(dirs):
        label = name.rstrip("/") + "/"
        if label not in seen:
            seen.add(label)
            found.append(label)
    info["found"] = found
    for label in REQUIRED:
        if label not in seen:
            info["missing"].append(label)
            info["warnings"].append("%s not found" % label)
    return info


def format_docs(info):
    """One-line CLI/brief summary."""
    if not info["exists"]:
        return "path missing"
    parts = []
    if info["found"]:
        parts.append(", ".join(info["found"]))
    if info["missing"]:
        parts.append("missing " + ", ".join(info["missing"]))
    return " · ".join(parts) or "no project docs"
