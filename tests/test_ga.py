"""The GA with the slides' names, its rivals (hill climbing and random search) and the code route."""
import json
import math
import pickle
import random
import traceback
from dataclasses import replace
from fractions import Fraction

import pytest

from beest import ga
from beest.fitness import FitnessSettings, normalise
from beest.geometry import LENGTH_NAMES
from beest.leg import LENGTH_BOUNDS, PAIRS_BOUNDS, RANDOM_SPREAD, Layout, jansen_lengths, leg_from
from beest.student_default import EDITOR, SOURCE, student_functions

SMALL = {"pop": 10, "generations": 6}


def reports(settings, fitness_fn=None, mutate_fn=None):
    seen = []
    ga.run(settings, fitness_fn, mutate_fn, seen.append)
    return seen


def in_bounds(genes):
    return all(LENGTH_BOUNDS[name][0] <= x <= LENGTH_BOUNDS[name][1]
               for name, x in zip(LENGTH_NAMES, genes))


def test_slide_constants():
    assert (ga.POP_SIZE, ga.GENERATIONS, ga.ELITE, ga.RATE) == (30, 40, 2, 0.2)
    assert (ga.MUTATION_SIZE, ga.TOURNAMENT) == (3.0, 3)


def test_random_genes_near_jansen():
    random.seed(1)
    for _ in range(200):
        genes = ga.random_genes()
        assert len(genes) == 13
        assert in_bounds(genes)
        for x, j in zip(genes, jansen_lengths()):
            assert abs(x - j) <= abs(j) * RANDOM_SPREAD + 1e-9


def test_clamp():
    assert ga.clamp([-100.0] * 13) == [-30.0 if name == "l" else 10.0 for name in LENGTH_NAMES]
    assert ga.clamp([500.0] * 13) == [30.0 if name == "l" else 104.0 for name in LENGTH_NAMES]


def test_mutate_rate_zero_is_identity():
    random.seed(1)
    genes = jansen_lengths()
    child = ga.mutate(genes, 0)
    assert child == genes
    assert child is not genes


def test_mutate_rate_one_changes_every_length():
    random.seed(1)
    genes = jansen_lengths()
    child = ga.mutate(genes, 1)
    assert all(x != j for x, j in zip(child, genes))
    assert genes == jansen_lengths()


def test_mutate_clamps():
    random.seed(1)
    for _ in range(50):
        assert in_bounds(ga.mutate(jansen_lengths(), 1, size=1000))


def test_crossover_kinds():
    random.seed(1)
    a, b = [float(k) for k in range(13)], [float(100 + k) for k in range(13)]
    index = {name: k for k, name in enumerate(LENGTH_NAMES)}
    mixed = False
    for _ in range(50):
        uniform = ga.crossover(a, b, "uniform")
        assert all(x in (p, q) for x, p, q in zip(uniform, a, b))
        mixed |= uniform != a and uniform != b

        blend = ga.crossover(a, b, "blend")
        assert all(p <= x <= q for x, p, q in zip(blend, a, b))

        triangles = ga.crossover(a, b, "triangles")
        assert all(x in (p, q) for x, p, q in zip(triangles, a, b))
        for team in ("bde", "ghi"):
            assert len({triangles[index[name]] >= 100 for name in team}) == 1

        none = ga.crossover(a, b, "none")
        assert none == a and none is not a
    assert mixed
    with pytest.raises(ValueError):
        ga.crossover(a, b, "swap")


def test_tournament_prefers_better():
    random.seed(1)
    population = [[float(k)] for k in range(10)]
    scores = list(range(10))
    picks = [ga.select(population, scores)[0] for _ in range(1000)]
    # The best of three draws from 0-9 averages 6.975; a random pick averages 4.5.
    assert sum(picks) / len(picks) > 6.5
    assert picks.count(9) > 5 * picks.count(0)


def test_select_works_on_tiny_populations():
    random.seed(1)
    assert ga.select([[1.0]], [0.0]) == [1.0]


