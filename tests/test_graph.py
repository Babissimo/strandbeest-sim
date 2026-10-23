"""The progress graph's scales, and that it draws whatever the scores are."""
import math
from types import SimpleNamespace

import pytest

from app import graph
from beest.fitness import INGREDIENTS


class Context:
    """Stands in for a canvas 2D context, keeping every call and every number it was given."""

    def __init__(self, numbers: list[float]):
        self.__dict__["numbers"] = numbers

    def __getattr__(self, name):
        def call(*args):
            self.numbers.extend(a for a in args if isinstance(a, (int, float)))
        return call


def browser():
    """A canvas and the parts of `window` the graph uses; paths keep the text they were made of."""
    numbers: list[float] = []
    paths: list[str] = []
    canvas = SimpleNamespace(getContext=lambda kind: Context(numbers))
    js = SimpleNamespace(
        Path2D=SimpleNamespace(new=lambda d: paths.append(d) or d),
        Array=SimpleNamespace(of=lambda *xs: list(xs), new=lambda: []),
    )
    return canvas, js, numbers, paths


def report(evaluations: int, best: float, mean: float, value: float = 0.0) -> dict:
    return {"evaluations": evaluations, "best_score": best, "mean_score": mean,
            "best_values": {name: value for name in INGREDIENTS}}


def drawn(series_reports: list[list[dict]], view: str = "score"):
    canvas, js, numbers, paths = browser()
    g = graph.Graph(canvas, js)
    g.width, g.height = 720, 300
    for k, reports in enumerate(series_reports):
        series = g.add(f"Run {k + 1}", relative=False)
        for r in reports:
            series.add(r)
    g.view = view
    g.hover = (300, 100)
    g.draw()
    return g, numbers, paths


def assert_finite(numbers: list[float], paths: list[str]) -> None:
    assert all(math.isfinite(x) for x in numbers)
    assert not any("nan" in p.lower() or "inf" in p.lower() for p in paths)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], (0.0, 1.0)),
        ([0.0, 0.0], (0.0, 1.0)),
        ([2.5, 2.5], (0.0, 2.5)),
        ([-3.0, -1.0], (-3.0, 0.0)),
        ([math.nan, math.inf, 4.0], (0.0, 4.0)),
        ([-1.0, 2.0], (-1.0, 2.0)),
    ],
)
def test_value_range_holds_zero_and_is_never_empty(values, expected):
    assert graph.value_range(values) == expected


@pytest.mark.parametrize(("low", "high"), [(0, 1), (0, 1.23), (-358, 174), (0, 1500), (0, 1e-9)])
def test_ticks_cover_the_range_in_round_steps(low, high):
    found = graph.ticks(low, high, 5)
    assert found[0] <= low and found[-1] >= high
    assert 3 <= len(found) <= 12
    steps = {round(b - a, 12) for a, b in zip(found, found[1:])}
    assert len(steps) == 1
    mantissa = steps.pop() / 10 ** math.floor(math.log10(found[1] - found[0]))
    assert round(mantissa, 9) in (1, 2, 5)


def test_tick_labels():
    assert graph.tick_label(1200, 200) == "1,200"
    assert graph.tick_label(0.5, 0.1) == "0.5"
    assert graph.tick_label(-0.0, 0.5) == "0"
    assert graph.short(1234.5) == "1,234"
    assert graph.short(0.8731) == "0.87"


@pytest.mark.parametrize("view", graph.VIEWS)
@pytest.mark.parametrize(
    "series_reports",
    [
        [],
        [[report(30, 0.0, 0.0)]],
        [[report(30 * k, 0.0, 0.0) for k in range(1, 41)]],
        [[report(k, 0.5, 0.5, 7.0) for k in range(1, 6)],
         [report(k, 0.5, 0.5, 7.0) for k in range(1, 3)]],
        [[report(10, -2.0, -5.0, -100.0), report(20, 3.0, 1.0, 50.0)]],
    ],
    ids=["empty", "one-point", "all-zero", "all-equal", "negative"],
)
def test_draws_any_scores(series_reports, view):
    g, numbers, paths = drawn(series_reports, view)
    assert_finite(numbers, paths)
    assert len(g.readout()) == len(series_reports)


