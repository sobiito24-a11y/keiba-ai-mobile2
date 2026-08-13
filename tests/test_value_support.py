# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from core.models import PredictionResult
from core.prediction_history import build_prediction_snapshot
from core.value_support import attach_value_signals, course_material_display, training_display


class ValueSupportTest(unittest.TestCase):
    def test_jra_training_display_uses_rank_and_omits_raw_lap_text(self) -> None:
        ranked = training_display({"調教評価": "A", "調教コメント": "上昇気配あり"}, "jra")
        raw_lap = training_display({"調教評価": "83.5(16.3)67.2(15.0)"}, "jra")
        nar = training_display({"調教評価": "A"}, "nar")

        self.assertEqual(ranked["display"], "調教A↑ 仕上上々")
        self.assertEqual(raw_lap["display"], "")
        self.assertEqual(nar["display"], "")

    def test_value_signal_requires_materials_not_high_odds_only(self) -> None:
        rows = attach_value_signals(
            [
                {"馬番": 1, "馬名": "HighOnly", "オッズ": 100, "能力帯": "Z", "能力順位": 11, "AI順位": 10},
                {"馬番": 2, "馬名": "Value", "オッズ": 35.1, "能力帯": "B", "能力順位": 3, "AI順位": 4, "表示印": "△", "近3走傾向": "上昇", "距離指数": 65, "調教評価": "A"},
            ],
            "jra",
        )

        self.assertFalse(rows[0]["value_signal"])
        self.assertTrue(rows[1]["value_signal"])
        self.assertIn("能力3位", rows[1]["value_reason"])
        self.assertEqual(rows[1]["AI順位"], 4)
        self.assertEqual(rows[1]["表示印"], "△")

    def test_value_signal_is_capped_to_two_horses_without_forcing_pick(self) -> None:
        value_rows = [
            {"馬番": no, "馬名": f"H{no}", "オッズ": 12 + no, "能力帯": "A", "能力順位": no, "AI順位": no, "表示印": "▲", "距離指数": 70}
            for no in (1, 2, 3)
        ]
        capped = attach_value_signals(value_rows, "jra")
        none = attach_value_signals([{"馬番": 9, "馬名": "NoValue", "オッズ": 3.0, "能力帯": "A", "能力順位": 1, "AI順位": 1}], "jra")

        self.assertEqual(sum(1 for row in capped if row["value_signal"]), 2)
        self.assertEqual(sum(1 for row in none if row["value_signal"]), 0)

    def test_course_material_separates_netkeiba_favorable_from_app_fit(self) -> None:
        display = course_material_display({"展開印": "○", "推定位置": "差し", "netkeiba推定有利馬": "有利"})

        self.assertIn("○", display["label"])
        self.assertEqual(display["netkeiba_label"], "○ 推定有利馬")

    def test_course_material_does_not_force_flat_text_without_horse_specific_data(self) -> None:
        display = course_material_display({"course_development_reason": "4角傾向フラット"})

        self.assertEqual(display["label"], "")
        self.assertEqual(display["tone"], "neutral")

    def test_prediction_history_saves_value_support_without_mutating_result(self) -> None:
        table = pd.DataFrame(
            [
                {"馬番": 2, "馬名": "Value", "オッズ": 35.1, "能力帯": "B", "能力順位": 3, "AI順位": 4, "表示印": "△", "近3走傾向": "上昇", "距離指数": 65, "調教評価": "A"},
                {"馬番": 8, "馬名": "NoValue", "オッズ": 3.2, "能力帯": "A", "能力順位": 1, "AI順位": 1, "表示印": "◎"},
            ]
        )
        result = PredictionResult(race_mode="jra", overall_table=table.copy(), horse_evaluation=table.copy())
        before_columns = list(result.overall_table.columns)

        snapshot = build_prediction_snapshot(result)
        horse = next(item for item in snapshot["horses"] if str(item["horse_no"]) == "2")

        self.assertTrue(horse["value_support"]["value_signal"])
        self.assertIn("value_reason", horse["support"])
        self.assertEqual(list(result.overall_table.columns), before_columns)


if __name__ == "__main__":
    unittest.main()
