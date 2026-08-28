from __future__ import annotations

import itertools
import json
import math
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from .value_support import attach_value_signals
from .v1_logic import V1_MARKS, build_v1_evaluations, v1_sort_key


CHECK_MARK = "✔︎"
MARK_ORDER = ["◎", "○", "▲", "☆", "△", CHECK_MARK]
MARK_SET_SPECS: dict[str, list[str]] = {
    "◎○": ["◎", "○"],
    "◎○▲": ["◎", "○", "▲"],
    "◎○▲☆": ["◎", "○", "▲", "☆"],
    "◎○▲☆△": ["◎", "○", "▲", "☆", "△"],
}
PAIR_BET_TYPES = {"quinella": "馬連", "wide": "ワイド"}
TRIO_BET_TYPES = {"trio": "三連複"}


@dataclass(frozen=True)
class RaceSource:
    race_id: str
    race_type: str
    race_dir: Path
    result_path: Path


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp932", "euc-jp"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "<html" in text.lower() or "netkeiba" in text.lower():
            return text
    return data.decode("utf-8", errors="replace")


def normalize_horse_no(value: Any) -> str:
    number = to_int(value)
    return str(number) if number is not None else ""


def normalize_mark(value: Any) -> str:
    text = clean_text(value)
    if text in MARK_ORDER:
        return text
    if text in {"✓", "✔"}:
        return CHECK_MARK
    return ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def pct(numerator: float, denominator: float) -> float:
    return round(float(numerator) / float(denominator) * 100, 1) if denominator else 0.0


def first_value(row: dict[str, Any] | pd.Series, keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row:
            value = row[key]
            if clean_text(value) != "":
                return value
    return None


def first_column(df: pd.DataFrame, *needles: str) -> str | None:
    for col in df.columns:
        name = re.sub(r"\s+", "", str(col))
        if all(needle in name for needle in needles):
            return str(col)
    return None


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            " ".join(str(part) for part in col if str(part) and not str(part).startswith("Unnamed")).strip()
            for col in out.columns
        ]
    else:
        out.columns = [str(col) for col in out.columns]
    return out


