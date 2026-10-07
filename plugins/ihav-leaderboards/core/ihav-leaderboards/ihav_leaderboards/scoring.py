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

from .numeric import finite_number, normalized_range, positive_fractions

MIN_SCORES = 3

WEIGHT_METADATA = (
    "domain", "url", "final_url", "monthly_visits", "monthly_visits_text", "visit_kind",
    "visit_period", "visit_analyzed_at", "visit_source", "visit_source_details", "visit_range",
    "visit_confidence", "visit_rank", "visit_error", "visit_contract_version", "split", "weight_basis",
)
EXTRACTION_METADATA = (
    "url", "final_url", "fetched_at", "method", "snapshot", "snapshot_sha256", "locator",
    "complete", "pagination_bound", "chatbot_evidence", "quality_column", "quality_reason", "direction",
    "score_kind",
)


class NoScoreError(Exception):
    """No leaderboard could be scored, so no final score exists."""

    def __init__(self, message: str, boards: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.boards = boards or []


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a nonempty string." % label)
    return value


def alias_map(matches: Dict[str, Any]) -> Tuple[Dict[Tuple[str, str], str], Dict[str, str]]:
    """Map (board slug, row name) to a canonical candidate id; also id -> display name."""
    aliases: Dict[Tuple[str, str], str] = {}
    names: Dict[str, str] = {}
    for candidate in matches.get("candidates", []):
        cid = _identity(candidate["id"], "Candidate id")
        if cid in names:
            raise ValueError("Duplicate candidate id %s." % cid)
        names[cid] = candidate.get("name", cid)
        for alias in candidate.get("aliases", []):
            key = (_identity(alias["board"], "Alias board"), _identity(alias["name"], "Alias name"))
            owner = aliases.get(key)
            if owner is not None and owner != cid:
                raise ValueError("Alias %r belongs to both %s and %s." % (key, owner, cid))
            aliases[key] = cid
    return aliases, names


def score_board(board: Dict[str, Any], aliases: Dict[Tuple[str, str], str]) -> Dict[str, Any]:
    """Return status, reason, normalized scores and diagnostics for one board."""
    slug = _identity(board["slug"], "Board slug")
    out: Dict[str, Any] = {
        "slug": slug, "scores": {}, "duplicates": [], "duplicate_conflicts": [],
        "unmatched": [], "unusable": [], "quality_values": {}, "score_evidence": {},
    }
    out.update({key: board[key] for key in EXTRACTION_METADATA if key in board})

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

    grouped: Dict[str, List[Tuple[int, Dict[str, Any], float]]] = {}
    for index, row in enumerate(board.get("rows", [])):
        name = row.get("name")
        cid = aliases.get((slug, name))
        if cid is None:
            out["unmatched"].append(name)
            continue
        q = finite_number(row.get("quality"))
        if q is None or row.get("verified") is not True:
            out["unusable"].append(name)
            continue
        grouped.setdefault(cid, []).append((index, row, q))

    values: Dict[str, float] = {}
    for cid, rows in grouped.items():
        preferred = [item for item in rows if item[1].get("preferred") is True]
        distinct = {item[2] for item in rows}
        if len(preferred) > 1 or (len(distinct) > 1 and len(preferred) != 1):
            out["duplicate_conflicts"].append({
                "candidate": cid, "rows": [item[1].get("name") for item in rows],
                "preferred_count": len(preferred),
                "reason": "Conflicting verified values require exactly one preferred row." if len(distinct) > 1
                else "Equal verified values allow at most one preferred row.",
            })
            continue
        selected = preferred[0] if len(preferred) == 1 else rows[0]
        for item in rows:
            if item is not selected:
                out["duplicates"].append(item[1].get("name"))
        index, row, raw = selected
        values[cid] = -raw if direction == "lower_better" else raw
        out["quality_values"][cid] = raw
        evidence = {key: row[key] for key in ("name", "quality", "verified", "cell", "row_id", "locator",
                                             "preferred", "evidence") if key in row}
        evidence["row_index"] = index
        out["score_evidence"][cid] = evidence

    if out["duplicate_conflicts"]:
        out.update(status="unverified", reason="Ambiguous duplicate selection: %s" %
                   "; ".join("%s: %s" % (item["candidate"], item["reason"]) for item in out["duplicate_conflicts"]))
        return out

    if len(values) < MIN_SCORES:
        out.update(status="dropped_too_few",
                   reason="%d distinct verified scores; at least %d are needed." % (len(values), MIN_SCORES))
        return out
    low, high = min(values.values()), max(values.values())
    if high == low:
        out.update(status="dropped_flat", reason="All scores are equal (max == min).")
        return out
    out["quality_min"] = min(out["quality_values"].values())
    out["quality_max"] = max(out["quality_values"].values())
    out["scores"] = {cid: normalized_range(q, low, high) for cid, q in values.items()}
    out.update(status="scored", reason="")
    return out


def merge(boards: List[Dict[str, Any]], weights: Dict[str, Any], matches: Dict[str, Any]) -> Dict[str, Any]:
    """Score every selected board and merge the scores into one leaderboard."""
    aliases, names = alias_map(matches)
    selected = {}
    weight_slugs = set()
    for entry in weights.get("boards", []):
        slug = _identity(entry["slug"], "Weight board slug")
        if slug in weight_slugs:
            raise ValueError("Duplicate weight board slug %s." % slug)
        weight_slugs.add(slug)
        if entry.get("selected") is True:
            mass = finite_number(entry.get("mass"))
            if mass is None or mass <= 0:
                raise ValueError("Mass for board %s must be finite positive." % slug)
            selected[slug] = dict(entry, mass=mass)
    by_slug = {}
    for board in boards:
        slug = _identity(board["slug"], "Extracted board slug")
        if slug in by_slug:
            raise ValueError("Duplicate extracted board slug %s." % slug)
        by_slug[slug] = board

    results = []
    for slug, entry in selected.items():
        board = by_slug.get(slug)
        if board is None:
            result = {"slug": slug, "status": "extract_failed", "reason": "No extracted table.", "scores": {},
                      "duplicates": [], "duplicate_conflicts": [], "unmatched": [], "unusable": [],
                      "quality_values": {}, "score_evidence": {}}
        else:
            result = score_board(board, aliases)
        result["mass"] = entry["mass"]
        result["weight"] = 0.0
        result.update({key: entry[key] for key in WEIGHT_METADATA if key in entry and key not in result})
        results.append(result)

    scored = [r for r in results if r["status"] == "scored"]
    if not scored:
        raise NoScoreError("No selected leaderboard could be scored; no final score exists.",
                           boards=[{key: value for key, value in result.items() if key != "scores"} for result in results])
    fractions = positive_fractions({result["slug"]: result["mass"] for result in scored})
    for r in results:
        r["weight"] = fractions.get(r["slug"], 0.0)

    match_metadata = {candidate["id"]: candidate for candidate in matches.get("candidates", [])}
    candidate_ids = sorted(set(names) | {cid for r in scored for cid in r["scores"]})
    candidates = []
    for cid in candidate_ids:
        contributions = {r["slug"]: (r["weight"], r["scores"][cid]) for r in scored if cid in r["scores"]}
        present = math.fsum(w for w, _ in contributions.values())
        # Normalize each candidate's weights before multiplying by scores. This
        # preserves a usable score even on a very small but positive board weight.
        final = math.fsum((w / present) * score for w, score in contributions.values()) if present > 0 else None
        if final is not None:
            final = min(100.0, max(0.0, final))
        decision = match_metadata.get(cid) or {}
        candidate = {
            "id": cid,
            "name": names.get(cid, cid),
            "final": final,
            "confidence": min(1.0, present),
            "scores": {slug: s for slug, (_, s) in contributions.items()},
            "match_method": decision.get("method"),
            "match_evidence": decision.get("evidence"),
            "match_confidence": decision.get("confidence"),
            "aliases": decision.get("aliases", []),
        }
        candidate.update({key: decision[key] for key in ("vendor", "product_type", "model", "version", "configuration")
                          if key in decision})
        candidates.append(candidate)

    ranked = sorted((c for c in candidates if c["final"] is not None),
                    key=lambda c: (-c["final"], -c["confidence"], c["name"]))
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    unranked = sorted((c for c in candidates if c["final"] is None), key=lambda c: c["name"])
    for candidate in unranked:
        candidate["rank"] = None

    return {
        "boards": [{key: value for key, value in r.items() if key != "scores"}
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
