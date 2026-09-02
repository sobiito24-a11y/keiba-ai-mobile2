from core.nar_race_diagnostics import (
    build_full_field_comparison,
    build_nar_full_field_comparison,
    build_nar_race_diagnostics,
    normalize_position_group,
    validate_v1_consistency,
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
            course_index=12,
            recent_runs=[{"venue": "東京", "finish": "2着"}, {"venue": "中山", "finish": "4着"}],
            _jockey_course_place_rate=31,
            jockey_change="継続",
            jockey_market="和田譲治",
            weight=56,
            previous_weight=56,
            body_weight="470kg",
            body_weight_change="-10",
            interval="中2週",
            class_record="今回C2",
            _h2h_latest="直近②に先着",
        ),
        _row(
            2,
            5,
            9,
            "先団",
            market_ability_score=12.5,
            condition_fit_level="same_turn_distance",
            course_index=-5,
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
    assert comparison["rows"][0]["jockey_info"] == "和田譲治｜継続｜複31%｜56.0kg（±0）"
    assert comparison["rows"][0]["weight"] == "56.0kg（±0）"
    assert comparison["rows"][0]["body_weight"] == "470kg（-10）"
    assert comparison["rows"][0]["interval"] == "中2週"
    assert comparison["rows"][0]["class_record"] == "今回C2"
    assert comparison["rows"][0]["matchup"] == "直近②に先着"
    assert comparison["rows"][0]["same_distance"] == "★"
    assert comparison["rows"][0]["same_course"] == "★"
    assert comparison["rows"][0]["same_turn"] == "★"
    assert comparison["rows"][1]["recent_win_label"] == "★"
    assert comparison["rows"][1]["recent_top3_label"] == "★★"
    assert comparison["rows"][1]["same_course"] == "—"
    assert "コース実績なし" not in comparison["rows"][1]["negative_tags"]
    assert "コース評価低め" in comparison["rows"][1]["negative_tags"]
    assert "4角前方" in comparison["rows"][1]["positive_tags"]
    assert comparison["rows"][2]["data_insufficient"] is True
    assert "能力材料不足" in comparison["rows"][2]["negative_tags"]
    assert comparison["transfer_watch"] is True
    assert build_nar_full_field_comparison(rows, race_mode="jra")["show"] is False


def test_nar_full_field_comparison_sort_modes() -> None:
    rows = [
        _row(1, 3, 2, "後方", market_ability_score=50, recent_runs=[{"venue": "笠松", "distance": "1400m", "time_index": "11"}]),
        _row(2, 1, 3, "先団", market_ability_score=80, recent_runs=[{"venue": "笠松", "distance": "1400m", "time_index": "22"}]),
        _row(3, 2, 1, "中団", market_ability_score=60, recent_runs=[{"venue": "笠松", "distance": "1400m", "time_index": "33"}]),
    ]

    by_number = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="horse_number")
    by_ability = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="ability")
    by_current = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="current")
    by_corner = build_nar_full_field_comparison(rows, race_mode="nar", sort_mode="corner4_front")

    assert [horse["number"] for horse in by_number["rows"]] == ["1", "2", "3"]
    assert [horse["number"] for horse in by_ability["rows"]] == ["2", "3", "1"]
    assert [horse["ability_value"] for horse in by_ability["rows"]] == [80.0, 60.0, 50.0]
    assert [horse["recent3_indices"] for horse in by_ability["rows"]] == ["22", "33", "11"]
    assert [horse["number"] for horse in by_current["rows"]] == ["2", "3", "1"]
    assert [horse["number"] for horse in by_corner["rows"]][0] == "2"