def test_too_small_to_draw():
    canvas, js, numbers, paths = browser()
    g = graph.Graph(canvas, js)
    g.width = g.height = 0
    g.hover = (0, 0)
    g.draw()
    assert g.readout() == []


def test_each_run_keeps_its_colour():
    canvas, js, _, _ = browser()
    g = graph.Graph(canvas, js)
    runs = [g.add(f"Run {k}", relative=False) for k in range(graph.MAX_SERIES)]
    assert [s.colour for s in runs] == list(graph.COLOURS)
    extra = g.add("Run 9", relative=False)
    assert runs[0] not in g.series and len(g.series) == graph.MAX_SERIES
    assert extra.colour == graph.COLOURS[0]
    assert [s.colour for s in g.series[:-1]] == list(graph.COLOURS[1:])
    assert g.dropped == 1
    # A run that fails before its first point gives its place back.
    g.discard(extra)
    assert g.series == runs and g.dropped == 0
    extra = g.add("Run 9", relative=False)
    extra.add(report(30, 1.0, 0.5))
    assert extra.displaced is None
    g.clear(keep=extra)
    assert g.series == [extra] and g.dropped == 0


def test_extremes_follow_the_points():
    series = graph.Series("Run 1", graph.COLOURS[0])
    series.add(report(30, 2.0, -1.0, 5.0))
    series.add(report(60, 3.0, 0.5, -2.0))
    assert series.extremes["score"] == (-1.0, 3.0)
    assert all(series.extremes[name] == (-2.0, 5.0) for name in INGREDIENTS)


def test_relative_axis_only_when_every_run_is_relative():
    canvas, js, _, _ = browser()
    g = graph.Graph(canvas, js)
    assert not g.relative
    g.add("Run 1", relative=True)
    assert g.relative
    g.add("Run 2", relative=False)
    assert not g.relative
    g.clear()
    assert g.series == [] and not g.relative


def test_readout_names_the_run_and_its_numbers():
    g, _, _ = drawn([[report(30, 0.25, 0.1), report(60, 1.5, 0.75)]])
    g.hover = (g._plots[0][0].right + 5, 100)
    assert g.readout() == ["Run 1 after 60 evaluations: best 1.50, average 0.75"]
    g.hover = None
    assert g.readout() == []


def test_long_runs_draw_two_points_a_pixel():
    long = [report(k, k / 1000, 0.0) for k in range(1, 50_001)]
    g, numbers, paths = drawn([long])
    plot = g._plots[0][0]
    assert all(p.count("L") <= 2 * (plot.right - plot.left) + 1 for p in paths)
    assert any(p.endswith(f"L{plot.x(50_000):.1f} {plot.y(50.0):.1f}") for p in paths)


def test_nearest_point():
    series = graph.Series("Run 1", graph.COLOURS[0])
    assert series.nearest(10) is None
    for evaluations in (30, 60, 90):
        series.add(report(evaluations, 0.0, 0.0))
    assert [series.nearest(x) for x in (0, 44, 46, 60, 1000)] == [0, 0, 1, 1, 2]


def test_ingredients_follow_the_engine(monkeypatch):
    monkeypatch.setattr(graph, "INGREDIENTS", {**INGREDIENTS, "grip": True})
    one = report(30, 1.0, 0.5) | {"best_values": {name: 2.0 for name in graph.INGREDIENTS}}
    g, numbers, paths = drawn([[one, one]], "ingredients")
    assert_finite(numbers, paths)
    assert len(g._plots) == len(INGREDIENTS) + 1
    assert graph.label("grip") == "Grip"
    assert graph.label("upright") == "Upright"
    assert graph.label("step_height") == "Step height (mm)"
    assert graph.reading("upright", 1.0) == "1.00"
    assert graph.reading("stride", 57.42) == "57.4 mm"
    g.hover = (g._plots[-1][0].left, g._plots[-1][0].top)
    assert g.readout()[0].endswith("flatness 2.00 mm, upright 2.00, grip 2.00")
