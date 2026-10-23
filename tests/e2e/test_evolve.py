"""Evolve mode: runs in a worker, Stop, presets on one graph, seeds that repeat, plain errors."""

import re

import pytest
from playwright.sync_api import Page, expect

from beest import ga
from beest.fitness import INGREDIENTS, FitnessSettings, fixed_limits
from beest.geometry import LENGTH_NAMES
from beest.leg import MM_PER_UNIT, jansen_lengths

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 90_000
RUN_TIMEOUT_MS = 60_000


@pytest.fixture
def evolve(page: Page) -> Page:
    page.goto("/#evolve")
    expect(page.locator("#evolve-mode")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS)
    return page


def mode(page: Page):
    return page.locator("#evolve-mode")


def run_and_wait(page: Page) -> None:
    page.get_by_role("button", name="Run", exact=True).click()
    expect(mode(page)).to_have_attribute("data-status", "ready", timeout=RUN_TIMEOUT_MS)
    expect(mode(page)).not_to_have_attribute("data-error", re.compile(".*"))


def number(page: Page, name: str) -> float:
    return float(mode(page).get_attribute(f"data-{name}"))


def stop_after(page: Page, kind: str, count: int) -> None:
    page.locator(f'input[name="ev-limit"][value="{kind}"]').check()
    page.locator(f"#ev-{kind}").fill(str(count))


def column(page: Page, kind: str):
    """The best beest of the latest generation ("latest") or of the whole run ("run")."""
    return page.locator(f'.best-beest[data-best="{kind}"]')


def test_worker_starts_when_the_mode_is_shown(page: Page) -> None:
    configs = []
    page.context.on("request", lambda request: configs.append(request.url)
                    if request.url.endswith("/worker.toml") else None)
    page.goto("/")
    expect(page.locator("#status")).to_have_attribute("data-status", "ready",
                                                      timeout=START_TIMEOUT_MS)
    page.wait_for_timeout(500)
    assert configs == []
    expect(mode(page)).not_to_have_attribute("data-status", re.compile(".*"))
    page.get_by_role("link", name="Evolve", exact=True).click()
    expect(mode(page)).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    assert len(configs) == 1


def test_default_run_completes(evolve: Page) -> None:
    run_and_wait(evolve)
    root = mode(evolve)
    expect(root).to_have_attribute("data-points", str(ga.GENERATIONS))
    expect(root).to_have_attribute("data-series", "1")
    expect(root).to_have_attribute("data-generation", str(ga.GENERATIONS - 1))
    expect(root).to_have_attribute("data-evaluations", str(ga.GENERATIONS * ga.POP_SIZE))
    for check in ("turns", "fits"):
        expect(root).to_have_attribute(f"data-winner-{check}", re.compile("^(true|false)$"))
        shown = column(evolve, "latest").locator(f'[data-check="{check}"]')
        expect(shown).to_be_visible()
        expect(shown).to_have_text(re.compile("^[✓✗] "))
    # The panel's defaults are the engine's, and Pyodide repeats CPython's run exactly.
    final = ga.run(ga.RunSettings())
    assert root.get_attribute("data-best-score") == repr(final.best_score)
    # The elites keep the best, so the run's best is the same beest, said once and drawn once.
    assert final.run_best_genes == final.best_genes
    expect(root).to_have_attribute("data-same-best", "true")
    expect(root).to_have_attribute("data-run-best-score", repr(final.run_best_score))
    expect(root).to_have_attribute("data-run-best-generation", str(final.run_best_generation))
    expect(column(evolve, "run").locator(".ev-same")).to_contain_text(
        f"The same beest as the best of the latest generation. It has been the best of the run "
        f"since generation {final.run_best_generation}.")
    expect(column(evolve, "run").locator(".best-shown")).to_be_hidden()
    # The best beest stands still at 0° until Play turns it.
    expect(root).to_have_attribute("data-playing", "false")
    expect(root).to_have_attribute("data-angle", "0")
    root.get_by_role("button", name="Play").click()
    expect(root).to_have_attribute("data-playing", "true")
    expect(root).not_to_have_attribute("data-angle", "0")
    expect(evolve.locator(".ev-legend")).to_contain_text("Run 1: GA, seed 1")
    expect(evolve.locator(".ev-progress")).to_contain_text("Finished: 40 generations")
    # The grid shows the last generation, every beest of it.
    expect(root).to_have_attribute("data-population", str(ga.POP_SIZE))
    expect(root).to_have_attribute("data-population-generation", str(ga.GENERATIONS - 1))
    expect(evolve.locator(".ev-population")).to_be_visible()
    expect(evolve.locator(".ev-population-hint")).to_contain_text(
        f"Run 1: GA, seed 1, generation {ga.GENERATIONS - 1}: every beest, best first")


