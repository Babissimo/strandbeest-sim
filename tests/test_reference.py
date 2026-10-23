"""Al's measured reference cases (docs/brief.md §3) and the geometry traps found while scoping.

The values are in Jansen units, at the holy numbers.
"""
import math

import pytest

from beest import geometry, measures

N = 360
PHASES = {1: [0], 2: [0, 180], 3: [0, 120, 240]}

# A leg within ±25% of Jansen's that passes the 180-angle jam check under the max-y/min-x rule,
# although the rule switches J5 between intersections and the foot jumps 108 mm in one 2° step.
TELEPORTER = {"a": 42.7, "b": 39.9, "c": 34.0, "d": 44.6, "e": 66.4, "f": 44.8, "g": 40.4,
              "h": 77.3, "i": 53.4, "j": 53.5, "k": 60.5, "l": 7.1, "m": 16.0}


@pytest.fixture(scope="module")
def jansen():
    return geometry.trace_leg(geometry.HOLY, n=N)


def test_holy_numbers():
    assert geometry.HOLY == {"a": 38, "b": 41.5, "c": 39.3, "d": 40.1, "e": 55.8, "f": 39.4, "g": 36.7,
                             "h": 65.7, "i": 49, "j": 50, "k": 61.9, "l": 7.8, "m": 15}


def test_jansen_turns_fully(jansen):
    assert not jansen.jammed
    assert jansen.rule_disagreements == 0


def test_step_height(jansen):
    assert measures.foot_measures(jansen.foot, 1.0).step_height == pytest.approx(22.46, abs=0.05)


@pytest.mark.parametrize("tol, time_down, stride", [(0.5, 0.37, 50.2), (1, 0.43, 57.4),
                                                    (2, 0.52, 64.9), (4, 0.65, 67.9)])
def test_single_foot(jansen, tol, time_down, stride):
    foot = measures.foot_measures(jansen.foot, tol)
    assert foot.time_down == pytest.approx(time_down, abs=0.01)
    assert foot.stride == pytest.approx(stride, abs=0.3)


@pytest.mark.parametrize("pairs, bob, distance", [(1, 2.19, 125.9), (2, 1.44, 135.3), (3, 0.08, 141.1)])
def test_whole_beest(jansen, pairs, bob, distance):
    beest = measures.beest_measures(jansen.foot, PHASES[pairs])
    assert beest.bob == pytest.approx(bob, abs=0.02)
    # The brief's distances leave out each takeover step; the continuous values are up to 0.5% higher.
    assert beest.distance == pytest.approx(distance, rel=0.01)


def test_foot_moves_plus_x_while_down(jansen):
    foot = jansen.foot
    low = min(y for _, y in foot)
    steps = [foot[(t + 1) % N][0] - foot[t][0] for t in range(N)
             if foot[t][1] <= low + 1 and foot[(t + 1) % N][1] <= low + 1]
    assert steps
    assert all(dx > 0 for dx in steps)


def test_jansen_closest_to_jam(jansen):
    # k and c nearly fold flat once a turn.
    assert jansen.closest_to_jam == pytest.approx(1.19, abs=0.03)


def test_tracking_keeps_a_switching_leg_continuous():
    rule = [geometry.rule_joints(TELEPORTER, 2 * math.pi * t / 180)["F"] for t in range(180)]
    assert max(math.dist(rule[t], rule[(t + 1) % 180]) for t in range(180)) > 100

    traced = geometry.trace_leg(TELEPORTER, n=720)
    assert not traced.jammed
    assert traced.rule_disagreements > 0
    assert max(math.dist(traced.foot[t], traced.foot[(t + 1) % 720]) for t in range(720)) < 5
