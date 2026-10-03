"""S5 to S6a: merge extracted leaderboards into one quality score.

norm_L(c)     = 100 * (q_c - min_L) / (max_L - min_L)
w_L           = mass_L / sum(mass over scored boards)
final(c)      = sum(w_L * norm_L(c) over E(c)) / sum(w_L over E(c))
confidence(c) = sum(w_L over E(c))

E(c) holds the scored boards on which candidate c has a finite, verified quality
value. Presence without a usable value never counts (design S6, review F2).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

MIN_SCORES = 3


class NoScoreError(Exception):
    """No leaderboard could be scored, so no final score exists."""


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def alias_map(matches: Dict[str, Any]) -> Tuple[Dict[Tuple[str, str], str], Dict[str, str]]:
    """Map (board slug, row name) to a canonical candidate id; also id -> display name."""
    aliases: Dict[Tuple[str, str], str] = {}
    names: Dict[str, str] = {}
    for candidate in matches.get("candidates", []):
        cid = candidate["id"]
        names[cid] = candidate.get("name", cid)
        for alias in candidate.get("aliases", []):
            aliases[(alias["board"], alias["name"])] = cid
    return aliases, names


def score_board(board: Dict[str, Any], aliases: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    """Return status, reason, normalized scores and diagnostics for one board."""
    slug = board["slug"]
    out: Dict[str, Any] = {"slug": slug, "scores": {}, "duplicates": [], "unmatched": [], "unusable": []}

    preset = board.get("status")
    if preset in ("extract_failed", "unverified"):
        out.update(status=preset, reason=board.get("reason", preset))
        return out
    if board.get("score_kind") == "rank_only":
        out.update(status="rank_only_unscored",
                   reason="Board gives only an order; ranks are not mixed into the metric score.")
        return out
    direction = board.get("direction")
    if direction not in ("higher_better", "lower_better"):
        out.update(status="extract_failed", reason="Unknown quality direction %r." % direction)
        return out

    values: Dict[str, float] = {}
    for row in board.get("rows", []):
        name = row.get("name")
        cid = aliases.get((slug, name))
        if cid is None:
            out["unmatched"].append(name)
            continue
        q = _finite(row.get("quality"))
        if q is None or row.get("verified") is False:
            out["unusable"].append(name)
            continue
        if cid in values:
            out["duplicates"].append(name)
            continue
        values[cid] = -q if direction == "lower_better" else q

    if len(values) < MIN_SCORES:
        out.update(status="dropped_too_few",
                   reason="%d distinct verified scores; at least %d are needed." % (len(values), MIN_SCORES))
        return out
    low, high = min(values.values()), max(values.values())
    if high == low:
        out.update(status="dropped_flat", reason="All scores are equal (max == min).")
        return out
    out["scores"] = {cid: 100.0 * (q - low) / (high - low) for cid, q in values.items()}
    out.update(status="scored", reason="")
    return out


def merge(boards: List[Dict[str, Any]], weights: Dict[str, Any], matches: Dict[str, Any]) -> Dict[str, Any]:
    """Score every selected board and merge the scores into one leaderboard."""
    aliases, names = alias_map(matches)
    selected = {e["slug"]: e for e in weights.get("boards", []) if e.get("selected")}
    by_slug = {b["slug"]: b for b in boards}

    results = []
    for slug, entry in selected.items():
        board = by_slug.get(slug)
        if board is None:
            result = {"slug": slug, "status": "extract_failed", "reason": "No extracted table.", "scores": {},
                      "duplicates": [], "unmatched": [], "unusable": []}
        else:
            result = score_board(board, aliases)
        result["mass"] = entry["mass"]
        results.append(result)

    scored = [r for r in results if r["status"] == "scored" and r["mass"] > 0]
    total = sum(r["mass"] for r in scored)
    if not scored or total <= 0:
        raise NoScoreError("No selected leaderboard could be scored; no final score exists.")
    for r in results:
        r["weight"] = r["mass"] / total if r in scored else 0.0

    candidate_ids = sorted(set(names) | {cid for r in scored for cid in r["scores"]})
    candidates = []
    for cid in candidate_ids:
        contributions = {r["slug"]: (r["weight"], r["scores"][cid]) for r in scored if cid in r["scores"]}
        present = sum(w for w, _ in contributions.values())
        final = sum(w * s for w, s in contributions.values()) / present if present > 0 else None
        candidates.append({
            "id": cid,
            "name": names.get(cid, cid),
            "final": final,
            "confidence": present,
            "scores": {slug: s for slug, (_, s) in contributions.items()},
        })

    ranked = sorted((c for c in candidates if c["final"] is not None),
                    key=lambda c: (-c["final"], -c["confidence"], c["name"]))
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    unranked = sorted((c for c in candidates if c["final"] is None), key=lambda c: c["name"])
    for candidate in unranked:
        candidate["rank"] = None

    return {
        "boards": [{k: r[k] for k in ("slug", "status", "reason", "mass", "weight", "duplicates", "unmatched", "unusable")}
                   for r in sorted(results, key=lambda r: (-r["weight"], r["slug"]))],
        "candidates": ranked + unranked,
        "counts": {
            "selected": len(results),
            "scored": len(scored),
            "candidates_ranked": len(ranked),
            "candidates_unranked": len(unranked),
        },
        "notes": [
            "confidence = share of scored source weight with a usable score for this candidate; "
            "it is not statistical certainty, extraction accuracy or match confidence.",
            "Weights are allocated domain popularity, not page visits.",
        ],
    }
