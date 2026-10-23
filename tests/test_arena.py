"""Whole beests walking in the physics arena."""
import math
import random

import pytest

from beest.arena import (FOOT_RADIUS_MM, STEPS_PER_TURN, STICK_ENDS, TIP_ANGLE_DEG, Arena,
                         ArenaResult, run, starting_legs)
from beest.geometry import DRAW_ANGLES, LENGTH_NAMES, rule_joints, trace_leg
from beest.ga import random_genes
from beest.leg import MM_PER_UNIT, Layout, jansen_lengths, leg_from

# A working leg whose J5 and F sit on the other branch from Al's rule at 120°.
SWITCHING = [50.5, 51.8, 38.2, 52.3, 72.2, 38.2, 54.3, 86.2, 45.5, 75.5, 58.3, 8.4, 20.4]


def with_length(name, value):
    genes = jansen_lengths()
    genes[LENGTH_NAMES.index(name)] = value
    return genes


@pytest.fixture(scope="module")
def jansen_walk():
    return run(jansen_lengths(), Layout(3), turns=5)


def test_jansen_walks_left(jansen_walk):
    assert isinstance(jansen_walk, ArenaResult)
    assert not jansen_walk.tipped
    assert jansen_walk.tipped_at is None
    assert jansen_walk.turns == 5
    assert 138 * MM_PER_UNIT <= jansen_walk.distance <= 148 * MM_PER_UNIT
    assert jansen_walk.travel == pytest.approx(5 * jansen_walk.distance)
    assert jansen_walk.max_tilt < 5


def test_one_pair_tips():
    result = run(jansen_lengths(), Layout(1), turns=10)
    assert result.tipped
    assert 0 <= result.tipped_at < 1
    # It ends on its back; leaning is measured from level, whichever way round it went.
    assert TIP_ANGLE_DEG < result.max_tilt <= 180


def test_jammed_leg_is_refused():
    # Jansen's crank 10% longer: f and g cannot meet part-way round.
    with pytest.raises(ValueError, match="f and g cannot meet"):
        Arena(with_length("m", 16.5 * MM_PER_UNIT))


@pytest.mark.parametrize("genes", [jansen_lengths()[:12], with_length("c", math.nan),
                                   with_length("j", 0.0)], ids=["short", "nan", "zero"])
def test_unbuildable_genes_are_refused(genes):
    with pytest.raises(ValueError):
        Arena(genes)


def test_every_working_leg_can_be_built():
    # Whatever leg_from counts as working, at any throw angles.
    random.seed(4)
    working = 0
    for _ in range(300):
        genes = random_genes()
        if not leg_from(genes).jams:
            working += 1
            phases = tuple(random.uniform(0, 360) for _ in range(3))
            assert len(starting_legs(genes, Layout(3, phases))) == 6
    assert working > 50


def test_results_repeat_exactly():
    assert run(jansen_lengths(), turns=1) == run(jansen_lengths(), turns=1)


def test_frame_by_frame_matches_run():
    arena = Arena(jansen_lengths())
    for _ in range(STEPS_PER_TURN // 10):
        arena.step(10)
    assert arena.turns == 1
    assert arena.result() == run(jansen_lengths(), turns=1)
    for bad in (-1, 2.5, True):
        with pytest.raises(ValueError):
            arena.step(bad)
    with pytest.raises(ValueError):
        arena.run(-1)


def test_crank_turns_anticlockwise():
    arena = Arena(jansen_lengths())
    arena.step(STEPS_PER_TURN // 4)
    crank = arena.legs()[0]
    x, y = crank["C"][0] - crank["O"][0], crank["C"][1] - crank["O"][1]
    # θ starts at 0 and has turned a quarter, less however far the body has leant.
    assert math.degrees(math.atan2(y, x)) == pytest.approx(90, abs=arena.max_tilt + 1)


def test_starting_pose_follows_the_tracked_leg():
    lengths = dict(zip(LENGTH_NAMES, SWITCHING))
    tracked = trace_leg(lengths, DRAW_ANGLES).joints[120]
    ruled = rule_joints(lengths, math.radians(120))
    legs = starting_legs(SWITCHING, Layout(3))
    assert len(legs) == 6
    for name in tracked:
        assert legs[2][name] == pytest.approx(tracked[name], abs=1e-9)
    assert math.dist(legs[2]["J5"], ruled["J5"]) > 10


def test_starting_pose_between_sampled_angles():
    genes = jansen_lengths()
    lengths = dict(zip(LENGTH_NAMES, genes))
    legs = starting_legs(genes, Layout(2, (0, 97.3)))
    for leg in legs:
        for name, (p, q) in STICK_ENDS.items():
            assert math.dist(leg[p], leg[q]) == pytest.approx(lengths[name], abs=1e-9)
    # The mirror of the throw at 97.3° is the original leg at 180° − 97.3°.
    mirror = trace_leg(lengths, n=3600).joints[827]
    assert legs[3]["F"] == pytest.approx((-mirror["F"][0], mirror["F"][1]), abs=1e-9)


def test_sticks_keep_their_lengths_while_walking():
    genes = jansen_lengths()
    lengths = dict(zip(LENGTH_NAMES, genes))
    arena = Arena(genes)
    arena.step(STEPS_PER_TURN)
    for leg in arena.legs():
        for name, (p, q) in STICK_ENDS.items():
            assert math.dist(leg[p], leg[q]) == pytest.approx(lengths[name], abs=0.5)


def test_feet_stand_on_the_ground():
    arena = Arena(jansen_lengths())
    arena.step(STEPS_PER_TURN // 3)
    lowest = min(leg["F"][1] for leg in arena.legs())
    assert lowest == pytest.approx(FOOT_RADIUS_MM, abs=0.5)
