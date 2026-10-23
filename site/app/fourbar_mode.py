"""Four-bar mode: four sticks in a loop, a crank that turns, and the path of a point on the coupler.

The crank turns about the origin and the rocker about (ground, 0) (decisions S4). The tracing point
sits `along` mm from the crank end of the coupler and `offset` mm out to its left (decisions Q7).
"""
from __future__ import annotations

import math

from pyscript import document

from app import draw
from app.controls import Animator, Slider, shown, swings
from beest.geometry import DRAW_ANGLES, FourBarTrace, Point, trace_four_bar

LINKS = ("ground", "crank", "coupler", "rocker")
COLOURS = {"ground": draw.GROUND, "crank": draw.CRANK, "coupler": draw.COUPLER,
           "rocker": draw.ROCKER}
# Hole-to-hole mm that fits on a lolly stick (decisions Q16).
STICK_BOUNDS = (10.0, 104.0)
# A crank-rocker: the crank is the shortest stick and S + L < P + Q.
DEFAULT_LENGTHS = {"ground": 60.0, "crank": 20.0, "coupler": 60.0, "rocker": 50.0}
DEFAULT_ALONG = 30.0
DEFAULT_OFFSET = 0.0
# The tracing point's reach, in multiples of the coupler's length.
ALONG_SPAN = (-1.0, 2.0)
OFFSET_SPAN = 1.0

# Each kind of four-bar in plain words: a name, then what it does.
GRASHOF_WORDS = {
    "crank-rocker": ("Crank-rocker", "The crank is the shortest stick, so it turns all the way "
                     "round while the rocker swings back and forth."),
    "double-crank": ("Double crank", "The ground is the shortest stick, so the crank and the "
                     "rocker both turn all the way round."),
    "rocker-crank": ("Rocker-crank", "The rocker is the shortest stick. It could turn all the way "
                     "round, but the crank can only swing, so turning the crank jams."),
    "double-rocker": ("Double rocker", "The coupler is the shortest stick. The crank and the "
                      "rocker can only swing, so turning the crank jams."),
    "change point": ("Change point", "The shortest and longest sticks add up to exactly the other "
                     "two, so at one point all four line up and the linkage can flip either way."),
    "non-Grashof": ("Not Grashof", "The shortest and longest sticks add up to more than the other "
                    "two, so no stick can turn all the way round and turning the crank jams."),
}


