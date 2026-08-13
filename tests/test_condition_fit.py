from __future__ import annotations

import unittest

from core.condition_fit import condition_fit_badge_text, evaluate_condition_fit


class ConditionFitTest(unittest.TestCase):
    def test_same_venue_distance_is_star(self) -> None:
        row = {
            "_past_runs": [
                {"label": "前走", "racecourse": "門別", "surface": "ダ", "distance": 1200, "direction": "右", "value": 24}
            ]
        }

        result = evaluate_condition_fit(row, {"venue": "門別", "distance": "ダ1200m", "turn": "右"})

        self.assertEqual(result["condition_fit_mark"], "★")
        self.assertEqual(result["condition_fit_level"], "same_venue_distance")
        self.assertEqual(result["matched_past_runs"][0]["venue"], "門別")
        self.assertEqual(condition_fit_badge_text(row, {"venue": "門別", "distance": 1200}), "★同会場距離")

    def test_same_turn_distance_is_white_star_when_venue_differs(self) -> None:
        row = {
            "_past_runs": [
                {"label": "前走", "racecourse": "大井", "distance": 1200, "direction": "右", "value": 24}
            ]
        }

        result = evaluate_condition_fit(row, {"venue": "門別", "distance": 1200, "turn": "右"})

        self.assertEqual(result["condition_fit_mark"], "☆")
        self.assertEqual(result["condition_fit_level"], "same_turn_distance")

    def test_same_distance_only_is_reference_mark(self) -> None:
        row = {
            "_past_runs": [
                {"label": "前走", "racecourse": "船橋", "distance": 1200, "direction": "左", "value": 24}
            ]
        }

        result = evaluate_condition_fit(row, {"venue": "門別", "distance": 1200, "turn": "右"})

        self.assertEqual(result["condition_fit_mark"], "※")
        self.assertEqual(result["condition_fit_level"], "same_distance")

    def test_no_distance_match_is_none(self) -> None:
        result = evaluate_condition_fit(
            {"_past_runs": [{"label": "前走", "racecourse": "門別", "distance": 1000, "value": 24}]},
            {"venue": "門別", "distance": 1200, "turn": "右"},
        )

        self.assertIsNone(result["condition_fit_mark"])
        self.assertEqual(result["condition_fit_level"], "none")
        self.assertEqual(result["condition_fit_data_status"], "no_match")
        self.assertEqual(result["matched_past_runs"], [])

    def test_priority_prefers_star_over_other_marks(self) -> None:
        row = {
            "_past_runs": [
                {"label": "前走", "racecourse": "大井", "distance": 1200, "direction": "右", "value": 24},
                {"label": "2走前", "racecourse": "門別", "distance": 1200, "direction": "右", "value": 14},
                {"label": "3走前", "racecourse": "船橋", "distance": 1200, "direction": "左", "value": 17},
            ]
        }

        result = evaluate_condition_fit(row, {"venue": "門別", "distance": 1200, "turn": "右"})

        self.assertEqual(result["condition_fit_mark"], "★")
        self.assertEqual(result["condition_fit_level"], "same_venue_distance")
        self.assertEqual(len(result["matched_past_runs"]), 1)
        self.assertEqual(result["matched_past_runs"][0]["label"], "2走前")

    def test_flattened_nar_runs_are_supported(self) -> None:
        row = {
            "race1_venue": "大井",
            "race1_distance": 1200,
            "race1_finish": "2",
            "race1": 24,
            "race2_venue": "門別",
            "race2_distance": 1200,
            "race2": 14,
        }

        result = evaluate_condition_fit(row, {"venue": "門別", "distance": 1200})

        self.assertEqual(result["condition_fit_mark"], "★")
        self.assertEqual(result["matched_past_runs"][0]["label"], "2走前")


if __name__ == "__main__":
    unittest.main()
