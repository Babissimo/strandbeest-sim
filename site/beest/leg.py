"""Jansen's leg in hole-to-hole mm: the scale, the bounds on each length and the down tolerance."""
from __future__ import annotations

from .geometry import HOLY, LENGTH_NAMES

MM_PER_UNIT = 1.2
DOWN_TOLERANCE_MM = 1.0
# a and l place the fixed pivot G from the crank axle; every other length is a stick.
LENGTH_BOUNDS: dict[str, tuple[float, float]] = {
    name: (-30.0, 30.0) if name == "l" else (10.0, 104.0) for name in LENGTH_NAMES}


def jansen_lengths() -> list[float]:
    """Jansen's holy numbers as hole-to-hole mm, a to m."""
    return [HOLY[name] * MM_PER_UNIT for name in LENGTH_NAMES]
