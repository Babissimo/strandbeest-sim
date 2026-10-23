"""The progress graph, drawn with the canvas 2D API: each run's best and average score against
evaluations, or a second view of the best beest's raw ingredients.

Runs stay on the graph, each in its own colour, until it is cleared; once MAX_SERIES are on it,
each new run takes the place of the oldest. The graph is handed its canvas, sized by its owner,
and the browser's `window` (for Path2D and Array), so nothing here imports the browser.
"""
from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from beest.fitness import INGREDIENTS

# Categorical colours in a fixed order (they keep apart under colour blindness in this order).
COLOURS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
MAX_SERIES = len(COLOURS)
INK = "#1d232a"
MUTED = "#59636e"
GRID = "#e3e7eb"
AXIS = "#b8c0c8"
PAPER = "#ffffff"
FONT = "12px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
TITLE_FONT = "600 12px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
# Space round the score plot for tick labels and titles, in px: top, right, bottom, left.
PAD = (26, 14, 36, 54)
MEAN_DASH = (5, 4)
VIEWS = ("score", "ingredients")
X_TITLE = "Evaluations (beests scored)"
# Each ingredient's title and unit; one missing here shows under its own name, with no unit.
INGREDIENT_NAMES: dict[str, tuple[str, str]] = {
    "distance": ("Distance per turn", "mm"),
    "stride": ("Stride", "mm"),
    "step_height": ("Step height", "mm"),
    "time_down": ("Time down", "fraction of a turn"),
    "flatness": ("Flatness: body bob", "mm"),
    # Whether a level body always has feet on either side: stricter than the arena's 30° rule.
    "upright": ("Upright (quick check)", ""),
}


def title(name: str) -> str:
    return INGREDIENT_NAMES.get(name, (name.replace("_", " ").capitalize(), ""))[0]


def label(name: str) -> str:
    """The ingredient's title with its unit, as a heading or a box's label."""
    unit = INGREDIENT_NAMES.get(name, ("", ""))[1]
    return f"{title(name)} ({unit})" if unit else title(name)


def reading(name: str, value: float) -> str:
    """A value of the ingredient with its unit when that is short."""
    unit = INGREDIENT_NAMES.get(name, ("", ""))[1]
    return f"{short(value)} mm" if unit == "mm" else short(value)


def value_range(values: list[float]) -> tuple[float, float]:
    """A range holding 0 and every finite value; 0 to 1 when there is nothing else to hold."""
    finite = [v for v in values if math.isfinite(v)]
    low, high = min(finite + [0.0]), max(finite + [0.0])
    if high - low <= 1e-12 * max(1.0, abs(low), abs(high)):
        return 0.0, 1.0
    return low, high


def nice_step(span: float, count: int) -> float:
    """A step of 1, 2 or 5 times a power of ten giving about `count` steps across `span`."""
    raw = span / max(count, 1)
    power = 10 ** math.floor(math.log10(raw))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= raw * (1 - 1e-9))


def ticks(low: float, high: float, count: int = 5) -> list[float]:
    """Round values from at or below `low` to at or above `high`; `high` must exceed `low`."""
    step = nice_step(high - low, count)
    first, last = math.floor(low / step + 1e-9), math.ceil(high / step - 1e-9)
    return [k * step for k in range(first, last + 1)]


def _without_minus_zero(text: str) -> str:
    return "0" if text.strip("-0.,") == "" else text


def tick_label(value: float, step: float) -> str:
    places = max(0, -math.floor(math.log10(step) + 1e-9))
    return _without_minus_zero(f"{value:,.{places}f}")


def short(value: float) -> str:
    """A value with as many decimals as a reading needs."""
    places = 0 if abs(value) >= 100 else 1 if abs(value) >= 10 else 2
    return _without_minus_zero(f"{value:,.{places}f}")