def test_best():
    assert ga.best([[1.0], [2.0], [3.0], [4.0]], [0.5, 2, 2, 1]) == ([2.0], 2)


def test_mutate_layout():
    random.seed(1)
    layouts = [Layout()]
    for _ in range(300):
        layouts.append(ga.mutate_layout(layouts[-1], 0.2))
    assert {layout.pairs for layout in layouts} == set(range(PAIRS_BOUNDS[0], PAIRS_BOUNDS[1] + 1))
    assert all(layout.phases[0] == 0 for layout in layouts)
    assert all(0 <= p < 360 for layout in layouts for p in layout.phases)
    assert any(layout.phases != Layout(layout.pairs).phases for layout in layouts)
    assert ga.mutate_layout(Layout(2, (0, 170)), 0) == Layout(2, (0, 170))


def test_default_run_is_the_slides_ga():
    seen = reports(ga.RunSettings(generations=3))
    assert [r.generation for r in seen] == [0, 1, 2]
    assert [r.evaluations for r in seen] == [30, 60, 90]


def test_run_repeats_with_seed():
    first = reports(ga.RunSettings(seed=7, **SMALL))
    again = reports(ga.RunSettings(seed=7, **SMALL))
    other = reports(ga.RunSettings(seed=8, **SMALL))
    assert first == again
    assert first != other


def test_budget_counts_evaluations():
    seen = reports(ga.RunSettings(pop=30, budget=100))
    assert [r.evaluations for r in seen] == [30, 60, 90, 100]

    seen = reports(ga.RunSettings(preset="random", pop=30, budget=75, generations=1))
    assert [r.evaluations for r in seen] == [30, 60, 75]

    seen = reports(ga.RunSettings(preset="hill", budget=50))
    assert [r.evaluations for r in seen] == list(range(1, 51))

    # Per-generation normalisation scores the parent again beside each child, and random
    # search's best so far beside each generation.
    together = FitnessSettings(normalisation="generation")
    seen = reports(ga.RunSettings(preset="hill", budget=10, fitness=together))
    assert [r.evaluations for r in seen] == [1, 3, 5, 7, 9]
    seen = reports(ga.RunSettings(preset="random", pop=10, budget=40, fitness=together))
    assert [r.evaluations for r in seen] == [10, 21, 32, 40]

    seen = reports(ga.RunSettings(pop=30, budget=12))
    assert [r.evaluations for r in seen] == [12]


def test_evaluations_count_fitness_calls():
    calls = []

    def fitness(leg):
        calls.append(leg)
        return 0.0 if leg.jams else leg.distance

    for settings in (ga.RunSettings(budget=95), ga.RunSettings(preset="hill", budget=40),
                     ga.RunSettings(preset="random", pop=20, budget=50)):
        calls.clear()
        final = ga.run(settings, fitness)
        assert final.evaluations == len(calls) == settings.budget


def test_hill_and_random_presets():
    # A score that only the crank length m sets, best at 30 mm, whether or not the leg jams.
    def near_30(leg):
        return -abs(leg.genes[-1] - 30)

    hill = reports(ga.RunSettings(preset="hill", generations=150, seed=3), near_30)
    assert len(hill) == 150
    assert hill[-1].evaluations == 150
    assert all(later.best_score >= earlier.best_score for earlier, later in zip(hill, hill[1:]))
    assert hill[-1].best_genes[-1] == pytest.approx(30, abs=1.5)

    rand = reports(ga.RunSettings(preset="random", pop=10, generations=8, seed=3))
    assert [r.evaluations for r in rand] == list(range(10, 90, 10))
    assert all(later.best_score >= earlier.best_score for earlier, later in zip(rand, rand[1:]))
    assert all(r.best_layout == Layout() for r in rand)


