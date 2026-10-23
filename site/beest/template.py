"""Printable templates at actual size: each stick with its holes marked, and the chassis holes.

Every page is an A4 portrait SVG whose viewBox counts millimetres, so a page printed at 100% gives
true lengths. Lengths are hole to hole; a stick's outline runs END_MARGIN_MM past each hole. Text
is fitted by an estimated width (`text_width`), as there are no font metrics to hand.
"""
from __future__ import annotations

import html
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .geometry import LENGTH_NAMES, Point
from .leg import Layout

PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297
# Printers leave 3–5 mm bare at each edge.
PAGE_MARGIN_MM = 10
STICK_WIDTH_MM = 10
# Holes sit at least this far from a stick's end (docs/brief.md §1).
END_MARGIN_MM = 5
HOLE_DIAMETER_MM = 3
CROSS_MM = 6
CALIBRATION_MM = 100
TITLE_FONT_MM = 5
TEXT_FONT_MM = 3.5
SMALL_FONT_MM = 3
LETTER_FONT_MM = 6
COLUMN_GAP_MM = 10
ROW_GAP_MM = 6
# Estimated character widths in ems, at least Helvetica Bold's (Arial shares its widths).
CHAR_EM = 0.62
CAPITAL_EM = 0.8
WIDE_EM = 0.95
WIDE_CHARACTERS = frozenset("MWmw%")

# One of each stick per leg, except the crank, whose tip both legs of a pair share.
STICKS_PER_PAIR: dict[str, int] = {name: 2 for name in "bcdefghijk"} | {"m": 1}
# The joints at the two holes of each stick of a leg (docs/brief.md §2).
LEG_STICK_ENDS: dict[str, tuple[str, str]] = {
    "b": ("G", "J2"), "c": ("G", "J4"), "d": ("G", "J3"), "e": ("J2", "J3"), "f": ("J3", "J5"),
    "g": ("J4", "J5"), "h": ("J5", "F"), "i": ("J4", "F"), "j": ("C", "J2"), "k": ("C", "J4"),
    "m": ("O", "C"),
}
FOUR_BAR_STICKS = ("ground", "crank", "coupler", "rocker")
CHASSIS_LABELS = {"O": "O (crank axle)", "G": "G", "mirrored-G": "G (mirrored leg)"}

# Arimo and Liberation Sans share Arial's widths, where Arial itself is missing.
_FONT = "Helvetica, Arial, Arimo, 'Liberation Sans', sans-serif"
_GREY = "#555"
_DESCENT = 0.3
_LINE_PITCH = 1.3
_RUN_GAP_MM = 3
_LEFT = PAGE_MARGIN_MM
_RIGHT = PAGE_WIDTH_MM - PAGE_MARGIN_MM
_BOTTOM = PAGE_HEIGHT_MM - PAGE_MARGIN_MM
_CONTENT_WIDTH = _RIGHT - _LEFT
_COLUMN_WIDTH = (_CONTENT_WIDTH - COLUMN_GAP_MM) / 2
_LONGEST_STICK_MM = _CONTENT_WIDTH - 2 * END_MARGIN_MM
_HOW_TO = "Lengths are hole to hole. Drill at the centre of each cross."
_CHECK = f"This bar should be {CALIBRATION_MM} mm long: check it with a ruler before you drill."
_TOO_BIG = "Part of this template is too big to print at actual size on A4."

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Stick:
    """A stick to make: `length` is hole to hole in mm, `ends` names the joint at each hole."""
    name: str
    length: float
    count: int
    ends: tuple[str, str] | None = None


@dataclass(frozen=True)
class Chassis:
    """The frame's holes: the crank axle O, a leg's fixed pivot G = (−a, −l) and its mirror."""
    a: float
    l: float

    @property
    def holes(self) -> dict[str, Point]:
        return {"O": (0.0, 0.0), "G": (-self.a, -self.l), "mirrored-G": (self.a, -self.l)}


def leg_sticks(genes: Sequence[float], pairs: int) -> list[Stick]:
    """The sticks for `pairs` pairs of legs, in the order b to k then the crank m."""
    lengths = _lengths(genes)
    return [Stick(name, lengths[name], per_pair * pairs, LEG_STICK_ENDS[name])
            for name, per_pair in STICKS_PER_PAIR.items()]


