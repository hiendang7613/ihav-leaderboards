"""Write ``leaderboard.md`` and ``leaderboard.csv`` from ``final.json``."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return "%.*f" % (digits, value)
    return str(value)


def dimension_keys(final: Dict[str, Any]) -> List[str]:
    return [entry["key"] for entry in final.get("registry", [])]


def to_csv(final: Dict[str, Any]) -> str:
    keys = dimension_keys(final)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["rank", "candidate", "final_score", "confidence"] + keys)
    for c in final["candidates"]:
        dims = final.get("dimensions", {}).get(c["id"], {})
        writer.writerow([_fmt(c["rank"]), c["name"], _fmt(c["final"], 2), _fmt(c["confidence"], 4)]
                        + [_fmt((dims.get(k) or {}).get("value"), 4) for k in keys])
    return buffer.getvalue()


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(final: Dict[str, Any]) -> str:
    keys = dimension_keys(final)
    lines = ["# %s" % _cell(final.get("query") or "Leaderboard"), ""]
    counts = final["counts"]
    lines.append("Scored %d of %d selected leaderboards. Ranked %d candidates."
                 % (counts["scored"], counts["selected"], counts["candidates_ranked"]))
    lines.append("")
    header = ["#", "Candidate", "Score", "Confidence"] + keys
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for c in final["candidates"]:
        dims = final.get("dimensions", {}).get(c["id"], {})
        confidence = "" if c["confidence"] is None else "%d%%" % round(100 * c["confidence"])
        row = [_fmt(c["rank"]) or "-", _cell(c["name"]), _fmt(c["final"]) or "-", confidence]
        row += [_fmt((dims.get(k) or {}).get("value"), 4) or "-" for k in keys]
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Sources", "", "| Leaderboard | Status | Weight | Note |", "|---|---|---|---|"]
    for b in final["boards"]:
        lines.append("| %s | %s | %.1f%% | %s |" % (_cell(b["slug"]), b["status"], 100 * b["weight"], _cell(b["reason"])))
    lines += [""] + ["- " + note for note in final.get("notes", [])]
    return "\n".join(lines) + "\n"
