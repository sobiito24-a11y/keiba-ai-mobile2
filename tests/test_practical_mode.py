from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import pandas as pd

from core.investment_decision import build_investment_decision
from core.models import PredictionResult
from core.practical_mode import (
    apply_practical_to_result,
    build_practical_decision,
    evaluate_practical_table,
    practical_decision_snapshot,
)
from core.practical_validation import (
    PREDICTIONS_CSV_NAME,
    RESULTS_CSV_NAME,
    freeze_practical_prediction,
    practical_validation_summary,
    settle_practical_result,
)
from core.ver4_engine import apply_prediction_logic, prediction_logic_version


RACE_INFO = {
    "race_id": "202630081201",
    "date": "2026-08-12",
    "venue": "門別",
    "race_number": "1R",
    "race_name": "実戦テスト",
    "distance": 1200,
    "turn": "右",
}


def horse_row(
    number: int,
    mark: str,
    *,
    gap: str = "中",
    axis: str = "A",
    trend: str = "上昇傾向",
    training: str = "B 状態良好",
) -> dict:
    return {
        "馬番": number,
        "馬名": f"Horse{number}",
        "表示印": mark,
        "最終印": mark,
        "display_mark": mark,
        "AI点": 88 - number,
        "AI順位": number,
        "raw_score": 82 - number,
        "ability_display_score": 82 - number,
        "軸信頼度": axis,
        "axis_confidence": axis,
        "能力差": gap,
        "ability_gap_level": gap,
        "近3走傾向": trend,
        "3走前": 68,
        "2走前": 71,
        "前走": 75,
        "平均指数": 71.3,
        "距離指数": 72,
        "コース指数": 70,
        "オッズ": 4.2 + number,
        "人気": number,
        "調教評価": training,
        "補足": "なし",
    }


def past_run(distance: int = 1200) -> dict:
    return {
        "label": "前走",
        "racecourse": "門別",
        "distance": distance,
        "direction": "右",
        "surface": "ダ",
        "race_date": "2026-08-01",
        "position": 2,
        "value": 75,
    }


def sample_result(mode: str = "nar", *, race_id: str | None = None) -> PredictionResult:
    rows = [horse_row(1, "◎"), horse_row(2, "○", axis="B"), horse_row(3, "▲", axis="B")]
    table = pd.DataFrame(rows)
    sources = {
        "1": {"_past_runs": [past_run()]},
        "2": {"_past_runs": [past_run(1000)]},
        "3": {"_past_runs": [past_run()]},
    }
    info = dict(RACE_INFO)
    if race_id:
        info["race_id"] = race_id
    return PredictionResult(
        race_mode=mode,  # type: ignore[arg-type]
        race_name="門別1R 実戦テスト",
        race_info=info,
        overall_table=table.copy(deep=True),
        horse_evaluation=table.copy(deep=True),
        debug_info={"condition_fit_sources": sources},
        status="ok",
    )


class PracticalModeTest(unittest.TestCase):
    def test_practical_uses_ver3_marks_and_keeps_condition_plumbing(self) -> None:
        result = sample_result()
        before = result.overall_table.copy(deep=True)

        apply_prediction_logic(result, "practical")

        self.assertEqual(result.logic_version, "practical")
        self.assertEqual(result.overall_table["表示印"].tolist(), before["表示印"].tolist())
        self.assertEqual(result.overall_table["AI点"].tolist(), before["AI点"].tolist())
        self.assertEqual(result.overall_table["raw_score"].tolist(), before["raw_score"].tolist())
        self.assertEqual(result.overall_table.loc[0, "condition_fit_mark"], "★")
        self.assertEqual(result.overall_table.loc[0, "condition_fit_data_status"], "ok")
        self.assertTrue(result.overall_table.loc[0, "matched_past_runs"])
        self.assertNotIn("horse_score_v4", result.overall_table.columns)
        self.assertNotIn("mark_v4", result.overall_table.columns)

    def test_buy_is_one_fixed_win_ticket_and_star_is_not_required(self) -> None:
        row = horse_row(1, "◎")
        row["_past_runs"] = [past_run(1000)]
        row["3走前"] = "68/東京ダ1600m左"
        row["2走前"] = "71/中山ダ1800m右"
        row["前走"] = "75/東京ダ1600m左★"
        table = evaluate_practical_table(pd.DataFrame([row]), "nar", RACE_INFO)

        decision = build_practical_decision(table, "nar", race_info=RACE_INFO)

        self.assertEqual(decision.practical_decision, "BUY")
        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.ticket_type, "単勝")
        self.assertEqual(decision.selected.tickets, ("1",))
        self.assertEqual(decision.total_stake, 100)
        self.assertEqual(table.iloc[0]["condition_fit_data_status"], "no_match")
        self.assertIsNone(table.iloc[0]["condition_fit_mark"])

    def test_watch_reasons_cover_close_gap_decline_and_missing_data(self) -> None:
        cases = [
            ({"能力差": "小", "ability_gap_level": "小"}, "評価差が小さい"),
            ({"近3走傾向": "連続下降"}, "連続下降"),
            ({"オッズ": None}, "オッズが未取得"),
        ]
        for changes, expected in cases:
            with self.subTest(expected=expected):
                row = horse_row(1, "◎")
                row.update(changes)
                row["_past_runs"] = [past_run()]
                table = evaluate_practical_table(pd.DataFrame([row]), "nar", RACE_INFO)
                decision = build_practical_decision(table, "nar", race_info=RACE_INFO)
                self.assertEqual(decision.practical_decision, "WATCH")
                self.assertIn(expected, " / ".join(decision.practical_reason_lines))
                self.assertEqual(decision.total_stake, 0)

    def test_result_fields_cannot_change_pre_race_decision(self) -> None:
        row = horse_row(1, "◎")
        row["_past_runs"] = [past_run()]
        clean = evaluate_practical_table(pd.DataFrame([row]), "nar", RACE_INFO)
        leaked = clean.copy(deep=True)
        leaked["着順"] = 1
        leaked["単勝払戻"] = 9990

        clean_decision = practical_decision_snapshot(build_practical_decision(clean, "nar", race_info=RACE_INFO))
        leaked_decision = practical_decision_snapshot(build_practical_decision(leaked, "nar", race_info=RACE_INFO))

        self.assertEqual(clean_decision, leaked_decision)

    def test_v3_and_v41_modes_remain_available(self) -> None:
        original = sample_result()
        before = original.overall_table.copy(deep=True)
        apply_prediction_logic(original, "v3")
        pd.testing.assert_frame_equal(original.overall_table, before)
        self.assertEqual(prediction_logic_version("v3"), "v3")
        self.assertEqual(prediction_logic_version("v4.1"), "v4.1")
        self.assertEqual(prediction_logic_version("実戦モード"), "practical")

        research = sample_result()
        apply_prediction_logic(research, "v4.1")
        self.assertEqual(research.logic_version, "v4.1")
        self.assertEqual(research.overall_table.loc[0, "condition_fit_mark"], "★")
        self.assertIn("horse_score_v4", research.overall_table.columns)

    def test_build_investment_decision_routes_practical_without_strategy_json(self) -> None:
        result = sample_result()
        apply_practical_to_result(result)
        decision = build_investment_decision(
            result.overall_table,
            "nar",
            race_info=result.race_info,
            prediction_logic_version="practical",
        )
        self.assertEqual(decision.practical_decision, "BUY")
        self.assertEqual(decision.practical_config_version, "practical-1.0")


