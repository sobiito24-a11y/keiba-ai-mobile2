from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from core.jra_notebook_logic import apply_jra_newspaper_html_features, parse_jra_newspaper_html
from core.market_compare import evaluate_market_table


FIXTURE = Path(__file__).parent / "fixtures" / "tanabata_20260712" / "keiba_data-61.html"
RACE_INFO = {
    "race_id": "202603020611",
    "date": "2026-07-12",
    "venue": "福島",
    "race_number": "11R",
    "race_name": "七夕賞(G3)",
    "distance": 2000,
    "surface": "芝",
}


def comparison_row(number: int, name: str, core: float, odds: float, popularity: int, **extra):
    row = {
        "馬番": number,
        "馬名": name,
        "_ver3_ability_core": core,
        # Deliberately incompatible legacy values prove they are not the band input.
        "raw_score": core + 30.0,
        "_market_non_ability_adjustment": -20.0,
        "オッズ": odds,
        "人気": popularity,
        "脚質": "先",
        "斤量": 56.0,
        "騎手": "テスト騎手",
        "レース間隔": "中3週",
    }
    row.update(extra)
    return row


class TanabataOnyankoponRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.newspaper = parse_jra_newspaper_html(FIXTURE.read_text(encoding="utf-8"))
        cls.onyankopon = cls.newspaper.loc[cls.newspaper["馬番"].eq(9)].iloc[0]

    def test_uploaded_pre_race_html_facts_are_fixed(self) -> None:
        self.assertEqual(len(self.newspaper), 16)
        self.assertEqual(self.onyankopon["_新聞馬名"], "オニャンコポン")
        self.assertEqual(self.onyankopon["_新聞単勝オッズ"], 73.5)
        self.assertEqual(self.onyankopon["_新聞人気"], 15)
        self.assertEqual(self.onyankopon["_新聞脚質"], "差")
        self.assertEqual(self.onyankopon["_新聞レース間隔"], "中1週")
        self.assertEqual(self.onyankopon["_新聞斤量"], 54.0)
        self.assertEqual(self.onyankopon["_新聞騎手"], "吉田豊")
        self.assertEqual(self.onyankopon["_新聞馬体重"], "468(-8)")
        self.assertEqual(self.onyankopon["_新聞今回クラス"], "G3")
        self.assertEqual(self.onyankopon["_新聞前走クラス"], "G3")
        self.assertEqual(self.onyankopon["_新聞クラス変動"], "同級")
        self.assertEqual(self.onyankopon["_新聞前走間隔日数"], 14)
        self.assertEqual(self.onyankopon["_新聞過去クラス"], ["G3", "G3", "L"])
        self.assertEqual(self.onyankopon["調教評価"], "B 復調気配")
        self.assertIn("もともとの地力がある馬", self.onyankopon["新聞コメント"])

    def test_newspaper_facts_are_merged_after_scoring_without_touching_core(self) -> None:
        source = pd.DataFrame(
            [{
                "馬番": 9,
                "馬名": "オニャンコポン",
                "_ver3_ability_core": 90.0,
                "_raw_score": 120.0,
                "_market_non_ability_adjustment": 30.0,
            }]
        )
        merged = apply_jra_newspaper_html_features(source, FIXTURE.read_text(encoding="utf-8"))
        row = merged.iloc[0]
        self.assertEqual(row["_ver3_ability_core"], 90.0)
        self.assertEqual(row["オッズ"], 73.5)
        self.assertEqual(row["人気"], 15)
        self.assertEqual(row["斤量"], 54.0)
        self.assertEqual(row["騎手"], "吉田豊")
        self.assertEqual(row["馬体重"], "468(-8)")
        self.assertEqual(row["_body_weight"], 468)
        self.assertEqual(row["_body_weight_change"], -8)
        self.assertEqual(row["_current_class_label"], "G3")
        self.assertEqual(row["_previous_class_label"], "G3")
        self.assertEqual(row["_days_since_last"], 14)
        self.assertEqual(row["調教評価"], "B 復調気配")

    def test_newspaper_zero_match_does_not_assign_empty_strings_to_int_columns(self) -> None:
        source = pd.DataFrame([comparison_row(99, "該当なし", 80.0, 12.3, 4)])
        source["人気"] = source["人気"].astype("int64")
        before = source.copy(deep=True)
        merged = apply_jra_newspaper_html_features(source, FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(merged.loc[0, "人気"], before.loc[0, "人気"])
        self.assertEqual(str(merged["人気"].dtype), str(before["人気"].dtype))
        self.assertEqual(merged.loc[0, "オッズ"], before.loc[0, "オッズ"])
        self.assertEqual(merged.loc[0, "_ver3_ability_core"], before.loc[0, "_ver3_ability_core"])

    def test_73_5_odds_and_15th_popularity_cannot_demote_ability_band(self) -> None:
        onyan = comparison_row(
            9,
            self.onyankopon["_新聞馬名"],
            90.0,
            self.onyankopon["_新聞単勝オッズ"],
            self.onyankopon["_新聞人気"],
            脚質=self.onyankopon["_新聞脚質"],
            斤量=self.onyankopon["_新聞斤量"],
            騎手=self.onyankopon["_新聞騎手"],
            レース間隔=self.onyankopon["_新聞レース間隔"],
            調教評価=self.onyankopon["調教評価"],
            新聞コメント=self.onyankopon["新聞コメント"],
        )
        table = pd.DataFrame(
            [
                comparison_row(1, "比較上位", 92.0, 2.1, 1),
                onyan,
                comparison_row(16, "比較下位", 68.0, 120.0, 16),
            ]
        )
        changed = table.copy(deep=True)
        changed.loc[changed["馬番"].eq(9), ["オッズ", "人気", "斤量", "騎手", "脚質", "レース間隔"]] = [
            1.1, 1, 62.0, "別騎手", "逃", "長期休養"
        ]

        actual = evaluate_market_table(table, "jra", RACE_INFO)
        counterfactual = evaluate_market_table(changed, "jra", RACE_INFO)
        actual_on = actual.loc[actual["馬番"].eq(9)].iloc[0]
        changed_on = counterfactual.loc[counterfactual["馬番"].eq(9)].iloc[0]

        self.assertEqual(actual_on["actual_odds"], 73.5)
        self.assertEqual(actual_on["market_ability_score"], 90.0)
        self.assertEqual(actual_on["ability_band_v2"], "A")
        self.assertEqual(actual_on["ability_core_source"], "explicit_ver3_core")
        self.assertIn("復調", actual_on["positive_materials"])
        for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
            self.assertEqual(actual_on[column], changed_on[column])


if __name__ == "__main__":
    unittest.main()
