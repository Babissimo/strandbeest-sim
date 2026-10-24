"""Templates: printed alone, one A4 page per sheet at actual size, and saved as SVG files."""

import re
import xml.etree.ElementTree as ET

import pytest
from playwright.sync_api import Locator, Page, expect

from beest.leg import Layout
from beest.template import leg_template_svg

pytestmark = pytest.mark.e2e

START_TIMEOUT_MS = 90_000
RUN_TIMEOUT_MS = 60_000
# 1 mm in CSS pixels.
PX_PER_MM = 96 / 25.4
# An A4 page in PDF points.
A4_PT = (595.28, 841.89)
LINKS = ("ground", "crank", "coupler", "rocker")


@pytest.fixture
def page(page: Page) -> Page:
    # Counts calls to window.print instead of opening the print dialog. page.pdf() then prints
    # as the dialog would, firing beforeprint and afterprint.
    page.add_init_script("window.printed = 0; window.print = () => { window.printed += 1; };")
    return page


def printed(page: Page) -> int:
    return page.evaluate("window.printed")


def sheets(page: Page) -> Locator:
    return page.locator("#template-print > svg")


def open_mode(page: Page, mode: str) -> Locator:
    page.goto(f"/#{mode}")
    expect(page.locator("#status")).to_have_attribute("data-status", "ready",
                                                      timeout=START_TIMEOUT_MS)
    return page.locator(f"#{mode}-mode")


def run_evolution(page: Page, root: Locator, generations: int) -> None:
    page.locator('input[name="ev-limit"][value="generations"]').check()
    page.locator("#ev-generations").fill(str(generations))
    page.get_by_role("button", name="Run", exact=True).click()
    expect(root).to_have_attribute("data-status", "ready", timeout=RUN_TIMEOUT_MS)
    expect(root).to_have_attribute("data-generation", str(generations - 1))


def assert_only_template_prints(page: Page, pages: int) -> None:
    """Under print media only the template shows, each page 210 mm by 297 mm and unscaled."""
    page.emulate_media(media="print")
    expect(sheets(page)).to_have_count(pages)
    shown = page.evaluate("""() => [...document.body.children]
        .filter(el => getComputedStyle(el).display !== "none").map(el => el.id)""")
    assert shown == ["template-print"]
    expect(page.locator("main")).to_be_hidden()
    expect(page.locator(".masthead")).to_be_hidden()
    for k in range(pages):
        box = sheets(page).nth(k).bounding_box()
        assert box["width"] == pytest.approx(210 * PX_PER_MM, abs=0.5)
        assert box["height"] == pytest.approx(297 * PX_PER_MM, abs=0.5)
    # Printing gives one A4 sheet per page, with no blank sheets between them.
    pdf = page.pdf(prefer_css_page_size=True).decode("latin-1")
    boxes = re.findall(r"/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)\s*\]", pdf)
    assert len(boxes) == pages
    for width, height in boxes:
        assert (float(width), float(height)) == pytest.approx(A4_PT, abs=0.5)
    page.emulate_media(media="screen")


def test_print_media(page: Page) -> None:
    root = open_mode(page, "evolve")
    leg_print = page.get_by_role("button", name="Print the leg template")
    expect(root).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    expect(leg_print).to_be_disabled()
    run_evolution(page, root, 3)
    expect(leg_print).to_be_enabled()
    expect(root).to_contain_text("Actual size")
    leg_print.click()
    assert printed(page) == 1
    pages = int(root.get_attribute("data-template-pages"))
    assert pages >= 1
    expect(sheets(page)).to_have_count(pages)
    # The template is the best beest's: its lengths (shown to 0.1 mm), one crank per pair.
    lengths = dict(page.evaluate("""() => [...document.querySelectorAll('.ev-facts .lengths span')]
        .map(span => [span.firstChild.textContent, Number(span.lastChild.textContent)])"""))
    layout = page.locator(".ev-facts .layout").inner_text()
    pairs = int(re.search(r"(\d+) pairs? of legs", layout)[1])
    sticks = page.locator("#template-print .stick")
    expect(sticks).to_have_count(11)
    for k in range(11):
        stick = sticks.nth(k)
        name = stick.get_attribute("data-name")
        assert float(stick.get_attribute("data-length")) == pytest.approx(lengths[name], abs=0.051)
        expect(stick).to_have_attribute("data-count", str(pairs if name == "m" else 2 * pairs))
    assert_only_template_prints(page, pages)
    # Once printing is over the page prints as itself again.
    assert_page_prints(page)


def assert_page_prints(page: Page) -> None:
    expect(sheets(page)).to_have_count(0)
    expect(page.locator("body")).not_to_have_attribute("data-print", re.compile(".*"))
    page.emulate_media(media="print")
    expect(page.locator("main")).to_be_visible()
    expect(page.locator(".masthead")).to_be_visible()
    page.emulate_media(media="screen")


def test_other_prints_clear_the_template(page: Page) -> None:
    open_mode(page, "fourbar")
    page.get_by_role("button", name="Print the sticks").click()
    # The print the button asked for keeps the template.
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    expect(sheets(page)).to_have_count(1)
    # A later print the page did not ask for (Ctrl+P) clears it, though no afterprint came between.
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert_page_prints(page)


def test_long_template_prints_page_by_page(page: Page) -> None:
    # Every stick at 104 mm and four pairs need three pages.
    pages = leg_template_svg([104.0] * 11 + [-30.0, 104.0], Layout(4))
    assert len(pages) == 3
    open_mode(page, "fourbar")
    page.evaluate("""pages => {
        document.getElementById("template-print").innerHTML = pages.join("");
        document.body.dataset.print = "template";
    }""", pages)
    assert_only_template_prints(page, 3)


def test_four_bar_prints_its_sticks(page: Page) -> None:
    root = open_mode(page, "fourbar")
    lengths = {"ground": 70.5, "crank": 15.0, "coupler": 80.25, "rocker": 60.0}
    for name, value in lengths.items():
        page.locator(f"#fourbar-{name}").fill(str(value))
    page.get_by_role("button", name="Print the sticks").click()
    assert printed(page) == 1
    expect(root).to_have_attribute("data-template-pages", "1")
    sticks = page.locator("#template-print .stick")
    assert [sticks.nth(k).get_attribute("data-name") for k in range(4)] == list(LINKS)
    for k, name in enumerate(LINKS):
        assert float(sticks.nth(k).get_attribute("data-length")) == pytest.approx(lengths[name])
        expect(sticks.nth(k)).to_have_attribute("data-count", "1")
    expect(root).to_contain_text("Actual size")
    assert_only_template_prints(page, 1)


def test_four_bar_downloads_svg(page: Page) -> None:
    open_mode(page, "fourbar")
    page.locator("#fourbar-crank").fill("25")
    with page.expect_download() as download:
        page.locator("#fourbar-mode").get_by_role("button", name="Download SVG").click()
    saved = download.value
    assert saved.suggested_filename == "four-bar-template.svg"
    svg = ET.parse(saved.path()).getroot()
    assert (svg.get("width"), svg.get("height")) == ("210mm", "297mm")
    assert svg.get("viewBox") == "0 0 210 297"
    crank = [g for g in svg.iter() if g.get("data-name") == "crank"]
    assert [float(g.get("data-length")) for g in crank] == [25.0]
    # Saving prints nothing.
    assert printed(page) == 0
    expect(sheets(page)).to_have_count(0)
