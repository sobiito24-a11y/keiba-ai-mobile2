# -*- coding: utf-8 -*-
from __future__ import annotations

import math

import pandas as pd

from core.investment_decision import build_investment_decision
from core.models import PredictionResult
from core.prediction_history import build_prediction_snapshot, prediction_csv_rows
from core.ver4_engine import (
    JRA_WEIGHTS,
    NAR_WEIGHTS,
    apply_prediction_logic,
    build_ver4_race_summary,
    evaluate_ver4_table,
    group_for_horse,
    legacy_decision_from_v4,
    normalize_index,
    validate_component_weights,
)


def horse(
    number: int,
    *,
    recent: tuple[object, object, object] = (60, 65, 70),
    average: object = 65,
    year_max: object = 78,
    distance: object = 70,
    course: object = 68,
    fit_mark: str = "★",
    fit_level: str = "same_venue_distance",
    matched_index: object = 72,
    age: str = "牡4",
    extra: dict | None = None,
) -> dict:
    row = {
        "馬番": number,
        "馬名": f"Horse{number}",
        "馬年齢": age,
        "3走前": recent[0],
        "2走前": recent[1],
        "前走": recent[2],
        "平均指数": average,
        "過去1年最高指数": year_max,
        "距離指数": distance,
        "コース指数": course,
        "condition_fit_mark": fit_mark,
        "condition_fit_level": fit_level,
        "condition_fit_reason": "既存条件実績",
        "matched_past_runs": [{"time_index": matched_index}],
        "騎手詳細": "継続 ○",
        "展開印": "○",
    }
    row.update(extra or {})
    return row


def test_weight_sums_are_exact_for_nar_and_jra() -> None:
    assert math.isclose(sum(NAR_WEIGHTS.values()), 1.0)
    assert math.isclose(sum(JRA_WEIGHTS.values()), 1.0)
    assert validate_component_weights("nar")
    assert validate_component_weights("jra")
    assert NAR_WEIGHTS == {
        "base_ability_score": 0.45,
        "condition_score": 0.30,
        "jockey_score": 0.08,
        "age_weight_score": 0.07,
        "momentum_score_v4": 0.07,
        "race_shape_score": 0.03,
    }


def test_horse_score_is_absolute_and_race_rank_is_separate() -> None:
    target = horse(1)
    alone = evaluate_ver4_table(pd.DataFrame([target]), "nar").iloc[0]
    together = evaluate_ver4_table(pd.DataFrame([target, horse(2, recent=(10, 15, 20), average=15)]), "nar")
    target_together = together.loc[together["馬番"].eq(1)].iloc[0]
    assert target_together["horse_score_v4"] == alone["horse_score_v4"]
    assert target_together["race_rank_v4"] == 1
    assert 0 <= target_together["horse_score_v4"] <= 100


def test_fixed_index_normalization_handles_negative_and_display_string() -> None:
    assert normalize_index(-35, "nar") == 0
    assert normalize_index(85, "nar") == 100
    assert normalize_index("25/稍重", "nar") == 50
    assert normalize_index(None, "nar") is None


def test_condition_fit_star_turn_and_distance_marks_are_preserved() -> None:
    rows = [
        horse(1, fit_mark="★", fit_level="same_venue_distance"),
        horse(2, fit_mark="☆", fit_level="same_turn_distance"),
        horse(3, fit_mark="※", fit_level="same_distance"),
    ]
    result = evaluate_ver4_table(pd.DataFrame(rows), "nar")
    assert result["condition_fit_mark"].tolist() == ["★", "☆", "※"]


def test_high_quality_turn_match_can_beat_low_quality_exact_venue_match() -> None:
    rows = [
        horse(1, fit_mark="★", fit_level="same_venue_distance", matched_index=5, distance=50, course=50),
        horse(2, fit_mark="☆", fit_level="same_turn_distance", matched_index=82, distance=50, course=50),
    ]
    result = evaluate_ver4_table(pd.DataFrame(rows), "nar").set_index("馬番")
    assert result.loc[2, "condition_score"] > result.loc[1, "condition_score"]


def test_two_year_old_missing_condition_is_neutral_not_major_penalty() -> None:
    row = horse(
        1,
        recent=(None, None, 55),
        average=55,
        fit_mark="",
        fit_level="none",
        matched_index=None,
        distance=None,
        course=None,
        age="牡2",
    )
    row["matched_past_runs"] = []
    result = evaluate_ver4_table(pd.DataFrame([row]), "nar").iloc[0]
    assert result["condition_score"] == 50.0
    assert "同距離条件実績なし" not in result["warning_reason"]


