"""Whole beests built from a leg design, in mm."""
import pytest

from beest.geometry import HOLY, LENGTH_NAMES
from beest.leg import (LENGTH_BOUNDS, MM_PER_UNIT, STICKS, Layout, jansen_lengths, leg_from)

MEASURES = ("stride", "step_height", "time_down", "distance", "bob", "flatness")


def with_length(name, value):
    genes = jansen_lengths()
    genes[LENGTH_NAMES.index(name)] = value
    return genes


def test_jansen_lengths_in_mm():
    genes = jansen_lengths()
    assert len(genes) == 13
    assert genes[LENGTH_NAMES.index("h")] == pytest.approx(78.84)
    assert genes == pytest.approx([HOLY[name] * MM_PER_UNIT for name in LENGTH_NAMES])


def test_jansen_leg():
    leg = leg_from(jansen_lengths())
    assert not leg.jams
    assert leg.jam_reason is None
    assert leg.fits
    assert leg.layout == Layout(3, (0, 120, 240))
    assert leg.distance == pytest.approx(141.83 * MM_PER_UNIT, rel=0.005)
    assert leg.bob == pytest.approx(0.08 * MM_PER_UNIT, abs=0.03)
    assert leg.flatness == leg.bob
    assert leg.step_height == pytest.approx(22.46 * MM_PER_UNIT, abs=0.1)
    assert leg.closest_to_jam == pytest.approx(1.19 * MM_PER_UNIT, abs=0.05)
    assert leg.tips is None
    assert leg.normalised == {}


def test_jammed_leg_measures_zero():
    # Jansen's crank 10% longer: f and g cannot meet part-way round.
    leg = leg_from(with_length("m", 16.5 * MM_PER_UNIT))
    assert leg.jams
    assert "f and g" in leg.jam_reason
    assert leg.fits
    for name in MEASURES:
        assert getattr(leg, name) == 0.0
    assert leg.closest_to_jam < 0


def test_layouts():
    assert Layout().phases == (0, 120, 240)
    assert Layout(2).phases == (0, 180)
    assert Layout(4).phases == (0, 90, 180, 270)
    assert Layout(1, [0]) == Layout(1, (0.0,))
    with pytest.raises(ValueError):
        Layout(2, (0, 120, 240))
    with pytest.raises(ValueError):
        Layout(0)
    for bad in (5, 2.0, True):
        with pytest.raises(ValueError):
            Layout(bad)
    with pytest.raises(ValueError):
        Layout(2, (0, float("nan")))


def test_pairs_change_the_beest():
    one = leg_from(jansen_lengths(), Layout(1))
    three = leg_from(jansen_lengths())
    assert one.distance == pytest.approx(125.96 * MM_PER_UNIT, rel=0.01)
    assert one.bob > three.bob
    assert one.stride == three.stride


def test_tolerance_changes_the_foot():
    tight = leg_from(jansen_lengths(), tol=0.5)
    loose = leg_from(jansen_lengths(), tol=4)
    assert tight.stride < loose.stride
    assert tight.time_down < loose.time_down
    assert tight.distance == loose.distance


def test_margin_counts_near_misses():
    # Jansen's k and c come within 1.43 mm of folding flat.
    assert leg_from(jansen_lengths(), margin=2.0).jams
    assert not leg_from(jansen_lengths(), margin=1.0).jams


@pytest.mark.parametrize("name", STICKS)
def test_sticks_must_fit(name):
    low, high = LENGTH_BOUNDS[name]
    assert leg_from(with_length(name, low)).fits
    assert leg_from(with_length(name, high)).fits
    assert not leg_from(with_length(name, low - 0.1)).fits
    assert not leg_from(with_length(name, high + 0.1)).fits


def test_frame_offsets_are_not_sticks():
    assert set(STICKS) == set(LENGTH_NAMES) - {"a", "l"}
    assert LENGTH_BOUNDS["l"] == (-30, 30)
    assert leg_from(with_length("a", 120)).fits
    assert leg_from(with_length("l", -40)).fits


def test_leg_keeps_its_own_genes():
    genes = jansen_lengths()
    leg = leg_from(genes)
    genes[0] = 99
    assert leg.genes == pytest.approx(jansen_lengths())


def test_leg_from_needs_13_lengths():
    with pytest.raises(ValueError, match="13 lengths"):
        leg_from(jansen_lengths()[:12])


def test_lengths_must_be_numbers():
    with pytest.raises(ValueError, match="length e"):
        leg_from(with_length("e", float("nan")))


def test_angles_must_be_even():
    assert not leg_from(jansen_lengths(), n=360).jams
    # A jammed leg is refused too, though it never reaches the mirror.
    for genes in (jansen_lengths(), with_length("m", 16.5 * MM_PER_UNIT)):
        with pytest.raises(ValueError, match="even"):
            leg_from(genes, n=181)


def test_tolerance_cannot_be_negative():
    assert leg_from(jansen_lengths(), tol=0).stride == 0
    for bad in (-0.1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="down tolerance"):
            leg_from(jansen_lengths(), tol=bad)


def test_repr_leaves_out_the_trace():
    assert "joints" not in repr(leg_from(jansen_lengths()))
