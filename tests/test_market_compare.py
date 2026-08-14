from __future__ import annotations

import copy
import unittest

import pandas as pd

from core.market_compare import (
    apply_market_compare_to_result,
    calibration_status,
    evaluate_market_table,
    market_prediction_signature,
    price_band_rows,
)
from core.models import PredictionResult
from core.prediction_history import build_prediction_snapshot
from core.ver4_engine import apply_prediction_logic, prediction_logic_version


RACE_INFO = {
    "race_id": "202630081210",
    "date": "2026-08-12",
    "venue": "大井",
    "race_number": "10R",
    "race_name": "能力価格比較テスト",
    "distance": 1600,
    "turn": "右",
    "class_label": "B3",
}


def row(number: int, score: float, odds: float, style: str = "先", **extra):
    value = {
        "馬番": number,
        "馬名": f"Horse{number}",
        "馬年齢": "牡4",
        "raw_score": score,
        "能力評価値": score,
        "AI点": 100 - number,
        "AI順位": number,
        "オッズ": odds,
        "人気": number,
        "脚質": style,
        "3走前": 60 + number,
        "2走前": 64 + number,
        "前走": 69 + number,
        "平均指数": 64 + number,
        "距離指数": 68 + number,
        "コース指数": 66 + number,
        "レース間隔": "中3週",
        "斤量": 56,
        "騎手": f"騎手{number}",
        "_current_class_label": "B3",
        "_previous_class_label": "C1",
        "_best_past_class_label": "B3",
        "_past_class_labels": ["C1", "C1", "B3"],
        "クラス変動": "クラス昇級",
        "_past_runs": [
            {"label": "3走前", "class_label": "B3", "position": 2, "distance": 1600, "racecourse": "大井"},
            {"label": "2走前", "class_label": "C1", "position": 1, "distance": 1400, "racecourse": "大井"},
            {"label": "前走", "class_label": "C1", "position": 2, "distance": 1600, "racecourse": "大井"},
        ],
    }
    value.update(extra)
    return value


