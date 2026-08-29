from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from core.audit_features import add_audit_evaluation_columns, build_audit_export_table
from render.mobile_png import _display_group


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
        self.assertIn("元印", audit.columns)
        self.assertIn("グループ", audit.columns)
        self.assertIn("脚質表示", audit.columns)
        self.assertEqual(audit.loc[0, "脚質表示"], "先行")
        self.assertEqual(audit.loc[0, "元印"], "◎")
        self.assertEqual(audit.loc[0, "グループ"], "SS")

    def test_display_group_is_derived_from_top_ability_gap_without_changing_original_mark(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": 1, "AI点": 100.0, "_raw_score": 90.0, "最終印": "◎"},
                {"馬番": 2, "AI点": 95.0, "_raw_score": 88.0, "最終印": "○"},
                {"馬番": 3, "AI点": 90.0, "_raw_score": 86.0, "最終印": "▲"},
                {"馬番": 4, "AI点": 85.0, "_raw_score": 80.0, "最終印": "△"},
                {"馬番": 5, "AI点": 80.0, "_raw_score": 76.0, "最終印": "✓"},
                {"馬番": 6, "AI点": 75.0, "_raw_score": 70.0, "最終印": ""},
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(list(result["original_mark"]), ["◎", "○", "▲", "△", "✓", ""])
        self.assertEqual(list(result["display_group"]), ["SS", "A", "B", "Z", "Z", "Z"])
        self.assertEqual(list(result["グループ"]), ["SS", "A", "B", "Z", "Z", "Z"])
        self.assertEqual(list(result["勢力図グループ"]), ["SS", "A", "B", "Z", "Z", "Z"])
        self.assertNotIn("D", set(result["display_group"]))
        audit = build_audit_export_table(result)
        self.assertEqual(list(audit["display_group"]), ["SS", "A", "B", "Z", "Z", "Z"])
        self.assertEqual(list(audit["original_mark"]), ["◎", "○", "▲", "△", "✓", ""])

    def test_power_groups_follow_top_ability_gap_in_close_race(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": number, "AI点": score, "_raw_score": score, "最終印": mark}
                for number, score, mark in [
                    (10, 97, "◎"),
                    (14, 95, ""),
                    (5, 94, ""),
                    (12, 93, ""),
                    (1, 92, ""),
                    (2, 92, ""),
                    (9, 91, ""),
                    (8, 91, ""),
                    (13, 90, ""),
                ]
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(list(result["display_group"]), ["SS", "A", "A", "B", "B", "B", "C", "C", "C"])
        self.assertNotIn("Z", set(result["display_group"]))

    def test_power_groups_follow_top_ability_gap_when_gaps_are_clear(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": idx + 1, "AI点": score, "_raw_score": score, "最終印": ""}
                for idx, score in enumerate([100, 99, 96, 94, 91, 88, 80])
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="jra")

        self.assertEqual(list(result["display_group"]), ["SS", "SS", "B", "C", "Z", "Z", "Z"])

    def test_power_groups_do_not_use_fixed_counts_or_split_ties(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": idx + 1, "AI点": score, "_raw_score": score, "最終印": ""}
                for idx, score in enumerate([95, 95, 94, 94, 93, 93])
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(list(result["display_group"]), ["SS", "SS", "SS", "SS", "A", "A"])
        self.assertEqual(result.loc[0, "display_group"], result.loc[1, "display_group"])
        self.assertEqual(result.loc[2, "display_group"], result.loc[3, "display_group"])
        self.assertEqual(result.loc[4, "display_group"], result.loc[5, "display_group"])

    def test_missing_ability_value_is_not_forced_to_z(self) -> None:
        frame = pd.DataFrame(
            [
                {"馬番": 1, "AI点": 100.0, "_raw_score": 97.0, "最終印": "◎"},
                {"馬番": 2, "AI点": 90.0, "_raw_score": None, "最終印": "○"},
            ]
        )

        result = add_audit_evaluation_columns(frame, race_type="nar")

        self.assertEqual(result.loc[0, "display_group"], "SS")
        self.assertEqual(result.loc[1, "display_group"], "未評価")

    def test_png_group_display_matches_audit_groups_and_converts_legacy_d(self) -> None:
        rows = [
            ({"表示印": "◎", "グループ": "SS"}, "SS"),
            ({"表示印": "○", "グループ": "A"}, "A"),
            ({"表示印": "▲", "グループ": "A"}, "A"),
            ({"表示印": "△", "グループ": "B"}, "B"),
            ({"表示印": "✓", "グループ": "D"}, "C"),
            ({"表示印": "", "グループ": "D"}, "Z"),
        ]
        self.assertEqual([_display_group(row) for row, _expected in rows], [expected for _row, expected in rows])

    def test_normal_card_sources_show_group_and_hide_rank_first_labels(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        card_source = app_source[app_source.index("def horse_summary_card_html") : app_source.index("def result_rows")]
        self.assertNotIn("AI点", card_source)
        self.assertNotIn("能力ランク", card_source)
        self.assertNotIn("勢いランク", card_source)
        self.assertIn("【{group}】", card_source)
        self.assertIn("脚質：", card_source)
        self.assertIn("状態：", card_source)
        self.assertIn("★最高指数：", card_source)

        png_source = (root / "render" / "mobile_png.py").read_text(encoding="utf-8")
        png_card_source = png_source[png_source.index("    def draw_horse_evaluation") : png_source.index("    def draw_attention_horses")]
        self.assertNotIn("能力ランク", png_card_source)
        self.assertNotIn("勢いランク", png_card_source)
        self.assertIn("状態：", png_card_source)
        self.assertIn("★該当なし", png_card_source)


if __name__ == "__main__":
    unittest.main()
