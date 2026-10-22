"""Display facts stay faithful to dated pre-race history and saved metrics."""
from copy import deepcopy

import pytest

from core.candidate_profile import facts
from core.final_candidate_metrics import project as candidate_metrics
from core.race_explorer_facts import project


def source():
    return {
        "_current_jockey": "松山", "_previous_jockey": "川田",
        "jockey_change_market": "乗替", "_current_load_weight": 56,
        "_previous_load_weight": 57, "weight_change_market": -1,
        "_days_since_last": 21, "3走平均": 67.7, "平均指数": 100,
        "★最高指数": 80, "★該当走": "2走前", "star_max_venue": "東京",
        "star_max_surface": "ダ", "star_max_distance": 1600,
        "調教評価": "A 好気配", "新聞コメント": "  前走は外を回った。\n改めて期待。〈厩舎〉  ",
        "_past_runs": [
            dict(label=label, race_date=date, value=index, position=finish,
                 racecourse=venue, surface=surface, distance=distance,
                 direction="左", race_name="3歳以上1勝クラス")
            for label, date, index, finish, venue, surface, distance in (
                ("3走前", "2026-07-05", 55, 2, "東京", "芝", 1600),
                ("2走前", "2026-08-09", 80, 3, "東京", "ダ", 1600),
                ("前走", "2026-09-27", 68, 7, "東京", "ダート", 1400),
            )
        ],
    }


def info():
    return dict(race_date="2026-10-18", venue="東京", surface="ダ", distance=1600, turn="左")


def horse(row=None, mode="jra", race_info=None):
    row = source() if row is None else row
    race_info = info() if race_info is None else race_info
    h = dict(mode=mode, jockey="松山（乗替）", training="A" if mode == "jra" else "",
             profile=facts(row, race_info), ability=60.5, ability_rank=2,
             course=dict(value=71, rank=1), distance=dict(value=75, rank=3),
             plus="保存済みの好走材料", caution="保存済みの注意材料",
             candidate_evidence=dict(plus=["調教A"], minus=["休養注意"],
                                     neutral=["位置・脚質の参考：4角5番手"]))
    h["final_metrics"] = candidate_metrics(h, row)
    return h


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_chronological_projection_preserves_saved_indices_and_inputs(mode):
    row, race_info = source(), info()
    h = horse(row, mode)
    before = deepcopy((row, h, race_info))
    result = project(h, row, race_info)
    assert [r["label"] for r in result["runs"]] == ["3走前", "2走前", "前走"]
    assert [r["time_index"] for r in result["runs"]] == [55, 80, 68]
    assert [r["finish"] for r in result["runs"]] == ["2着", "3着", "7着"]
    assert [r["is_maximum"] for r in result["runs"]] == [False, True, False]
    assert result["runs"][0]["condition"] == "東京・芝1600m・左"
    assert "1勝" in result["runs"][1]["class_raw"]
    assert result["metrics"] == h["final_metrics"]
    assert result["metrics"]["average"] == 67.7
    assert result["metrics"]["maximum"] == 80
    assert (row, h, race_info) == before
    result["metrics"]["ability"]["value"] = -999
    assert h["final_metrics"]["ability"]["value"] == 60.5


def test_condition_counts_keep_surface_and_scope_distinct():
    row = source()
    result = project(horse(row), row, info())
    records = {r["key"]: r for r in result["condition_records"]}
    assert (records["venue_distance"]["starts"], records["venue_distance"]["top3"]) == (1, 1)
    assert (records["venue_surface"]["starts"], records["venue_surface"]["top3"]) == (2, 1)
    assert (records["surface_distance"]["starts"], records["surface_distance"]["top3"]) == (1, 1)
    assert (records["venue"]["starts"], records["venue"]["top3"]) == (3, 2)
    assert records["venue_distance"]["label"] == "東京ダ1600m"
    assert records["venue_surface"]["label"] == "東京ダート"
    assert all("近3走の範囲" in r["scope"] and "近3走の範囲" in r["text"] for r in records.values())
    assert len(result["features"]) <= 3
    assert "1戦1回3着以内" in result["features"][0]


def test_other_venues_never_count_as_current_venue():
    row = source()
    for run in row["_past_runs"]:
        run["racecourse"] = "中京"
    result = project(horse(row), row, info())
    records = {r["key"]: r for r in result["condition_records"]}
    assert records["venue_distance"]["starts"] == records["venue_surface"]["starts"] == records["venue"]["starts"] == 0
    assert records["surface_distance"]["starts"] == 1


def test_missing_conditions_and_non_starts_are_not_counted_as_experience():
    row = source()
    row["_past_runs"][0]["surface"] = ""
    row["_past_runs"][1]["position"] = "取消"
    result = project(horse(row), row, info())
    record = result["condition_records"][0]
    assert record["starts"] == record["top3"] == 0
    assert record["unknown"] == 1
    assert "未確認1走" in record["text"]


@pytest.mark.parametrize("saved_days", [20, 22, -1])
def test_saved_interval_conflict_is_unknown(saved_days):
    row = source()
    row["_days_since_last"] = saved_days
    result = project(horse(row), row, info())
    assert result["rest_days"] is None
    assert result["rest_status"] == "conflict"
    assert "不一致" in result["rest_label"]