class PracticalValidationTest(unittest.TestCase):
    def test_prediction_is_frozen_before_result_and_roi_is_calculated(self) -> None:
        result = sample_result()
        apply_practical_to_result(result)
        decision = build_practical_decision(result.overall_table, "nar", race_info=result.race_info)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "practical"
            prediction_path = freeze_practical_prediction(result, decision, root=root)
            before = prediction_path.read_bytes()
            before_hash = hashlib.sha256(before).hexdigest()

            settlement_path = settle_practical_result(
                RACE_INFO["race_id"],
                {
                    "race_id": RACE_INFO["race_id"],
                    "results": [
                        {"horse_no": 1, "finish": 1},
                        {"horse_no": 2, "finish": 2},
                        {"horse_no": 3, "finish": 3},
                    ],
                    "payoffs": {"win": [{"horse_no": 1, "payout": 350}]},
                },
                root=root,
            )
            after = prediction_path.read_bytes()
            summary = practical_validation_summary(root=root)

            self.assertTrue(settlement_path.exists())
            self.assertEqual(before, after)
            self.assertEqual(before_hash, hashlib.sha256(after).hexdigest())
            self.assertTrue((root / PREDICTIONS_CSV_NAME).exists())
            self.assertTrue((root / RESULTS_CSV_NAME).exists())
            overall = summary["scopes"]["ALL"]
            self.assertEqual(overall["buy_count"], 1)
            self.assertEqual(overall["investment_yen"], 100)
            self.assertEqual(overall["payout_yen"], 350)
            self.assertEqual(overall["profit_yen"], 250)
            self.assertEqual(overall["return_rate"], 350.0)
            self.assertEqual(overall["honmei_win_rate"], 100.0)
            self.assertEqual(overall["top3_winner_capture_rate"], 100.0)

            changed = deepcopy(result)
            changed.overall_table.loc[0, "表示印"] = "○"
            same_path = freeze_practical_prediction(changed, decision, root=root)
            self.assertEqual(same_path.read_bytes(), before)

    def test_result_without_frozen_prediction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                settle_practical_result(
                    "missing",
                    {"race_id": "missing", "results": [{"horse_no": 1, "finish": 1}]},
                    root=Path(tmp),
                )

    def test_return_rate_excludes_highest_one_and_two_payout_races(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "practical"
            for suffix, payout in (("01", 500), ("02", 200), ("03", 100)):
                race_id = f"2026300813{suffix}"
                result = sample_result(race_id=race_id)
                apply_practical_to_result(result)
                freeze_practical_prediction(result, root=root)
                settle_practical_result(
                    race_id,
                    {
                        "race_id": race_id,
                        "results": [
                            {"horse_no": 1, "finish": 1},
                            {"horse_no": 2, "finish": 2},
                            {"horse_no": 3, "finish": 3},
                        ],
                        "payoffs": {"win": [{"horse_no": 1, "payout": payout}]},
                    },
                    root=root,
                )

            overall = practical_validation_summary(root=root)["scopes"]["ALL"]
            self.assertEqual(overall["return_rate"], 266.7)
            self.assertEqual(overall["return_rate_without_top1_payout"], 150.0)
            self.assertEqual(overall["return_rate_without_top2_payouts"], 100.0)

    def test_manifest_rejects_rule_change_during_100_races(self) -> None:
        result = sample_result()
        apply_practical_to_result(result)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "practical"
            freeze_practical_prediction(result, root=root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["config_signature"] = "changed"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            other = sample_result(race_id="202630081202")
            apply_practical_to_result(other)
            with self.assertRaises(RuntimeError):
                freeze_practical_prediction(other, root=root)


if __name__ == "__main__":
    unittest.main()