def test_random_search_keeps_its_best_under_generation_normalisation():
    # With distance alone, both normalisations rank the same beests the same way.
    absolute = FitnessSettings(weights={"distance": 1.0})
    relative = FitnessSettings(weights={"distance": 1.0}, normalisation="generation")
    by_jansen = reports(ga.RunSettings(preset="random", seed=3, fitness=absolute, **SMALL))
    by_generation = reports(ga.RunSettings(preset="random", seed=3, fitness=relative, **SMALL))
    found = [r.best_values["distance"] for r in by_generation]
    assert found == sorted(found)
    assert by_generation[-1].best_genes == by_jansen[-1].best_genes


def test_random_search_mean_leaves_out_its_best_so_far():
    calls = []

    def crank(leg):
        calls.append(leg.genes[-1])
        return leg.genes[-1]

    together = FitnessSettings(normalisation="generation")
    seen = reports(ga.RunSettings(preset="random", pop=10, generations=3, fitness=together), crank)
    # Each later generation scores the best so far first, then ten newcomers.
    assert len(calls) == 10 + 11 + 11
    assert seen[1].mean_score == pytest.approx(sum(calls[11:21]) / 10)
    assert seen[2].mean_score == pytest.approx(sum(calls[22:32]) / 10)


def test_ga_improves():
    seen = reports(ga.RunSettings(generations=21, seed=1))
    assert seen[20].best_score > seen[0].best_score


def test_elitism_keeps_the_best():
    seen = reports(ga.RunSettings(seed=2, **SMALL))
    assert all(later.best_score >= earlier.best_score for earlier, later in zip(seen, seen[1:]))


def test_report_matches_its_best_beest():
    for preset in ga.PRESETS:
        final = ga.run(ga.RunSettings(preset=preset, seed=4, **SMALL))
        leg = leg_from(final.best_genes, final.best_layout)
        assert final.best_values["distance"] == leg.distance
        assert final.best_values["flatness"] == leg.bob
        assert (final.best_jams, final.best_fits) == (leg.jams, leg.fits)


def scored(settings, record=lambda leg: leg):
    """Every beest the run scores, in order, as `record` gives it, and the run's reports."""
    calls = []

    def fitness(leg):
        calls.append(record(leg))
        return leg.distance

    return calls, reports(settings, fitness)


def test_random_start_is_the_default():
    assert ga.RunSettings().start == "random"
    assert reports(ga.RunSettings(start="random", **SMALL)) == reports(ga.RunSettings(**SMALL))


def test_turning_start_scores_only_beests_that_turn():
    calls, seen = scored(ga.RunSettings(start="turning", pop=20, generations=1),
                         lambda leg: leg.jams)
    # Checking for jams scores nothing.
    assert seen[-1].evaluations == len(calls) == 20
    assert not any(calls)
    # A random start jams most of the time.
    calls, _ = scored(ga.RunSettings(pop=20, generations=1), lambda leg: leg.jams)
    assert sum(calls) > 10


def test_turning_start_gives_up_plainly():
    # No leg keeps every pair of links 50 mm from failing to meet.
    calls = []
    with pytest.raises(ga.StartError, match=f"{ga.START_TRIES} tries"):
        ga.run(ga.RunSettings(start="turning", margin=50, **SMALL), calls.append)
    assert calls == []


@pytest.mark.parametrize("start", ["jansen", "design"])
def test_leg_and_mutants_start(start):
    design = [x * 1.05 for x in jansen_lengths()]
    leg = jansen_lengths() if start == "jansen" else design
    settings = ga.RunSettings(start=start, start_genes=design, pop=10, generations=1, rate=0.5,
                              size=2.0, mask=frozenset("bcd"))
    calls, _ = scored(settings, lambda leg: list(leg.genes))
    assert calls[0] == leg
    for genes in calls[1:]:
        assert in_bounds(genes)
        # Lengths outside the mask keep the leg's own.
        assert [x for name, x in zip(LENGTH_NAMES, genes) if name not in "bcd"] == [
            x for name, x in zip(LENGTH_NAMES, leg) if name not in "bcd"]
    assert any(genes != leg for genes in calls[1:])
    # Mutated with the engine's mutate at the run's rate and size, so a rate of 0 copies the leg.
    calls, _ = scored(replace(settings, rate=0), lambda leg: list(leg.genes))
    assert all(genes == leg for genes in calls)


