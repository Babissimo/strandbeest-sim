"""Every beest of a generation, small and best first, each with its score under it.

Each beest is drawn at the crank angle it is given, so Evolve's one crank turns them all with the
best beests; a beest that jams is drawn grey and still, as it stands at 0°. Tracing a generation
takes longer than a frame, so `work` traces a few beests at a time and the grid shows a
generation once it is all traced; one offered meanwhile waits its turn, and only the latest waits.
Each leg's position is turned into canvas coordinates once and kept until the layout changes, so a
frame mostly joins strings already made.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from pyscript import window

from app import draw
from app.beest_picture import BEHIND, FRONT, LEG_STICKS, pair_steps, step, traced_as_scored
from app.graph import short
from beest.geometry import LENGTH_NAMES, LegTrace
from beest.measures import throw_steps

# The small beests are traced at this many angles a turn, plenty at their size.
POPULATION_ANGLES = 90
# Each cell is at least this wide, and from the first to the second of these tall, in px, its
# score's line included.
CELL_WIDTH_PX = 104
CELL_HEIGHT_PX = (64, 112)
SCORE_PX = 18
PAD_PX = 6
# How long each frame may spend tracing, in s.
TRACE_BUDGET_S = 0.004
STILL = draw.translucent(draw.GROUND, 0.8)
# Drawn in this order, each colour with its line width in px.
STROKES = ((draw.GROUND, 1.0), (BEHIND, 1.5), (STILL, 1.5), (FRONT, 2.2), (draw.CRANK, 2.2))
FONT = "600 12px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

# Where a point in mm lands on the canvas, as "x y" in px.
Place = Callable[[float, float], str]


@dataclass
class _Small:
    """One small beest: its score, whether the run found it jams, its trace and its reach (the
    largest |x| and the lowest and highest y of every position it is drawn in)."""
    score: float
    jams: bool
    trace: LegTrace
    per_turn: int
    shifts: list[int]
    reach: tuple[float, float, float]
    # Each position's sticks as canvas path data, by (step, kind), for the layout on show.
    paths: dict[tuple[int, str], str] = field(default_factory=dict)

    @property
    def still(self) -> bool:
        return self.jams or self.trace.jammed

    def path(self, index: int, kind: str, place: Place) -> str:
        """The leg at this step ("leg"), its mirror image ("mirror") or its crank ("crank")."""
        key = (index, kind)
        made = self.paths.get(key)
        if made is None:
            joints = self.trace.joints[index]
            if kind == "crank":
                made = f"M{place(*joints['O'])}L{place(*joints['C'])}"
            else:
                sign = -1.0 if kind == "mirror" else 1.0
                at = {name: place(sign * x, y) for name, (x, y) in joints.items()}
                made = "".join(f"M{at[p]}L{at[q]}" for p, q in LEG_STICKS)
            self.paths[key] = made
        return made


@dataclass
class _Job:
    """A generation on its way to the screen: its members, best first, and those traced so far."""
    key: object
    members: list[dict]
    margin: float
    traced: list[_Small] = field(default_factory=list)


def traced(member: dict, margin: float) -> _Small:
    """A member of a report's population, traced for drawing."""
    lengths = dict(zip(LENGTH_NAMES, member["genes"]))
    trace, n = traced_as_scored(lengths, POPULATION_ANGLES, margin, member["jams"])
    still = member["jams"] or trace.jammed
    points = [p for pose in (trace.joints[:1] if still else trace.joints) for p in pose.values()]
    reach = ((max(abs(x) for x, _ in points), min(y for _, y in points),
              max(y for _, y in points)) if points else (0.0, math.inf, -math.inf))
    return _Small(member["score"], member["jams"], trace, n, throw_steps(member["phases"], n),
                  reach)