def test_ss_can_be_zero_or_multiple() -> None:
    weak = evaluate_ver4_table(
        pd.DataFrame([horse(1, recent=(15, 20, 25), average=20, year_max=30, distance=25, course=25)]),
        "nar",
    )
    assert not weak["group_v4"].eq("SS").any()

    strong = evaluate_ver4_table(
        pd.DataFrame(
            [
                horse(1, recent=(80, 82, 84), average=82, year_max=85, distance=84, course=82, matched_index=84, extra={"展開印": "◎"}),
                horse(2, recent=(79, 82, 85), average=82, year_max=85, distance=85, course=84, matched_index=83, extra={"展開印": "◎"}),
            ]
        ),
        "nar",
    )
    assert strong["group_v4"].eq("SS").sum() == 2


def test_group_and_mark_are_independent() -> None:
    result = evaluate_ver4_table(
        pd.DataFrame(
            [
                horse(1, recent=(80, 82, 84), average=82, year_max=85, distance=84, course=82, matched_index=84, extra={"展開印": "◎"}),
                horse(2, recent=(79, 81, 83), average=81, year_max=84, distance=82, course=80, matched_index=82, extra={"展開印": "◎"}),
            ]
        ),
        "nar",
    )
    assert set(result["group_v4"]) == {"SS"}
    assert result["mark_v4"].tolist().count("◎") == 1
    assert result["mark_v4"].tolist().count("○") == 1


def test_watch_mark_requires_one_strong_existing_reason() -> None:
    rows = [
        horse(1, recent=(80, 82, 84), average=82, year_max=85, distance=82, course=82, matched_index=84),
        horse(2, recent=(58, 58, 58), average=58, year_max=60, distance=55, course=55, matched_index=55),
        horse(3, recent=(20, 20, 20), average=20, year_max=25, distance=84, course=20, matched_index=25),
        horse(4, recent=(18, 18, 18), average=18, year_max=22, distance=20, course=20, matched_index=20),
        horse(5, recent=(15, 15, 15), average=15, year_max=20, distance=20, course=20, matched_index=20),
        horse(6, recent=(10, 10, 10), average=10, year_max=15, distance=20, course=20, matched_index=15),
    ]
    result = evaluate_ver4_table(pd.DataFrame(rows), "nar").set_index("馬番")
    assert result.loc[3, "mark_v4"] == "✓"
    assert "距離適性" in result.loc[3, "watch_reason_v4"]
    assert result.loc[6, "mark_v4"] == ""


def test_opponent_veto_blocks_weak_b_or_unqualified_watch() -> None:
    rows = [
        horse(1, recent=(80, 82, 84), average=82, year_max=85, distance=84, course=82, matched_index=84),
        horse(2, recent=(50, 52, 54), average=52, year_max=58, distance=10, course=10, matched_index=5),
    ]
    result = evaluate_ver4_table(pd.DataFrame(rows), "nar").set_index("馬番")
    assert not bool(result.loc[2, "opponent_eligible_v4"])
    assert result.loc[2, "opponent_veto_reason_v4"]


def test_decision_and_legacy_mapping() -> None:
    assert legacy_decision_from_v4("BUY") == "BUY"
    assert legacy_decision_from_v4("LIGHT") == "HOLD"
    assert legacy_decision_from_v4("WATCH") == "HOLD"
    assert legacy_decision_from_v4("SKIP") == "SKIP"

    result = evaluate_ver4_table(
        pd.DataFrame(
            [
                horse(1, recent=(80, 82, 84), average=82, year_max=85, distance=84, course=82, matched_index=84, extra={"展開印": "◎"}),
                horse(2, recent=(68, 70, 72), average=70, year_max=76, distance=72, course=70, matched_index=72),
            ]
        ),
        "nar",
    )
    summary = build_ver4_race_summary(result)
    assert summary["decision_v4"] in {"BUY", "LIGHT"}
    assert summary["legacy_decision"] in {"BUY", "HOLD"}
    assert 1 <= len(summary["tickets"]) <= 3


def test_single_is_only_used_for_a_strong_axis_without_viable_partners() -> None:
    result = evaluate_ver4_table(
        pd.DataFrame(
            [
                horse(1, recent=(84, 85, 86), average=85, year_max=87, distance=85, course=85, matched_index=86, extra={"展開印": "◎"}),
                horse(2, recent=(-30, -28, -25), average=-28, year_max=-20, distance=-30, course=-30, matched_index=-30),
            ]
        ),
        "nar",
    )
    summary = build_ver4_race_summary(result)
    assert summary["ticket_type"] == "単勝"
    assert summary["tickets"] == ["1"]
    assert summary["decision_v4"] == "LIGHT"


