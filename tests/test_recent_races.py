from __future__ import annotations

import unittest

from core.recent_races import (
    build_recent_races,
    recent_race_preview_text,
    recent_races_detail_text,
    recent_races_summary_text,
)


class RecentRacesTest(unittest.TestCase):
    def test_nested_past_runs_are_sorted_latest_first(self) -> None:
        row = {
            "_past_runs": [
                {
                    "label": "3走前",
                    "race_date": "2026-07-01",
                    "racecourse": "中山",
                    "surface": "芝",
                    "distance": 1800,
                    "position": 6,
                    "popularity": 3,
                    "value": 76,
                    "passing_order": "8-8",
                },
                {
                    "label": "2走前",
                    "race_date": "2026-07-15",
                    "racecourse": "東京",
                    "surface": "芝",
                    "distance": 1600,
                    "position": 1,
                    "popularity": 2,
                    "value": 88,
                    "passing_order": "4-3",
                },
                {
                    "label": "前走",
                    "race_date": "2026-08-01",
                    "racecourse": "新潟",
                    "surface": "芝",
                    "distance": 1600,
                    "position": 3,
                    "popularity": 4,
                    "value": 82,
                    "passing_order": "6-6",
                    "running_style": "差し",
                },
            ]
        }

        runs = build_recent_races(row)

        self.assertEqual([run["label"] for run in runs], ["前走", "2走前", "3走前"])
        self.assertEqual(runs[0]["venue"], "新潟")
        self.assertEqual(runs[0]["time_index"], "82")
        self.assertIn("前走 新潟 芝 1600m 3着", recent_race_preview_text(row))
        summary = recent_races_summary_text(row)
        self.assertIn("前走：新潟 芝 1600m 3着 指数82", summary)
        self.assertIn("2走前：東京 芝 1600m 1着 指数88", summary)
        self.assertIn("3走前：中山 芝 1800m 6着 指数76", summary)
        detail = recent_races_detail_text(row)
        self.assertIn("2026-08-01 / 新潟 / 芝 / 1600m", detail)
        self.assertIn("通過6-6", detail)
        self.assertIn("脚質差し", detail)

    def test_flattened_race_keys_are_used_without_new_parser_fields(self) -> None:
        row = {
            "race1_venue": "船橋",
            "race1_surface": "ダ",
            "race1_distance": 1500,
            "race1_finish": "2",
            "race1_popularity": "4",
            "race1": 53,
            "race2_venue": "大井",
            "race2_surface": "ダ",
            "race2_distance": 1400,
            "race2": 49,
            "race3_venue": "川崎",
            "race3_surface": "ダ",
            "race3_distance": 1600,
            "race3": 45,
        }

        runs = build_recent_races(row)

        self.assertEqual(len(runs), 3)
        self.assertEqual(runs[0]["venue"], "船橋")
        self.assertEqual(runs[0]["finish"], "2着")
        self.assertEqual(runs[0]["popularity"], "4人気")
        self.assertEqual(runs[1]["time_index"], "49")

    def test_nested_runs_are_backfilled_from_flattened_existing_fields(self) -> None:
        row = {
            "_past_runs": [
                {"label": "前走", "value": 24},
                {"label": "2走前", "value": 14},
                {"label": "3走前", "value": 17},
            ],
            "race1_venue": "門別",
            "race1_distance": 1200,
            "race1_finish": "2",
            "race2_venue": "門別",
            "race2_distance": 1200,
            "race2_finish": "4",
            "race3_venue": "大井",
            "race3_distance": 1200,
            "race3_finish": "3",
        }

        summary = recent_races_summary_text(row)

        self.assertIn("前走：門別 1200m 2着 指数24", summary)
        self.assertIn("2走前：門別 1200m 4着 指数14", summary)
        self.assertIn("3走前：大井 1200m 3着 指数17", summary)

    def test_missing_recent_races_are_safe(self) -> None:
        self.assertEqual(build_recent_races({}), [])
        self.assertEqual(recent_race_preview_text({}), "")
        self.assertEqual(recent_races_summary_text({}), "")
        self.assertIn("データなし", recent_races_detail_text({}))


if __name__ == "__main__":
    unittest.main()
