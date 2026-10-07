"""Validate agent-authored run shapes and declared extraction evidence."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

from .numeric import finite_number

from .runs import RunInputError, file_digest, object_file, relative_file

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunInputError("%s must be a nonempty string." % label)
    return value


def records(value: Any, label: str) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RunInputError("%s must be a list of objects." % label)
    return value


def unique(entries: List[Dict[str, Any]], key: str, label: str, slug: bool = False) -> None:
    seen = set()
    for entry in entries:
        value = text(entry.get(key), "%s.%s" % (label, key))
        if slug and not _SLUG.fullmatch(value):
            raise RunInputError("%s has an invalid slug: %s" % (label, value))
        if value in seen:
            raise RunInputError("Duplicate %s %s: %s" % (label, key, value))
        seen.add(value)


def request_file(run: Path) -> Dict[str, Any]:
    request = object_file(run / "request.json")
    version = request.get("schema_version")
    if isinstance(version, bool) or version not in (1, 2):
        raise RunInputError("request.json needs supported schema_version 1 or 2.")
    text(request.get("query"), "request.query")
    if not isinstance(request.get("synthetic", False), bool):
        raise RunInputError("request.synthetic must be a boolean.")
    dependencies = request.get("dependencies", {})
    if not isinstance(dependencies, dict) or any(not isinstance(item, dict) for item in dependencies.values()):
        raise RunInputError("request.dependencies must map names to metadata objects.")
    return request


def canonical_host(host: str) -> str:
    """Use the visit counter's host identity: www removed, subdomains retained."""
    host = text(host, "host").rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise RunInputError("Invalid host: %s." % host) from exc
    if len(host) > 253 or "." not in host or any(not _HOST_LABEL.fullmatch(part) for part in host.split(".")):
        raise RunInputError("Invalid host: %s." % host)
    return host


def boards_file(run: Path) -> List[Dict[str, Any]]:
    document = object_file(run / "boards.json")
    boards = records(document.get("boards"), "boards")
    unique(boards, "slug", "boards", slug=True)
    checked = []
    for original in boards:
        board = dict(original)
        domain = text(board.get("domain"), "boards.domain")
        if board.get("status") not in ("live", "blocked", "rate_limited", "transient", "dead"):
            raise RunInputError("Unknown liveness status for %s." % board["slug"])
        if board["status"] == "live":
            domain = canonical_host(domain)
            url = text(board.get("final_url") or board.get("url"), "live board source URL")
            try:
                parsed = urlsplit(url)
                host = parsed.hostname
                parsed.port  # Reject malformed ports before accepting source identity.
                if (parsed.scheme not in ("http", "https") or not host or parsed.username is not None
                        or parsed.password is not None or any(char.isspace() for char in url)):
                    raise ValueError("needs an HTTP(S) URL without credentials or whitespace")
            except ValueError as exc:
                raise RunInputError("Invalid collected source URL for %s: %s." % (board["slug"], exc)) from exc
            if canonical_host(host) != domain:
                raise RunInputError("Collected source URL host differs from domain for %s." % board["slug"])
            board["domain"] = domain
        checked.append(board)
    return checked

def matches_file(run: Path) -> Dict[str, Any]:
    document = object_file(run / "matches.json")
    candidates = records(document.get("candidates"), "matches.candidates")
    unique(candidates, "id", "candidates")
    for candidate in candidates:
        if "name" in candidate:
            text(candidate["name"], "candidate.name")
        for alias in records(candidate.get("aliases", []), "candidate.aliases"):
            text(alias.get("board"), "alias.board")
            text(alias.get("name"), "alias.name")
    return document


