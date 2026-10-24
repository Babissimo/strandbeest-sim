"""Arena tab: a whole beest walking in the page's physics engine, which loads when the tab opens."""

import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Locator, Page, Request, expect

from beest.leg import MM_PER_UNIT

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 60_000
# Evolve's worker starts a second Python.
EVOLVE_START_TIMEOUT_MS = 90_000
# The crank turns once a second, so this many turns take as many seconds.
WALK_TURNS = 3
NEW_BEST = "Evolve has found a new best beest. Press Reset to walk it."
# Stands in for the GA worker. It runs the real GA, but the best beest it reports is the one the
# run's seed picks, and each generation takes at least GENERATION_S, so Evolve shows every one.
FAKE_WORKER = """
import json
import time

from pyscript import sync

from app.job import run_request
from beest.leg import jansen_lengths

GENERATION_S = 0.3


def best(seed, generation):
    if seed == 3:
        # A new best every generation: Jansen's leg a little bigger each time, on 3 pairs.
        return [x * (1 + 0.01 * (generation + 1)) for x in jansen_lengths()], 3
    # Jansen's leg on 3 pairs, or the same lengths on 4.
    return jansen_lengths(), {1: 3, 2: 4}[seed]


def run(request):
    seed = json.loads(request)["settings"]["seed"]

    def report(text):
        until = time.monotonic() + GENERATION_S
        while time.monotonic() < until:
            pass
        generation = json.loads(text)
        genes, pairs = best(seed, generation["generation"])
        generation["best_genes"] = genes
        generation["best_layout"] = {"pairs": pairs,
                                     "phases": [360 * k / pairs for k in range(pairs)]}
        return sync.report(json.dumps(generation))

    return run_request(request, report)


sync.run = run
sync.started = lambda: True
"""


def origin(url: str) -> str:
    parts = urlsplit(url.removeprefix("blob:"))
    return f"{parts.scheme}://{parts.netloc}"


def turns(mode: Locator) -> float:
    return float(mode.get_attribute("data-turns"))


def walks_on(page: Page, beyond: float) -> None:
    """Waits until the arena's crank has turned past `beyond` turns."""
    page.wait_for_function(
        "turns => Number(document.querySelector('#arena-mode').dataset.turns) > turns",
        arg=beyond,
        timeout=10_000,
    )


def evolve_from_arena(page: Page, seed: int, generations: int) -> None:
    """Runs Evolve from the Arena tab, as if its Run button were pressed, and waits for the end."""
    page.evaluate(
        """([seed, generations]) => {
            document.querySelector("#ev-seed").value = String(seed);
            document.querySelector("#ev-generations").value = String(generations);
            document.querySelector(".ev-run").click();
        }""",
        [seed, generations],
    )
    expect(page.locator("#evolve-mode")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )


def open_arena(page: Page) -> Locator:
    page.goto("/#arena")
    mode = page.locator("#arena-mode")
    expect(mode).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    return mode


def test_jansen_walks_left(page: Page, base_url: str) -> None:
    requested: list[str] = []

    def on_request(request: Request) -> None:
        requested.append(request.url)

    page.context.on("request", on_request)
    mode = open_arena(page)
    expect(mode).to_have_attribute("data-beest", "jansen")
    expect(mode).to_have_attribute("data-pairs", "3")
    expect(mode).to_have_attribute("data-turns", "0.0")
    start = page.locator("#arena-start")
    start.click()
    expect(mode).to_have_attribute("data-status", "running")
    page.wait_for_function(
        "turns => Number(document.querySelector('#arena-mode').dataset.turns) >= turns",
        arg=WALK_TURNS,
        timeout=30_000,
    )
    start.click()
    expect(mode).to_have_attribute("data-status", "ready")
    expect(mode).to_have_attribute("data-tipped", "false")
    distance = float(mode.get_attribute("data-distance-per-turn"))
    assert 138 * MM_PER_UNIT <= distance <= 148 * MM_PER_UNIT
    assert float(mode.get_attribute("data-travel")) > 0
    page.locator("#arena-reset").click()
    expect(mode).to_have_attribute("data-turns", "0.0")
    expect(mode).to_have_attribute("data-distance-per-turn", "")
    elsewhere = [
        url for url in requested if not url.startswith("data:") and origin(url) != base_url
    ]
    assert elsewhere == []
    assert any(url.endswith(".whl") for url in requested)


def test_jammed_playground_leg_is_refused(page: Page) -> None:
    page.goto("/#leg")
    expect(page.locator("#status")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )
    # Jansen's crank made 10% longer.
    page.locator("#leg-m").fill(f"{16.5 * MM_PER_UNIT:g}")
    expect(page.locator("#leg-mode")).to_have_attribute("data-jammed", "true")
    page.get_by_role("link", name="Arena", exact=True).click()
    mode = page.locator("#arena-mode")
    expect(mode).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.locator("#arena-beest").select_option("leg")
    expect(mode).to_have_attribute("data-beest", "leg")
    expect(mode).to_have_attribute("data-jammed", "true")
    expect(page.locator("#arena-message")).to_contain_text("f and g cannot meet")
    expect(page.locator("#arena-start")).to_be_disabled()


