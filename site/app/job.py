"""One run as the GA worker carries it out: settings in, a report per generation out, as JSON.

Nothing here touches the browser, so the page and the worker share it and the tests run it under
CPython. A request is `{"settings": {...}, "source": str | null}`: with a source, the editor's
`fitness` and `mutate` score and mutate the beests; without one, the settings do.
"""
from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from dataclasses import fields

from beest import ga
from beest.fitness import FitnessSettings
from beest.student_default import student_functions

_RUN_FIELDS = {f.name for f in fields(ga.RunSettings)}
_FITNESS_FIELDS = {f.name for f in fields(FitnessSettings)}


def _refuse_unknown(data: dict, known: set[str]) -> None:
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(unknown)}")


def fitness_from_dict(data: dict) -> FitnessSettings:
    _refuse_unknown(data, _FITNESS_FIELDS)
    data = dict(data)
    if "limits" in data:
        data["limits"] = {name: tuple(pair) for name, pair in data["limits"].items()}
    return FitnessSettings(**data)


def settings_from_dict(data: dict) -> ga.RunSettings:
    """RunSettings from plain JSON values; a missing setting takes its default.

    Raises ValueError with the engine's message when a setting is out of range.
    """
    _refuse_unknown(data, _RUN_FIELDS)
    data = dict(data)
    if "mask" in data:
        data["mask"] = frozenset(data["mask"])
    if "fitness" in data:
        data["fitness"] = fitness_from_dict(data["fitness"])
    return ga.RunSettings(**data)


def _editor_frames(exc: BaseException) -> traceback.StackSummary:
    frames = traceback.extract_tb(exc.__traceback__)
    return traceback.StackSummary.from_list([f for f in frames if f.filename == ga.EDITOR])


def _told(kind: str, message: str, line: int | None = None, trace: str | None = None) -> dict:
    return {"kind": kind, "message": message, "line": line, "traceback": trace}


def failure(exc: BaseException) -> dict:
    """What went wrong during a run, for the page: `kind`, a plain `message`, the editor `line`
    and a `traceback` (both None when they do not apply).

    kind is "student" for the editor's code (its traceback keeps only the editor's lines) and
    "crash" for anything else.
    """
    if isinstance(exc, SyntaxError) and exc.filename == ga.EDITOR:
        return _told("student", f"{type(exc).__name__} on line {exc.lineno}: {exc.msg}",
                     exc.lineno, "".join(traceback.format_exception_only(exc)))
    if isinstance(exc, ga.StudentCodeError):
        return _told("student", exc.message, exc.line)
    detail = f": {exc}" if str(exc) else ""
    frames = _editor_frames(exc)
    if frames:
        line = frames[-1].lineno
        trace = ("Traceback (most recent call last):\n" + "".join(frames.format())
                 + "".join(traceback.format_exception_only(exc)))
        return _told("student", f"{type(exc).__name__} on line {line}{detail}", line, trace)
    return _told("crash", f"{type(exc).__name__}{detail}",
                 trace="".join(traceback.format_exception(exc)))


def run_request(request: str, report: Callable[[str], object]) -> str:
    """Carry out one request and say how it ended, as JSON.

    `report` gets each generation's report as JSON; when it returns False the run stops. The
    answer is `{"status": "done" | "stopped", "report": <last report>}` or
    `{"status": "error", "error": {...}}`, the error as failure() gives it or, for settings the
    engine refuses, of kind "settings"; no exception escapes.
    """
    stopped = False

    def on_generation(generation: ga.Report) -> bool:
        nonlocal stopped
        stopped = report(json.dumps(generation.as_dict())) is False
        return not stopped

    try:
        asked = json.loads(request)
        try:
            settings = settings_from_dict(asked["settings"])
        except ValueError as exc:
            return json.dumps({"status": "error", "error": _told("settings", str(exc))})
        source = asked.get("source")
        fitness_fn, mutate_fn = (None, None) if source is None else student_functions(source)
        last = ga.run(settings, fitness_fn, mutate_fn, on_generation)
    # exit() in the editor raises SystemExit, which must come back as a message like the rest.
    except BaseException as exc:
        return json.dumps({"status": "error", "error": failure(exc)})
    return json.dumps({"status": "stopped" if stopped else "done", "report": last.as_dict()})
