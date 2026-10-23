"""Leg playground: one Jansen leg with the body held still, its foot path and what the foot measures.

Measures come from a trace at ANGLES, as the GA scores legs; the drawing comes from one at
DRAW_ANGLES. A leg counts as jammed if either trace jams; the finer one is drawn unless only the
other jams.
"""
from __future__ import annotations

import math

from app import draw
from app.controls import Animator, Slider, announce, listen, swings
from beest.geometry import ANGLES, DRAW_ANGLES, LENGTH_NAMES, LegTrace, Point, trace_leg
from beest.leg import DOWN_TOLERANCE_MM, LENGTH_BOUNDS, jansen_lengths
from beest.measures import FootMeasures, foot_measures

# The down tolerance a student may choose here and in Evolve, in mm (decisions Q4).
TOLERANCE_BOUNDS = (0.5, 4.0)
LABELS = {"a": "a (frame)", "l": "l (frame)", "m": "m (crank)"}
# Each stick by the joints it joins, drawn in this order.
STICKS = (("j", "C", "J2"), ("k", "C", "J4"), ("b", "G", "J2"), ("c", "G", "J4"),
          ("d", "G", "J3"), ("e", "J2", "J3"), ("f", "J3", "J5"), ("g", "J4", "J5"),
          ("h", "J5", "F"), ("i", "J4", "F"), ("m", "O", "C"))
# The two rigid triangles: G-J2-J3 (b, d, e) on top and J4-J5-F (g, i, h) below.
COLOURS = {"a": draw.GROUND, "l": draw.GROUND, "m": draw.CRANK,
           **dict.fromkeys("bde", draw.COUPLER), **dict.fromkeys("ghi", draw.ROCKER),
           **dict.fromkeys("cfjk", draw.LINK)}
TRIANGLES = ((("G", "J2", "J3"), draw.COUPLER), (("J4", "J5", "F"), draw.ROCKER))
# Room in px below the foot path for the stride and the arrow, and between them.
BELOW_PX = 96
STRIDE_GAP_PX = 16
ARROW_GAP_PX = 74


MEASURES = ("stride", "step-height", "time-down", "closest-to-jam")


def measures_text(measures: FootMeasures | None, closest: float) -> list[str]:
    """Stride, step height, time down and closest to jam, as the table shows them."""
    if measures is None:
        return ["jams"] * len(MEASURES)
    return [f"{measures.stride:.1f} mm", f"{measures.step_height:.1f} mm",
            f"{round(100 * measures.time_down)}%", f"{closest:.1f} mm"]


