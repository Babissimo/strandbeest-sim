"""Drawing linkages on a canvas: a view that fits a box in mm to the canvas, with y up.

Every size given in px is a CSS pixel; the canvas keeps one bitmap pixel per device pixel, so lines
stay crisp on high-density screens.
"""
from __future__ import annotations

import math
from collections.abc import Callable

from pyodide.ffi import create_proxy
from pyscript import window

from beest.geometry import Point

INK = "#1d232a"
MUTED = "#59636e"
GRID = "#edf0f3"
GROUND = "#8c96a0"
CRANK = "#e8590c"
COUPLER = "#1f5fbf"
ROCKER = "#2b8a3e"
TRACE = "#c2255c"
JAM = "#c62828"
BAND = "rgba(31, 95, 191, 0.12)"
PAPER = "#ffffff"

FONT = "600 13px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
STICK_PX = 9
HOLE_PX = 4.0
ARROW_PX = 64
# Box = (x_min, y_min, x_max, y_max) in mm.
Box = tuple[float, float, float, float]
# Paths built for the current view, by id of their point list.
_PATH_CACHE_SIZE = 8


def bounds(points: list[Point]) -> Box:
    """The smallest box holding every point."""
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def translucent(colour: str, alpha: float) -> str:
    """A #rrggbb colour as rgba with this opacity."""
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


