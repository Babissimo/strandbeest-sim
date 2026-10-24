"""Survey random working legs for the fixed limits of the second normalisation (decisions Q5).

Each length is drawn uniformly within ±25% of Jansen's, on the standard layout, until 2,000 legs
turn fully; each ingredient's limits are its 5th and 95th percentiles over those legs, except that
an ingredient that is only ever 0 or 1 takes those as its limits. Distance's highest limit and
flatness's best end then move out past Jansen, so that beating him still scores more. Writes
site/beest/limits.json.

    uv run scripts/survey_limits.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))

from beest.fitness import INGREDIENTS, LIMITS_FILE, ingredient_values  # noqa: E402
from beest.leg import DOWN_TOLERANCE_MM, Layout, jansen_lengths, leg_from  # noqa: E402

LEGS = 2000
SPREAD = 0.25
SEED = 1
PERCENTILES = (5, 95)
# Ingredients that are only ever 0 or 1; their limits are 0 and 1, not percentiles.
WHOLE_RANGE = {"upright": [0.0, 1.0]}
# Distance's highest limit is Jansen's distance per turn (default layout and down tolerance) times
# this; its lowest stays the survey's.
DISTANCE_TOP_JANSEN_TIMES = 2
# The bob that scores full marks on flatness; its other end stays the survey's.
FLATNESS_BEST_MM = 0.0


def survey(legs: int = LEGS, spread: float = SPREAD, seed: int = SEED) -> dict[str, list[float]]:
    """Each ingredient's low and high percentile over `legs` random working legs, or WHOLE_RANGE."""
    rng = random.Random(seed)
    jansen = jansen_lengths()
    values: dict[str, list[float]] = {name: [] for name in INGREDIENTS}
    found = 0
    while found < legs:
        leg = leg_from([rng.uniform(x * (1 - spread), x * (1 + spread)) for x in jansen])
        if leg.jams:
            continue
        found += 1
        for name, value in ingredient_values(leg).items():
            values[name].append(value)
    limits = {}
    for name, sample in values.items():
        if name in WHOLE_RANGE:
            limits[name] = WHOLE_RANGE[name]
            continue
        cuts = statistics.quantiles(sample, n=100, method="inclusive")
        limits[name] = [round(cuts[p - 1], 4) for p in PERCENTILES]
    return limits


def widened(limits: dict[str, list[float]], jansen_distance: float) -> dict[str, list[float]]:
    """A copy of the limits with distance's highest at DISTANCE_TOP_JANSEN_TIMES Jansen's distance
    and flatness's lowest, its best end, at FLATNESS_BEST_MM."""
    limits = {name: list(pair) for name, pair in limits.items()}
    limits["distance"][1] = round(DISTANCE_TOP_JANSEN_TIMES * jansen_distance, 4)
    limits["flatness"][0] = FLATNESS_BEST_MM
    return limits


def main() -> None:
    jansen = leg_from(jansen_lengths(), Layout(), DOWN_TOLERANCE_MM)
    data = {
        "about": "Limits for normalisation by fixed limits: each ingredient's 5th and 95th "
                 "percentiles over random working legs, or 0 and 1 for an ingredient that is only "
                 "ever 0 or 1, except that distance's highest limit is "
                 f"{DISTANCE_TOP_JANSEN_TIMES} times Jansen's distance per turn and flatness's "
                 f"lowest is {FLATNESS_BEST_MM:g} mm, so that beating Jansen still scores more. "
                 "Written by scripts/survey_limits.py.",
        "legs": LEGS,
        "spread": SPREAD,
        "seed": SEED,
        "percentiles": list(PERCENTILES),
        "down_tolerance_mm": DOWN_TOLERANCE_MM,
        "distance_top_jansen_times": DISTANCE_TOP_JANSEN_TIMES,
        "flatness_best_mm": FLATNESS_BEST_MM,
        "limits": widened(survey(), jansen.distance),
    }
    LIMITS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for name, (low, high) in data["limits"].items():
        print(f"{name:12} {low:10.4f} {high:10.4f}")


if __name__ == "__main__":
    main()