@dataclass(eq=False)
class Series:
    """One run's points: evaluations so far, best and average score, and the best's ingredients.

    `relative` marks a run normalised by each generation's own lowest and highest; `ended`
    says how a run that did not finish ended ("stopped", say), for the legend.
    """
    label: str
    colour: str
    relative: bool = False
    evaluations: list[int] = field(default_factory=list)
    best: list[float] = field(default_factory=list)
    mean: list[float] = field(default_factory=list)
    values: list[dict[str, float]] = field(default_factory=list)
    ended: str = ""
    # The lowest and highest score ("score") and value of each ingredient so far.
    extremes: dict[str, tuple[float, float]] = field(default_factory=dict)
    # The run that made way for this one on a full graph.
    displaced: Series | None = field(default=None, repr=False)

    def add(self, report: dict) -> None:
        # A run with points stays, so the run it displaced cannot come back.
        self.displaced = None
        self.evaluations.append(report["evaluations"])
        self.best.append(report["best_score"])
        self.mean.append(report["mean_score"])
        self.values.append(report["best_values"])
        self._widen("score", report["best_score"], report["mean_score"])
        for name, value in report["best_values"].items():
            self._widen(name, value)

    def _widen(self, key: str, *values: float) -> None:
        low, high = self.extremes.get(key, (math.inf, -math.inf))
        self.extremes[key] = min(low, *values), max(high, *values)

    def __len__(self) -> int:
        return len(self.evaluations)

    def nearest(self, evaluations: float) -> int | None:
        """The point closest to this many evaluations, or None before the first."""
        if not self.evaluations:
            return None
        # Evaluations only grow along a run.
        k = bisect.bisect_left(self.evaluations, evaluations)
        nearby = [j for j in (k - 1, k) if 0 <= j < len(self)]
        return min(nearby, key=lambda j: abs(self.evaluations[j] - evaluations))


@dataclass(frozen=True)
class Plot:
    """A plotting area of the canvas in px, the ticks along each axis, and the cell round it
    (left, top, right, bottom) where the pointer reads it."""
    left: float
    top: float
    right: float
    bottom: float
    xs: list[float]
    ys: list[float]
    cell: tuple[float, float, float, float]

    def x(self, value: float) -> float:
        across = (value - self.xs[0]) / (self.xs[-1] - self.xs[0])
        return self.left + across * (self.right - self.left)

    def y(self, value: float) -> float:
        up = (value - self.ys[0]) / (self.ys[-1] - self.ys[0])
        return self.bottom - up * (self.bottom - self.top)

    def holds(self, point: tuple[float, float]) -> bool:
        x0, y0, x1, y1 = self.cell
        return x0 <= point[0] <= x1 and y0 <= point[1] <= y1

    def value_at(self, px: float) -> float:
        """The evaluations under px, which is first brought inside the plot."""
        px = min(max(px, self.left), self.right)
        return self.xs[0] + (px - self.left) / (self.right - self.left) * (self.xs[-1] - self.xs[0])


