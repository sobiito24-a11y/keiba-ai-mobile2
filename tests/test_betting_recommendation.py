from __future__ import annotations

import unittest

import pandas as pd

from core.betting_recommendation import build_betting_recommendations


class BettingRecommendationTest(unittest.TestCase):
    def test_builds_display_only_recommendations_from_existing_columns(self) -> None:
        table = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "Axis", "AI順位": 1, "オッズ": 12.0, "グループ": "SS", "AI点": 100.0, "最終印": "◎"},
                {"馬番": 2, "馬名": "Main", "AI順位": 2, "オッズ": 4.0, "グループ": "A", "AI点": 95.0, "最終印": "○"},
                {"馬番": 3, "馬名": "Value", "AI順位": 3, "オッズ": 14.0, "グループ": "A", "AI点": 92.0, "最終印": "▲"},
                {"馬番": 4, "馬名": "Hole", "AI順位": 5, "オッズ": 18.0, "グループ": "C", "AI点": 86.0, "最終印": "✓"},
            ]
        )
        before = table.copy(deep=True)

        recommendations = build_betting_recommendations(table)

        pd.testing.assert_frame_equal(table, before)
        self.assertGreaterEqual(len(recommendations), 3)
        self.assertEqual(recommendations[0].ticket_type, "単勝")
        self.assertEqual(recommendations[0].label, "AI3位")
        self.assertIn("SS-C", {item.label for item in recommendations})

    def test_returns_empty_when_no_display_condition_matches(self) -> None:
        table = pd.DataFrame(
            [
                {"馬番": 1, "AI順位": 1, "オッズ": 2.0, "グループ": "SS"},
                {"馬番": 2, "AI順位": 2, "オッズ": 3.0, "グループ": "A"},
                {"馬番": 3, "AI順位": 3, "オッズ": 4.0, "グループ": "Z"},
            ]
        )

        recommendations = build_betting_recommendations(table)

        self.assertEqual(recommendations, [])


if __name__ == "__main__":
    unittest.main()
