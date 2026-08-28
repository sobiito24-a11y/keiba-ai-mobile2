from __future__ import annotations

from core.v1_logic import build_v1_evaluations, jra_reproducibility, nar_reproducibility, pace_evaluation, state_evaluation


def test_nar_reproducibility_ranks_same_venue_distance_results() -> None:
    current = {"venue": "船橋", "distance": 2200}
    assert nar_reproducibility(
        [
            {"racecourse": "船橋", "distance": 2200, "position": 1},
            {"racecourse": "船橋", "distance": 2200, "position": 3},
        ],
        current,
    )["rank"] == "S"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 2200, "position": 2}], current)["rank"] == "A"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 2200, "position": 8}], current)["rank"] == "C"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 1600, "position": 2}], current)["rank"] == "B"
    assert nar_reproducibility([{"racecourse": "大井", "distance": 1200, "position": 2}], current)["rank"] == "—"


def test_jra_reproducibility_uses_surface_distance_turn_before_turn_only() -> None:
    current = {"venue": "中京", "surface": "芝", "distance": 2000, "turn": "左"}
    assert jra_reproducibility(
        [
            {"racecourse": "東京", "surface": "芝", "distance": 2000, "direction": "左", "position": 2},
            {"racecourse": "新潟", "surface": "芝", "distance": 2000, "direction": "左", "position": 3},
        ],
        current,
    )["rank"] == "S"
    assert jra_reproducibility([{"racecourse": "東京", "surface": "芝", "distance": 2000, "direction": "左", "position": 2}], current)["rank"] == "A"
    assert jra_reproducibility([{"racecourse": "阪神", "surface": "芝", "distance": 2000, "direction": "右", "position": 2}], current)["rank"] == "B"
    assert jra_reproducibility([{"racecourse": "東京", "surface": "芝", "distance": 1600, "direction": "左", "position": 2}], current)["rank"] == "C"
    assert jra_reproducibility([{"racecourse": "阪神", "surface": "ダート", "distance": 1400, "direction": "右", "position": 2}], current)["rank"] == "—"


def test_pace_and_state_evaluations_are_display_axes_only() -> None:
    assert pace_evaluation({"corner4_group": "front", "running_style": "逃げ"}) == {"rank": "○", "reason": "4角前方想定（逃げ）"}
    assert pace_evaluation({"_estimated_position_corner4_label": "逃げ"}) == {"rank": "○", "reason": "4角前方想定"}
    assert pace_evaluation({"position_corner4_label_market": "先団"})["rank"] == "○"
    assert pace_evaluation({"_estimated_position_corner4_label": "中団"})["rank"] == "△"
    assert pace_evaluation({"estimated_position_path": "中団 → 中団 → 後方"})["rank"] == "×"
    assert pace_evaluation({"corner4_group": "back"})["rank"] == "×"
    assert state_evaluation(
        {
            "training": "A/好調",
            "stable_comment": "順調で期待",
            "jockey_change": "継続",
            "weight_diff": -1,
        },
        [],
        "jra",
    )["rank"] == "A"
    assert state_evaluation({"jockey_change": "継続"}, [], "jra") == {"rank": "—", "reason": "材料不足"}
    assert state_evaluation({"jockey_change": "乗替"}, [], "nar") == {"rank": "—", "reason": "材料不足"}
    assert state_evaluation({}, [], "nar") == {"rank": "—", "reason": "材料不足"}
    assert state_evaluation({}, [{"index": 30}, {"index": 20}], "nar")["rank"] == "B"
    assert state_evaluation({"weight_diff": 3}, [{"index": 30}, {"index": 20}], "nar")["rank"] == "—"
    assert state_evaluation({"interval": "休み明け", "weight_diff": 2}, [], "nar")["rank"] == "C"


def test_state_evaluation_orders_labeled_runs_for_trend_only() -> None:
    lapland_runs = [
        {"label": "3走前", "value": 47},
        {"label": "2走前", "value": 49},
        {"label": "前走", "value": 44},
    ]

    nar_state = state_evaluation({}, lapland_runs, "nar")
    jra_state = state_evaluation({"training": "B 好気配"}, lapland_runs, "jra")

    assert nar_state == {"rank": "—", "reason": "材料不足"}
    assert jra_state["rank"] == "B"
    assert "近走上昇" not in jra_state["reason"]
    assert "近走下降" not in jra_state["reason"]


