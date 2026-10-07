"""Pareto frontier for quality versus one extra dimension (design S6b)."""

from __future__ import annotations

from typing import Any, Dict, List

from .numeric import finite_number

DIRECTIONS = {"lower_better", "higher_better"}


def _usable(value: Any) -> bool:
    return finite_number(value) is not None


def frontier(points: List[Dict[str, Any]], x_direction: str) -> List[str]:
    """Return the ids of non-dominated points, in input order.

    Each point has ``id``, ``x`` (the dimension) and ``y`` (quality, higher is better).
    A point is dominated when another is at least as good on both axes and strictly
    better on one. Equal points are both kept. Null and nonfinite values are excluded.
    """
    if x_direction not in DIRECTIONS:
        raise ValueError("x_direction must be lower_better or higher_better")
    sign = -1.0 if x_direction == "lower_better" else 1.0
    usable = [p for p in points if _usable(p.get("x")) and _usable(p.get("y"))]
    keep = []
    for p in usable:
        px, py = sign * p["x"], p["y"]
        dominated = False
        for q in usable:
            if q is p:
                continue
            qx, qy = sign * q["x"], q["y"]
            if qx >= px and qy >= py and (qx > px or qy > py):
                dominated = True
                break
        if not dominated:
            keep.append(p["id"])
    return keep
