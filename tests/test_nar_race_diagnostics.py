from core.nar_race_diagnostics import (
    build_full_field_comparison,
    build_nar_full_field_comparison,
    build_nar_race_diagnostics,
    normalize_position_group,
)


def _row(no, rank, current, corner4, **extra):
    data = {
        "馬番": no,
        "馬名": f"馬{no}",
        "ai_current_mark": {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "☆"}.get(rank, ""),
        "market_ability_rank": rank,
        "market_ability_score": 100 - (rank or 9),
        "current_evaluation_rank": current,
        "running_style_market": extra.pop("style", "差し"),
        "position_start_label_market": extra.pop("start", "中団"),
        "position_corner3_label_market": extra.pop("corner3", "中団"),
        "position_corner4_label_market": corner4,
    }
    data.update(extra)
    return data


def test_nar_diagnostics_classifies_top3_front_and_unknown_positions() -> None:
    diagnostics = build_nar_race_diagnostics(
        [
            _row(1, 1, 1, "中団"),
            _row(2, 3, 2, "先団"),
            _row(3, 5, 9, "先団", style="先行"),
            _row(4, 7, 8, "先団"),
            _row(5, 7, 4, "後方"),
            _row(6, 8, 8, "中団", recent_runs=[{"finish": "3着"}]),
            _row(7, None, 10, "先団", market_ability_score=None),
            _row(8, 4, 5, "位置不明"),
        ],
        race_mode="nar",
    )

    assert [horse["number"] for horse in diagnostics["win_candidates"]] == ["1", "2"]
    assert {horse["number"] for horse in diagnostics["main_partners"]} == {"2", "3"}
    assert {horse["number"] for horse in diagnostics["pace_watch"]} == {"2", "3", "4", "7"}
    assert {horse["number"] for horse in diagnostics["ability_outside_watch"]} == {"5", "6"}
    assert {horse["number"] for horse in diagnostics["data_insufficient_watch"]} == {"7"}
    assert "4" not in {horse["number"] for horse in diagnostics["ability_outside_watch"]}
    assert diagnostics["positions"]["corner4"]["front"][0]["number"] == "2"
    assert diagnostics["positions"]["corner4"]["unknown"][0]["number"] == "8"


def test_nar_diagnostics_uses_saved_position_path_and_ignores_jra() -> None:
    row = _row(9, 2, 3, "", position_path_market="後方 → 中団 → 先団")
    diagnostics = build_nar_race_diagnostics([row], race_mode="nar")

    assert diagnostics["main_partners"][0]["number"] == "9"
    assert diagnostics["main_partners"][0]["corner4_label"] == "先団"
    assert normalize_position_group("中団") == "middle"
    assert normalize_position_group("後方") == "back"
    assert build_nar_race_diagnostics([row], race_mode="jra")["show"] is False


def test_nar_full_field_comparison_keeps_all_horses_and_display_facts() -> None:
    rows = [
        _row(
            1,
            1,
            1,
            "中団",
            market_ability_score=26.8,
            condition_fit_level="same_venue_distance",
            recent_runs=[{"venue": "東京", "finish": "2着"}, {"venue": "中山", "finish": "4着"}],
            _jockey_course_place_rate=31,
        ),
        _row(
            2,
            5,
            9,
            "先団",
            market_ability_score=12.5,
            condition_fit_level="same_turn_distance",
            recent_runs=[{"venue": "門別", "finish": "1着"}, {"venue": "門別", "finish": "3着"}],
            style="先行",
        ),
        _row(
            7,
            None,
            10,
            "先団",
            market_ability_score=None,
            recent_runs=[],
        ),
    ]

    comparison = build_nar_full_field_comparison(rows, race_mode="nar")

    assert [horse["number"] for horse in comparison["rows"]] == ["1", "2", "7"]
    assert round(comparison["gap_1_2"], 1) == 14.3
    assert comparison["rows"][0]["ability_gap_text"] == "0"
    assert comparison["rows"][0]["transfer_status"] == "JRA→NAR初戦"
    assert comparison["rows"][0]["jockey_course_place_rate"] == "31%"
    assert comparison["rows"][0]["same_distance"] == "★"
    assert comparison["rows"][0]["same_course"] == "★"
    assert comparison["rows"][0]["same_turn"] == "★"
    assert comparison["rows"][1]["recent_win_label"] == "★"
    assert comparison["rows"][1]["recent_top3_label"] == "★★"
    assert comparison["rows"][1]["same_course"] == "—"
    assert "4角前方" in comparison["rows"][1]["positive_tags"]
    assert comparison["rows"][2]["data_insufficient"] is True
    assert "能力材料不足" in comparison["rows"][2]["negative_tags"]
    assert comparison["transfer_watch"] is True
    assert build_nar_full_field_comparison(rows, race_mode="jra")["show"] is False


