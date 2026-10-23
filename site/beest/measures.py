"""What a foot path measures: one foot on its own, and a whole beest of mirrored pairs."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import Point


@dataclass(frozen=True)
class FootMeasures:
    step_height: float
    time_down: float
    stride: float


def foot_measures(foot: list[Point], tol: float) -> FootMeasures:
    """A foot counts as down within `tol` of its lowest point; stride is its x extent while down.

    `foot` is a whole turn, so a jammed leg's path does not qualify.
    """
    ys = [y for _, y in foot]
    low = min(ys)
    down = [x for x, y in foot if y <= low + tol]
    return FootMeasures(step_height=max(ys) - low, time_down=len(down) / len(foot),
                        stride=max(down) - min(down))


def mirrored(foot: list[Point]) -> list[Point]:
    """The mirrored leg's foot: at crank angle θ it is (−x, y) of the original at π − θ (n even)."""
    n = len(foot)
    if n % 2:
        raise ValueError(f"mirroring needs an even number of crank angles, not {n}")
    return [(-foot[(n // 2 - t) % n][0], foot[(n // 2 - t) % n][1]) for t in range(n)]


def throw_steps(phases_deg: list[float], n: int) -> list[int]:
    """Each throw's angle as the nearest of n sampled steps round the turn."""
    return [math.floor(phase * n / 360 + 0.5) % n for phase in phases_deg]


def beest_feet(foot: list[Point], phases_deg: list[float]) -> list[list[Point]]:
    """Every foot at each crank angle: the original then the mirror, for each throw in turn.

    Each phase is rounded to the nearest sampled angle.
    """
    n = len(foot)
    mirror = mirrored(foot)
    shifts = throw_steps(phases_deg, n)
    return [[f for s in shifts for f in (foot[(t + s) % n], mirror[(t + s) % n])] for t in range(n)]


def tips(feet: list[list[Point]], tol: float, com_x: float = 0.0) -> bool:
    """Whether a level body over these feet tips over at any crank angle.

    At each angle the supporting feet are those within `tol` of that angle's lowest foot. The
    beest tips when `com_x` lies outside their x range; a foot exactly under it holds it up.
    """
    for at_angle in feet:
        low = min(y for _, y in at_angle)
        xs = [x for x, y in at_angle if y <= low + tol]
        if not min(xs) <= com_x <= max(xs):
            return True
    return False


@dataclass(frozen=True)
class BeestMeasures:
    bob: float
    distance: float


def beest_measures(foot: list[Point], phases_deg: list[float]) -> BeestMeasures:
    """Body bob and distance per turn for a level body carried by its lowest foot, with no slipping.

    `foot` is a whole turn. Each step's travel is the x travel of the foot that is lowest at the start of that step.
    """
    feet = beest_feet(foot, phases_deg)
    n = len(feet)
    # Between equally low feet, the one lower at the next angle carries the body.
    lowest = [min(range(len(f)), key=lambda k: (f[k][1], feet[(t + 1) % n][k][1]))
              for t, f in enumerate(feet)]
    heights = [feet[t][lowest[t]][1] for t in range(n)]
    distance = sum(feet[(t + 1) % n][lowest[t]][0] - feet[t][lowest[t]][0] for t in range(n))
    return BeestMeasures(bob=max(heights) - min(heights), distance=distance)