def test_start_repeats_with_seed():
    for start in ga.STARTS:
        settings = ga.RunSettings(start=start, start_genes=jansen_lengths(), seed=5, **SMALL)
        assert reports(settings) == reports(settings)


def test_hill_climbing_starts_from_the_start():
    seen = reports(ga.RunSettings(preset="hill", start="jansen", **SMALL))
    assert seen[0].best_genes == jansen_lengths()
    _, seen = scored(ga.RunSettings(preset="hill", start="turning", **SMALL))
    assert not seen[0].best_jams


def test_random_search_draws_as_it_starts():
    # Every generation's newcomers are made the way the first ones were.
    calls, _ = scored(ga.RunSettings(preset="random", start="turning", pop=8, generations=4),
                      lambda leg: leg.jams)
    assert len(calls) == 32 and not any(calls)
    calls, _ = scored(ga.RunSettings(preset="random", start="jansen", rate=0, pop=8,
                                     generations=4), lambda leg: list(leg.genes))
    assert all(genes == jansen_lengths() for genes in calls)


def test_report_carries_the_generation():
    def distance(leg):
        return leg.distance

    seen = reports(ga.RunSettings(seed=3, **SMALL), distance)
    for report in seen:
        assert len(report.population) == SMALL["pop"]
        for member in report.population:
            leg = leg_from(member.genes, member.layout)
            assert (member.score, member.jams) == (leg.distance, leg.jams)
        assert max(m.score for m in report.population) == report.best_score
        assert report.mean_score == pytest.approx(
            sum(m.score for m in report.population) / SMALL["pop"])


def test_hill_climbing_reports_parent_and_child():
    seen = reports(ga.RunSettings(preset="hill", seed=5, **SMALL), lambda leg: leg.distance)
    assert len(seen[0].population) == 1
    for before, report in zip(seen, seen[1:]):
        parent, child = report.population
        assert (parent.genes, parent.score) == (before.best_genes, before.best_score)
        assert report.best_score == max(parent.score, child.score)


def test_random_search_reports_its_newcomers():
    relative = FitnessSettings(normalisation="generation")
    for fitness in (FitnessSettings(), relative):
        seen = reports(ga.RunSettings(preset="random", fitness=fitness, **SMALL))
        assert all(len(report.population) == SMALL["pop"] for report in seen)


def test_plain_population_is_small():
    final = ga.run(ga.RunSettings(generations=1))
    plain = final.as_dict()["population"]
    assert len(plain) == ga.POP_SIZE
    for member, beest in zip(plain, final.population):
        assert member["genes"] == [round(x, ga.POPULATION_DECIMALS) for x in beest.genes]
        assert member["phases"] == list(beest.layout.phases)
        assert (member["score"], member["jams"]) == (beest.score, beest.jams)
    assert len(json.dumps(plain)) < 6000


def test_run_best_keeps_a_beest_the_ga_lost():
    # Without elites an earlier generation's best is not carried on, and the last scores lower.
    seen = reports(ga.RunSettings(elite=0, seed=2, **SMALL))
    assert seen[-1].best_score < seen[-1].run_best_score
    record = -math.inf
    for report in seen:
        record = max(record, report.best_score)
        assert report.run_best_score == record
        found = seen[report.run_best_generation]
        assert report.run_best_score == found.best_score
        assert (report.run_best_genes, report.run_best_layout) == (found.best_genes,
                                                                   found.best_layout)
    assert seen[-1].run_best_generation < seen[-1].generation
    assert seen[-1].run_best_genes != seen[-1].best_genes


