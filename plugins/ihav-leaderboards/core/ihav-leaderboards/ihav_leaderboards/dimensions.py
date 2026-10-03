"""S6b: pick one comparable value per candidate and dimension, then build Pareto charts.

Observations are first filtered to the dimension's declared comparable context, so an
out-of-context value can never hide a comparable one. Precedence inside the context:
leaderboard columns (higher board weight first), then official pages, then the newer
date, then the observation id.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .pareto import frontier

SOURCE_RANK = {"leaderboard": 1, "official": 2}
CONFLICT_RATIO = 0.20


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


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
    return abs(x - y) / scale > CONFLICT_RATIO


def choose(registry: List[Dict[str, Any]], observations: List[Dict[str, Any]],
           board_weights: Dict[str, float]) -> Dict[str, Any]:
    """Return chosen values per candidate and key, plus conflicts and omissions."""
    chosen: Dict[str, Dict[str, Any]] = {}
    conflict_list = []
    out_of_context = 0
    for entry in registry:
        key, context, kind = entry["key"], entry.get("context"), entry.get("type", "number")
        per_candidate: Dict[str, List[Dict[str, Any]]] = {}
        for obs in observations:
            if obs.get("key") != key:
                continue
            if obs.get("context") != context:
                out_of_context += 1
                continue
            if kind == "number" and _number(obs.get("value")) is None:
                continue
            per_candidate.setdefault(obs["candidate"], []).append(obs)
        for cid, items in per_candidate.items():
            # Stable sorts, least significant key first: id, newer date, then source.
            items.sort(key=lambda o: str(o.get("id")))
            items.sort(key=lambda o: str(o.get("date") or ""), reverse=True)
            items.sort(key=lambda o: (SOURCE_RANK.get(o.get("source_type"), 9),
                                      -board_weights.get(o.get("board") or "", 0.0)))
            best = items[0]
            chosen.setdefault(cid, {})[key] = {
                "value": best["value"], "observation": best.get("id"),
                "source_type": best.get("source_type"), "url": best.get("url"), "date": best.get("date"),
            }
            for other in items[1:]:
                if conflicts(kind, best["value"], other["value"]):
                    conflict_list.append({"candidate": cid, "key": key,
                                          "chosen": best.get("id"), "other": other.get("id")})
    return {"values": chosen, "conflicts": conflict_list, "out_of_context": out_of_context}


def pareto_charts(registry: List[Dict[str, Any]], values: Dict[str, Dict[str, Any]],
                  candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One frontier per numeric dimension with a direction."""
    charts = {}
    for entry in registry:
        if entry.get("type", "number") != "number" or entry.get("direction") not in ("lower_better", "higher_better"):
            continue
        key = entry["key"]
        points, omitted = [], 0
        for c in candidates:
            x = (values.get(c["id"]) or {}).get(key, {}).get("value")
            if c.get("final") is None or _number(x) is None:
                omitted += 1
                continue
            points.append({"id": c["id"], "x": float(x), "y": c["final"]})
        charts[key] = {
            "unit": entry.get("unit"),
            "context": entry.get("context"),
            "direction": entry["direction"],
            "frontier": frontier(points, entry["direction"]),
            "plotted": len(points),
            "omitted": omitted,
        }
    return charts