class FourBarMode:
    """The four-bar section of the page, from its sliders to its canvas."""

    def __init__(self, root):
        self.root = root
        self.grashof = root.querySelector("#fourbar-grashof")
        self.warning = root.querySelector("#fourbar-jam")
        self.badge = root.querySelector("#fourbar-figure-eight")
        # The Grashof class and sums last shown.
        self.described: tuple[str, str] | None = None
        lengths = root.querySelector("#fourbar-lengths")
        tracer = root.querySelector("#fourbar-tracer")
        self.sliders = {name: Slider(lengths, f"fourbar-{name}", name.capitalize(), STICK_BOUNDS,
                                     DEFAULT_LENGTHS[name], self.changed, colour=COLOURS[name])
                        for name in LINKS}
        coupler = DEFAULT_LENGTHS["coupler"]
        self.sliders["along"] = Slider(tracer, "fourbar-along", "Along",
                                       self.along_bounds(coupler), DEFAULT_ALONG, self.changed)
        self.sliders["offset"] = Slider(tracer, "fourbar-offset", "Sideways",
                                        self.offset_bounds(coupler), DEFAULT_OFFSET, self.changed)
        self.view = draw.View(root.querySelector("canvas"), self.resized)
        self.trace: FourBarTrace | None = None
        self.animator = Animator(root, self.draw)
        self.changed()

    @staticmethod
    def along_bounds(coupler: float) -> tuple[float, float]:
        return ALONG_SPAN[0] * coupler, ALONG_SPAN[1] * coupler

    @staticmethod
    def offset_bounds(coupler: float) -> tuple[float, float]:
        return -OFFSET_SPAN * coupler, OFFSET_SPAN * coupler

    def value(self, name: str) -> float:
        return self.sliders[name].value

    def changed(self) -> None:
        """Traces the linkage again and shows what it does."""
        coupler = self.value("coupler")
        self.sliders["along"].set_bounds(self.along_bounds(coupler))
        self.sliders["offset"].set_bounds(self.offset_bounds(coupler))
        lengths = [self.value(name) for name in LINKS]
        trace = trace_four_bar(*lengths, self.value("along"), self.value("offset"), n=DRAW_ANGLES)
        self.trace = trace
        self.describe(lengths, trace)
        for name, slider in self.sliders.items():
            self.root.setAttribute(f"data-{name}", str(slider.value))
        self.root.dataset.jammed = str(trace.jammed).lower()
        self.root.dataset.grashof = trace.grashof
        self.root.dataset.figureEight = str(trace.figure_eight).lower()
        self.fit()
        self.animator.load(trace.angles, DRAW_ANGLES, loops=not trace.jammed)

    def describe(self, lengths: list[float], trace: FourBarTrace) -> None:
        name, meaning = GRASHOF_WORDS[trace.grashof]
        short, p, q, long = sorted(lengths)
        rule = (f"Shortest + longest: {shown(short)} + {shown(long)} = {shown(short + long)} mm. "
                f"The other two: {shown(p)} + {shown(q)} = {shown(p + q)} mm.")
        if self.described != (name, rule):
            self.described = name, rule
            heading = document.createElement("strong")
            heading.textContent = f"{name}. "
            detail = document.createElement("span")
            detail.className = "rule"
            detail.textContent = rule
            self.grashof.replaceChildren(heading, meaning, document.createElement("br"), detail)
        warning = f"This linkage jams: {trace.jam_reason}.{swings(trace)}" if trace.jammed else ""
        # The warning stays on the page, empty and out of sight when there is no jam, so screen
        # readers announce it as it fills; it is rewritten only when it changes.
        if self.warning.textContent != warning:
            self.warning.textContent = warning
        self.badge.hidden = not trace.figure_eight

    def unassembled(self) -> list[tuple[Point, float]]:
        """For a linkage that cannot be put together, the coupler's and rocker's circles about
        their ends with the crank at 0°; they never meet."""
        if self.trace.angles:
            return []
        return [((self.value("crank"), 0.0), self.value("coupler")),
                ((self.value("ground"), 0.0), self.value("rocker"))]

    def fit(self) -> None:
        """Frames everything the linkage reaches in its turn, so the view holds still."""
        ground, crank = self.value("ground"), self.value("crank")
        trace = self.trace
        points: list[Point] = [(0.0, 0.0), (ground, 0.0), (-crank, -crank), (crank, crank)]
        points += trace.coupler_joint + trace.tracer
        for (x, y), r in self.unassembled():
            points += [(x - r, y - r), (x + r, y + r)]
        # Room below for the fixed pivots' stands.
        self.view.fit(draw.bounds(points), pad=(0, 0, 18, 0))

    def resized(self) -> None:
        self.fit()
        self.animator.draw_now()

    def draw(self, index: int | None) -> bool:
        view, trace = self.view, self.trace
        if not view.ready:
            return False
        view.clear()
        view.grid()
        ground, crank = self.value("ground"), self.value("crank")
        pivot: Point = (ground, 0.0)
        view.circle((0.0, 0.0), crank, draw.GROUND, dashed=True)
        view.path(trace.tracer, closed=not trace.jammed, colour=draw.TRACE)
        view.stick((0.0, 0.0), pivot, draw.GROUND)
        if index is None:
            for centre, radius in self.unassembled():
                view.circle(centre, radius, draw.JAM, dashed=True)
            tip = (crank, 0.0)
            view.stick((0.0, 0.0), tip, draw.CRANK)
            view.hole(tip)
        else:
            tip, joint, tracer = (trace.crank_tip[index], trace.coupler_joint[index],
                                  trace.tracer[index])
            if math.dist(tracer, tip) + math.dist(tracer, joint) > self.value("coupler") + 1e-6:
                # Off the coupler, the point is held by two more sticks: a rigid triangle.
                view.plate([tip, joint, tracer], draw.COUPLER)
                view.stick(tip, tracer, draw.COUPLER, width=draw.STICK_PX - 3)
                view.stick(joint, tracer, draw.COUPLER, width=draw.STICK_PX - 3)
            view.stick(joint, pivot, draw.ROCKER)
            view.stick(tip, joint, draw.COUPLER)
            view.stick((0.0, 0.0), tip, draw.CRANK)
            view.hole(tip)
            view.hole(joint)
            view.hole(tracer, draw.TRACE)
        view.pivot((0.0, 0.0))
        view.pivot(pivot)
        if trace.jam_angle is not None:
            # Where the crank tip would have to go next.
            theta = trace.jam_angle
            view.cross((crank * math.cos(theta), crank * math.sin(theta)))
        return True
