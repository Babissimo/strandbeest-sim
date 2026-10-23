"""The code route: the editor's fitness and mutate run, fail with editor line numbers, are
stopped when they never return, and are kept by the browser."""

import re

import pytest
from playwright.sync_api import Page, expect

from beest import ga
from beest.student_default import SOURCE, student_functions

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 90_000
RUN_TIMEOUT_MS = 60_000
# The last line of the default fitness, line 9 of SOURCE, inside `def fitness` on line 6.
SCORE = "return leg.stride + 0.5 * leg.step_height"
FITNESS_LINE = 6
SCORE_LINE = 9
# Fails on the 601st beest scored, as generation 20 (counting from 0) is scored; line 12 raises.
LATE = SOURCE.replace("def fitness(leg):\n", """calls = []


def fitness(leg):
    calls.append(1)
    if len(calls) > 600:
        raise ValueError("late")
""")


def mode(page: Page):
    return page.locator("#evolve-mode")


def open_evolve(page: Page) -> None:
    page.goto("/#evolve")
    expect(mode(page)).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)


@pytest.fixture
def code(page: Page) -> Page:
    """Evolve on the code route, its worker ready."""
    open_evolve(page)
    page.get_by_label("my code").check()
    expect(mode(page)).to_have_attribute("data-route", "code")
    return page


# app/editor.js keeps the editor's handle on its element as `editor`; its setText changes the
# text as typing would, so the page saves it too.
def set_code(page: Page, source: str) -> None:
    page.locator(".ev-editor").evaluate("(host, text) => host.editor.setText(text)", source)


def code_text(page: Page) -> str:
    return page.locator(".ev-editor").evaluate("host => host.editor.getText()")


def stop_after(page: Page, generations: int) -> None:
    page.locator('input[name="ev-limit"][value="generations"]').check()
    page.locator("#ev-generations").fill(str(generations))


def run(page: Page) -> None:
    page.get_by_role("button", name="Run", exact=True).click()


def run_and_wait(page: Page) -> None:
    run(page)
    expect(mode(page)).to_have_attribute("data-status", "ready", timeout=RUN_TIMEOUT_MS)
    expect(mode(page)).not_to_have_attribute("data-error", re.compile(".*"))


def expect_halted(page: Page, line: int, message: str, marked: str) -> None:
    """The run stopped on an error in the code before any generation was scored; the message
    names `line`, whose text is `marked`, and the editor marks it."""
    root = mode(page)
    expect(root).to_have_attribute("data-error-line", str(line), timeout=RUN_TIMEOUT_MS)
    expect(root).to_have_attribute("data-error", message)
    expect(page.locator(".ev-code-error")).to_have_text(message)
    expect(page.locator(".ev-editor .error-line")).to_have_text([marked])
    expect(root).to_have_attribute("data-series", "0")
    expect(page.locator(".ev-progress")).to_contain_text(
        "Your code stopped the run after 0 generations")
    # Each run of code gets a fresh worker.
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)


def test_default_code_runs(code: Page) -> None:
    assert code_text(code) == SOURCE
    numbers = code.locator(".ev-editor .cm-lineNumbers .cm-gutterElement")
    expect(numbers.last).to_have_text(str(len(SOURCE.split("\n"))))
    # The code's fitness and mutate take over from the weights, flips and mutation size, and
    # normalisation still fills leg.normalised.
    for key in ("w-distance", "flip-flatness", "size"):
        expect(code.locator(f"#ev-{key}")).to_be_disabled()
    for key in ("normalisation", "rate", "pop"):
        expect(code.locator(f"#ev-{key}")).to_be_enabled()
    stop_after(code, 10)
    run_and_wait(code)
    root = mode(code)
    expect(root).to_have_attribute("data-points", "10")
    expected = ga.run(ga.RunSettings(generations=10), *student_functions(SOURCE))
    assert root.get_attribute("data-best-score") == repr(expected.best_score)
    expect(code.locator(".ev-legend li")).to_have_text(["Run 1: GA, your code, seed 1"])
    # Back on the settings route, the same settings score by the panel.
    code.get_by_label("the settings").check()
    expect(root).to_have_attribute("data-route", "settings")
    expect(code.locator(".code-panel")).to_be_hidden()
    expect(code.locator("#ev-w-distance")).to_be_enabled()
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    run_and_wait(code)
    expect(code.locator(".ev-legend li").last).to_have_text("Run 2: GA, seed 1")


