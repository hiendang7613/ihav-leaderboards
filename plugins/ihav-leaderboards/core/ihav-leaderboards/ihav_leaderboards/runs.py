"""Run files, strict JSON and local run-writer serialization. No network calls."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

SPACE = Path(".ihav_space") / "ihav-leaderboards" / "runs"
SCHEMA_VERSION = 2


class RunInputError(ValueError):
    """A run file is missing, malformed or outside the run."""


class DependencyContractError(Exception):
    """Saved dependency output uses an unsupported contract."""


class RunBusyError(Exception):
    """A cooperating writer currently holds the run; wait without editing inputs."""


def new_run_id(now: datetime = None) -> str:
    now = now or datetime.now(timezone.utc)
    return "%s-%s" % (now.strftime("%Y%m%dT%H%M%S"), secrets.token_hex(4))


def create_run(project: Path, query: str, synthetic: bool = False) -> Path:
    if not isinstance(query, str) or not query.strip():
        raise RunInputError("Query must be a nonempty string.")
    run = project / SPACE / new_run_id()
    (run / "visits").mkdir(parents=True)
    (run / "leaderboards").mkdir()
    (run / "discovery").mkdir()
    write_json(run / "request.json", {
        "schema_version": SCHEMA_VERSION, "query": query,
        "synthetic": synthetic, "dependencies": {},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return run


def gitignore_warning(project: Path) -> str:
    path = project / ".gitignore"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    if any(line.strip().rstrip("/") in (".ihav_space", "/.ihav_space") for line in lines):
        return ""
    return "Warning: add .ihav_space/ to .gitignore; run files are saved there."


def _unique_object(pairs: List[Any]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key: %s" % key)
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number: %s" % value)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except FileNotFoundError as exc:
        raise RunInputError("Missing file: %s" % path) from exc
    except (OSError, ValueError) as exc:
        raise RunInputError("Cannot read %s: %s" % (path, exc)) from exc


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_text(path: Path, text: str) -> None:
    """Replace one complete file; remove our temporary file on every failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json_text(value))


def object_file(path: Path) -> Dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise RunInputError("%s must contain a JSON object." % path.name)
    return value


def read_folder(folder: Path) -> List[Dict[str, Any]]:
    if not folder.is_dir():
        return []
    return [object_file(p) for p in sorted(folder.glob("*.json"))]


def relative_file(run: Path, name: str) -> Path:
    """Resolve a saved evidence path without following it outside this run."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise RunInputError("Saved evidence path must be a nonempty relative path.")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise RunInputError("Saved evidence path must stay inside the run: %s" % name)
    target = run / relative
    try:
        target.resolve().relative_to(run.resolve())
    except ValueError as exc:
        raise RunInputError("Saved evidence path resolves outside the run: %s" % name) from exc
    return target


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise RunInputError("Cannot hash %s: %s" % (path.name, exc)) from exc
    return digest.hexdigest()


def read_visits(run: Path) -> Dict[str, Dict[str, Any]]:
    """Keep domain-less errors under their filename; never alter saved child JSON."""
    values: Dict[str, Dict[str, Any]] = {}
    for path in sorted((run / "visits").glob("*.json")):
        item = object_file(path)
        domain = item.get("domain", path.stem)
        if not isinstance(domain, str) or not domain or domain != path.stem:
            raise RunInputError("Visit domain must match its filename: %s" % path.name)
        version = item.get("contract_version")
        if isinstance(version, bool) or (version is not None and not isinstance(version, int)):
            raise RunInputError("Visit contract_version must be an integer: %s" % path.name)
        if version not in (None, 1, 2):
            raise DependencyContractError("Unsupported visit contract_version %r in %s." % (version, path.name))
        if "error" in item:
            if any(key in item for key in ("kind", "monthly_visits", "monthly_visits_text", "rank")):
                raise RunInputError("Visit error and result fields are mutually exclusive: %s" % path.name)
            if not isinstance(item["error"], dict) or not isinstance(item["error"].get("code"), str):
                raise RunInputError("Visit error needs a code: %s" % path.name)
        elif item.get("kind") not in ("estimate", "rank_only"):
            raise RunInputError("Visit result needs estimate/rank_only kind: %s" % path.name)
        values[domain] = dict(item, _contract_compatibility=(
            "current" if version == 2 else "legacy_unversioned" if version is None else "legacy_v1"))
    return values


@contextmanager
def run_lock(run: Path) -> Iterator[None]:
    """Serialize cooperating CLI writers; OS releases the lock after a crash."""
    if not run.is_dir():
        raise RunInputError("Run folder does not exist: %s" % run)
    lock = run / ".run.lock"
    if lock.is_symlink():
        raise RunInputError("Run lock must not be a symlink.")
    with lock.open("a+b") as handle:
        acquired = False
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                raise RunInputError("This platform has no supported local file-lock API.")
            acquired = True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise RunBusyError("Another writer holds this run; try again after it finishes.") from exc
            raise
        try:
            yield
        finally:
            if acquired and fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif acquired and msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
