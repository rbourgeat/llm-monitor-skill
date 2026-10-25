#!/usr/bin/env python3
"""Portable llm-monitor entry point; run from any directory."""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
