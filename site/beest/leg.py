"""Jansen's leg in mm, and a whole beest built from any leg design with everything it measures.

Genes are hole-to-hole lengths in mm (MM_PER_UNIT to a Jansen unit): a plain list of 13 in the
order a to m (decisions S6). The layout (how many leg pairs, at which throw angles) travels beside
the list.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .geometry import ANGLES, HOLY, JAM_MARGIN_MM, LENGTH_NAMES, LegTrace, trace_leg
from .measures import beest_feet, beest_measures, foot_measures, tips

MM_PER_UNIT = 1.2
DOWN_TOLERANCE_MM = 1.0
# Where the body's centre of mass lies along x from the crank axle, which the chassis is
# symmetric about.
CENTRE_OF_MASS_X_MM = 0.0
# a and l place the fixed pivot G from the crank axle; every other length is a stick.
LENGTH_BOUNDS: dict[str, tuple[float, float]] = {
    name: (-30.0, 30.0) if name == "l" else (10.0, 104.0) for name in LENGTH_NAMES}
STICKS = tuple(name for name in LENGTH_NAMES if name not in ("a", "l"))
PAIRS_BOUNDS = (1, 4)
RANDOM_SPREAD = 0.3


def even_phases(pairs: int) -> tuple[float, ...]:
    """Throw angles in degrees spread evenly round the crank, the first at 0."""
    return tuple(360 * k / pairs for k in range(pairs))


@dataclass(frozen=True)
class Layout:
    """How many mirrored leg pairs the crank carries, and each pair's throw angle in degrees."""
    pairs: int = 3
    # Left empty, the throws are spread evenly.
    phases: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        whole = isinstance(self.pairs, int) and not isinstance(self.pairs, bool)
        if not whole or not PAIRS_BOUNDS[0] <= self.pairs <= PAIRS_BOUNDS[1]:
            raise ValueError(f"a beest has a whole number of pairs of legs from {PAIRS_BOUNDS[0]} "
                             f"to {PAIRS_BOUNDS[1]}, not {self.pairs!r}")
        phases = tuple(float(p) for p in self.phases) or even_phases(self.pairs)
        if len(phases) != self.pairs:
            raise ValueError(f"{self.pairs} pairs need {self.pairs} throw angles, not {len(phases)}")
        if not all(math.isfinite(p) for p in phases):
            raise ValueError(f"throw angles must be ordinary numbers, not {phases}")
        object.__setattr__(self, "phases", phases)


def jansen_lengths() -> list[float]:
    """Jansen's holy numbers as hole-to-hole mm, a to m."""
    return [HOLY[name] * MM_PER_UNIT for name in LENGTH_NAMES]


@dataclass(frozen=True)
class Leg:
    """A whole beest built from one leg design: what `fitness(leg)` reads.

    Lengths are in mm. A jammed leg carries 0.0 for every measure.
    """
    genes: list[float]
    layout: Layout
    jams: bool
    jam_reason: str | None
    # One foot's travel along the ground while it is down.
    stride: float
    # How high one foot lifts.
    step_height: float
    # The fraction of a turn one foot is down.
    time_down: float
    # How far the whole beest walks in one crank turn; negative when it walks the wrong way.
    distance: float
    # How far the body rises and falls over a turn.
    bob: float
    # How close the tightest pair of links comes to failing to meet; negative for a jammed leg.
    closest_to_jam: float
    # Every stick lies within LENGTH_BOUNDS.
    fits: bool
    trace: LegTrace = field(repr=False)
    # Whether the beest tips over at some crank angle: its centre of mass lies beyond the feet on
    # the ground (those within the down tolerance of the lowest). None for a jammed leg.
    tips: bool | None = None
    # Each ingredient on a common scale, filled in by fitness.normalise.
    normalised: dict[str, float] = field(default_factory=dict, repr=False, compare=False)

    @property
    def flatness(self) -> float:
        """The body bob under the slides' name; lower is better."""
        return self.bob

    @property
    def upright(self) -> float:
        """1.0 when the beest stays up all the way round, 0.0 when it tips or jams."""
        return 1.0 if self.tips is False else 0.0


def leg_from(genes: list[float], layout: Layout = Layout(), tol: float = DOWN_TOLERANCE_MM,
             n: int = ANGLES, margin: float = JAM_MARGIN_MM) -> Leg:
    """Build the beest these 13 lengths (a to m) describe, on this layout, and measure it.

    A foot counts as down within `tol` mm of its lowest point, and holds the body up within `tol`
    mm of the lowest foot at that angle. A pair of links closer than `margin` mm to failing to
    meet counts as jammed.
    """
    if len(genes) != len(LENGTH_NAMES):
        raise ValueError(f"a leg needs {len(LENGTH_NAMES)} lengths (a to m), not {len(genes)}")
    if not 0 <= tol < math.inf:
        raise ValueError(f"the down tolerance must be 0 mm or more, not {tol}")
    if n < 2 or n % 2:
        raise ValueError(f"a beest needs an even number of crank angles, not {n}")
    genes = [float(x) for x in genes]
    lengths = dict(zip(LENGTH_NAMES, genes))
    for name, length in lengths.items():
        if not math.isfinite(length):
            raise ValueError(f"length {name} must be an ordinary number, not {length}")
    trace = trace_leg(lengths, n, margin)
    fits = all(LENGTH_BOUNDS[name][0] <= lengths[name] <= LENGTH_BOUNDS[name][1] for name in STICKS)
    if trace.jammed:
        return Leg(genes=genes, layout=layout, jams=True, jam_reason=trace.jam_reason, stride=0.0,
                   step_height=0.0, time_down=0.0, distance=0.0, bob=0.0,
                   closest_to_jam=trace.closest_to_jam, fits=fits, trace=trace)
    foot = foot_measures(trace.foot, tol)
    beest = beest_measures(trace.foot, list(layout.phases))
    return Leg(genes=genes, layout=layout, jams=False, jam_reason=None, stride=foot.stride,
               step_height=foot.step_height, time_down=foot.time_down, distance=beest.distance,
               bob=beest.bob, closest_to_jam=trace.closest_to_jam, fits=fits, trace=trace,
               tips=tips(beest_feet(trace.foot, list(layout.phases)), tol, CENTRE_OF_MASS_X_MM))
