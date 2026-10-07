"""Write ``leaderboard.md`` and ``leaderboard.csv`` from ``final.json``."""

from __future__ import annotations

import csv
import html
import io
import json
import unicodedata
from typing import Any, Dict, List


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return "%.*f" % (digits, value)
    return str(value)


def _dim(value: Any) -> str:
    """Dimension values keep their own precision, without trailing zeros."""
    if isinstance(value, float):
        return "%g" % value
    return _fmt(value)


def dimension_keys(final: Dict[str, Any]) -> List[str]:
    return [entry["key"] for entry in final.get("registry", [])]


def _csv_text(text: str) -> str:
    """Keep external text inert when a spreadsheet opens the CSV.

    CSV quoting does not stop formula interpretation. Whitespace and control
    characters can hide a formula prefix, so inspect the first visible character.
    Numeric values use a separate path and retain their numeric representation.
    """
    significant = next((char for char in text
                        if not char.isspace() and unicodedata.category(char) not in ("Cc", "Cf")), "")
    return "'" + text if significant in ("=", "+", "-", "@") else text


def _csv_dimension(value: Any) -> str:
    return _csv_text(value) if isinstance(value, str) else _dim(value)


def to_csv(final: Dict[str, Any]) -> str:
    keys = dimension_keys(final)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["rank", "candidate", "final_score", "confidence"] + [_csv_text(k) for k in keys] + ["synthetic"])
    synthetic = "true" if final.get("synthetic") is True else "false"
    for c in final["candidates"]:
        dims = final.get("dimensions", {}).get(c["id"], {})
        writer.writerow([_fmt(c["rank"]), _csv_text(c["name"]), _fmt(c["final"], 2), _fmt(c["confidence"], 4)]
                        + [_csv_dimension((dims.get(k) or {}).get("value")) for k in keys] + [synthetic])
    return buffer.getvalue()


def _cell(value: Any) -> str:
    text = _fmt(value)
    return html.escape(text).replace("|", "\\|").replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _table(lines: List[str], header: List[Any], rows: List[List[Any]]) -> None:
    lines.append("| " + " | ".join(_cell(value) for value in header) + " |")
    lines.append("|" + "---|" * len(header))
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)


def _period(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _fmt(value)


def to_markdown(final: Dict[str, Any]) -> str:
    keys = dimension_keys(final)
    lines = ["# %s" % _cell(final.get("query") or "Leaderboard"), ""]
    counts = final["counts"]
    lines.append("Scored %d of %d selected leaderboards. Ranked %d candidates."
                 % (counts["scored"], counts["selected"], counts["candidates_ranked"]))
    lines.append("")
    if final.get("synthetic") is True:
        lines += ["**Synthetic example: these values demonstrate the report; they are not live benchmark evidence.**", ""]
    if final.get("warnings"):
        lines += ["## Warnings", ""] + ["- " + _cell(warning) for warning in final["warnings"]] + [""]
    lines += ["Confidence is the share of scored source weight with a usable quality value, not statistical certainty or match confidence.", ""]
    header = ["#", "Candidate", "Score", "Confidence"] + keys
    rows = []
    for c in final["candidates"]:
        dims = final.get("dimensions", {}).get(c["id"], {})
        confidence = "" if c["confidence"] is None else "%d%%" % round(100 * c["confidence"])
        row = [_fmt(c["rank"]) or "-", c["name"], _fmt(c["final"]) or "-", confidence]
        row += [_dim((dims.get(k) or {}).get("value")) or "-" for k in keys]
        rows.append(row)
    _table(lines, header, rows)
    lines += ["", "## Sources", ""]
    rows = []
    for b in final["boards"]:
        rows.append([b["slug"], b["status"], "%.1f%%" % (100 * b.get("weight", 0)),
                     b.get("weight_basis") or "unrecorded", b.get("domain"), b.get("split"),
                     _period(b.get("visit_period")), b.get("visit_source"), b.get("reason")])
    _table(lines, ["Leaderboard", "Status", "Weight", "Weight basis", "Domain", "Domain split", "Visit period", "Visit source", "Note"], rows)
    if "collection" in final:
        lines += ["", "## Discovery collection", ""]
        _table(lines, ["Leaderboard", "URL", "Liveness", "Reason"],
               [[b.get("slug"), b.get("url") or b.get("final_url"), b.get("status"), b.get("reason")] for b in final["collection"]])
    if "unselected_boards" in final:
        lines += ["", "## Live boards outside the selected group", ""]
        _table(lines, ["Leaderboard", "Domain", "Weight basis", "Reason"],
               [[b.get("slug"), b.get("domain"), b.get("weight_basis"), b.get("reason") or "not selected for scoring"] for b in final["unselected_boards"]])
    if final.get("dimensions"):
        lines += ["", "## Dimension sources", ""]
        rows = []
        names = {c["id"]: c["name"] for c in final["candidates"]}
        for cid, values in final["dimensions"].items():
            for key, obs in values.items():
                rows.append([names.get(cid, cid), key, _dim(obs.get("value")), obs.get("context"),
                             obs.get("source_type"), obs.get("observation"), obs.get("url") or obs.get("final_url"), obs.get("date"),
                             obs.get("method"), obs.get("reason") or obs.get("selection_reason")])
        _table(lines, ["Candidate", "Dimension", "Value", "Context", "Source", "Observation", "URL", "Date", "Method", "Selection reason"], rows)
    conflicts = final.get("dimension_conflicts", [])
    if conflicts:
        lines += ["", "## Dimension conflicts", "",
                  "Comparable bool/category differences, or numeric differences above 20%, are reported as conflicts.", ""]
        _table(lines, ["Candidate", "Dimension", "Chosen observation", "Conflicting observation"],
               [[c.get("candidate"), c.get("key"), c.get("chosen"), c.get("other")] for c in conflicts])
    decisions = [c for c in final["candidates"]
                 if c.get("aliases") or c.get("match_evidence") or c.get("match_method")
                 or c.get("match_confidence") is not None]
    if decisions:
        lines += ["", "## Identity matching decisions", "",
                  "Match confidence records identity evidence and remains separate from the score's source coverage.", ""]
        _table(lines, ["Candidate", "Match confidence", "Method", "Evidence", "Aliases"],
               [[c["name"], c.get("match_confidence"), c.get("match_method"),
                 json.dumps(c.get("match_evidence"), ensure_ascii=False) if isinstance(c.get("match_evidence"), (dict, list)) else c.get("match_evidence"),
                 json.dumps(c.get("aliases", []), ensure_ascii=False)] for c in decisions])
    publication = final.get("publication", {})
    digests = publication.get("source_sha256", {})
    if digests:
        lines += ["", "## Source fingerprints", ""]
        _table(lines, ["Saved source", "SHA-256"], [[path, digest] for path, digest in sorted(digests.items())])
    lines += [""] + ["- " + _cell(note) for note in final.get("notes", [])]
    return "\n".join(lines) + "\n"