def test_stop_halts_run(evolve: Page) -> None:
    stop_after(evolve, "generations", 100_000)
    evolve.get_by_role("button", name="Run", exact=True).click()
    root = mode(evolve)
    expect(root).to_have_attribute("data-status", "running")
    expect(root).to_have_attribute("data-generation", re.compile(r"^([3-9]|\d\d+)$"),
                                   timeout=RUN_TIMEOUT_MS)
    # The page keeps drawing while the worker runs, and the grid takes up later generations.
    root.get_by_role("button", name="Play").click()
    angle = root.get_attribute("data-angle")
    expect(root).not_to_have_attribute("data-angle", angle)
    expect(root).to_have_attribute("data-population-generation", re.compile(r"^\d+$"))
    shown = root.get_attribute("data-population-generation")
    expect(root).not_to_have_attribute("data-population-generation", shown)
    expect(root).to_have_attribute("data-status", "running")
    evolve.get_by_role("button", name="Stop", exact=True).click()
    expect(root).to_have_attribute("data-status", "ready", timeout=10_000)
    stopped_at = number(evolve, "points")
    evolve.wait_for_timeout(500)
    assert number(evolve, "points") == stopped_at < 100_000
    expect(evolve.locator(".ev-legend")).to_contain_text("(stopped)")
    # The fresh worker runs the next search.
    stop_after(evolve, "generations", 3)
    run_and_wait(evolve)
    expect(root).to_have_attribute("data-series", "2")
    expect(root).to_have_attribute("data-points", "3")


def test_presets_overlay(evolve: Page) -> None:
    # Choosing a rival search sets a budget of evaluations, which the GA then keeps.
    by_budget = evolve.locator('input[name="ev-limit"][value="budget"]')
    expect(by_budget).not_to_be_checked()
    evolve.locator("#ev-preset").select_option("random")
    expect(by_budget).to_be_checked()
    expect(evolve.locator("#ev-budget")).to_have_value(str(ga.BUDGET))
    evolve.locator("#ev-preset").select_option("ga")
    expect(by_budget).to_be_checked()
    budget = 300
    # The grid shows each search's last generation: hill climbing's parent and child.
    for preset, population in (("random", ga.POP_SIZE), ("hill", 2), ("ga", ga.POP_SIZE)):
        evolve.locator("#ev-preset").select_option(preset)
        stop_after(evolve, "budget", budget)
        run_and_wait(evolve)
        assert number(evolve, "evaluations") == budget
        expect(mode(evolve)).to_have_attribute("data-population", str(population))
        expect(mode(evolve)).to_have_attribute("data-population-generation",
                                               mode(evolve).get_attribute("data-generation"))
    expect(mode(evolve)).to_have_attribute("data-series", "3")
    legend = evolve.locator(".ev-legend li")
    expect(legend).to_have_text([
        "Run 1: Random search, seed 1", "Run 2: Hill climbing, seed 1", "Run 3: GA, seed 1"])
    # Hill climbing tries one beest at a time.
    evolve.locator("#ev-preset").select_option("hill")
    expect(evolve.locator("#ev-pop")).to_be_disabled()
    expect(evolve.locator("#ev-pop")).to_have_value("1")
    evolve.locator("#ev-preset").select_option("ga")
    expect(evolve.locator("#ev-pop")).to_be_enabled()
    expect(evolve.locator("#ev-pop")).to_have_value(str(ga.POP_SIZE))
    evolve.get_by_role("button", name="Clear graph").click()
    expect(mode(evolve)).to_have_attribute("data-series", "0")