class LegMode:
    """The leg section of the page, from its sliders to its canvas."""

    def __init__(self, root):
        self.root = root
        self.warning = root.querySelector("#leg-jam")
        self.cells = [root.querySelector(f"#leg-{name}") for name in MEASURES]
        self.jansen_cells = [root.querySelector(f"#leg-jansen-{name}") for name in MEASURES]
        lengths = root.querySelector("#leg-lengths")
        self.sliders = {name: Slider(lengths, f"leg-{name}", LABELS.get(name, name),
                                     LENGTH_BOUNDS[name], value, self.changed,
                                     colour=COLOURS[name])
                        for name, value in zip(LENGTH_NAMES, jansen_lengths())}
        self.tolerance = Slider(root.querySelector("#leg-down"), "leg-tolerance", "Within",
                                TOLERANCE_BOUNDS, DOWN_TOLERANCE_MM, self.tolerance_changed)
        self.jansen = trace_leg(dict(zip(LENGTH_NAMES, jansen_lengths())))
        self.reset = root.querySelector("#leg-reset")
        self._reset_proxy = listen(self.reset, "click", self.reset_to_jansen)
        self.view = draw.View(root.querySelector("canvas"), self.resized)
        # The leg at the angles the GA scores at, and the trace on screen.
        self.scored: LegTrace | None = None
        self.shown: LegTrace | None = None
        self.foot: list[Point] = []
        self.frame: list[Point] = []
        # The scored foot's lowest point and its x extent while down.
        self.ground: tuple[float, float, float] | None = None
        self.animator = Animator(root, self.draw)
        self.show_jansen()
        self.changed()
        self.reset.disabled = False

    @property
    def lengths(self) -> dict[str, float]:
        return {name: slider.value for name, slider in self.sliders.items()}

    def reset_to_jansen(self, event) -> None:
        for slider, value in zip(self.sliders.values(), jansen_lengths()):
            slider.set(value)
        self.changed()

    def changed(self) -> None:
        """Traces the leg again and shows what it does."""
        lengths = self.lengths
        self.scored = trace_leg(lengths)
        drawn = trace_leg(lengths, n=DRAW_ANGLES)
        # The drawing always agrees with the warning.
        if self.scored.jammed and not drawn.jammed:
            self.shown, per_turn = self.scored, ANGLES
        else:
            self.shown, per_turn = drawn, DRAW_ANGLES
        # LegTrace.foot builds a new list each time; the view caches its path by the list.
        self.foot = self.shown.foot
        for name, value in lengths.items():
            self.root.setAttribute(f"data-{name}", str(value))
        jammed = self.shown.jammed
        self.root.dataset.jammed = str(jammed).lower()
        announce(self.warning,
                 f"This leg jams: {self.shown.jam_reason}.{swings(self.shown)}" if jammed else "")
        # The frame offsets: a across from the crank axle, then l down to the pivot G.
        a, l = lengths["a"], lengths["l"]
        self.frame = [(0.0, 0.0), (-a, 0.0), (-a, -l)]
        self.measure()
        self.fit()
        self.animator.load(self.shown.angles, per_turn, loops=not jammed)

    def tolerance_changed(self) -> None:
        self.show_jansen()
        self.measure()

    def show_jansen(self) -> None:
        jansen = foot_measures(self.jansen.foot, self.tolerance.value)
        for cell, text in zip(self.jansen_cells,
                              measures_text(jansen, self.jansen.closest_to_jam)):
            cell.textContent = text

    def measure(self) -> None:
        """Measures the foot at the current down tolerance; a jammed leg has no measures."""
        tol = self.tolerance.value
        self.root.dataset.tolerance = str(tol)
        scored = self.scored
        measures = None if self.shown.jammed else foot_measures(scored.foot, tol)
        values = dict.fromkeys(MEASURES, "")
        self.ground = None
        if measures is not None:
            values = dict(zip(MEASURES, (measures.stride, measures.step_height,
                                         measures.time_down, scored.closest_to_jam)))
            # The band and the stride bar follow foot_measures on the scored foot, so they
            # match the numbers.
            low = min(y for _, y in scored.foot)
            down = [x for x, y in scored.foot if y <= low + tol]
            self.ground = low, min(down), max(down)
        for name, value in values.items():
            self.root.setAttribute(f"data-{name}", str(value))
        for cell, text in zip(self.cells, measures_text(measures, scored.closest_to_jam)):
            cell.textContent = text
        self.animator.redraw()

    def fit(self) -> None:
        """Frames everything the leg reaches in its turn, so the view holds still."""
        m, a = self.sliders["m"].value, self.sliders["a"].value
        points: list[Point] = [(-m, -m), (m, m), (-a, 0.0)]
        for joints in self.shown.joints:
            points += joints.values()
        if not self.shown.joints:
            points.append((-a, -self.sliders["l"].value))
        # Room below for the stride and the arrow.
        self.view.fit(draw.bounds(points), pad=(0, 0, BELOW_PX, 0))

    def resized(self) -> None:
        self.fit()
        self.animator.draw_now()

    def draw(self, index: int | None) -> bool:
        view = self.view
        if not view.ready:
            return False
        view.clear()
        view.grid()
        lengths = self.lengths
        a, l, m = lengths["a"], lengths["l"], lengths["m"]
        if self.ground is not None:
            self.draw_ground(*self.ground)
        x0, y0, x1, _ = view.box
        view.arrow(((x0 + x1) / 2, y0 - view.mm(ARROW_GAP_PX)), (-1.0, 0.0),
                   "The beest walks this way")
        view.circle((0.0, 0.0), m, draw.GROUND, dashed=True)
        view.path(self.foot, closed=not self.shown.jammed, colour=draw.TRACE)
        view.path(self.frame, colour=draw.GROUND, width=1.5)
        labels = [((-a / 2, 0.0), "a"), ((-a, -l / 2), "l")]
        if index is None:
            joints = {"O": (0.0, 0.0), "C": (m, 0.0), "G": (-a, -l)}
            view.stick(joints["O"], joints["C"], draw.CRANK)
            view.hole(joints["C"])
            labels.append(((m / 2, 0.0), "m"))
        else:
            joints = self.shown.joints[index]
            for corners, colour in TRIANGLES:
                view.plate([joints[name] for name in corners], colour)
            for name, p, q in STICKS:
                view.stick(joints[p], joints[q], COLOURS[name])
            for name in ("C", "J2", "J3", "J4", "J5"):
                view.hole(joints[name])
            view.hole(joints["F"], draw.TRACE)
            labels += [(midpoint(joints[p], joints[q]), name) for name, p, q in STICKS]
        view.pivot(joints["O"])
        view.pivot(joints["G"])
        view.labels(labels, draw.INK)
        if self.shown.jam_angle is not None:
            # Where the crank tip would have to go next.
            theta = self.shown.jam_angle
            view.cross((m * math.cos(theta), m * math.sin(theta)))
        return True

    def draw_ground(self, low: float, left: float, right: float) -> None:
        """The down band above the foot's lowest point and the stride under it."""
        view = self.view
        view.band(low, low + self.tolerance.value)
        y = low - view.mm(STRIDE_GAP_PX)
        view.dimension((left, y), (right, y), "stride")


def midpoint(p: Point, q: Point) -> Point:
    return (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
