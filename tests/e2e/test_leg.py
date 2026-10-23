"""Leg playground: Jansen's leg and its stride, a leg that jams part-way round, and the reset."""

import math

import pytest
from playwright.sync_api import Locator, Page, expect

from beest.geometry import DRAW_ANGLES, LENGTH_NAMES, trace_leg
from beest.leg import DOWN_TOLERANCE_MM, LENGTH_BOUNDS, MM_PER_UNIT, jansen_lengths
from beest.measures import foot_measures

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 60_000
JANSEN = dict(zip(LENGTH_NAMES, jansen_lengths()))


def open_leg(page: Page) -> Locator:
    page.goto("/#leg")
    expect(page.locator("#status")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )
    return page.locator("#leg-mode")


def set_lengths(page: Page, **lengths: float) -> None:
    """Types each length into its number box, as a student would."""
    for name, value in lengths.items():
        page.locator(f"#leg-{name}").fill(f"{value:g}")


def shown(mode: Locator, name: str) -> float:
    return float(mode.get_attribute(f"data-{name}"))


def drawn_to(page: Page, degrees: int, timeout: float = 15_000) -> None:
    """Waits until the animation has drawn the leg at `degrees` or further round."""
    page.wait_for_function(
        "degrees => Number(document.querySelector('#leg-mode').dataset.drawnTo) >= degrees",
        arg=degrees,
        timeout=timeout,
    )


def play(mode: Locator) -> None:
    """Presses Play: the leg starts paused."""
    mode.get_by_role("button", name="Play").click()
    expect(mode).to_have_attribute("data-playing", "true")


def next_frames(page: Page) -> None:
    """Waits for two animation frames, so the page has drawn at least once since the last change."""
    page.evaluate(
        "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
    )


def expect_jansen(page: Page, mode: Locator) -> None:
    for name, value in JANSEN.items():
        expect(mode).to_have_attribute(f"data-{name}", str(value))
    expect(mode).to_have_attribute("data-jammed", "false")
    measures = foot_measures(trace_leg(JANSEN).foot, DOWN_TOLERANCE_MM)
    expect(mode).not_to_have_attribute("data-stride", "")
    assert shown(mode, "stride") == pytest.approx(measures.stride, abs=0.05)
    expect(page.locator("#leg-stride")).to_have_text(f"{measures.stride:.1f} mm")


def test_shows_jansen_stride(page: Page) -> None:
    mode = open_leg(page)
    expect_jansen(page, mode)
    trace = trace_leg(JANSEN)
    measures = foot_measures(trace.foot, DOWN_TOLERANCE_MM)
    assert shown(mode, "tolerance") == DOWN_TOLERANCE_MM
    assert shown(mode, "step-height") == pytest.approx(measures.step_height, abs=0.05)
    assert shown(mode, "time-down") == pytest.approx(measures.time_down, abs=0.005)
    assert shown(mode, "closest-to-jam") == pytest.approx(trace.closest_to_jam, abs=0.05)
    expect(page.locator("#leg-jam")).to_be_hidden()
    play(mode)
    drawn_to(page, 350)


def test_partial_jam_draws(page: Page) -> None:
    mode = open_leg(page)
    # Jansen's crank made 10% longer.
    m = 16.5 * MM_PER_UNIT
    set_lengths(page, m=m)
    expect(mode).to_have_attribute("data-jammed", "true")
    warning = page.locator("#leg-jam")
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("f and g")
    trace = trace_leg({**JANSEN, "m": round(m, 2)}, n=DRAW_ANGLES)
    assert trace.jammed and abs(math.degrees(trace.jam_angle) - 182) <= 2
    expect(warning).to_contain_text(trace.jam_reason)
    # The leg swings up to its last position before the jam, and no further.
    last = round(math.degrees(trace.angles[-1]))
    assert abs(last - 182) <= 2
    play(mode)
    drawn_to(page, last)
    next_frames(page)
    expect(mode).to_have_attribute("data-drawn-to", str(last))
    for name in ("stride", "step-height", "time-down", "closest-to-jam"):
        expect(mode).to_have_attribute(f"data-{name}", "")


def jams(lengths: dict[str, float]) -> bool:
    """A leg jams if it jams at either the scoring or the drawing angles."""
    return trace_leg(lengths).jammed or trace_leg(lengths, n=DRAW_ANGLES).jammed