def test_run_best_matches_its_beest():
    for preset in ga.PRESETS:
        final = ga.run(ga.RunSettings(preset=preset, elite=0, seed=2, **SMALL))
        leg = leg_from(final.run_best_genes, final.run_best_layout)
        assert final.run_best_values["distance"] == leg.distance
        assert final.run_best_values["flatness"] == leg.bob
        assert (final.run_best_jams, final.run_best_fits) == (leg.jams, leg.fits)


def test_run_best_follows_a_search_that_keeps_its_best():
    # Elites, hill climbing's parent and random search's best so far: the latest best is the
    # run's, and it keeps the generation it first led.
    for settings in (ga.RunSettings(seed=1, **SMALL), ga.RunSettings(preset="hill", seed=5, **SMALL),
                     ga.RunSettings(preset="random", seed=1, **SMALL)):
        seen = reports(settings)
        for report in seen:
            assert (report.run_best_genes, report.run_best_layout, report.run_best_score) == (
                report.best_genes, report.best_layout, report.best_score)
            first = next(r for r in seen if r.best_genes == report.best_genes)
            assert report.run_best_generation == first.generation


def test_run_best_takes_a_later_tie():
    # Every beest scores the same, so each generation's best is the run's.
    seen = reports(ga.RunSettings(elite=0, seed=1, **SMALL), lambda leg: 1)
    assert [r.run_best_generation for r in seen] == list(range(SMALL["generations"]))
    assert all(r.run_best_genes == r.best_genes for r in seen)


def test_run_best_under_generation_normalisation_is_the_latest():
    relative = FitnessSettings(normalisation="generation")
    seen = reports(ga.RunSettings(elite=0, seed=2, fitness=relative, **SMALL))
    for report in seen:
        assert (report.run_best_genes, report.run_best_score) == (report.best_genes,
                                                                  report.best_score)


def test_all_jammed_population_runs():
    for preset in ga.PRESETS:
        for normalisation in ("jansen", "limits", "generation"):
            settings = ga.RunSettings(preset=preset, fitness=FitnessSettings(normalisation=normalisation),
                                      **SMALL)
            final = ga.run(settings, lambda leg: 0)
            assert final.best_score == 0
            assert final.mean_score == 0
            assert final.generation == SMALL["generations"] - 1


@pytest.mark.parametrize("preset", ga.PRESETS)
@pytest.mark.parametrize("normalisation", ("jansen", "limits", "generation"))
def test_every_beest_jams(preset, normalisation):
    # No leg keeps every pair of links 50 mm from failing to meet.
    settings = ga.RunSettings(preset=preset, margin=50, fitness=FitnessSettings(normalisation=normalisation),
                              **SMALL)
    seen = reports(settings)
    assert len(seen) == SMALL["generations"]
    assert all(r.best_score == r.mean_score == 0 for r in seen)
    assert all(value == 0 for value in seen[-1].best_values.values())


def test_on_generation_can_stop():
    seen = []
    final = ga.run(ga.RunSettings(), on_generation=lambda report: seen.append(report) or False)
    assert len(seen) == 1
    assert final is seen[0]
    assert final.evaluations == 30


def test_mask_holds_other_lengths_at_jansen():
    for preset in ga.PRESETS:
        settings = ga.RunSettings(preset=preset, mask=frozenset("bm"), seed=5, **SMALL)
        for report in reports(settings):
            for name, x, j in zip(LENGTH_NAMES, report.best_genes, jansen_lengths()):
                if name not in "bm":
                    assert x == j


def test_mask_reaches_student_mutate():
    final = ga.run(ga.RunSettings(mask=frozenset("m"), rate=1.0, **SMALL),
                   mutate_fn=lambda genes, rate: [x + 1 for x in genes])
    assert [x - j for x, j in zip(final.best_genes, jansen_lengths())][:12] == [0.0] * 12


def layouts_scored(settings):
    seen = set()

    def fitness(leg):
        seen.add(leg.layout)
        return 0.0 if leg.jams else leg.distance

    ga.run(settings, fitness)
    return seen


