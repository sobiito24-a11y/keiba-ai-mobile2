# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.purchase_conditions import (
    ASSETS_ANALYSIS_DIR,
    DEFAULT_DATA_DIR,
    build_condition_json_payload,
    enrich_analysis_records,
    horse_no,
    load_jra_analysis_records,
    max_drawdown,
    max_losing_streak,
    pct,
    search_purchase_conditions,
    to_float,
)
from core.ticket_strategy_analysis import (
    evaluate_ticket_strategies,
    order_key,
    pair_key,
    trio_key,
)
from tools.analyze_jra_betting_expectation import (
    build_feature_summary,
    build_time_split_frame,
    condition_entries_from_payload,
    json_default,
    markdown_table,
    ticket_entries_from_frame,
)


DEFAULT_NAR_REPORT_DIR = PROJECT_ROOT / "work" / "nar_betting_expectation_report"
DEFAULT_SCOPE = "地方"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze NAR betting expectation from saved audit data.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_NAR_REPORT_DIR)
    parser.add_argument("--app-json-dir", type=Path, default=None)
    args = parser.parse_args()

    records, meta = load_nar_analysis_records(args.data_dir)
    payouts_by_race, payout_meta = build_nar_payouts_by_race(records, args.data_dir)
    meta.update(payout_meta)

    all_frame, official, reference, avoid, search_meta = search_purchase_conditions(records)
    meta.update(search_meta)
    time_split = build_time_split_frame(all_frame)
    ticket_all, ticket_official, ticket_reference, ticket_avoid = evaluate_ticket_strategies(
        records,
        payouts_by_race,
        source_race_count=int(meta.get("race_count", 0) or 0),
    )
    ticket_all = annotate_ticket_payout_availability(ticket_all, meta)
    ticket_official = annotate_ticket_payout_availability(ticket_official, meta)
    ticket_reference = annotate_ticket_payout_availability(ticket_reference, meta)
    ticket_avoid = annotate_ticket_payout_availability(ticket_avoid, meta)

    feature_summary = build_feature_summary(records)
    comparison = build_jra_nar_comparison(records, ticket_all, official, args.data_dir)
    paths = write_outputs(
        args.out_dir,
        records,
        all_frame,
        official,
        reference,
        avoid,
        time_split,
        ticket_all,
        ticket_official,
        ticket_reference,
        ticket_avoid,
        feature_summary,
        comparison,
        meta,
    )
    if args.app_json_dir is not None:
        paths.update(write_json_payloads(args.app_json_dir, ticket_official, ticket_reference, official, reference, meta))

    print(f"NAR data: {meta.get('race_count')}R / {meta.get('horse_count')} horses")
    print(f"data dir: {args.data_dir}")
    print(f"explored conditions: {meta.get('explored_conditions')}")
    print(f"official purchase conditions: {len(official)}")
    print(f"ticket strategies: {len(ticket_all)} total / {len(ticket_official)} official")
    print(f"output: {args.out_dir}")
    for name, path in paths.items():
        print(f"{name}: {path}")


def load_nar_analysis_records(data_dir: Path = DEFAULT_DATA_DIR) -> tuple[pd.DataFrame, dict[str, Any]]:
    records_path = data_dir / "nar_records.csv"
    payoff_path = data_dir / "horse_individual_records.csv"
    if not records_path.exists():
        raise FileNotFoundError(f"NAR records not found: {records_path}")

    records = pd.read_csv(records_path, encoding="utf-8-sig").copy()
    records["race_id"] = records["race_id"].astype(str)
    records["horse_no_key"] = records.apply(lambda row: horse_no(first_existing(row, ["馬番", "horse_no"])), axis=1)

    if payoff_path.exists():
        payoff = pd.read_csv(payoff_path, encoding="utf-8-sig")
        if "区分" in payoff.columns:
            payoff = payoff[payoff["区分"].astype(str).eq(DEFAULT_SCOPE)].copy()
        payoff["race_id"] = payoff["race_id"].astype(str)
        payoff["horse_no_key"] = payoff.apply(lambda row: horse_no(first_existing(row, ["馬番", "horse_no"])), axis=1)
        payoff_cols = [
            "race_id",
            "horse_no_key",
            "単勝払戻",
            "複勝払戻",
            "実際の着順",
            "結果人気",
            "結果オッズ",
        ]
        payoff = payoff[[col for col in payoff_cols if col in payoff.columns]].drop_duplicates(["race_id", "horse_no_key"])
        records = records.merge(payoff, on=["race_id", "horse_no_key"], how="left", suffixes=("", "_payoff"))

    records = enrich_analysis_records(records)
    meta = discover_nar_data(records, data_dir, records_path, payoff_path)
    return records, meta