class View:
    """Fits a box in mm to a canvas and draws into it; follows the canvas as it resizes.

    `on_resize` runs after each resize, which clears the canvas, so it should redraw.
    """

    def __init__(self, canvas, on_resize: Callable[[], None] | None = None, margin: float = 24):
        self.canvas = canvas
        self.ctx = canvas.getContext("2d")
        self.on_resize = on_resize
        self.margin = margin
        self.box: Box = (-1.0, -1.0, 1.0, 1.0)
        self.pad = (0.0, 0.0, 0.0, 0.0)
        self.width = self.height = 0
        self.scale = 0.0
        self._ox = self._oy = 0.0
        self._paths: dict[int, tuple[list[Point], bool, object]] = {}
        # The grid's step and its lines for the current view.
        self._grid: tuple[float, object] | None = None
        self._measure()
        self._resized = create_proxy(self._on_resize)
        self._observer = window.ResizeObserver.new(self._resized)
        self._observer.observe(canvas)
        # Moving to a screen of another pixel density changes the ratio but not the size.
        self._ratio_changed = create_proxy(self._on_ratio)
        self._watch_ratio()

    @property
    def ready(self) -> bool:
        """Whether the canvas is on screen and big enough to draw in."""
        return self.scale > 0

    def fit(self, box: Box, pad: tuple[float, float, float, float] = (0, 0, 0, 0)) -> None:
        """Shows `box` (mm) as large as fits, centred, with `pad` px more room (top, right,
        bottom, left) beyond the margin."""
        self.box = box
        self.pad = pad
        self._place()

    def px(self, p: Point) -> tuple[float, float]:
        """Where a point in mm lands on the canvas, in px from the top left."""
        return self._ox + p[0] * self.scale, self._oy - p[1] * self.scale

    def clear(self) -> None:
        self.ctx.clearRect(0, 0, self.width, self.height)

    def grid(self, step: float = 10.0) -> None:
        """Faint lines every `step` mm, left out when they would crowd closer than 8 px."""
        if not self.ready or step * self.scale < 8:
            return
        if self._grid is None or self._grid[0] != step:
            self._grid = step, window.Path2D.new(self._grid_lines(step))
        self._stroke(self._grid[1], GRID, 1)

    def _grid_lines(self, step: float) -> str:
        x0, x1 = -self._ox / self.scale, (self.width - self._ox) / self.scale
        y0, y1 = (self._oy - self.height) / self.scale, self._oy / self.scale
        parts = []
        for k in range(math.ceil(x0 / step), math.floor(x1 / step) + 1):
            x = self._ox + k * step * self.scale
            parts.append(f"M{x:.1f} 0V{self.height}")
        for k in range(math.ceil(y0 / step), math.floor(y1 / step) + 1):
            y = self._oy - k * step * self.scale
            parts.append(f"M0 {y:.1f}H{self.width}")
        return "".join(parts)

    def stick(self, p: Point, q: Point, colour: str, width: float = STICK_PX) -> None:
        """A stick between two holes: a thick line with rounded ends."""
        ctx = self.ctx
        ctx.beginPath()
        ctx.moveTo(*self.px(p))
        ctx.lineTo(*self.px(q))
        ctx.lineCap = "round"
        self._stroke(None, colour, width)

    def plate(self, points: list[Point], colour: str) -> None:
        """A rigid shape between holes, filled lightly."""
        ctx = self.ctx
        ctx.beginPath()
        ctx.moveTo(*self.px(points[0]))
        for p in points[1:]:
            ctx.lineTo(*self.px(p))
        ctx.closePath()
        ctx.fillStyle = translucent(colour, 0.18)
        ctx.fill()

    def hole(self, p: Point, colour: str = INK) -> None:
        """A pin joint: a hole through the sticks."""
        ctx = self.ctx
        x, y = self.px(p)
        ctx.beginPath()
        ctx.arc(x, y, HOLE_PX, 0, 2 * math.pi)
        ctx.fillStyle = PAPER
        ctx.fill()
        self._stroke(None, colour, 1.75)

    def pivot(self, p: Point) -> None:
        """A pivot fixed to the frame: a dark pin on a hatched stand."""
        ctx = self.ctx
        x, y = self.px(p)
        ctx.beginPath()
        ctx.moveTo(x, y)
        ctx.lineTo(x - 9, y + 15)
        ctx.lineTo(x + 9, y + 15)
        ctx.closePath()
        ctx.fillStyle = translucent(GROUND, 0.45)
        ctx.fill()
        hatch = [f"M{x - 12:.1f} {y + 15:.1f}H{x + 12:.1f}"]
        hatch += [f"M{x + dx:.1f} {y + 15:.1f}l-4 5" for dx in (-8, -3, 2, 7, 12)]
        self._stroke(window.Path2D.new("".join(hatch)), GROUND, 1.5)
        ctx.beginPath()
        ctx.arc(x, y, HOLE_PX + 1.5, 0, 2 * math.pi)
        ctx.fillStyle = INK
        ctx.fill()

    def path(self, points: list[Point], closed: bool = False, colour: str = TRACE,
             width: float = 2.5) -> None:
        """A line through the points, joined back to the first when `closed`."""
        if len(points) >= 2:
            self.ctx.lineCap = "round"
            self._stroke(self._polyline(points, closed), colour, width)

    def circle(self, centre: Point, radius: float, colour: str, dashed: bool = False) -> None:
        """A circle of `radius` mm, drawn thin."""
        ctx = self.ctx
        x, y = self.px(centre)
        ctx.beginPath()
        ctx.arc(x, y, max(radius * self.scale, 0.0), 0, 2 * math.pi)
        if dashed:
            ctx.setLineDash(window.Array.of(6, 5))
        self._stroke(None, colour, 1.5)
        ctx.setLineDash(window.Array.new())

    def band(self, y0: float, y1: float, colour: str = BAND) -> None:
        """A shaded strip across the whole canvas between two heights in mm."""
        top, bottom = self.px((0, max(y0, y1)))[1], self.px((0, min(y0, y1)))[1]
        self.ctx.fillStyle = colour
        self.ctx.fillRect(0, top, self.width, max(bottom - top, 1))

    def arrow(self, p: Point, direction: Point, label: str, colour: str = INK) -> None:
        """An arrow ARROW_PX long centred on `p`, pointing along `direction`, labelled above."""
        length = math.hypot(*direction)
        if not length:
            return
        ux, uy = direction[0] / length, -direction[1] / length
        cx, cy = self.px(p)
        half = ARROW_PX / 2
        tip = (cx + ux * half, cy + uy * half)
        tail = (cx - ux * half, cy - uy * half)
        head = [(tip[0] - ux * 11 + s * uy * 6, tip[1] - uy * 11 - s * ux * 6) for s in (1, -1)]
        shaft = f"M{tail[0]:.1f} {tail[1]:.1f}L{tip[0]:.1f} {tip[1]:.1f}"
        barbs = "".join(f"M{tip[0]:.1f} {tip[1]:.1f}L{x:.1f} {y:.1f}" for x, y in head)
        self.ctx.lineCap = "round"
        self._stroke(window.Path2D.new(shaft + barbs), colour, 2.5)
        self.text((cx, cy - 12), label, colour, world=False)

    def cross(self, p: Point, colour: str = JAM) -> None:
        """An X marking a place, such as where a linkage jams."""
        x, y = self.px(p)
        d = 6
        self.ctx.lineCap = "round"
        self._stroke(window.Path2D.new(
            f"M{x - d:.1f} {y - d:.1f}L{x + d:.1f} {y + d:.1f}"
            f"M{x - d:.1f} {y + d:.1f}L{x + d:.1f} {y - d:.1f}"), colour, 3)

    def text(self, p, label: str, colour: str = MUTED, world: bool = True) -> None:
        """A short label centred on `p` (mm, or px when `world` is false), with a paper halo."""
        ctx = self.ctx
        x, y = self.px(p) if world else p
        ctx.font = FONT
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.lineJoin = "round"
        ctx.lineWidth = 4
        ctx.strokeStyle = PAPER
        ctx.strokeText(label, x, y)
        ctx.fillStyle = colour
        ctx.fillText(label, x, y)

    def _stroke(self, shape, colour: str, width: float) -> None:
        ctx = self.ctx
        ctx.strokeStyle = colour
        ctx.lineWidth = width
        ctx.lineJoin = "round"
        if shape is None:
            ctx.stroke()
        else:
            ctx.stroke(shape)

    def _polyline(self, points: list[Point], closed: bool):
        # Each list becomes one Path2D, kept until the view changes, so redrawing it every frame
        # costs one call. The cache holds the list itself, so its id cannot be reused meanwhile.
        cached = self._paths.pop(id(points), None)
        if cached is not None and cached[0] is points and cached[1] == closed:
            self._paths[id(points)] = cached
            return cached[2]
        coords = (self.px(p) for p in points)
        d = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in coords) + ("Z" if closed else "")
        shape = window.Path2D.new(d)
        if len(self._paths) >= _PATH_CACHE_SIZE:
            self._paths.pop(next(iter(self._paths)))
        self._paths[id(points)] = (points, closed, shape)
        return shape

    def _place(self) -> None:
        self._paths.clear()
        self._grid = None
        top, right, bottom, left = self.pad
        x0, y0, x1, y1 = self.box
        across = self.width - 2 * self.margin - left - right
        down = self.height - 2 * self.margin - top - bottom
        if across <= 0 or down <= 0:
            self.scale = 0.0
            return
        # A box with no width or height still gets a finite scale.
        self.scale = min(across / max(x1 - x0, 1e-3), down / max(y1 - y0, 1e-3))
        self._ox = self.margin + left + across / 2 - (x0 + x1) / 2 * self.scale
        self._oy = self.margin + top + down / 2 + (y0 + y1) / 2 * self.scale

    def _measure(self) -> None:
        ratio = window.devicePixelRatio or 1
        self.width, self.height = self.canvas.clientWidth, self.canvas.clientHeight
        self.canvas.width = round(self.width * ratio)
        self.canvas.height = round(self.height * ratio)
        self.ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
        self._place()

    def _on_resize(self, entries=None, observer=None) -> None:
        self._measure()
        if self.on_resize is not None:
            self.on_resize()

    def _watch_ratio(self) -> None:
        self._ratio = window.matchMedia(f"(resolution: {window.devicePixelRatio}dppx)")
        self._ratio.addEventListener("change", self._ratio_changed)

    def _on_ratio(self, event) -> None:
        self._ratio.removeEventListener("change", self._ratio_changed)
        self._watch_ratio()
        self._on_resize()
