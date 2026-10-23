"""The races (brief §4) and their courses in the physics arena."""
import pymunk
import pytest

from beest.arena import (DISTANCE_TURNS, MAX_RACE_TURNS, PENCIL_COUNT, PENCIL_DIAMETER_MM,
                         PENCIL_SPACING_MM, RACES, TIP_ANGLE_DEG, TOWEL_BUMP_MM,
                         TOWEL_BUMP_SPACING_MM, TOWEL_LENGTH_MM, Arena, Race, fell, race)
from beest.leg import MM_PER_UNIT, Layout, jansen_lengths


@pytest.fixture(scope="module")
def jansen_races():
    return {name: race(jansen_lengths(), Layout(3), name) for name in RACES}


def test_jansen_finishes_every_race(jansen_races):
    for name, result in jansen_races.items():
        assert result.finished, result.message
        assert result.race == name
    distance = jansen_races["distance"]
    assert distance.turns == DISTANCE_TURNS
    assert 138 * MM_PER_UNIT <= distance.travel / DISTANCE_TURNS <= 148 * MM_PER_UNIT
    assert distance.message == f"It walked {distance.travel:.0f} mm in {DISTANCE_TURNS} turns."
    for name in ("pencils", "towel"):
        crossed = jansen_races[name]
        assert 1 < crossed.turns < MAX_RACE_TURNS
        assert crossed.message == f"It crossed the {name} in {crossed.turns:.1f} turns."


def test_beest_that_tips_does_not_finish():
    result = race(jansen_lengths(), Layout(1), "pencils")
    assert result.outcome == "fell"
    assert not result.finished
    assert result.turns < 1
    assert result.message == "It fell over after 0.3 turns, so it did not finish."


def test_race_gives_up_after_its_most_turns():
    result = race(jansen_lengths(), Layout(3), "towel", max_turns=1)
    assert result.outcome == "gave up"
    assert result.turns == 1
    assert result.message == "It was not across the towel after 1 turn, so it did not finish."


def test_race_run_in_frames_matches_one_go(jansen_races):
    stepped = Race(jansen_lengths(), Layout(3), "pencils")
    while not stepped.done:
        stepped.step(7)
    assert stepped.result == jansen_races["pencils"]
    # A decided race goes no further.
    stepped.step(100)
    assert stepped.arena.turns == stepped.result.turns


def test_courses_lie_ahead_of_the_beest():
    radius = PENCIL_DIAMETER_MM / 2
    pencils = Arena(jansen_lengths(), Layout(3), "pencils")
    feet = [leg["F"][0] for leg in pencils.legs()]
    centres = pencils.course.pencils
    assert len(centres) == PENCIL_COUNT
    assert all(y == radius for _, y in centres)
    assert [a[0] - b[0] for a, b in zip(centres, centres[1:])] == pytest.approx(
        [PENCIL_SPACING_MM] * (PENCIL_COUNT - 1))
    assert centres[0][0] + radius < min(feet)
    assert pencils.course.finish_x == centres[-1][0] - radius

    towel = Arena(jansen_lengths(), Layout(3), "towel")
    left, right = towel.course.towel
    assert right - left == TOWEL_LENGTH_MM
    assert right < min(leg["F"][0] for leg in towel.legs())
    surface = towel.course.surface
    assert surface[0] == (right, 0.0)
    assert surface[-1] == pytest.approx((left, 0.0))
    assert min(y for _, y in surface) == pytest.approx(0)
    peaks = [x for x, y in surface if y == pytest.approx(TOWEL_BUMP_MM)]
    assert len(peaks) == TOWEL_LENGTH_MM / TOWEL_BUMP_SPACING_MM
    assert [a - b for a, b in zip(peaks, peaks[1:])] == pytest.approx(
        [TOWEL_BUMP_SPACING_MM] * (len(peaks) - 1))
    assert towel.course.finish_x == left

    flat = Arena(jansen_lengths()).course
    assert (flat.pencils, flat.towel, flat.surface, flat.finish_x) == ((), None, (), None)


def test_unknown_race_or_course_is_refused():
    with pytest.raises(ValueError, match="no race called 'sprint'"):
        Race(jansen_lengths(), race="sprint")
    with pytest.raises(ValueError, match="no course called 'sand'"):
        Arena(jansen_lengths(), course="sand")
    with pytest.raises(ValueError):
        Race(jansen_lengths()).step(2.5)


def test_chassis_on_an_obstacle_has_tipped():
    arena = Arena(jansen_lengths(), Layout(3), "pencils")
    # Something fixed rising to just under the chassis, as a fallen beest's chassis lands on.
    outline = arena.chassis_outline()
    left, right = min(x for x, _ in outline), max(x for x, _ in outline)
    bottom = min(y for _, y in outline)
    space = arena._space
    space.add(pymunk.Poly(space.static_body, [(left, 0), (right, 0), (right, bottom + 0.5),
                                              (left, bottom + 0.5)]))
    arena.step(10)
    assert arena.tipped
    assert arena.max_tilt < TIP_ANGLE_DEG


def test_falling_is_put_in_words():
    assert fell(0) == "before the crank started"
    assert fell(0.02) == "as the crank started"
    assert fell(2.34) == "after 2.3 turns"