class MarketCompareTest(unittest.TestCase):
    def test_aa_is_not_forced_and_a_can_contain_multiple_horses(self) -> None:
        table = pd.DataFrame(
            [
                row(1, 90.0, 2.5),
                row(2, 88.0, 4.5),
                row(3, 86.0, 11.4),
                row(4, 85.0, 23.7),
                row(5, 79.0, 40.0),
            ]
        )
        result = evaluate_market_table(table, "nar", RACE_INFO)
        self.assertNotIn("AA", set(result["ability_band_v2"]))
        self.assertEqual(list(result.loc[:3, "ability_band_v2"]), ["A", "A", "A", "A"])

    def test_clear_exceptional_top_can_be_aa(self) -> None:
        result = evaluate_market_table(
            pd.DataFrame([row(1, 98.0, 3.0), row(2, 92.0, 5.0), row(3, 89.0, 9.0)]),
            "jra",
            RACE_INFO,
        )
        self.assertEqual(result.loc[0, "ability_band_v2"], "AA")

    def test_price_popularity_jockey_interval_weight_and_pace_do_not_change_ability(self) -> None:
        original = pd.DataFrame([row(1, 90.0, 2.0, "逃"), row(2, 86.0, 5.0, "先"), row(3, 75.0, 80.0, "追")])
        changed = original.copy(deep=True)
        changed["オッズ"] = [80.0, 1.2, 999.0]
        changed["人気"] = [15, 1, 18]
        changed["騎手"] = ["有名騎手", "新人", "別騎手"]
        changed["レース間隔"] = ["長期休養", "連闘", "休み明け"]
        changed["斤量"] = [50, 60, 48]
        changed["脚質"] = ["追", "逃", "先"]
        left = evaluate_market_table(original, "nar", RACE_INFO)
        right = evaluate_market_table(changed, "nar", RACE_INFO)
        self.assertEqual(left["market_ability_score"].tolist(), right["market_ability_score"].tolist())
        self.assertEqual(left["market_ability_rank"].tolist(), right["market_ability_rank"].tolist())
        self.assertEqual(left["ability_band_v2"].tolist(), right["ability_band_v2"].tolist())

    def test_recorded_legacy_weight_state_adjustment_is_removed_only_in_new_mode(self) -> None:
        source = pd.DataFrame(
            [
                row(1, 92.5, 4.0, **{"_market_non_ability_adjustment": 2.5}),
                row(2, 88.0, 7.0, **{"_market_non_ability_adjustment": -1.0}),
            ]
        )
        result = evaluate_market_table(source, "jra", RACE_INFO)
        self.assertEqual(result["legacy_raw_score"].tolist(), [92.5, 88.0])
        self.assertEqual(result["market_ability_score"].tolist(), [90.0, 89.0])
        self.assertEqual(source["raw_score"].tolist(), [92.5, 88.0])
        self.assertEqual(set(result["ability_core_source"]), {"legacy_adjustment_fallback"})

    def test_explicit_ver3_core_is_authoritative_not_legacy_adjustments(self) -> None:
        first = pd.DataFrame(
            [
                row(1, 130.0, 73.5, **{"_ver3_ability_core": 90.0, "_market_non_ability_adjustment": 40.0}),
                row(2, 40.0, 2.1, **{"_ver3_ability_core": 88.0, "_market_non_ability_adjustment": -48.0}),
            ]
        )
        second = first.copy(deep=True)
        second["raw_score"] = [-500.0, 900.0]
        second["能力評価値"] = [-500.0, 900.0]
        second["_market_non_ability_adjustment"] = [-999.0, 777.0]
        second["斤量"] = [48.0, 62.0]
        second["騎手"] = ["別騎手A", "別騎手B"]
        second["脚質"] = ["追", "逃"]
        second["オッズ"] = [1.1, 500.0]
        second["人気"] = [1, 18]

        left = evaluate_market_table(first, "jra", RACE_INFO)
        right = evaluate_market_table(second, "jra", RACE_INFO)

        for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
            self.assertEqual(left[column].tolist(), right[column].tolist())
        self.assertEqual(left["market_ability_score"].tolist(), [90.0, 88.0])
        self.assertEqual(set(left["ability_core_source"]), {"explicit_ver3_core"})

    def test_a_longshot_remains_a_and_z_is_not_promoted_by_price(self) -> None:
        result = evaluate_market_table(
            pd.DataFrame([row(1, 90.0, 73.5), row(2, 88.0, 2.1), row(3, 60.0, 500.0)]),
            "jra",
            RACE_INFO,
        )
        self.assertEqual(result.loc[0, "ability_band_v2"], "A")
        self.assertEqual(result.loc[2, "ability_band_v2"], "Z")
        self.assertNotIn("買い", " / ".join(result.loc[0, "positive_materials"]))
        self.assertNotIn("VALUE", " / ".join(result.loc[0, "positive_materials"]))

    def test_band_price_view_is_sorted_by_odds_inside_band(self) -> None:
        result = evaluate_market_table(
            pd.DataFrame([row(1, 90.0, 23.7), row(2, 89.0, 2.5), row(3, 88.0, 11.4)]),
            "nar",
            RACE_INFO,
        )
        self.assertEqual([item["odds"] for item in price_band_rows(result)["A"]], [2.5, 11.4, 23.7])

    def test_state_class_pace_and_materials_are_independent_columns(self) -> None:
        table = pd.DataFrame(
            [
                row(1, 90.0, 4.0, "逃", **{"3走前": 54, "2走前": 68, "前走": 72, "_load_weight_change": -3}),
                row(2, 86.0, 8.0, "先", **{"3走前": 70, "2走前": 65, "前走": 58}),
                row(3, 83.0, 12.0, "追", **{"レース間隔": "休み明け"}),
            ]
        )
        result = evaluate_market_table(table, "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "state_arrow"], "↑")
        self.assertIn("54→68→72", result.loc[0, "state_transition"])
        self.assertIn("B3経験あり", result.loc[0, "class_basis_market"])
        self.assertEqual(result.loc[0, "pace_mark_market"], "○")
        self.assertIn("斤量-3.0kg", result.loc[0, "positive_materials"])
        self.assertIn("休み明け", result.loc[2, "negative_materials"])
        self.assertEqual(result.loc[0, "market_ability_score"], 90.0)

    def test_saved_class_runs_and_interval_are_used_when_display_value_is_unconfirmed(self) -> None:
        source = row(
            1,
            90.0,
            4.0,
            **{
                "レース間隔": "未確認",
                "_days_since_last": 35,
                "_current_class_rank": 45,
                "_current_class_label": "B3",
                "_previous_class_rank": 40,
                "_previous_class_label": "C1",
                "_class_shift": "同級",
                "_past_class_labels": [],
                "_past_runs": [
                    {"label": "前走", "class_rank": 40, "class_label": "C1", "position": 1},
                    {"label": "2走前", "class_rank": 45, "class_label": "B3", "position": 2},
                    {"label": "3走前", "class_rank": 40, "class_label": "C1", "position": 4},
                ],
            },
        )
        result = evaluate_market_table(pd.DataFrame([source]), "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "race_interval_market"], "中4週")
        self.assertEqual(result.loc[0, "class_shift_market"], "クラス昇級")
        self.assertIn("B3経験あり", result.loc[0, "class_basis_market"])
        self.assertIn("B3好走歴", result.loc[0, "class_basis_market"])

    def test_body_weight_is_display_only_and_preserves_ability(self) -> None:
        original = pd.DataFrame([row(1, 90.0, 4.0, **{"馬体重": "501(+31)", "_body_weight": 501, "_body_weight_change": 31})])
        changed = original.copy(deep=True)
        changed["馬体重"] = "470(-5)"
        changed["_body_weight"] = 470
        changed["_body_weight_change"] = -5
        left = evaluate_market_table(original, "nar", RACE_INFO)
        right = evaluate_market_table(changed, "nar", RACE_INFO)
        self.assertEqual(left.loc[0, "body_weight_market"], "501kg（+31）")
        self.assertEqual(right.loc[0, "body_weight_market"], "470kg（-5）")
        for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
            self.assertEqual(left[column].tolist(), right[column].tolist())

    def test_fair_odds_is_explicitly_uncalibrated(self) -> None:
        result = evaluate_market_table(pd.DataFrame([row(1, 90.0, 4.0)]), "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "fair_odds_display"], "未校正")
        self.assertEqual(calibration_status()["status"], "uncalibrated")
        self.assertIn("development/holdout", calibration_status()["reason"])

    def test_current_evaluation_rank_and_marks_are_separate_from_ability_rank(self) -> None:
        table = pd.DataFrame(
            [
                row(1, 90.0, 2.0, "先", **{"レース間隔": "休み明け", "3走前": 80, "2走前": 70, "前走": 60}),
                row(2, 88.0, 12.0, "差", **{"3走前": 60, "2走前": 68, "前走": 75, "_load_weight_change": -2}),
                row(3, 80.0, 30.0, "追"),
            ]
        )
        table["_course_context_status"] = "取得"
        table["_netkeiba_pace"] = "H"
        result = evaluate_market_table(table, "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "market_ability_rank"], 1)
        self.assertEqual(result.loc[1, "current_evaluation_rank"], 1)
        self.assertEqual(result.loc[1, "ai_current_mark"], "◎")
        self.assertEqual(result.loc[0, "ability_band_v2"], "A")
        self.assertEqual(result.loc[1, "ability_band_v2"], "A")

    def test_odds_do_not_change_current_factor_balance_or_ability(self) -> None:
        first = pd.DataFrame([row(1, 90.0, 2.0), row(2, 88.0, 50.0)])
        second = first.copy(deep=True)
        second["オッズ"] = [500.0, 1.1]
        left = evaluate_market_table(first, "nar", RACE_INFO)
        right = evaluate_market_table(second, "nar", RACE_INFO)
        for column in (
            "market_ability_score",
            "market_ability_rank",
            "ability_band_v2",
            "current_evaluation_balance",
        ):
            self.assertEqual(left[column].tolist(), right[column].tolist())

    def test_missing_jockey_stats_still_generates_ai_marks(self) -> None:
        result = evaluate_market_table(
            pd.DataFrame([row(1, 90.0, 4.0), row(2, 86.0, 8.0)]),
            "nar",
            RACE_INFO,
        )
        self.assertEqual(set(result["jockey_course_stats_market"]), {"騎手成績なし"})
        self.assertEqual(set(result["jockey_course_sample_market"]), {"参考値なし"})
        self.assertIn("◎", set(result["ai_current_mark"]))
        self.assertTrue(result["current_evaluation_rank"].notna().all())

    def test_high_jockey_rate_is_weak_and_cannot_rewrite_ability_band(self) -> None:
        base = pd.DataFrame([row(1, 90.0, 4.0), row(2, 86.0, 8.0)])
        stats = base.copy(deep=True)
        stats["_jockey_course_win_rate"] = [28, 2]
        stats["_jockey_course_quinella_rate"] = [46, 8]
        stats["_jockey_course_place_rate"] = [58, 12]
        stats["_jockey_course_starts"] = [459, 100]
        left = evaluate_market_table(base, "nar", RACE_INFO)
        right = evaluate_market_table(stats, "nar", RACE_INFO)
        for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
            self.assertEqual(left[column].tolist(), right[column].tolist())
        self.assertEqual(right.loc[0, "jockey_display_market"], "騎手1（複58%）")
        self.assertLessEqual(abs(float(right.loc[0, "current_evaluation_balance"]) - float(left.loc[0, "current_evaluation_balance"])), 0.25)

    def test_jockey_change_displays_previous_to_current(self) -> None:
        table = pd.DataFrame(
            [
                row(
                    1,
                    90.0,
                    4.0,
                    **{
                        "騎手": "塚本征(替)",
                        "_previous_jockey": "丸野勝虎",
                        "_jockey_changed": True,
                        "_jockey_course_place_rate": 27,
                        "_jockey_course_starts": 100,
                    },
                )
            ]
        )
        result = evaluate_market_table(table, "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "jockey_market"], "塚本征")
        self.assertEqual(result.loc[0, "previous_jockey_market"], "丸野勝虎")
        self.assertEqual(result.loc[0, "jockey_display_market"], "丸野勝虎 → 塚本征（複27%）")

    def test_continuing_jockey_is_shown_as_current_with_continuation(self) -> None:
        table = pd.DataFrame(
            [row(1, 90.0, 4.0, **{"騎手": "塚本征", "_previous_jockey": "塚本征", "_jockey_changed": False})]
        )
        result = evaluate_market_table(table, "nar", RACE_INFO)
        self.assertEqual(result.loc[0, "jockey_change_market"], "継続")
        self.assertEqual(result.loc[0, "jockey_display_market"], "塚本征（継）")

    def test_three_character_jockey_abbreviation_is_not_treated_as_a_change(self) -> None:
        base = pd.DataFrame(
            [
                row(
                    10,
                    88.2,
                    1.6,
                    **{"騎手": "矢野貴", "_previous_jockey": "矢野貴之", "_jockey_changed": False},
                )
            ]
        )
        result = evaluate_market_table(base, "nar", RACE_INFO)

        self.assertEqual(result.loc[0, "jockey_change_market"], "継続")
        self.assertEqual(result.loc[0, "jockey_display_market"], "矢野貴之（継）")
        self.assertNotIn("→", result.loc[0, "jockey_display_market"])
        self.assertEqual(result.loc[0, "market_ability_score"], 88.2)
        self.assertEqual(result.loc[0, "market_ability_rank"], 1)

    def test_unknown_previous_jockey_is_not_guessed(self) -> None:
        table = pd.DataFrame([row(1, 90.0, 4.0, **{"騎手": "塚本征(替)"})])
        result = evaluate_market_table(table, "nar", RACE_INFO)
        display = result.loc[0, "jockey_display_market"]
        self.assertEqual(display, "塚本征（替・前走騎手不明）")
        self.assertNotIn("→", display)

    def test_result_columns_cannot_change_prediction_signature(self) -> None:
        base = pd.DataFrame([row(1, 90.0, 4.0), row(2, 86.0, 8.0)])
        leaked = base.copy(deep=True)
        leaked["着順"] = [1, 2]
        leaked["単勝払戻"] = [400, 0]
        leaked["result"] = ["win", "lose"]
        self.assertEqual(
            market_prediction_signature(base, "nar", RACE_INFO),
            market_prediction_signature(leaked, "nar", RACE_INFO),
        )

    def test_new_mode_preserves_old_columns_and_freezes_comparison_snapshot(self) -> None:
        table = pd.DataFrame([row(1, 90.0, 4.0), row(2, 86.0, 8.0)])
        result = PredictionResult(
            race_mode="nar",
            race_name="能力価格比較テスト",
            race_info=copy.deepcopy(RACE_INFO),
            overall_table=table.copy(deep=True),
            horse_evaluation=table.copy(deep=True),
            status="ok",
        )
        before = result.overall_table[["raw_score", "AI点", "オッズ"]].copy(deep=True)
        apply_market_compare_to_result(result)
        pd.testing.assert_frame_equal(result.overall_table[["raw_score", "AI点", "オッズ"]], before)
        self.assertEqual(result.logic_version, "market")
        snapshot = build_prediction_snapshot(result)
        self.assertEqual(snapshot["logic_version"], "market")
        self.assertTrue(snapshot["market_compare"]["prediction_signature"])
        self.assertEqual(len(snapshot["market_compare"]["horses"]), 2)
        serialized = str(snapshot["market_compare"])
        self.assertNotIn("着順", serialized)
        self.assertNotIn("払戻", serialized)

    def test_market_version_routes_without_removing_legacy_modes(self) -> None:
        self.assertEqual(prediction_logic_version("能力×価格比較"), "market")
        self.assertEqual(prediction_logic_version("実戦モード"), "practical")
        self.assertEqual(prediction_logic_version("v4.1"), "v4.1")
        result = PredictionResult(
            race_mode="jra",
            race_info=copy.deepcopy(RACE_INFO),
            overall_table=pd.DataFrame([row(1, 90.0, 4.0)]),
            horse_evaluation=pd.DataFrame([row(1, 90.0, 4.0)]),
        )
        apply_prediction_logic(result, "market")
        self.assertEqual(result.logic_version, "market")


if __name__ == "__main__":
    unittest.main()