def parse_result_html(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    return parse_result_html_text(read_text(path))


def parse_result_html_text(html: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    tables = [flatten_columns(table) for table in pd.read_html(StringIO(html), flavor="lxml")]
    finish = parse_finish_table(tables)
    payouts = parse_payoff_tables(tables)
    return finish, payouts


def parse_finish_table(tables: list[pd.DataFrame]) -> dict[str, dict[str, Any]]:
    result_table = find_finish_table(tables)
    if result_table is None:
        return {}
    rank_col = first_column(result_table, "着", "順") or first_column(result_table, "着") or str(result_table.columns[0])
    horse_col = first_column(result_table, "馬", "番")
    name_col = first_column(result_table, "馬名")
    pop_col = first_column(result_table, "人", "気")
    odds_col = first_column(result_table, "単勝", "オッズ")
    finish: dict[str, dict[str, Any]] = {}
    if horse_col is None:
        return finish
    for _, row in result_table.iterrows():
        no = normalize_horse_no(row.get(horse_col))
        rank = to_int(row.get(rank_col))
        if not no or rank is None:
            continue
        finish[no] = {
            "finish": rank,
            "result_name": clean_text(row.get(name_col)) if name_col else "",
            "result_popularity": to_int(row.get(pop_col)) if pop_col else None,
            "result_odds": to_float(row.get(odds_col)) if odds_col else None,
        }
    return finish


def find_finish_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    for table in tables:
        cols = " ".join(str(col) for col in table.columns)
        compact = re.sub(r"\s+", "", cols)
        if "着順" in compact and "馬番" in compact:
            return table
    return None


def empty_payouts() -> dict[str, Any]:
    return {
        "win": {},
        "place": {},
        "wide": {},
        "quinella": {},
        "exacta": {},
        "trio": {},
        "trifecta": {},
    }


def parse_payoff_tables(tables: list[pd.DataFrame]) -> dict[str, Any]:
    payouts = empty_payouts()
    for table in tables:
        if table.shape[1] < 3:
            continue
        for _, row in table.iterrows():
            kind = clean_text(row.iloc[0])
            combo = clean_text(row.iloc[1])
            amount = clean_text(row.iloc[2])
            nums = re.findall(r"\d+", combo)
            pays = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", amount)]
            if not kind or not nums or not pays:
                continue
            if "単勝" in kind:
                payouts["win"][nums[0]] = pays[0]
            elif "複勝" in kind:
                for no, pay in zip(nums, pays):
                    payouts["place"][no] = pay
            elif "ワイド" in kind:
                for pair, pay in zip(pairwise_numbers(nums), pays):
                    payouts["wide"][pair_key(pair)] = pay
            elif "馬連" in kind:
                payouts["quinella"][pair_key(nums[:2])] = pays[0]
            elif "馬単" in kind:
                payouts["exacta"][tuple(nums[:2])] = pays[0]
            elif "3連複" in kind or "三連複" in kind:
                payouts["trio"][trio_key(nums[:3])] = pays[0]
            elif "3連単" in kind or "三連単" in kind:
                payouts["trifecta"][tuple(nums[:3])] = pays[0]
    return payouts


def pairwise_numbers(nums: list[str]) -> list[tuple[str, str]]:
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def pair_key(nums: Iterable[Any]) -> tuple[str, str]:
    values = [normalize_horse_no(value) for value in nums]
    values = [value for value in values if value]
    return tuple(sorted(values, key=lambda item: int(item)))[:2]  # type: ignore[return-value]


def trio_key(nums: Iterable[Any]) -> tuple[str, str, str]:
    values = [normalize_horse_no(value) for value in nums]
    values = [value for value in values if value]
    return tuple(sorted(values, key=lambda item: int(item)))[:3]  # type: ignore[return-value]


def prediction_html_files(race_dir: Path, race_type: str) -> tuple[dict[str, str], dict[str, str]]:
    kinds = ["newspaper", "speed", "style", "oikiri"] if race_type == "jra" else ["newspaper", "speed", "style"]
    html_files: dict[str, str] = {}
    file_names: dict[str, str] = {}
    for kind in kinds:
        path = find_kind_file(race_dir, kind)
        if path is None:
            continue
        html_files[kind] = read_text(path)
        file_names[kind] = path.name
    return html_files, file_names


def find_kind_file(race_dir: Path, kind: str) -> Path | None:
    candidates = sorted(race_dir.glob(f"*_{kind}.html"))
    if candidates:
        return candidates[0]
    for path in sorted(race_dir.glob("*.html")):
        if path.stem.endswith(kind):
            return path
    return None


def discover_race_sources(roots: Iterable[Path], race_type: str) -> tuple[list[RaceSource], dict[str, Any]]:
    sources: list[RaceSource] = []
    seen: set[str] = set()
    duplicates = 0
    missing_prediction_pages = 0
    for root in roots:
        if root is None or not root.exists():
            continue
        for result_path in sorted(root.rglob("*_result.html")):
            race_dir = result_path.parent
            race_id = result_path.stem.removesuffix("_result")
            if not re.fullmatch(r"\d{10,12}", race_id):
                race_id = race_dir.name
            if race_id in seen:
                duplicates += 1
                continue
            html_files, _ = prediction_html_files(race_dir, race_type)
            if not html_files:
                missing_prediction_pages += 1
                continue
            seen.add(race_id)
            sources.append(RaceSource(race_id=race_id, race_type=race_type, race_dir=race_dir, result_path=result_path))
    meta = {
        "race_type": race_type,
        "roots": [str(root) for root in roots if root is not None],
        "discovered_races": len(sources),
        "duplicate_result_files_skipped": duplicates,
        "missing_prediction_pages": missing_prediction_pages,
    }
    return sources, meta


def extract_prediction_rows(result: Any, race_id: str, race_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    table = getattr(result, "overall_table", None)
    if table is None or getattr(table, "empty", True):
        return [], {}
    frame = table.copy()
    if "ai_rank" not in frame.columns:
        score_col = find_existing_column(frame, ["AI点", "normalized_ai_score"])
        if score_col:
            frame["ai_rank"] = pd.to_numeric(frame[score_col], errors="coerce").rank(method="first", ascending=False)
    if "ability_rank_for_backtest" not in frame.columns:
        ability_col = find_existing_column(frame, ["能力評価値", "ability_display_score", "raw_score"])
        if ability_col:
            frame["ability_rank_for_backtest"] = pd.to_numeric(frame[ability_col], errors="coerce").rank(method="first", ascending=False)
    rows: list[dict[str, Any]] = []
    race_info = dict(getattr(result, "race_info", {}) or {})
    for _, row in frame.iterrows():
        raw = row.to_dict()
        no = normalize_horse_no(first_value(raw, ["馬番", "horse_no", "鬥ｬ逡ｪ"]))
        if not no:
            continue
        rows.append(
            {
                "race_id": race_id,
                "date": infer_date(race_id, race_info),
                "race_type": race_type,
                "venue": infer_venue(result, race_info),
                "race_name": clean_text(getattr(result, "race_name", "")) or clean_text(race_info.get("race_name")),
                "distance": to_int(first_value(race_info, ["distance", "距離"])) or to_int(first_value(raw, ["距離"])),
                "surface": clean_text(first_value(race_info, ["surface", "course_type", "芝ダ"])) or clean_text(first_value(raw, ["芝ダ"])),
                "field_size": len(frame),
                "horse_no": no,
                "horse_name": clean_text(first_value(raw, ["馬名", "horse_name"])),
                "mark": normalize_mark(first_value(raw, ["表示印", "display_mark", "最終印", "original_mark", "旧印", "old_final_mark", "印", "mark"])),
                "raw_mark": clean_text(first_value(raw, ["表示印", "display_mark", "最終印", "original_mark", "旧印", "old_final_mark", "印", "mark"])),
                "ability_band": clean_text(first_value(raw, ["能力帯", "ability_band", "ability_rank"])),
                "ability_rank": to_int(first_value(raw, ["能力順位", "ability_rank_for_backtest"])),
                "ability_value": to_float(first_value(raw, ["能力評価値", "ability_display_score", "raw_score", "_raw_score"])),
                "ai_current_rank": to_int(first_value(raw, ["AI今回評価順位", "ai_rank", "AI順位"])),
                "ai_score": to_float(first_value(raw, ["AI点", "normalized_ai_score", "ai_score"])),
                "odds": to_float(first_value(raw, ["オッズ", "単勝オッズ", "odds"])),
                "popularity": to_int(first_value(raw, ["人気", "単勝人気", "popularity"])),
                "recent_runs": first_value(raw, ["_past_runs", "recent_runs", "past_runs", "recent3_runs"]),
                "running_style": clean_text(first_value(raw, ["脚質", "running_style", "style"])),
                "corner4_group": clean_text(first_value(raw, ["corner4_group", "position_corner4_group_market"])),
                "corner4_position": clean_text(
                    first_value(
                        raw,
                        [
                            "position_corner4_label_market",
                            "_estimated_position_corner4_label",
                            "corner4_position_label",
                            "corner4_evaluation",
                            "4角評価",
                        ],
                    )
                ),
                "training": clean_text(first_value(raw, ["training_display", "training_market", "training_short", "training_grade", "調教評価"])),
                "stable_comment": clean_text(first_value(raw, ["stable_comment_display", "stable_comment_market", "stable_comment", "厩舎コメント"])),
                "jockey_change": clean_text(first_value(raw, ["騎手継続/乗替", "jockey_change", "jockey_change_market"])),
                "weight_diff": to_float(first_value(raw, ["_load_weight_change", "weight_diff", "斤量差", "斤量増減"])),
                "interval": clean_text(first_value(raw, ["race_interval_market", "レース間隔", "間隔"])),
                "current_weight": to_float(first_value(raw, ["_current_load_weight", "斤量", "weight"])),
                "previous_weight": to_float(first_value(raw, ["_previous_load_weight", "previous_weight"])),
                "current_jockey": clean_text(first_value(raw, ["_current_jockey", "騎手", "jockey"])),
                "previous_jockey": clean_text(first_value(raw, ["_previous_jockey", "previous_jockey"])),
                "jockey_changed": first_value(raw, ["_jockey_changed", "jockey_changed"]),
                "star_max_venue": clean_text(first_value(raw, ["star_max_venue"])),
                "star_max_distance": to_int(first_value(raw, ["star_max_distance"])),
                "star_max_surface": clean_text(first_value(raw, ["star_max_surface"])),
                "star_max_turn": clean_text(first_value(raw, ["star_max_turn"])),
                "star_match_level": clean_text(first_value(raw, ["star_match_level"])),
            }
        )
    return rows, race_info


def infer_venue(result: Any, race_info: dict[str, Any]) -> str:
    for key in ["venue", "racecourse", "競馬場", "場所", "開催場"]:
        text = clean_text(race_info.get(key))
        if text:
            return text
    race_name = clean_text(getattr(result, "race_name", ""))
    match = re.search(r"(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉|門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀)", race_name)
    return match.group(1) if match else ""


def infer_date(race_id: str, race_info: dict[str, Any]) -> str:
    for key in ["date", "race_date", "開催日", "日付"]:
        text = clean_text(race_info.get(key))
        if text:
            return text
    race_text = clean_text(race_id)
    if len(race_text) >= 8 and race_text[:4].isdigit():
        return race_text[:8]
    return ""


def find_existing_column(frame: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def attach_results(prediction_rows: list[dict[str, Any]], finish: dict[str, dict[str, Any]], payouts: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in prediction_rows:
        out = dict(row)
        no = out.get("horse_no", "")
        result_row = finish.get(no, {})
        out["finish"] = result_row.get("finish")
        out["result_popularity"] = result_row.get("result_popularity")
        out["result_odds"] = result_row.get("result_odds")
        out["win_payoff"] = payouts.get("win", {}).get(no, 0)
        out["place_payoff"] = payouts.get("place", {}).get(no, 0)
        rows.append(out)
    return rows


def race_exclusion_reason(
    prediction_rows: list[dict[str, Any]],
    finish: dict[str, dict[str, Any]],
    payouts: dict[str, Any],
) -> str:
    if not prediction_rows:
        return "印データなし"
    if not any(clean_text(row.get("mark")) for row in prediction_rows):
        return "印データなし"
    if not finish:
        return "着順なし"
    if not any((payouts or {}).get(kind) for kind in ("win", "place", "wide", "quinella", "trio")):
        return "払戻なし"
    return ""


def attach_value_signals_to_records(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return records
    groups: list[pd.DataFrame] = []
    for _race_id, group in records.groupby("race_id", sort=False):
        race_type = clean_text(group.iloc[0].get("race_type")) or "jra"
        enriched = attach_value_signals(group.to_dict(orient="records"), race_type)
        groups.append(pd.DataFrame(enriched))
    return pd.concat(groups, ignore_index=True) if groups else records.copy()


def attach_v1_predictions_to_records(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return records
    groups: list[pd.DataFrame] = []
    for _race_id, group in records.groupby("race_id", sort=False):
        race_type = clean_text(group.iloc[0].get("race_type")) or "jra"
        evaluated = build_v1_evaluations(group.to_dict(orient="records"), race_type)
        by_no = {normalize_horse_no(row.get("horse_no")): row for row in evaluated.get("rows", [])}
        updated = group.copy()
        for column in [
            "v1_mark",
            "v1_order",
            "v1_score",
            "v1_role",
            "v1_base_score",
            "v1_base_rank",
            "v1_final_score",
            "v1_final_rank",
            "v1_final_mark",
            "v1_final_role",
            "v1_final_reason",
            "baseline_current_evaluation_rank",
            "baseline_mark",
            "v1_reproducibility",
            "v1_reproducibility_reason",
            "v1_pace_eval",
            "v1_pace_reason",
            "v1_state_eval",
            "v1_state_reason",
            "v1_special_distance",
        ]:
            if column not in updated.columns:
                updated[column] = None
        for index, row in updated.iterrows():
            v1_row = by_no.get(normalize_horse_no(row.get("horse_no")))
            if not v1_row:
                continue
            for column in [
                "v1_mark",
                "v1_order",
                "v1_score",
                "v1_role",
                "v1_base_score",
                "v1_base_rank",
                "v1_final_score",
                "v1_final_rank",
                "v1_final_mark",
                "v1_final_role",
                "v1_final_reason",
                "baseline_current_evaluation_rank",
                "baseline_mark",
                "v1_reproducibility",
                "v1_reproducibility_reason",
                "v1_pace_eval",
                "v1_pace_reason",
                "v1_state_eval",
                "v1_state_reason",
                "v1_special_distance",
            ]:
                updated.at[index, column] = v1_row.get(column)
        groups.append(updated)
    return pd.concat(groups, ignore_index=True) if groups else records.copy()


def evaluate_mark_singles(records: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for mark in MARK_ORDER:
        targets = records[records["mark"].eq(mark)].copy()
        for bet_type, payoff_col in [("単勝", "win_payoff"), ("複勝", "place_payoff")]:
            stake = len(targets) * 100
            payout_values = pd.to_numeric(targets.get(payoff_col, pd.Series(dtype=float)), errors="coerce").fillna(0)
            hits = int((payout_values > 0).sum())
            payout = float(payout_values.sum())
            dependency = payout_dependency_metrics(payout_values, stake)
            rows.append(
                {
                    "印": mark,
                    "券種": bet_type,
                    "対象レース数": int(targets["race_id"].nunique()) if not targets.empty else 0,
                    "購入数": int(len(targets)),
                    "購入額": int(stake),
                    "的中数": hits,
                    "的中率": pct(hits, len(targets)),
                    "払戻額": int(payout),
                    "回収率": pct(payout, stake),
                    "平均払戻": round(payout / hits, 1) if hits else 0.0,
                    "最大払戻": int(payout_values.max()) if len(payout_values) else 0,
                    "最大払戻除外回収率": dependency["top1_excluded_roi"],
                    "上位2件除外回収率": dependency["top2_excluded_roi"],
                    "最大払戻依存度": dependency["max_payout_dependency"],
                    "購入参考": classify_reference(len(targets), hits, pct(payout, stake)),
                }
            )
    return pd.DataFrame(rows)


def evaluate_mark_summary(records: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if records is None or records.empty:
        return pd.DataFrame()
    for mark in MARK_ORDER:
        targets = records[records["mark"].eq(mark)].copy()
        rows.append(mark_performance_row(mark, targets))
    return pd.DataFrame(rows)


def mark_performance_row(label: str, targets: pd.DataFrame) -> dict[str, Any]:
    finish = pd.to_numeric(targets.get("finish", pd.Series(dtype=float)), errors="coerce")
    win_pay = pd.to_numeric(targets.get("win_payoff", pd.Series(dtype=float)), errors="coerce").fillna(0)
    place_pay = pd.to_numeric(targets.get("place_payoff", pd.Series(dtype=float)), errors="coerce").fillna(0)
    popularity = effective_numeric_series(targets, ["popularity", "result_popularity"])
    odds = effective_numeric_series(targets, ["odds", "result_odds"])
    count = int(len(targets))
    win_stake = count * 100
    place_stake = count * 100
    return {
        "印": label,
        "出走数": count,
        "1着数": int((finish == 1).sum()),
        "2着数": int((finish == 2).sum()),
        "3着数": int((finish == 3).sum()),
        "勝率": pct((finish == 1).sum(), count),
        "連対率": pct((finish <= 2).sum(), count),
        "複勝率": pct((finish <= 3).sum(), count),
        "平均人気": round(float(popularity.mean()), 2) if popularity.notna().any() else None,
        "平均単勝オッズ": round(float(odds.mean()), 2) if odds.notna().any() else None,
        "単勝購入額": win_stake,
        "単勝払戻": int(win_pay.sum()),
        "単勝回収率": pct(win_pay.sum(), win_stake),
        "複勝購入額": place_stake,
        "複勝払戻": int(place_pay.sum()),
        "複勝回収率": pct(place_pay.sum(), place_stake),
    }


def effective_numeric_series(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    result = pd.Series([None] * len(frame), index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        result = result.where(result.notna(), values)
    return pd.to_numeric(result, errors="coerce")


def evaluate_group_capture(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for label, marks in [("◎○▲", ["◎", "○", "▲"]), ("◎○▲☆", ["◎", "○", "▲", "☆"])]:
        rows.append(group_capture_row(records, label, marks))
    rows.append(unmarked_capture_row(records))
    return pd.DataFrame(rows)


def group_capture_row(records: pd.DataFrame, label: str, marks: list[str]) -> dict[str, Any]:
    race_count = 0
    winner_hits = 0
    top3_hits = 0
    top3_two_or_more = 0
    top3_all = 0
    for _race_id, group in records.groupby("race_id", sort=True):
        race_count += 1
        marked = group[group["mark"].isin(marks)]
        finishes = pd.to_numeric(marked.get("finish", pd.Series(dtype=float)), errors="coerce")
        if (finishes == 1).any():
            winner_hits += 1
        top3_count = int((finishes <= 3).sum())
        if top3_count > 0:
            top3_hits += 1
        if top3_count >= 2:
            top3_two_or_more += 1
        if top3_count >= len(marks) and len(marked) >= len(marks):
            top3_all += 1
    return {
        "対象": label,
        "レース数": race_count,
        "1着捕捉レース数": winner_hits,
        "1着捕捉率": pct(winner_hits, race_count),
        "3着内捕捉レース数": top3_hits,
        "3着内捕捉率": pct(top3_hits, race_count),
        "2頭以上馬券内レース数": top3_two_or_more,
        "2頭以上馬券内率": pct(top3_two_or_more, race_count),
        "全頭馬券内レース数": top3_all,
        "全頭馬券内率": pct(top3_all, race_count),
    }


def unmarked_capture_row(records: pd.DataFrame) -> dict[str, Any]:
    unmarked = records[~records["mark"].isin(MARK_ORDER)].copy()
    finish = pd.to_numeric(unmarked.get("finish", pd.Series(dtype=float)), errors="coerce")
    race_count = int(records["race_id"].nunique()) if "race_id" in records else 0
    unmarked_winner_races = int(unmarked[finish == 1]["race_id"].nunique()) if not unmarked.empty else 0
    return {
        "対象": "無印",
        "レース数": race_count,
        "出走数": int(len(unmarked)),
        "勝率": pct((finish == 1).sum(), len(unmarked)),
        "複勝率": pct((finish <= 3).sum(), len(unmarked)),
        "無印1着レース数": unmarked_winner_races,
        "無印1着レース割合": pct(unmarked_winner_races, race_count),
    }


def evaluate_check_mark(records: pd.DataFrame) -> pd.DataFrame:
    targets = records[records["mark"].eq(CHECK_MARK)].copy() if records is not None and not records.empty else pd.DataFrame()
    row = mark_performance_row(CHECK_MARK, targets)
    finish = pd.to_numeric(targets.get("finish", pd.Series(dtype=float)), errors="coerce")
    place_targets = targets[finish <= 3].copy()
    place_popularity = effective_numeric_series(place_targets, ["popularity", "result_popularity"])
    top_marks = {"◎", "○", "▲"}
    check_place_races = set(place_targets.get("race_id", pd.Series(dtype=str)).astype(str).tolist())
    with_top_mark = 0
    for race_id in check_place_races:
        group = records[records["race_id"].astype(str).eq(str(race_id))]
        top_mark_finish = pd.to_numeric(group[group["mark"].isin(top_marks)].get("finish", pd.Series(dtype=float)), errors="coerce")
        if (top_mark_finish <= 3).any():
            with_top_mark += 1
    row.update(
        {
            "✔︎出現数": row["出走数"],
            "✔︎が3着以内に入った際の平均人気": round(float(place_popularity.mean()), 2) if place_popularity.notna().any() else None,
            "✔︎が◎○▲と同時に馬券内へ入った割合": pct(with_top_mark, len(check_place_races)),
        }
    )
    return pd.DataFrame([row])


def compare_late_marks(records: pd.DataFrame) -> pd.DataFrame:
    summary = evaluate_mark_summary(records)
    if summary.empty or "印" not in summary.columns:
        return pd.DataFrame()
    return summary[summary["印"].isin(["☆", "△", CHECK_MARK])].reset_index(drop=True)


def evaluate_mark_summary_for_column(records: pd.DataFrame, mark_column: str, *, label: str) -> pd.DataFrame:
    if records is None or records.empty or mark_column not in records.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for mark in V1_MARKS:
        targets = records[records[mark_column].fillna("").astype(str).eq(mark)].copy()
        row = mark_performance_row(mark, targets)
        rows.append({"ロジック": label, **row})
    return pd.DataFrame(rows)


def evaluate_baseline_vs_v1(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return pd.DataFrame()
    rows = [
        logic_comparison_row(records, "Baseline v0", "mark"),
        logic_comparison_row(records, "New v1", "v1_mark"),
    ]
    return pd.DataFrame(rows)


def logic_comparison_row(records: pd.DataFrame, label: str, mark_column: str) -> dict[str, Any]:
    if mark_column not in records.columns:
        return {"ロジック": label}
    honmei = records[records[mark_column].fillna("").astype(str).eq("◎")].copy()
    honmei_row = mark_performance_row("◎", honmei)
    capture = capture_metrics_for_marks(records, mark_column, ["◎", "○", "▲"])
    star = mark_performance_row("☆", records[records[mark_column].fillna("").astype(str).eq("☆")].copy())
    check = mark_performance_row(CHECK_MARK, records[records[mark_column].fillna("").astype(str).eq(CHECK_MARK)].copy())
    return {
        "ロジック": label,
        "◎出走数": honmei_row.get("出走数", 0),
        "◎勝率": honmei_row.get("勝率", 0.0),
        "◎連対率": honmei_row.get("連対率", 0.0),
        "◎複勝率": honmei_row.get("複勝率", 0.0),
        "◎○▲1着捕捉率": capture.get("1着捕捉率", 0.0),
        "◎○▲3着内1頭以上率": capture.get("3着内捕捉率", 0.0),
        "◎○▲2頭以上馬券内率": capture.get("2頭以上馬券内率", 0.0),
        "◎○▲3頭完全捕捉率": capture.get("全頭馬券内率", 0.0),
        "☆出走数": star.get("出走数", 0),
        "☆勝率": star.get("勝率", 0.0),
        "☆複勝率": star.get("複勝率", 0.0),
        "✔︎出走数": check.get("出走数", 0),
        "✔︎勝率": check.get("勝率", 0.0),
        "✔︎複勝率": check.get("複勝率", 0.0),
    }


def capture_metrics_for_marks(records: pd.DataFrame, mark_column: str, marks: list[str]) -> dict[str, Any]:
    race_count = 0
    winner_hits = 0
    top3_hits = 0
    top3_two_or_more = 0
    top3_all = 0
    for _race_id, group in records.groupby("race_id", sort=False):
        race_count += 1
        marked = group[group[mark_column].fillna("").astype(str).isin(marks)]
        finishes = pd.to_numeric(marked.get("finish", pd.Series(dtype=float)), errors="coerce")
        if (finishes == 1).any():
            winner_hits += 1
        top3_count = int((finishes <= 3).sum())
        if top3_count > 0:
            top3_hits += 1
        if top3_count >= 2:
            top3_two_or_more += 1
        if top3_count >= len(marks) and len(marked) >= len(marks):
            top3_all += 1
    return {
        "レース数": race_count,
        "1着捕捉率": pct(winner_hits, race_count),
        "3着内捕捉率": pct(top3_hits, race_count),
        "2頭以上馬券内率": pct(top3_two_or_more, race_count),
        "全頭馬券内率": pct(top3_all, race_count),
    }


def evaluate_recommendation_summary(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if records is None or records.empty:
        return pd.DataFrame(), pd.DataFrame()
    summary_rows: list[dict[str, Any]] = []
    race_rows: list[dict[str, Any]] = []
    for size in (3, 4, 5):
        race_count = 0
        winner_hits = 0
        top3_total = 0
        top3_all = 0
        for race_id, group in records.groupby("race_id", sort=False):
            ordered = v1_ordered_group(group)
            if ordered.empty:
                continue
            selected = ordered.head(size).copy()
            race_count += 1
            finishes = pd.to_numeric(selected.get("finish", pd.Series(dtype=float)), errors="coerce")
            top3_count = int((finishes <= 3).sum())
            if (finishes == 1).any():
                winner_hits += 1
            top3_total += top3_count
            if top3_count >= 3:
                top3_all += 1
            race_rows.append(
                {
                    "race_id": race_id,
                    "推奨頭数": size,
                    "race_type": clean_text(group.iloc[0].get("race_type")),
                    "venue": clean_text(group.iloc[0].get("venue")),
                    "勝馬捕捉": bool((finishes == 1).any()),
                    "3着内捕捉頭数": top3_count,
                    "3着内3頭完全捕捉": top3_count >= 3,
                    "推奨馬": " / ".join(
                        f"{clean_text(row.get('v1_mark'))}{normalize_horse_no(row.get('horse_no'))} {clean_text(row.get('horse_name'))}"
                        for _, row in selected.iterrows()
                    ),
                }
            )
        summary_rows.append(
            {
                "推奨頭数": size,
                "レース数": race_count,
                "勝馬捕捉率": pct(winner_hits, race_count),
                "3着内平均捕捉頭数": round(top3_total / race_count, 2) if race_count else 0.0,
                "3着内3頭完全捕捉率": pct(top3_all, race_count),
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(race_rows)


def v1_ordered_group(group: pd.DataFrame) -> pd.DataFrame:
    work = group.copy()
    if "v1_order" not in work.columns:
        return pd.DataFrame()
    work["_v1_order_sort"] = pd.to_numeric(work.get("v1_order"), errors="coerce").fillna(99)
    work["_v1_score_sort"] = pd.to_numeric(work.get("v1_score"), errors="coerce").fillna(-9999)
    work["_horse_no_sort"] = pd.to_numeric(work.get("horse_no"), errors="coerce").fillna(999)
    return work.sort_values(["_v1_order_sort", "_v1_score_sort", "_horse_no_sort"], ascending=[True, False, True])


def evaluate_v1_role_summary(records: pd.DataFrame) -> pd.DataFrame:
    return evaluate_grouped_performance(records, "v1_role", "役割")


def evaluate_v1_reproducibility_summary(records: pd.DataFrame) -> pd.DataFrame:
    return evaluate_grouped_performance(records, "v1_reproducibility", "再現性")


def evaluate_grouped_performance(records: pd.DataFrame, column: str, label_name: str) -> pd.DataFrame:
    if records is None or records.empty or column not in records.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for label, group in records.groupby(records[column].fillna("—").astype(str), sort=True):
        row = mark_performance_row(clean_text(label) or "—", group.copy())
        row.pop("印", None)
        rows.append({label_name: clean_text(label) or "—", **row})
    return pd.DataFrame(rows)


def evaluate_v1_check_mark_deep_dive(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty or "v1_mark" not in records.columns:
        return pd.DataFrame()
    check = records[records["v1_mark"].fillna("").astype(str).eq(CHECK_MARK)].copy()
    scenarios: list[tuple[str, pd.DataFrame]] = [
        ("✔︎全体", check),
        ("✔︎＋再現性S", check[check.get("v1_reproducibility", pd.Series(dtype=str)).fillna("").astype(str).eq("S")]),
        ("✔︎＋再現性A以上", check[check.get("v1_reproducibility", pd.Series(dtype=str)).fillna("").astype(str).isin(["S", "A"])]),
        ("✔︎＋展開○", check[check.get("v1_pace_eval", pd.Series(dtype=str)).fillna("").astype(str).eq("○")]),
        ("✔︎＋特殊距離実績", check[check.get("v1_special_distance", pd.Series(dtype=bool)).fillna(False).astype(bool)]),
        (
            "✔︎＋能力順位4〜8位",
            check[
                pd.to_numeric(check.get("ability_rank", pd.Series(dtype=float)), errors="coerce").between(4, 8, inclusive="both")
            ],
        ),
        (
            "✔︎＋再現性A以上＋展開○",
            check[
                check.get("v1_reproducibility", pd.Series(dtype=str)).fillna("").astype(str).isin(["S", "A"])
                & check.get("v1_pace_eval", pd.Series(dtype=str)).fillna("").astype(str).eq("○")
            ],
        ),
    ]
    rows: list[dict[str, Any]] = []
    for label, frame in scenarios:
        row = mark_performance_row(label, frame.copy())
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_value_singles(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty or "value_signal" not in records.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    targets_all = records[records["value_signal"].astype(bool)].copy()
    for label, targets in [("妙味あり", targets_all), *[(f"妙味あり＋{mark}", targets_all[targets_all["mark"].eq(mark)]) for mark in MARK_ORDER]]:
        if targets.empty:
            rows.append(empty_value_summary_row(label))
            continue
        win_values = pd.to_numeric(targets.get("win_payoff", pd.Series(dtype=float)), errors="coerce").fillna(0)
        place_values = pd.to_numeric(targets.get("place_payoff", pd.Series(dtype=float)), errors="coerce").fillna(0)
        stake = len(targets) * 100
        win_hits = int((win_values > 0).sum())
        place_hits = int((place_values > 0).sum())
        win_dependency = payout_dependency_metrics(win_values, stake)
        place_dependency = payout_dependency_metrics(place_values, stake)
        rows.append(
            {
                "対象": label,
                "対象レース数": int(targets["race_id"].nunique()),
                "購入数": int(len(targets)),
                "単勝的中数": win_hits,
                "単勝的中率": pct(win_hits, len(targets)),
                "単勝購入額": int(stake),
                "単勝払戻額": int(win_values.sum()),
                "単勝回収率": pct(win_values.sum(), stake),
                "単勝最大払戻": int(win_values.max()) if len(win_values) else 0,
                "単勝最大払戻除外回収率": win_dependency["top1_excluded_roi"],
                "単勝上位2件除外回収率": win_dependency["top2_excluded_roi"],
                "複勝的中数": place_hits,
                "複勝的中率": pct(place_hits, len(targets)),
                "複勝購入額": int(stake),
                "複勝払戻額": int(place_values.sum()),
                "複勝回収率": pct(place_values.sum(), stake),
                "複勝最大払戻": int(place_values.max()) if len(place_values) else 0,
                "複勝最大払戻除外回収率": place_dependency["top1_excluded_roi"],
                "複勝上位2件除外回収率": place_dependency["top2_excluded_roi"],
                "参考区分": classify_reference(len(targets), max(win_hits, place_hits), max(pct(win_values.sum(), stake), pct(place_values.sum(), stake))),
            }
        )
    return pd.DataFrame(rows)


def empty_value_summary_row(label: str) -> dict[str, Any]:
    return {
        "対象": label,
        "対象レース数": 0,
        "購入数": 0,
        "単勝的中数": 0,
        "単勝的中率": 0.0,
        "単勝購入額": 0,
        "単勝払戻額": 0,
        "単勝回収率": 0.0,
        "単勝最大払戻": 0,
        "単勝最大払戻除外回収率": 0.0,
        "単勝上位2件除外回収率": 0.0,
        "複勝的中数": 0,
        "複勝的中率": 0.0,
        "複勝購入額": 0,
        "複勝払戻額": 0,
        "複勝回収率": 0.0,
        "複勝最大払戻": 0,
        "複勝最大払戻除外回収率": 0.0,
        "複勝上位2件除外回収率": 0.0,
        "参考区分": "サンプル不足",
    }


def payout_dependency_metrics(payout_values: pd.Series, stake: float) -> dict[str, float]:
    values = pd.to_numeric(payout_values, errors="coerce").fillna(0).sort_values(ascending=False)
    total = float(values.sum())
    top1 = float(values.iloc[0]) if len(values) else 0.0
    top2 = float(values.iloc[:2].sum()) if len(values) else 0.0
    return {
        "top1_excluded_roi": pct(total - top1, stake),
        "top2_excluded_roi": pct(total - top2, stake),
        "max_payout_dependency": round(top1 / total * 100, 1) if total else 0.0,
    }


def evaluate_box_strategies(records: pd.DataFrame, payouts_by_race: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, marks in MARK_SET_SPECS.items():
        for bet_type, bet_label in {**PAIR_BET_TYPES, **TRIO_BET_TYPES}.items():
            if bet_type == "trio" and len(marks) < 3:
                continue
            race_rows = []
            for race_id, group in records.groupby("race_id", sort=True):
                horses = marked_horses(group, marks)
                size = 3 if bet_type == "trio" else 2
                tickets = list(itertools.combinations(horses, size))
                if not tickets:
                    continue
                payout = payout_for_tickets(tickets, bet_type, payouts_by_race.get(str(race_id), {}))
                race_rows.append({"race_id": str(race_id), "points": len(tickets), "stake": len(tickets) * 100, "payout": payout})
            total_points = sum(row["points"] for row in race_rows)
            stake = sum(row["stake"] for row in race_rows)
            payout = sum(row["payout"] for row in race_rows)
            hits = sum(1 for row in race_rows if row["payout"] > 0)
            dependency = payout_dependency_metrics(pd.Series([row["payout"] for row in race_rows]), stake)
            rows.append(
                {
                    "対象印": label,
                    "券種": bet_label,
                    "レース数": len(race_rows),
                    "総点数": total_points,
                    "総購入額": stake,
                    "的中レース数": hits,
                    "的中率": pct(hits, len(race_rows)),
                    "総払戻額": int(payout),
                    "回収率": pct(payout, stake),
                    "平均点数": round(total_points / len(race_rows), 2) if race_rows else 0.0,
                    "最大払戻": int(max([row["payout"] for row in race_rows] or [0])),
                    "最大払戻除外回収率": dependency["top1_excluded_roi"],
                    "上位2件除外回収率": dependency["top2_excluded_roi"],
                    "最大払戻依存度": dependency["max_payout_dependency"],
                    "購入参考": classify_reference(len(race_rows), hits, pct(payout, stake)),
                }
            )
    return pd.DataFrame(rows)


def evaluate_bet_strategies(records: pd.DataFrame, payouts_by_race: dict[str, dict[str, Any]]) -> pd.DataFrame:
    specs: list[tuple[str, str, Callable[[dict[str, str]], list[tuple[str, ...]]]]] = [
        ("◎ 単勝", "win", lambda marks: one_horse_ticket(marks, "◎")),
        ("◎ 複勝", "place", lambda marks: one_horse_ticket(marks, "◎")),
        ("◎-○ 馬連", "quinella", lambda marks: pair_flow_tickets(marks, "◎", ["○"])),
        ("◎-○▲ 馬連流し", "quinella", lambda marks: pair_flow_tickets(marks, "◎", ["○", "▲"])),
        ("◎○▲ 馬連BOX", "quinella", lambda marks: box_tickets(marks, ["◎", "○", "▲"], 2)),
        ("◎-○ ワイド", "wide", lambda marks: pair_flow_tickets(marks, "◎", ["○"])),
        ("◎-○▲ ワイド流し", "wide", lambda marks: pair_flow_tickets(marks, "◎", ["○", "▲"])),
        ("◎○▲ ワイドBOX", "wide", lambda marks: box_tickets(marks, ["◎", "○", "▲"], 2)),
        ("◎軸 ○▲ 3連複", "trio", lambda marks: trio_axis_tickets(marks, "◎", ["○", "▲"])),
        ("◎○▲ 3連複BOX", "trio", lambda marks: box_tickets(marks, ["◎", "○", "▲"], 3)),
        ("◎軸 ○▲☆ ワイド", "wide", lambda marks: pair_flow_tickets(marks, "◎", ["○", "▲", "☆"])),
        ("◎軸 ○▲☆✔︎ ワイド", "wide", lambda marks: pair_flow_tickets(marks, "◎", ["○", "▲", "☆", CHECK_MARK])),
        ("◎軸 ○▲☆ 3連複", "trio", lambda marks: trio_axis_tickets(marks, "◎", ["○", "▲", "☆"])),
        ("◎軸 ○▲☆✔︎ 3連複", "trio", lambda marks: trio_axis_tickets(marks, "◎", ["○", "▲", "☆", CHECK_MARK])),
    ]
    rows: list[dict[str, Any]] = []
    for name, bet_type, ticket_builder in specs:
        race_rows: list[dict[str, Any]] = []
        for race_id, group in records.groupby("race_id", sort=True):
            mark_map = first_mark_map(group)
            tickets = unique_tickets(ticket_builder(mark_map), bet_type)
            if not tickets:
                continue
            stake = len(tickets) * 100
            payout = payout_for_tickets(tickets, bet_type, payouts_by_race.get(str(race_id), {}))
            race_rows.append({"race_id": str(race_id), "points": len(tickets), "stake": stake, "payout": payout})
        rows.append(bet_summary_row(name, race_rows))
    return pd.DataFrame(rows)


def bet_summary_row(name: str, race_rows: list[dict[str, Any]]) -> dict[str, Any]:
    race_count = len(race_rows)
    total_points = sum(row["points"] for row in race_rows)
    stake = sum(row["stake"] for row in race_rows)
    payout = sum(row["payout"] for row in race_rows)
    hits = sum(1 for row in race_rows if row["payout"] > 0)
    profit_races = sum(1 for row in race_rows if row["payout"] > row["stake"])
    max_payout = max([row["payout"] for row in race_rows] or [0])
    return {
        "買い方": name,
        "対象レース数": race_count,
        "的中レース数": hits,
        "的中率": pct(hits, race_count),
        "購入点数": total_points,
        "総購入額": stake,
        "総払戻額": int(payout),
        "回収率": pct(payout, stake),
        "収支": int(payout - stake),
        "1レース平均購入額": round(stake / race_count, 1) if race_count else 0.0,
        "最大払戻": int(max_payout),
        "最大連敗": max_losing_streak(race_rows),
        "平均的中払戻": round(payout / hits, 1) if hits else 0.0,
        "収支プラスレース率": pct(profit_races, race_count),
    }


def first_mark_map(group: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for mark in MARK_ORDER:
        horses = marked_horses(group, [mark])
        if horses:
            result[mark] = horses[0]
    return result


def one_horse_ticket(marks: dict[str, str], mark: str) -> list[tuple[str, ...]]:
    no = marks.get(mark)
    return [(no,)] if no else []


def pair_flow_tickets(marks: dict[str, str], axis: str, opponents: list[str]) -> list[tuple[str, ...]]:
    axis_no = marks.get(axis)
    if not axis_no:
        return []
    return [(axis_no, marks[mark]) for mark in opponents if marks.get(mark) and marks[mark] != axis_no]


def trio_axis_tickets(marks: dict[str, str], axis: str, opponents: list[str]) -> list[tuple[str, ...]]:
    axis_no = marks.get(axis)
    if not axis_no:
        return []
    opponent_numbers = [marks[mark] for mark in opponents if marks.get(mark) and marks[mark] != axis_no]
    return [(axis_no, left, right) for left, right in itertools.combinations(opponent_numbers, 2)]


def box_tickets(marks: dict[str, str], mark_order: list[str], size: int) -> list[tuple[str, ...]]:
    numbers: list[str] = []
    for mark in mark_order:
        no = marks.get(mark)
        if no and no not in numbers:
            numbers.append(no)
    if len(numbers) < size:
        return []
    return list(itertools.combinations(numbers, size))


def unique_tickets(tickets: list[tuple[str, ...]], bet_type: str) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[tuple[str, ...]] = []
    for ticket in tickets:
        if bet_type in {"quinella", "wide"}:
            key = pair_key(ticket)
        elif bet_type == "trio":
            key = trio_key(ticket)
        else:
            key = tuple(ticket)
        if len(key) != len(ticket) or key in seen:
            continue
        seen.add(key)
        unique.append(tuple(ticket))
    return unique


def max_losing_streak(race_rows: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for row in race_rows:
        if row["payout"] > 0:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def marked_horses(group: pd.DataFrame, marks: list[str]) -> list[str]:
    horses: list[str] = []
    for mark in marks:
        subset = group[group["mark"].eq(mark)].copy()
        sort_cols = [column for column in ["ai_current_rank", "horse_no"] if column in subset.columns]
        if sort_cols:
            subset = subset.sort_values(sort_cols, na_position="last")
        if subset.empty:
            continue
        no = str(subset.iloc[0].get("horse_no", ""))
        if no and no not in horses:
            horses.append(no)
    return horses


def payout_for_tickets(tickets: Iterable[tuple[str, ...]], bet_type: str, payouts: dict[str, Any]) -> float:
    total = 0.0
    payout_map = payouts.get(bet_type, {})
    for ticket in tickets:
        if bet_type in {"win", "place"}:
            key = normalize_horse_no(ticket[0]) if ticket else ""
        elif bet_type in {"wide", "quinella"}:
            key = pair_key(ticket)
        elif bet_type == "trio":
            key = trio_key(ticket)
        else:
            key = tuple(str(value) for value in ticket)
        total += float(payout_map.get(key, 0) or 0)
    return total


def build_condition_summary(records: pd.DataFrame) -> pd.DataFrame:
    honmei = records[records["mark"].eq("◎")].copy()
    if honmei.empty:
        return pd.DataFrame()
    honmei["距離帯"] = honmei["distance"].apply(distance_band)
    honmei["頭数帯"] = honmei["field_size"].apply(field_size_band)
    honmei["◎単勝オッズ帯"] = honmei["odds"].apply(odds_band)
    if "◎○能力値差" in honmei.columns:
        honmei["◎○能力値差帯"] = honmei["◎○能力値差"].apply(diff_band)
    if "◎○今回評価差" in honmei.columns:
        honmei["◎○今回評価差帯"] = honmei["◎○今回評価差"].apply(diff_band)
    condition_columns = [
        ("JRA/NAR", "race_type"),
        ("競馬場", "venue"),
        ("芝/ダート", "surface"),
        ("距離帯", "距離帯"),
        ("頭数帯", "頭数帯"),
        ("◎の能力帯", "ability_band"),
        ("◎の能力順位", "ability_rank"),
        ("◎のAI今回評価順位", "ai_current_rank"),
        ("◎の単勝オッズ帯", "◎単勝オッズ帯"),
        ("◎と○の能力値差", "◎○能力値差帯"),
        ("◎と○の今回評価差", "◎○今回評価差帯"),
    ]
    rows: list[dict[str, Any]] = []
    for label, column in condition_columns:
        if column not in honmei.columns:
            continue
        for value, group in honmei.groupby(column, dropna=False):
            if clean_text(value) == "":
                value = "欠損"
            win_pay = pd.to_numeric(group["win_payoff"], errors="coerce").fillna(0)
            place_pay = pd.to_numeric(group["place_payoff"], errors="coerce").fillna(0)
            stake = len(group) * 100
            rows.append(
                {
                    "条件": label,
                    "値": value,
                    "サンプル数": len(group),
                    "対象レース数": group["race_id"].nunique(),
                    "単勝的中率": pct((win_pay > 0).sum(), len(group)),
                    "単勝回収率": pct(win_pay.sum(), stake),
                    "複勝的中率": pct((place_pay > 0).sum(), len(group)),
                    "複勝回収率": pct(place_pay.sum(), stake),
                    "参考区分": "参考値" if len(group) < 30 or group["race_id"].nunique() < 20 else "集計対象",
                }
            )
    return pd.DataFrame(rows)


def build_mark_by_popularity(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return pd.DataFrame()
    frame = records.copy()
    frame["人気帯"] = effective_numeric_series(frame, ["popularity", "result_popularity"]).apply(popularity_band)
    rows: list[dict[str, Any]] = []
    for (mark, band), group in frame[frame["mark"].isin(MARK_ORDER)].groupby(["mark", "人気帯"], dropna=False, sort=True):
        row = mark_performance_row(str(mark), group)
        row["人気帯"] = band
        rows.append(row)
    return pd.DataFrame(rows)


def build_simple_group_summary(records: pd.DataFrame, group_column: str, label_column: str) -> pd.DataFrame:
    if records is None or records.empty or group_column not in records.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for value, group in records.groupby(group_column, dropna=False, sort=True):
        finish = pd.to_numeric(group.get("finish", pd.Series(dtype=float)), errors="coerce")
        honmei = group[group["mark"].eq("◎")]
        honmei_finish = pd.to_numeric(honmei.get("finish", pd.Series(dtype=float)), errors="coerce")
        rows.append(
            {
                label_column: clean_text(value) or "欠損",
                "レース数": int(group["race_id"].nunique()),
                "出走数": int(len(group)),
                "全馬勝率": pct((finish == 1).sum(), len(group)),
                "全馬複勝率": pct((finish <= 3).sum(), len(group)),
                "◎出走数": int(len(honmei)),
                "◎勝率": pct((honmei_finish == 1).sum(), len(honmei)),
                "◎複勝率": pct((honmei_finish <= 3).sum(), len(honmei)),
            }
        )
    return pd.DataFrame(rows)


def popularity_band(value: Any) -> str:
    popularity = to_int(value)
    if popularity is None:
        return "人気欠損"
    if popularity == 1:
        return "1番人気"
    if popularity <= 3:
        return "2〜3番人気"
    if popularity <= 6:
        return "4〜6番人気"
    return "7番人気以下"


def build_race_backtest(records: pd.DataFrame, payouts_by_race: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if records is None or records.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for race_id, group in records.groupby("race_id", sort=True):
        group = group.copy()
        payouts = payouts_by_race.get(str(race_id), {})
        base = group.iloc[0].to_dict()
        finish_order = finish_numbers(group)
        row: dict[str, Any] = {
            "race_id": race_id,
            "date": clean_text(base.get("date")),
            "venue": clean_text(base.get("venue")),
            "distance": base.get("distance"),
            "surface": clean_text(base.get("surface")),
            "race_name": clean_text(base.get("race_name")),
            "1着馬番": finish_order.get(1, ""),
            "2着馬番": finish_order.get(2, ""),
            "3着馬番": finish_order.get(3, ""),
        }
        for mark in MARK_ORDER:
            mark_row = first_mark_row(group, mark)
            prefix = mark
            row[f"{prefix}馬番"] = clean_text(mark_row.get("horse_no")) if mark_row else ""
            row[f"{prefix}馬名"] = clean_text(mark_row.get("horse_name")) if mark_row else ""
            row[f"{prefix}人気"] = effective_row_number(mark_row, ["popularity", "result_popularity"]) if mark_row else None
            row[f"{prefix}単勝オッズ"] = effective_row_number(mark_row, ["odds", "result_odds"]) if mark_row else None
            row[f"{prefix}着順"] = mark_row.get("finish") if mark_row else None
        mark_map = first_mark_map(group)
        row["◎単勝的中"] = payout_for_tickets(one_horse_ticket(mark_map, "◎"), "win", payouts) > 0
        row["◎複勝的中"] = payout_for_tickets(one_horse_ticket(mark_map, "◎"), "place", payouts) > 0
        row["◎○▲馬連BOX的中"] = payout_for_tickets(box_tickets(mark_map, ["◎", "○", "▲"], 2), "quinella", payouts) > 0
        row["◎○▲ワイドBOX的中"] = payout_for_tickets(box_tickets(mark_map, ["◎", "○", "▲"], 2), "wide", payouts) > 0
        row["◎○▲3連複的中"] = payout_for_tickets(box_tickets(mark_map, ["◎", "○", "▲"], 3), "trio", payouts) > 0
        rows.append(row)
    return pd.DataFrame(rows)


def finish_numbers(group: pd.DataFrame) -> dict[int, str]:
    result: dict[int, str] = {}
    for _, row in group.iterrows():
        finish = to_int(row.get("finish"))
        no = normalize_horse_no(row.get("horse_no"))
        if finish in {1, 2, 3} and finish not in result and no:
            result[finish] = no
    return result


def first_mark_row(group: pd.DataFrame, mark: str) -> dict[str, Any] | None:
    subset = group[group["mark"].eq(mark)].copy()
    if subset.empty:
        return None
    sort_cols = [column for column in ["ai_current_rank", "horse_no"] if column in subset.columns]
    if sort_cols:
        subset = subset.sort_values(sort_cols, na_position="last")
    return subset.iloc[0].to_dict()


def effective_row_number(row: dict[str, Any] | None, columns: list[str]) -> float | int | None:
    if not row:
        return None
    for column in columns:
        value = to_float(row.get(column))
        if value is not None:
            return int(value) if float(value).is_integer() else value
    return None


def distance_band(value: Any) -> str:
    distance = to_float(value)
    if distance is None:
        return "欠損"
    if distance < 1400:
        return "短距離"
    if distance < 1800:
        return "マイル前後"
    if distance < 2200:
        return "中距離"
    return "長距離"


def field_size_band(value: Any) -> str:
    size = to_int(value)
    if size is None:
        return "欠損"
    if size <= 8:
        return "少頭数"
    if size <= 12:
        return "中頭数"
    return "多頭数"


def odds_band(value: Any) -> str:
    odds = to_float(value)
    if odds is None:
        return "欠損"
    if odds < 2:
        return "2倍未満"
    if odds < 5:
        return "2〜5倍"
    if odds < 10:
        return "5〜10倍"
    if odds < 20:
        return "10〜20倍"
    return "20倍以上"


def diff_band(value: Any) -> str:
    diff = to_float(value)
    if diff is None:
        return "欠損"
    if diff < 0:
        return "○が上"
    if diff < 2:
        return "0〜2差"
    if diff < 5:
        return "2〜5差"
    if diff < 10:
        return "5〜10差"
    return "10差以上"


def classify_reference(sample_size: int, hits: int, roi: float) -> str:
    if sample_size < 30:
        return "サンプル不足"
    if roi >= 110 and hits >= 3:
        return "購入参考候補"
    if roi >= 80:
        return "参考"
    return "見送り参考"


def build_report_payload(
    records: pd.DataFrame,
    payouts_by_race: dict[str, dict[str, Any]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    records = ensure_records_frame(records)
    if records is not None and not records.empty and "value_signal" not in records.columns:
        records = attach_value_signals_to_records(records)
    if records is not None and not records.empty and "v1_mark" not in records.columns:
        records = attach_v1_predictions_to_records(records)
    mark_single_summary = evaluate_mark_singles(records)
    mark_summary = evaluate_mark_summary(records)
    box_summary = evaluate_box_strategies(records, payouts_by_race)
    bet_summary = evaluate_bet_strategies(records, payouts_by_race)
    condition_summary = build_condition_summary(records)
    value_summary = evaluate_value_singles(records)
    group_capture = evaluate_group_capture(records)
    check_mark_summary = evaluate_check_mark(records)
    late_mark_comparison = compare_late_marks(records)
    race_backtest = build_race_backtest(records, payouts_by_race)
    mark_by_popularity = build_mark_by_popularity(records)
    venue_summary = build_simple_group_summary(records, "venue", "競馬場")
    distance_summary = build_simple_group_summary(records, "distance", "距離")
    mark_summary_v1 = evaluate_mark_summary_for_column(records, "v1_mark", label="New v1")
    baseline_vs_v1_summary = evaluate_baseline_vs_v1(records)
    recommendation_summary, recommendation_races = evaluate_recommendation_summary(records)
    role_summary = evaluate_v1_role_summary(records)
    reproducibility_summary = evaluate_v1_reproducibility_summary(records)
    check_mark_v1_analysis = evaluate_v1_check_mark_deep_dive(records)
    return {
        "meta": meta,
        "mark_summary": mark_summary,
        "mark_single_summary": mark_single_summary,
        "box_summary": box_summary,
        "bet_summary": bet_summary,
        "condition_summary": condition_summary,
        "value_summary": value_summary,
        "group_capture": group_capture,
        "check_mark_summary": check_mark_summary,
        "late_mark_comparison": late_mark_comparison,
        "race_backtest": race_backtest,
        "mark_by_popularity": mark_by_popularity,
        "venue_summary": venue_summary,
        "distance_summary": distance_summary,
        "baseline_vs_v1_summary": baseline_vs_v1_summary,
        "recommendation_summary": recommendation_summary,
        "recommendation_races": recommendation_races,
        "mark_summary_v1": mark_summary_v1,
        "role_summary": role_summary,
        "reproducibility_summary": reproducibility_summary,
        "check_mark_v1_analysis": check_mark_v1_analysis,
    }


def ensure_records_frame(records: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "race_id",
        "date",
        "race_type",
        "venue",
        "race_name",
        "distance",
        "surface",
        "field_size",
        "horse_no",
        "horse_name",
        "mark",
        "raw_mark",
        "ability_band",
        "ability_rank",
        "ability_value",
        "ai_current_rank",
        "ai_score",
        "odds",
        "popularity",
        "finish",
        "result_popularity",
        "result_odds",
        "win_payoff",
        "place_payoff",
        "v1_mark",
        "v1_order",
        "v1_score",
        "v1_role",
        "v1_reproducibility",
        "v1_reproducibility_reason",
        "v1_pace_eval",
        "v1_state_eval",
    ]
    if records is None or records.empty:
        return pd.DataFrame(columns=columns)
    frame = records.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame


def write_outputs(payload: dict[str, Any], records: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    mark_summary = payload["mark_summary"]
    mark_single_summary = payload.get("mark_single_summary", pd.DataFrame())
    box_summary = payload["box_summary"]
    bet_summary = payload.get("bet_summary", pd.DataFrame())
    condition_summary = payload["condition_summary"]
    value_summary = payload.get("value_summary", pd.DataFrame())
    group_capture = payload.get("group_capture", pd.DataFrame())
    check_mark_summary = payload.get("check_mark_summary", pd.DataFrame())
    late_mark_comparison = payload.get("late_mark_comparison", pd.DataFrame())
    race_backtest = payload.get("race_backtest", pd.DataFrame())
    mark_by_popularity = payload.get("mark_by_popularity", pd.DataFrame())
    venue_summary = payload.get("venue_summary", pd.DataFrame())
    distance_summary = payload.get("distance_summary", pd.DataFrame())
    baseline_vs_v1_summary = payload.get("baseline_vs_v1_summary", pd.DataFrame())
    recommendation_summary = payload.get("recommendation_summary", pd.DataFrame())
    recommendation_races = payload.get("recommendation_races", pd.DataFrame())
    mark_summary_v1 = payload.get("mark_summary_v1", pd.DataFrame())
    role_summary = payload.get("role_summary", pd.DataFrame())
    reproducibility_summary = payload.get("reproducibility_summary", pd.DataFrame())
    check_mark_v1_analysis = payload.get("check_mark_v1_analysis", pd.DataFrame())
    paths = {
        "race_mark_details": out_dir / "race_mark_details.csv",
        "race_backtest": out_dir / "race_backtest.csv",
        "mark_summary": out_dir / "mark_summary.csv",
        "mark_single_summary": out_dir / "mark_single_summary.csv",
        "bet_summary": out_dir / "bet_summary.csv",
        "box_summary": out_dir / "box_summary.csv",
        "condition_summary": out_dir / "condition_summary.csv",
        "value_summary": out_dir / "value_signal_summary.csv",
        "group_capture": out_dir / "group_capture_summary.csv",
        "check_mark_summary": out_dir / "check_mark_summary.csv",
        "late_mark_comparison": out_dir / "late_mark_comparison.csv",
        "mark_by_popularity": out_dir / "mark_by_popularity.csv",
        "venue_summary": out_dir / "venue_summary.csv",
        "distance_summary": out_dir / "distance_summary.csv",
        "baseline_vs_v1_summary": out_dir / "baseline_vs_v1_summary.csv",
        "recommendation_summary": out_dir / "recommendation_summary.csv",
        "recommendation_races": out_dir / "recommendation_races.csv",
        "mark_summary_v1": out_dir / "mark_summary_v1.csv",
        "role_summary": out_dir / "role_summary.csv",
        "reproducibility_summary": out_dir / "reproducibility_summary.csv",
        "check_mark_v1_analysis": out_dir / "check_mark_v1_analysis.csv",
        "json": out_dir / "mark_betting_backtest_summary.json",
        "markdown": out_dir / "mark_betting_backtest_report.md",
    }
    records.to_csv(paths["race_mark_details"], index=False, encoding="utf-8-sig")
    race_backtest.to_csv(paths["race_backtest"], index=False, encoding="utf-8-sig")
    mark_summary.to_csv(paths["mark_summary"], index=False, encoding="utf-8-sig")
    mark_single_summary.to_csv(paths["mark_single_summary"], index=False, encoding="utf-8-sig")
    bet_summary.to_csv(paths["bet_summary"], index=False, encoding="utf-8-sig")
    box_summary.to_csv(paths["box_summary"], index=False, encoding="utf-8-sig")
    condition_summary.to_csv(paths["condition_summary"], index=False, encoding="utf-8-sig")
    value_summary.to_csv(paths["value_summary"], index=False, encoding="utf-8-sig")
    group_capture.to_csv(paths["group_capture"], index=False, encoding="utf-8-sig")
    check_mark_summary.to_csv(paths["check_mark_summary"], index=False, encoding="utf-8-sig")
    late_mark_comparison.to_csv(paths["late_mark_comparison"], index=False, encoding="utf-8-sig")
    mark_by_popularity.to_csv(paths["mark_by_popularity"], index=False, encoding="utf-8-sig")
    venue_summary.to_csv(paths["venue_summary"], index=False, encoding="utf-8-sig")
    distance_summary.to_csv(paths["distance_summary"], index=False, encoding="utf-8-sig")
    baseline_vs_v1_summary.to_csv(paths["baseline_vs_v1_summary"], index=False, encoding="utf-8-sig")
    recommendation_summary.to_csv(paths["recommendation_summary"], index=False, encoding="utf-8-sig")
    recommendation_races.to_csv(paths["recommendation_races"], index=False, encoding="utf-8-sig")
    mark_summary_v1.to_csv(paths["mark_summary_v1"], index=False, encoding="utf-8-sig")
    role_summary.to_csv(paths["role_summary"], index=False, encoding="utf-8-sig")
    reproducibility_summary.to_csv(paths["reproducibility_summary"], index=False, encoding="utf-8-sig")
    check_mark_v1_analysis.to_csv(paths["check_mark_v1_analysis"], index=False, encoding="utf-8-sig")
    json_payload = {
        "meta": payload["meta"],
        "mark_summary": mark_summary.to_dict(orient="records"),
        "mark_single_summary": mark_single_summary.to_dict(orient="records"),
        "bet_summary": bet_summary.to_dict(orient="records"),
        "box_summary": box_summary.to_dict(orient="records"),
        "condition_summary": condition_summary.to_dict(orient="records"),
        "value_summary": value_summary.to_dict(orient="records"),
        "group_capture": group_capture.to_dict(orient="records"),
        "check_mark_summary": check_mark_summary.to_dict(orient="records"),
        "late_mark_comparison": late_mark_comparison.to_dict(orient="records"),
        "race_backtest": race_backtest.to_dict(orient="records"),
        "mark_by_popularity": mark_by_popularity.to_dict(orient="records"),
        "venue_summary": venue_summary.to_dict(orient="records"),
        "distance_summary": distance_summary.to_dict(orient="records"),
        "baseline_vs_v1_summary": baseline_vs_v1_summary.to_dict(orient="records"),
        "recommendation_summary": recommendation_summary.to_dict(orient="records"),
        "recommendation_races": recommendation_races.to_dict(orient="records"),
        "mark_summary_v1": mark_summary_v1.to_dict(orient="records"),
        "role_summary": role_summary.to_dict(orient="records"),
        "reproducibility_summary": reproducibility_summary.to_dict(orient="records"),
        "check_mark_v1_analysis": check_mark_v1_analysis.to_dict(orient="records"),
    }
    paths["json"].write_text(json.dumps(json_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["markdown"].write_text(build_markdown_report(payload), encoding="utf-8")
    return paths


def add_honmei_maruta_difference_columns(records: pd.DataFrame) -> pd.DataFrame:
    if records is None or records.empty:
        return records
    frame = records.copy()
    frame["◎○能力値差"] = None
    frame["◎○今回評価差"] = None
    for race_id, group in frame.groupby("race_id", sort=False):
        honmei = group[group["mark"].eq("◎")]
        maru = group[group["mark"].eq("○")]
        if honmei.empty or maru.empty:
            continue
        honmei_row = honmei.sort_values(["ai_current_rank", "horse_no"], na_position="last").iloc[0]
        maru_row = maru.sort_values(["ai_current_rank", "horse_no"], na_position="last").iloc[0]
        ability_diff = numeric_diff(honmei_row.get("ability_value"), maru_row.get("ability_value"))
        ai_diff = numeric_diff(honmei_row.get("ai_score"), maru_row.get("ai_score"))
        mask = frame["race_id"].astype(str).eq(str(race_id))
        frame.loc[mask, "◎○能力値差"] = ability_diff
        frame.loc[mask, "◎○今回評価差"] = ai_diff
    return frame


def numeric_diff(left: Any, right: Any) -> float | None:
    left_number = to_float(left)
    right_number = to_float(right)
    if left_number is None or right_number is None:
        return None
    return round(left_number - right_number, 3)


def build_markdown_report(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    lines = [
        "# 印・馬券バックテストレポート",
        "",
        "現行の予想ロジックを変更せず、保存済みHTMLから予想を再生成して結果HTMLと照合した検証です。",
        "結果HTMLは予想生成後の照合にのみ使用し、予想入力からは除外しています。",
        "",
        "## データ監査",
        "",
        f"- 総レース数: {meta.get('attempted_races', meta.get('total_discovered_races', 0))}R",
        f"- 検証可能レース数: {meta.get('usable_races', 0)}R",
        f"- 除外レース数: {meta.get('excluded_races', 0)}R",
        f"- 除外理由: {meta.get('excluded_reasons', {})}",
        f"- JRA: {meta.get('jra_races', 0)}R",
        f"- NAR: {meta.get('nar_races', 0)}R",
        f"- 対象馬数: {meta.get('horse_count', 0)}頭",
        f"- 予想エラー: {meta.get('prediction_error_count', 0)}件",
        f"- 結果HTMLは予想生成入力から除外: {meta.get('future_info_isolated', True)}",
        "",
        "## 印別成績",
        "",
        markdown_table(payload["mark_summary"]),
        "",
        "## Baseline v0 vs New v1",
        "",
        markdown_table(payload.get("baseline_vs_v1_summary", pd.DataFrame())),
        "",
        "## v1 推奨3/4/5頭",
        "",
        markdown_table(payload.get("recommendation_summary", pd.DataFrame())),
        "",
        "## v1 印別成績",
        "",
        markdown_table(payload.get("mark_summary_v1", pd.DataFrame())),
        "",
        "## v1 役割別",
        "",
        markdown_table(payload.get("role_summary", pd.DataFrame())),
        "",
        "## v1 再現性別",
        "",
        markdown_table(payload.get("reproducibility_summary", pd.DataFrame())),
        "",
        "## v1 ✔︎ 深掘り",
        "",
        markdown_table(payload.get("check_mark_v1_analysis", pd.DataFrame())),
        "",
        "## 印別 単勝・複勝",
        "",
        markdown_table(payload.get("mark_single_summary", pd.DataFrame())),
        "",
        "## 上位印捕捉・無印",
        "",
        markdown_table(payload.get("group_capture", pd.DataFrame())),
        "",
        "## ✔︎ 個別",
        "",
        markdown_table(payload.get("check_mark_summary", pd.DataFrame())),
        "",
        "## ☆ / △ / ✔︎ 比較",
        "",
        markdown_table(payload.get("late_mark_comparison", pd.DataFrame())),
        "",
        "## 馬券シミュレーション",
        "",
        markdown_table(payload.get("bet_summary", pd.DataFrame())),
        "",
        "## BOX",
        "",
        markdown_table(payload["box_summary"]),
        "",
        "## 妙味あり 単勝・複勝",
        "",
        markdown_table(payload.get("value_summary", pd.DataFrame())),
        "",
        "## 条件別（◎）",
        "",
        markdown_table(payload["condition_summary"].head(80)),
        "",
        "## 人気帯別",
        "",
        markdown_table(payload.get("mark_by_popularity", pd.DataFrame()).head(80)),
        "",
        "## 注意",
        "",
        "- 現行表示で穴系の第6印が `✓/✔` の場合、バックテスト上は依頼対象の `✔︎` として正規化しています。元の表示値は `race_mark_details.csv` の `raw_mark` に保持しています。",
        "- `妙味あり` は印とは別の表示補助です。能力帯・順位・印・材料・判定時オッズから結果前に判定し、印やAI点へは反映していません。",
        "- 回収率が高い方式でも、サンプル不足の場合は正式推奨ではなく参考値です。",
        "- 最大払戻除外回収率は、1件の高配当に依存していないかを見るための監査値です。",
        "- New v1 は同じ保存済み予想材料から作った比較用派生評価です。Baseline v0の保存印・AI点・能力評価・研究買いロジックは変更していません。",
    ]
    return "\n".join(lines) + "\n"


def markdown_table(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "_データなし_"
    show = frame.copy()
    columns = list(show.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in show.iterrows():
        values = [clean_text(row.get(column)).replace("|", "/") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)