@pytest.mark.parametrize("preset", ("ga", "hill"))
def test_layout_mutation(preset):
    layouts = layouts_scored(ga.RunSettings(preset=preset, layout_mutates=True, rate=0.5, seed=6,
                                            **SMALL))
    assert len(layouts) > 1
    for layout in layouts:
        assert PAIRS_BOUNDS[0] <= layout.pairs <= PAIRS_BOUNDS[1]
        assert len(layout.phases) == layout.pairs


@pytest.mark.parametrize("preset", ga.PRESETS)
def test_layout_stays_unless_it_may_mutate(preset):
    assert layouts_scored(ga.RunSettings(preset=preset, **SMALL)) == {Layout()}


def test_student_mutate_cannot_harm_parents():
    def vandal(genes, rate):
        child = ga.mutate(genes, rate)
        genes[:] = [10.0] * 13
        return child

    for preset in ("ga", "hill"):
        seen = reports(ga.RunSettings(preset=preset, seed=2, **SMALL), mutate_fn=vandal)
        assert all(later.best_score >= earlier.best_score for earlier, later in zip(seen, seen[1:]))
        for report in seen:
            leg = leg_from(report.best_genes, report.best_layout)
            assert report.best_values["distance"] == leg.distance


def test_student_fitness_cannot_harm_the_run():
    # The kept beests (elites, hill climbing's parent, random search's best) are scored again
    # each generation from the leg already built.
    def vandal(leg):
        crank = leg.genes[-1]
        leg.genes[-1] += 5
        return crank

    together = FitnessSettings(normalisation="generation")
    for preset in ga.PRESETS:
        settings = ga.RunSettings(preset=preset, seed=2, fitness=together, **SMALL)
        for report in reports(settings, vandal):
            assert report.best_score == report.best_genes[-1]


def test_bad_returns_give_the_editor_line():
    source = ("import random\n"
              "\n"
              "def fitness(leg):\n"
              "    leg.stride\n"
              "\n"
              "def mutate(genes, rate):\n"
              "    genes.append(1.0)\n")
    fitness, mutate = student_functions(source)
    with pytest.raises(ga.StudentCodeError) as caught:
        ga.run(ga.RunSettings(**SMALL), fitness)
    assert caught.value.line == 3
    with pytest.raises(ga.StudentCodeError) as caught:
        ga.run(ga.RunSettings(**SMALL), mutate_fn=mutate)
    assert caught.value.line == 6
    with pytest.raises(ga.StudentCodeError) as caught:
        ga.run(ga.RunSettings(**SMALL), lambda leg: None)
    assert caught.value.line is None


@pytest.mark.parametrize("score, shown", [(None, "None"), (math.nan, "nan"), (math.inf, "inf"),
                                          ("fast", "'fast'"), ([1], "[1]"), (10 ** 400, "1000"),
                                          (True, "True")])
def test_bad_score_says_what_fitness_returned(score, shown):
    with pytest.raises(ga.StudentCodeError, match="fitness returned") as caught:
        ga.run(ga.RunSettings(**SMALL), lambda leg: score)
    assert shown in str(caught.value)
    assert caught.value.function == "fitness"


def test_numbers_of_any_kind_score():
    for score in (1, Fraction(1, 2), 10 ** 30):
        final = ga.run(ga.RunSettings(**SMALL), lambda leg: score)
        assert final.best_score == float(score)
        assert isinstance(final.best_score, float)


def test_student_code_error_survives_pickling():
    error = pickle.loads(pickle.dumps(ga.StudentCodeError("fitness", "fitness returned None", 3)))
    assert (error.function, str(error), error.line) == ("fitness", "fitness returned None", 3)


@pytest.mark.parametrize("genes, said", [(None, "mutate returned None"),
                                         ([1.0] * 12, "12 lengths"),
                                         ([1.0] * 12 + [math.nan], "length m"),
                                         ([True] + [1.0] * 12, "length a"),
                                         ("abc", "'abc'")])
