from __future__ import annotations

import unittest

import pandas as pd

from core.jra_notebook_logic import parse_speed_table as parse_jra_speed_table
from core.star_index import build_star_max_result, star_match_level


class StarIndexTest(unittest.TestCase):
    def test_single_same_venue_distance_run_is_used(self) -> None:
        current = {"racecourse": "名古屋", "surface": "ダ", "distance": 1500, "direction": "右"}
        result = build_star_max_result(
            current,
            [
                {"label": "3走前", "racecourse": "笠松", "surface": "ダ", "distance": 1400, "direction": "右", "value": 31},
                {"label": "2走前", "racecourse": "名古屋", "surface": "ダ", "distance": 1500, "direction": "右", "value": 42},
                {"label": "前走", "racecourse": "名古屋", "surface": "ダ", "distance": 1400, "direction": "右", "value": 13},
            ],
        )

        self.assertEqual(result.value, 42)
        self.assertEqual(result.race, "2走前")
        self.assertEqual(result.match_level, "venue_distance_surface_turn")

    def test_multiple_same_condition_runs_use_highest_index(self) -> None:
        current = {"racecourse": "名古屋", "surface": "ダ", "distance": 1500}
        result = build_star_max_result(
            current,
            [
                {"label": "3走前", "racecourse": "名古屋", "surface": "ダ", "distance": 1500, "value": 31},
                {"label": "2走前", "racecourse": "名古屋", "surface": "ダ", "distance": 1500, "value": 42},
                {"label": "前走", "racecourse": "笠松", "surface": "ダ", "distance": 1400, "value": 13},
            ],
        )

        self.assertEqual(result.value, 42)
        self.assertEqual(result.race, "2走前")

    def test_distance_or_venue_mismatch_is_not_used(self) -> None:
        current = {"racecourse": "名古屋", "surface": "ダ", "distance": 1500}
        result = build_star_max_result(
            current,
            [
                {"label": "3走前", "racecourse": "名古屋", "surface": "ダ", "distance": 1400, "value": 90},
                {"label": "2走前", "racecourse": "笠松", "surface": "ダ", "distance": 1500, "value": 88},
            ],
        )

        self.assertIsNone(result.value)
        self.assertEqual(result.source, "missing")

    def test_surface_mismatch_is_rejected_when_both_are_known(self) -> None:
        current = {"racecourse": "東京", "surface": "芝", "distance": 1600}

        self.assertEqual(
            star_match_level(current, {"racecourse": "東京", "surface": "ダ", "distance": 1600, "value": 90}),
            "none",
        )

    def test_year_max_only_does_not_create_star_max(self) -> None:
        current = {"racecourse": "大井", "surface": "ダ", "distance": 1600}
        result = build_star_max_result(
            current,
            [
                {"label": "3走前", "racecourse": "船橋", "surface": "ダ", "distance": 1600, "value": 72},
                {"label": "2走前", "racecourse": "大井", "surface": "ダ", "distance": 1200, "value": 71},
            ],
        )

        self.assertIsNone(result.value)
        self.assertEqual(result.match_level, "none")


class JraStarIndexParseTest(unittest.TestCase):
    def test_jra_speed_table_separates_year_max_from_same_condition_star_max(self) -> None:
        html = """
        <html>
          <head>
            <link rel="canonical" href="https://race.netkeiba.com/race/speed.html?race_id=202605030101">
          </head>
          <body>
            <h1 class="RaceName">テスト戦</h1>
            <div class="RaceData01">10:00発走 / 芝1600m (左)</div>
            <div class="RaceData02">3回東京1日目</div>
            <div id="Speed_List">
              <table class="SpeedIndex_Table">
                <tbody>
                  <tr class="List">
                    <td class="Waku">1</td>
                    <td class="sk__umaban">1</td>
                    <td class="sk__horse_name"><a>中央テスト</a></td>
                    <td class="Txt_C">牡3</td>
                    <td class="sk__load_weight">56.0</td>
                    <td class="Jockey">テスト騎手</td>
                    <td class="sk__odds">3.4</td>
                    <td class="sk__ninki">1</td>
                    <td class="sk__max_index">99</td>
                    <td class="sk__max_distance_index">80</td>
                    <td class="sk__max_course_index">81</td>
                    <td class="sk__index3" data-star-venue="東京" data-star-surface="芝" data-star-distance="1600" data-star-turn="左">70</td>
                    <td class="sk__index2" data-star-venue="東京" data-star-surface="芝" data-star-distance="1800" data-star-turn="左">95</td>
                    <td class="sk__index1" data-star-venue="東京" data-star-surface="ダ" data-star-distance="1600" data-star-turn="左">90</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </body>
        </html>
        """

        parsed, _ = parse_jra_speed_table(
            html,
            "https://race.netkeiba.com/race/speed.html?race_id=202605030101",
            session=None,
            fetch_past_detail=False,
        )
        row = parsed.set_index("馬番").loc[1]

        self.assertEqual(float(row["year_max_index"]), 99.0)
        self.assertEqual(float(row["★最高"]), 70.0)
        self.assertEqual(row["star_max_race"], "3走前")
        self.assertEqual(row["star_match_level"], "venue_distance_surface_turn")
        self.assertEqual(row["star_max_source"], "recent3_same_condition")
        self.assertFalse(pd.isna(row["AI点"]))


if __name__ == "__main__":
    unittest.main()