def discover_nar_data(records: pd.DataFrame, data_dir: Path, records_path: Path, payoff_path: Path) -> dict[str, Any]:
    key_columns = [
        "finish_eval",
        "win_payoff_eval",
        "place_payoff_eval",
        "ai_rank_eval",
        "ai_score_eval",
        "ability_value_eval",
        "距離指数",
        "コース指数",
        "平均指数",
        "最高指数",
        "★最高指数",
        "脚質",
        "_jockey_changed",
        "_load_weight_change",
        "クラス変動",
        "勢い",
        "調教評価",
    ]
    missing = {}
    for column in key_columns:
        if column in records.columns:
            missing[column] = int(records[column].isna().sum())
        else:
            missing[column] = "column_missing"

    result_available = int(records["finish_eval"].notna().sum()) if "finish_eval" in records.columns else 0
    win_payoff_available = int(pd.to_numeric(records.get("win_payoff_eval", pd.Series(dtype=float)), errors="coerce").notna().sum())
    place_payoff_available = int(pd.to_numeric(records.get("place_payoff_eval", pd.Series(dtype=float)), errors="coerce").notna().sum())
    return {
        "scope": "nar",
        "data_dir": str(data_dir),
        "records_path": str(records_path),
        "payoff_path": str(payoff_path),
        "race_count": int(records["race_id"].nunique()),
        "horse_count": int(len(records)),
        "result_available_horses": result_available,
        "win_payoff_available_horses": win_payoff_available,
        "place_payoff_available_horses": place_payoff_available,
        "missing_counts": missing,
        "source_columns": list(records.columns),
        "odds_basis": "保存済み地方AI出力CSVのレース前オッズで条件判定、払戻は監査CSVの確定払戻を使用",
    }


