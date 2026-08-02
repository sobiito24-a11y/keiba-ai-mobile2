from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.betting_recommendation import LAST_MATCH_AUDIT, build_betting_recommendations


class BettingRecommendationTest(unittest.TestCase):
    def test_fixed_recommendations_are_only_fallback_when_json_is_absent(self) -> None:
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "ai_rank": 1, "odds": 12.0, "mark": "◎", "ai_score": 100.0},
                {"horse_no": 2, "horse_name": "Main", "ai_rank": 2, "odds": 4.0, "mark": "○", "ai_score": 95.0},
                {"horse_no": 3, "horse_name": "Value", "ai_rank": 3, "odds": 14.0, "mark": "▲", "ai_score": 92.0},
                {"horse_no": 4, "horse_name": "Hole", "ai_rank": 5, "odds": 18.0, "mark": "✓", "ai_score": 86.0},
            ]
        )
        before = table.copy(deep=True)

        recommendations = build_betting_recommendations(table, json_paths=[])

        pd.testing.assert_frame_equal(table, before)
        self.assertGreaterEqual(len(recommendations), 2)
        self.assertEqual(recommendations[0].source, "fixed")
        self.assertEqual(recommendations[0].ticket_type, "単勝")
        self.assertEqual(recommendations[0].label, "AI3位")

    def test_json_recommendations_have_priority_over_fixed_rules(self) -> None:
        payload = {
            "recommendations": [
                {
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "AI1-AI2",
                    "stars": "★★★★☆",
                    "return_rate": 131.0,
                    "hit_rate": 25.0,
                    "purchase_races": 30,
                    "risk_label": "正式",
                    "role_pattern": {"type": "pair", "left_roles": ["AI1"], "right_roles": ["AI2"]},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "ai_rank": 1, "odds": 12.0, "mark": "◎"},
                {"horse_no": 2, "horse_name": "Main", "ai_rank": 2, "odds": 4.0, "mark": "○"},
                {"horse_no": 3, "horse_name": "Value", "ai_rank": 3, "odds": 14.0, "mark": "▲"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].source, "analysis_json")
        self.assertEqual(recommendations[0].ticket_type, "ワイド")
        self.assertEqual(recommendations[0].expected_roi, 131.0)

    def test_broken_latest_json_uses_fixed_fallback_only_when_json_unusable(self) -> None:
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "ai_rank": 1, "odds": 12.0, "mark": "◎"},
                {"horse_no": 3, "horse_name": "Value", "ai_rank": 3, "odds": 14.0, "mark": "▲"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{broken", encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].source, "fixed")

    def test_json_recommendations_hide_when_no_current_ticket_matches(self) -> None:
        payload = {
            "recommendations": [
                {
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "SS-B",
                    "return_rate": 133.0,
                    "risk_label": "正式",
                    "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "ai_rank": 1, "odds": 3.0, "mark": "◎"},
                {"horse_no": 2, "horse_name": "Main", "ai_rank": 2, "odds": 4.0, "mark": "○"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(recommendations, [])

    def test_json_recommendations_are_limited_and_not_saturated_by_one_ticket_type(self) -> None:
        items = []
        for idx, rank in enumerate([1, 2, 3], start=1):
            items.append(
                {
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "単勝",
                    "label": f"AI{rank}",
                    "return_rate": 150 - idx,
                    "risk_label": "正式",
                    "role_pattern": {"type": "single", "roles": [f"AI{rank}"]},
                }
            )
        items.extend(
            [
                {
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "複勝",
                    "label": "AI1",
                    "return_rate": 120,
                    "risk_label": "正式",
                    "role_pattern": {"type": "single", "roles": ["AI1"]},
                },
                {
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "AI1-AI2",
                    "return_rate": 110,
                    "risk_label": "正式",
                    "role_pattern": {"type": "pair", "left_roles": ["AI1"], "right_roles": ["AI2"]},
                },
            ]
        )
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "ai_rank": 1, "odds": 3.0, "mark": "◎"},
                {"horse_no": 2, "horse_name": "Main", "ai_rank": 2, "odds": 4.0, "mark": "○"},
                {"horse_no": 3, "horse_name": "Third", "ai_rank": 3, "odds": 8.0, "mark": "▲"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps({"recommendations": items}, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path], max_items=4)

        self.assertLessEqual(len(recommendations), 4)
        self.assertGreaterEqual(len({item.ticket_type for item in recommendations}), 3)

    def test_ticket_recommendation_contains_actual_tickets_and_conditions(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "wide_ss_b",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "SS-B",
                    "return_rate": 133.0,
                    "hit_rate": 45.5,
                    "purchase_races": 22,
                    "risk_label": "正式",
                    "reliability_score": 60.0,
                    "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"horse_no": 5, "horse_name": "Axis", "display_group": "SS", "ai_rank": 1},
                {"horse_no": 8, "horse_name": "Blue", "display_group": "B", "ai_rank": 4},
                {"horse_no": 9, "horse_name": "Value", "display_group": "B", "ai_rank": 5},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].tickets, ("5-8", "5-9"))
        self.assertEqual(recommendations[0].ticket_count, 2)
        self.assertIn("SSが1頭", recommendations[0].matched_conditions)
        self.assertIn("Bが2頭", recommendations[0].matched_conditions)

    def test_matching_reference_only_strategy_is_hold_not_forced_display(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "wide_ss_b_reference",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "SS-B",
                    "return_rate": 200.0,
                    "hit_rate": 40.0,
                    "purchase_races": 10,
                    "risk_label": "参考",
                    "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"horse_no": 5, "horse_name": "Axis", "display_group": "SS"},
                {"horse_no": 8, "horse_name": "Blue", "display_group": "B"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(recommendations, [])
        self.assertEqual(LAST_MATCH_AUDIT[0]["non_adoption_reason"], "正式推奨が0件のため見送り")

    def test_ai2_strategy_hides_when_ai2_is_absent(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "place_ai2",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "複勝",
                    "label": "AI2",
                    "return_rate": 120.0,
                    "hit_rate": 40.0,
                    "purchase_races": 30,
                    "risk_label": "正式",
                    "role_pattern": {"type": "single", "roles": ["AI2"]},
                }
            ]
        }
        table = pd.DataFrame([{"horse_no": 1, "horse_name": "Axis", "ai_rank": 1}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(recommendations, [])
        self.assertIn("AI2位が不在", LAST_MATCH_AUDIT[0]["unmatched_conditions"])

    def test_trio_strategy_hides_when_required_horse_count_is_short(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "trio_ss_a_b",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "三連複",
                    "label": "SS-A-B BOX",
                    "return_rate": 180.0,
                    "hit_rate": 25.0,
                    "purchase_races": 20,
                    "risk_label": "正式",
                    "role_pattern": {"type": "box", "roles": ["SS", "A", "B"], "size": 3},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"horse_no": 1, "horse_name": "Axis", "display_group": "SS"},
                {"horse_no": 2, "horse_name": "Main", "display_group": "A"},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(recommendations, [])
        self.assertIn("BOX対象が3頭未満", LAST_MATCH_AUDIT[0]["unmatched_conditions"])

    def test_generated_tickets_change_by_race(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "wide_ss_b",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "SS-B",
                    "return_rate": 133.0,
                    "hit_rate": 45.5,
                    "purchase_races": 22,
                    "risk_label": "正式",
                    "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            first = build_betting_recommendations(
                pd.DataFrame(
                    [
                        {"horse_no": 1, "horse_name": "Axis", "display_group": "SS"},
                        {"horse_no": 2, "horse_name": "Blue", "display_group": "B"},
                    ]
                ),
                json_paths=[path],
            )
            second = build_betting_recommendations(
                pd.DataFrame(
                    [
                        {"horse_no": 7, "horse_name": "Axis2", "display_group": "SS"},
                        {"horse_no": 9, "horse_name": "Blue2", "display_group": "B"},
                    ]
                ),
                json_paths=[path],
            )

        self.assertEqual(first[0].tickets, ("1-2",))
        self.assertEqual(second[0].tickets, ("7-9",))

    def test_japanese_app_columns_generate_current_tickets(self) -> None:
        payload = {
            "recommendations": [
                {
                    "strategy_id": "wide_ss_b",
                    "recommendation_kind": "ticket_strategy",
                    "ticket_type": "ワイド",
                    "label": "SS-B",
                    "return_rate": 133.0,
                    "hit_rate": 45.5,
                    "purchase_races": 22,
                    "risk_label": "正式",
                    "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"馬番": 5, "馬名": "軸馬", "グループ": "SS", "AI順位": 1},
                {"馬番": 9, "馬名": "相手馬", "グループ": "B", "AI順位": 3},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "betting_recommendations.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_betting_recommendations(table, json_paths=[path])

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].tickets, ("5-9",))


if __name__ == "__main__":
    unittest.main()
