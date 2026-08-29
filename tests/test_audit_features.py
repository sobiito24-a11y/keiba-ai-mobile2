from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from core.audit_features import add_audit_evaluation_columns


class AuditFeaturesTest(unittest.TestCase):
    def test_raw_score_is_preserved_and_not_minmax_displayed_as_100(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": 1,
                    "馬名": "トップ",
                    "AI点": 100.0,
                    "_raw_score": 92.4,
                    "AI順位": 1,
                    "最終印": "◎",
                    "_最終印点": 101.0,
                    "市場反映勝率": 32.1,
                    "勝率順位": 1,
                    "_prev_values": [91, 92, 93],
                    "平均指数": 92,
                    "前走": 93,
                    "_重大マイナス数": 0,
                    "脚質": "先",
                },
                {
                    "馬番": 2,
                    "馬名": "セカンド",
                    "AI点": 88.0,
                    "_raw_score": 89.2,
                    "AI順位": 2,
                    "最終印": "○",
                    "_最終印点": 88.5,
                    "市場反映勝率": 20.0,
                    "勝率順位": 2,
                    "_prev_values": [88, 89, 90],
                    "平均指数": 89,
                    "前走": 90,
                    "_重大マイナス数": 0,
                    "脚質": "差",
                },
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="jra")

        self.assertEqual(result.loc[0, "raw_score"], 92.4)
        self.assertEqual(result.loc[0, "ability_display_score"], 92.4)
        self.assertNotEqual(result.loc[0, "ability_display_score"], 100.0)
        self.assertEqual(result.loc[0, "normalized_ai_score"], 100.0)
        self.assertEqual(result.loc[0, "最終印"], "◎")
        self.assertEqual(result.loc[0, "running_style_display"], "先行")
        self.assertEqual(result.loc[1, "脚質表示"], "差し")

    def test_existing_ai_score_and_marks_are_not_mutated(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": 1, "AI点": 100.0, "_raw_score": 90.0, "AI順位": 1, "最終印": "◎", "_最終印点": 101.0},
                {"馬番": 2, "AI点": 90.0, "_raw_score": 85.0, "AI順位": 2, "最終印": "○", "_最終印点": 90.0},
                {"馬番": 3, "AI点": 80.0, "_raw_score": 80.0, "AI順位": 3, "最終印": "✓", "_最終印点": 80.0},
            ]
        )
        before_ai = frame["AI点"].copy()
        before_mark = frame["最終印"].copy()

        result = add_audit_evaluation_columns(frame, race_type="jra")

        pd.testing.assert_series_equal(result["AI点"], before_ai, check_names=False)
        pd.testing.assert_series_equal(result["最終印"], before_mark, check_names=False)
        self.assertEqual(result.loc[2, "old_final_mark"], "✓")
        self.assertTrue(bool(result.loc[2, "old_watch_mark"]))

    def test_axis_confidence_handles_missing_values(self) -> None:
        frame = pd.DataFrame([{"馬番": 1, "AI点": pd.NA, "最終印": "", "_raw_score": pd.NA}])

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(result.loc[0, "axis_confidence"], "C")
        self.assertIn("欠損", result.loc[0, "axis_confidence_reason"])

    def test_training_c_alone_does_not_remove_watch_or_hole_classification(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": 8,
                    "AI点": 83.0,
                    "_raw_score": 88.0,
                    "AI順位": 5,
                    "最終印": "✓",
                    "_最終印点": 86.0,
                    "単勝オッズ": 16.0,
                    "評価/検討材料": "高指数 / 距離実績",
                    "調教評価": "C",
                }
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="jra")

        self.assertEqual(result.loc[0, "old_final_mark"], "✓")
        self.assertTrue(bool(result.loc[0, "hole_candidate"]) or bool(result.loc[0, "watch_horse"]))

    def test_hole_candidate_is_limited_to_two(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": number,
                    "AI点": 80.0 - number,
                    "_raw_score": 88.0 - number,
                    "AI順位": number,
                    "最終印": "✓",
                    "_最終印点": 90.0 - number,
                    "単勝オッズ": 12.0 + number,
                    "評価/検討材料": "高指数 / コース実績",
                }
                for number in range(1, 6)
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertLessEqual(int(result["hole_candidate"].sum()), 2)
        self.assertLessEqual(int(result["display_mark"].eq("✓").sum()), 2)
        self.assertGreaterEqual(int(result["watch_horse"].sum()), 1)

    def test_display_mark_limits_old_watch_marks_without_mutating_final_mark(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": number,
                    "AI点": 90.0 - number,
                    "_raw_score": 88.0 - number,
                    "AI順位": number,
                    "最終印": "✓",
                    "_最終印点": 100.0 - number,
                    "単勝オッズ": 12.0 + number,
                    "評価/検討材料": "高指数 / コース実績",
                }
                for number in range(1, 6)
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="jra")

        self.assertTrue(result["最終印"].eq("✓").all())
        self.assertTrue(result["old_watch_mark"].all())
        self.assertEqual(int(result["hole_candidate"].sum()), 2)
        self.assertEqual(int(result["display_mark"].eq("✓").sum()), 2)
        self.assertEqual(int(result["表示印"].eq("✓").sum()), 2)
        self.assertGreaterEqual(int(result["watch_horse"].sum()), 3)
        self.assertTrue(result.loc[result["display_mark"].ne("✓"), "表示印"].eq("").all())
        self.assertEqual(list(result["display_group"]), ["SS", "SS", "A", "A", "B"])
        self.assertNotIn("D", set(result["display_group"]))
        self.assertTrue(result["original_mark"].eq("✓").all())

    def test_legacy_final_mark_function_is_not_called_by_mobile_wrappers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ["core/jra_notebook_logic.py", "core/nar_notebook_logic.py"]:
            source = (root / relative).read_text(encoding="utf-8")
            wrapper_start = source.index("def _run_")
            wrapper_source = source[wrapper_start:]
            self.assertNotIn("add_final_marks_v1_legacy(", wrapper_source)


if __name__ == "__main__":
    unittest.main()
