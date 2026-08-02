# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.purchase_conditions import (
    ConditionSpec,
    build_condition_catalog,
    build_purchase_condition_recommendations,
    condition_score,
    enrich_analysis_records,
    has_conflict,
    horse_stats,
    search_purchase_conditions,
)


class PurchaseConditionTest(unittest.TestCase):
    def test_searches_conditions_and_excludes_missing_star(self) -> None:
        records = enrich_analysis_records(make_records(40))

        specs, excluded = build_condition_catalog(records)
        all_frame, official, reference, avoid, meta = search_purchase_conditions(records, beam_size=80)

        self.assertGreater(len(specs), 10)
        self.assertGreater(meta["explored_conditions"], 0)
        self.assertFalse(all_frame.empty)
        self.assertFalse(official.empty)
        self.assertTrue((official["該当馬数"] >= 30).all())
        self.assertTrue((official["該当レース数"] >= 20).all())
        self.assertTrue(any("★最高指数" in item for item in excluded))
        self.assertNotIn("★最高指数", {spec.source for spec in specs})
        self.assertIsInstance(reference, pd.DataFrame)
        self.assertIsInstance(avoid, pd.DataFrame)

    def test_under_ten_samples_are_not_ranked(self) -> None:
        records = enrich_analysis_records(make_records(9))

        all_frame, official, reference, _avoid, _meta = search_purchase_conditions(records, beam_size=20)

        self.assertTrue(all_frame.empty)
        self.assertTrue(official.empty)
        self.assertTrue(reference.empty)

    def test_conflicting_conditions_are_detected(self) -> None:
        self.assertTrue(
            has_conflict(
                [
                    ConditionSpec("ai1", "AI順位1位", "ai_rank", "AI順位", "eq", 1),
                    ConditionSpec("ai2", "AI順位2位", "ai_rank", "AI順位", "eq", 2),
                ]
            )
        )
        self.assertFalse(
            has_conflict(
                [
                    ConditionSpec("ai1", "AI順位1位", "ai_rank", "AI順位", "eq", 1),
                    ConditionSpec("odds", "オッズ8～12倍", "odds", "オッズ", "range", low=8, high=12),
                ]
            )
        )

    def test_zero_payoff_is_counted_as_zero_not_missing(self) -> None:
        records = enrich_analysis_records(make_records(12))
        records.loc[:, "単勝払戻"] = 0
        records.loc[:, "複勝払戻"] = 0
        records = enrich_analysis_records(records)

        stats = horse_stats(records)

        self.assertEqual(stats["単勝払戻額"], 0.0)
        self.assertEqual(stats["単勝回収率"], 0.0)
        self.assertEqual(stats["最大単勝払戻寄与率"], 0.0)

    def test_condition_score_penalizes_one_shot_dependency(self) -> None:
        base = {
            "該当馬数": 30,
            "該当レース数": 20,
            "単勝回収率": 180.0,
            "複勝回収率": 110.0,
            "勝率": 20.0,
            "複勝率": 40.0,
            "最大単勝払戻寄与率": 35.0,
            "最大複勝払戻寄与率": 30.0,
            "最大連敗": 5,
            "最大ドローダウン": 800.0,
        }
        stable = condition_score(base, {"該当馬数": 20}, {"該当馬数": 8, "単勝回収率": 100, "複勝回収率": 100, "複勝率": 35}, 2, "正式")
        one_shot = condition_score({**base, "最大単勝払戻寄与率": 85.0}, {"該当馬数": 20}, {"該当馬数": 8, "単勝回収率": 100, "複勝回収率": 100, "複勝率": 35}, 2, "正式")

        self.assertGreater(stable, one_shot)

    def test_json_recommendations_match_only_current_rows(self) -> None:
        payload = {
            "recommendations": [
                {
                    "ticket_type": "単勝候補",
                    "stars": "★★★★☆",
                    "condition_score": 72.0,
                    "ranking_type": "正式",
                    "condition_labels": ["AI順位2位", "オッズ8～12倍"],
                    "conditions": [
                        ConditionSpec("ai2", "AI順位2位", "ai_rank", "AI順位", "eq", 2).to_dict(),
                        ConditionSpec("odds", "オッズ8～12倍", "odds", "オッズ", "range", low=8, high=12).to_dict(),
                    ],
                    "target_horses": 35,
                    "target_races": 25,
                    "win_rate": 18.0,
                    "place_rate": 36.0,
                    "win_roi": 155.0,
                    "place_roi": 112.0,
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "Axis", "AI順位": 1, "オッズ": 3.0},
                {"馬番": 2, "馬名": "Value", "AI順位": 2, "オッズ": 9.5},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "purchase_condition_ranked.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_purchase_condition_recommendations(table, json_path=path)

        self.assertEqual(len(recommendations), 1)
        self.assertIn("2", recommendations[0].matched_horses[0])
        self.assertIn("Value", recommendations[0].matched_horses[0])

    def test_json_recommendations_hide_when_no_current_match(self) -> None:
        payload = {
            "recommendations": [
                {
                    "ticket_type": "単勝候補",
                    "condition_score": 72.0,
                    "conditions": [ConditionSpec("ai2", "AI順位2位", "ai_rank", "AI順位", "eq", 2).to_dict()],
                }
            ]
        }
        table = pd.DataFrame([{"馬番": 1, "馬名": "Axis", "AI順位": 1, "オッズ": 3.0}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "purchase_condition_ranked.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            recommendations = build_purchase_condition_recommendations(table, json_path=path)

        self.assertEqual(recommendations, [])

    def test_purchase_condition_recommendations_are_limited_to_betting_adopted_horses(self) -> None:
        payload = {
            "recommendations": [
                {
                    "ticket_type": "単勝候補",
                    "stars": "★★★★☆",
                    "condition_score": 72.0,
                    "ranking_type": "正式",
                    "condition_labels": ["AI順位2位"],
                    "conditions": [ConditionSpec("ai2", "AI順位2位", "ai_rank", "AI順位", "eq", 2).to_dict()],
                    "target_horses": 35,
                    "target_races": 25,
                    "win_rate": 18.0,
                    "place_rate": 36.0,
                    "win_roi": 155.0,
                    "place_roi": 112.0,
                }
            ]
        }
        table = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "Axis", "AI順位": 1, "オッズ": 3.0},
                {"馬番": 2, "馬名": "Value", "AI順位": 2, "オッズ": 9.5},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "purchase_condition_ranked.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            no_adoption = build_purchase_condition_recommendations(
                table,
                json_path=path,
                adopted_horse_numbers={"1"},
                adoption_map={"1": ["ワイド SS-B"]},
            )
            adopted = build_purchase_condition_recommendations(
                table,
                json_path=path,
                adopted_horse_numbers={"2"},
                adoption_map={"2": ["単勝 AI2", "複勝 AI2"]},
            )

        self.assertEqual(no_adoption, [])
        self.assertEqual(len(adopted), 1)
        self.assertEqual(adopted[0].horse_no, "2")
        self.assertEqual(adopted[0].recommended_ticket_types, ["単勝", "複勝"])
        self.assertEqual(adopted[0].adopted_betting_labels, ["単勝 AI2", "複勝 AI2"])


def make_records(races: int) -> pd.DataFrame:
    rows = []
    for i in range(races):
        race_id = f"202699{i:06d}"
        rows.append(
            {
                "race_id": race_id,
                "馬番": 1,
                "馬名": f"Axis{i}",
                "AI順位": 1,
                "AI点": 94.0,
                "補正AI点": 94.0,
                "総合評価点": 96.0,
                "_raw_score": 64.0,
                "オッズ": 3.0,
                "人気": 1,
                "距離指数": 65,
                "コース指数": 60,
                "近3走最高": 68,
                "平均指数": 63,
                "最高指数": 70,
                "脚質": "先",
                "能力": "能力上位",
                "勢い": "横ばい",
                "馬タイプ": "能力型",
                "クラス根拠": "同級",
                "購入判定": "中心候補",
                "_調教評価記号": "B",
                "_jockey_changed": False,
                "finish": 2,
                "単勝払戻": 0,
                "複勝払戻": 120,
                "★最高指数": None,
            }
        )
        rows.append(
            {
                "race_id": race_id,
                "馬番": 2,
                "馬名": f"Value{i}",
                "AI順位": 2,
                "AI点": 88.0,
                "補正AI点": 88.0,
                "総合評価点": 88.0,
                "_raw_score": 55.0,
                "オッズ": 9.0,
                "人気": 5,
                "距離指数": 55,
                "コース指数": 52,
                "近3走最高": 58,
                "平均指数": 51,
                "最高指数": 60,
                "脚質": "差",
                "能力": "能力上位",
                "勢い": "上昇",
                "馬タイプ": "中穴警戒",
                "クラス根拠": "同級",
                "購入判定": "相手候補",
                "_調教評価記号": "A",
                "_jockey_changed": False,
                "finish": 1 if i % 4 == 0 else 4,
                "単勝払戻": 900 if i % 4 == 0 else 0,
                "複勝払戻": 260 if i % 4 == 0 else 0,
                "★最高指数": None,
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
