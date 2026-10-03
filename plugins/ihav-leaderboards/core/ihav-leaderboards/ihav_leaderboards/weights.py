"""S3: turn ihav-web-visit-counter results into leaderboard weights.

Rules (design S3, admin O1/O2):
- Visits are per registrable domain. A domain's visits are split equally across
  its live leaderboards ("allocated domain popularity", not page visits).
- A domain without a finite positive visit count gets one floor weight before the
  split: the smallest finite positive domain visit count in the set. The floor is a
  policy weight; the raw ``monthly_visits`` stays ``None``.
- With no finite positive visit count at all there is no weight. The caller gets a
  ``NoWeightError`` and must not fall back to equal weights.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

TOP_N = 32


class NoWeightError(Exception):
    """No finite positive visit count exists, so visit weighting is unavailable."""


def _positive_visits(result: Optional[Dict[str, Any]]) -> Optional[float]:
    if not result or result.get("kind") != "estimate":
        return None
    value = result.get("monthly_visits")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def allocate(boards: List[Dict[str, Any]], visits: Dict[str, Dict[str, Any]], top_n: int = TOP_N) -> Dict[str, Any]:
    """Return the weights document for live boards.

    ``boards``: S2 entries with ``slug``, ``domain`` and ``status``.
    ``visits``: visit-counter JSON results keyed by domain; a missing key means no data.
    """
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
        for board in domain_boards:
            basis = "domain_split(%d)" % split if raw is not None else "floor+domain_split(%d)" % split
            entries.append({
                "slug": board["slug"],
                "domain": domain,
                "monthly_visits": int(raw) if raw is not None else None,
                "visit_kind": result.get("kind"),
                "visit_period": result.get("period"),
                "visit_analyzed_at": result.get("analyzed_at"),
                "visit_source": (result.get("source") or {}).get("name"),
                "split": split,
                "mass": domain_mass / split,
                "weight_basis": basis,
            })

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
