"""S6b: pick one comparable value per candidate and dimension, then build Pareto charts.

Observations are first filtered to the dimension's declared comparable context, so an
out-of-context value can never hide a comparable one. Precedence inside the context:
leaderboard columns (higher board weight first), then official pages, then the newer
date, then the observation id.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .numeric import finite_number
from .pareto import frontier

SOURCE_RANK = {"leaderboard": 1, "official": 2}
CONFLICT_RATIO = 0.20


def _number(value: Any) -> Optional[float]:
    return finite_number(value)


def _usable(kind: str, value: Any) -> bool:
    if kind == "number":
        return finite_number(value) is not None
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "category":
        return isinstance(value, str) and bool(value.strip())
    raise ValueError("Unknown dimension type %r." % kind)


def conflicts(kind: str, a: Any, b: Any) -> bool:
    """Typed conflict rule: bool/category differ on any change; numbers past 20%."""
    if kind != "number":
        return a != b
    x, y = _number(a), _number(b)
    if x is None or y is None:
        return False
    scale = max(abs(x), abs(y))
    if scale == 0:
        return False
    # Divide before subtracting so opposite-sign finite extremes cannot overflow.
    return abs(x / scale - y / scale) > CONFLICT_RATIO


def choose(registry: List[Dict[str, Any]], observations: List[Dict[str, Any]],
           board_weights: Dict[str, float]) -> Dict[str, Any]:
    """Return chosen values per candidate and key, plus conflicts and omissions."""
    chosen: Dict[str, Dict[str, Any]] = {}
    conflict_list = []
    out_of_context = 0
    unsupported_sources = 0
    omissions = []
    keys = set()
    for entry in registry:
        key, context, kind = entry["key"], entry.get("context"), entry.get("type", "number")
        if key in keys:
            raise ValueError("Duplicate dimension key %s." % key)
        keys.add(key)
        if kind not in ("number", "bool", "category"):
            raise ValueError("Unknown dimension type %r." % kind)
        per_candidate: Dict[str, List[Dict[str, Any]]] = {}
        for obs in observations:
            if obs.get("key") != key:
                continue
            if obs.get("context") != context:
                out_of_context += 1
                continue
            if obs.get("source_type") not in SOURCE_RANK:
                unsupported_sources += 1
                omissions.append({"candidate": obs.get("candidate"), "key": key, "observation": obs.get("id"),
                                  "reason": "Unsupported source_type; only leaderboard and official observations compete."})
                continue
            if not _usable(kind, obs.get("value")):
                omissions.append({"candidate": obs.get("candidate"), "key": key, "observation": obs.get("id"),
                                  "reason": "Missing or unusable %s value." % kind})
                continue
            per_candidate.setdefault(obs["candidate"], []).append(obs)
        for cid, items in per_candidate.items():
            # Stable sorts, least significant key first: id, newer date, then source.
            items.sort(key=lambda o: str(o.get("id")))
            items.sort(key=lambda o: str(o.get("date") or ""), reverse=True)
            items.sort(key=lambda o: (SOURCE_RANK[o["source_type"]],
                                      -(finite_number(board_weights.get(o.get("board") or "", 0.0)) or 0.0)
                                      if o["source_type"] == "leaderboard" else 0.0))
            best = items[0]
            reason = (
                "Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID."
                if best["source_type"] == "leaderboard" else
                "Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID."
            )
            chosen.setdefault(cid, {})[key] = {
                "value": best["value"], "observation": best.get("id"),
                "source_type": best.get("source_type"), "url": best.get("url"), "date": best.get("date"),
                "context": context, "board": best.get("board"), "method": best.get("method"),
                "snapshot": best.get("snapshot"), "snapshot_sha256": best.get("snapshot_sha256"),
                "cell": best.get("cell") or best.get("locator"),
                "reason": reason, "source_reason": best.get("reason", best.get("selection_reason")),
            }
            for other in items[1:]:
                if conflicts(kind, best["value"], other["value"]):
                    conflict_list.append({"candidate": cid, "key": key,
                                          "chosen": best.get("id"), "other": other.get("id"),
                                          "chosen_value": best["value"], "other_value": other["value"],
                                          "context": context, "type": kind})
    return {"values": chosen, "conflicts": conflict_list, "out_of_context": out_of_context,
            "unsupported_sources": unsupported_sources, "omissions": omissions}


def pareto_charts(registry: List[Dict[str, Any]], values: Dict[str, Dict[str, Any]],
                  candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One frontier per numeric dimension with a direction."""
    charts = {}
    for entry in registry:
        if entry.get("type", "number") != "number" or entry.get("direction") not in ("lower_better", "higher_better"):
            continue
        key = entry["key"]
        points, omitted = [], 0
        reasons = {"unusable_quality": 0, "unusable_dimension": 0}
        for c in candidates:
            x = (values.get(c["id"]) or {}).get(key, {}).get("value")
            quality, dimension = finite_number(c.get("final")), finite_number(x)
            if quality is None or dimension is None:
                omitted += 1
                reasons["unusable_quality" if quality is None else "unusable_dimension"] += 1
                continue
            points.append({"id": c["id"], "x": dimension, "y": quality})
        charts[key] = {
            "unit": entry.get("unit"),
            "context": entry.get("context"),
            "direction": entry["direction"],
            "frontier": frontier(points, entry["direction"]),
            "plotted": len(points),
            "omitted": omitted,
            "omitted_reasons": reasons,
        }
    return charts
