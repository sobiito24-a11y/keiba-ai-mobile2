from __future__ import annotations

import unittest

import pandas as pd

from core.horse_trust import build_horse_trust_for_numbers, build_horse_trust_summary


class HorseTrustTest(unittest.TestCase):
    def test_jra_trust_uses_existing_materials_and_training(self) -> None:
        row = {
            "馬番": 7,
            "馬名": "テストホース",
            "馬年齢": "牡3",
            "騎手詳細": "武豊【継続】",
            "距離指数": 63,
            "コース指数": 58,
            "近3走最高": 66,
            "調教評価": "B",
            "斤量詳細": "57.0kg（前走比+1.0kg）",
            "状態": "上昇",
            "補足": "初ブリンカー",
        }

        summary = build_horse_trust_summary(row, "jra", max_items=10)

        self.assertIn("指数◎", summary)
        self.assertIn("騎手○", summary)
        self.assertIn("3歳+", summary)
        self.assertIn("調教○", summary)
        self.assertIn("初B", summary)

    def test_nar_trust_does_not_mix_jra_training(self) -> None:
        row = {
            "馬番": 4,
            "馬名": "地方ホース",
            "馬年齢": "牝6",
            "騎手詳細": "山本聡【乗替】",
            "距離指数": 48,
            "コース指数": 44,
            "近3走最高": 52,
            "調教評価": "A",
        }

        summary = build_horse_trust_summary(row, "nar", max_items=10)

        self.assertIn("指数○", summary)
        self.assertIn("騎手△", summary)
        self.assertNotIn("調教", summary)

    def test_trust_rows_are_limited_to_ticket_horses(self) -> None:
        table = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "A", "近3走最高": 70},
                {"馬番": 2, "馬名": "B", "近3走最高": 60},
                {"馬番": 3, "馬名": "C", "近3走最高": 50},
            ]
        )

        rows = build_horse_trust_for_numbers(table, "jra", ["2", "3"])

        self.assertEqual([item["horse_no"] for item in rows], ["2", "3"])
        self.assertEqual([item["horse_name"] for item in rows], ["B", "C"])


if __name__ == "__main__":
    unittest.main()