def leg_template_svg(genes: list[float], layout: Layout) -> list[str]:
    """One SVG per A4 page: every stick of the beest, then the chassis holes."""
    pairs = layout.pairs
    lengths = _lengths(genes)
    note = f"For {pairs} pair{'s' if pairs != 1 else ''} ({2 * pairs} legs)."
    return template_pages("Strandbeest leg template", note, leg_sticks(genes, pairs),
                          Chassis(lengths["a"], lengths["l"]))


def four_bar_template_svg(ground: float, crank: float, coupler: float, rocker: float) -> list[str]:
    """One SVG per A4 page: one of each of the four-bar's sticks."""
    sticks = [Stick(name, length, 1)
              for name, length in zip(FOUR_BAR_STICKS, (ground, crank, coupler, rocker))]
    return template_pages("Four-bar linkage template", "", sticks)


def template_pages(title: str, note: str, sticks: Sequence[Stick],
                   chassis: Chassis | None = None) -> list[str]:
    """Lay the sticks (and the chassis, last) onto as many A4 pages as they need.

    Each page repeats the heading and the calibration bar. Raises ValueError for anything that
    cannot be drawn at actual size inside the margins.
    """
    blocks = [_stick_block(stick) for stick in sticks]
    if chassis is not None:
        blocks.append(_chassis_block(chassis))
    top = _header(title, note, 1, 1)[3]
    pages = _paginate(_rows(blocks), top)
    return [_page(title, note, number, len(pages), placed) for number, placed in enumerate(pages, 1)]


def _lengths(genes: Sequence[float]) -> dict[str, float]:
    if len(genes) != len(LENGTH_NAMES):
        raise ValueError(f"A leg needs {len(LENGTH_NAMES)} lengths, a to m, not {len(genes)}.")
    return {name: float(value) for name, value in zip(LENGTH_NAMES, genes)}


# Drawing primitives, in mm with y down. Each knows its extent, ignoring stroke width.

@dataclass(frozen=True)
class _Run:
    text: str
    size: float
    cls: str | None = None
    bold: bool = False
    grey: bool = False


@dataclass(frozen=True)
class _Text:
    x: float
    y: float  # baseline
    runs: tuple[_Run, ...]
    cls: str
    anchor: str = "start"

    def box(self) -> Box:
        width = sum(text_width(r.text, r.size) for r in self.runs) + _RUN_GAP_MM * (len(self.runs) - 1)
        left = self.x - {"start": 0.0, "middle": width / 2, "end": width}[self.anchor]
        size = max(r.size for r in self.runs)
        return left, self.y - size, left + width, self.y + _DESCENT * size

    def svg(self, dx: float, dy: float) -> str:
        attrs = {"class": self.cls, "x": self.x + dx, "y": self.y + dy, "font-size": self.runs[0].size,
                 "text-anchor": None if self.anchor == "start" else self.anchor, "fill": "#000"}
        if len(self.runs) == 1 and self.runs[0].cls is None:
            return _el("text", attrs | _style(self.runs[0]), _esc(self.runs[0].text))
        spans = "".join(_el("tspan", {"class": r.cls, "dx": _RUN_GAP_MM if i else None,
                                      "font-size": r.size} | _style(r), _esc(r.text))
                        for i, r in enumerate(self.runs))
        return _el("text", attrs, spans)


@dataclass(frozen=True)
class _Line:
    x1: float
    y1: float
    x2: float
    y2: float
    cls: str
    stroke: float = 0.2

    def box(self) -> Box:
        return min(self.x1, self.x2), min(self.y1, self.y2), max(self.x1, self.x2), max(self.y1, self.y2)

    def svg(self, dx: float, dy: float) -> str:
        return _el("line", {"class": self.cls, "x1": self.x1 + dx, "y1": self.y1 + dy, "x2": self.x2 + dx,
                            "y2": self.y2 + dy, "stroke": "#000", "stroke-width": self.stroke})


@dataclass(frozen=True)
class _Hole:
    cx: float
    cy: float
    joint: str | None

    def box(self) -> Box:
        r = HOLE_DIAMETER_MM / 2
        return self.cx - r, self.cy - r, self.cx + r, self.cy + r

    def svg(self, dx: float, dy: float) -> str:
        return _el("circle", {"class": "hole", "cx": self.cx + dx, "cy": self.cy + dy,
                              "r": HOLE_DIAMETER_MM / 2, "data-joint": self.joint, "fill": "none",
                              "stroke": "#000", "stroke-width": 0.25})


