#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build result-isolated Ver3/Ver4 regression reports from prediction ZIPs."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.purchase_conditions import clean_text, horse_no  # noqa: E402
from core.ver4_engine import build_ver4_race_summary, evaluate_ver4_table  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare saved Ver3 predictions with result-isolated Ver4 output.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Prediction History ZIP files")
    parser.add_argument("--results-json", type=Path, help="Optional actual results, joined only after prediction")
    parser.add_argument("--output", type=Path, default=Path("work/ver4_analysis"))
    args = parser.parse_args()

    predictions = [evaluate_prediction_zip(path) for path in args.inputs]
    actual_results = load_results(args.results_json) if args.results_json else {}
    write_reports(predictions, actual_results, args.output)
    print(f"Ver4 reports written: {args.output.resolve()}")
    return 0


def evaluate_prediction_zip(path: Path) -> dict[str, Any]:
    """Evaluate without accepting or reading a result/payoff object."""

    with zipfile.ZipFile(path) as archive:
        snapshot = json.loads(archive.read("prediction.json").decode("utf-8-sig"))
    race_info = snapshot.get("race_info") if isinstance(snapshot.get("race_info"), Mapping) else {}
    race_type = "nar" if clean_text(race_info.get("race_type")).lower() == "nar" else "jra"
    source_rows = [flatten_snapshot_horse(item) for item in snapshot.get("horses", []) if isinstance(item, Mapping)]
    v4 = evaluate_ver4_table(pd.DataFrame(source_rows), race_type, race_info)
    summary = build_ver4_race_summary(v4)
    return {
        "source_zip": path.name,
        "race_info": dict(race_info),
        "race_type": race_type,
        "ver3_investment": snapshot.get("investment_decision", {}),
        "horses": v4.to_dict("records"),
        "summary": summary,
    }


def flatten_snapshot_horse(horse: Mapping[str, Any]) -> dict[str, Any]:
    prediction = _mapping(horse.get("prediction"))
    indices = _mapping(horse.get("indices"))
    support = _mapping(horse.get("support"))
    final_context = _mapping(horse.get("final_betting_context"))
    momentum = _mapping(final_context.get("momentum"))
    race_shape = _mapping(final_context.get("race_shape"))
    row = {
        "馬番": horse.get("horse_no"),
        "馬名": horse.get("horse_name"),
        "馬年齢": horse.get("sex_age"),
        "斤量": horse.get("weight"),
        "斤量詳細": horse.get("weight_detail"),
        "騎手": horse.get("jockey"),
        "騎手詳細": horse.get("jockey_detail"),
        "騎手継続/乗替": horse.get("jockey_change"),
        "人気": horse.get("popularity"),
        "単勝オッズ": horse.get("odds"),
        "AI点": prediction.get("ai_score"),
        "AI順位": prediction.get("ai_rank"),
        "raw_score": prediction.get("raw_score"),
        "能力評価値": prediction.get("ability_value"),
        "表示印": prediction.get("mark"),
        "グループ": prediction.get("display_group"),
        "original_mark": prediction.get("original_mark"),
        "距離指数": indices.get("distance_index"),
        "コース指数": indices.get("course_index"),
        "3走前": indices.get("race3"),
        "2走前": indices.get("race2"),
        "前走": indices.get("race1"),
        "平均指数": indices.get("recent3_average"),
        "過去1年最高指数": indices.get("year_max_index"),
        "★最高指数": indices.get("star_max_index"),
        "★該当走": indices.get("star_max_race"),
        "★条件": indices.get("star_max_condition"),
        "年齢補正": support.get("age_adjustment"),
        "調教評価": support.get("training_evaluation"),
        "状態": support.get("state"),
        "補足": support.get("supplement"),
        "condition_fit_mark": horse.get("condition_fit_mark"),
        "condition_fit_level": horse.get("condition_fit_level"),
        "condition_fit_reason": horse.get("condition_fit_reason"),
        "matched_past_runs": horse.get("matched_past_runs", []),
        "recent_runs": horse.get("recent_races", []),
        "momentum_score": momentum.get("score"),
        "近3走傾向": horse.get("trend_label") or horse.get("trend"),
        "pace_fit": horse.get("pace_fit") or race_shape.get("pace_fit"),
        "corner4_evaluation": horse.get("corner4_evaluation") or race_shape.get("corner4_evaluation"),
        "straight_evaluation": horse.get("straight_evaluation") or race_shape.get("straight_evaluation"),
    }
    return row