def build_nar_payouts_by_race(records: pd.DataFrame, data_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payouts: dict[str, dict[str, Any]] = {}
    for race_id, group in records.groupby("race_id"):
        race_map = empty_payout_map()
        for _, row in group.iterrows():
            no = horse_no(row.get("horse_no_eval"))
            if not no:
                continue
            win = to_float(row.get("win_payoff_eval")) or 0
            place = to_float(row.get("place_payoff_eval")) or 0
            if win > 0:
                race_map["win"][no] = win
            if place > 0:
                race_map["place"][no] = place
        payouts[str(race_id)] = race_map

    pair_sources = [
        data_dir / "full_ticket_rank_pair_detail.csv",
        data_dir / "single_odds_umaren_umatan_detail.csv",
        data_dir / "full_ticket_rank_wide_detail.csv",
        data_dir / "single_odds_wide_detail.csv",
    ]
    pair_rows = 0
    for path in pair_sources:
        pair_rows += merge_pair_payouts(payouts, path, set(records["race_id"].astype(str)))

    triple_rows = merge_triple_payouts_from_existing_hits(payouts, records, data_dir / "best_hit_combinations_detail.csv")
    meta = {
        "payout_sources": {
            "single": "horse_individual_records.csv",
            "pair": [str(path) for path in pair_sources if path.exists()],
            "triple": str(data_dir / "best_hit_combinations_detail.csv"),
        },
        "pair_payout_rows_used": pair_rows,
        "triple_payout_rows_used": triple_rows,
        "payout_race_counts": payout_race_counts(payouts),
    }
    return payouts, meta


def empty_payout_map() -> dict[str, dict[Any, float]]:
    return {
        "win": {},
        "place": {},
        "wide": {},
        "quinella": {},
        "exacta": {},
        "trio": {},
        "trifecta": {},
    }


def merge_pair_payouts(payouts: dict[str, dict[str, Any]], path: Path, race_ids: set[str]) -> int:
    if not path.exists():
        return 0
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "区分" in frame.columns:
        frame = frame[frame["区分"].astype(str).eq(DEFAULT_SCOPE)].copy()
    required = {"race_id", "券種", "馬番1", "馬番2", "払戻"}
    if not required.issubset(frame.columns):
        return 0
    used = 0
    for _, row in frame.iterrows():
        race_id = str(row.get("race_id"))
        if race_id not in race_ids:
            continue
        kind = normalize_ticket_kind(row.get("券種"))
        if kind not in {"wide", "quinella", "exacta"}:
            continue
        payout = to_float(row.get("払戻")) or 0
        if payout <= 0:
            continue
        no1 = horse_no(row.get("馬番1"))
        no2 = horse_no(row.get("馬番2"))
        if not no1 or not no2 or no1 == no2:
            continue
        key = order_key((no1, no2)) if kind == "exacta" else pair_key((no1, no2))
        payouts.setdefault(race_id, empty_payout_map()).setdefault(kind, {})
        payouts[race_id][kind][key] = max(float(payout), float(payouts[race_id][kind].get(key, 0) or 0))
        used += 1
    return used


def merge_triple_payouts_from_existing_hits(
    payouts: dict[str, dict[str, Any]],
    records: pd.DataFrame,
    path: Path,
) -> int:
    if not path.exists():
        return 0
    detail = pd.read_csv(path, encoding="utf-8-sig")
    if "区分" in detail.columns:
        detail = detail[detail["区分"].astype(str).eq(DEFAULT_SCOPE)].copy()
    if not {"race_id", "券種", "払戻"}.issubset(detail.columns):
        return 0

    top3_by_race = actual_top3_by_race(records)
    used = 0
    for race_id, group in detail.groupby(detail["race_id"].astype(str)):
        top3 = top3_by_race.get(str(race_id))
        if not top3:
            continue
        race_map = payouts.setdefault(str(race_id), empty_payout_map())
        for source_kind, target_kind in [("trio", "trio"), ("trifecta", "trifecta")]:
            subset = group[group["券種"].astype(str).map(normalize_ticket_kind).eq(source_kind)]
            pays = pd.to_numeric(subset["払戻"], errors="coerce").fillna(0)
            payout = float(pays.max()) if not pays.empty else 0.0
            if payout <= 0:
                continue
            key = trio_key(top3) if target_kind == "trio" else order_key(top3)
            race_map[target_kind][key] = max(payout, float(race_map[target_kind].get(key, 0) or 0))
            used += 1
    return used


def actual_top3_by_race(records: pd.DataFrame) -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    frame = records.copy()
    frame["_finish_num"] = pd.to_numeric(frame.get("finish_eval"), errors="coerce")
    for race_id, group in frame.dropna(subset=["_finish_num"]).groupby("race_id"):
        top = group[group["_finish_num"].between(1, 3)].sort_values("_finish_num")
        nums = [horse_no(value) for value in top["horse_no_eval"].tolist()]
        nums = [value for value in nums if value]
        if len(nums) == 3:
            out[str(race_id)] = (nums[0], nums[1], nums[2])
    return out


def payout_race_counts(payouts: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for kind in ["win", "place", "wide", "quinella", "exacta", "trio", "trifecta"]:
        counts[kind] = sum(1 for race_map in payouts.values() if race_map.get(kind))
    return counts


def annotate_ticket_payout_availability(frame: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    out = frame.copy()
    counts = meta.get("payout_race_counts", {})

    def status(ticket_type: Any) -> str:
        key = japanese_ticket_to_key(str(ticket_type))
        available = int(counts.get(key, 0) or 0)
        return "available" if available > 0 else "payout_data_missing"

    out["payout_data_status"] = out["ticket_type"].map(status)
    return out


def write_outputs(
    out_dir: Path,
    records: pd.DataFrame,
    all_frame: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    avoid: pd.DataFrame,
    time_split: pd.DataFrame,
    ticket_all: pd.DataFrame,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    ticket_avoid: pd.DataFrame,
    feature_summary: pd.DataFrame,
    comparison: dict[str, pd.DataFrame],
    meta: dict[str, Any],
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    paths["data_discovery"] = out_dir / "nar_data_discovery.csv"
    paths["condition_all"] = out_dir / "nar_purchase_condition_all.csv"
    paths["condition_ranked"] = out_dir / "nar_purchase_condition_ranked.csv"
    paths["condition_reference"] = out_dir / "nar_purchase_condition_reference.csv"
    paths["condition_avoid"] = out_dir / "nar_purchase_condition_avoid.csv"
    paths["condition_time_split"] = out_dir / "nar_purchase_condition_time_split.csv"
    paths["ticket_all"] = out_dir / "nar_ticket_strategy_all.csv"
    paths["ticket_ranked"] = out_dir / "nar_ticket_strategy_ranked.csv"
    paths["ticket_reference"] = out_dir / "nar_ticket_strategy_reference.csv"
    paths["ticket_avoid"] = out_dir / "nar_ticket_strategy_avoid.csv"
    paths["ticket_by_type"] = out_dir / "nar_ticket_strategy_by_type.csv"
    paths["feature_summary"] = out_dir / "nar_feature_expectation_summary.csv"
    paths["comparison"] = out_dir / "jra_nar_comparison.csv"
    paths["recommendations_json"] = out_dir / "nar_betting_recommendations.json"
    paths["ticket_json"] = out_dir / "nar_ticket_strategy_ranked.json"
    paths["condition_json"] = out_dir / "nar_purchase_condition_ranked.json"
    paths["summary_json"] = out_dir / "nar_analysis_summary.json"
    paths["markdown"] = out_dir / "nar_betting_expectation_report.md"

    data_discovery_frame(meta).to_csv(paths["data_discovery"], index=False, encoding="utf-8-sig")
    write_condition_csv(all_frame, paths["condition_all"])
    write_condition_csv(official, paths["condition_ranked"])
    write_condition_csv(reference, paths["condition_reference"])
    write_condition_csv(avoid, paths["condition_avoid"])
    time_split.to_csv(paths["condition_time_split"], index=False, encoding="utf-8-sig")

    ticket_all.to_csv(paths["ticket_all"], index=False, encoding="utf-8-sig")
    ticket_official.to_csv(paths["ticket_ranked"], index=False, encoding="utf-8-sig")
    ticket_reference.to_csv(paths["ticket_reference"], index=False, encoding="utf-8-sig")
    ticket_avoid.to_csv(paths["ticket_avoid"], index=False, encoding="utf-8-sig")
    ticket_by_type = ticket_all.sort_values(["ticket_type", "reliability_score", "return_rate"], ascending=[True, False, False]) if not ticket_all.empty else ticket_all
    ticket_by_type.to_csv(paths["ticket_by_type"], index=False, encoding="utf-8-sig")
    feature_summary.to_csv(paths["feature_summary"], index=False, encoding="utf-8-sig")
    comparison["combined"].to_csv(paths["comparison"], index=False, encoding="utf-8-sig")

    payload_paths = write_json_payloads(out_dir, ticket_official, ticket_reference, official, reference, meta)
    paths.update({f"json_{key}": value for key, value in payload_paths.items()})
    paths["summary_json"].write_text(
        json.dumps(build_summary_payload(records, ticket_all, official, reference, avoid, comparison, meta), ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    paths["markdown"].write_text(
        build_nar_report(records, all_frame, official, reference, avoid, ticket_all, ticket_official, ticket_reference, feature_summary, comparison, meta),
        encoding="utf-8",
    )
    return paths


def write_condition_csv(frame: pd.DataFrame, path: Path) -> None:
    if frame is None:
        pd.DataFrame().to_csv(path, index=False, encoding="utf-8-sig")
        return
    columns = [col for col in frame.columns if col not in {"conditions", "match_signature"}]
    frame[columns].to_csv(path, index=False, encoding="utf-8-sig")


def write_json_payloads(
    out_dir: Path,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    meta: dict[str, Any],
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "nar_betting_recommendations": out_dir / "nar_betting_recommendations.json",
        "nar_ticket_strategy_ranked": out_dir / "nar_ticket_strategy_ranked.json",
        "nar_purchase_condition_ranked": out_dir / "nar_purchase_condition_ranked.json",
    }
    condition_payload = build_nar_condition_payload(official, reference, meta)
    ticket_payload = build_nar_recommendation_payload(ticket_official, ticket_reference, official, reference, meta, ticket_only=True)
    betting_payload = build_nar_recommendation_payload(ticket_official, ticket_reference, official, reference, meta)
    paths["nar_betting_recommendations"].write_text(json.dumps(betting_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["nar_ticket_strategy_ranked"].write_text(json.dumps(ticket_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["nar_purchase_condition_ranked"].write_text(json.dumps(condition_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return paths


def build_nar_condition_payload(official: pd.DataFrame, reference: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    payload = build_condition_json_payload(official, reference, meta)
    payload["scope"] = "nar"
    payload["note"] = "地方競馬の保存済み監査データだけを使った暫定検証結果。AI予想ロジックには使用しません。"
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return payload


def build_nar_recommendation_payload(
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    meta: dict[str, Any],
    *,
    ticket_only: bool = False,
) -> dict[str, Any]:
    ticket_entries = ticket_entries_from_frame(pd.concat([ticket_official.head(20), ticket_reference.head(20)], ignore_index=True))
    condition_entries = [] if ticket_only else condition_entries_from_payload(build_nar_condition_payload(official, reference, meta))
    return {
        "version": 2,
        "scope": "nar",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "race_count": int(meta.get("race_count", 0) or 0),
            "horse_count": int(meta.get("horse_count", 0) or 0),
            "source_race_count": int(meta.get("race_count", 0) or 0),
            "odds_basis": meta.get("odds_basis", ""),
            "payout_race_counts": meta.get("payout_race_counts", {}),
        },
        "recommendations": ticket_entries + condition_entries,
    }


def build_jra_nar_comparison(
    nar_records: pd.DataFrame,
    nar_ticket_all: pd.DataFrame,
    nar_official_conditions: pd.DataFrame,
    data_dir: Path,
) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for scope, records in [("地方", nar_records)]:
        rows.extend(rank_summary_rows(scope, records))
        rows.extend(mark_summary_rows(scope, records))

    jra_records: pd.DataFrame | None = None
    try:
        jra_records, _meta = load_jra_analysis_records(data_dir)
        rows.extend(rank_summary_rows("中央", jra_records))
        rows.extend(mark_summary_rows("中央", jra_records))
    except Exception as exc:
        rows.append({"比較区分": "中央", "項目": "load_error", "値": str(exc)})

    rows.extend(ticket_comparison_rows("地方", nar_ticket_all))
    jra_report = data_dir.parent / "jra_betting_expectation_report" / "ticket_strategy_by_type.csv"
    if jra_report.exists():
        jra_ticket = pd.read_csv(jra_report, encoding="utf-8-sig")
        rows.extend(ticket_comparison_rows("中央", jra_ticket))

    top_condition_rows = top_condition_comparison_rows("地方", nar_official_conditions)
    jra_condition = data_dir.parent / "jra_betting_expectation_report" / "purchase_condition_ranked.csv"
    if jra_condition.exists():
        top_condition_rows.extend(top_condition_comparison_rows("中央", pd.read_csv(jra_condition, encoding="utf-8-sig")))
    rows.extend(top_condition_rows)

    pass_rows = build_pass_rate_rows(nar_records, nar_ticket_all, jra_records, data_dir)
    rows.extend(pass_rows)
    return {"combined": pd.DataFrame(rows)}


def rank_summary_rows(scope: str, records: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank in [1, 2]:
        subset = records[pd.to_numeric(records["ai_rank_eval"], errors="coerce").eq(rank)]
        stats = horse_expectation_stats(subset)
        rows.append({"比較区分": scope, "項目": f"AI{rank}位", **stats})
    return rows


def mark_summary_rows(scope: str, records: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if "mark_eval" not in records.columns:
        return rows
    for mark, group in records.groupby("mark_eval", dropna=False):
        if not str(mark):
            continue
        rows.append({"比較区分": scope, "項目": f"印{mark}", **horse_expectation_stats(group)})
    return rows


def ticket_comparison_rows(scope: str, ticket_all: pd.DataFrame) -> list[dict[str, Any]]:
    if ticket_all is None or ticket_all.empty:
        return []
    rows: list[dict[str, Any]] = []
    sorted_frame = ticket_all.sort_values(["ticket_type", "reliability_score", "return_rate"], ascending=[True, False, False])
    for ticket_type, group in sorted_frame.groupby("ticket_type", sort=True):
        row = group.iloc[0]
        rows.append(
            {
                "比較区分": scope,
                "項目": f"券種別トップ:{ticket_type}",
                "条件": row.get("label", ""),
                "対象R": row.get("purchase_races", 0),
                "購入点数": row.get("purchase_points", 0),
                "的中率": row.get("hit_rate", 0),
                "回収率": row.get("return_rate", 0),
                "収支": row.get("profit", 0),
            }
        )
    return rows


def top_condition_comparison_rows(scope: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in frame.head(5).iterrows():
        rows.append(
            {
                "比較区分": scope,
                "項目": "条件探索上位",
                "条件": row.get("条件内容", ""),
                "対象馬数": row.get("該当馬数", 0),
                "対象R": row.get("該当レース数", 0),
                "単勝回収率": row.get("単勝回収率", 0),
                "複勝回収率": row.get("複勝回収率", 0),
                "condition_score": row.get("condition_score", 0),
            }
        )
    return rows


def build_pass_rate_rows(
    nar_records: pd.DataFrame,
    nar_ticket_all: pd.DataFrame,
    jra_records: pd.DataFrame | None,
    data_dir: Path,
) -> list[dict[str, Any]]:
    rows = [pass_rate_row("地方", nar_records, nar_ticket_all)]
    jra_ticket_path = data_dir.parent / "jra_betting_expectation_report" / "ticket_strategy_ranked.csv"
    if jra_records is not None and jra_ticket_path.exists():
        rows.append(pass_rate_row("中央", jra_records, pd.read_csv(jra_ticket_path, encoding="utf-8-sig")))
    return rows


def pass_rate_row(scope: str, records: pd.DataFrame, ticket_frame: pd.DataFrame) -> dict[str, Any]:
    race_count = int(records["race_id"].nunique()) if records is not None and not records.empty else 0
    best_coverage = int(pd.to_numeric(ticket_frame.get("purchase_races", pd.Series(dtype=float)), errors="coerce").max() or 0) if ticket_frame is not None and not ticket_frame.empty else 0
    return {
        "比較区分": scope,
        "項目": "見送り率(概算)",
        "対象R": race_count,
        "購入R": best_coverage,
        "見送り率": round((race_count - best_coverage) / race_count * 100, 1) if race_count else 0.0,
        "条件": "券種ランキング最上位の最大カバー率から算出した概算",
    }


def horse_expectation_stats(group: pd.DataFrame) -> dict[str, Any]:
    n = int(len(group))
    if n == 0:
        return {"対象馬数": 0, "対象R": 0, "勝率": 0.0, "連対率": 0.0, "複勝率": 0.0, "単勝回収率": 0.0, "複勝回収率": 0.0}
    finish = pd.to_numeric(group.get("finish_eval"), errors="coerce")
    win_pay = pd.to_numeric(group.get("win_payoff_eval"), errors="coerce").fillna(0)
    place_pay = pd.to_numeric(group.get("place_payoff_eval"), errors="coerce").fillna(0)
    stake = n * 100
    return {
        "対象馬数": n,
        "対象R": int(group["race_id"].nunique()) if "race_id" in group.columns else 0,
        "勝率": pct(int(finish.eq(1).sum()), n),
        "連対率": pct(int(finish.between(1, 2).sum()), n),
        "複勝率": pct(int(finish.between(1, 3).sum()), n),
        "単勝回収率": pct(float(win_pay.sum()), stake),
        "複勝回収率": pct(float(place_pay.sum()), stake),
        "平均人気": round(float(pd.to_numeric(group.get("popularity_eval"), errors="coerce").mean()), 1) if "popularity_eval" in group.columns else None,
        "平均オッズ": round(float(pd.to_numeric(group.get("odds_eval"), errors="coerce").mean()), 1) if "odds_eval" in group.columns else None,
    }


def build_summary_payload(
    records: pd.DataFrame,
    ticket_all: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    avoid: pd.DataFrame,
    comparison: dict[str, pd.DataFrame],
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": 1,
        "scope": "nar",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "top_ticket_strategies": frame_records(ticket_all.head(20)),
        "top_purchase_conditions": frame_records(official.head(20)),
        "reference_purchase_conditions": frame_records(reference.head(20)),
        "avoid_conditions": frame_records(avoid.head(20)),
        "comparison": frame_records(comparison["combined"]),
        "headline": {
            "ai1": horse_expectation_stats(records[pd.to_numeric(records["ai_rank_eval"], errors="coerce").eq(1)]),
            "ai2": horse_expectation_stats(records[pd.to_numeric(records["ai_rank_eval"], errors="coerce").eq(2)]),
        },
    }


def build_nar_report(
    records: pd.DataFrame,
    all_frame: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    avoid: pd.DataFrame,
    ticket_all: pd.DataFrame,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    feature_summary: pd.DataFrame,
    comparison: dict[str, pd.DataFrame],
    meta: dict[str, Any],
) -> str:
    ai1 = horse_expectation_stats(records[pd.to_numeric(records["ai_rank_eval"], errors="coerce").eq(1)])
    ai2 = horse_expectation_stats(records[pd.to_numeric(records["ai_rank_eval"], errors="coerce").eq(2)])
    lines = [
        "# 地方競馬 買い方期待値分析レポート",
        "",
        "保存済み地方競馬データだけを使った暫定検証です。AI点・印・能力評価・Parser・PredictionResult・PNG・既存予想ロジックは変更していません。",
        "",
        "## データ検出",
        f"- 保存場所: {meta.get('data_dir')}",
        f"- 対象レース数: {meta.get('race_count')}R",
        f"- 対象馬数: {meta.get('horse_count')}頭",
        f"- 結果データ取得: {meta.get('result_available_horses')}頭",
        f"- 単勝払戻データ取得: {meta.get('win_payoff_available_horses')}頭",
        f"- 複勝払戻データ取得: {meta.get('place_payoff_available_horses')}頭",
        f"- 券種払戻データ取得R: {meta.get('payout_race_counts')}",
        "",
        "## 全体サマリー",
        markdown_table(pd.DataFrame([
            {"項目": "AI1位", **ai1},
            {"項目": "AI2位", **ai2},
        ]), ["項目", "対象馬数", "対象R", "勝率", "連対率", "複勝率", "単勝回収率", "複勝回収率", "平均人気", "平均オッズ"]),
        "",
        "## 券種別分析（正式）",
        markdown_table(ticket_official.head(20), ["ticket_type", "label", "purchase_races", "purchase_points", "hit_rate", "return_rate", "profit", "average_payout", "max_losing_streak", "max_drawdown", "risk_label", "payout_data_status"]),
        "",
        "## 券種別分析（参考）",
        markdown_table(ticket_reference.head(20), ["ticket_type", "label", "purchase_races", "purchase_points", "hit_rate", "return_rate", "profit", "average_payout", "max_losing_streak", "max_drawdown", "risk_label", "payout_data_status"]),
        "",
        "## 買う条件ランキング（正式）",
        markdown_table(official.head(20), ["評価", "条件内容", "該当馬数", "該当レース数", "勝率", "連対率", "複勝率", "単勝回収率", "複勝回収率", "condition_score", "最大単勝払戻寄与率"]),
        "",
        "## 買う条件ランキング（参考）",
        markdown_table(reference.head(20), ["評価", "条件内容", "該当馬数", "該当レース数", "勝率", "連対率", "複勝率", "単勝回収率", "複勝回収率", "condition_score", "最大単勝払戻寄与率"]),
        "",
        "## 買わない条件ランキング",
        markdown_table(avoid.head(20), ["条件内容", "該当馬数", "該当レース数", "勝率", "複勝率", "単勝回収率", "複勝回収率", "最大連敗", "最大ドローダウン"]),
        "",
        "## 特徴量別期待値",
        markdown_table(feature_summary.head(30), ["項目", "条件", "対象数", "勝率", "複勝率", "単勝回収率", "複勝回収率"]),
        "",
        "## 中央・地方比較",
        markdown_table(comparison["combined"], ["比較区分", "項目", "条件", "対象馬数", "対象R", "勝率", "連対率", "複勝率", "単勝回収率", "複勝回収率", "回収率", "的中率", "見送り率"]),
        "",
        "## 地方だけ悪化する場合の主な確認点",
        "- 地方の今回サンプルは34Rで、中央49Rよりさらに少ないため一発配当の影響を強く受けます。",
        "- ★最高指数は現行保存CSVでは不足が多く、条件探索から除外される場合があります。",
        "- 三連系の払戻は既存集計から補完しているため、保存済み結果HTMLから直接取った中央より検証精度が落ちる可能性があります。",
        "- 地方はオッズ変動、取消、クラス差、転入初戦などの影響が中央より大きく、同じAI順位でも期待値が不安定になりやすいです。",
        "",
        "## 生成物",
        "- nar_betting_recommendations.json",
        "- nar_ticket_strategy_ranked.json",
        "- nar_purchase_condition_ranked.json",
        "- CSV一式",
    ]
    return "\n".join(lines)


def data_discovery_frame(meta: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key in [
        "data_dir",
        "records_path",
        "payoff_path",
        "race_count",
        "horse_count",
        "result_available_horses",
        "win_payoff_available_horses",
        "place_payoff_available_horses",
        "pair_payout_rows_used",
        "triple_payout_rows_used",
    ]:
        rows.append({"項目": key, "値": meta.get(key)})
    for key, value in (meta.get("payout_race_counts") or {}).items():
        rows.append({"項目": f"payout_races_{key}", "値": value})
    for key, value in (meta.get("missing_counts") or {}).items():
        rows.append({"項目": f"missing_{key}", "値": value})
    rows.append({"項目": "source_columns", "値": ", ".join(map(str, meta.get("source_columns", [])))})
    return pd.DataFrame(rows)


def frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return json.loads(json.dumps(frame.to_dict(orient="records"), ensure_ascii=False, default=json_default))


def normalize_ticket_kind(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "win": "win",
        "place": "place",
        "wide": "wide",
        "quinella": "quinella",
        "exacta": "exacta",
        "trio": "trio",
        "trifecta": "trifecta",
        "単勝": "win",
        "複勝": "place",
        "ワイド": "wide",
        "馬連": "quinella",
        "馬単": "exacta",
        "三連複": "trio",
        "三連単": "trifecta",
        "3連複": "trio",
        "3連単": "trifecta",
    }
    return mapping.get(text, text)


def japanese_ticket_to_key(ticket_type: str) -> str:
    return normalize_ticket_kind(ticket_type)


def first_existing(row: pd.Series, columns: list[str]) -> Any:
    for column in columns:
        if column in row.index:
            value = row.get(column)
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                return value
    return None


if __name__ == "__main__":
    main()
