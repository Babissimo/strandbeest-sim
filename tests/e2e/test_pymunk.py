"""The arena's physics runs in the browser from the site's own files."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, expect

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vendor = script("vendor")
serve = script("serve")

START_TIMEOUT_MS = 60_000
WHEEL = f"./vendor/pyodide/{vendor.PYMUNK_WHEEL}"
# Two ways to load pymunk: PyScript's packages setting (through micropip) as Python starts, or
# Pyodide's loadPackage when the code first needs it. Either way cffi comes from the lock file.
ROUTES = {
    "packages": ({"packages": [WHEEL]}, ""),
    "loadPackage": ({}, f'import pyodide_js\nawait pyodide_js.loadPackage(["cffi", "{WHEEL}"])\n'),
}
# A ball of radius 5 mm dropped from 50 mm, after one second.
PROBE = """
import pymunk
from pyscript import document

space = pymunk.Space()
space.gravity = (0, -9810)
ball = pymunk.Body()
circle = pymunk.Circle(ball, 5)
circle.mass = 1
ball.position = (0, 50)
space.add(pymunk.Segment(space.static_body, (-100, 0), (100, 0), 0), ball, circle)
for _ in range(600):
    space.step(1 / 600)
probe = document.getElementById("probe")
probe.dataset.version = pymunk.version
probe.dataset.height = str(ball.position.y)
probe.dataset.status = "done"
"""


def probe_page(settings: dict, prelude: str) -> str:
    config = {"interpreter": "./vendor/pyodide/pyodide.mjs", **settings}
    return f"""<!doctype html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <title>pymunk probe</title>
  <link rel="icon" href="data:,">
  <script type="module" src="./vendor/pyscript/core.js"></script>
</head>
<body>
  <p id="probe" data-status="loading"></p>
  <script type="py" config='{json.dumps(config)}'>
{prelude}{PROBE}</script>
</body>
</html>
"""


def origin(url: str) -> str:
    parts = urlsplit(url.removeprefix("blob:"))
    return f"{parts.scheme}://{parts.netloc}"


@pytest.mark.parametrize("route", ROUTES)
def test_pymunk_runs_from_vendored_wheels(page: Page, base_url: str, route: str) -> None:
    requested: list[str] = []

    def on_request(request: Request) -> None:
        requested.append(request.url)

    page.context.on("request", on_request)
    html = probe_page(*ROUTES[route])
    # Served beside index.html with the server's headers, so it loads the vendored files as the
    # page does.
    page.route(
        "**/pymunk-probe.html",
        lambda answer: answer.fulfill(
            body=html, content_type="text/html; charset=utf-8", headers=serve.HEADERS
        ),
    )
    page.goto("/pymunk-probe.html")
    probe = page.locator("#probe")
    expect(probe).to_have_attribute("data-status", "done", timeout=START_TIMEOUT_MS)
    assert page.evaluate("self.crossOriginIsolated")
    expect(probe).to_have_attribute("data-version", vendor.PYMUNK_VERSION)
    assert float(probe.get_attribute("data-height")) == pytest.approx(5, abs=0.5)
    elsewhere = [
        url for url in requested if not url.startswith("data:") and origin(url) != base_url
    ]
    assert elsewhere == []
    assert any(url.endswith(vendor.PYMUNK_WHEEL) for url in requested)