def test_build_v1_evaluations_assigns_star_and_check_without_odds() -> None:
    rows = [
        {"horse_no": "1", "horse_name": "A", "venue": "船橋", "distance": 2200, "ability_value": 100, "ability_rank": 1, "ai_current_rank": 1, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "2", "horse_name": "B", "venue": "船橋", "distance": 2200, "ability_value": 95, "ability_rank": 2, "ai_current_rank": 2, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "3", "horse_name": "C", "venue": "船橋", "distance": 2200, "ability_value": 90, "ability_rank": 3, "ai_current_rank": 3, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "4", "horse_name": "D", "venue": "船橋", "distance": 2200, "ability_value": 10, "ability_rank": 8, "ai_current_rank": 7, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 1}]},
        {"horse_no": "5", "horse_name": "E", "venue": "船橋", "distance": 2200, "ability_value": 9, "ability_rank": 9, "ai_current_rank": 8, "corner4_group": "front", "recent_runs": [{"racecourse": "船橋", "distance": 1600, "position": 2}]},
        {"horse_no": "6", "horse_name": "F", "venue": "船橋", "distance": 2200, "ability_value": 8, "ability_rank": 10, "ai_current_rank": 9, "corner4_group": "front", "recent_runs": []},
    ]
    result = build_v1_evaluations(rows, "nar")
    marks = {row["horse_no"]: row["v1_mark"] for row in result["rows"]}
    final_marks = {row["horse_no"]: row["v1_final_mark"] for row in result["rows"]}
    final_ranks = [row["v1_final_rank"] for row in result["rows"]]
    assert marks["1"] == "◎"
    assert final_marks["1"] == "◎"
    assert result["recommendations"][0]["v1_final_role"] == "軸候補"
    assert "☆" in final_marks.values()
    assert len(final_ranks) == len(set(final_ranks))
    assert [row["number"] for row in result["recommendations"]] == [
        row["number"] for row in sorted(result["rows"], key=lambda row: row["v1_final_rank"])[:5]
    ]
    assert all(row.get("odds") is None for row in result["rows"])


def test_build_v1_evaluations_uses_race_info_and_saved_market_keys() -> None:
    rows = [
        {
            "馬番": "5",
            "馬名": "ラップランド",
            "market_ability_score": 31.2,
            "market_ability_rank": 4,
            "current_evaluation_rank": 2,
            "_estimated_position_corner4_label": "中団",
            "recent_runs": [{"racecourse": "船橋", "distance": "2200m", "finish": "3着"}],
        },
        {
            "馬番": "6",
            "馬名": "ヒロシゲジャック",
            "market_ability_score": 20.5,
            "market_ability_rank": 8,
            "current_evaluation_rank": 8,
            "position_corner4_label_market": "先団",
            "recent_runs": [{"racecourse": "船橋競馬場", "distance": 2200, "finish": "8着"}],
        },
    ]

    result = build_v1_evaluations(rows, "nar", race_info={"racecourse": "船橋", "distance": 2200})
    by_number = {row["number"]: row for row in result["rows"]}

    assert result["current_condition"]["venue"] == "船橋"
    assert result["current_condition"]["distance"] == 2200
    assert by_number["5"]["ability_rank"] == 4
    assert by_number["5"]["ability_value"] == 31.2
    assert by_number["5"]["v1_reproducibility"] == "A"
    assert "船橋2200m" in by_number["5"]["v1_reproducibility_reason"]
    assert by_number["6"]["v1_reproducibility"] == "C"
    assert by_number["6"]["v1_pace_eval"] == "○"
    assert by_number["5"]["baseline_current_evaluation_rank"] == 2
    assert "再現性" in result["summary"]
    assert "A:1" not in result["summary"]["再現性"]
    assert "ラップランド" in result["summary"]["再現性"]
    assert result["summary"]["_今回評価_numbers"] == [row["number"] for row in result["recommendations"]]


def test_build_v1_evaluations_reads_saved_recent_races_key() -> None:
    result = build_v1_evaluations(
        [
            {
                "horse_number": "5",
                "horse_name": "ラップランド",
                "market_ability_score": 48.7,
                "market_ability_rank": 10,
                "current_evaluation_rank": 12,
                "mark": "",
                "recent_races": [
                    {"racecourse": "船橋", "distance": "2200m", "finish": "1着"},
                    {"racecourse": "船橋", "distance": "1800m", "finish": "5着"},
                ],
            }
        ],
        "nar",
        race_info={"venue": "船橋", "distance": 2200},
    )

    row = result["rows"][0]
    assert row["number"] == "5"
    assert row["v1_reproducibility"] == "A"
    assert row["v1_final_role"] == "軸候補"
    assert row["baseline_current_evaluation_rank"] == 12
    assert row["baseline_mark"] == ""


def test_build_v1_evaluations_fills_missing_display_ability_rank_from_saved_values() -> None:
    result = build_v1_evaluations(
        [
            {"馬番": "1", "馬名": "低値", "market_ability_score": 10, "current_evaluation_rank": 2},
            {"馬番": "2", "馬名": "高値", "market_ability_score": 30, "current_evaluation_rank": 1},
        ],
        "nar",
        race_info={"venue": "船橋", "distance": 1600},
    )
    by_number = {row["number"]: row for row in result["rows"]}

    assert by_number["2"]["ability_rank"] == 1
    assert by_number["1"]["ability_rank"] == 2
    assert result["recommendations"][0]["number"] == "2"


def test_jra_state_prioritizes_training_and_comment_over_layoff() -> None:
    mars = state_evaluation(
        {
            "training": "B 好気配",
            "stable_comment": "前走を見るとクラスにメド。初めての中京だけど、コース適性もあるはず。",
            "interval": "休み明け",
        },
        [],
        "jra",
    )
    tripolitania = state_evaluation(
        {
            "training": "A 仕上抜群",
            "stable_comment": "休み明けでも状態はいい",
            "interval": "休み明け",
        },
        [],
        "jra",
    )
    peisha = state_evaluation({"training": "C 反応平凡"}, [], "jra")
    mario = state_evaluation({"training": "C 良化遅い", "stable_comment": "ズブさへの懸念"}, [], "jra")

    assert mars["rank"] == "B"
    assert "調教B 好気配" in mars["reason"]
    assert tripolitania["rank"] == "A"
    assert peisha["rank"] == "C"
    assert mario["rank"] == "C"
