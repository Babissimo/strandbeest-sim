"""The page shell: Python starts from the site's own files, and the tabs switch modes."""

import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

pytestmark = pytest.mark.e2e

MODES = {"fourbar": "Four-bar", "leg": "Leg", "evolve": "Evolve"}
START_TIMEOUT_MS = 60_000


def origin(url: str) -> str:
    # A blob: URL carries the origin of the page that made it.
    parts = urlsplit(url.removeprefix("blob:"))
    return f"{parts.scheme}://{parts.netloc}"


def expect_only(page: Page, mode: str) -> None:
    for name, label in MODES.items():
        section = page.locator(f"#{name}-mode")
        tab = page.get_by_role("link", name=label, exact=True)
        if name == mode:
            expect(section).to_be_visible()
            expect(tab).to_have_attribute("aria-current", "page")
        else:
            expect(section).to_be_hidden()
            expect(tab).not_to_have_attribute("aria-current", "page")


def test_page_starts_python(page: Page, base_url: str) -> None:
    requested: list[str] = []

    def on_request(request: Request) -> None:
        requested.append(request.url)

    # The context also sees requests made by workers.
    page.context.on("request", on_request)
    page.goto("/")
    status = page.locator("#status")
    expect(status).to_have_attribute("data-status", "ready", timeout=START_TIMEOUT_MS)
    expect(status).to_have_attribute("data-python", "3.14.2")
    assert page.evaluate("self.crossOriginIsolated")
    elsewhere = [
        url for url in requested if not url.startswith("data:") and origin(url) != base_url
    ]
    assert requested and elsewhere == []


@pytest.mark.page_errors_expected
@pytest.mark.parametrize(
    ("path", "reply"),
    [
        ("app/main.py", {"body": "raise RuntimeError('broken on purpose')"}),
        ("vendor/pyodide/pyodide.mjs", {"status": 404}),
        ("vendor/pyscript/core.js", {"status": 404}),
    ],
    ids=["python-raises", "pyodide-missing", "pyscript-missing"],
)
def test_start_up_error_is_shown(
    page: Page, page_errors: list[str], path: str, reply: dict
) -> None:
    page.route(f"**/{path}", lambda route: route.fulfill(**reply))
    page.goto("/")
    status = page.locator("#status")
    expect(status).to_have_attribute("data-status", "error", timeout=START_TIMEOUT_MS)
    expect(status).to_have_text("Python could not start. Try reloading the page.")
    assert page_errors


def test_tabs_switch(page: Page) -> None:
    page.goto("/")
    expect_only(page, "fourbar")
    page.goto("/#leg")
    expect_only(page, "leg")
    for mode, label in [("evolve", "Evolve"), ("fourbar", "Four-bar"), ("leg", "Leg")]:
        page.get_by_role("link", name=label, exact=True).click()
        expect(page).to_have_url(re.compile(f"#{mode}$"))
        expect_only(page, mode)
    page.goto("/#nowhere")
    expect_only(page, "fourbar")
    page.reload()
    expect_only(page, "fourbar")
    page.goto("/#evolve")
    page.reload()
    expect_only(page, "evolve")
    expect(page.locator("#status")).to_have_attribute(
        "data-status", "ready", timeout=START_TIMEOUT_MS
    )
