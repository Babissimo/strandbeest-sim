"""Circle intersections, leg tracking, jams and four-bar linkages."""
import math
import random

import pytest

from beest.geometry import (HOLY, LENGTH_NAMES, LegTrace, circ, circle_margin, grashof_class,
                            self_intersects, trace_four_bar, trace_leg)


def test_circ_tangent():
    points = circ((0, 0), 1, (2, 0), 1)
    assert points is not None
    for p in points:
        assert math.dist(p, (1, 0)) < 1e-9


def test_circ_apart_and_concentric():
    assert circ((0, 0), 1, (3, 0), 1) is None
    assert circ((0, 0), 1, (0, 0), 2) is None


def test_margin_sign():
    assert circle_margin((0, 0), 1, (1.5, 0), 1) > 0
    assert circle_margin((0, 0), 1, (3, 0), 1) < 0


def test_jams_part_way():
    trace = trace_leg({**HOLY, "m": 16.5})
    assert trace.jammed
    assert math.degrees(trace.jam_angle) == pytest.approx(182, abs=2)
    assert "f and g" in trace.jam_reason
    assert len(trace.joints) == 91
    assert len(trace.angles) == 91


def test_margin_counts_near_misses():
    # Jansen's k and c come within 1.19 of folding flat, so a 2 margin jams him there.
    trace = trace_leg(HOLY, n=360, margin=2.0)
    assert trace.jammed
    assert "k and c" in trace.jam_reason
    assert not trace_leg(HOLY, n=360, margin=1.0).jammed


@pytest.mark.parametrize("value", [10, 104])
@pytest.mark.parametrize("l", [None, -30, 30])
def test_extreme_lengths_never_raise(value, l):
    lengths = {name: value for name in LENGTH_NAMES}
    if l is not None:
        lengths["l"] = l
    trace = trace_leg(lengths)
    assert isinstance(trace, LegTrace)
    assert trace.jammed == (trace.jam_reason is not None)


@pytest.mark.parametrize("lengths, expected", [
    ((40, 15, 40, 35), "crank-rocker"),
    ((15, 40, 35, 40), "double-crank"),
    ((40, 30, 20, 25), "non-Grashof"),
    ((40, 20, 40, 20), "change point"),
    ((40, 35, 15, 40), "double-rocker"),
    ((40, 35, 40, 15), "rocker-crank"),
])
def test_grashof_classes(lengths, expected):
    assert grashof_class(*lengths) == expected


@pytest.mark.parametrize("lengths, jams", [
    ((40, 15, 40, 35), False),
    ((15, 40, 35, 40), False),
    ((40, 30, 20, 25), True),
    ((40, 35, 15, 40), True),
    ((40, 35, 40, 15), True),
])
def test_four_bar_jams_iff_not_rotatable(lengths, jams):
    trace = trace_four_bar(*lengths)
    assert trace.jammed == jams
    if jams:
        assert len(trace.tracer) < 180


@pytest.mark.parametrize("lengths", [(40, 20, 40, 20), (40, 40, 40, 40)])
def test_change_point_returns(lengths):
    assert trace_four_bar(*lengths).grashof == "change point"


def test_four_bar_closes_its_path():
    trace = trace_four_bar(40, 15, 40, 35, along=20, offset=10)
    assert len(trace.tracer) == len(trace.angles) == len(trace.crank_tip) == len(trace.coupler_joint)
    for a, b in zip(trace.crank_tip, trace.coupler_joint):
        assert math.dist(a, b) == pytest.approx(40)
        assert math.dist(b, (40, 0)) == pytest.approx(35)


def test_figure_eight_survey():
    rng = random.Random(1)
    linkages = []
    while len(linkages) < 200:
        lengths = [rng.uniform(15, 104) for _ in range(4)]
        if grashof_class(*lengths) == "crank-rocker":
            linkages.append(lengths)
    straight = sum(trace_four_bar(*ls, along=rng.uniform(0, ls[2])).figure_eight for ls in linkages)
    offset = sum(trace_four_bar(*ls, along=rng.uniform(0, ls[2]),
                                offset=rng.uniform(-ls[2], ls[2])).figure_eight for ls in linkages)
    assert straight == 0
    assert offset >= 20


def test_known_figure_eight():
    assert trace_four_bar(59.5, 44.0, 92.6, 95.1, along=18.6, offset=-31.9).figure_eight


@pytest.mark.parametrize("along, offset", [(40, 0), (40 - 1e-6, 0), (40, 1e-6), (39.99, 0)])
def test_rocker_arc_is_not_a_figure_eight(along, offset):
    # On or beside the coupler joint the tracer swings to and fro along one arc.
    assert not trace_four_bar(40, 15, 40, 35, along=along, offset=offset).figure_eight


def test_four_bar_jam_reason():
    assert trace_four_bar(40, 15, 40, 35).jam_reason is None
    assert "cannot meet" in trace_four_bar(40, 30, 20, 25).jam_reason


def test_self_intersects():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    bow_tie = [(0, 0), (1, 1), (1, 0), (0, 1)]
    assert not self_intersects(square)
    assert self_intersects(bow_tie)


# Passes every circle check, but f and g pass through a fold, so J5 ends the turn on the other
# intersection.
NON_CLOSING = {"a": 38.1, "b": 33.2, "c": 29.9, "d": 41.0, "e": 70.0, "f": 48.1, "g": 37.0,
               "h": 61.7, "i": 36.2, "j": 43.3, "k": 55.0, "l": 9.9, "m": 11.6}


def test_leg_that_does_not_come_back_jams():
    trace = trace_leg(NON_CLOSING)
    assert trace.jammed
    assert trace.jam_angle is None
    assert trace.jam_reason == "the leg does not come back to where it started"
    assert len(trace.joints) == 180
