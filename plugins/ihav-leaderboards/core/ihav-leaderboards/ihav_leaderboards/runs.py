"""Run folders under ``.ihav_space/ihav-leaderboards/runs/<run-id>/`` and their JSON files."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SPACE = Path(".ihav_space") / "ihav-leaderboards" / "runs"
SCHEMA_VERSION = 1


class RunInputError(Exception):
    """A run folder file is missing or malformed."""


def new_run_id(now: datetime = None) -> str:
    now = now or datetime.now(timezone.utc)
    return "%s-%s" % (now.strftime("%Y%m%dT%H%M%S"), secrets.token_hex(4))


def create_run(project: Path, query: str) -> Path:
    run = project / SPACE / new_run_id()
    (run / "visits").mkdir(parents=True)
    (run / "leaderboards").mkdir()
    (run / "discovery").mkdir()
    write_json(run / "request.json", {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return run


def gitignore_warning(project: Path) -> str:
    """Return a warning when .ihav_space/ is not ignored; never edits the file."""
    path = project / ".gitignore"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    if any(line.strip().rstrip("/") in (".ihav_space", "/.ihav_space") for line in lines):
        return ""
    return "Warning: add .ihav_space/ to .gitignore; run files are saved there."


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RunInputError("Missing file: %s" % path)
    except (OSError, ValueError) as exc:
        raise RunInputError("Cannot read %s: %s" % (path, exc))


def write_json(path: Path, value: Any) -> None:
    """Write atomically so a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(tmp, path)


def read_folder(folder: Path) -> List[Dict[str, Any]]:
    if not folder.is_dir():
        return []
    return [read_json(p) for p in sorted(folder.glob("*.json"))]


def read_visits(run: Path) -> Dict[str, Dict[str, Any]]:
    """Visit-counter results keyed by their ``domain`` field."""
    return {item["domain"]: item for item in read_folder(run / "visits") if isinstance(item, dict) and "domain" in item}
