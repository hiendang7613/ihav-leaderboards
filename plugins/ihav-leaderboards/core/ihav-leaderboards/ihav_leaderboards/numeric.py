"""Finite numeric conversions and bounded score arithmetic.

JSON integers can exceed the float range. Keep that conversion at one boundary,
and never return an infinity or silently turn a positive source weight into zero.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


def finite_number(value: Any) -> Optional[float]:
    """Return a finite float for a real JSON number, otherwise None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_range(value: float, low: float, high: float) -> float:
    """Map a finite non-flat range to 0..100 without overflowing differences."""
    if value == low:
        return 0.0
    if value == high:
        return 100.0
    span = high - low
    if math.isfinite(span):
        fraction = (value - low) / span
    else:
        # An overflowing finite range necessarily spans opposite signs. Scale
        # before subtraction so both differences remain within -2..2.
        scale = max(abs(low), abs(high))
        fraction = (value / scale - low / scale) / (high / scale - low / scale)
    return min(100.0, max(0.0, 100.0 * fraction))


def positive_fractions(masses: Dict[str, float]) -> Dict[str, float]:
    """Normalize positive finite masses while avoiding an overflowing total."""
    if not masses:
        return {}
    largest = max(masses.values())
    scaled = {slug: mass / largest for slug, mass in masses.items()}
    total = math.fsum(scaled.values())
    fractions = {slug: mass / total for slug, mass in scaled.items()}
    for slug, fraction in fractions.items():
        if not math.isfinite(fraction) or fraction <= 0:
            raise ValueError("Weight for board %s is not representable with this mass range." % slug)
    return fractions