def test_syntax_error_names_line(code: Page) -> None:
    set_code(code, SOURCE.replace("def fitness(leg):", "def fitness(leg)"))
    run(code)
    expect_halted(code, FITNESS_LINE, "SyntaxError on line 6: expected ':'", "def fitness(leg)")
    expect(code.locator(".ev-error")).to_be_hidden()
    # Code put in with the marked line changed takes the mark away, and leaves the message.
    set_code(code, SOURCE.replace("def fitness(leg):", "def fitness(leg) :"))
    expect(code.locator(".ev-editor .error-line")).to_have_count(0)
    expect(code.locator(".ev-code-error")).to_be_visible()
    # Back to the slide code, the message goes, and the code runs.
    code.once("dialog", lambda dialog: dialog.accept())
    code.get_by_role("button", name="Reset to slide code").click()
    assert code_text(code) == SOURCE
    expect(code.locator(".ev-code-error")).to_be_hidden()
    expect(mode(code)).not_to_have_attribute("data-error", re.compile(".*"))
    expect(mode(code)).not_to_have_attribute("data-error-line", re.compile(".*"))
    stop_after(code, 2)
    run_and_wait(code)
    expect(mode(code)).to_have_attribute("data-points", "2")


def test_exception_shows_traceback(code: Page) -> None:
    set_code(code, SOURCE.replace(SCORE, "return leg.stride / 0"))
    run(code)
    expect_halted(code, SCORE_LINE, "ZeroDivisionError on line 9: division by zero",
                  "    return leg.stride / 0")
    traceback = code.locator(".ev-traceback")
    expect(traceback).to_be_visible()
    traceback.locator("summary").click()
    shown = traceback.locator("pre")
    expect(shown).to_be_visible()
    expect(shown).to_contain_text('File "<editor>", line 9, in fitness')
    expect(shown).to_contain_text("return leg.stride / 0")
    expect(shown).to_contain_text("ZeroDivisionError: division by zero")
    # Only the editor's lines: none of the simulator's own.
    expect(shown).not_to_contain_text(".py")
    # A line added above the marked one moves the mark with it; typing in it takes it away.
    marked = code.locator(".ev-editor .error-line")
    code.locator(".ev-editor .cm-line").nth(SCORE_LINE - 2).click()
    code.keyboard.press("End")
    code.keyboard.press("Enter")
    expect(marked).to_have_text(["    return leg.stride / 0"])
    # Home goes to the end of the indent, and Enter there moves the line down whole.
    marked.click()
    code.keyboard.press("Home")
    code.keyboard.press("Enter")
    expect(marked).to_have_text(["    return leg.stride / 0"])
    code.keyboard.press("End")
    code.keyboard.type(" + 1")
    expect(marked).to_have_count(0)
    # An error part-way through keeps the generations that were scored.
    set_code(code, LATE)
    run(code)
    root = mode(code)
    expect(root).to_have_attribute("data-status", "running")
    # Code edited meanwhile no longer has the line that failed, so nothing is marked.
    set_code(code, "# A new first line\n" + LATE)
    # With the editor hidden meanwhile, the message shows beside Run.
    code.get_by_label("the settings").check()
    late = "ValueError on line 12: late"
    expect(root).to_have_attribute("data-error", late, timeout=RUN_TIMEOUT_MS)
    expect(code.locator(".ev-error")).to_have_text(late)
    expect(root).to_have_attribute("data-error-line", "12")
    expect(root).to_have_attribute("data-points", "20")
    expect(code.locator(".ev-legend li")).to_have_text(
        ["Run 1: GA, your code, seed 1 (ended by an error in your code)"])
    expect(code.locator(".ev-progress")).to_contain_text(
        "Your code stopped the run after 20 generations, 600 beests scored")
    code.get_by_label("my code").check()
    expect(code.locator(".ev-code-error")).to_have_text(late)
    expect(code.locator(".ev-error")).to_be_hidden()
    expect(code.locator(".ev-editor .error-line")).to_have_count(0)