@dataclass(frozen=True)
class _Outline:
    x: float
    y: float
    width: float

    def box(self) -> Box:
        return self.x, self.y, self.x + self.width, self.y + STICK_WIDTH_MM

    def svg(self, dx: float, dy: float) -> str:
        # Rounded ends like a lolly stick's, centred on the end holes.
        r = STICK_WIDTH_MM / 2
        return _el("rect", {"class": "outline", "x": self.x + dx, "y": self.y + dy, "width": self.width,
                            "height": STICK_WIDTH_MM, "rx": r, "ry": r, "fill": "none", "stroke": "#000",
                            "stroke-width": 0.3})


_Shape = _Text | _Line | _Hole | _Outline


@dataclass(frozen=True)
class _Block:
    """Shapes drawn as one group, placed by the top-left corner of their extent."""
    attrs: dict[str, object]
    shapes: tuple[_Shape, ...]
    box: Box

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    def svg(self, x: float, y: float) -> str:
        dx, dy = x - self.box[0], y - self.box[1]
        return _el("g", self.attrs, "".join(shape.svg(dx, dy) for shape in self.shapes))


def _block(attrs: dict[str, object], shapes: Iterable[_Shape]) -> _Block:
    shapes = tuple(shapes)
    return _Block(attrs, shapes, _union(shape.box() for shape in shapes))


def _union(boxes: Iterable[Box]) -> Box:
    lefts, tops, rights, bottoms = zip(*boxes)
    return min(lefts), min(tops), max(rights), max(bottoms)


def _hole(x: float, y: float, joint: str | None) -> list[_Shape]:
    arm = CROSS_MM / 2
    return [_Line(x - arm, y, x + arm, y, "cross"), _Line(x, y - arm, x, y + arm, "cross"),
            _Hole(x, y, joint)]


def _stick_block(stick: Stick) -> _Block:
    length = stick.length
    if not (math.isfinite(length) and length > 0):
        raise ValueError(f"Stick {stick.name} must be longer than 0 mm.")
    if length > _LONGEST_STICK_MM:
        raise ValueError(f"Stick {stick.name} ({_mm(length)}) is too long to print at actual size "
                         f"on A4 ({_mm(_LONGEST_STICK_MM)} at most).")
    runs = [_Run(stick.name, LETTER_FONT_MM, "letter", bold=True), _Run(_mm(length), TEXT_FONT_MM, "length"),
            _Run(f"make {stick.count}", TEXT_FONT_MM, "count")]
    if stick.ends:
        runs.append(_Run(" to ".join(stick.ends), SMALL_FONT_MM, "ends", grey=True))
    # The label sits above the stick, so even the shortest stick's label has room.
    top = LETTER_FONT_MM * (1 + _DESCENT) + 1
    middle = top + STICK_WIDTH_MM / 2
    shapes: list[_Shape] = [_Text(0, LETTER_FONT_MM, tuple(runs), "label"),
                            _Outline(0, top, length + 2 * END_MARGIN_MM)]
    for x, joint in zip((END_MARGIN_MM, END_MARGIN_MM + length), stick.ends or (None, None)):
        shapes += _hole(x, middle, joint)
    # The letter goes on the stick too where it clears both crosses by 1 mm.
    if text_width(stick.name, LETTER_FONT_MM) + 2 <= length - CROSS_MM:
        shapes.append(_Text(END_MARGIN_MM + length / 2, middle + 0.35 * LETTER_FONT_MM,
                            (_Run(stick.name, LETTER_FONT_MM, grey=True),), "name-on-stick", "middle"))
    attrs = {"class": "stick", "data-name": stick.name, "data-length": length, "data-count": stick.count,
             "data-ends": " ".join(stick.ends) if stick.ends else None}
    return _block(attrs, shapes)


def _chassis_block(chassis: Chassis) -> _Block:
    if not (math.isfinite(chassis.a) and math.isfinite(chassis.l)):
        raise ValueError("The chassis needs finite lengths a and l.")
    for turned in (False, True):
        block = _chassis_layout(chassis, turned)
        if block.width <= _CONTENT_WIDTH:
            return block
    raise ValueError("The chassis holes are too far apart to print at actual size on A4.")


