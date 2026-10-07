"""Source-bound stage receipts and recoverable publication.

Only a complete receipt makes outputs current. Multiple files cannot be replaced
atomically together; the manifest is committed last and verified before consumption.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import __version__
from .runs import SCHEMA_VERSION, RunInputError, file_digest, object_file, relative_file, write_json, write_text

STATE_NAME = "run_state.json"
FINAL_OUTPUTS = ("final.json", "leaderboard.md", "leaderboard.csv", "report.html")


class StaleRunError(Exception):
    """Saved stage cannot be used against the current files/runtime."""


def runtime_identity() -> Dict[str, str]:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(list(package.glob("*.py")) + list(package.glob("*.html"))):
        digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes())
    return {"version": __version__, "code_sha256": digest.hexdigest()}


def _add_file(run: Path, files: Dict[str, str], path: Path) -> None:
    name = path.relative_to(run).as_posix()
    checked = relative_file(run, name)
    if checked.is_file():
        files[name] = file_digest(checked)


def input_digests(run: Path, stage: str) -> Dict[str, str]:
    """Include missing/added files through the complete path set, and source bytes."""
    files: Dict[str, str] = {}
    for name in ("request.json", "boards.json"):
        _add_file(run, files, run / name)
    for folder in ("visits", "discovery"):
        for path in sorted((run / folder).rglob("*")):
            if path.is_file():
                _add_file(run, files, path)
    if stage == "score":
        for name in ("weights.json", "matches.json", "dimensions.json"):
            _add_file(run, files, run / name)
        for path in sorted((run / "leaderboards").glob("*.json")):
            _add_file(run, files, path)
            board = object_file(path)
            snapshot = board.get("snapshot")
            if isinstance(snapshot, str) and snapshot:
                _add_file(run, files, relative_file(run, snapshot))
        if (run / "dimensions.json").exists():
            dims = object_file(run / "dimensions.json")
            for observation in dims.get("observations", []):
                if isinstance(observation, dict) and isinstance(observation.get("snapshot"), str):
                    _add_file(run, files, relative_file(run, observation["snapshot"]))
    return files


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GENERATION = re.compile(r"^[0-9a-f]{32}$")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def _hashes(run: Path, value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise RunInputError("%s must map relative file paths to SHA-256 strings." % label)
    for name, digest in value.items():
        relative_file(run, name)
        if Path(name).as_posix() != name or name == "." or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise RunInputError("Malformed %s path/hash: %s." % (label, name))


def validate_state(run: Path, state: Any) -> Dict[str, Any]:
    """Reject malformed identities before deciding whether a valid receipt is stale."""
    if (not isinstance(state, dict) or type(state.get("schema_version")) is not int
            or state["schema_version"] != SCHEMA_VERSION or not isinstance(state.get("stages"), dict)
            or set(state["stages"]) - {"weigh", "score"}):
        raise RunInputError("Unsupported or malformed run_state.json.")
    for stage, entry in state["stages"].items():
        label = "%s receipt" % stage
        if not isinstance(entry, dict) or entry.get("status") not in ("invalidated", "running", "failed", "complete", "rendering"):
            raise RunInputError("Malformed %s status." % label)
        status = entry["status"]
        if status == "invalidated":
            if stage != "score" or set(entry) != {"status", "reason"} or not _nonempty(entry.get("reason")):
                raise RunInputError("Malformed invalidated %s." % label)
            continue
        generation, runtime, config = entry.get("generation"), entry.get("runtime"), entry.get("config")
        if not isinstance(generation, str) or not _GENERATION.fullmatch(generation):
            raise RunInputError("Malformed %s generation." % label)
        if (not isinstance(runtime, dict) or set(runtime) != {"version", "code_sha256"}
                or not _nonempty(runtime.get("version")) or not isinstance(runtime.get("code_sha256"), str)
                or not _SHA256.fullmatch(runtime["code_sha256"])):
            raise RunInputError("Malformed %s runtime identity." % label)
        if not isinstance(config, dict):
            raise RunInputError("Malformed %s configuration." % label)
        if stage == "weigh":
            if set(config) != {"top_n"} or type(config.get("top_n")) is not int or (status == "complete" and config["top_n"] < 1):
                raise RunInputError("Malformed %s top_n configuration." % label)
        elif config:
            raise RunInputError("Malformed score configuration.")
        if not _timestamp(entry.get("started_at")):
            raise RunInputError("Malformed %s started_at." % label)
        if status == "failed" and not _nonempty(entry.get("reason")):
            raise RunInputError("Malformed %s failure reason." % label)
        if status == "rendering" and stage != "score":
            raise RunInputError("Only a score receipt can be rendering.")
        if "archive" in entry:
            relative_file(run, entry["archive"])
        for key in ("inputs", "outputs"):
            if key in entry or status in ("complete", "rendering"):
                _hashes(run, entry.get(key), "%s.%s" % (stage, key))
        expected = {"weights.json"} if stage == "weigh" else set(FINAL_OUTPUTS)
        if "outputs" in entry and set(entry["outputs"]) != expected:
            raise RunInputError("Malformed %s output set." % label)
        if "completed_at" in entry or status in ("complete", "rendering"):
            if not _timestamp(entry.get("completed_at")):
                raise RunInputError("Malformed %s completed_at." % label)
        if stage == "score" and ("weigh_generation" in entry or status in ("complete", "rendering")):
            linked = entry.get("weigh_generation")
            if not isinstance(linked, str) or not _GENERATION.fullmatch(linked):
                raise RunInputError("Malformed score weigh_generation.")
    return state


def read_state(run: Path) -> Dict[str, Any]:
    path = run / STATE_NAME
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    return validate_state(run, object_file(path))


def archive_outputs(run: Path, names: Any, reason: str, state: Dict[str, Any]) -> Any:
    """Copy and verify all backups before removing any original; journal progress."""
    present = [name for name in names if (run / name).exists() or (run / name).is_symlink()]
    if not present:
        return None
    for name in present:
        path = run / name
        if path.is_symlink() or not path.is_file():
            raise RunInputError("Output must be a regular file: %s" % name)
    history = run / ".history"
    if history.is_symlink() or (history.exists() and not history.is_dir()):
        raise RunInputError("Run history must be a directory, not a symlink or file.")
    relative_file(run, ".history")  # Reject an external resolved parent before mutation.
    history.mkdir(exist_ok=True)
    archive = history / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4))
    if history.is_symlink():
        raise RunInputError("Run history changed to a symlink.")
    archive.mkdir()
    inventory = {name: file_digest(run / name) for name in present}
    manifest = {
        "reason": reason, "status": "preparing", "expected_files": inventory,
        "files": {}, "removed_from_root": [], "prior_state": state,
        "recovery": "Only files listed in files have verified backups here. Unlisted originals remain at the run root; verify all hashes before reuse.",
    }
    journal = archive / "manifest.json"
    def check_archive() -> None:
        if history.is_symlink() or archive.is_symlink():
            raise RunInputError("Run history/archive must not be a symlink.")
        relative_file(run, archive.relative_to(run).as_posix())

    def record() -> None:
        check_archive()
        write_json(journal, manifest)

    record()
    try:
        for name in present:
            check_archive()
            if (archive / name).is_symlink():
                raise RunInputError("Archive output must not be a symlink: %s." % name)
            shutil.copyfile(run / name, archive / name)
            if file_digest(archive / name) != inventory[name]:
                raise OSError("Archive copy hash mismatch: %s" % name)
            manifest["files"][name] = inventory[name]
            record()
        manifest["status"] = "copied"
        manifest["recovery"] = "All named files have verified backups here; some originals may remain at the run root. Copy only needed files back and verify before reuse."
        record()
        for name in present:
            check_archive()
            source = run / name
            if source.is_symlink() or not source.is_file() or file_digest(source) != inventory[name]:
                raise StaleRunError("Output changed while archiving: %s." % name)
            source.unlink()
            manifest["removed_from_root"].append(name)
            record()
        manifest["status"] = "complete"
        record()
    except (OSError, RunInputError, StaleRunError) as exc:
        manifest["status"] = "copy_failed" if len(manifest["files"]) != len(inventory) else "removal_incomplete"
        manifest["error"] = str(exc)
        try:
            record()
        except (OSError, RunInputError):
            pass  # The last successful progress record and preserved bytes remain.
        raise
    return archive.relative_to(run).as_posix()

def begin_stage(run: Path, stage: str, config: Dict[str, Any]) -> Dict[str, Any]:
    state = read_state(run)
    prior = {"schema_version": state["schema_version"], "stages": dict(state["stages"])}
    attempt = {"status": "running", "generation": secrets.token_hex(16), "config": config,
               "runtime": runtime_identity(),
               "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    state["stages"][stage] = attempt
    if stage == "weigh":
        state["stages"]["score"] = {"status": "invalidated", "reason": "A weigh attempt began."}
    write_json(run / STATE_NAME, state)  # Invalidate first, including interrupted attempts.
    names = ("weights.json",) + FINAL_OUTPUTS if stage == "weigh" else FINAL_OUTPUTS
    archive = archive_outputs(run, names, "Before %s attempt %s" % (stage, attempt["generation"]), prior)
    if archive:
        attempt["archive"] = archive
        write_json(run / STATE_NAME, state)
    return attempt


def fail_stage(run: Path, stage: str, reason: str, exit_code: int, boards: Any = None,
               config: Any = None) -> None:
    state = read_state(run)
    entry = state["stages"].get(stage)
    if entry is None or entry.get("status") == "invalidated":
        entry = {"generation": secrets.token_hex(16), "config": config or {},
                 "runtime": runtime_identity(), "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    entry.update(status="failed", reason=reason)
    state["stages"][stage] = entry
    # Record the failed receipt and diagnostic before attempting recoverable cleanup.
    write_json(run / STATE_NAME, state)
    diagnostic = {"stage": stage, "reason": reason, "exit_code": exit_code}
    if boards is not None:
        diagnostic["boards"] = boards
    write_json(run / "diagnostic.json", diagnostic)
    names = ("weights.json",) + FINAL_OUTPUTS if stage == "weigh" else FINAL_OUTPUTS
    try:
        archive_outputs(run, names, "Failed %s publication" % stage, state)
    except (OSError, RunInputError, StaleRunError) as exc:
        diagnostic["cleanup_error"] = str(exc)
        try:
            write_json(run / "diagnostic.json", diagnostic)
        except OSError:
            pass
        raise

def check_stage(run: Path, stage: str, state: Any = None, ignore_html: bool = False) -> Dict[str, Any]:
    state = read_state(run) if state is None else validate_state(run, state)
    entry = state["stages"].get(stage)
    if not isinstance(entry, dict) or entry.get("status") != "complete":
        raise StaleRunError("%s has no complete receipt; run %s locally." % (stage, stage))
    if entry.get("runtime") != runtime_identity():
        raise StaleRunError("%s runtime changed; run weigh and score locally." % stage)
    if not isinstance(entry.get("config"), dict) or not isinstance(entry.get("inputs"), dict):
        raise RunInputError("Malformed %s receipt." % stage)
    if entry["inputs"] != input_digests(run, stage):
        raise StaleRunError("%s inputs changed; run weigh and score locally." % stage)
    outputs = entry.get("outputs")
    expected = ("weights.json",) if stage == "weigh" else FINAL_OUTPUTS
    if not isinstance(outputs, dict) or set(outputs) != set(expected):
        raise RunInputError("Malformed %s output receipt." % stage)
    for name, expected_digest in outputs.items():
        if ignore_html and stage == "score" and name == "report.html":
            continue
        path = relative_file(run, name)
        if path.is_symlink() or not path.is_file() or file_digest(path) != expected_digest:
            raise StaleRunError("%s output %s is missing or changed." % (stage, name))
    if stage == "score":
        weigh = check_stage(run, "weigh", state)
        if entry.get("weigh_generation") != weigh["generation"]:
            raise StaleRunError("score belongs to an earlier weigh attempt; run score locally.")
    return entry


def publish(run: Path, stage: str, attempt: Dict[str, Any], inputs: Dict[str, str],
            outputs: Dict[str, str]) -> None:
    expected = ("weights.json",) if stage == "weigh" else FINAL_OUTPUTS
    if set(outputs) != set(expected):
        raise RunInputError("Publication must provide every %s output." % stage)
    if input_digests(run, stage) != inputs:
        raise StaleRunError("Inputs changed during %s; no current outputs were published." % stage)
    runtime = attempt["runtime"]
    if runtime_identity() != runtime:
        raise StaleRunError("Runtime changed during computation; rerun locally.")
    temporary = Path(tempfile.mkdtemp(prefix=".publish-", dir=str(run)))
    try:
        for name, content in outputs.items():
            write_text(temporary / name, content)
        # Hash staged bytes before replacing any public output.
        digests = {name: file_digest(temporary / name) for name in outputs}
        if input_digests(run, stage) != inputs or runtime_identity() != runtime:
            raise StaleRunError("Inputs/runtime changed during publication; rerun locally.")
        for name in outputs:
            os.replace(temporary / name, run / name)
        state = read_state(run)
        current = state["stages"].get(stage, {})
        if current.get("generation") != attempt["generation"]:
            raise StaleRunError("Stage identity changed during publication.")
        current.update(status="complete", runtime=runtime, inputs=inputs, outputs=digests,
                       completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if stage == "score":
            current["weigh_generation"] = state["stages"]["weigh"]["generation"]
        write_json(run / STATE_NAME, state)  # Commit point, after the complete output group.
        diagnostic = run / "diagnostic.json"
        if diagnostic.exists():
            archive_outputs(run, ("diagnostic.json",), "Resolved by %s" % stage, state)
    finally:
        shutil.rmtree(temporary)


def verify_run(run: Path) -> Dict[str, Any]:
    state = read_state(run)
    issues = []
    stages = {}
    for stage in ("weigh", "score"):
        try:
            entry = check_stage(run, stage, state)
            stages[stage] = {"status": "current", "generation": entry["generation"]}
        except StaleRunError as exc:
            stages[stage] = {"status": "stale_or_incomplete", "reason": str(exc)}
            issues.append(str(exc))
    if read_state(run) != state:
        reason = "Run state changed during verification; retry after the writer finishes."
        issues.append(reason)
        stages = {stage: {"status": "stale_or_incomplete", "reason": reason}
                  for stage in ("weigh", "score")}
    return {
        "schema_version": SCHEMA_VERSION, "current": not issues, "stages": stages,
        "issues": issues,
        "scope": "Saved input/output byte identity and declared evidence links; no provider, browser or human acceptance.",
    }
