"""Open the host's native folder chooser for the local llm-monitor UI.

The browser cannot reveal an absolute path from its own directory picker, so the
local server opens the operating system's chooser instead. This module is only
used by the loopback HTTP API; it never mutates the board.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

PROMPT = "Choose a project folder"
TIMEOUT = 300.0


def _clean_path(raw):
    text = (raw or "").strip()
    if not text:
        return None
    return os.path.normpath(text)


def _default_start(start):
    if start and os.path.isabs(start) and os.path.isdir(start):
        return start
    return os.path.expanduser("~")


def _quote_applescript(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)


def _cancelled(stderr):
    text = (stderr or "").lower()
    return "user canceled" in text or "user cancelled" in text or "(-128)" in text


def _macos(start):
    tool = shutil.which("osascript")
    if not tool:
        raise ValueError("Native folder chooser unavailable: osascript was not found.")
    script = (
        "on run\n"
        'set startFolder to (POSIX file "%s") as alias\n'
        'set chosenFolder to choose folder with prompt "%s" default location startFolder\n'
        "return POSIX path of chosenFolder\n"
        "end run\n"
    ) % (_quote_applescript(start), PROMPT)
    result = _run([tool, "-e", script])
    if result.returncode != 0:
        if _cancelled(result.stderr):
            return None
        raise ValueError("Native folder chooser failed: %s" % (result.stderr or "unknown error"))
    return _clean_path(result.stdout)


def _linux(start):
    zenity = shutil.which("zenity")
    if zenity:
        command = [zenity, "--file-selection", "--directory", "--title", PROMPT,
                   "--filename", start.rstrip(os.sep) + os.sep]
        result = _run(command)
        if result.returncode != 0:
            if _cancelled(result.stderr) or result.returncode == 1:
                return None
            raise ValueError("Native folder chooser failed: %s" % (result.stderr or "unknown error"))
        return _clean_path(result.stdout)

    kdialog = shutil.which("kdialog")
    if kdialog:
        result = _run([kdialog, "--getexistingdirectory", start, "--title", PROMPT])
        if result.returncode != 0:
            if _cancelled(result.stderr) or result.returncode == 1:
                return None
            raise ValueError("Native folder chooser failed: %s" % (result.stderr or "unknown error"))
        return _clean_path(result.stdout)

    raise ValueError("No native folder chooser available. Install zenity or kdialog, "
                     "or type the absolute path manually.")


def _windows(start):
    tool = shutil.which("powershell") or shutil.which("pwsh")
    if not tool:
        raise ValueError("Native folder chooser unavailable: PowerShell was not found.")
    quoted = start.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description = 'Choose a project folder';"
        "$d.SelectedPath = '%s';"
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ Write-Output $d.SelectedPath }"
    ) % quoted
    result = _run([tool, "-NoProfile", "-Command", script])
    if result.returncode != 0:
        raise ValueError("Native folder chooser failed: %s" % (result.stderr or "unknown error"))
    return _clean_path(result.stdout)


def pick_folder(start=None):
    """Open the native chooser; return an absolute path or None if cancelled."""
    start_dir = _default_start(start)
    try:
        if sys.platform == "darwin":
            return _macos(start_dir)
        if sys.platform.startswith("linux"):
            return _linux(start_dir)
        if sys.platform == "win32":
            return _windows(start_dir)
    except subprocess.TimeoutExpired:
        raise ValueError("Native folder chooser timed out.")
    raise ValueError("No native folder chooser available on this platform; "
                     "type the absolute path manually.")