@pytest.mark.page_errors_expected
def test_engine_that_cannot_load_leaves_the_other_tabs_working(page: Page) -> None:
    page.route("**/pymunk-*.whl", lambda route: route.fulfill(status=404))
    page.goto("/#arena")
    mode = page.locator("#arena-mode")
    expect(mode).to_have_attribute("data-status", "error", timeout=START_TIMEOUT_MS)
    expect(page.locator("#arena-message")).to_contain_text("could not load")
    expect(page.locator("#arena-start")).to_be_disabled()
    page.get_by_role("link", name="Leg", exact=True).click()
    expect(page.locator("#leg-mode")).not_to_have_attribute("data-stride", "")


def test_best_from_evolve_is_offered(page: Page) -> None:
    page.goto("/#evolve")
    evolve = page.locator("#evolve-mode")
    expect(evolve).to_have_attribute("data-status", "ready", timeout=EVOLVE_START_TIMEOUT_MS)
    page.locator('input[name="ev-limit"][value="generations"]').check()
    page.locator("#ev-generations").fill("2")
    page.get_by_role("button", name="Run", exact=True).click()
    expect(evolve).to_have_attribute("data-best-score", re.compile("."), timeout=START_TIMEOUT_MS)
    expect(evolve).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.get_by_role("link", name="Arena", exact=True).click()
    mode = page.locator("#arena-mode")
    expect(mode).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    expect(page.locator('#arena-beest option[value="evolved"]')).to_be_enabled()
    page.locator("#arena-beest").select_option("evolved")
    expect(mode).to_have_attribute("data-beest", "evolved")
    expect(mode).to_have_attribute("data-pairs", "3")


def test_walk_goes_on_when_the_tab_is_opened_again(page: Page) -> None:
    mode = open_arena(page)
    page.locator("#arena-beest").select_option("leg")
    page.locator("#arena-start").click()
    walks_on(page, 0.2)
    page.get_by_role("link", name="Leg", exact=True).click()
    page.locator("#leg-m").fill(f"{14 * MM_PER_UNIT:g}")
    page.get_by_role("link", name="Arena", exact=True).click()
    expect(page.locator("#arena-message")).to_contain_text("The leg in the Leg tab has changed")
    expect(mode).to_have_attribute("data-status", "running")
    walks_on(page, turns(mode) + 0.2)


def test_new_best_from_evolve_waits_for_reset(page: Page) -> None:
    page.route("**/app/ga_worker.py", lambda route: route.fulfill(body=FAKE_WORKER))
    page.goto("/#evolve")
    evolve = page.locator("#evolve-mode")
    expect(evolve).to_have_attribute("data-status", "ready", timeout=EVOLVE_START_TIMEOUT_MS)
    page.locator('input[name="ev-limit"][value="generations"]').check()
    page.locator("#ev-generations").fill("1")
    page.locator("#ev-seed").fill("1")
    page.get_by_role("button", name="Run", exact=True).click()
    expect(evolve).to_have_attribute("data-best-score", re.compile("."), timeout=START_TIMEOUT_MS)
    expect(evolve).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.get_by_role("link", name="Arena", exact=True).click()
    mode = page.locator("#arena-mode")
    expect(mode).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    page.locator("#arena-beest").select_option("evolved")
    expect(mode).to_have_attribute("data-pairs", "3")
    message = page.locator("#arena-message")
    expect(message).to_have_text("")

    # The same lengths on another layout is a new best, which waits while the tab is on show.
    evolve_from_arena(page, seed=2, generations=1)
    expect(message).to_have_text(NEW_BEST)
    expect(mode).to_have_attribute("data-pairs", "3")
    page.locator("#arena-reset").click()
    expect(mode).to_have_attribute("data-pairs", "4")
    expect(message).to_have_text("")

    # Pairs chosen by hand stand while new bests arrive, and the notice is announced once.
    page.locator("#arena-pairs").select_option("1")
    expect(mode).to_have_attribute("data-pairs", "1")
    message.evaluate(
        """region => {
            window.notices = 0;
            new MutationObserver(changes => { window.notices += changes.length; })
                .observe(region, {childList: true, characterData: true, subtree: true});
        }"""
    )
    evolve_from_arena(page, seed=3, generations=3)
    expect(message).to_have_text(NEW_BEST)
    expect(mode).to_have_attribute("data-pairs", "1")
    assert page.evaluate("window.notices") == 1
    # Changing Pairs takes up the new best on the pairs chosen.
    page.locator("#arena-pairs").select_option("2")
    expect(mode).to_have_attribute("data-pairs", "2")
    expect(message).to_have_text("")

    # A walk under way carries on through Evolve's new bests.
    page.locator("#arena-start").click()
    walks_on(page, 0.1)
    evolve_from_arena(page, seed=1, generations=2)
    expect(message).to_have_text(NEW_BEST)
    expect(mode).to_have_attribute("data-status", "running")
    expect(mode).to_have_attribute("data-pairs", "2")
    walks_on(page, turns(mode) + 0.1)
