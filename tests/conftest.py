"""Runs scripts/serve.py for the tests that need files served over HTTP."""

import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / "scripts" / "serve.py"
START_TIMEOUT_S = 10.0

# Proxy settings in the environment must not catch requests to the local server.
direct = build_opener(ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def serving(folder: Path) -> Iterator[str]:
    """Serves folder with scripts/serve.py on a free port; yields the base URL, no trailing slash."""
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, str(SERVE), "--port", str(port), "--directory", str(folder)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + START_TIMEOUT_S
        while True:
            try:
                direct.open(url + "/", timeout=1).close()
                break
            except HTTPError as answer:
                answer.close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    pytest.fail(f"scripts/serve.py did not answer on port {port}")
                time.sleep(0.1)
        yield url
    finally:
        server.kill()
        server.wait()


@pytest.fixture(scope="session")
def serve_folder() -> Callable[[Path], AbstractContextManager[str]]:
    """serving() as a fixture, for tests that serve a folder of their own."""
    return serving


@pytest.fixture(scope="session")
def site_url() -> Iterator[str]:
    """The base URL of site/ as scripts/serve.py serves it."""
    with serving(ROOT / "site") as url:
        yield url
