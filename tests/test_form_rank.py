from __future__ import annotations

import unittest

import pandas as pd

from core.audit_features import add_audit_evaluation_columns
from core.form_rank import ability_rank, momentum_for_row


class FormRankTest(unittest.TestCase):
    def test_momentum_continuous_rise(self) -> None:
        result = momentum_for_row(pd.Series({"3走前": 38, "2走前": 45, "前走": 50}))

        self.assertIn(result.rank, {"A", "S"})
        self.assertEqual(result.trend, "連続上昇")
        self.assertEqual(result.valid_count, 3)

    def test_momentum_continuous_decline(self) -> None:
        result = momentum_for_row(pd.Series({"3走前": 50, "2走前": 45, "前走": 38}))

        self.assertIn(result.rank, {"C", "D"})
        self.assertEqual(result.trend, "連続下降")

    def test_momentum_flat(self) -> None:
        result = momentum_for_row(pd.Series({"3走前": 48, "2走前": 50, "前走": 49}))

        self.assertEqual(result.rank, "B")
        self.assertEqual(result.trend, "横ばい")

    def test_momentum_rebound(self) -> None:
        result = momentum_for_row(pd.Series({"3走前": 55, "2走前": 40, "前走": 52}))

        self.assertIn(result.trend, {"持ち直し", "反発"})

    def test_momentum_missing_values_are_safe(self) -> None:
        one_value = momentum_for_row(pd.Series({"3走前": None, "2走前": None, "前走": 42}))
        no_value = momentum_for_row(pd.Series({"3走前": None, "2走前": None, "前走": None}))

        self.assertEqual(one_value.rank, "判定保留")
        self.assertEqual(no_value.rank, "未判定")

    def test_ability_and_momentum_are_independent(self) -> None:
        high_ability_rank, _ = ability_rank(90)
        high_ability_decline = momentum_for_row(pd.Series({"3走前": 60, "2走前": 52, "前走": 40}))
        low_ability_rank, _ = ability_rank(60)
        low_ability_rise = momentum_for_row(pd.Series({"3走前": 30, "2走前": 38, "前走": 50}))

        self.assertEqual(high_ability_rank, "S")
        self.assertIn(high_ability_decline.rank, {"C", "D"})
        self.assertEqual(low_ability_rank, "D")
        self.assertIn(low_ability_rise.rank, {"A", "S"})

    def test_audit_adds_form_columns_without_mutating_existing_prediction(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": 1,
                    "馬名": "テストホース",
                    "AI点": 91.2,
                    "_raw_score": 83.2,
                    "能力評価値": 83.2,
                    "最終印": "◎",
                    "_最終印点": 94.5,
                    "3走前": 38,
                    "2走前": 45,
                    "前走": 50,
                }
            ]
        )
        before = frame.loc[0, ["AI点", "_raw_score", "能力評価値", "最終印"]].copy()

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(result.loc[0, "AI点"], before["AI点"])
        self.assertEqual(result.loc[0, "_raw_score"], before["_raw_score"])
        self.assertEqual(result.loc[0, "能力評価値"], before["能力評価値"])
        self.assertEqual(result.loc[0, "最終印"], before["最終印"])
        self.assertEqual(result.loc[0, "ability_rank"], "S")
        self.assertIn(result.loc[0, "momentum_rank"], {"A", "S"})
        self.assertIn("power_group", result.columns)
        self.assertIn("check_summary", result.columns)


if __name__ == "__main__":
    unittest.main()
