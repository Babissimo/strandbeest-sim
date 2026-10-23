"""Single-foot and whole-beest measures."""
import math

import pytest

from beest import geometry, measures
from beest.leg import MM_PER_UNIT


@pytest.fixture(scope="module")
def foot():
    return geometry.trace_leg(geometry.HOLY, n=360).foot


def test_mirror_identity(foot):
    mirror = measures.mirrored(foot)
    for t in range(0, 360, 7):
        x, y = geometry.rule_joints(geometry.HOLY, math.pi - math.radians(t))["F"]
        assert mirror[t] == pytest.approx((-x, y), abs=1e-9)


def test_beest_feet_order(foot):
    feet = measures.beest_feet(foot, [0, 120, 240])
    mirror = measures.mirrored(foot)
    assert len(feet) == 360
    assert all(len(f) == 6 for f in feet)
    assert feet[10][0] == foot[10]
    assert feet[10][1] == mirror[10]
    assert feet[10][2] == foot[130]
    assert feet[10][5] == mirror[250]


def test_phases_round_half_up(foot):
    # 0.5° and 1.5° are each half a sample past one at 360 angles.
    assert measures.beest_feet(foot, [0.5])[0][0] == foot[1]
    assert measures.beest_feet(foot, [1.5])[0][0] == foot[2]


def test_phases_round_half_up_at_180_angles():
    foot = geometry.trace_leg(geometry.HOLY).foot
    assert measures.beest_feet(foot, [13])[0][0] == foot[7]


def test_throw_steps():
    assert measures.throw_steps([0, 120, 240], 180) == [0, 60, 120]
    assert measures.throw_steps([13, 359.9, -120], 180) == [7, 0, 120]
    assert measures.throw_steps([0.5, 1.5], 360) == [1, 2]


def test_phase_order_does_not_matter(foot):
    assert (measures.beest_measures(foot, [0, -120, 120])
            == measures.beest_measures(foot, [0, 120, 240]))


def test_mirror_needs_even_angles():
    with pytest.raises(ValueError):
        measures.mirrored([(0, 0)] * 181)


def test_distance_converges():
    def distance(n):
        return measures.beest_measures(geometry.trace_leg(geometry.HOLY, n=n).foot, [0, 120, 240]).distance
    assert distance(180) == pytest.approx(distance(720), rel=0.005)


def test_foot_measures_flat_foot():
    # A foot sliding along a flat bottom then lifting 10: down for half the turn over 30 of travel.
    foot = [(x, 0.0) for x in range(0, 31, 2)] + [(x, 10.0) for x in range(30, 0, -2)]
    m = measures.foot_measures(foot, 1.0)
    assert m.step_height == 10
    assert m.stride == 30
    assert m.time_down == pytest.approx(16 / 31)


def jansen_feet(phases):
    """Every foot of a Jansen beest in mm, at 180 angles."""
    mm = {name: geometry.HOLY[name] * MM_PER_UNIT for name in geometry.LENGTH_NAMES}
    return measures.beest_feet(geometry.trace_leg(mm).foot, phases)


def test_one_pair_tips():
    assert measures.tips(jansen_feet([0]), 1.0)


def test_three_pairs_stay_up():
    assert not measures.tips(jansen_feet([0, 120, 240]), 1.0)


def test_two_pairs_stay_up_only_with_room():
    # At some angles one foot carries the body alone, 0.65 mm below the foot that would balance it.
    feet = jansen_feet([0, 180])
    assert not measures.tips(feet, 1.0)
    assert measures.tips(feet, 0.5)


def test_centre_of_mass_moves():
    feet = jansen_feet([0, 120, 240])
    assert not measures.tips(feet, 1.0, com_x=20.0)
    assert measures.tips(feet, 1.0, com_x=100.0)
    assert measures.tips(feet, 1.0, com_x=-100.0)


def test_only_feet_near_the_lowest_support():
    feet = [[(-10.0, 0.0), (10.0, 2.0)]]
    assert measures.tips(feet, 1.0)
    assert not measures.tips(feet, 2.0)
    # Standing at one angle is not enough.
    assert measures.tips([[(-10.0, 0.0), (10.0, 0.5)], [(-10.0, 0.0), (10.0, 2.0)]], 1.0)


def test_a_foot_under_the_centre_of_mass_holds_it_up():
    assert not measures.tips([[(0.0, 0.0), (30.0, 5.0)]], 1.0)
    assert not measures.tips([[(-10.0, 0.0), (0.0, 0.0)]], 0.0)
    assert measures.tips([[(1e-9, 0.0)]], 1.0)