def test_paused_leg_redraws_when_a_length_changes(page: Page) -> None:
    mode = open_leg(page)
    expect(mode).to_have_attribute("data-playing", "false")
    expect(mode).to_have_attribute("data-drawn-to", "0")
    set_lengths(page, j=55)
    expect(mode).to_have_attribute("data-j", "55.0")
    expect(mode).to_have_attribute("data-drawn-to", "0")
    page.wait_for_timeout(300)
    expect(mode).to_have_attribute("data-angle", "0")


def test_reset_restores_jansen(page: Page) -> None:
    mode = open_leg(page)
    changes = {"a": 40, "l": -5, "m": 19.8}
    assert jams({**JANSEN, **changes})
    set_lengths(page, **changes)
    expect(mode).to_have_attribute("data-a", "40.0")
    expect(mode).to_have_attribute("data-l", "-5.0")
    expect(mode).to_have_attribute("data-jammed", "true")
    expect(page.locator("#leg-jam")).to_be_visible()
    page.get_by_role("button", name="Reset to Jansen").click()
    expect_jansen(page, mode)
    expect(page.locator("#leg-c")).to_have_value("47.16")
    expect(page.locator("#leg-jam")).to_be_hidden()


def test_tolerance_changes_stride(page: Page) -> None:
    mode = open_leg(page)
    box = page.locator("#leg-tolerance")
    # Q4 bounds the tolerance to 0.5–4 mm.
    box.fill("9")
    box.press("Enter")
    expect(mode).to_have_attribute("data-tolerance", "4.0")
    expect(box).to_have_value("4")
    measures = foot_measures(trace_leg(JANSEN).foot, 4.0)
    expect(page.locator("#leg-stride")).to_have_text(f"{measures.stride:.1f} mm")
    expect(page.locator("#leg-jansen-stride")).to_have_text(f"{measures.stride:.1f} mm")
    assert shown(mode, "time-down") == pytest.approx(measures.time_down, abs=0.005)


@pytest.mark.parametrize(
    "changes",
    [
        {name: low for name, (low, _) in LENGTH_BOUNDS.items()},
        {name: high for name, (_, high) in LENGTH_BOUNDS.items()},
        {"l": LENGTH_BOUNDS["l"][0]},
        {"l": LENGTH_BOUNDS["l"][1]},
        {"m": LENGTH_BOUNDS["m"][0]},
    ],
    ids=["all-lower", "all-upper", "l-lower", "l-upper", "m-lower"],
)
def test_lengths_at_their_bounds(page: Page, changes: dict[str, float]) -> None:
    mode = open_leg(page)
    set_lengths(page, **changes)
    for name, value in changes.items():
        expect(mode).to_have_attribute(f"data-{name}", str(value))
    jammed = jams({**JANSEN, **changes})
    expect(mode).to_have_attribute("data-jammed", str(jammed).lower())
    expect(page.locator("#leg-jam")).to_be_visible(visible=jammed)
    if not jammed:
        expect(mode).not_to_have_attribute("data-stride", "")
        play(mode)
        drawn_to(page, 350)
    next_frames(page)


def test_jam_only_at_scoring_angles(page: Page) -> None:
    # This leg closes its turn at DRAW_ANGLES but not at the ANGLES the GA scores at.
    lengths = {"a": 39.9, "b": 51.0, "c": 39.0, "d": 35.9, "e": 64.7, "f": 35.3, "g": 33.0,
               "h": 80.8, "i": 50.2, "j": 66.7, "k": 58.7, "l": 6.9, "m": 20.5}
    scored = trace_leg(lengths)
    assert scored.jammed and not trace_leg(lengths, n=DRAW_ANGLES).jammed
    mode = open_leg(page)
    set_lengths(page, **lengths)
    expect(mode).to_have_attribute("data-jammed", "true")
    expect(page.locator("#leg-jam")).to_contain_text(scored.jam_reason)
    expect(page.locator("#leg-jam")).to_contain_text("swing back and forth")
    expect(mode).to_have_attribute("data-stride", "")
    # The scored trace is the one drawn, swinging through its whole turn.
    play(mode)
    drawn_to(page, round(math.degrees(scored.angles[-1])))