def test_seed_repeats(evolve: Page) -> None:
    evolve.locator("#ev-seed").fill("7")
    stop_after(evolve, "generations", 8)
    scores = []
    for _ in range(2):
        run_and_wait(evolve)
        scores.append(mode(evolve).get_attribute("data-best-score"))
    assert scores[0] == scores[1]
    expect(evolve.locator(".ev-legend li").first).to_have_text("Run 1: GA, seed 7")


def test_hill_climbing_starts_from_a_beest_that_turns(evolve: Page) -> None:
    start = evolve.locator("#ev-start")
    expect(start).to_have_value("random")
    start.select_option("jansen")
    evolve.locator("#ev-preset").select_option("hill")
    expect(start).to_have_value("turning")
    expect(evolve.locator("#ev-start-hint")).to_contain_text("costs no evaluations")
    # Leaving hill climbing gives the start back, as it does the population.
    evolve.locator("#ev-preset").select_option("ga")
    expect(start).to_have_value("jansen")
    # A start chosen while on hill climbing stays when it is left.
    evolve.locator("#ev-preset").select_option("hill")
    start.select_option("design")
    evolve.locator("#ev-preset").select_option("ga")
    expect(start).to_have_value("design")
    start.select_option("jansen")
    # Random search makes its copies of Jansen's leg with the mutation rate and size.
    evolve.locator("#ev-preset").select_option("random")
    expect(evolve.locator("#ev-rate")).to_be_enabled()
    start.select_option("random")
    expect(evolve.locator("#ev-rate")).to_be_disabled()


def test_turning_start_repeats_the_engine(evolve: Page) -> None:
    evolve.locator("#ev-start").select_option("turning")
    evolve.locator("#ev-pop").fill("10")
    stop_after(evolve, "generations", 3)
    run_and_wait(evolve)
    expected = ga.run(ga.RunSettings(start="turning", pop=10, generations=3))
    expect(mode(evolve)).to_have_attribute("data-best-score", repr(expected.best_score))


def test_design_start_takes_the_leg_tab(evolve: Page) -> None:
    root = mode(evolve)
    # Jansen's crank made 10% longer jams.
    evolve.get_by_role("link", name="Leg", exact=True).click()
    evolve.locator("#leg-m").fill(f"{16.5 * MM_PER_UNIT:g}")
    expect(evolve.locator("#leg-mode")).to_have_attribute("data-jammed", "true")
    evolve.get_by_role("link", name="Evolve", exact=True).click()
    evolve.locator("#ev-start").select_option("design")
    expect(root).to_have_attribute("data-design-jams", "true")
    warning = evolve.locator(".ev-design-jams")
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("The leg in the Leg tab jams: f and g")
    # A design that turns clears the warning once Evolve is shown again.
    evolve.get_by_role("link", name="Leg", exact=True).click()
    evolve.locator("#leg-m").fill("18")
    evolve.locator("#leg-j").fill("55")
    expect(evolve.locator("#leg-mode")).to_have_attribute("data-jammed", "false")
    evolve.get_by_role("link", name="Evolve", exact=True).click()
    expect(root).to_have_attribute("data-design-jams", "false")
    expect(warning).to_be_hidden()
    # The warning follows the jam margin it is checked at.
    evolve.locator("details", has_text="More settings").locator("summary").click()
    evolve.locator("#ev-margin").fill("30")
    expect(root).to_have_attribute("data-design-jams", "true")
    evolve.locator("#ev-margin").fill("0")
    expect(root).to_have_attribute("data-design-jams", "false")
    evolve.locator("#ev-pop").fill("10")
    stop_after(evolve, "generations", 3)
    run_and_wait(evolve)
    design = dict(zip(LENGTH_NAMES, jansen_lengths())) | {"m": 18.0, "j": 55.0}
    expected = ga.run(ga.RunSettings(start="design", start_genes=list(design.values()), pop=10,
                                     generations=3))
    expect(root).to_have_attribute("data-best-score", repr(expected.best_score))