def test_audited_interval_conflict_stays_unknown_even_if_other_values_match():
    row = source()
    h = horse(row)
    h["candidate_evidence"]["audit"] = {"rest": {"status": "conflict", "days": None}}
    result = project(h, row, info())
    assert result["rest_status"] == "conflict" and result["rest_days"] is None


def test_interval_uses_actual_prior_start_not_latest_cancelled_entry():
    row = source()
    row["_past_runs"][-1]["position"] = "取消"
    row["_days_since_last"] = 70
    result = project(horse(row), row, info())
    assert result["rest_days"] == 70
    assert result["rest_label"] == "約2ヶ月"


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_interval_uses_same_calendar_week_definition_in_both_modes(mode):
    row = source()
    result = project(horse(row, mode), row, info())
    assert result["rest_days"] == 21
    assert result["rest_label"] == "中2週"
    assert "月曜" in result["rest_definition"]


def test_more_recent_uncertain_start_blocks_interval():
    row = source()
    row["_past_runs"][-1]["position"] = "未取得"
    result = project(horse(row), row, info())
    assert result["rest_status"] == "unknown"
    assert result["rest_days"] is None


def test_current_and_future_records_never_supply_historical_facts():
    row = source()
    h = horse(row)
    h["profile"]["runs"][0]["date"] = "2026-10-18"
    h["profile"]["runs"][1]["date"] = "2026-11-18"
    result = project(h, row, info())
    assert [r["time_index"] for r in result["runs"]] == [55, None, None]
    assert not any(r["is_maximum"] for r in result["runs"])
    assert result["condition_records"][0]["starts"] == 0


def test_missing_previous_rider_never_becomes_current_rider():
    row = source()
    row["_previous_jockey"] = "未取得"
    result = project(horse(row), row, info())
    assert result["current_jockey"] == "松山"
    assert result["previous_jockey"] == "未取得"
    assert result["jockey_status"] == "乗替"
    assert result["jockey_change"] == "乗替・前走騎手未取得"
    row["jockey_change_market"] = "継続"
    result = project(horse(row), row, info())
    assert result["previous_jockey"] == "未取得"
    assert result["jockey_status"] == "未取得"
    assert result["jockey_change"] == "前走騎手未取得"


def test_replacement_riders_and_weight_pair_are_correct():
    row = source()
    result = project(horse(row), row, info())
    assert result["jockey_change"] == "川田 → 松山"
    assert (result["current_weight"], result["previous_weight"], result["weight_delta"]) == (56, 57, -1)
    assert result["weight_label"] == "56kg" and result["weight_delta_label"] == "−1kg"
    row["weight_change_market"] = 2
    assert project(horse(row), row, info())["weight_delta"] is None


def test_existing_weight_audit_can_intentionally_suppress_delta():
    row = source()
    h = horse(row)
    h["candidate_evidence"]["audit"] = {"weight": dict(current=56, previous=57, delta=None)}
    assert project(h, row, info())["weight_delta"] is None


def test_three_run_absence_cannot_prove_first_surface_or_blinker():
    row = source()
    for run in row["_past_runs"]:
        run["surface"] = "芝"
    row["blinkers"] = True
    result = project(horse(row), row, info())
    labels = " / ".join(result["features"] + result["changes"])
    assert "馬場変更 芝→ダ" in labels
    assert not any(label in labels for label in ("初ダート", "初芝", "初ブリンカー", "ブリンカー再装着"))


def test_stable_comment_original_is_exact_and_separate_from_interpretation():
    row = source()
    row["stable_comment_market"] = "AI加工済み要約"
    h = horse(row)
    h["comment"] = "予測表示用の加工済みコメント"
    result = project(h, row, info())
    assert result["stable_comment_raw"] == row["新聞コメント"]
    assert result["stable_comment_source"] == "新聞コメント"
    assert "指数推移" in result["interpretation"]
    assert result["plus"] == h["final_metrics"]["plus"]
    assert result["caution"] == h["final_metrics"]["caution"]
    row.pop("新聞コメント")
    row["stable_comment_summary"] = "原文ではない"
    assert project(h, row, info())["stable_comment_raw"] == "未取得"


def test_nar_training_is_outside_scope_and_missing_data_stays_missing():
    result = project(dict(mode="nar"), {}, {})
    assert result["training"] == "対象外"
    assert result["rest_status"] == "unknown"
    assert result["rest_days"] is result["weight_delta"] is None
    assert result["previous_jockey"] == result["stable_comment_raw"] == "未取得"
    assert result["features"] == []
    assert all(run["time_index"] is None for run in result["runs"])


def test_peak_historical_condition_is_not_used_as_current_distance():
    row = source()
    race_info = dict(race_date="2026-10-18", venue="東京", surface="ダ")
    result = project(horse(row, race_info=race_info), row, race_info)
    records = {r["key"]: r for r in result["condition_records"]}
    assert records["venue_distance"]["starts"] == records["surface_distance"]["starts"] == 0
    assert records["venue_surface"]["starts"] == 2
