# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import itertools
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "work" / "audit_ver20_outputs"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "work" / "jra_betting_expectation_report"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze saved JRA betting expectation data.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    records = load_jra_records(args.data_dir)
    pair_detail = load_ticket_detail(args.data_dir / "full_ticket_rank_pair_detail.csv", "quinella")
    wide_detail = load_ticket_detail(args.data_dir / "full_ticket_rank_wide_detail.csv", "wide")
    precomputed = load_precomputed_summary(args.data_dir / "best_hit_combinations_summary.csv")

    ticket_summary = build_ticket_strategy_summary(records, pair_detail, wide_detail, precomputed)
    feature_summary = build_feature_summary(records)
    condition_ranking = build_condition_ranking(records)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ticket_summary.to_csv(args.out_dir / "ticket_strategy_summary.csv", index=False, encoding="utf-8-sig")
    feature_summary.to_csv(args.out_dir / "feature_expectation_summary.csv", index=False, encoding="utf-8-sig")
    condition_ranking.to_csv(args.out_dir / "condition_combo_ranking.csv", index=False, encoding="utf-8-sig")
    report = build_markdown_report(ticket_summary, feature_summary, condition_ranking, records)
    (args.out_dir / "jra_betting_expectation_report.md").write_text(report, encoding="utf-8")

    print(report)
    print(f"\nwritten: {args.out_dir}")


def load_jra_records(data_dir: Path) -> pd.DataFrame:
    rich = pd.read_csv(data_dir / "jra_folder_records.csv", encoding="utf-8-sig")
    rich = rich.copy()
    rich["race_id"] = rich["race_id"].astype(str)
    rich["馬番"] = rich["馬番"].map(horse_no)
    rich = rich[rich["race_id"].str.len().gt(0) & rich["馬番"].str.len().gt(0)].copy()

    pay_path = data_dir / "horse_individual_records.csv"
    if pay_path.exists():
        payoff = pd.read_csv(pay_path, encoding="utf-8-sig")
        payoff = payoff[payoff.get("区分").astype(str).eq("中央")].copy()
        payoff["race_id"] = payoff["race_id"].astype(str)
        payoff["馬番"] = payoff["馬番"].map(horse_no)
        payoff_cols = ["race_id", "馬番", "単勝払戻", "複勝払戻", "実際の着順", "結果人気", "結果オッズ"]
        payoff = payoff[[c for c in payoff_cols if c in payoff.columns]].drop_duplicates(["race_id", "馬番"])
        rich = rich.merge(payoff, on=["race_id", "馬番"], how="left", suffixes=("", "_payoff"))
    for source, target in [("finish", "実際の着順"), ("result_popularity", "結果人気"), ("result_odds", "結果オッズ")]:
        if source in rich.columns and target in rich.columns:
            rich[target] = rich[target].where(pd.notna(rich[target]), rich[source])
    rich["display_group"] = rich.apply(display_group, axis=1)
    rich["display_mark"] = rich.apply(display_mark, axis=1)
    rich["ai_rank_eval"] = rich.apply(lambda row: first_number(row, ["ai_rank", "AI順位", "AI点順位"]), axis=1)
    rich["ability_value_eval"] = rich.apply(lambda row: first_number(row, ["能力評価値", "ability_display_score", "_raw_score", "raw_score"]), axis=1)
    rich["win_payoff_eval"] = pd.to_numeric(rich.get("単勝払戻"), errors="coerce").fillna(0)
    rich["place_payoff_eval"] = pd.to_numeric(rich.get("複勝払戻"), errors="coerce").fillna(0)
    rich["finish_eval"] = pd.to_numeric(rich.get("実際の着順"), errors="coerce")
    return rich


def load_ticket_detail(path: Path, bet_type: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["race_id", "pair_key", "払戻", "的中", "券種"])
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame = frame[frame.get("区分").astype(str).eq("中央")].copy()
    frame["race_id"] = frame["race_id"].astype(str)
    frame["pair_key"] = frame.apply(lambda row: pair_key([row.get("馬番1"), row.get("馬番2")]), axis=1)
    frame["払戻"] = pd.to_numeric(frame.get("払戻"), errors="coerce").fillna(0)
    frame["的中"] = frame["払戻"].gt(0)
    frame["券種"] = bet_type
    return frame