def test_fitness_returning_none_or_nan(code: Page) -> None:
    set_code(code, SOURCE.replace(SCORE, "return None"))
    run(code)
    expect_halted(code, FITNESS_LINE,
                  "Line 6: fitness returned None, but it must return an ordinary number. "
                  "Check that every way through it ends with return.", "def fitness(leg):")
    expect(code.locator(".ev-traceback")).to_be_hidden()
    set_code(code, SOURCE.replace(SCORE, "return float('nan')"))
    run(code)
    expect_halted(code, FITNESS_LINE,
                  "Line 6: fitness returned nan, but it must return an ordinary number.",
                  "def fitness(leg):")


def test_endless_loop_stop(code: Page) -> None:
    set_code(code, SOURCE.replace(SCORE, "while True:\n        pass"))
    run(code)
    root = mode(code)
    expect(root).to_have_attribute("data-status", "running")
    code.wait_for_timeout(1_500)
    expect(root).to_have_attribute("data-status", "running")
    # The page answers while the worker loops.
    code.locator("#ev-seed").fill("2")
    code.get_by_role("button", name="Stop", exact=True).click()
    expect(root).to_have_attribute("data-status", "ready", timeout=10_000)
    expect(code.locator(".ev-progress")).to_contain_text("Stopped after 0 generations")
    expect(root).to_have_attribute("data-series", "0")
    # The fresh worker runs mended code to the end.
    set_code(code, SOURCE)
    stop_after(code, 3)
    run_and_wait(code)
    expect(root).to_have_attribute("data-points", "3")
    expect(code.locator(".ev-legend li")).to_have_text(["Run 1: GA, your code, seed 2"])


def test_code_survives_reload(code: Page) -> None:
    changed = SOURCE.replace("0.5 * leg.step_height", "0.25 * leg.step_height")
    set_code(code, changed)
    code.reload()
    expect(mode(code)).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    expect(mode(code)).to_have_attribute("data-route", "code")
    expect(code.get_by_label("my code")).to_be_checked()
    assert code_text(code) == changed
    # Reset asks first, and keeps the code when the answer is no. It leaves a message about the
    # settings alone.
    code.locator("#ev-pop").fill("")
    run(code)
    expect(code.locator(".ev-error")).to_have_text("Population needs a number.")
    reset = code.get_by_role("button", name="Reset to slide code")
    questions = []

    def answer(dialog, accept: bool) -> None:
        questions.append(dialog.message)
        dialog.accept() if accept else dialog.dismiss()

    code.once("dialog", lambda dialog: answer(dialog, False))
    reset.click()
    assert code_text(code) == changed
    code.once("dialog", lambda dialog: answer(dialog, True))
    reset.click()
    assert code_text(code) == SOURCE
    assert len(questions) == 2
    expect(code.locator(".ev-error")).to_have_text("Population needs a number.")
    # The slide code itself is not kept, so new slide code on the site shows after a reload.
    assert code.evaluate("localStorage.getItem('strandbeest-sim.code')") is None
    code.reload()
    expect(mode(code)).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    assert code_text(code) == SOURCE


def test_blocked_storage(page: Page) -> None:
    # As when the browser blocks storage for the site: reading it throws.
    page.add_init_script("""
        Object.defineProperty(window, "localStorage", {
          get() { throw new DOMException("The operation is insecure.", "SecurityError"); },
        });
    """)
    open_evolve(page)
    page.get_by_label("my code").check()
    assert code_text(page) == SOURCE
    expect(page.locator(".ev-not-kept")).to_be_hidden()
    set_code(page, SOURCE.replace("0.5 * leg.step_height", "0.25 * leg.step_height"))
    expect(page.locator(".ev-not-kept")).to_be_visible()
    set_code(page, SOURCE)
    expect(page.locator(".ev-not-kept")).to_be_hidden()
    set_code(page, SOURCE.replace("0.5 * leg.step_height", "0.25 * leg.step_height"))
    stop_after(page, 2)
    run_and_wait(page)
    expect(mode(page)).to_have_attribute("data-points", "2")
