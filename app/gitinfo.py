"""Read-only git activity probes for registered project paths."""
from __future__ import annotations

import os
import subprocess

from .model import now_iso


def _run_git(path, args, timeout=2.5):
    command = ["git", "-C", path, "-c", "core.quotepath=false"] + args
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except FileNotFoundError:
        return None, "", "git executable not found"
    except subprocess.TimeoutExpired:
        return None, "", "git command timed out after %.1fs" % timeout
    except OSError as error:
        return None, "", str(error)
    if result.returncode != 0:
        return None, result.stdout, result.stderr.strip() or "git exited %d" % result.returncode
    return result.returncode, result.stdout, result.stderr


def project_activity(path, timeout=2.5):
    """Return a compact, never-throwing activity summary for one path."""
    path = os.path.abspath(os.path.expanduser(path))
    info = {
        "path": path,
        "exists": os.path.isdir(path),
        "git": False,
        "branch": None,
        "last_commit": None,
        "dirty": None,
        "commits_7d": None,
        "error": None,
        "checked_at": now_iso(),
    }
    if not info["exists"]:
        info["error"] = "path is missing or not a directory"
        return info
    code, out, err = _run_git(path, ["rev-parse", "--is-inside-work-tree"], timeout)
    if code is None or out.strip() != "true":
        info["error"] = err or "not a git repository"
        return info
    info["git"] = True

    code, out, err = _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"], timeout)
    info["branch"] = out.strip() if code is not None else None
    if code is None:
        info["error"] = err

    code, out, err = _run_git(path, ["log", "-1", "--format=%ct%x1f%s%x1f%an"], timeout)
    if code is not None and out.strip():
        parts = out.strip().split("\x1f")
        if len(parts) >= 3:
            try:
                epoch = int(parts[0])
            except ValueError:
                epoch = None
            info["last_commit"] = {
                "epoch": epoch,
                "ts": now_iso(epoch) if epoch is not None else None,
                "subject": parts[1][:200],
                "author": parts[2][:120],
            }
    elif code is None:
        info["error"] = err

    code, out, err = _run_git(path, ["status", "--porcelain"], timeout)
    if code is not None:
        info["dirty"] = len([line for line in out.splitlines() if line.strip()])
    else:
        info["error"] = err

    code, out, err = _run_git(path, ["rev-list", "--count", "--since=7.days", "HEAD"], timeout)
    if code is not None:
        try:
            info["commits_7d"] = int(out.strip())
        except ValueError:
            info["commits_7d"] = 0
    return info


def format_activity(info):
    """One-line human summary used by CLI output."""
    if not info["exists"]:
        return "missing path"
    if not info["git"]:
        return "not a git repo" + ((" (%s)" % info["error"]) if info["error"] else "")
    commit = info.get("last_commit") or {}
    age = commit.get("ts", "no commits")
    dirty = info.get("dirty")
    changes = "uncommitted ?" if dirty is None else (
        "clean tree" if dirty == 0 else
        "%d uncommitted file%s" % (dirty, "" if dirty == 1 else "s"))
    return "%s · %s · last %s · %s commits/7d" % (
        info.get("branch") or "detached",
        changes,
        age,
        "?" if info.get("commits_7d") is None else info["commits_7d"],
    )
