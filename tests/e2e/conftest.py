"""Browser test set-up: the served site, the Chromium to launch, and errors the page logs."""

import os
from collections.abc import Iterator

import pytest
from playwright.sync_api import BrowserContext, ConsoleMessage, Page


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    # E2E_CHROMIUM names a Chromium to launch instead of the one Playwright installs.
    chromium = os.environ.get("E2E_CHROMIUM")
    if chromium:
        return {**browser_type_launch_args, "executable_path": chromium}
    return browser_type_launch_args


@pytest.fixture(scope="session")
def base_url(site_url: str) -> str:
    """pytest-playwright gives every page this base, so tests can write page.goto("/#leg")."""
    return site_url


@pytest.fixture
def page_errors() -> list[str]:
    """Console errors and uncaught exceptions from the test's page, in order."""
    return []


@pytest.fixture
def page(context: BrowserContext, page_errors: list[str]) -> Iterator[Page]:
    page = context.new_page()

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            page_errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    yield page


def logged(errors: list[str]) -> str:
    return "the page logged errors:\n" + "\n".join(errors)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    # A test whose page logged an error fails, even when its own checks passed, unless it is
    # marked page_errors_expected. A test that fails anyway shows the errors with its failure.
    errors = item.funcargs.get("page_errors")
    try:
        result = yield
    except BaseException as failure:
        if errors:
            failure.add_note(logged(errors))
        raise
    page = item.funcargs.get("page")
    if page is None or errors is None or item.get_closest_marker("page_errors_expected"):
        return result
    if not page.is_closed():
        # Playwright hands over events only during a call, so one more call collects the last.
        page.evaluate("0")
    if errors:
        pytest.fail(logged(errors), pytrace=False)
    return result
