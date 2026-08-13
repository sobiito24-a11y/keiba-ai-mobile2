from __future__ import annotations

from copy import deepcopy

import pandas as pd

from core.condition_fit import (
    canonical_condition_fit_level,
    evaluate_condition_fit,
    extract_condition_fit_sources,
)
from core.models import PredictionResult
from core.ver4_engine import apply_prediction_logic, evaluate_ver4_table


RACE_INFO = {"venue": "門別", "distance": 1200, "turn": "右"}


def base_row(number: int = 1) -> dict:
    return {
        "馬番": number,
        "馬名": f"Horse{number}",
        "馬年齢": "牡4",
        "3走前": 78,
        "2走前": 80,
        "前走": 82,
        "平均指数": 80,
        "過去1年最高指数": 84,
        "距離指数": 80,
        "コース指数": 80,
        "AI点": 91,
        "raw_score": 123.4,
        "ability_display_score": 88.8,
        "展開印": "○",
    }


def past_run(venue: str, distance: int, turn: str, value: int = 70) -> dict:
    return {
        "label": "前走",
        "racecourse": venue,
        "distance": distance,
        "direction": turn,
        "surface": "ダ",
        "race_date": "2026-08-01",
        "position": "2",
        "value": value,
    }


def test_condition_fit_marks_and_statuses_are_distinct() -> None:
    cases = [
        (past_run("門別", 1200, "右"), "★", "same_venue_distance"),
        (past_run("大井", 1200, "右"), "☆", "same_turn_distance"),
        (past_run("船橋", 1200, "左"), "※", "same_distance"),
    ]
    for run, mark, level in cases:
        result = evaluate_condition_fit({"_past_runs": [run]}, RACE_INFO)
        assert result["condition_fit_mark"] == mark
        assert result["condition_fit_level"] == level
        assert result["condition_fit_data_status"] == "ok"

    no_match = evaluate_condition_fit(
        {"_past_runs": [past_run("門別", 1000, "右")]},
        RACE_INFO,
    )
    assert no_match["condition_fit_mark"] is None
    assert no_match["condition_fit_level"] == "none"
    assert no_match["condition_fit_data_status"] == "no_match"

    missing = evaluate_condition_fit(base_row(), RACE_INFO)
    assert missing["condition_fit_mark"] is None
    assert missing["condition_fit_level"] == "none"
    assert missing["condition_fit_data_status"] == "missing_source_data"


def test_known_same_distance_is_kept_when_venue_and_turn_are_missing() -> None:
    result = evaluate_condition_fit(
        {"_past_runs": [{"label": "前走", "distance": 1200, "value": 70}]},
        RACE_INFO,
    )
    assert result["condition_fit_mark"] == "※"
    assert result["condition_fit_level"] == "same_distance"
    assert result["condition_fit_data_status"] == "ok"


def test_legacy_star_aliases_only_map_semantically_known_values() -> None:
    assert canonical_condition_fit_level("venue_distance") == "same_venue_distance"
    assert canonical_condition_fit_level("venue_distance_surface_turn") == "same_venue_distance"
    assert canonical_condition_fit_level("same_turn_distance") == "same_turn_distance"
    assert canonical_condition_fit_level("unknown_level") is None


def test_source_map_is_horse_keyed_copied_and_result_free() -> None:
    raw = base_row()
    raw["_past_runs"] = [past_run("門別", 1200, "右")]
    raw["finish"] = 1
    frame = pd.DataFrame([raw])

    sources = extract_condition_fit_sources(frame)

    assert set(sources) == {"1"}
    assert sources["1"]["_past_runs"][0]["racecourse"] == "門別"
    assert "finish" not in sources["1"]
    sources["1"]["_past_runs"][0]["racecourse"] = "changed"
    assert frame.iloc[0]["_past_runs"][0]["racecourse"] == "門別"


def test_v41_connects_hidden_past_runs_without_mutating_source_tables() -> None:
    display = pd.DataFrame([base_row()])
    raw = base_row()
    raw["_past_runs"] = [past_run("門別", 1200, "右", 76)]
    source_map = extract_condition_fit_sources(pd.DataFrame([raw]))
    result = PredictionResult(
        race_mode="nar",
        race_info=RACE_INFO,
        overall_table=display.copy(deep=True),
        horse_evaluation=display.copy(deep=True),
        debug_info={"condition_fit_sources": source_map},
    )
    originals = {
        name: deepcopy(result.overall_table.iloc[0][name])
        for name in ("AI点", "raw_score", "ability_display_score", "距離指数", "コース指数")
    }

    apply_prediction_logic(result, "v4.1")

    row = result.overall_table.iloc[0]
    assert result.logic_version == "v4.1"
    assert row["condition_fit_mark"] == "★"
    assert row["condition_fit_level"] == "same_venue_distance"
    assert row["condition_fit_data_status"] == "ok"
    assert "_past_runs" not in result.overall_table.columns
    assert "_past_runs" not in result.horse_evaluation.columns
    for name, before in originals.items():
        assert row[name] == before


def test_v4_baseline_is_preserved_while_v41_treats_missing_as_unknown() -> None:
    display = pd.DataFrame([base_row()])
    baseline = PredictionResult(
        race_mode="nar",
        race_info=RACE_INFO,
        overall_table=display.copy(deep=True),
        horse_evaluation=display.copy(deep=True),
    )
    fixed = deepcopy(baseline)

    apply_prediction_logic(baseline, "v4")
    apply_prediction_logic(fixed, "v4.1")

    old = baseline.overall_table.iloc[0]
    new = fixed.overall_table.iloc[0]
    assert old["condition_matched_quality"] == 30.0
    assert "近3走に同距離条件実績なし" in old["warning_reason"]
    assert new["condition_fit_data_status"] == "missing_source_data"
    assert new["condition_matched_quality"] == 50.0
    assert "近3走に同距離条件実績なし" not in new["warning_reason"]


def test_confirmed_no_match_still_uses_existing_veto_rule() -> None:
    row = base_row()
    row["_past_runs"] = [past_run("門別", 1000, "右")]
    result = evaluate_ver4_table(
        pd.DataFrame([row]),
        "nar",
        RACE_INFO,
        condition_fit_plumbing=True,
    ).iloc[0]

    assert result["condition_fit_data_status"] == "no_match"
    assert "近3走に同距離条件実績なし" in result["warning_reason"]
