"""One run as the GA worker carries it out: settings and reports as JSON, errors as messages."""
import json

import pytest

from app import job
from beest import ga
from beest.fitness import FitnessSettings
from beest.student_default import SOURCE

SMALL = {"pop": 6, "generations": 4}
# The last line of the default fitness, line 14 of SOURCE.
SCORE = "return (distance + (1 - bob)) / 2"


def request(settings: dict, source: str | None = None) -> str:
    return json.dumps({"settings": settings, "source": source})


def carry_out(settings: dict, source: str | None = None, keep_going=lambda report: True):
    seen = []

    def report(text: str) -> bool:
        seen.append(json.loads(text))
        return keep_going(seen[-1])

    return json.loads(job.run_request(request(settings, source), report)), seen


def test_settings_from_plain_values():
    plain = {
        "preset": "random", "pop": 12, "generations": 7, "budget": 300, "elite": 1,
        "rate": 0.3, "size": 2.5, "crossover": "blend", "mask": ["a", "b", "c"],
        "layout_mutates": True, "seed": 7, "tol": 2.0, "margin": 0.5,
        "fitness": {"weights": {"distance": 1.0, "flatness": 2.0}, "normalisation": "limits",
                    "flip": {"flatness": False}, "limits": {"distance": [-10.0, 20.0]}},
    }
    assert job.settings_from_dict(json.loads(json.dumps(plain))) == ga.RunSettings(
        preset="random", pop=12, generations=7, budget=300, elite=1, rate=0.3, size=2.5,
        crossover="blend", mask=frozenset("abc"), layout_mutates=True, seed=7, tol=2.0,
        margin=0.5, fitness=FitnessSettings(
            weights={"distance": 1.0, "flatness": 2.0}, normalisation="limits",
            flip={"flatness": False}, limits={"distance": (-10.0, 20.0)}))


def test_missing_settings_take_the_defaults():
    assert job.settings_from_dict({}) == ga.RunSettings()
    assert job.settings_from_dict({"fitness": {}}) == ga.RunSettings()


@pytest.mark.parametrize("settings", [{"popsize": 3}, {"fitness": {"weight": {}}}])
def test_unknown_settings_are_refused(settings):
    with pytest.raises(ValueError, match="weight|popsize"):
        job.settings_from_dict(settings)


def test_reports_each_generation():
    result, seen = carry_out(SMALL)
    assert result["status"] == "done"
    assert [report["generation"] for report in seen] == [0, 1, 2, 3]
    assert result["report"] == seen[-1]
    assert seen[-1]["evaluations"] == 24
    assert len(seen[-1]["best_genes"]) == 13


def test_matches_the_engine():
    result, _ = carry_out({**SMALL, "seed": 7})
    assert result["report"] == ga.run(ga.RunSettings(seed=7, **SMALL)).as_dict()


def test_stops_when_told():
    result, seen = carry_out({**SMALL, "generations": 50}, keep_going=lambda r: r["generation"] < 2)
    assert result["status"] == "stopped"
    assert len(seen) == 3
    assert result["report"] == seen[-1]


def test_settings_error_comes_back_as_a_message():
    result, seen = carry_out({"pop": 2, "elite": 2})
    assert seen == []
    assert result["status"] == "error"
    assert result["error"]["kind"] == "settings"
    assert result["error"]["message"].startswith("elite (2) must be smaller than the population")


def test_design_start_from_plain_values():
    settings = job.settings_from_dict({"start": "design", "start_genes": [40.0] * 13})
    assert settings == ga.RunSettings(start="design", start_genes=(40.0,) * 13)


def test_start_that_cannot_be_made_comes_back_as_a_message():
    # No leg keeps every pair of links 50 mm from failing to meet.
    result, seen = carry_out({**SMALL, "start": "turning", "margin": 50})
    assert seen == []
    assert result["status"] == "error"
    assert result["error"]["kind"] == "settings"
    assert f"{ga.START_TRIES} tries" in result["error"]["message"]


def test_student_source_runs():
    result, seen = carry_out(SMALL, SOURCE)
    assert result["status"] == "done"
    assert len(seen) == 4


@pytest.mark.parametrize(
    ("source", "line", "words"),
    [
        ("def fitness(leg)\n    return 0\n", 1, "SyntaxError"),
        (SOURCE.replace(SCORE, "return leg.stride / 0"), 14, "ZeroDivisionError"),
        (SOURCE.replace(SCORE, "return None"), 6, "fitness returned None"),
        ("def fitness(leg):\n    return 0\n", None, "mutate(genes, rate)"),
        (SOURCE.replace(SCORE, "exit()"), 14, "SystemExit on line 14"),
        ("raise SystemExit('bye')\n" + SOURCE, 1, "SystemExit on line 1: bye"),
        ("class Quit(BaseException):\n    pass\nraise Quit()\n", 3, "Quit on line 3"),
    ],
    ids=["syntax", "exception", "returns-none", "missing-mutate", "exit", "exit-at-the-top",
         "base-exception"],
)
def test_student_errors_come_back_with_editor_lines(source, line, words):
    result, _ = carry_out(SMALL, source)
    assert result["status"] == "error"
    error = result["error"]
    assert error["kind"] == "student"
    assert error["line"] == line
    assert words in error["message"]
    if line is not None:
        message = error["message"]
        assert message.startswith(f"Line {line}: ") or f" on line {line}" in message
    if error["traceback"] is not None:
        assert "ga.py" not in error["traceback"]
        assert f'"{ga.EDITOR}", line {line}' in error["traceback"]


@pytest.mark.parametrize("comment", ["", "  # \x0c\u2028"], ids=["plain", "odd-breaks"])
def test_traceback_shows_the_editor_lines(comment):
    # A form feed or line separator in a comment breaks no line for Python.
    source = SOURCE.replace(SCORE, "return leg.stride / 0").replace("import clamp\n",
                                                                     f"import clamp{comment}\n")
    result, _ = carry_out(SMALL, source)
    trace = result["error"]["traceback"]
    assert '"<editor>", line 14, in fitness\n    return leg.stride / 0\n' in trace


def test_crash_comes_back_with_its_traceback(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("broken on purpose")

    monkeypatch.setattr(ga, "run", broken)
    result, _ = carry_out(SMALL)
    assert result["status"] == "error"
    assert result["error"]["kind"] == "crash"
    assert result["error"]["message"] == "RuntimeError: broken on purpose"
    assert "broken on purpose" in result["error"]["traceback"]


def test_unreadable_request_comes_back_as_a_crash():
    result = json.loads(job.run_request("{", lambda text: True))
    assert result["status"] == "error"
    assert result["error"]["kind"] == "crash"
