# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.purchase_conditions import (
    DEFAULT_DATA_DIR,
    DEFAULT_REPORT_DIR,
    build_ticket_strategy_detailed,
    load_jra_analysis_records,
    search_purchase_conditions,
    write_condition_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search JRA purchase conditions from saved audit data.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    records, meta = load_jra_analysis_records(args.data_dir)
    all_frame, official, reference, avoid, search_meta = search_purchase_conditions(records)
    meta.update(search_meta)

    time_split = build_time_split_frame(all_frame)
    ticket_detail = build_ticket_strategy_detailed(records, args.data_dir)
    paths = write_condition_outputs(records, all_frame, official, reference, avoid, time_split, ticket_detail, meta, args.out_dir)

    # Backward-compatible output names used by the previous UI investigation report.
    ticket_detail.to_csv(args.out_dir / "ticket_strategy_summary.csv", index=False, encoding="utf-8-sig")
    feature_summary = build_feature_summary(records)
    feature_summary.to_csv(args.out_dir / "feature_expectation_summary.csv", index=False, encoding="utf-8-sig")
    condition_combo = all_frame[all_frame["条件数"].le(2)].copy()
    condition_combo[[col for col in condition_combo.columns if col != "conditions"]].to_csv(
        args.out_dir / "condition_combo_ranking.csv", index=False, encoding="utf-8-sig"
    )
    (args.out_dir / "jra_betting_expectation_report.md").write_text(
        (args.out_dir / "jra_purchase_condition_report.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    print(f"データ: {meta['race_count']}R / {meta['horse_count']}頭")
    print(f"探索条件総数: {meta['explored_conditions']}")
    print(f"正式ランキング: {len(official)}件")
    print(f"参考ランキング: {len(reference)}件")
    print(f"出力先: {args.out_dir}")
    for name, path in paths.items():
        print(f"{name}: {path}")


def build_time_split_frame(all_frame: pd.DataFrame) -> pd.DataFrame:
    if all_frame.empty:
        return pd.DataFrame()
    columns = [
        "条件内容",
        "ranking_type",
        "探索期間_該当馬数",
        "探索期間_単勝回収率",
        "探索期間_複勝回収率",
        "検証期間_該当馬数",
        "検証期間_単勝回収率",
        "検証期間_複勝回収率",
        "検証メモ",
    ]
    return all_frame[[col for col in columns if col in all_frame.columns]].copy()


def build_feature_summary(records: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    features = [
        ("AI順位", "ai_rank_eval"),
        ("AI点", "ai_score_eval"),
        ("能力評価値", "ability_value_eval"),
        ("SS/A/B/C/Z", "display_group_eval"),
        ("オッズ", "odds_eval"),
        ("人気", "popularity_eval"),
        ("距離指数", "距離指数_num"),
        ("コース指数", "コース指数_num"),
        ("近3走最高", "近3走最高_num"),
        ("脚質", "脚質"),
        ("勢い", "勢い"),
        ("能力", "能力"),
        ("馬タイプ", "馬タイプ"),
        ("調教評価", "_調教評価記号"),
    ]
    for label, column in features:
        if column not in records.columns:
            continue
        series = records[column]
        if pd.api.types.is_numeric_dtype(series):
            values = pd.qcut(series.rank(method="first"), q=min(4, max(1, series.notna().sum() // 30)), duplicates="drop")
        else:
            values = series.astype(str)
        for value, group in records.groupby(values, dropna=False):
            if len(group) < 10:
                continue
            rows.append(feature_stats(label, str(value), group))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["単勝回収率", "複勝回収率", "対象数"], ascending=[False, False, False]).reset_index(drop=True)


def feature_stats(feature: str, value: str, group: pd.DataFrame) -> dict[str, object]:
    n = len(group)
    finish = pd.to_numeric(group["finish_eval"], errors="coerce")
    win_pay = pd.to_numeric(group["win_payoff_eval"], errors="coerce").fillna(0).sum()
    place_pay = pd.to_numeric(group["place_payoff_eval"], errors="coerce").fillna(0).sum()
    stake = n * 100
    return {
        "項目": feature,
        "条件": value,
        "対象数": n,
        "勝率": round(float(finish.eq(1).sum()) / n * 100, 1) if n else 0.0,
        "複勝率": round(float(finish.between(1, 3).sum()) / n * 100, 1) if n else 0.0,
        "単勝回収率": round(float(win_pay) / stake * 100, 1) if stake else 0.0,
        "複勝回収率": round(float(place_pay) / stake * 100, 1) if stake else 0.0,
        "単勝払戻": round(float(win_pay), 1),
        "複勝払戻": round(float(place_pay), 1),
    }


if __name__ == "__main__":
    main()