def test_best_of_the_run_beside_the_latest(evolve: Page) -> None:
    # With no elites the GA loses generation 0's best, which the run's column keeps.
    settings = ga.RunSettings(elite=0, pop=10, generations=6, seed=2)
    final = ga.run(settings)
    assert final.run_best_genes != final.best_genes
    evolve.locator("details", has_text="More settings").locator("summary").click()
    evolve.locator("#ev-elite").fill("0")
    evolve.locator("#ev-pop").fill("10")
    evolve.locator("#ev-seed").fill("2")
    stop_after(evolve, "generations", 6)
    run_and_wait(evolve)
    root = mode(evolve)
    expect(root).to_have_attribute("data-same-best", "false")
    expect(root).to_have_attribute("data-best-score", repr(final.best_score))
    expect(root).to_have_attribute("data-run-best-score", repr(final.run_best_score))
    expect(root).to_have_attribute("data-run-best-generation", str(final.run_best_generation))
    for kind, prefix, jams, fits in (("latest", "", final.best_jams, final.best_fits),
                                     ("run", "run-", final.run_best_jams, final.run_best_fits)):
        expect(root).to_have_attribute(f"data-{prefix}winner-turns", str(not jams).lower())
        expect(root).to_have_attribute(f"data-{prefix}winner-fits", str(fits).lower())
        for check in ("turns", "fits"):
            expect(column(evolve, kind).locator(f'[data-check="{check}"]')).to_be_visible()
    expect(column(evolve, "run").locator(".which")).to_contain_text(
        f"the best since generation {final.run_best_generation}")
    expect(column(evolve, "run").locator(".ev-same")).to_be_hidden()
    # One crank turns both.
    root.get_by_role("button", name="Play").click()
    expect(root).not_to_have_attribute("data-angle", "0")


def test_settings_error_is_shown_beside_run(evolve: Page) -> None:
    evolve.locator("#ev-pop").fill("2")
    evolve.get_by_role("button", name="Run", exact=True).click()
    error = evolve.locator(".ev-error")
    expect(error).to_have_text(
        "elite (2) must be smaller than the population (2), or no children are made")
    expect(mode(evolve)).to_have_attribute("data-error", re.compile("^elite"))
    expect(mode(evolve)).to_have_attribute("data-status", "ready")
    expect(mode(evolve)).to_have_attribute("data-series", "0")
    evolve.locator("#ev-pop").fill("")
    evolve.get_by_role("button", name="Run", exact=True).click()
    expect(error).to_have_text("Population needs a number.")
    evolve.locator("#ev-pop").fill("6")
    stop_after(evolve, "generations", 2)
    run_and_wait(evolve)
    expect(error).to_be_hidden()


def test_all_zero_scores_draw(evolve: Page) -> None:
    # Every weight 0 scores every beest 0, under each normalisation.
    evolve.locator("details", has_text="Fitness").locator("summary").click()
    for name in INGREDIENTS:
        evolve.locator(f"#ev-w-{name}").fill("0")
    stop_after(evolve, "generations", 3)
    for normalisation in ("jansen", "limits", "generation"):
        evolve.locator("#ev-normalisation").select_option(normalisation)
        run_and_wait(evolve)
        assert number(evolve, "best-score") == 0
    evolve.locator(".segmented label", has_text="Ingredients").click()
    expect(mode(evolve)).to_have_attribute("data-graph-view", "ingredients")
    evolve.locator(".ev-graph").hover(position={"x": 100, "y": 60})
    expect(evolve.locator(".ev-readout")).to_contain_text("Run 3: GA, seed 1 after")
    expect(evolve.locator(".ev-readout")).to_contain_text("upright")


def test_relative_axis_label(evolve: Page) -> None:
    evolve.locator("details", has_text="Fitness").locator("summary").click()
    evolve.locator("#ev-normalisation").select_option("generation")
    stop_after(evolve, "generations", 2)
    run_and_wait(evolve)
    expect(mode(evolve)).to_have_attribute("data-axis", "Score, relative to this generation")
    expect(evolve.locator("#ev-normalisation-hint")).to_contain_text("same generation")
    # Relative scores do not compare across generations, so the latest best is the run's.
    expect(mode(evolve)).to_have_attribute("data-same-best", "true")
    expect(column(evolve, "run").locator(".ev-same")).to_contain_text("cannot be compared")
    evolve.locator("#ev-normalisation").select_option("jansen")
    run_and_wait(evolve)
    expect(mode(evolve)).to_have_attribute("data-axis", "Score")
    expect(evolve.locator(".ev-legend li").first).to_have_text(
        "Run 1: GA, seed 1 (relative to each generation)")


