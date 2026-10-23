"""The settings route's fitness: ingredients, weights, normalisation and flips.

A score is the weighted mean of the chosen ingredients, each normalised one of three ways and
flipped (1 − normalised) where lower is better (decisions S3, Q5, Q15). A jammed leg scores 0.
"""
from __future__ import annotations

import functools
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .leg import Leg

# Each ingredient is read from the Leg attribute of the same name; True when higher is better.
INGREDIENTS: dict[str, bool] = {"distance": True, "stride": True, "step_height": True,
                                "time_down": True, "flatness": False}
DEFAULT_WEIGHTS: dict[str, float] = {"distance": 1.0, "step_height": 0.5}
# "jansen" divides by Jansen's value; "limits" maps fixed limits onto 0–1; "generation" maps each
# generation's own lowest and highest onto 0–1.
NORMALISATIONS = ("jansen", "limits", "generation")
# Written by scripts/survey_limits.py (decisions Q5).
LIMITS_FILE = Path(__file__).parent / "limits.json"


@functools.cache
def _surveyed_limits() -> dict[str, tuple[float, float]]:
    data = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
    return {name: (float(low), float(high)) for name, (low, high) in data["limits"].items()}


def fixed_limits() -> dict[str, tuple[float, float]]:
    """The surveyed limits of each ingredient, as a fresh dict."""
    return dict(_surveyed_limits())


def ingredient_values(leg: Leg) -> dict[str, float]:
    """The leg's raw value of each ingredient."""
    return {name: float(getattr(leg, name)) for name in INGREDIENTS}


@dataclass(frozen=True)
class FitnessSettings:
    """How the settings route scores a beest.

    An ingredient missing from `weights` weighs 0; missing from `flip`, it is flipped when lower
    is better; missing from `limits`, it uses the surveyed limits.
    """
    weights: dict[str, float] = field(
        default_factory=lambda: {name: DEFAULT_WEIGHTS.get(name, 0.0) for name in INGREDIENTS})
    normalisation: str = "jansen"
    flip: dict[str, bool] = field(
        default_factory=lambda: {name: not higher for name, higher in INGREDIENTS.items()})
    limits: dict[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.normalisation not in NORMALISATIONS:
            raise ValueError(f"normalisation must be one of {', '.join(NORMALISATIONS)}, "
                             f"not {self.normalisation!r}")
        for setting in (self.weights, self.flip, self.limits):
            for name in setting:
                if name not in INGREDIENTS:
                    raise ValueError(f"{name!r} is not an ingredient")
        for name, weight in self.weights.items():
            if not 0 <= weight < math.inf:
                raise ValueError(f"the weight of {name} must be 0 or more, not {weight}; "
                                 f"flip an ingredient to make lower better")
        for name, flipped in self.flip.items():
            if not isinstance(flipped, bool):
                raise ValueError(f"the flip of {name} must be True or False, not {flipped!r}")
        for name, pair in self.limits.items():
            if len(pair) != 2 or not all(math.isfinite(x) for x in pair):
                raise ValueError(f"the limits of {name} must be two ordinary numbers, not {pair}")

    def weight(self, name: str) -> float:
        return self.weights.get(name, 0.0)

    def flipped(self, name: str) -> bool:
        return self.flip.get(name, not INGREDIENTS[name])

    def limit(self, name: str) -> tuple[float, float]:
        low, high = self.limits[name] if name in self.limits else _surveyed_limits()[name]
        return min(low, high), max(low, high)


def _between(value: float, low: float, high: float) -> float:
    """Where value lies from low (0) to high (1); when they are equal, 0, 0.5 or 1."""
    if high > low:
        return (value - low) / (high - low)
    return 0.0 if value < low else 1.0 if value > high else 0.5


def _scale(name: str, settings: FitnessSettings, jansen: Leg,
           working: list[Leg]) -> Callable[[float], float]:
    if settings.normalisation == "jansen":
        reference = getattr(jansen, name)
        return lambda value: value / reference if reference else 0.0
    if settings.normalisation == "limits":
        low, high = settings.limit(name)
        return lambda value: min(max(_between(value, low, high), 0.0), 1.0)
    values = [getattr(leg, name) for leg in working]
    low, high = (min(values), max(values)) if values else (0.0, 0.0)
    return lambda value: _between(value, low, high)


def normalise(legs: list[Leg], settings: FitnessSettings, jansen: Leg) -> None:
    """Fill each leg's `normalised` with every ingredient on the settings' scale, before flipping.

    `jansen` is the reference leg for "jansen" normalisation; an ingredient Jansen scores 0 on
    normalises to 0. Under "generation" normalisation only working legs set the lowest and
    highest. A jammed leg gets 0.0 for every ingredient.
    """
    working = [leg for leg in legs if not leg.jams]
    for name in INGREDIENTS:
        scale = _scale(name, settings, jansen, working)
        for leg in legs:
            leg.normalised[name] = 0.0 if leg.jams else scale(getattr(leg, name))


def settings_fitness(settings: FitnessSettings) -> Callable[[Leg], float]:
    """The fitness function the settings describe, for legs already normalised.

    It is the weighted mean of the normalised ingredients, flipped where set; 0 for a jammed leg
    or when every weight is 0.
    """
    weights = {name: settings.weight(name) for name in INGREDIENTS if settings.weight(name)}
    flips = {name: settings.flipped(name) for name in weights}
    total = sum(weights.values())

    def fitness(leg: Leg) -> float:
        if leg.jams or not total:
            return 0.0
        score = 0.0
        for name, weight in weights.items():
            value = leg.normalised[name]
            score += weight * (1 - value if flips[name] else value)
        return score / total

    return fitness
