"""The GA worker: runs evolution off the page's main thread, so the page stays responsive.

The page sets `sync.report` before calling `sync.run(request)`; see app.job for the request, the
reports and the answer. Stopping a run, or code that never returns, is the page's job: it
terminates this worker and starts a fresh one.
"""
from pyscript import sync

from app.job import run_request


def run(request: str) -> str:
    return run_request(request, lambda report: sync.report(report))


def started() -> bool:
    """The page's check that this script ran to the end: the worker counts as ready even when
    the script raised, and then has no `run`."""
    return True


sync.run = run
sync.started = started
