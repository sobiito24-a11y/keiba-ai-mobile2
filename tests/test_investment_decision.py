from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.investment_decision import (
    JUDGEMENT_BUY,
    JUDGEMENT_HOLD,
    JUDGEMENT_PASS,
    build_investment_decision,
)


def write_payload(tmp: str, strategies: list[dict]) -> Path:
    path = Path(tmp) / "strategy_selection.json"
    payload = {
        "scope": "test",
        "updated_at": "2026-08-02T00:00:00",
        "source": {"race_count": 34, "note": "test"},
        "strategies": strategies,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def sample_table(*, ai1_odds: float = 3.0, with_b: bool = True) -> pd.DataFrame:
    rows = [
        {"horse_no": 5, "horse_name": "Axis", "display_group": "SS", "ai_rank": 1, "ai_score": 98.0, "能力評価値": 86.0, "odds": ai1_odds, "popularity": 1, "近3走最高": 70, "馬年齢": "牡5", "騎手詳細": "騎手A【継続】", "近3走傾向": "上昇", "4角予想": "好位", "直線評価": "勝ち負け"},
        {"horse_no": 2, "horse_name": "Main", "display_group": "A", "ai_rank": 2, "ai_score": 95.0, "能力評価値": 78.0, "odds": 4.0, "popularity": 2, "近3走最高": 62, "馬年齢": "牝4", "騎手詳細": "騎手B【継続】", "近3走傾向": "横ばい", "4角予想": "中団", "直線評価": "直線勝負"},
        {"horse_no": 7, "horse_name": "Third", "display_group": "B" if with_b else "Z", "ai_rank": 3, "ai_score": 92.0, "能力評価値": 71.0, "odds": 12.0, "popularity": 6, "近3走最高": 58, "馬年齢": "牡3", "騎手詳細": "騎手C【乗り替わり】", "近3走傾向": "下降", "4角予想": "後方", "直線評価": "評価保留"},
        {"horse_no": 9, "horse_name": "Blue", "display_group": "B" if with_b else "Z", "ai_rank": 4, "ai_score": 88.0, "能力評価値": 68.0, "odds": 16.0, "popularity": 7, "近3走最高": 52, "馬年齢": "牡6", "騎手詳細": "騎手D【継続】", "近3走傾向": "上昇", "4角予想": "中団", "直線評価": "差し浮上"},
    ]
    return pd.DataFrame(rows)


def wide_ss_b(score: float = 80.0) -> dict:
    return {
        "strategy_id": "wide_ss_b",
        "ticket_type": "ワイド",
        "label": "SS-B",
        "risk_label": "正式",
        "strategy_score": score,
        "return_rate": 179.3,
        "hit_rate": 50.0,
        "target_races": 14,
        "hits": 7,
        "max_payout_contribution": 38.8,
        "role_pattern": {"type": "pair", "left_roles": ["SS"], "right_roles": ["B"]},
        "conditions": [{"label": "AI1オッズ2～5倍", "role": "AI1", "field": "odds", "op": "range", "low": 2, "high": 5}],
    }


def win_b(score: float = 76.0) -> dict:
    return {
        "strategy_id": "win_b",
        "ticket_type": "単勝",
        "label": "B",
        "risk_label": "正式",
        "strategy_score": score,
        "return_rate": 298.3,
        "hit_rate": 50.0,
        "target_races": 12,
        "hits": 6,
        "max_payout_contribution": 39.9,
        "role_pattern": {"type": "single", "roles": ["B"]},
        "conditions": [{"label": "AI3のAI点90～95", "role": "AI3", "field": "ai_score", "op": "range", "low": 90, "high": 95}],
        "avoid_conditions": [{"label": "AI1オッズ2倍未満", "role": "AI1", "field": "odds", "op": "lt", "high": 2}],
    }


class InvestmentDecisionTest(unittest.TestCase):
    def test_multiple_matches_select_only_one_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_payload(tmp, [wide_ss_b(), win_b()])
            decision = build_investment_decision(sample_table(), "nar", json_paths=[path])

        self.assertEqual(decision.judgement, JUDGEMENT_BUY)
        self.assertIsNotNone(decision.selected)
        self.assertEqual(decision.selected.strategy_id, "wide_ss_b")
        self.assertEqual(decision.selected.tickets, ("5-7", "5-9"))
        self.assertEqual(decision.selected.ticket_count, 2)
        self.assertEqual(decision.total_stake, 200)
        self.assertEqual([item["horse_no"] for item in decision.horse_trust], ["5", "7", "9"])
        self.assertTrue(any("指数" in line for line in decision.horse_trust_summary))
        self.assertIn("horse_trust", decision.selected.audit)
        self.assertEqual([item["horse_number"] for item in decision.final_betting_context], ["5", "7", "9"])
        self.assertTrue(any("ゲージ 86" in line for line in decision.final_context_summary))
        self.assertEqual([item["ticket"] for item in decision.ticket_alignment], ["5-7", "5-9"])
        self.assertIn(decision.ticket_alignment[0]["alignment"], {"一致", "一部一致", "不一致"})
        self.assertIn("ticket_alignment", decision.selected.audit)
        self.assertTrue(all("7" in " ".join(decision.target_horses) or "9" in " ".join(decision.target_horses) for _ in [0]))

    def test_avoid_condition_blocks_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_payload(tmp, [win_b()])
            decision = build_investment_decision(sample_table(ai1_odds=1.8), "nar", json_paths=[path])

        self.assertEqual(decision.judgement, JUDGEMENT_PASS)
        self.assertIsNone(decision.selected)
        self.assertTrue(any("AI1オッズ2倍未満" in row.get("avoid_matched", []) for row in decision.audit_rows))

    def test_missing_required_role_is_not_displayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_payload(tmp, [wide_ss_b()])
            decision = build_investment_decision(sample_table(with_b=False), "nar", json_paths=[path])

        self.assertEqual(decision.judgement, JUDGEMENT_PASS)
        self.assertIsNone(decision.selected)
        self.assertTrue(any("Bが不在" in row.get("unmatched_conditions", []) for row in decision.audit_rows))

    def test_reference_strategy_becomes_hold(self) -> None:
        item = wide_ss_b(score=52.0)
        item["risk_label"] = "参考"
        item["return_rate"] = 108.0
        with tempfile.TemporaryDirectory() as tmp:
            path = write_payload(tmp, [item])
            decision = build_investment_decision(sample_table(), "jra", json_paths=[path])

        self.assertEqual(decision.judgement, JUDGEMENT_HOLD)
        self.assertIsNotNone(decision.selected)

    def test_loaded_json_without_match_does_not_use_fixed_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_payload(tmp, [wide_ss_b()])
            decision = build_investment_decision(sample_table(ai1_odds=9.0), "jra", json_paths=[path])

        self.assertEqual(decision.judgement, JUDGEMENT_PASS)
        self.assertIsNone(decision.selected)
        self.assertFalse(decision.fallback_used)

    def test_jra_and_nar_use_separate_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jra_path = write_payload(tmp, [wide_ss_b(score=80.0)])
            nar_path = Path(tmp) / "nar_strategy_selection.json"
            nar_path.write_text(
                json.dumps({"source": {"race_count": 34}, "strategies": [win_b(score=90.0)]}, ensure_ascii=False),
                encoding="utf-8",
            )
            jra = build_investment_decision(sample_table(), "jra", json_paths=[jra_path])
            nar = build_investment_decision(sample_table(), "nar", json_paths=[nar_path])

        self.assertEqual(jra.selected.strategy_id, "wide_ss_b")
        self.assertEqual(nar.selected.strategy_id, "win_b")


if __name__ == "__main__":
    unittest.main()