def _chassis_layout(chassis: Chassis, turned: bool) -> _Block:
    # Page y runs down. Turning is a quarter turn, which keeps every distance between holes.
    points = {name: (x, -y) for name, (x, y) in chassis.holes.items()}
    if turned:
        points = {name: (-y, x) for name, (x, y) in points.items()}
    ox, oy = points["O"]
    pivots = [points["G"], points["mirrored-G"]]
    mean = (sum(x for x, _ in pivots) / 2, sum(y for _, y in pivots) / 2)
    # O's label sits on the side away from the pivots, and each pivot's points away from the
    # other pivot (G's to the left where they coincide, when a is 0), so the two never meet.
    away = {"O": (ox - mean[0], oy - mean[1])}
    for name, side in (("G", -1.0), ("mirrored-G", 1.0)):
        outward = points[name][0] - mean[0], points[name][1] - mean[1]
        away[name] = outward if outward != (0.0, 0.0) else (side, 0.0)
    shapes: list[_Shape] = []
    for name, (x, y) in points.items():
        shapes += _hole(x, y, name)
        shapes.append(_beside(CHASSIS_LABELS[name], x, y, *away[name]))
    left, y, _, _ = _union(shape.box() for shape in shapes)
    # On its own line, the note keeps a turned chassis narrow enough to share a row.
    if turned:
        y -= 1 + _DESCENT * TEXT_FONT_MM
        shapes.append(_Text(left, y, (_Run("Turned on its side to fit the page.", TEXT_FONT_MM),),
                            "turned-note"))
        y -= TEXT_FONT_MM
    caption = (_Run("Chassis", LETTER_FONT_MM, "title", bold=True),
               _Run(f"a = {_mm(chassis.a)}, l = {_mm(chassis.l)}", TEXT_FONT_MM, "detail"))
    shapes.append(_Text(left, y - 1 - _DESCENT * LETTER_FONT_MM, caption, "caption"))
    attrs = {"class": "chassis", "data-a": chassis.a, "data-l": chassis.l,
             "data-turned": "true" if turned else "false"}
    return _block(attrs, shapes)


def _beside(text: str, x: float, y: float, vx: float, vy: float) -> _Text:
    """A hole's label, beside its cross in the direction (vx, vy); above when that is (0, 0)."""
    clear = CROSS_MM / 2 + 1
    run = (_Run(text, TEXT_FONT_MM),)
    if abs(vx) > abs(vy):
        baseline = y + 0.35 * TEXT_FONT_MM
        if vx > 0:
            return _Text(x + clear, baseline, run, "hole-label")
        return _Text(x - clear, baseline, run, "hole-label", "end")
    if vy > 0:
        return _Text(x, y + clear + TEXT_FONT_MM, run, "hole-label", "middle")
    return _Text(x, y - clear - _DESCENT * TEXT_FONT_MM, run, "hole-label", "middle")


def _rows(blocks: Sequence[_Block]) -> list[list[_Block]]:
    """Two narrow blocks share a row, one per column; a wider block takes a row to itself."""
    rows: list[list[_Block]] = []
    for block in blocks:
        if block.width > _CONTENT_WIDTH:
            raise ValueError(_TOO_BIG)
        narrow = block.width <= _COLUMN_WIDTH
        if narrow and rows and len(rows[-1]) == 1 and rows[-1][0].width <= _COLUMN_WIDTH:
            rows[-1].append(block)
        else:
            rows.append([block])
    return rows


def _paginate(rows: Sequence[list[_Block]], top: float) -> list[list[tuple[_Block, float, float]]]:
    """Stack rows down each page from `top`; a row that would cross the bottom margin starts a page."""
    pages: list[list[tuple[_Block, float, float]]] = [[]]
    y = top
    for row in rows:
        height = max(block.height for block in row)
        if height > _BOTTOM - top:
            raise ValueError(_TOO_BIG)
        if y + height > _BOTTOM:
            pages.append([])
            y = top
        for column, block in enumerate(row):
            pages[-1].append((block, _LEFT + column * (_COLUMN_WIDTH + COLUMN_GAP_MM), y))
        y += height + ROW_GAP_MM
    return pages