def test_full_field_comparison_keeps_ver3_audit_but_uses_pure_ability_top5() -> None:
    rows = [
        _row(
            6,
            2,
            2,
            "中団",
            馬名="メイプルタピット",
            ai_current_mark="○",
            最終印="◎",
            _最終印点=81.0,
            AI点=79.0,
            AI順位=2,
            能力評価値=79.0,
            recent_runs=[{"venue": "船橋", "distance": "1800m", "time_index": "12"}],
        ),
        _row(
            3,
            1,
            1,
            "先団",
            馬名="ルトンワージ",
            ai_current_mark="◎",
            最終印="○",
            _最終印点=80.0,
            AI点=80.0,
            AI順位=1,
            能力評価値=80.0,
            recent_runs=[{"venue": "船橋", "distance": "1800m", "time_index": "18"}],
        ),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar", sort_mode="current")
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert [horse["number"] for horse in comparison["rows"]] == ["3", "6"]
    assert by_number["6"]["mark"] == "◎"
    assert by_number["6"]["current_evaluation_rank"] == 1
    assert by_number["6"]["ability_rank"] == 2
    assert by_number["6"]["ability_value"] == 98.0
    assert by_number["6"]["baseline_mark"] == "○"
    assert by_number["6"]["baseline_current_evaluation_rank"] == 2
    assert by_number["6"]["baseline_ver3_final_mark"] == "◎"
    assert by_number["6"]["baseline_ver3_current_evaluation_rank"] == 1
    assert by_number["6"]["nar_top5_rank"] == 2
    assert by_number["6"]["nar_top5_score"] == 98.0
    assert by_number["6"]["nar_top5_mark"] == "○"
    assert by_number["3"]["mark"] == "○"
    assert by_number["3"]["current_evaluation_rank"] == 2
    assert by_number["3"]["nar_top5_rank"] == 1
    assert by_number["3"]["nar_top5_score"] == 99.0
    assert by_number["3"]["nar_top5_mark"] == "◎"


def test_nar_top5_final_mark_is_rank_based_not_legacy_mark() -> None:
    rows = [
        _row(1, 1, 1, "中団", ai_current_mark="◎", 最終印="☆", _最終印点=100),
        _row(2, 2, 2, "中団", ai_current_mark="○", 最終印="◎", _最終印点=90),
        _row(3, 3, 3, "中団", ai_current_mark="▲", 最終印="◎", _最終印点=80),
        _row(4, 4, 6, "中団", ai_current_mark="△", 最終印="◎", _最終印点=50),
        _row(5, 5, 4, "中団", ai_current_mark="☆", 最終印="☆", _最終印点=70),
        _row(6, 6, 5, "先団", ai_current_mark="◎", 最終印="◎", _最終印点=60),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar", sort_mode="current")
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert [horse["number"] for horse in comparison["rows"]] == ["1", "2", "3", "4", "5", "6"]
    assert [horse["nar_top5_rank"] for horse in comparison["rows"]] == [1, 2, 3, 4, 5, 6]
    assert [horse["nar_top5_mark"] for horse in comparison["rows"]] == ["◎", "○", "▲", "△", "△", ""]
    assert by_number["1"]["baseline_ver3_final_mark"] == "☆"
    assert by_number["5"]["baseline_ver3_final_mark"] == "☆"
    assert by_number["5"]["nar_top5_mark"] == "△"
    assert by_number["6"]["baseline_ver3_final_mark"] == "◎"
    assert by_number["6"]["baseline_ver3_current_evaluation_rank"] == 5
    assert by_number["6"]["nar_ver3_top5"] is True
    assert by_number["6"]["nar_pure_top5"] is False
    assert by_number["6"]["nar_top5_swap_status"] == "VER3_ONLY"
    assert by_number["6"]["nar_warning_candidate"] is True
    assert "能力順位以上に警戒" in by_number["6"]["nar_warning_reason"]
    assert by_number["6"]["nar_top5_mark"] == ""
    assert by_number["4"]["nar_top5_swap_status"] == "PURE_ONLY"


def test_nar_pure_ability_rank_uses_market_score_not_legacy_ai_rank() -> None:
    rows = [
        _row(9, 1, 1, "中団", market_ability_score=54.6),
        _row(6, 2, 2, "中団", market_ability_score=50.2),
        _row(4, 3, 3, "中団", market_ability_score=41.0),
        _row(1, 4, 4, "中団", market_ability_score=39.4),
        _row(8, 5, 5, "中団", market_ability_score=37.4),
        _row(3, 6, 6, "中団", market_ability_score=35.4),
        _row(7, 7, 7, "中団", market_ability_score=33.4),
        _row(5, 10, 10, "先団", market_ability_rank="", AI順位=10, market_ability_score=31.9),
        _row(11, 8, 8, "中団", market_ability_score=30.6),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar")
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert by_number["5"]["nar_pure_ability_score"] == 31.9
    assert by_number["5"]["nar_pure_ability_rank"] == 8
    assert by_number["5"]["ability_rank"] == 8
    assert "能力10位" not in by_number["5"]["negative_tags"]
    assert "能力8位" in by_number["5"]["negative_tags"]


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
            venue="中京競馬場",
            distance=1400,
            distance_index=43,
            course_index=48,
            jockey_display_market="川田将雅（継続）",
            _jockey_course_place_rate=35,
            jockey_change="継続",
            training_short="B 83.5(16.3)67.2(15.0)",
            stable_comment_market="順調に仕上がった。状態は良い。",
            recent_races=[
                {"label": "前走", "venue": "中京", "distance": "1400m", "time_index": "72", "finish": "2着", "matchup": "vs 3：先着"},
                {"label": "2走前", "venue": "東京", "distance": "1600m", "time_index": "68", "finish": "4着"},
                {"label": "3走前", "venue": "中京", "distance": "1400m", "time_index": "75", "finish": "1着"},
            ],
            matched_past_runs=[
                {"label": "前走", "venue": "中京", "distance": 1400, "time_index": "72"},
                {"label": "3走前", "venue": "中京", "distance": 1400, "time_index": "75"},
            ],
            condition_fit_level="same_turn_distance",
            weight=54,
            previous_weight=56,
            body_weight="444kg",
            body_weight_change="-14",
            interval="休み明け",
            class_record="今回G3",
            _h2h_label="対戦○",
        ),
        _row(2, None, 9, "位置不明", market_ability_score=None, jockey_display_market="田辺裕信"),
        _row(3, 4, 4, "前方", market_ability_score=60.0, style="逃げ"),
    ]

    comparison = build_full_field_comparison(rows, race_mode="jra")

    assert comparison["show"] is True
    assert [horse["number"] for horse in comparison["rows"]] == ["1", "2", "3"]
    assert comparison["rows"][0]["recent3_indices"] == "★72(左)（vs 3：先着） / 68(左) / ★75(左)"
    assert comparison["rows"][0]["recent3_conditions"] == "中京1400m / 東京1600m / 中京1400m"
    assert comparison["rows"][0]["distance_index"] == "43"
    assert comparison["rows"][0]["course_index"] == "48"
    assert comparison["rows"][0]["same_turn"] == "★"
    assert comparison["rows"][0]["same_turn_display"] == "○"
    assert comparison["rows"][0]["jockey_display"] == "川田将雅（継続） 35%"
    assert comparison["rows"][0]["jockey_info"] == "川田将雅｜継続｜複35%｜54.0kg（-2.0）"
    assert comparison["rows"][0]["training"] == "B"
    assert comparison["rows"][0]["stable_comment"] == "順調に仕上がった。状態は良い。"
    assert "83.5" not in comparison["rows"][0]["training"]
    assert comparison["rows"][0]["weight"] == "54.0kg（-2.0）"
    assert comparison["rows"][0]["body_weight"] == "444kg（-14）"
    assert comparison["rows"][0]["interval"] == "休み明け"
    assert comparison["rows"][0]["class_record"] == "今回G3"
    assert comparison["rows"][0]["matchup"] == "対戦○"
    assert comparison["rows"][1]["data_insufficient"] is True
    by_number = {horse["number"]: horse for horse in comparison["rows"]}
    assert by_number["3"]["corner4_display"] == "前方（逃げ）"


def test_full_field_comparison_passes_race_info_to_v1_axes_and_recent_stars() -> None:
    rows = [
        _row(
            5,
            4,
            2,
            "中団",
            馬名="ラップランド",
            market_ability_score=31.2,
            recent_runs=[{"racecourse": "船橋", "distance": "2200m", "time_index": "18", "finish": "3着"}],
        ),
        _row(
            6,
            8,
            8,
            "先団",
            馬名="ヒロシゲジャック",
            market_ability_score=20.5,
            recent_runs=[{"racecourse": "船橋競馬場", "distance": 2200, "time_index": "9", "finish": "8着"}],
        ),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar", race_info={"racecourse": "船橋", "distance": 2200})
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert by_number["5"]["v1_reproducibility"] == "A"
    assert "船橋2200m" in by_number["5"]["v1_reproducibility_reason"]
    assert by_number["5"]["recent3_indices"] == "★18"
    assert by_number["6"]["v1_reproducibility"] == "C"
    assert by_number["6"]["v1_pace_eval"] == "○"
    assert comparison["v1_recommendations"][0]["name"]
    assert "再現性" in comparison["v1_summary"]


def test_v1_final_consistency_promotes_condition_specialist_without_overwriting_baseline() -> None:
    rows = [
        _row(7, 1, 1, "先団", 馬名="レルアバド", market_ability_score=70, recent_runs=[]),
        _row(9, 2, 2, "先団", 馬名="セイノスケ", market_ability_score=68, recent_runs=[]),
        _row(11, 3, 3, "中団", 馬名="ジラルデ", market_ability_score=66, recent_runs=[]),
        _row(2, 4, 4, "中団", 馬名="ゴッドトレジャー", market_ability_score=64, recent_runs=[]),
        _row(
            5,
            10,
            12,
            "後方",
            馬名="ラップランド",
            ai_current_mark="",
            market_ability_score=48.7,
            recent_runs=[{"racecourse": "船橋", "distance": "2200m", "time_index": "18", "finish": "1着"}],
        ),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar", race_info={"racecourse": "船橋", "distance": 2200})
    by_number = {horse["number"]: horse for horse in comparison["rows"]}
    recommendations = comparison["v1_recommendations"]

    assert validate_v1_consistency(comparison)["ok"] is True
    assert [horse["number"] for horse in recommendations] == comparison["v1_summary_top_horses"][: len(recommendations)]
    lapland = by_number["5"]
    assert lapland["v1_reproducibility"] == "A"
    assert lapland["v1_final_role"] == "条件スペシャリスト"
    assert lapland["v1_final_mark"] == "☆"
    assert lapland["v1_final_rank"] == 4
    assert lapland["baseline_current_evaluation_rank"] == 12
    assert lapland["baseline_mark"] == ""


def test_jockey_info_shows_previous_to_current_for_change() -> None:
    comparison = build_full_field_comparison(
        [
            _row(
                1,
                1,
                1,
                "中団",
                jockey_market="戸崎圭太",
                jockey_change="乗替",
                previous_jockey="横山武史",
                _jockey_course_place_rate=28,
                weight=56,
                previous_weight=56,
            ),
            _row(
                2,
                2,
                2,
                "中団",
                jockey_market="川田将雅",
                jockey_change="継続",
                _jockey_course_place_rate=35,
                weight=54,
                previous_weight=56,
            ),
        ],
        race_mode="jra",
    )
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert by_number["1"]["jockey_info"] == "戸崎圭太｜乗替：横山武史→戸崎圭太｜複28%｜56.0kg（±0）"
    assert by_number["2"]["jockey_info"] == "川田将雅｜継続｜複35%｜54.0kg（-2.0）"


def test_jra_same_turn_is_independent_from_same_course() -> None:
    left_with_left_runs = _row(
        1,
        1,
        1,
        "中団",
        venue="東京",
        distance="1600m",
        recent_runs=[
            {"venue": "中京", "distance": "1400m", "time_index": "10"},
            {"venue": "京都", "distance": "1600m", "time_index": "11"},
        ],
    )
    left_with_right_runs = _row(
        2,
        2,
        2,
        "中団",
        venue="東京",
        distance="1600m",
        recent_runs=[
            {"venue": "中山", "distance": "1600m", "time_index": "12"},
            {"venue": "阪神", "distance": "1800m", "time_index": "13"},
            {"venue": "京都", "distance": "1600m", "time_index": "14"},
        ],
    )
    missing_turn = _row(3, 3, 3, "中団", venue="", distance="1600m", recent_runs=[{"venue": "", "distance": "1600m"}])

    comparison = build_full_field_comparison(
        [left_with_left_runs, left_with_right_runs, missing_turn],
        race_mode="jra",
    )
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert by_number["1"]["same_course"] == "—"
    assert by_number["1"]["same_turn_display"] == "○"
    assert by_number["2"]["same_turn_display"] == "×"
    assert by_number["3"]["same_turn_display"] == "—"


def test_recent3_star_falls_back_to_saved_current_venue_and_distance() -> None:
    rows = [
        _row(
            1,
            1,
            1,
            "先団",
            venue="園田競馬場",
            distance=1400,
            recent_runs=[
                {"venue": "園田", "distance": "ダート1400m", "time_index": "13", "finish": "2着"},
                {"venue": "姫路", "distance": "1400m", "time_index": "-10", "finish": "4着"},
                {"venue": "園田", "distance": "820m", "time_index": "2", "finish": "5着"},
            ],
        )
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar")

    assert comparison["rows"][0]["recent3_indices"] == "★13 / -10 / 2"
    assert comparison["rows"][0]["recent3_conditions"] == "園田ダート1400m / 姫路1400m / 園田820m"


def test_recent3_star_uses_current_venue_and_distance_not_matched_runs_only() -> None:
    rows = [
        _row(
            1,
            1,
            1,
            "中団",
            venue="園田",
            distance="820m",
            recent_runs=[
                {"label": "前走", "venue": "園田", "distance": "1400m", "time_index": "13"},
                {"label": "2走前", "venue": "園田", "distance": "820m", "time_index": "7"},
            ],
            matched_past_runs=[
                {"label": "前走", "venue": "園田", "distance": "1400m", "time_index": "13"},
            ],
        )
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar")

    assert comparison["rows"][0]["recent3_indices"] == "13 / ★7"


def test_recent3_star_uses_saved_condition_reason_when_race_fields_are_not_on_horse_row() -> None:
    rows = [
        _row(
            1,
            1,
            1,
            "中団",
            condition_fit_reason="笠松 1400mの過去走あり",
            recent_races=[
                {"venue": "笠松", "distance": "1400m", "time_index": "18"},
                {"venue": "名古屋", "distance": "1400m", "time_index": "28"},
                {"venue": "笠松", "distance": "1600m", "time_index": "43"},
            ],
        )
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar")

    assert comparison["rows"][0]["recent3_indices"] == "★18 / 28 / 43"


def test_full_field_comparison_extracts_sex_age_from_saved_key_variants() -> None:
    rows = [
        _row(6, 1, 1, "中団", 馬名="マモリーフィルム", 馬年齢="牡4"),
        _row(3, 2, 2, "中団", 馬名="サンプルレディ", sexage="牝3"),
        _row(8, 3, 3, "中団", 馬名="テストセン", sex="セ", age=5),
        _row(9, 4, 4, "中団", 馬名="セイレイフメイ"),
    ]

    comparison = build_full_field_comparison(rows, race_mode="nar")
    by_number = {horse["number"]: horse for horse in comparison["rows"]}

    assert by_number["6"]["sex_age"] == "牡4"
    assert by_number["3"]["sex_age"] == "牝3"
    assert by_number["8"]["sex_age"] == "セ5"
    assert by_number["9"]["sex_age"] == ""
