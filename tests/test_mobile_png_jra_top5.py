from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace

import pandas as pd

bs4_stub = types.ModuleType("bs4")
bs4_stub.BeautifulSoup = lambda *_args, **_kwargs: SimpleNamespace(
    select=lambda *_args, **_kwargs: [],
    select_one=lambda *_args, **_kwargs: None,
    find=lambda *_args, **_kwargs: None,
    find_all=lambda *_args, **_kwargs: [],
    get_text=lambda *_args, **_kwargs: "",
)
sys.modules.setdefault("bs4", bs4_stub)

from core.models import PredictionResult
from render import mobile_png


class MobilePngJraTop5Test(unittest.TestCase):
    def test_jra_png_top5_rows_use_same_source_as_web_and_ignore_raw_score(self) -> None:
        result = PredictionResult(
            race_mode="jra",
            race_info={"venue": "中京", "surface": "芝", "distance": 1600, "turn": "左"},
            overall_table=pd.DataFrame(
                [
                    {
                        "馬番": 1,
                        "馬名": "RawOnly",
                        "mark_v4": "◎",
                        "raw_score": 999.0,
                        "market_ability_score": 50.0,
                        "market_ability_rank": 2,
                        "training": "C/平凡",
                    },
                    {
                        "馬番": 2,
                        "馬名": "PureAbility",
                        "mark_v4": "",
                        "raw_score": 1.0,
                        "market_ability_score": 80.0,
                        "market_ability_rank": 1,
                        "training": "B/キビキビ",
                        "_estimated_position_corner4_label": "先団",
                        "recent_runs": [
                            {
                                "racecourse": "中京",
                                "surface": "芝",
                                "distance": 1600,
                                "direction": "左",
                                "finish": 2,
                            }
                        ],
                    },
                ]
            ),
        )

        rows = mobile_png._jra_comparison_rows(result)

        self.assertEqual([str(row["number"]) for row in rows[:2]], ["2", "1"])
        self.assertEqual(rows[0]["jra_pure_ability_score"], 80.0)
        self.assertEqual(rows[0]["v1_final_mark"], "◎")
        self.assertEqual(mobile_png._display_mark({"v1_final_mark": "◎", "mark_v4": "△"}, "jra"), "◎")


if __name__ == "__main__":
    unittest.main()