def _header(title: str, note: str, number: int,
            pages: int) -> tuple[list[_Shape], list[_Shape], _Text, float]:
    """The heading, the calibration bar, the page number, and where the sticks may start."""
    heading, y = _paragraph(f"{title}: print at 100% (actual size)", TITLE_FONT_MM, "title",
                            PAGE_MARGIN_MM, bold=True)
    lines, y = _paragraph(f"{note} {_HOW_TO}".strip(), TEXT_FONT_MM, "note", y + 1.5)
    heading += lines
    bar_y = y + 5
    calibration: list[_Shape] = [_Line(_LEFT, bar_y, _LEFT + CALIBRATION_MM, bar_y, "bar", 0.4)]
    for mm in range(0, CALIBRATION_MM + 1, 10):
        tick = 2 if mm in (0, CALIBRATION_MM) else 1
        calibration.append(_Line(_LEFT + mm, bar_y - tick, _LEFT + mm, bar_y + tick, "tick", 0.3))
    lines, y = _paragraph(_CHECK, TEXT_FONT_MM, "check", bar_y + 3)
    calibration += lines
    page_number = _Text(_RIGHT, bar_y + 0.35 * TEXT_FONT_MM,
                        (_Run(f"Page {number} of {pages}", TEXT_FONT_MM),), "page-number", "end")
    return heading, calibration, page_number, y + ROW_GAP_MM


def _paragraph(text: str, size: float, cls: str, top: float,
               bold: bool = False) -> tuple[list[_Shape], float]:
    """Lines of text wrapped to the page's width, starting at `top`; returns them and their bottom."""
    shapes: list[_Shape] = []
    bottom = top
    for k, line in enumerate(_wrap(text, size, _CONTENT_WIDTH)):
        baseline = top + size + k * _LINE_PITCH * size
        shapes.append(_Text(_LEFT, baseline, (_Run(line, size, bold=bold),), cls))
        bottom = baseline + _DESCENT * size
    return shapes, bottom


def _wrap(text: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and text_width(f"{lines[-1]} {word}", size) <= width:
            lines[-1] += f" {word}"
        elif text_width(word, size) <= width:
            lines.append(word)
        else:
            raise ValueError(_TOO_BIG)
    return lines


def _page(title: str, note: str, number: int, pages: int,
          placed: Sequence[tuple[_Block, float, float]]) -> str:
    heading, calibration, page_number, _ = _header(title, note, number, pages)
    body = (_el("title", {}, _esc(f"{title}, page {number} of {pages}"))
            + _el("g", {"class": "heading"}, "".join(shape.svg(0, 0) for shape in heading))
            + _el("g", {"class": "calibration", "data-length": CALIBRATION_MM},
                  "".join(shape.svg(0, 0) for shape in calibration))
            + page_number.svg(0, 0)
            + "".join(block.svg(x, y) for block, x, y in placed))
    return _el("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": f"{PAGE_WIDTH_MM}mm",
                       "height": f"{PAGE_HEIGHT_MM}mm", "viewBox": f"0 0 {PAGE_WIDTH_MM} {PAGE_HEIGHT_MM}",
                       "class": "template-page", "data-page": number, "data-pages": pages,
                       "font-family": _FONT}, body)


def text_width(text: str, size: float) -> float:
    """The estimated width in mm of `text` at a font size of `size` mm."""
    return size * sum(WIDE_EM if c in WIDE_CHARACTERS else CAPITAL_EM if c.isupper() else CHAR_EM
                      for c in text)


def _style(run: _Run) -> dict[str, object]:
    # Only what the run sets, so a plain run keeps the fill of its text element.
    return ({"font-weight": "bold"} if run.bold else {}) | ({"fill": _GREY} if run.grey else {})


def _mm(value: float) -> str:
    text = f"{value:.1f}"
    if text == "-0.0":
        text = "0.0"
    return text.replace("-", "−") + " mm"


def _num(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _esc(text: str) -> str:
    return html.escape(text)


def _el(tag: str, attrs: dict[str, object], inner: str = "") -> str:
    """One SVG element; attributes set to None are left out, and numbers are given to 0.001 mm."""
    written = "".join(
        f' {key}="{_num(value) if isinstance(value, int | float) else _esc(str(value))}"'
        for key, value in attrs.items() if value is not None)
    return f"<{tag}{written}>{inner}</{tag}>" if inner else f"<{tag}{written}/>"
