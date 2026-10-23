"""Ingredients, weights, the three normalisations and flips (the settings route)."""
import json
import math

import pytest

from beest.fitness import (INGREDIENTS, LIMITS_FILE, NORMALISATIONS, FitnessSettings, fixed_limits,
                           ingredient_values, normalise, settings_fitness)
from beest.geometry import LENGTH_NAMES
from beest.leg import MM_PER_UNIT, jansen_lengths, leg_from

NO_FLIPS = {name: False for name in INGREDIENTS}


@pytest.fixture(scope="module")
def jansen():
    return leg_from(jansen_lengths())


def stretched(scale):
    """Jansen's leg with every length scaled, which scales every distance with it."""
    return leg_from([x * scale for x in jansen_lengths()])


def jammed():
    genes = jansen_lengths()
    genes[LENGTH_NAMES.index("m")] = 16.5 * MM_PER_UNIT
    return leg_from(genes)


def only(name, **settings):
    return FitnessSettings(weights={name: 1.0}, **settings)


def test_ingredients():
    assert INGREDIENTS == {"distance": True, "stride": True, "step_height": True,
                           "time_down": True, "flatness": False}


def test_defaults():
    settings = FitnessSettings()
    assert settings.normalisation == "jansen"
    assert settings.weight("distance") == 1
    assert settings.weight("step_height") == 0.5
    assert all(settings.weight(name) == 0 for name in ("stride", "time_down", "flatness"))
    assert settings.flipped("flatness")
    assert not any(settings.flipped(name) for name in INGREDIENTS if name != "flatness")


def test_jansen_normalises_to_one(jansen):
    leg = leg_from(jansen_lengths())
    normalise([leg], FitnessSettings(), jansen)
    assert leg.normalised == pytest.approx({name: 1.0 for name in INGREDIENTS})
    assert settings_fitness(FitnessSettings())(leg) == pytest.approx(1.0)


def test_jansen_mode_divides(jansen):
    big = stretched(1.1)
    normalise([big], FitnessSettings(), jansen)
    assert big.normalised["distance"] == pytest.approx(1.1, rel=0.01)
    assert big.normalised["time_down"] == pytest.approx(big.time_down / jansen.time_down)


def test_generation_mode_all_equal(jansen):
    legs = [leg_from(jansen_lengths()) for _ in range(4)]
    settings = FitnessSettings(normalisation="generation")
    normalise(legs, settings, jansen)
    for leg in legs:
        assert leg.normalised == {name: 0.5 for name in INGREDIENTS}
        assert settings_fitness(settings)(leg) == 0.5


def test_generation_mode_spans_zero_to_one(jansen):
    legs = [stretched(0.9), stretched(1.0), stretched(1.1)]
    normalise(legs, FitnessSettings(normalisation="generation"), jansen)
    assert [leg.normalised["distance"] for leg in legs] == pytest.approx([0, 0.5, 1], abs=0.02)


def test_generation_mode_leaves_out_jammed_legs(jansen):
    legs = [stretched(1.0), jammed(), stretched(1.1)]
    normalise(legs, FitnessSettings(normalisation="generation"), jansen)
    assert legs[0].normalised["distance"] == 0
    assert legs[2].normalised["distance"] == 1
    assert legs[1].normalised == {name: 0.0 for name in INGREDIENTS}


def test_single_working_leg_is_half(jansen):
    legs = [jammed(), stretched(1.05)]
    normalise(legs, FitnessSettings(normalisation="generation"), jansen)
    assert legs[1].normalised == {name: 0.5 for name in INGREDIENTS}


@pytest.mark.parametrize("normalisation", NORMALISATIONS)
def test_all_jammed_scores_zero(jansen, normalisation):
    legs = [jammed() for _ in range(3)]
    settings = FitnessSettings(normalisation=normalisation)
    normalise(legs, settings, jansen)
    for leg in legs:
        assert leg.normalised == {name: 0.0 for name in INGREDIENTS}
        assert settings_fitness(settings)(leg) == 0.0


def test_jammed_leg_scores_zero_even_flipped(jansen):
    # A jammed leg's bob is 0.0, which flipped would otherwise look perfect.
    leg = jammed()
    settings = only("flatness")
    normalise([leg], settings, jansen)
    assert settings_fitness(settings)(leg) == 0.0


