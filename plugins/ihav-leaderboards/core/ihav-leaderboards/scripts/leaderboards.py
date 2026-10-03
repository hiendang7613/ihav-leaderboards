#!/usr/bin/env python3
"""Portable entry point for Claude Code, Codex and direct terminal use."""

from __future__ import annotations

import sys
from pathlib import Path


if sys.version_info < (3, 9):
    print("ihav-leaderboards requires Python 3.9 or later.", file=sys.stderr)
    raise SystemExit(64)


SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from ihav_leaderboards.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
