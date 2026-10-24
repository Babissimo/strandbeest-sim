"""Survey random working legs for the fixed limits of the second normalisation (decisions Q5).

Each length is drawn uniformly within ±25% of Jansen's, on the standard layout, until 2,000 legs
turn fully; each ingredient's limits are its 5th and 95th percentiles over those legs. Writes
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
from beest.leg import DOWN_TOLERANCE_MM, jansen_lengths, leg_from  # noqa: E402

LEGS = 2000
SPREAD = 0.25
SEED = 1
PERCENTILES = (5, 95)


def survey(legs: int = LEGS, spread: float = SPREAD, seed: int = SEED) -> dict[str, list[float]]:
    """Each ingredient's low and high percentile over `legs` random working legs."""
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
        cuts = statistics.quantiles(sample, n=100, method="inclusive")
        limits[name] = [round(cuts[p - 1], 4) for p in PERCENTILES]
    return limits


def main() -> None:
    data = {
        "about": "Limits for normalisation by fixed limits: each ingredient's 5th and 95th "
                 "percentiles over random working legs. Written by scripts/survey_limits.py.",
        "legs": LEGS,
        "spread": SPREAD,
        "seed": SEED,
        "percentiles": list(PERCENTILES),
        "down_tolerance_mm": DOWN_TOLERANCE_MM,
        "limits": survey(),
    }
    LIMITS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for name, (low, high) in data["limits"].items():
        print(f"{name:12} {low:10.4f} {high:10.4f}")


if __name__ == "__main__":
    main()