def test_flip(jansen):
    big = stretched(1.1)
    flipped = only("distance", flip={"distance": True})
    normalise([big], flipped, jansen)
    assert settings_fitness(flipped)(big) == pytest.approx(1 - big.normalised["distance"])
    assert settings_fitness(only("distance"))(big) == pytest.approx(big.normalised["distance"])
    # Jansen's own flatness normalises to 1, so flipped it scores 0.
    leg = leg_from(jansen_lengths())
    normalise([leg], only("flatness"), jansen)
    assert settings_fitness(only("flatness"))(leg) == pytest.approx(0.0)
    assert settings_fitness(only("flatness", flip=NO_FLIPS))(leg) == pytest.approx(1.0)


def test_limits_clip(jansen):
    legs = [stretched(0.9), stretched(1.0), stretched(1.1)]
    middle = legs[1].distance
    settings = FitnessSettings(normalisation="limits",
                               limits={"distance": (middle - 1, middle + 1)})
    normalise(legs, settings, jansen)
    assert [leg.normalised["distance"] for leg in legs] == [0.0, pytest.approx(0.5), 1.0]
    assert all(0 <= value <= 1 for leg in legs for value in leg.normalised.values())


def test_limits_equal_or_reversed(jansen):
    legs = [stretched(0.9), stretched(1.0), stretched(1.1)]
    middle = legs[1].distance
    normalise(legs, FitnessSettings(normalisation="limits", limits={"distance": (middle, middle)}),
              jansen)
    assert [leg.normalised["distance"] for leg in legs] == [0.0, 0.5, 1.0]
    normalise(legs, FitnessSettings(normalisation="limits",
                                    limits={"distance": (middle + 1, middle - 1)}), jansen)
    assert [leg.normalised["distance"] for leg in legs] == [0.0, pytest.approx(0.5), 1.0]


def test_limits_default_to_the_survey(jansen):
    settings = FitnessSettings(normalisation="limits")
    leg = leg_from(jansen_lengths())
    normalise([leg], settings, jansen)
    low, high = fixed_limits()["stride"]
    assert leg.normalised["stride"] == pytest.approx(min(max((leg.stride - low) / (high - low), 0), 1))


def test_limits_file_covers_every_ingredient():
    data = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
    assert data["legs"] == 2000
    assert data["seed"] == 1
    limits = fixed_limits()
    assert set(limits) == set(INGREDIENTS)
    for low, high in limits.values():
        assert math.isfinite(low) and math.isfinite(high)
        assert low < high


def test_fixed_limits_is_a_fresh_copy():
    fixed_limits()["distance"] = (0, 0)
    assert fixed_limits()["distance"] != (0, 0)


def test_weighted_mean(jansen):
    big = stretched(1.1)
    settings = FitnessSettings(weights={"distance": 3, "time_down": 1}, flip=NO_FLIPS)
    normalise([big], settings, jansen)
    expected = (3 * big.normalised["distance"] + big.normalised["time_down"]) / 4
    assert settings_fitness(settings)(big) == pytest.approx(expected)


def test_no_weights_scores_zero(jansen):
    settings = FitnessSettings(weights={})
    leg = leg_from(jansen_lengths())
    normalise([leg], settings, jansen)
    assert settings_fitness(settings)(leg) == 0.0


@pytest.mark.parametrize("bad", [
    {"weights": {"speed": 1}},
    {"weights": {"distance": -1}},
    {"weights": {"distance": math.nan}},
    {"flip": {"speed": True}},
    {"flip": {"distance": "false"}},
    {"limits": {"speed": (0, 1)}},
    {"limits": {"distance": (-math.inf, 100)}},
    {"limits": {"distance": (0,)}},
    {"normalisation": "scaling"},
])
def test_bad_settings_are_refused(bad):
    with pytest.raises(ValueError):
        FitnessSettings(**bad)


def test_ingredient_values(jansen):
    values = ingredient_values(jansen)
    assert list(values) == list(INGREDIENTS)
    assert values["distance"] == jansen.distance
    assert values["flatness"] == jansen.bob