def dimensions_file(run: Path, candidate_ids: Any, board_slugs: Any,
                    source_boards: Any = None) -> Dict[str, Any]:
    document = object_file(run / "dimensions.json")
    registry = records(document.get("registry"), "dimensions.registry")
    observations = records(document.get("observations"), "dimensions.observations")
    unique(registry, "key", "dimension")
    unique(observations, "id", "observation")
    entries = {entry["key"]: entry for entry in registry}
    for entry in registry:
        if entry.get("type", "number") not in ("number", "bool", "category"):
            raise RunInputError("Unknown dimension type for %s." % entry["key"])
        if entry.get("direction", "none") not in ("none", "higher_better", "lower_better"):
            raise RunInputError("Unknown dimension direction for %s." % entry["key"])
    checked = []
    for original in observations:
        observation = dict(original)
        if observation.get("candidate") not in candidate_ids:
            raise RunInputError("Observation candidate is absent from matches: %s." % observation["id"])
        if observation.get("key") not in entries:
            raise RunInputError("Observation key is absent from registry: %s." % observation["id"])
        if observation.get("source_type") not in ("leaderboard", "official"):
            raise RunInputError("Unknown observation source_type: %s." % observation["id"])
        if observation.get("source_type") == "leaderboard" and observation.get("board") not in board_slugs:
            raise RunInputError("Observation board is absent from boards: %s." % observation["id"])
        entry = entries[observation["key"]]
        kind, value = entry.get("type", "number"), observation.get("value")
        usable = (finite_number(value) is not None if kind == "number" else
                  isinstance(value, bool) if kind == "bool" else
                  isinstance(value, str) and bool(value.strip()))
        comparable = usable and observation.get("context") == entry.get("context")
        if comparable:
            if observation["source_type"] == "leaderboard":
                board = (source_boards or {}).get(observation["board"])
                if (not isinstance(board, dict) or board.get("status") in ("unverified", "extract_failed")
                        or board.get("complete") is not True or not board.get("snapshot")
                        or board.get("method") not in ("direct", "browser", "chatbot")):
                    raise RunInputError("Dimension has no validated board snapshot: %s." % observation["id"])
                if "snapshot" in observation and observation["snapshot"] != board["snapshot"]:
                    raise RunInputError("Dimension snapshot differs from referenced board: %s." % observation["id"])
                declared, board_digest = observation.get("snapshot_sha256"), board.get("snapshot_sha256")
                if ("snapshot_sha256" in observation and
                        (not isinstance(declared, str) or not isinstance(board_digest, str)
                         or declared.lower() != board_digest.lower())):
                    raise RunInputError("Dimension hash differs from referenced board: %s." % observation["id"])
                observation["snapshot"] = board["snapshot"]
                observation["snapshot_sha256"] = board.get("snapshot_sha256")
            text(observation.get("cell") or observation.get("locator"), "dimension cell/locator")
        if comparable or "snapshot" in observation:
            snapshot = relative_file(run, observation.get("snapshot"))
            digest = observation.get("snapshot_sha256")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or file_digest(snapshot) != digest.lower():
                raise RunInputError("Dimension snapshot hash mismatch: %s." % observation["id"])
        checked.append(observation)
    document["observations"] = checked
    return document


def extraction_files(run: Path) -> List[Dict[str, Any]]:
    boards = []
    for path in sorted((run / "leaderboards").glob("*.json")):
        board = object_file(path)
        slug = text(board.get("slug"), "extracted board.slug")
        if not _SLUG.fullmatch(slug) or slug != path.stem:
            raise RunInputError("Extracted board slug must match its filename: %s." % path.name)
        if "score_kind" in board and board["score_kind"] not in ("score", "rank_only"):
            raise RunInputError("Unknown extracted score_kind for %s; expected score or rank_only." % slug)
        rows = records(board.get("rows", []), "extracted rows")
        for row in rows:
            text(row.get("name"), "row.name")
            if "preferred" in row and not isinstance(row["preferred"], bool):
                raise RunInputError("row.preferred must be a boolean.")
        if board.get("status") in ("extract_failed", "unverified"):
            boards.append(board)
            continue
        issues = []
        if board.get("method") not in ("direct", "browser", "chatbot"):
            issues.append("Unknown or missing extraction method.")
        if board.get("complete") is not True:
            issues.append("Extraction completeness is not explicitly true.")
        snapshot = board.get("snapshot")
        declared_digest = board.get("snapshot_sha256")
        if not isinstance(snapshot, str) or not snapshot:
            issues.append("No saved source snapshot.")
        elif not isinstance(declared_digest, str) or not _SHA256.fullmatch(declared_digest):
            issues.append("No valid source snapshot SHA-256.")
        else:
            source = relative_file(run, snapshot)
            if not source.is_file():
                issues.append("Saved source snapshot is missing.")
            elif file_digest(source) != declared_digest.lower():
                issues.append("Saved source snapshot SHA-256 does not match.")
        checked = dict(board)
        if issues:
            checked.update(status="unverified", reason=" ".join(issues), evidence_issues=issues)
        else:
            checked_rows = []
            for row in rows:
                value = dict(row)
                if row.get("verified") is True and (not isinstance(row.get("cell"), str) or not row["cell"].strip()):
                    value["verified"] = False
                    value["verification_reason"] = "No saved cell reference."
                checked_rows.append(value)
            checked["rows"] = checked_rows
        boards.append(checked)
    unique(boards, "slug", "extracted boards", slug=True)
    return boards


def dependency_summary(request: Dict[str, Any], visits: Dict[str, Any]) -> Dict[str, Any]:
    """Export public version/hash metadata, never local install paths."""
    packages = {}
    for name, metadata in request.get("dependencies", {}).items():
        packages[name] = {key: metadata[key] for key in (
            "version", "bundle_version", "runtime_version", "contract_version", "source_tree_sha256", "manifest_sha256")
            if key in metadata}
    contracts = {domain: {"contract_version": value.get("contract_version"),
                          "compatibility": value.get("_contract_compatibility")}
                 for domain, value in visits.items()}
    return {"packages": packages, "visit_contracts": contracts}


def report_warnings(request: Dict[str, Any], dependencies: Dict[str, Any]) -> List[str]:
    warnings = []
    if request.get("synthetic"):
        warnings.append("Synthetic fixture data; this report is not a live leaderboard evaluation.")
    if not dependencies["packages"]:
        warnings.append("Dependency package versions were not recorded by the host.")
    legacy = sorted(domain for domain, item in dependencies["visit_contracts"].items()
                    if item["compatibility"] != "current")
    if legacy:
        warnings.append("Legacy saved visit contracts retained without migration: %s." % ", ".join(legacy))
    return warnings