def load_results(path: Path) -> dict[str, dict[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, dict[str, int]] = {}
    for race_id, items in payload.items():
        if not isinstance(items, list):
            continue
        output[str(race_id)] = {
            horse_no(item.get("horse_no")): int(item.get("finish"))
            for item in items
            if isinstance(item, Mapping) and horse_no(item.get("horse_no"))
        }
    return output


def write_reports(predictions: list[dict[str, Any]], actual: dict[str, dict[str, int]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    comparison_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    race_rows: list[dict[str, Any]] = []

    for item in predictions:
        info = item["race_info"]
        race_id = clean_text(info.get("race_id"))
        finishes = actual.get(race_id, {})
        horses = sorted(item["horses"], key=lambda row: int(row.get("race_rank_v4") or 999))
        for row in horses:
            number = horse_no(_pick(row, "馬番", "horse_no"))
            finish = finishes.get(number)
            comparison_rows.append(
                {
                    "race_id": race_id,
                    "venue": info.get("venue", ""),
                    "race_number": info.get("race_number", ""),
                    "horse_no": number,
                    "horse_name": row.get("馬名", ""),
                    "finish": finish if finish is not None else "",
                    "ver3_ai_score": row.get("AI点", ""),
                    "ver3_ai_rank": row.get("AI順位", ""),
                    "ver3_mark": row.get("表示印", ""),
                    "ver3_group": row.get("グループ", ""),
                    "horse_score_v4": row.get("horse_score_v4", ""),
                    "race_rank_v4": row.get("race_rank_v4", ""),
                    "mark_v4": row.get("mark_v4", ""),
                    "group_v4": row.get("group_v4", ""),
                    "condition_fit_mark": row.get("condition_fit_mark", ""),
                    "warning_reason": row.get("warning_reason", ""),
                    "watch_reason_v4": row.get("watch_reason_v4", ""),
                }
            )
            component_rows.append(
                {
                    "race_id": race_id,
                    "horse_no": number,
                    "horse_name": row.get("馬名", ""),
                    **{key: row.get(key, "") for key in (
                        "horse_score_v4", "race_rank_v4", "base_ability_score", "condition_score",
                        "jockey_score", "age_weight_score", "training_score", "momentum_score_v4",
                        "race_shape_score", "condition_matched_quality", "condition_distance_score",
                        "condition_course_score", "group_v4", "mark_v4", "axis_score",
                        "ticket_candidate_score", "opponent_eligible_v4", "opponent_veto_reason_v4",
                    )},
                }
            )

        top = horses[0] if horses else {}
        top_no = horse_no(_pick(top, "馬番", "horse_no"))
        top3 = {horse_no(_pick(row, "馬番", "horse_no")) for row in horses[:3]}
        winner = next((number for number, finish in finishes.items() if finish == 1), "")
        summary = item["summary"]
        race_rows.append(
            {
                "race_id": race_id,
                "venue": info.get("venue", ""),
                "race_number": info.get("race_number", ""),
                "winner": winner,
                "v4_top": top_no,
                "v4_top1_hit": bool(winner and winner == top_no),
                "v4_top3_hit": bool(winner and winner in top3),
                "decision_v4": summary.get("decision_v4", ""),
                "legacy_decision": summary.get("legacy_decision", ""),
                "axis_horse_no": summary.get("axis_horse_no", ""),
                "axis_confidence": summary.get("axis_confidence", ""),
                "ticket_count": len(summary.get("tickets", [])),
                "ticket_veto_reason": summary.get("ticket_veto_reason", ""),
            }
        )

    comparison = pd.DataFrame(comparison_rows)
    components = pd.DataFrame(component_rows)
    races = pd.DataFrame(race_rows)
    comparison.to_csv(output / "ver3_vs_ver4_5race.csv", index=False, encoding="utf-8-sig")
    components.to_csv(output / "ver4_component_scores.csv", index=False, encoding="utf-8-sig")
    races.to_csv(output / "ver4_backtest_summary.csv", index=False, encoding="utf-8-sig")
    (output / "ver3_vs_ver4_5race.md").write_text(_comparison_markdown(races, comparison), encoding="utf-8")
    (output / "ver4_logic_report.md").write_text(_logic_report(predictions, races), encoding="utf-8")
    summary_json = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "logic_version": "v4",
        "result_isolation": "Predictions were finalised before --results-json was joined.",
        "race_count": len(races),
        "result_linked_race_count": int(races["winner"].astype(str).str.len().gt(0).sum()) if not races.empty else 0,
        "top1_hits": int(races["v4_top1_hit"].sum()) if not races.empty else 0,
        "top3_hits": int(races["v4_top3_hit"].sum()) if not races.empty else 0,
        "decisions": races["decision_v4"].value_counts().to_dict() if not races.empty else {},
        "races": race_rows,
    }
    (output / "ver4_summary.json").write_text(json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")


def _comparison_markdown(races: pd.DataFrame, comparison: pd.DataFrame) -> str:
    lines = [
        "# Ver3 / Ver4 5レース比較",
        "",
        "実着順はVer4計算完了後に照合しており、Horse Score・印・グループ・買い判断には入力していません。",
        "",
        _frame_markdown(races) if not races.empty else "対象なし",
        "",
        "## 全馬比較",
        "",
        _frame_markdown(comparison) if not comparison.empty else "対象なし",
    ]
    return "\n".join(lines) + "\n"


def _logic_report(predictions: list[dict[str, Any]], races: pd.DataFrame) -> str:
    decisions = races["decision_v4"].value_counts().to_dict() if not races.empty else {}
    return "\n".join(
        [
            "# Ver4ロジック監査レポート",
            "",
            f"- 対象: {len(predictions)}レース",
            f"- 判断内訳: {json.dumps(decisions, ensure_ascii=False)}",
            "- Horse Score: 固定絶対スケールのコンポーネント加重平均",
            "- Race Rank: 同一レース内のHorse Score順位（Horse Score計算には不使用）",
            "- 条件適性: 条件一致レベル×該当走品質 50% + 距離 25% + コース 25%",
            "- 買い構成: 馬評価→印→軸→相手VETO→券種→点数の順",
            "- 実着順・払戻・オッズ: Score、印、グループ、判断の計算には不使用",
            "- 注意: 5レースは方向確認用で、パラメータ最適化や収益性の断定には使用しない",
            "",
        ]
    )


def _frame_markdown(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(_markdown_cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column)) for column in frame.columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return clean_text(value).replace("|", "\\|").replace("\n", "<br>")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and clean_text(value) not in {"", "-", "—"}:
            return value
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