class Graph:
    def __init__(self, canvas, js):
        self.canvas = canvas
        self.ctx = canvas.getContext("2d")
        self.js = js
        self.series: list[Series] = []
        self.view = "score"
        # The canvas's size on the page, in CSS px.
        self.width = self.height = 0.0
        # Runs that have made way for newer ones since the graph was last cleared.
        self.dropped = 0
        # Where the pointer is over the canvas, in px, or None.
        self.hover: tuple[float, float] | None = None
        # Each plot drawn last, with what it plots for a series at a point.
        self._plots: list[tuple[Plot, Callable[[Series, int], list[float]]]] = []

    def add(self, label: str, relative: bool) -> Series:
        """A new run's series, in the first free colour; the oldest run goes when all are used."""
        displaced = None
        if len(self.series) >= MAX_SERIES:
            displaced = self.series.pop(0)
            self.dropped += 1
        used = {s.colour for s in self.series}
        series = Series(label, next(c for c in COLOURS if c not in used), relative,
                        displaced=displaced)
        self.series.append(series)
        return series

    def discard(self, series: Series) -> None:
        """Take a run off the graph, bringing back the run it displaced."""
        self.series.remove(series)
        if series.displaced is not None and len(self.series) < MAX_SERIES:
            self.series.insert(0, series.displaced)
            self.dropped -= 1

    def clear(self, keep: Series | None = None) -> None:
        """Take every run off the graph but `keep`."""
        self.series[:] = [] if keep is None else [keep]
        self.dropped = 0
        if keep is not None:
            keep.displaced = None

    @property
    def relative(self) -> bool:
        """Whether every run on the graph is scored relative to its own generations."""
        return bool(self.series) and all(s.relative for s in self.series)

    @property
    def axis_title(self) -> str:
        return "Score, relative to this generation" if self.relative else "Score"

    def draw(self) -> None:
        self.ctx.clearRect(0, 0, self.width, self.height)
        self._plots = []
        if self.width < 120 or self.height < 120:
            return
        if self.view == "score":
            self._draw_scores()
        else:
            self._draw_ingredients()
        self._crosshair()

    def _x_ticks(self) -> list[float]:
        most = max((s.evaluations[-1] for s in self.series if len(s)), default=0)
        return ticks(0.0, float(max(most, 1)), 6)

    def _draw_scores(self) -> None:
        values = [v for s in self.series for v in s.extremes.get("score", ())]
        top, right, bottom, left = PAD
        plot = Plot(left, top, self.width - right, self.height - bottom, self._x_ticks(),
                    ticks(*value_range(values), 5), (0, 0, self.width, self.height))
        self._plots.append((plot, lambda s, k: [s.best[k], s.mean[k]]))
        self._axes(plot, self.axis_title, x_labels=True)
        self._text(plot.right, self.height - 6, X_TITLE, MUTED, "right")
        for series in self.series:
            self._line(plot, series.evaluations, series.mean, series.colour, 1.5, dashed=True)
            self._line(plot, series.evaluations, series.best, series.colour, 2.0)
        for series in self.series:
            if len(series):
                self._dot(plot.x(series.evaluations[-1]), plot.y(series.best[-1]), series.colour)
        if not self.series:
            self._text((plot.left + plot.right) / 2, (plot.top + plot.bottom) / 2,
                       "Press Run: each run draws its own line here.", MUTED, "center")

    def _draw_ingredients(self) -> None:
        names = list(INGREDIENTS)
        columns = 3 if self.width >= 640 else 2
        rows = math.ceil(len(names) / columns)
        cell_w, cell_h = self.width / columns, (self.height - 22) / rows
        xs = self._x_ticks()
        for k, name in enumerate(names):
            row, column = divmod(k, columns)
            # A panel with none below it carries the evaluation labels.
            labelled = k + columns >= len(names)
            x0, y0 = column * cell_w, row * cell_h
            values = [v for s in self.series for v in s.extremes.get(name, ())]
            plot = Plot(x0 + 50, y0 + 22, x0 + cell_w - 20, y0 + cell_h - (22 if labelled else 10),
                        xs, ticks(*value_range(values), 3), (x0, y0, x0 + cell_w, y0 + cell_h))
            self._plots.append((plot, lambda s, k, name=name: [s.values[k][name]]))
            self._axes(plot, label(name), x_labels=labelled, x_count=3)
            for series in self.series:
                self._line(plot, series.evaluations, [v[name] for v in series.values],
                           series.colour, 2.0)
        self._text(self.width - 12, self.height - 6, X_TITLE, MUTED, "right")
        if not self.series:
            self._text(self.width / 2, self.height / 2,
                       "Press Run to see the best beest's measurements.", MUTED, "center")

    def _axes(self, plot: Plot, heading: str, x_labels: bool, x_count: int = 6) -> None:
        ctx = self.ctx
        ctx.lineWidth = 1
        ctx.strokeStyle = GRID
        grid = "".join(f"M{plot.left:.1f} {plot.y(v):.1f}H{plot.right:.1f}" for v in plot.ys)
        ctx.stroke(self.js.Path2D.new(grid))
        ctx.strokeStyle = AXIS
        zero = plot.y(0.0)
        ctx.stroke(self.js.Path2D.new(f"M{plot.left:.1f} {zero:.1f}H{plot.right:.1f}"
                                      f"M{plot.left:.1f} {plot.top:.1f}V{plot.bottom:.1f}"))
        y_step = plot.ys[1] - plot.ys[0]
        for v in plot.ys:
            self._text(plot.left - 6, plot.y(v), tick_label(v, y_step), MUTED, "right")
        if x_labels:
            every = max(1, math.ceil((len(plot.xs) - 1) / x_count))
            x_step = plot.xs[1] - plot.xs[0]
            for v in plot.xs[::every]:
                self._text(plot.x(v), plot.bottom + 12, tick_label(v, x_step), MUTED, "center")
        self._text(plot.left - 44, plot.top - 13, heading, INK, "left", TITLE_FONT)

    def _line(self, plot: Plot, xs: list[int], ys: list[float], colour: str, width: float,
              dashed: bool = False) -> None:
        if len(xs) < 2:
            return
        ctx = self.ctx
        # More than two points a pixel cannot be seen, so long runs draw every few, and the last.
        every = math.ceil(len(xs) / max(1, round(2 * (plot.right - plot.left))))
        kept = list(range(0, len(xs), every))
        if kept[-1] != len(xs) - 1:
            kept.append(len(xs) - 1)
        path = "M" + "L".join(f"{plot.x(xs[k]):.1f} {plot.y(ys[k]):.1f}" for k in kept)
        ctx.strokeStyle = colour
        ctx.lineWidth = width
        ctx.lineJoin = ctx.lineCap = "round"
        if dashed:
            ctx.setLineDash(self.js.Array.of(*MEAN_DASH))
        ctx.stroke(self.js.Path2D.new(path))
        if dashed:
            ctx.setLineDash(self.js.Array.new())

    def _dot(self, x: float, y: float, colour: str) -> None:
        ctx = self.ctx
        ctx.beginPath()
        ctx.arc(x, y, 4, 0, 2 * math.pi)
        ctx.fillStyle = colour
        ctx.fill()
        ctx.lineWidth = 2
        ctx.strokeStyle = PAPER
        ctx.stroke()

    def _hovered(self):
        """The plot under the pointer, what it plots, and the evaluations there; or None."""
        if self.hover is None or not self.series:
            return None
        for plot, values in self._plots:
            if plot.holds(self.hover):
                return plot, values, plot.value_at(self.hover[0])
        return None

    def _crosshair(self) -> None:
        hovered = self._hovered()
        if hovered is None:
            return
        plot, values, at = hovered
        ctx = self.ctx
        ctx.lineWidth = 1
        ctx.strokeStyle = AXIS
        x = plot.x(at)
        ctx.stroke(self.js.Path2D.new(f"M{x:.1f} {plot.top:.1f}V{plot.bottom:.1f}"))
        for series in self.series:
            k = series.nearest(at)
            if k is not None:
                for v in values(series, k):
                    self._dot(plot.x(series.evaluations[k]), plot.y(v), series.colour)

    def readout(self) -> list[str]:
        """What the graph shows where the pointer is, one line per run."""
        hovered = self._hovered()
        if hovered is None:
            return []
        at = hovered[2]
        lines = []
        for series in self.series:
            k = series.nearest(at)
            if k is None:
                continue
            where = f"{series.label} after {series.evaluations[k]:,} evaluations:"
            if self.view == "score":
                lines.append(f"{where} best {short(series.best[k])}, "
                             f"average {short(series.mean[k])}")
            else:
                parts = [f"{name.replace('_', ' ')} {reading(name, value)}"
                         for name, value in series.values[k].items()]
                lines.append(f"{where} {', '.join(parts)}")
        return lines

    def _text(self, x: float, y: float, text: str, colour: str, align: str,
              font: str = FONT) -> None:
        ctx = self.ctx
        ctx.font = font
        ctx.fillStyle = colour
        ctx.textAlign = align
        ctx.textBaseline = "middle"
        ctx.fillText(text, x, y)
