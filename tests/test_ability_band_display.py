from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from core.audit_features import add_audit_evaluation_columns, build_audit_export_table


class AbilityBandDisplayTest(unittest.TestCase):
    def test_close_raw_scores_are_small_gap_mixed_race(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "A", "AI点": 100.0, "_raw_score": 83.2, "最終印": "◎"},
                {"馬番": 2, "馬名": "B", "AI点": 98.0, "_raw_score": 81.0, "最終印": "○"},
                {"馬番": 3, "馬名": "C", "AI点": 96.0, "_raw_score": 79.6, "最終印": "▲"},
                {"馬番": 4, "馬名": "D", "AI点": 94.0, "_raw_score": 79.1, "最終印": "△"},
                {"馬番": 5, "馬名": "E", "AI点": 92.0, "_raw_score": 78.7, "最終印": "✓"},
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="jra")

        self.assertEqual(result.loc[0, "ability_display_score"], 83.2)
        self.assertEqual(result.loc[0, "ability_gap_level"], "小")
        self.assertEqual(result.loc[0, "race_difficulty"], "混戦")
        self.assertIn("接近", result.loc[0, "race_difficulty_reason"])
        self.assertTrue(set(result["ability_band"]).issubset({"上位帯", "中位帯", "下位帯", "未評価"}))
        self.assertNotIn("下位帯", set(result["ability_band"]))
        self.assertIn("能力差が小さい", result.loc[0, "display_comment"])

    def test_clear_raw_score_gap_is_easy_to_narrow(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": 1, "AI点": 100.0, "_raw_score": 100.0, "最終印": "◎"},
                {"馬番": 2, "AI点": 92.0, "_raw_score": 93.0, "最終印": "○"},
                {"馬番": 3, "AI点": 84.0, "_raw_score": 86.0, "最終印": "▲"},
                {"馬番": 4, "AI点": 76.0, "_raw_score": 70.0, "最終印": "△"},
                {"馬番": 5, "AI点": 68.0, "_raw_score": 55.0, "最終印": ""},
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(result.loc[0, "ability_gap_level"], "大")
        self.assertEqual(result.loc[0, "race_difficulty"], "絞りやすい")
        self.assertEqual(result.loc[0, "ability_band"], "上位帯")
        self.assertEqual(result.loc[4, "ability_band"], "下位帯")

    def test_audit_export_keeps_hidden_and_new_fields(self) -> None:
        frame = pd.DataFrame([{"馬番": 1, "馬名": "A", "脚質": "先", "AI点": 100.0, "_raw_score": 83.2, "最終印": "◎"}])

        result = add_audit_evaluation_columns(frame, race_type="jra")
        audit = build_audit_export_table(result)

        for column in [
            "raw_score",
            "normalized_ai_score",
            "ai_rank",
            "axis_confidence",
            "axis_confidence_reason",
            "ability_band",
            "ability_gap_level",
            "race_difficulty",
            "race_difficulty_reason",
            "display_mark",
            "running_style_display",
        ]:
            self.assertIn(column, audit.columns)
        self.assertIn("表示印", audit.columns)
        self.assertIn("脚質表示", audit.columns)
        self.assertEqual(audit.loc[0, "脚質表示"], "先行")

    def test_normal_card_and_png_sources_show_form_rank_labels(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ["app.py", "render/mobile_png.py"]:
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("AI点", source)
            self.assertIn("能力評価値：", source)
            self.assertIn("能力帯：", source)
            self.assertIn("能力ランク", source)
            self.assertIn("勢いランク", source)
            self.assertIn("脚質：", source)
            self.assertIn("穴候補：該当", source)
            self.assertIn("注意馬：該当", source)


if __name__ == "__main__":
    unittest.main()
