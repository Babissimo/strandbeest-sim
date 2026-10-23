"""Four-bar mode: the linkage turns, jams, traces a figure of eight and survives change points."""

import math

import pytest
from playwright.sync_api import Locator, Page, expect

from beest.geometry import DRAW_ANGLES, trace_four_bar

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 60_000
LINKS = ("ground", "crank", "coupler", "rocker")


def open_four_bar(page: Page) -> Locator:
    page.goto("/#fourbar")
    expect(page.locator("#status")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )
    return page.locator("#fourbar-mode")


def set_values(page: Page, **values: float) -> None:
    """Types each value into its number box, as a student would."""
    for name, value in values.items():
        page.locator(f"#fourbar-{name}").fill(str(value))


def set_lengths(page: Page, *lengths: float) -> None:
    set_values(page, **dict(zip(LINKS, lengths)))


def shown(mode: Locator, name: str) -> float:
    return float(mode.get_attribute(f"data-{name}"))


def drawn_to(page: Page, degrees: int, timeout: float = 15_000) -> None:
    """Waits until the animation has drawn the linkage at `degrees` or further round."""
    page.wait_for_function(
        "degrees => Number(document.querySelector('#fourbar-mode').dataset.drawnTo) >= degrees",
        arg=degrees,
        timeout=timeout,
    )


def next_frames(page: Page) -> None:
    """Waits for two animation frames, so the page has drawn at least once since the last change."""
    page.evaluate(
        "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
    )


def test_default_turns_fully(page: Page) -> None:
    mode = open_four_bar(page)
    expect(mode).to_have_attribute("data-jammed", "false")
    expect(mode).to_have_attribute("data-grashof", "crank-rocker")
    expect(page.locator("#fourbar-jam")).to_be_hidden()
    expect(page.locator("#fourbar-grashof")).to_contain_text("Crank-rocker")
    trace = trace_four_bar(*(shown(mode, name) for name in LINKS), n=DRAW_ANGLES)
    assert not trace.jammed and trace.grashof == "crank-rocker"
    drawn_to(page, 350)


def test_jam_warning(page: Page) -> None:
    mode = open_four_bar(page)
    set_lengths(page, 40, 30, 20, 25)
    trace = trace_four_bar(40, 30, 20, 25, n=DRAW_ANGLES)
    expect(mode).to_have_attribute("data-jammed", "true")
    expect(mode).to_have_attribute("data-grashof", "non-Grashof")
    warning = page.locator("#fourbar-jam")
    expect(warning).to_be_visible()
    expect(warning).to_contain_text(trace.jam_reason)
    # It swings up to the last angle before the jam, and no further.
    last = round(math.degrees(trace.angles[-1]))
    drawn_to(page, last)
    next_frames(page)
    expect(mode).to_have_attribute("data-drawn-to", str(last))


def test_figure_eight_badge(page: Page) -> None:
    mode = open_four_bar(page)
    badge = page.locator("#fourbar-figure-eight")
    expect(mode).to_have_attribute("data-figure-eight", "false")
    expect(badge).to_be_hidden()
    set_lengths(page, 59.5, 44.0, 92.6, 95.1)
    set_values(page, along=18.6, offset=-31.9)
    expect(mode).to_have_attribute("data-along", "18.6")
    expect(mode).to_have_attribute("data-offset", "-31.9")
    expect(mode).to_have_attribute("data-figure-eight", "true")
    expect(badge).to_be_visible()
    set_values(page, offset=0)
    expect(badge).to_be_hidden()


@pytest.mark.parametrize(
    "lengths",
    [
        (40, 20, 40, 20),
        (40, 20, 20, 40),
        (40, 40, 40, 40),
        (10, 104, 10, 104),
        (104, 10, 104, 10),
    ],
    ids=["parallelogram", "kite", "rhombus", "short-ground", "long-ground"],
)
def test_change_point_lengths(page: Page, lengths: tuple[float, ...]) -> None:
    mode = open_four_bar(page)
    set_lengths(page, *lengths)
    for name, value in zip(LINKS, lengths):
        expect(mode).to_have_attribute(f"data-{name}", str(float(value)))
    trace = trace_four_bar(*lengths, shown(mode, "along"), shown(mode, "offset"), n=DRAW_ANGLES)
    expect(mode).to_have_attribute("data-grashof", "change point")
    expect(mode).to_have_attribute("data-jammed", str(trace.jammed).lower())
    expect(page.locator("#fourbar-jam")).to_be_visible(visible=trace.jammed)
    next_frames(page)


def test_tracer_stays_within_reach_of_the_coupler(page: Page) -> None:
    mode = open_four_bar(page)
    set_values(page, along=50, offset=-40)
    set_lengths(page, 60, 20, 30, 50)
    # Along runs from -coupler to 2 × coupler, and the offset to ± coupler.
    expect(mode).to_have_attribute("data-along", "50.0")
    expect(mode).to_have_attribute("data-offset", "-30.0")
    expect(page.locator("#fourbar-offset")).to_have_value("-30")
    set_lengths(page, 60, 20, 20, 50)
    expect(mode).to_have_attribute("data-along", "40.0")
    # A longer coupler gives the point back where the student put it.
    set_lengths(page, 60, 20, 100, 50)
    expect(mode).to_have_attribute("data-along", "50.0")
    expect(mode).to_have_attribute("data-offset", "-40.0")
    expect(page.locator("#fourbar-along")).to_have_value("50")


def test_typed_values_keep_two_decimals(page: Page) -> None:
    mode = open_four_bar(page)
    box = page.locator("#fourbar-coupler")
    box.fill("33.333")
    box.press("Enter")
    expect(mode).to_have_attribute("data-coupler", "33.33")
    expect(box).to_have_value("33.33")
    # The along slider's ends sit on whole tenths inside the bounds, so dragging gives round values.
    slider = page.locator("#fourbar-along-slider")
    expect(slider).to_have_attribute("min", "-33.3")
    slider.fill("12.3")
    expect(mode).to_have_attribute("data-along", "12.3")


def test_typed_value_out_of_range_is_clamped(page: Page) -> None:
    mode = open_four_bar(page)
    box = page.locator("#fourbar-ground")
    box.fill("200")
    box.press("Enter")
    expect(mode).to_have_attribute("data-ground", "104.0")
    expect(box).to_have_value("104")
    expect(page.locator("#fourbar-ground-slider")).to_have_value("104")
    box.fill("")
    box.press("Enter")
    expect(box).to_have_value("104")


def test_pause_and_play(page: Page) -> None:
    mode = open_four_bar(page)
    drawn_to(page, 10)
    mode.get_by_role("button", name="Pause").click()
    expect(mode).to_have_attribute("data-playing", "false")
    held = mode.get_attribute("data-angle")
    next_frames(page)
    page.wait_for_timeout(200)
    expect(mode).to_have_attribute("data-angle", held)
    mode.get_by_role("button", name="Play").click()
    expect(mode).not_to_have_attribute("data-angle", held)


def test_turns_once_its_tab_is_shown(page: Page) -> None:
    page.goto("/#leg")
    expect(page.locator("#status")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )
    mode = page.locator("#fourbar-mode")
    page.get_by_role("link", name="Four-bar", exact=True).click()
    drawn_to(page, 10)
    page.get_by_role("link", name="Leg", exact=True).click()
    page.get_by_role("link", name="Four-bar", exact=True).click()
    held = mode.get_attribute("data-angle")
    expect(mode).not_to_have_attribute("data-angle", held)