class PopulationGrid:
    """The grid on its canvas. `on_resize` runs after the canvas changes size, which clears it."""

    def __init__(self, canvas, on_resize: Callable[[], None]):
        self.canvas = canvas
        self.on_resize = on_resize
        self.view = draw.View(canvas, self._resized, margin=0)
        self.shown: list[_Small] = []
        self.key: object = None
        self._job: _Job | None = None
        self._wanted: _Job | None = None
        # How long a trace has taken lately, in s.
        self._trace_s = 0.0
        # The largest reach across, and the lowest and highest y, of the beests on show.
        self._reach = (1.0, -1.0, 1.0)
        self._height = 0.0
        # The cell width and scale the beests' paths were made for.
        self._layout: tuple[float, float] | None = None
        # The finest number of steps a turn among the beests on show.
        self._steps = POPULATION_ANGLES
        # What was drawn last, so an unchanged frame is not drawn again.
        self._drawn: tuple | None = None

    @property
    def busy(self) -> bool:
        return self._job is not None or self._wanted is not None

    def offer(self, key: object, members: list[dict], margin: float) -> None:
        """Shows these members of a report's population once they are traced; `key` names the
        generation, and offering the one on show or on its way again changes nothing."""
        if key in (self.key, None if self._job is None else self._job.key):
            return
        best_first = sorted(members, key=lambda m: m["score"], reverse=True)
        self._wanted = _Job(key, best_first, margin)

    def work(self) -> bool:
        """Traces beests for about TRACE_BUDGET_S; True when a generation has gone on show."""
        if self._job is None:
            self._job, self._wanted = self._wanted, None
        job = self._job
        if job is None:
            return False
        deadline = time.perf_counter() + TRACE_BUDGET_S
        # At least one beest a frame, and another only if it should end within the budget.
        for count in range(len(job.members) - len(job.traced)):
            began = time.perf_counter()
            if count and began + self._trace_s > deadline:
                break
            job.traced.append(traced(job.members[len(job.traced)], job.margin))
            # The slowest trace lately, forgotten slowly.
            self._trace_s = max(self._trace_s * 0.9, time.perf_counter() - began)
        if len(job.traced) < len(job.members):
            return False
        self._job = None
        self.shown, self.key = job.traced, job.key
        across = max((s.reach[0] for s in self.shown), default=0.0)
        low = min((s.reach[1] for s in self.shown), default=math.inf)
        high = max((s.reach[2] for s in self.shown), default=-math.inf)
        self._reach = (max(across, 1.0), low, high) if low <= high else (1.0, -1.0, 1.0)
        self._steps = max((s.per_turn for s in self.shown), default=POPULATION_ANGLES)
        self._layout = self._drawn = None
        self._lay_out()
        return True

    def _cell(self, width: float) -> tuple[int, float, float, float]:
        """For a canvas this wide, the number of columns, a cell's width and height in px, and
        the scale in px a mm."""
        columns = max(1, int(width // CELL_WIDTH_PX))
        cell = width / columns
        across, low, high = self._reach
        scale = (cell - 2 * PAD_PX) / (2 * across)
        tall = scale * (high - low) + SCORE_PX + 2 * PAD_PX
        height = min(max(tall, CELL_HEIGHT_PX[0]), CELL_HEIGHT_PX[1])
        scale = min(scale, (height - SCORE_PX - 2 * PAD_PX) / max(high - low, 1e-3))
        return columns, cell, height, scale

    def _lay_out(self) -> None:
        """Sizes the canvas to hold every cell; a new size redraws through on_resize."""
        self.canvas.hidden = not self.shown
        # A canvas that has just been shown has not been measured yet; its panel has, unless the
        # mode is hidden, and then the resize on its return lays it out.
        width = self.view.width or self.canvas.parentElement.clientWidth
        if not self.shown or not width:
            return
        columns, _, height, _ = self._cell(width)
        total = round(math.ceil(len(self.shown) / columns) * height)
        if total != self._height:
            self._height = total
            self.canvas.style.height = f"{total}px"

    def _resized(self) -> None:
        self._drawn = None
        if self.shown:
            self._lay_out()
        self.on_resize()

    def draw(self, theta: float) -> bool:
        """Draws every beest with the crank at `theta` (radians). False when there is nothing to
        draw or the canvas is not on screen."""
        view = self.view
        if not self.shown or not view.width:
            return False
        key = (self.key, step(theta, self._steps), view.width, view.height)
        if key == self._drawn:
            return True
        self._drawn = key
        columns, cell, height, scale = self._cell(view.width)
        if self._layout != (cell, scale):
            self._layout = cell, scale
            for small in self.shown:
                small.paths.clear()
        high = self._reach[2]
        lines: dict[str, list[str]] = {colour: [] for colour, _ in STROKES}
        scores = []
        for k, small in enumerate(self.shown):
            row, column = divmod(k, columns)
            left, top = column * cell, row * height + PAD_PX
            centre = left + cell / 2

            def place(x: float, y: float, centre=centre, top=top) -> str:
                return f"{centre + x * scale:.1f} {top + (high - y) * scale:.1f}"

            foot = self._beest(small, theta, place, lines)
            if foot is not None:
                y = top + (high - foot) * scale
                lines[draw.GROUND].append(
                    f"M{left + PAD_PX:.1f} {y:.1f}H{left + cell - PAD_PX:.1f}")
            scores.append((centre, (row + 1) * height - SCORE_PX / 2,
                           "jams" if small.jams else short(small.score), small.jams))
        ctx = view.ctx
        ctx.clearRect(0, 0, view.width, view.height)
        ctx.lineCap = ctx.lineJoin = "round"
        for colour, width in STROKES:
            if lines[colour]:
                ctx.strokeStyle = colour
                ctx.lineWidth = width
                ctx.stroke(window.Path2D.new("".join(lines[colour])))
        ctx.font = FONT
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        for x, y, text, jams in scores:
            ctx.fillStyle = draw.MUTED if jams else draw.INK
            ctx.fillText(text, x, y)
        return True

    @staticmethod
    def _beest(small: _Small, theta: float, place: Place,
               lines: dict[str, list[str]]) -> float | None:
        """Adds the beest's sticks to `lines`, by colour; returns its lowest foot's height, or
        None when it cannot be put together."""
        joints = small.trace.joints
        if not joints:
            return None
        if small.still:
            # As it stands at 0°: its first leg alone.
            lines[STILL] += [small.path(0, "leg", place), small.path(0, "crank", place)]
            return joints[0]["F"][1]
        foot = math.inf
        steps = pair_steps(step(theta, small.per_turn), small.shifts, len(joints))
        for k, (leg, mirror) in enumerate(steps):
            colour = FRONT if k == 0 else BEHIND
            lines[colour] += [small.path(leg, "leg", place), small.path(mirror, "mirror", place)]
            lines[draw.CRANK].append(small.path(leg, "crank", place))
            foot = min(foot, joints[leg]["F"][1], joints[mirror]["F"][1])
        return foot
