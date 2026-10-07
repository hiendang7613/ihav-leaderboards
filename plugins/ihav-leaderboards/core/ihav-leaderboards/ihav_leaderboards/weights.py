"""S3: turn ihav-web-visit-counter results into leaderboard weights.

Rules (design S3, admin O1/O2):
- Visits are per host (the visit counter's ``domain``: scheme, path and a leading
  ``www`` removed; subdomains kept). A domain's visits are split equally across
  its live leaderboards ("allocated domain popularity", not page visits).
- A domain without a finite positive visit count gets one floor weight before the
  split: the smallest finite positive domain visit count in the set. The floor is a
  policy weight; the raw ``monthly_visits`` stays ``None``.
- With no finite positive visit count at all there is no weight. The caller gets a
  ``NoWeightError`` and must not fall back to equal weights.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .numeric import finite_number

TOP_N = 32


class NoWeightError(Exception):
    """No finite positive visit count exists, so visit weighting is unavailable."""


_SUFFIX = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_TEXT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMBT]?)\s*$", re.I)


def parse_visits_text(text: Any) -> Optional[float]:
    """Parse a rounded provider label such as "631.0M" or "12K"; anything else is None."""
    if not isinstance(text, str):
        return None
    match = _TEXT.match(text.replace(",", ""))
    if not match:
        return None
    value = finite_number(float(match.group(1)))
    return finite_number(value * _SUFFIX[match.group(2).upper()]) if value is not None else None


def _positive_visits(result: Optional[Dict[str, Any]]) -> Optional[float]:
    """Visits from an ``estimate`` result: the number, else its rounded text label."""
    if not result or result.get("kind") != "estimate":
        return None
    value = result.get("monthly_visits")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = parse_visits_text(result.get("monthly_visits_text"))
    value = finite_number(value)
    if value is None or value <= 0:
        return None
    return float(value)


def allocate(boards: List[Dict[str, Any]], visits: Dict[str, Dict[str, Any]], top_n: int = TOP_N) -> Dict[str, Any]:
    """Return the weights document for live boards.

    ``boards``: S2 entries with ``slug``, ``domain`` and ``status``.
    ``visits``: visit-counter JSON results keyed by domain; a missing key means no data.
    """
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer.")
    slugs = set()
    for board in boards:
        slug = board["slug"]
        if slug in slugs:
            raise ValueError("Duplicate board slug %s." % slug)
        slugs.add(slug)
    live = [b for b in boards if b.get("status") == "live"]
    if not live:
        raise NoWeightError("No live leaderboard to weight.")

    by_domain: Dict[str, List[Dict[str, Any]]] = {}
    for board in live:
        by_domain.setdefault(board["domain"], []).append(board)

    known = {d: _positive_visits(visits.get(d)) for d in by_domain}
    positives = [v for v in known.values() if v is not None]
    if not positives:
        raise NoWeightError(
            "No live leaderboard domain has a finite positive visit estimate; "
            "visit-weighted aggregation is unavailable."
        )
    floor = min(positives)

    entries = []
    for domain, domain_boards in by_domain.items():
        result = visits.get(domain) or {}
        raw = known[domain]
        domain_mass = raw if raw is not None else floor
        split = len(domain_boards)
        allocated = domain_mass / split
        if allocated <= 0:
            raise ValueError("Allocated mass for domain %s is not representable after its split." % domain)
        source = result.get("source") or {}
        if not isinstance(source, dict):
            raise ValueError("Visit source for domain %s must be an object." % domain)
        for board in domain_boards:
            basis = "domain_split(%d)" % split if raw is not None else "floor+domain_split(%d)" % split
            entries.append({
                "slug": board["slug"],
                "domain": domain,
                "monthly_visits": finite_number(result.get("monthly_visits")) if raw is not None else None,
                "monthly_visits_text": result.get("monthly_visits_text"),
                "visit_kind": result.get("kind"),
                "visit_period": result.get("period"),
                "visit_analyzed_at": result.get("analyzed_at"),
                "visit_source": source.get("name"),
                "visit_source_details": source,
                "visit_range": result.get("range"),
                "visit_confidence": result.get("confidence"),
                "visit_rank": result.get("rank"),
                "visit_error": result.get("error"),
                "visit_contract_version": result.get("contract_version"),
                "split": split,
                "mass": allocated,
                "weight_basis": basis,
            })
            entries[-1].update({key: board[key] for key in ("url", "final_url") if key in board})

    entries.sort(key=lambda e: (-e["mass"], e["slug"]))
    for index, entry in enumerate(entries):
        entry["selected"] = index < top_n

    floor_domains = sorted(d for d, v in known.items() if v is None)
    return {
        "floor": floor,
        "floor_domains": floor_domains,
        "top_n": top_n,
        "boards": entries,
        "note": "Weights are allocated domain popularity, not page visits.",
    }