def test_default_fitness_is_distance_and_flatness(evolve: Page) -> None:
    # Under the fixed limits (decisions S3), whose table shows from the start.
    evolve.locator("details", has_text="Fitness").locator("summary").click()
    expect(evolve.locator("#ev-normalisation")).to_have_value("limits")
    expect(evolve.locator("#ev-lo-distance")).to_be_visible()
    for name in INGREDIENTS:
        weight = "1" if name in ("distance", "flatness") else "0"
        expect(evolve.locator(f"#ev-w-{name}")).to_have_value(weight)
    expect(evolve.locator("#ev-flip-flatness")).to_be_checked()


def test_fixed_limits_left_alone_are_the_surveyed_ones(evolve: Page) -> None:
    evolve.locator("details", has_text="Fitness").locator("summary").click()
    evolve.locator("#ev-normalisation").select_option("limits")
    expect(evolve.locator("#ev-lo-distance")).to_be_visible()
    stop_after(evolve, "generations", 3)
    run_and_wait(evolve)
    limits = FitnessSettings(normalisation="limits")
    expected = ga.run(ga.RunSettings(generations=3, fitness=limits))
    assert mode(evolve).get_attribute("data-best-score") == repr(expected.best_score)
    # A limit typed in takes over from the surveyed one, and the other keeps its surveyed value.
    evolve.locator("#ev-hi-distance").fill("50")
    run_and_wait(evolve)
    low = fixed_limits()["distance"][0]
    limits = FitnessSettings(normalisation="limits", limits={"distance": (low, 50.0)})
    expected = ga.run(ga.RunSettings(generations=3, fitness=limits))
    assert mode(evolve).get_attribute("data-best-score") == repr(expected.best_score)


@pytest.mark.page_errors_expected
def test_worker_crash_is_shown(page: Page, page_errors: list[str]) -> None:
    # The page fetches the engine before it starts the worker, so only the worker's copy breaks.
    fetches = []

    def break_the_second(route) -> None:
        fetches.append(route.request.url)
        response = route.fetch()
        body = response.text()
        if len(fetches) > 1:
            # Replaces the settings route's fitness, which the GA imports once this has run.
            body += ("\n\ndef settings_fitness(settings):\n"
                     "    raise RuntimeError('broken on purpose')\n")
        route.fulfill(response=response, body=body)

    page.context.route("**/beest/fitness.py", break_the_second)
    page.goto("/#evolve")
    root = mode(page)
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.get_by_role("button", name="Run", exact=True).click()
    expect(root).to_have_attribute("data-error", "RuntimeError: broken on purpose",
                                   timeout=RUN_TIMEOUT_MS)
    expect(page.locator(".ev-error")).to_have_text("RuntimeError: broken on purpose")
    expect(root).to_have_attribute("data-status", "ready")
    expect(root).to_have_attribute("data-series", "0")
    assert len(fetches) == 2
    assert any("broken on purpose" in error for error in page_errors)


@pytest.mark.page_errors_expected
def test_failed_worker_is_replaced(page: Page, page_errors: list[str]) -> None:
    # This worker starts but has no run, so calling it fails as a broken worker's call would.
    starts = []

    def no_run(route) -> None:
        starts.append(route.request.url)
        route.fulfill(body="from pyscript import sync\nsync.started = lambda: True\n")

    page.route("**/app/ga_worker.py", no_run)
    page.goto("/#evolve")
    root = mode(page)
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.get_by_role("button", name="Run", exact=True).click()
    expect(root).to_have_attribute("data-error", re.compile("^The run failed: "),
                                   timeout=RUN_TIMEOUT_MS)
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    # The page's own copy, then one for each worker started.
    assert len(starts) == 3
    assert any("The run failed" in error for error in page_errors)


@pytest.mark.page_errors_expected
def test_worker_that_cannot_start_is_shown(page: Page, page_errors: list[str]) -> None:
    page.route("**/app/ga_worker.py",
               lambda route: route.fulfill(body="raise RuntimeError('broken on purpose')"))
    page.goto("/#evolve")
    expect(mode(page)).to_have_attribute("data-status", "error", timeout=START_TIMEOUT_MS)
    expect(page.locator(".ev-progress")).to_have_text(
        "The evolution engine could not start. Try reloading the page.")
    expect(page.get_by_role("button", name="Run", exact=True)).to_be_disabled()
    assert page_errors
