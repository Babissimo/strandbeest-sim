"""scripts/survey_limits.py moves two of the surveyed limits out past Jansen (decisions Q5)."""
import importlib.util
import json
from pathlib import Path

from beest.fitness import LIMITS_FILE

spec = importlib.util.spec_from_file_location(
    "survey_limits", Path(__file__).resolve().parents[1] / "scripts" / "survey_limits.py")
survey_limits = importlib.util.module_from_spec(spec)
spec.loader.exec_module(survey_limits)


def test_widened_moves_only_distance_top_and_flatness_best():
    surveyed = {"distance": [-300.0, 150.0], "stride": [4.0, 30.0], "flatness": [1.0, 12.0],
                "upright": [0.0, 1.0]}
    assert survey_limits.widened(surveyed, 170.123456) == {
        "distance": [-300.0, 340.2469], "stride": [4.0, 30.0], "flatness": [0.0, 12.0],
        "upright": [0.0, 1.0]}
    assert surveyed["distance"] == [-300.0, 150.0]
    assert surveyed["flatness"] == [1.0, 12.0]


def test_limits_file_records_the_widening():
    data = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
    assert data["distance_top_jansen_times"] == survey_limits.DISTANCE_TOP_JANSEN_TIMES == 2
    assert data["flatness_best_mm"] == survey_limits.FLATNESS_BEST_MM == 0.0