def load_precomputed_summary(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "区分" in frame.columns:
        frame = frame[frame["区分"].astype(str).eq("中央")].copy()
    return frame


def build_ticket_strategy_summary(
    records: pd.DataFrame,
    pair_detail: pd.DataFrame,
    wide_detail: pd.DataFrame,
    precomputed: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    single_selectors = {
        "AI1位": lambda df: df[df["ai_rank_eval"].eq(1)],
        "AI2位": lambda df: df[df["ai_rank_eval"].eq(2)],
        "AI3位": lambda df: df[df["ai_rank_eval"].eq(3)],
        "SS": lambda df: df[df["display_group"].eq("SS")],
        "A": lambda df: df[df["display_group"].eq("A")],
        "B": lambda df: df[df["display_group"].eq("B")],
        "C": lambda df: df[df["display_group"].eq("C")],
    }
    for label, selector in single_selectors.items():
        selected = selector(records).copy()
        if selected.empty:
            continue
        rows.append(summarise_horse_strategy("単勝", label, selected, "win_payoff_eval"))
        rows.append(summarise_horse_strategy("複勝", label, selected, "place_payoff_eval"))

    pair_strategies = [
        ("SS-A", lambda df: cross_group_pairs(df, ["SS"], ["A"])),
        ("SS-B", lambda df: cross_group_pairs(df, ["SS"], ["B"])),
        ("SS-C", lambda df: cross_group_pairs(df, ["SS"], ["C"])),
        ("A-B", lambda df: cross_group_pairs(df, ["A"], ["B"])),
        ("A-C", lambda df: cross_group_pairs(df, ["A"], ["C"])),
        ("AI1-AI2", lambda df: ai_rank_pair(df, 1, 2)),
        ("AI1-AI3", lambda df: ai_rank_pair(df, 1, 3)),
        ("AI2-AI3", lambda df: ai_rank_pair(df, 2, 3)),
    ]
    for label, selector in pair_strategies:
        rows.append(summarise_pair_strategy(records, pair_detail, "馬連", label, selector))
        rows.append(summarise_pair_strategy(records, wide_detail, "ワイド", label, selector))

    if not precomputed.empty:
        mapped = precomputed.rename(
            columns={
                "カテゴリ": "券種",
                "組み合わせ": "買い方",
                "購入R": "対象レース数",
                "平均点数": "平均購入点数",
                "的中R": "的中数",
                "的中率": "的中率",
                "平均配当": "平均配当",
                "投資": "購入点数",
                "払戻": "払戻",
                "ROI": "回収率",
            }
        ).copy()
        mapped["分析元"] = "既存組み合わせ集計"
        mapped["購入点数"] = pd.to_numeric(mapped["購入点数"], errors="coerce") / 100
        mapped["収支"] = pd.to_numeric(mapped["払戻"], errors="coerce") - pd.to_numeric(precomputed.get("投資"), errors="coerce")
        mapped = mapped[["券種", "買い方", "対象レース数", "的中数", "的中率", "回収率", "購入点数", "平均購入点数", "平均配当", "払戻", "収支", "分析元"]]
        rows.extend(mapped.to_dict("records"))

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    for column in ["対象レース数", "的中数", "購入点数"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    for column in ["的中率", "回収率", "平均購入点数", "平均配当", "払戻", "収支"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").round(1)
    return result.sort_values(["回収率", "的中率", "対象レース数"], ascending=[False, False, False]).reset_index(drop=True)


def summarise_horse_strategy(ticket_type: str, label: str, selected: pd.DataFrame, payoff_col: str) -> dict[str, Any]:
    grouped = selected.groupby("race_id")
    race_count = grouped.ngroups
    points = int(len(selected))
    payout = float(selected[payoff_col].sum())
    hits = int(grouped[payoff_col].sum().gt(0).sum())
    stake = points * 100
    hit_payouts = grouped[payoff_col].sum()
    hit_payouts = hit_payouts[hit_payouts.gt(0)]
    return {
        "券種": ticket_type,
        "買い方": label,
        "対象レース数": race_count,
        "的中数": hits,
        "的中率": pct(hits, race_count),
        "回収率": pct(payout, stake),
        "購入点数": points,
        "平均購入点数": round(points / race_count, 1) if race_count else 0,
        "平均配当": round(float(hit_payouts.mean()), 1) if not hit_payouts.empty else 0.0,
        "払戻": payout,
        "収支": payout - stake,
        "分析元": "馬単位払戻",
    }


def summarise_pair_strategy(
    records: pd.DataFrame,
    detail: pd.DataFrame,
    ticket_type: str,
    label: str,
    selector,
) -> dict[str, Any]:
    payout_lookup = {(str(row.race_id), row.pair_key): row.払戻 for row in detail.itertuples(index=False)}
    race_rows = []
    for race_id, group in records.groupby("race_id"):
        combos = selector(group)
        if not combos:
            continue
        payout = sum(float(payout_lookup.get((str(race_id), combo), 0)) for combo in combos)
        race_rows.append({"race_id": race_id, "points": len(combos), "payout": payout, "hit": payout > 0})
    return summarise_ticket_races(ticket_type, label, race_rows, "実払戻detail")


def summarise_ticket_races(ticket_type: str, label: str, race_rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    race_count = len(race_rows)
    points = sum(int(row["points"]) for row in race_rows)
    payout = sum(float(row["payout"]) for row in race_rows)
    hits = sum(1 for row in race_rows if row["hit"])
    stake = points * 100
    hit_payouts = [float(row["payout"]) for row in race_rows if row["payout"]]
    return {
        "券種": ticket_type,
        "買い方": label,
        "対象レース数": race_count,
        "的中数": hits,
        "的中率": pct(hits, race_count),
        "回収率": pct(payout, stake),
        "購入点数": points,
        "平均購入点数": round(points / race_count, 1) if race_count else 0,
        "平均配当": round(sum(hit_payouts) / len(hit_payouts), 1) if hit_payouts else 0.0,
        "払戻": payout,
        "収支": payout - stake,
        "分析元": source,
    }


def build_feature_summary(records: pd.DataFrame) -> pd.DataFrame:
    frame = records.copy()
    frame["AI順位帯"] = frame["ai_rank_eval"].map(rank_band)
    frame["AI点帯"] = pd.to_numeric(frame.get("AI点"), errors="coerce").map(score_band)
    frame["能力評価値帯"] = frame["ability_value_eval"].map(ability_value_band)
    frame["オッズ帯"] = pd.to_numeric(frame.get("単勝オッズ"), errors="coerce").map(odds_band)
    frame["人気帯"] = pd.to_numeric(frame.get("人気"), errors="coerce").map(popularity_band)
    frame["距離指数帯"] = pd.to_numeric(frame.get("距離指数"), errors="coerce").map(index_band)
    frame["コース指数帯"] = pd.to_numeric(frame.get("コース指数"), errors="coerce").map(index_band)
    frame["★有無"] = pd.to_numeric(frame.get("★最高指数"), errors="coerce").notna().map({True: "★あり", False: "★なし"})
    frame["継続騎乗"] = frame.get("_jockey_changed").map(lambda v: "継続" if str(v).lower() in {"false", "0", "nan", "none", ""} else "乗り替わり")
    features = [
        ("AI順位", "AI順位帯"),
        ("AI点", "AI点帯"),
        ("能力評価値", "能力評価値帯"),
        ("SS/A/B/C/Z", "display_group"),
        ("オッズ", "オッズ帯"),
        ("人気", "人気帯"),
        ("距離指数", "距離指数帯"),
        ("コース指数", "コース指数帯"),
        ("★有無", "★有無"),
        ("状態", "勢い"),
        ("クラス", "クラス変動"),
        ("脚質", "脚質"),
        ("継続騎乗", "継続騎乗"),
    ]
    rows: list[dict[str, Any]] = []
    for feature, column in features:
        if column not in frame.columns:
            continue
        for value, group in frame.groupby(column, dropna=False):
            label = clean_text(value) or "未取得"
            rows.append(feature_stats(feature, label, group))
    return pd.DataFrame(rows).sort_values(["単勝回収率", "複勝回収率", "対象数"], ascending=[False, False, False]).reset_index(drop=True)


def feature_stats(feature: str, value: str, group: pd.DataFrame) -> dict[str, Any]:
    n = len(group)
    wins = int(group["finish_eval"].eq(1).sum())
    places = int(group["finish_eval"].between(1, 3).sum())
    win_pay = float(group["win_payoff_eval"].sum())
    place_pay = float(group["place_payoff_eval"].sum())
    stake = n * 100
    return {
        "項目": feature,
        "条件": value,
        "対象数": n,
        "勝率": pct(wins, n),
        "複勝率": pct(places, n),
        "単勝回収率": pct(win_pay, stake),
        "複勝回収率": pct(place_pay, stake),
        "単勝払戻": win_pay,
        "複勝払戻": place_pay,
    }


def build_condition_ranking(records: pd.DataFrame) -> pd.DataFrame:
    conditions = build_condition_masks(records)
    rows: list[dict[str, Any]] = []
    for (name1, mask1), (name2, mask2) in itertools.combinations(conditions.items(), 2):
        mask = mask1 & mask2
        group = records[mask].copy()
        if len(group) < 5:
            continue
        row = feature_stats("掛け合わせ", f"{name1} × {name2}", group)
        rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["単勝回収率", "複勝回収率", "対象数"], ascending=[False, False, False]).head(80).reset_index(drop=True)


def build_condition_masks(records: pd.DataFrame) -> dict[str, pd.Series]:
    ai_rank = records["ai_rank_eval"]
    ai_score = pd.to_numeric(records.get("AI点"), errors="coerce")
    ability = records["ability_value_eval"]
    odds = pd.to_numeric(records.get("単勝オッズ"), errors="coerce")
    popularity = pd.to_numeric(records.get("人気"), errors="coerce")
    distance = pd.to_numeric(records.get("距離指数"), errors="coerce")
    course = pd.to_numeric(records.get("コース指数"), errors="coerce")
    star = pd.to_numeric(records.get("★最高指数"), errors="coerce").notna()
    trend = records.get("勢い", pd.Series("", index=records.index)).astype(str)
    changed = records.get("_jockey_changed", pd.Series(False, index=records.index)).astype(str).str.lower().isin({"true", "1"})
    return {
        "AI1位": ai_rank.eq(1),
        "AI2位": ai_rank.eq(2),
        "AI3位": ai_rank.eq(3),
        "AI点90以上": ai_score.ge(90),
        "能力評価値80以上": ability.ge(80),
        "SS": records["display_group"].eq("SS"),
        "A": records["display_group"].eq("A"),
        "B": records["display_group"].eq("B"),
        "C": records["display_group"].eq("C"),
        "オッズ8〜20倍": odds.ge(8) & odds.lt(20),
        "オッズ10倍以上": odds.ge(10),
        "人気5番人気以下": popularity.ge(5),
        "距離指数60以上": distance.ge(60),
        "コース指数60以上": course.ge(60),
        "★あり": star,
        "上昇/能力上位": trend.str.contains("上昇|能力上位|近走", na=False),
        "継続騎乗": ~changed,
        "乗り替わり": changed,
        "クラス降級": records.get("クラス変動", pd.Series("", index=records.index)).astype(str).str.contains("降", na=False),
    }


def cross_group_pairs(df: pd.DataFrame, left_groups: list[str], right_groups: list[str]) -> set[tuple[str, str]]:
    left = df[df["display_group"].isin(left_groups)]["馬番"].map(horse_no).tolist()
    right = df[df["display_group"].isin(right_groups)]["馬番"].map(horse_no).tolist()
    return {pair_key((a, b)) for a in left for b in right if a and b and a != b}


def ai_rank_pair(df: pd.DataFrame, rank1: int, rank2: int) -> set[tuple[str, str]]:
    left = df[df["ai_rank_eval"].eq(rank1)]["馬番"].map(horse_no).tolist()
    right = df[df["ai_rank_eval"].eq(rank2)]["馬番"].map(horse_no).tolist()
    return {pair_key((a, b)) for a in left for b in right if a and b and a != b}


def display_mark(row: pd.Series) -> str:
    mark = clean_text(first_value(row, ["表示印", "display_mark", "mark", "最終印", "印"]))
    if mark in {"◎", "○", "▲", "△"}:
        return mark
    if mark in {"✓", "✔", "☆"}:
        return "✓"
    return ""


def display_group(row: pd.Series) -> str:
    group = clean_text(first_value(row, ["グループ", "display_group"]))
    if group in {"SS", "A", "B", "C", "Z"}:
        return group
    mark = display_mark(row)
    if mark == "◎":
        return "SS"
    if mark in {"○", "▲"}:
        return "A"
    if mark == "△":
        return "B"
    if mark == "✓":
        return "C"
    return "Z"


def first_value(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row.index and not is_missing(row[name]):
            return row[name]
    return None


def first_number(row: pd.Series, names: list[str]) -> float | None:
    return to_float(first_value(row, names))


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return clean_text(value).lower() in {"", "-", "—", "nan", "none", "null"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", " ", str(value)).strip()


def horse_no(value: Any) -> str:
    text = clean_text(value)
    match = re.search(r"\d+", text)
    return match.group() if match else ""


def pair_key(values: Iterable[Any]) -> tuple[str, str]:
    numbers = sorted(horse_no(value) for value in values if horse_no(value))
    return tuple(numbers[:2]) if len(numbers) >= 2 else ("", "")


def to_float(value: Any) -> float | None:
    if is_missing(value):
        return None
    text = clean_text(value).replace(",", "").replace("倍", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def pct(numerator: float, denominator: float) -> float:
    return round(float(numerator) / float(denominator) * 100, 1) if denominator else 0.0


def rank_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value <= 3:
        return f"AI{int(value)}位"
    if value <= 6:
        return "AI4〜6位"
    return "AI7位以下"


def score_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value >= 95:
        return "95以上"
    if value >= 90:
        return "90〜94.9"
    if value >= 85:
        return "85〜89.9"
    if value >= 80:
        return "80〜84.9"
    return "80未満"


def ability_value_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value >= 85:
        return "85以上"
    if value >= 80:
        return "80〜84.9"
    if value >= 75:
        return "75〜79.9"
    if value >= 70:
        return "70〜74.9"
    return "70未満"


def odds_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value < 3:
        return "3倍未満"
    if value < 5:
        return "3〜4.9倍"
    if value < 10:
        return "5〜9.9倍"
    if value < 20:
        return "10〜19.9倍"
    return "20倍以上"


def popularity_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value <= 3:
        return f"{int(value)}人気"
    if value <= 6:
        return "4〜6人気"
    return "7人気以下"


def index_band(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "未取得"
    if value >= 80:
        return "80以上"
    if value >= 70:
        return "70〜79"
    if value >= 60:
        return "60〜69"
    return "60未満"


def build_markdown_report(
    ticket_summary: pd.DataFrame,
    feature_summary: pd.DataFrame,
    condition_ranking: pd.DataFrame,
    records: pd.DataFrame,
) -> str:
    race_count = records["race_id"].nunique()
    horse_count = len(records)
    lines = [
        "# JRA買い方検証レポート",
        "",
        f"- 対象: 保存済み中央競馬データ",
        f"- 対象レース数: {race_count}",
        f"- 対象頭数: {horse_count}",
        "- 注意: AI点・印・Parser・予想ロジックは変更していません。",
        "",
        "## 買い方別 上位",
        dataframe_to_markdown(ticket_summary.head(25)),
        "",
        "## 特徴量別 期待値 上位",
        dataframe_to_markdown(feature_summary.head(40)),
        "",
        "## 条件掛け合わせ 上位",
        dataframe_to_markdown(condition_ranking.head(40)) if not condition_ranking.empty else "該当なし",
        "",
        "## おすすめ候補",
    ]
    for ticket in ("単勝", "複勝", "馬連", "ワイド", "馬単", "3連複F 2→2→5", "3連単F 2→2→5"):
        subset = ticket_summary[ticket_summary["券種"].astype(str).eq(ticket)]
        if subset.empty:
            continue
        row = subset.iloc[0]
        lines.append(f"- {ticket}: {row['買い方']} / 回収率 {row['回収率']}% / 的中率 {row['的中率']}%")
    weak = feature_summary[(feature_summary["対象数"].ge(10)) & (feature_summary["単勝回収率"].lt(50))].head(10)
    lines.extend(["", "## 買わない方が良い条件候補", dataframe_to_markdown(weak) if not weak.empty else "該当なし"])
    return "\n".join(lines)


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "該当なし"
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(escape_markdown_cell(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        rows.append("| " + " | ".join(escape_markdown_cell(row[column]) for column in columns) + " |")
    return "\n".join(rows)


def escape_markdown_cell(value: Any) -> str:
    text = clean_text(value)
    return text.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