def test_nar_full_field_comparison_sort_modes() -> None:
    rows = [
        _row(8, 4, 2, "後方", market_ability_score=30),
        _row(2, 2, 3, "先団", market_ability_score=40),
        _row(5, 1, 1, "中団", market_ability_score=50),
    ]

    by_number = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="horse_number")
    by_ability = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="ability")
    by_current = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="current")
    by_corner = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="corner4_front")

    assert [horse["number"] for horse in by_number["rows"]] == ["2", "5", "8"]
    assert [horse["number"] for horse in by_ability["rows"]] == ["5", "2", "8"]
    assert [horse["number"] for horse in by_current["rows"]] == ["5", "8", "2"]
    assert [horse["number"] for horse in by_corner["rows"]][0] == "2"


def test_monbetsu_5r_expected_research_categories_without_result_data() -> None:
    rows = [
        _row(10, 1, 1, "中団", market_ability_score=26.8, style="差し"),
        _row(2, 5, 9, "前方", market_ability_score=12.5, style="先行"),
        _row(7, None, 10, "前方", market_ability_score=None, style="差し"),
        _row(4, 6, 8, "中団", market_ability_score=10.1, style="差し"),
    ]

    diagnostics = build_nar_race_diagnostics(rows, race_mode="nar")
    comparison = build_nar_full_field_comparison(rows, race_mode="nar")

    assert {horse["number"] for horse in diagnostics["win_candidates"]} == {"10"}
    assert {horse["number"] for horse in diagnostics["main_partners"]} == {"2"}
    assert {horse["number"] for horse in diagnostics["pace_watch"]} == {"2", "7"}
    assert {horse["number"] for horse in diagnostics["data_insufficient_watch"]} == {"7"}
    assert "4" not in {horse["number"] for horse in diagnostics["ability_outside_watch"]}
    by_number = {horse["number"]: horse for horse in comparison["rows"]}
    assert by_number["10"]["corner4_group"] == "middle"
    assert by_number["2"]["corner4_group"] == "front"
    assert by_number["7"]["data_insufficient"] is True


def test_full_field_comparison_supports_jra_display_fields_without_diagnostics() -> None:
    rows = [
        _row(
            1,
            1,
            1,
            "中団",
            market_ability_score=72.4,
            distance_index=43,
            course_index=48,
            jockey_display_market="川田将雅（継続）",
            _jockey_course_place_rate=35,
            jockey_change="継続",
            training_short="B 83.5(16.3)67.2(15.0)",
            recent_races=[
                {"label": "前走", "venue": "中京", "distance": "1400m", "time_index": "72", "finish": "2着"},
                {"label": "2走前", "venue": "東京", "distance": "1600m", "time_index": "68", "finish": "4着"},
                {"label": "3走前", "venue": "中京", "distance": "1400m", "time_index": "75", "finish": "1着"},
            ],
            matched_past_runs=[
                {"label": "前走", "venue": "中京", "distance": 1400, "time_index": "72"},
                {"label": "3走前", "venue": "中京", "distance": 1400, "time_index": "75"},
            ],
            condition_fit_level="same_turn_distance",
        ),
        _row(2, None, 9, "位置不明", market_ability_score=None, jockey_display_market="田辺裕信"),
    ]

    comparison = build_full_field_comparison(rows, race_mode="jra")

    assert comparison["show"] is True
    assert [horse["number"] for horse in comparison["rows"]] == ["1", "2"]
    assert comparison["rows"][0]["recent3_indices"] == "★72 / 68 / ★75"
    assert comparison["rows"][0]["recent3_conditions"] == "中京1400m / 東京1600m / 中京1400m"
    assert comparison["rows"][0]["distance_index"] == "43"
    assert comparison["rows"][0]["course_index"] == "48"
    assert comparison["rows"][0]["same_turn"] == "★"
    assert comparison["rows"][0]["jockey_display"] == "川田将雅（継続） 35%"
    assert comparison["rows"][0]["training"] == "調教B↑ 仕上上々"
    assert "83.5" not in comparison["rows"][0]["training"]
    assert comparison["rows"][1]["data_insufficient"] is True