def test_bad_genes_say_what_mutate_returned(genes, said):
    with pytest.raises(ga.StudentCodeError, match="mutate") as caught:
        ga.run(ga.RunSettings(**SMALL), mutate_fn=lambda g, rate: genes)
    assert said in str(caught.value)
    assert caught.value.function == "mutate"


def test_report_is_plain():
    final = ga.run(ga.RunSettings(**SMALL))
    plain = final.as_dict()
    assert json.loads(json.dumps(plain)) == plain
    assert plain["best_layout"] == {"pairs": 3, "phases": [0.0, 120.0, 240.0]}
    assert plain["run_best_layout"] == plain["best_layout"]
    assert set(plain["best_values"]) == {"distance", "stride", "step_height", "time_down", "flatness",
                                         "upright"}


@pytest.mark.parametrize("bad", [{"preset": "annealing"}, {"crossover": "swap"},
                                 {"mask": {"z"}}, {"pop": 0}, {"generations": 0},
                                 {"budget": 0}, {"elite": -1}, {"tol": -1}, {"pop": 2},
                                 {"size": math.nan}, {"rate": -0.1}, {"tol": math.nan},
                                 {"margin": math.inf}, {"pop": 30.5}, {"budget": True},
                                 {"generations": 2.0}, {"start": "best"}, {"start": "design"},
                                 {"start_genes": [1.0] * 12}, {"start_genes": [math.nan] * 13},
                                 {"start_genes": [True] * 13}])
def test_bad_settings_are_refused(bad):
    with pytest.raises(ValueError):
        ga.RunSettings(**bad)


def test_elite_matters_only_to_the_ga():
    assert ga.RunSettings(preset="hill", pop=1).elite == ga.ELITE
    assert ga.RunSettings(preset="random", pop=2).elite == ga.ELITE


def test_student_default_runs():
    fitness, mutate = student_functions(SOURCE)
    seen = reports(ga.RunSettings(generations=3), fitness, mutate)
    assert [r.evaluations for r in seen] == [30, 60, 90]
    assert seen[-1].best_score > 0
    # The mean of distance and flipped flatness, as the settings route's default (decisions S5).
    leg = leg_from(seen[-1].best_genes, seen[-1].best_layout)
    normalise([leg], FitnessSettings(), leg_from(jansen_lengths()))
    assert seen[-1].best_score == pytest.approx(
        (leg.normalised["distance"] + 1 - leg.normalised["flatness"]) / 2)


@pytest.mark.parametrize("normalisation", ("jansen", "limits", "generation"))
def test_student_default_repeats_the_settings_route(normalisation):
    settings = ga.RunSettings(seed=3, fitness=FitnessSettings(normalisation=normalisation), **SMALL)
    assert reports(settings, *student_functions(SOURCE)) == reports(settings)


def test_student_default_repeats_with_seed():
    first = reports(ga.RunSettings(seed=9, **SMALL), *student_functions(SOURCE))
    again = reports(ga.RunSettings(seed=9, **SMALL), *student_functions(SOURCE))
    assert first == again


def test_student_errors_name_editor_lines():
    source = SOURCE.replace("return 0\n", "return 1 / 0\n", 1)
    fitness, mutate = student_functions(source)
    with pytest.raises(ZeroDivisionError) as caught:
        ga.run(ga.RunSettings(**SMALL), fitness, mutate)
    frames = [frame for frame in traceback.extract_tb(caught.value.__traceback__)
              if frame.filename == EDITOR]
    assert frames
    assert source.splitlines()[frames[-1].lineno - 1].strip() == "return 1 / 0"


def test_student_code_must_define_both():
    with pytest.raises(ga.StudentCodeError, match="mutate"):
        student_functions("def fitness(leg):\n    return 0\n")
    with pytest.raises(SyntaxError):
        student_functions("def fitness(leg)\n")