def test_trio_requires_three_strong_horses_and_stays_one_point() -> None:
    result = evaluate_ver4_table(
        pd.DataFrame(
            [
                horse(1, recent=(84, 85, 86), average=85, year_max=87, distance=85, course=85, matched_index=86, extra={"展開印": "◎"}),
                horse(2, recent=(75, 77, 79), average=77, year_max=82, distance=78, course=77, matched_index=78),
                horse(3, recent=(73, 75, 78), average=75, year_max=81, distance=76, course=75, matched_index=77),
            ]
        ),
        "nar",
    )
    summary = build_ver4_race_summary(result)
    assert summary["ticket_type"] == "三連複"
    assert len(summary["tickets"]) == 1
    assert len(summary["tickets"][0].split("-")) == 3


def test_v3_v4_switch_preserves_v3_tables() -> None:
    original = pd.DataFrame([horse(1)])
    v3 = PredictionResult(race_mode="nar", overall_table=original.copy(), horse_evaluation=original.copy())
    before = v3.overall_table.copy(deep=True)
    returned = apply_prediction_logic(v3, "v3")
    pd.testing.assert_frame_equal(returned.overall_table, before)
    assert returned.logic_version == "v3"
    assert "horse_score_v4" not in returned.overall_table

    v4 = PredictionResult(race_mode="nar", overall_table=original.copy(), horse_evaluation=original.copy())
    apply_prediction_logic(v4, "v4")
    assert v4.logic_version == "v4"
    assert "horse_score_v4" in v4.overall_table
    pd.testing.assert_frame_equal(original, before)


def test_prediction_history_contains_ver4_audit_and_csv_fields() -> None:
    original = pd.DataFrame([horse(1)])
    result = PredictionResult(
        race_mode="nar",
        race_name="テスト1R",
        race_info={"race_id": "202630081199", "venue": "門別", "race_number": "1R"},
        overall_table=original.copy(),
        horse_evaluation=original.copy(),
        status="ok",
    )
    apply_prediction_logic(result, "v4")
    decision = build_investment_decision(result.overall_table, "nar", prediction_logic_version="v4")
    snapshot = build_prediction_snapshot(result, decision)
    assert snapshot["logic_version"] == "v4"
    assert snapshot["horses"][0]["ver4"]["horse_score_v4"] != ""
    assert snapshot["horses"][0]["ver4"]["condition_score"] != ""
    assert "decision_v4" in snapshot["investment_decision"]
    assert "ticket_veto_reason" in snapshot["investment_decision"]
    csv_row = prediction_csv_rows(snapshot)[0]
    assert csv_row["logic_version"] == "v4"
    assert "ver4_horse_score_v4" in csv_row

    automatic = build_prediction_snapshot(result)
    assert automatic["investment_decision"]["logic_version"] == "v4"
    assert automatic["investment_decision"]["decision_v4"] in {"BUY", "LIGHT", "WATCH", "SKIP"}


def test_missing_values_and_zero_are_safe_for_both_race_types() -> None:
    row = horse(1, recent=(0, "0", None), average="", year_max=None, distance=0, course="0", matched_index="0")
    for race_type in ("nar", "jra"):
        result = evaluate_ver4_table(pd.DataFrame([row]), race_type)
        assert len(result) == 1
        assert 0 <= result.iloc[0]["horse_score_v4"] <= 100
        assert result.iloc[0]["condition_distance_score"] == normalize_index(0, race_type)
        assert result.iloc[0]["condition_course_score"] == normalize_index("0", race_type)


def test_jra_has_training_component_and_nar_does_not_weight_it() -> None:
    row = horse(1, extra={"調教評価": "◎"})
    jra = evaluate_ver4_table(pd.DataFrame([row]), "jra").iloc[0]
    nar = evaluate_ver4_table(pd.DataFrame([row]), "nar").iloc[0]
    assert jra["training_score"] == 85.0
    assert "training_score" in JRA_WEIGHTS
    assert "training_score" not in NAR_WEIGHTS
    assert not pd.isna(nar["horse_score_v4"])


def test_group_thresholds_do_not_depend_on_mark() -> None:
    assert group_for_horse({"horse_score_v4": 70, "base_ability_score": 0, "condition_score": 0}, "nar") == "A"
    assert group_for_horse({"horse_score_v4": 58, "base_ability_score": 0, "condition_score": 0}, "nar") == "B"
    assert group_for_horse({"horse_score_v4": 45, "base_ability_score": 0, "condition_score": 0}, "nar") == "C"
    assert group_for_horse({"horse_score_v4": 44.9, "base_ability_score": 100, "condition_score": 100}, "nar") == "Z"
