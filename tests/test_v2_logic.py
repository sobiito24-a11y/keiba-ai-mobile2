from __future__ import annotations

from core.v2_logic import build_v2_evaluations


def row(no: int, ability: float, rank: int, **extra):
    data = {
        "馬番": no,
        "馬名": f"馬{no}",
        "market_ability_score": ability,
        "market_ability_rank": rank,
        "running_style_market": extra.pop("style", "差し"),
        "position_corner4_label_market": extra.pop("corner4", "中団"),
    }
    data.update(extra)
    return data


def test_nar_v2_condition_scores_do_not_penalize_unexperienced_horses() -> None:
    result = build_v2_evaluations(
        [
            row(
                1,
                20,
                1,
                recent_runs=[
                    {"racecourse": "船橋", "distance": 2200, "finish": "1着"},
                    {"racecourse": "船橋", "distance": "2200m", "finish": "3着"},
                ],
            ),
            row(
                2,
                19,
                2,
                recent_runs=[
                    {"racecourse": "船橋", "distance": 2200, "finish": "2着"},
                    {"racecourse": "船橋", "distance": 2200, "finish": "3着"},
                ],
            ),
            row(3, 18, 3, recent_runs=[{"racecourse": "船橋", "distance": 2200, "finish": "2着"}]),
            row(4, 17, 4, recent_runs=[{"racecourse": "船橋", "distance": 2200, "finish": "8着"}]),
            row(5, 16, 5, recent_runs=[{"racecourse": "大井", "distance": 1200, "finish": "8着"}]),
        ],
        "nar",
        race_info={"racecourse": "船橋", "distance": 2200},
    )
    by_no = {horse["number"]: horse for horse in result["rows"]}

    assert by_no["1"]["v2_condition_score"] == 4.0
    assert by_no["2"]["v2_condition_score"] == 3.5
    assert by_no["3"]["v2_condition_score"] == 2.5
    assert by_no["4"]["v2_condition_score"] == 0.0
    assert by_no["5"]["v2_condition_score"] == 0.0
    assert by_no["5"]["v2_ai_score"] == 16.0


def test_nar_v2_recent_score_is_capped_and_uses_newest_first_labels() -> None:
    result = build_v2_evaluations(
        [
            row(
                1,
                20,
                1,
                recent_runs=[
                    {"label": "3走前", "value": 47},
                    {"label": "2走前", "value": 49},
                    {"label": "前走", "value": 44},
                ],
            ),
            row(
                2,
                19,
                2,
                recent_runs=[
                    {"label": "3走前", "value": 20},
                    {"label": "2走前", "value": 24},
                    {"label": "前走", "value": 35},
                ],
            ),
        ],
        "nar",
        race_info={"racecourse": "船橋", "distance": 2200},
    )
    by_no = {horse["number"]: horse for horse in result["rows"]}

    assert by_no["1"]["v2_recent_state_score"] == -0.25
    assert by_no["1"]["v2_recent_state_reason"] == "近走弱含み"
    assert by_no["2"]["v2_recent_state_score"] == 0.5


def test_v2_pace_style_and_marks_are_based_on_ai_score_gap() -> None:
    result = build_v2_evaluations(
        [
            row(1, 80.0, 1, style="逃げ"),
            row(2, 79.0, 2, style="差し"),
            row(
                3,
                75.5,
                8,
                style="差し",
                recent_runs=[{"racecourse": "船橋", "distance": 2200, "finish": "1着"}],
            ),
            row(4, 70.0, 4, style="追込"),
        ],
        "nar",
        race_info={"racecourse": "船橋", "distance": 2200, "pace": "H"},
    )
    by_no = {horse["number"]: horse for horse in result["rows"]}
    ordered = sorted(result["rows"], key=lambda horse: -horse["v2_ai_score"])

    assert by_no["1"]["v2_pace_score"] == -1.0
    assert by_no["2"]["v2_pace_score"] == 1.0
    assert ordered[0]["v2_final_mark"] == "◎"
    assert by_no["3"]["v2_final_mark"] == "☆"
    assert by_no["3"]["v2_final_role"] == "条件スペシャリスト"


def test_jra_v2_condition_and_state_scores_use_saved_training_and_comments() -> None:
    result = build_v2_evaluations(
        [
            row(
                1,
                70,
                1,
                training="A 仕上抜群",
                stable_comment="休み明けでも状態はいい",
                recent_runs=[
                    {"racecourse": "東京", "surface": "芝", "distance": 2000, "direction": "左", "finish": "2着"},
                    {"racecourse": "新潟", "surface": "芝", "distance": 2000, "direction": "左", "finish": "3着"},
                ],
            ),
            row(
                2,
                69,
                2,
                training="C 反応平凡",
                stable_comment="まだ良化途上",
                recent_runs=[{"racecourse": "阪神", "surface": "芝", "distance": 2000, "direction": "右", "finish": "2着"}],
            ),
        ],
        "jra",
        race_info={"venue": "中京", "surface": "芝", "distance": 2000, "turn": "左"},
    )
    by_no = {horse["number"]: horse for horse in result["rows"]}

    assert by_no["1"]["v2_condition_score"] == 3.0
    assert by_no["1"]["v2_recent_state_score"] == 2.0
    assert by_no["2"]["v2_condition_score"] == 1.0
    assert by_no["2"]["v2_recent_state_score"] == -2.0
    assert -2.0 <= by_no["2"]["v2_recent_state_score"] <= 2.0
    assert by_no["1"]["v2_jockey_score"] == 0.0


def test_v2_final_reason_keeps_training_basis_compact() -> None:
    result = build_v2_evaluations(
        [
            row(
                1,
                70,
                1,
                training="B 好気配｜87.6(18.8)68.8(15.3)53.5(14.8)",
                stable_comment="前走を見るとクラスにメド。状態はいい。",
            )
        ],
        "jra",
        race_info={"venue": "中京", "surface": "ダ", "distance": 1800, "turn": "左"},
    )

    reason = result["rows"][0]["v2_final_reason"]

    assert "調教B 好気配" in reason
    assert "コメント前向き" in reason
    assert "87.6" not in reason
