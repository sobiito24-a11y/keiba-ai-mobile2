from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from core.mark_backtest import (
    add_honmei_maruta_difference_columns,
    attach_value_signals_to_records,
    attach_results,
    build_condition_summary,
    evaluate_box_strategies,
    evaluate_mark_singles,
    evaluate_value_singles,
    extract_prediction_rows,
    parse_result_html_text,
    prediction_html_files,
)


class MarkBacktestTest(unittest.TestCase):
    def test_parse_result_html_text_for_single_pair_and_trio_payoffs(self) -> None:
        html = """
        <table>
          <tr><th>着 順</th><th>馬 番</th><th>馬名</th><th>人 気</th><th>単勝 オッズ</th></tr>
          <tr><td>1</td><td>6</td><td>A</td><td>1</td><td>2.8</td></tr>
          <tr><td>2</td><td>10</td><td>B</td><td>5</td><td>10.6</td></tr>
          <tr><td>3</td><td>3</td><td>C</td><td>6</td><td>15.0</td></tr>
        </table>
        <table>
          <tr><td>単勝</td><td>6</td><td>280円</td><td>1人気</td></tr>
          <tr><td>複勝</td><td>6 10 3</td><td>130円 290円 350円</td><td>1人気4人気6人気</td></tr>
        </table>
        <table>
          <tr><td>ワイド</td><td>6 10 3 6 3 10</td><td>680円 580円 3,130円</td><td></td></tr>
          <tr><td>馬連</td><td>6 10</td><td>2,060円</td><td></td></tr>
          <tr><td>馬単</td><td>6 10</td><td>2,860円</td><td></td></tr>
          <tr><td>3連複</td><td>3 6 10</td><td>7,700円</td><td></td></tr>
          <tr><td>3連単</td><td>6 10 3</td><td>28,000円</td><td></td></tr>
        </table>
        """
        finish, payouts = parse_result_html_text(html)

        self.assertEqual(finish["6"]["finish"], 1)
        self.assertEqual(payouts["win"]["6"], 280)
        self.assertEqual(payouts["place"]["10"], 290)
        self.assertEqual(payouts["wide"][("6", "10")], 680)
        self.assertEqual(payouts["quinella"][("6", "10")], 2060)
        self.assertEqual(payouts["exacta"][("6", "10")], 2860)
        self.assertEqual(payouts["trio"][("3", "6", "10")], 7700)
        self.assertEqual(payouts["trifecta"][("6", "10", "3")], 28000)

    def test_prediction_html_files_excludes_result_html(self) -> None:
        race_dir = Path(__file__).resolve().parent / "fixtures" / "mark_backtest_race"

        html_files, file_names = prediction_html_files(race_dir, "jra")

        self.assertEqual(set(html_files), {"newspaper", "speed", "style", "oikiri"})
        self.assertNotIn("result", html_files)
        self.assertNotIn("result", file_names)

    def test_extract_prediction_rows_keeps_current_app_marks(self) -> None:
        result = SimpleNamespace(
            race_name="札幌1R",
            race_info={"venue": "札幌", "distance": 1800, "surface": "ダ"},
            overall_table=pd.DataFrame(
                [
                    {"馬番": 6, "馬名": "A", "表示印": "◎", "AI点": 90, "能力評価値": 80, "能力帯": "A", "オッズ": 2.8},
                    {"馬番": 10, "馬名": "B", "表示印": "○", "AI点": 88, "能力評価値": 78, "能力帯": "A", "オッズ": 10.6},
                    {"馬番": 3, "馬名": "C", "表示印": "✓", "AI点": 70, "能力評価値": 60, "能力帯": "C", "オッズ": 20.0},
                ]
            ),
        )

        rows, _ = extract_prediction_rows(result, "202601010101", "jra")

        self.assertEqual([row["mark"] for row in rows], ["◎", "○", "☆"])
        self.assertEqual(rows[0]["ai_current_rank"], 1)
        self.assertEqual(rows[1]["ability_rank"], 2)

    def test_single_win_place_payoff_calculation_and_missing_payoff(self) -> None:
        records = pd.DataFrame(
            [
                {"race_id": "r1", "race_type": "jra", "horse_no": "1", "mark": "◎", "win_payoff": 500, "place_payoff": 160},
                {"race_id": "r1", "race_type": "jra", "horse_no": "2", "mark": "○", "win_payoff": 0, "place_payoff": 120},
                {"race_id": "r2", "race_type": "nar", "horse_no": "3", "mark": "◎", "win_payoff": 0, "place_payoff": 0},
                {"race_id": "r2", "race_type": "nar", "horse_no": "4", "mark": "▲", "win_payoff": None, "place_payoff": None},
            ]
        )

        summary = evaluate_mark_singles(records)
        honmei_win = summary[(summary["印"] == "◎") & (summary["券種"] == "単勝")].iloc[0]
        honmei_place = summary[(summary["印"] == "◎") & (summary["券種"] == "複勝")].iloc[0]

        self.assertEqual(honmei_win["購入額"], 200)
        self.assertEqual(honmei_win["的中数"], 1)
        self.assertEqual(honmei_win["払戻額"], 500)
        self.assertEqual(honmei_win["回収率"], 250.0)
        self.assertEqual(honmei_win["最大払戻除外回収率"], 0.0)
        self.assertEqual(honmei_place["払戻額"], 160)

    def test_box_calculation_with_missing_marks_and_100_yen_units(self) -> None:
        records = pd.DataFrame(
            [
                {"race_id": "r1", "horse_no": "1", "mark": "◎"},
                {"race_id": "r1", "horse_no": "2", "mark": "○"},
                {"race_id": "r1", "horse_no": "3", "mark": "▲"},
                {"race_id": "r2", "horse_no": "4", "mark": "◎"},
            ]
        )
        payouts = {
            "r1": {"quinella": {("1", "2"): 800}, "wide": {("1", "2"): 300, ("1", "3"): 220}, "trio": {("1", "2", "3"): 1200}},
            "r2": {"quinella": {}, "wide": {}, "trio": {}},
        }

        summary = evaluate_box_strategies(records, payouts)
        quinella_3 = summary[(summary["対象印"] == "◎○▲") & (summary["券種"] == "馬連")].iloc[0]
        wide_3 = summary[(summary["対象印"] == "◎○▲") & (summary["券種"] == "ワイド")].iloc[0]
        trio_3 = summary[(summary["対象印"] == "◎○▲") & (summary["券種"] == "三連複")].iloc[0]

        self.assertEqual(quinella_3["総点数"], 3)
        self.assertEqual(quinella_3["総購入額"], 300)
        self.assertEqual(quinella_3["総払戻額"], 800)
        self.assertEqual(wide_3["総払戻額"], 520)
        self.assertEqual(trio_3["総購入額"], 100)
        self.assertEqual(trio_3["的中レース数"], 1)

    def test_attach_results_and_condition_summary_are_jra_nar_safe(self) -> None:
        rows = [
            {"race_id": "r1", "race_type": "jra", "venue": "札幌", "surface": "ダ", "distance": 1700, "field_size": 14, "horse_no": "1", "mark": "◎", "ability_band": "A", "ability_rank": 1, "ai_current_rank": 1, "odds": 2.8},
            {"race_id": "r2", "race_type": "nar", "venue": "門別", "surface": "ダ", "distance": 1200, "field_size": 10, "horse_no": "2", "mark": "◎", "ability_band": "B", "ability_rank": 2, "ai_current_rank": 2, "odds": None},
        ]
        finish = {"1": {"finish": 1}, "2": {"finish": 4}}
        payouts = {"win": {"1": 280}, "place": {"1": 130}, "wide": {}, "quinella": {}, "exacta": {}, "trio": {}, "trifecta": {}}
        attached = attach_results(rows, finish, payouts)

        frame = pd.DataFrame(attached)
        summary = build_condition_summary(frame)

        self.assertIn("jra", set(summary[summary["条件"] == "JRA/NAR"]["値"]))
        self.assertIn("nar", set(summary[summary["条件"] == "JRA/NAR"]["値"]))
        self.assertTrue((summary["参考区分"] == "参考値").all())

    def test_honmei_maruta_differences_are_stored_without_recalculating_scores(self) -> None:
        frame = pd.DataFrame(
            [
                {"race_id": "r1", "horse_no": "1", "mark": "◎", "ability_value": 82.5, "ai_score": 91.0, "ai_current_rank": 1},
                {"race_id": "r1", "horse_no": "2", "mark": "○", "ability_value": 80.0, "ai_score": 88.5, "ai_current_rank": 2},
            ]
        )

        result = add_honmei_maruta_difference_columns(frame)

        self.assertEqual(result.loc[0, "◎○能力値差"], 2.5)
        self.assertEqual(result.loc[1, "◎○今回評価差"], 2.5)
        self.assertEqual(frame.columns.tolist(), ["race_id", "horse_no", "mark", "ability_value", "ai_score", "ai_current_rank"])

    def test_value_signal_backtest_summary_is_separate_from_existing_marks(self) -> None:
        frame = pd.DataFrame(
            [
                {"race_id": "r1", "race_type": "jra", "horse_no": "1", "mark": "△", "ability_band": "B", "ability_rank": 3, "ai_current_rank": 4, "odds": 35.1, "win_payoff": 1200, "place_payoff": 300, "距離指数": 65, "近3走傾向": "上昇", "調教評価": "A"},
                {"race_id": "r1", "race_type": "jra", "horse_no": "2", "mark": "◎", "ability_band": "A", "ability_rank": 1, "ai_current_rank": 1, "odds": 2.2, "win_payoff": 0, "place_payoff": 110},
            ]
        )

        enriched = attach_value_signals_to_records(frame)
        summary = evaluate_value_singles(enriched)
        total = summary[summary["対象"].eq("妙味あり")].iloc[0]
        delta = summary[summary["対象"].eq("妙味あり＋△")].iloc[0]

        self.assertEqual(int(enriched["value_signal"].sum()), 1)
        self.assertEqual(total["購入数"], 1)
        self.assertEqual(total["単勝回収率"], 1200.0)
        self.assertEqual(delta["複勝払戻額"], 300)
        self.assertEqual(frame.loc[0, "mark"], "△")


if __name__ == "__main__":
    unittest.main()
