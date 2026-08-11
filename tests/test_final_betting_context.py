from __future__ import annotations

import unittest

import pandas as pd

from core.final_betting_context import build_final_betting_context, build_ticket_alignment


class FinalBettingContextTest(unittest.TestCase):
    def test_context_uses_existing_card_values_without_mutating_source(self) -> None:
        table = pd.DataFrame(
            [
                {
                    "馬番": 4,
                    "馬名": "クーリッジ",
                    "表示印": "◎",
                    "display_group": "SS",
                    "AI点": 96.1,
                    "AI順位": 1,
                    "能力評価値": 86.4,
                    "近3走傾向": "上昇",
                    "4角予想": "好位",
                    "直線評価": "勝ち負け",
                    "展開タイプ": "先行有利",
                    "距離指数": 64,
                    "コース指数": 61,
                    "調教評価": "B",
                    "_past_runs": [
                        {"label": "前走", "racecourse": "東京", "distance": 1600, "direction": "左", "value": 80}
                    ],
                },
                {
                    "馬番": 1,
                    "馬名": "相手弱め",
                    "表示印": "",
                    "display_group": "Z",
                    "AI点": 74.0,
                    "AI順位": 7,
                    "能力評価値": 48.2,
                },
            ]
        )
        before = table.copy(deep=True)

        contexts = build_final_betting_context(table, "jra", race_info={"venue": "東京", "distance": 1600, "turn": "左"})
        axis = next(item for item in contexts if item["horse_number"] == "4")

        self.assertEqual(axis["momentum"]["gauge"], 86)
        self.assertEqual(axis["momentum"]["trend"], "上昇")
        self.assertEqual(axis["race_shape"]["corner4_evaluation"], "好位")
        self.assertEqual(axis["race_shape"]["straight_evaluation"], "勝ち負け")
        self.assertIn("training", axis["trust"])
        self.assertEqual(axis["condition_fit"]["mark"], "★")
        self.assertEqual(axis["condition_fit"]["level"], "same_venue_distance")
        pd.testing.assert_frame_equal(table, before)

    def test_ticket_alignment_records_match_and_mismatch_without_changing_ticket(self) -> None:
        table = pd.DataFrame(
            [
                {"馬番": 4, "馬名": "軸", "表示印": "◎", "display_group": "SS", "能力評価値": 86, "直線評価": "勝ち負け"},
                {"馬番": 1, "馬名": "薄い相手", "display_group": "Z", "能力評価値": 50},
                {"馬番": 6, "馬名": "展開相手", "display_group": "B", "能力評価値": 72, "近3走傾向": "上昇", "直線評価": "差し浮上"},
            ]
        )
        contexts = build_final_betting_context(table, "nar", ticket_numbers=["4", "1", "6"])
        rows = build_ticket_alignment(contexts, [("4", "1"), ("4", "6")], strategy_id="wide", strategy_label="SS-B")

        self.assertEqual([row["ticket"] for row in rows], ["4-1", "4-6"])
        self.assertEqual(rows[0]["alignment"], "一部一致")
        self.assertEqual(rows[1]["alignment"], "一致")
        self.assertNotIn("training", contexts[0]["trust"])

    def test_missing_values_are_kept_as_none(self) -> None:
        contexts = build_final_betting_context(pd.DataFrame([{"馬番": 8, "馬名": "欠損"}]), "jra")
        context = contexts[0]

        self.assertIsNone(context["momentum"]["gauge"])
        self.assertIsNone(context["race_shape"]["straight_evaluation"])
        self.assertIsNone(context["race_shape"]["corner4_evaluation"])


if __name__ == "__main__":
    unittest.main()
