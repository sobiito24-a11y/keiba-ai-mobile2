from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from core.investment_decision import build_investment_decision
from core.models import PredictionResult
from core.prediction_history import (
    build_prediction_snapshot,
    prediction_csv_rows,
    prediction_zip_bytes,
    save_prediction_history,
)


def strategy_payload(path: Path) -> Path:
    payload = {
        "updated_at": "2026-08-10T00:00:00",
        "source": {"race_count": 50, "note": "test source"},
        "strategies": [
            {
                "strategy_id": "win_ai1",
                "ticket_type": "単勝",
                "label": "AI1",
                "risk_label": "正式",
                "strategy_score": 85,
                "return_rate": 155.2,
                "hit_rate": 38.0,
                "target_races": 50,
                "hits": 19,
                "max_losing_streak": 5,
                "max_payout_contribution": 40.0,
                "role_pattern": {"type": "single", "roles": ["AI1"]},
                "conditions": [{"label": "AI1が存在", "role": "AI1", "op": "exists"}],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def sample_result(mode: str = "jra") -> PredictionResult:
    table = pd.DataFrame(
        [
            {
                "馬番": 7,
                "馬名": "アルファ",
                "馬年齢": "牡3",
                "斤量": 57.0,
                "斤量詳細": "57.0kg（前走比+1.0kg）",
                "騎手": "武豊",
                "騎手詳細": "武豊【継続】",
                "人気": 2,
                "オッズ": 4.2,
                "AI点": 96.0,
                "AI順位": 1,
                "raw_score": 84.7,
                "能力評価値": 84.7,
                "表示印": "◎",
                "display_group": "SS",
                "距離指数": 63,
                "コース指数": 58,
                "3走前": 50,
                "2走前": 55,
                "前走": 62,
                "平均指数": 55.7,
                "最高指数": 70,
                "★最高指数": 62,
                "★該当走": "前走",
                "★条件": "今回と同条件",
                "調教評価": "B",
                "状態": "上昇",
                "近3走傾向": "連続上昇",
                "4角予想": "好位",
                "直線評価": "勝ち負け",
                "展開タイプ": "先行有利",
                "補足": "初ブリンカー",
                "_past_runs": [
                    {
                        "label": "前走",
                        "race_date": "2026-08-01",
                        "racecourse": "新潟",
                        "surface": "芝",
                        "distance": 1600,
                        "position": 3,
                        "popularity": 4,
                        "value": 62,
                        "passing_order": "6-6",
                    },
                    {
                        "label": "2走前",
                        "race_date": "2026-07-15",
                        "racecourse": "東京",
                        "surface": "芝",
                        "distance": 1600,
                        "position": 1,
                        "popularity": 2,
                        "value": 55,
                    },
                    {
                        "label": "3走前",
                        "race_date": "2026-07-01",
                        "racecourse": "中山",
                        "surface": "芝",
                        "distance": 1800,
                        "position": 5,
                        "popularity": 6,
                        "value": 50,
                    },
                ],
            },
            {
                "馬番": 3,
                "馬名": "ベータ",
                "AI点": 90.0,
                "AI順位": 2,
                "表示印": "○",
                "display_group": "A",
                "能力評価値": 72.0,
                "近3走傾向": "下降",
                "4角予想": "後方",
                "直線評価": "評価保留",
            },
        ]
    )
    return PredictionResult(
        race_mode=mode,  # type: ignore[arg-type]
        version="test",
        race_name="札幌11R テスト",
        race_info={
            "race_id": "202608150111",
            "date": "2026-08-15",
            "venue": "札幌",
            "race_number": "11R",
            "race_name": "テスト",
            "distance": "芝1600m",
            "surface": "芝",
            "class": "OP",
            "head_count": 2,
            "post_time": "15:45",
        },
        overall_table=table.copy(),
        horse_evaluation=table.copy(),
        status="ok",
    )


class PredictionHistoryTest(unittest.TestCase):
    def test_prediction_snapshot_zip_and_csv_are_generated_without_mutating_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = strategy_payload(Path(tmp) / "strategy.json")
            result = sample_result("jra")
            before_columns = list(result.overall_table.columns)
            decision = build_investment_decision(result.overall_table, "jra", json_paths=[path])

            snapshot = build_prediction_snapshot(result, decision)
            rows = prediction_csv_rows(snapshot)
            zipped = prediction_zip_bytes(result, decision)

        self.assertEqual(snapshot["race_info"]["race_type"], "jra")
        self.assertEqual(snapshot["investment_decision"]["decision"], "BUY")
        horse7 = next(item for item in snapshot["horses"] if str(item["horse_no"]) == "7")
        self.assertIn("指数", horse7["horse_trust_summary"])
        self.assertIn("調教", horse7["horse_trust_summary"])
        self.assertEqual(horse7["gauge"], 85)
        self.assertEqual(horse7["trend"], "連続上昇")
        self.assertEqual(horse7["corner4_evaluation"], "好位")
        self.assertEqual(horse7["straight_evaluation"], "勝ち負け")
        self.assertEqual(horse7["recent_races"][0]["label"], "前走")
        self.assertEqual(horse7["recent_races"][0]["venue"], "新潟")
        self.assertEqual(horse7["recent_races"][0]["time_index"], "62")
        self.assertEqual(len(horse7["recent_races"]), 3)
        self.assertEqual(horse7["recent_races"][2]["label"], "3走前")
        self.assertEqual(horse7["condition_fit_mark"], "※")
        self.assertEqual(horse7["condition_fit_level"], "same_distance")
        self.assertTrue(horse7["matched_past_runs"])
        self.assertEqual(horse7["final_betting_context"]["condition_fit"]["level"], "same_distance")
        self.assertIn("recent_races", rows[0])
        self.assertIn("condition_fit_mark", rows[0])
        self.assertTrue(snapshot["investment_decision"]["ticket_alignment"])
        self.assertTrue(snapshot["investment_decision"]["ticket_alignment_summary"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(list(result.overall_table.columns), before_columns)
        with zipfile.ZipFile(BytesIO(zipped)) as archive:
            self.assertEqual(set(archive.namelist()), {"prediction.json", "prediction.csv", "summary.txt"})
            loaded = json.loads(archive.read("prediction.json").decode("utf-8"))
            self.assertEqual(len(loaded["horses"]), 2)

    def test_nar_snapshot_omits_jra_training_material_and_saves_result_stub_separately(self) -> None:
        result = sample_result("nar")
        with tempfile.TemporaryDirectory() as tmp:
            path = strategy_payload(Path(tmp) / "strategy.json")
            decision = build_investment_decision(result.overall_table, "nar", json_paths=[path])
            saved = save_prediction_history(result, decision, root=Path(tmp) / "history")

            prediction = json.loads(saved.read_text(encoding="utf-8"))
            result_stub = saved.with_name("result.json")
            self.assertTrue(result_stub.exists())
            result_payload = json.loads(result_stub.read_text(encoding="utf-8"))

        self.assertEqual(prediction["race_info"]["race_type"], "nar")
        horse7 = next(item for item in prediction["horses"] if str(item["horse_no"]) == "7")
        self.assertEqual(horse7["support"]["training_evaluation"], "")
        self.assertEqual(result_payload["results"], [])


if __name__ == "__main__":
    unittest.main()
