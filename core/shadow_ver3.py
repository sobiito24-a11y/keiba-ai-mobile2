from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .mark_backtest import normalize_mark, parse_result_html, to_float, to_int
from .v1_logic import (
    build_v1_evaluations,
    corner4_group,
    finish_in_top3,
    finish_is_win,
    normalize_surface,
    normalize_turn,
    pace_evaluation,
    recent_runs,
    state_evaluation,
    venue_key,
    venue_turn,
)


CHECK_MARK = "✔︎"
BASELINE_MARK_ORDER = {"◎": 0, "○": 1, "▲": 2, "☆": 3, "△": 4, CHECK_MARK: 5, "✓": 5, "": 9}
REPRO_BONUS_NAR = {"S": 5.0, "A": 3.5, "B": 1.0, "C": 0.0, "—": 0.0, "": 0.0}
REPRO_BONUS_JRA = {"S": 3.0, "A": 2.0, "B": 0.8, "C": 0.2, "—": 0.0, "": 0.0}
STATE_BONUS_JRA = {"A": 2.0, "B": 0.7, "C": -1.0, "—": 0.0, "": 0.0}
PACE_BONUS = {"○": 0.5, "△": 0.0, "×": -0.5, "—": 0.0, "": 0.0}


@dataclass(frozen=True)
class ShadowRace:
    label: str
    race_id: str
    race_type: str
    race_info: dict[str, Any]
    rows: list[dict[str, Any]]
    result_path: Path


def load_keiba_races(paths: Sequence[str | Path], *, result_root: str | Path | None = None) -> tuple[list[ShadowRace], dict[str, Any]]:
    result_index = build_result_index(result_root)
    races: list[ShadowRace] = []
    missing_results: list[str] = []
    for path_value in paths:
        path = Path(path_value)
        if not path.exists():
            missing_results.append(f"{path}: file not found")
            continue
        label = path.stem.replace("_all_venues", "")
        snapshot = _read_snapshot(path)
        for race in snapshot.get("races", []) or []:
            race_id = clean_text(race.get("race_id"))
            if not race_id:
                continue
            result_path = choose_result_path(result_index.get(race_id, []), label)
            if result_path is None:
                missing_results.append(f"{label}:{race_id}: result html not found")
                continue
            rows = rows_from_snapshot_race(race)
            if not rows:
                missing_results.append(f"{label}:{race_id}: prediction rows not found")
                continue
            race_info = race_info_from_snapshot(race)
            races.append(
                ShadowRace(
                    label=label,
                    race_id=race_id,
                    race_type=clean_text(race.get("race_mode")).lower() or infer_race_type(race_id),
                    race_info=race_info,
                    rows=rows,
                    result_path=result_path,
                )
            )
    return races, {"loaded_races": len(races), "missing_results": missing_results}


def build_result_index(result_root: str | Path | None = None) -> dict[str, list[Path]]:
    roots = [Path(result_root)] if result_root else [Path(r"C:\Users\28011\Documents\Codex\Keiba_AI_Data")]
    index: dict[str, list[Path]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*_result.html"):
            race_id = path.stem.removesuffix("_result")
            if race_id:
                index.setdefault(race_id, []).append(path)
    return index


def choose_result_path(paths: Sequence[Path], label: str) -> Path | None:
    if not paths:
        return None
    date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", label)
    date_key = "".join(date_match.groups()) if date_match else ""
    ordered = sorted(paths, key=lambda path: str(path))
    if date_key:
        same_date = [path for path in ordered if date_key in str(path)]
        if same_date:
            ordered = same_date
    return ordered[-1]


def rows_from_snapshot_race(race: Mapping[str, Any]) -> list[dict[str, Any]]:
    detailed = _table_records(((race.get("prediction_result") or {}).get("overall_table") or {}))
    by_no: dict[str, dict[str, Any]] = {}
    for row in detailed:
        no = normalize_horse_no(first(row, "馬番", "horse_no", "horse_number", "number"))
        if no:
            by_no[no] = dict(row)
    for simple in race.get("horses", []) or []:
        if not isinstance(simple, Mapping):
            continue
        no = normalize_horse_no(first(simple, "horse_no", "horse_number", "馬番", "number"))
        if not no:
            continue
        merged = by_no.get(no, {}).copy()
        for key, value in simple.items():
            if clean_text(merged.get(key)) == "":
                merged[key] = value
            merged[f"snapshot_{key}"] = value
        by_no[no] = merged
    rows: list[dict[str, Any]] = []
    race_info = race_info_from_snapshot(race)
    for no in sorted(by_no, key=lambda item: to_int(item) or 999):
        row = by_no[no]
        row["race_id"] = clean_text(race.get("race_id"))
        row["race_type"] = clean_text(race.get("race_mode")).lower() or infer_race_type(clean_text(race.get("race_id")))
        row["venue"] = race_info.get("venue")
        row["distance"] = race_info.get("distance")
        row["surface"] = race_info.get("surface")
        row["turn"] = race_info.get("turn")
        row["horse_no"] = no
        row["horse_name"] = clean_text(first(row, "horse_name", "馬名", "snapshot_horse_name", "name"))
        row["mark"] = normalize_mark(first(row, "mark", "表示印", "old_final_mark", "snapshot_mark"))
        rows.append(row)
    return rows


def race_info_from_snapshot(race: Mapping[str, Any]) -> dict[str, Any]:
    venue = venue_key(first(race, "venue", "racecourse", "開催場", "競馬場", "場所"))
    distance = to_int(first(race, "distance", "距離"))
    surface = normalize_surface(first(race, "surface", "course_type", "芝ダ"))
    turn = normalize_turn(first(race, "turn", "回り", "direction")) or venue_turn(venue)
    return {
        "race_id": clean_text(race.get("race_id")),
        "race_name": clean_text(race.get("race_name")),
        "race_number": clean_text(race.get("race_number")),
        "venue": venue,
        "distance": distance,
        "surface": surface,
        "turn": turn,
    }


def evaluate_shadow_candidates(races: Sequence[ShadowRace]) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict[str, Any]] = []
    for race in races:
        try:
            finish, _payouts = parse_result_html(race.result_path)
        except Exception:
            continue
        if not finish:
            continue
        evaluated = evaluate_shadow_race(race.rows, race.race_type, race.race_info)
        for variant, horses in evaluated.items():
            ordered = sorted(horses, key=lambda row: to_float(row.get(f"{variant}_rank")) or 999)
            top5_numbers = {horse_no(row) for row in ordered[:5]}
            top1_no = horse_no(ordered[0]) if ordered else ""
            top3_finishers = {no for no, result in finish.items() if to_int(result.get("finish")) in {1, 2, 3}}
            winner = next((no for no, result in finish.items() if to_int(result.get("finish")) == 1), "")
            for row in horses:
                no = horse_no(row)
                result_row = finish.get(no, {})
                detail_rows.append(
                    {
                        "dataset": race.label,
                        "race_id": race.race_id,
                        "race_type": race.race_type,
                        "variant": variant,
                        "horse_no": no,
                        "horse_name": clean_text(first(row, "horse_name", "馬名", "name")),
                        "finish": to_int(result_row.get("finish")),
                        "selected_top5": no in top5_numbers,
                        "selected_top1": no == top1_no,
                        "race_winner_in_top5": bool(winner and winner in top5_numbers),
                        "race_top3_count_in_top5": len(top3_finishers.intersection(top5_numbers)),
                        "race_all_top3_in_top5": len(top3_finishers) == 3 and top3_finishers.issubset(top5_numbers),
                        "mark": clean_text(row.get(f"{variant}_mark")),
                        "rank": to_int(row.get(f"{variant}_rank")),
                        "score": to_float(row.get(f"{variant}_score")),
                        "repro": clean_text(row.get("shadow_reproducibility")),
                        "repro_reason": clean_text(row.get("shadow_reproducibility_reason")),
                        "pace": clean_text(row.get("shadow_pace_eval")),
                        "state": clean_text(row.get("shadow_state_eval")),
                        "condition_specialist": bool(row.get("shadow_condition_specialist")),
                        "warning_candidate": bool(row.get("shadow_warning_candidate")),
                    }
                )
    details = pd.DataFrame(detail_rows)
    return build_shadow_summary(details), details


def evaluate_shadow_records(records: pd.DataFrame, *, dataset: str = "existing_records") -> tuple[pd.DataFrame, pd.DataFrame]:
    if records is None or records.empty:
        return build_shadow_summary(pd.DataFrame()), pd.DataFrame()
    detail_rows: list[dict[str, Any]] = []
    for race_id, group in records.groupby("race_id", sort=False):
        race_type = clean_text(group.iloc[0].get("race_type")).lower() or "jra"
        race_info = {
            "race_id": clean_text(race_id),
            "venue": clean_text(group.iloc[0].get("venue")),
            "distance": to_int(group.iloc[0].get("distance")),
            "surface": clean_text(group.iloc[0].get("surface")),
        }
        rows = group.to_dict(orient="records")
        finish = {
            horse_no(row): {"finish": to_int(row.get("finish"))}
            for row in rows
            if to_int(row.get("finish")) is not None and horse_no(row)
        }
        if len(finish) < 3:
            continue
        evaluated = evaluate_shadow_race(rows, race_type, race_info)
        for variant, horses in evaluated.items():
            ordered = sorted(horses, key=lambda row: to_float(row.get(f"{variant}_rank")) or 999)
            top5_numbers = {horse_no(row) for row in ordered[:5]}
            top1_no = horse_no(ordered[0]) if ordered else ""
            top3_finishers = {no for no, result in finish.items() if to_int(result.get("finish")) in {1, 2, 3}}
            winner = next((no for no, result in finish.items() if to_int(result.get("finish")) == 1), "")
            for row in horses:
                no = horse_no(row)
                result_row = finish.get(no, {})
                detail_rows.append(
                    {
                        "dataset": dataset,
                        "race_id": clean_text(race_id),
                        "race_type": race_type,
                        "variant": variant,
                        "horse_no": no,
                        "horse_name": clean_text(first(row, "horse_name", "馬名", "name")),
                        "finish": to_int(result_row.get("finish")),
                        "selected_top5": no in top5_numbers,
                        "selected_top1": no == top1_no,
                        "race_winner_in_top5": bool(winner and winner in top5_numbers),
                        "race_top3_count_in_top5": len(top3_finishers.intersection(top5_numbers)),
                        "race_all_top3_in_top5": len(top3_finishers) == 3 and top3_finishers.issubset(top5_numbers),
                        "mark": clean_text(row.get(f"{variant}_mark")),
                        "rank": to_int(row.get(f"{variant}_rank")),
                        "score": to_float(row.get(f"{variant}_score")),
                        "repro": clean_text(row.get("shadow_reproducibility")),
                        "repro_reason": clean_text(row.get("shadow_reproducibility_reason")),
                        "pace": clean_text(row.get("shadow_pace_eval")),
                        "state": clean_text(row.get("shadow_state_eval")),
                        "condition_specialist": bool(row.get("shadow_condition_specialist")),
                        "warning_candidate": bool(row.get("shadow_warning_candidate")),
                    }
                )
    details = pd.DataFrame(detail_rows)
    return build_shadow_summary(details), details


def evaluate_shadow_race(
    rows: Sequence[Mapping[str, Any]],
    race_type: str,
    race_info: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    mode = clean_text(race_type).lower() or "jra"
    base_rows = [dict(row) for row in rows]
    v1 = build_v1_evaluations(base_rows, mode, race_info)
    v1_by_no = {horse_no(row): row for row in v1.get("rows", [])}
    enriched: list[dict[str, Any]] = []
    for row in base_rows:
        no = horse_no(row)
        merged = row.copy()
        merged.update({k: v for k, v in (v1_by_no.get(no) or {}).items() if k.startswith("v1_") or k.startswith("baseline_")})
        merged["shadow_reproducibility"] = clean_text(merged.get("v1_reproducibility"))
        merged["shadow_reproducibility_reason"] = clean_text(merged.get("v1_reproducibility_reason"))
        pace = pace_evaluation(merged)
        merged["shadow_pace_eval"] = pace.get("rank", "—")
        merged["shadow_pace_reason"] = pace.get("reason", "")
        state = state_evaluation(merged, recent_runs(merged), mode)
        merged["shadow_state_eval"] = state.get("rank", "—")
        merged["shadow_state_reason"] = state.get("reason", "")
        if mode == "nar":
            stats = nar_same_condition_stats(merged, race_info)
            merged.update(stats)
            merged["shadow_condition_specialist"] = is_nar_condition_specialist(merged)
            merged["shadow_warning_candidate"] = is_nar_warning_candidate(merged)
        else:
            merged["shadow_condition_specialist"] = is_jra_condition_specialist(merged)
            merged["shadow_warning_candidate"] = is_jra_warning_candidate(merged)
        enriched.append(merged)
    baseline = assign_variant_marks(sorted(enriched, key=baseline_sort_key), "baseline", mode)
    if mode == "nar":
        candidate_a = assign_variant_marks(nar_candidate_a_order(enriched), "candidate_a", mode)
        candidate_b = assign_variant_marks(
            sorted(enriched, key=lambda row: candidate_score_key(row, "nar_b")),
            "candidate_b",
            mode,
            score_mode="nar_b",
        )
        candidate_c = assign_variant_marks(
            sorted(enriched, key=lambda row: candidate_score_key(row, "nar_c")),
            "candidate_c",
            mode,
            score_mode="nar_c",
        )
    else:
        candidate_a = assign_variant_marks(
            sorted(enriched, key=lambda row: candidate_score_key(row, "jra_a")),
            "candidate_a",
            mode,
            score_mode="jra_a",
        )
        candidate_b = assign_variant_marks(
            sorted(enriched, key=lambda row: candidate_score_key(row, "jra_b")),
            "candidate_b",
            mode,
            score_mode="jra_b",
        )
        candidate_c = assign_variant_marks(
            sorted(enriched, key=lambda row: candidate_score_key(row, "jra_c")),
            "candidate_c",
            mode,
            score_mode="jra_c",
        )
    return {
        "baseline": baseline,
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
        "candidate_c": candidate_c,
    }


def assign_variant_marks(
    ordered: Sequence[Mapping[str, Any]],
    variant: str,
    race_type: str,
    *,
    score_mode: str | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, source in enumerate(ordered, start=1):
        row = dict(source)
        if variant == "baseline":
            mark = baseline_mark(row)
            score = baseline_rank_score(row)
        else:
            if index == 1:
                mark = "◎"
            elif index == 2:
                mark = "○"
            elif index == 3:
                mark = "▲"
            elif row.get("shadow_condition_specialist"):
                mark = "☆"
            elif row.get("shadow_warning_candidate"):
                mark = CHECK_MARK
            else:
                mark = "△" if index <= 5 else ""
            score = candidate_score(row, score_mode or "")
        row[f"{variant}_rank"] = index
        row[f"{variant}_mark"] = mark
        row[f"{variant}_score"] = score
        output.append(row)
    return output


def nar_candidate_a_order(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    baseline = [dict(row) for row in sorted(rows, key=baseline_sort_key)]
    top = baseline[:3]
    used = {horse_no(row) for row in top}
    specialists = [
        row
        for row in baseline
        if horse_no(row) not in used and row.get("shadow_condition_specialist")
    ]
    specialists = sorted(
        specialists,
        key=lambda row: (
            -int(row.get("same_condition_wins") or 0),
            -int(row.get("same_condition_top3") or 0),
            -float(to_float(first(row, "距離指数", "distance_index")) or 0),
            -float(to_float(first(row, "コース指数", "course_index")) or 0),
            baseline_sort_key(row),
        ),
    )
    rest = [row for row in baseline if horse_no(row) not in used and horse_no(row) not in {horse_no(item) for item in specialists}]
    return [*top, *specialists, *rest]


def candidate_score_key(row: Mapping[str, Any], mode: str) -> tuple[float, int]:
    return (-candidate_score(row, mode), to_int(first(row, "horse_no", "馬番")) or 999)


def candidate_score(row: Mapping[str, Any], mode: str) -> float:
    ability = ability_score(row)
    if ability is None:
        ability = 0.0
    score = ability
    repro = clean_text(row.get("shadow_reproducibility"))
    pace = clean_text(row.get("shadow_pace_eval"))
    state = clean_text(row.get("shadow_state_eval"))
    if mode == "nar_b":
        score += REPRO_BONUS_NAR.get(repro, 0.0)
        if row.get("shadow_condition_specialist"):
            score += 4.0
    elif mode == "nar_c":
        score += REPRO_BONUS_NAR.get(repro, 0.0)
        if row.get("shadow_condition_specialist"):
            score += 4.0
        score += PACE_BONUS.get(pace, 0.0)
    elif mode == "jra_a":
        score += REPRO_BONUS_JRA.get(repro, 0.0)
    elif mode == "jra_b":
        score += REPRO_BONUS_JRA.get(repro, 0.0)
        score += STATE_BONUS_JRA.get(state, 0.0)
    elif mode == "jra_c":
        score += REPRO_BONUS_JRA.get(repro, 0.0)
        score += STATE_BONUS_JRA.get(state, 0.0)
        score += PACE_BONUS.get(pace, 0.0)
    return round(score, 3)


def build_shadow_summary(details: pd.DataFrame) -> pd.DataFrame:
    if details.empty:
        return pd.DataFrame(
            columns=[
                "dataset",
                "race_type",
                "variant",
                "races",
                "top1_win_rate",
                "top1_top3_rate",
                "top5_winner_capture_rate",
                "top5_avg_top3_count",
                "top5_all_top3_capture_rate",
                "avg_selection_count",
                "star_top3_rate",
                "check_top3_rate",
            ]
        )
    rows: list[dict[str, Any]] = []
    race_groups = details.groupby(["dataset", "race_type", "variant", "race_id"], sort=False)
    for (dataset, race_type, variant), group in details.groupby(["dataset", "race_type", "variant"], sort=False):
        race_rows = []
        selected_count = []
        star_rows = []
        check_rows = []
        for (_d, _t, _v, _race_id), race in race_groups:
            if _d != dataset or _t != race_type or _v != variant:
                continue
            top1 = race[race["selected_top1"].eq(True)]
            selected = race[race["selected_top5"].eq(True)]
            selected_count.append(len(selected))
            race_rows.append(
                {
                    "top1_win": bool(not top1.empty and to_int(top1.iloc[0].get("finish")) == 1),
                    "top1_top3": bool(not top1.empty and (to_int(top1.iloc[0].get("finish")) or 999) <= 3),
                    "winner_capture": bool(race.iloc[0].get("race_winner_in_top5")),
                    "top3_count": int(race.iloc[0].get("race_top3_count_in_top5") or 0),
                    "all_top3": bool(race.iloc[0].get("race_all_top3_in_top5")),
                }
            )
            star_rows.extend(selected[selected["mark"].eq("☆")].to_dict("records"))
            check_rows.extend(selected[selected["mark"].isin([CHECK_MARK, "✓"])].to_dict("records"))
        race_frame = pd.DataFrame(race_rows)
        rows.append(
            {
                "dataset": dataset,
                "race_type": race_type,
                "variant": variant,
                "races": int(len(race_frame)),
                "top1_win_rate": pct(race_frame["top1_win"].sum(), len(race_frame)),
                "top1_top3_rate": pct(race_frame["top1_top3"].sum(), len(race_frame)),
                "top5_winner_capture_rate": pct(race_frame["winner_capture"].sum(), len(race_frame)),
                "top5_avg_top3_count": round(float(race_frame["top3_count"].mean()), 3) if not race_frame.empty else 0,
                "top5_all_top3_capture_rate": pct(race_frame["all_top3"].sum(), len(race_frame)),
                "avg_selection_count": round(sum(selected_count) / len(selected_count), 3) if selected_count else 0,
                "star_top3_rate": mark_top3_rate(star_rows),
                "check_top3_rate": mark_top3_rate(check_rows),
            }
        )
    return pd.DataFrame(rows)


def acceptance_report(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if summary.empty:
        return pd.DataFrame()
    for (dataset, race_type), group in summary.groupby(["dataset", "race_type"], sort=False):
        base = group[group["variant"].eq("baseline")]
        if base.empty:
            continue
        base_row = base.iloc[0]
        for _, candidate in group[~group["variant"].eq("baseline")].iterrows():
            rows.append(
                {
                    "dataset": dataset,
                    "race_type": race_type,
                    "variant": candidate.get("variant"),
                    "top1_top3_delta": round(float(candidate.get("top1_top3_rate") or 0) - float(base_row.get("top1_top3_rate") or 0), 3),
                    "top5_winner_delta": round(float(candidate.get("top5_winner_capture_rate") or 0) - float(base_row.get("top5_winner_capture_rate") or 0), 3),
                    "top5_avg_top3_delta": round(float(candidate.get("top5_avg_top3_count") or 0) - float(base_row.get("top5_avg_top3_count") or 0), 3),
                    "top5_all_top3_delta": round(float(candidate.get("top5_all_top3_capture_rate") or 0) - float(base_row.get("top5_all_top3_capture_rate") or 0), 3),
                    "avg_selection_delta": round(float(candidate.get("avg_selection_count") or 0) - float(base_row.get("avg_selection_count") or 0), 3),
                }
            )
    return pd.DataFrame(rows)


def funabashi_12_diagnostic(races: Sequence[ShadowRace]) -> pd.DataFrame:
    target = next((race for race in races if race.race_id == "202643082712"), None)
    if target is None:
        return pd.DataFrame()
    evaluated = evaluate_shadow_race(target.rows, target.race_type, target.race_info)["candidate_a"]
    rows = []
    for horse in evaluated:
        if horse_no(horse) in {"5", "6"}:
            rows.append(
                {
                    "horse_no": horse_no(horse),
                    "horse_name": clean_text(first(horse, "horse_name", "馬名")),
                    "ability_band": clean_text(first(horse, "snapshot_ability_band", "能力帯", "ability_band_v2", "ability_band")),
                    "ability_value": ability_score(horse),
                    "baseline_rank": baseline_rank(horse),
                    "baseline_mark": baseline_mark(horse),
                    "same_condition_runs": horse.get("same_condition_runs"),
                    "same_condition_top3": horse.get("same_condition_top3"),
                    "same_condition_wins": horse.get("same_condition_wins"),
                    "repro": horse.get("shadow_reproducibility"),
                    "repro_reason": horse.get("shadow_reproducibility_reason"),
                    "condition_specialist": horse.get("shadow_condition_specialist"),
                    "candidate_a_rank": horse.get("candidate_a_rank"),
                    "candidate_a_mark": horse.get("candidate_a_mark"),
                }
            )
    return pd.DataFrame(rows)


def nar_same_condition_stats(row: Mapping[str, Any], race_info: Mapping[str, Any]) -> dict[str, Any]:
    venue = venue_key(first(race_info, "venue", "racecourse", "競馬場"))
    distance = to_int(first(race_info, "distance", "距離"))
    same = []
    for run in recent_runs(row):
        if venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track", "track")) == venue and to_int(first(run, "distance", "距離")) == distance:
            same.append(run)
    return {
        "same_condition_runs": len(same),
        "same_condition_top3": sum(1 for run in same if finish_in_top3(run)),
        "same_condition_wins": sum(1 for run in same if finish_is_win(run)),
    }


def is_nar_condition_specialist(row: Mapping[str, Any]) -> bool:
    wins = int(row.get("same_condition_wins") or 0)
    top3 = int(row.get("same_condition_top3") or 0)
    if not (wins >= 1 or top3 >= 2):
        return False
    return condition_support_exists(row)


def condition_support_exists(row: Mapping[str, Any]) -> bool:
    distance = to_float(first(row, "距離指数", "distance_index"))
    course = to_float(first(row, "コース指数", "course_index"))
    if distance is not None and distance >= 50:
        return True
    if course is not None and course >= 50:
        return True
    material = " ".join(
        [
            clean_text(first(row, "評価/検討材料", "decision_material", "snapshot_decision_material")),
            clean_text(row.get("plus_materials")),
            clean_text(row.get("snapshot_plus_materials")),
        ]
    )
    return any(token in material for token in ("距離実績", "コース実績", "近走", "適性", "同馬場実績"))


def is_nar_warning_candidate(row: Mapping[str, Any]) -> bool:
    ability_rank = to_int(first(row, "market_ability_rank", "ability_rank", "snapshot_ability_rank", "能力順位"))
    if ability_rank is not None and ability_rank <= 5:
        return False
    return clean_text(row.get("shadow_pace_eval")) == "○" or "コース実績" in clean_text(row.get("plus_materials"))


def is_jra_condition_specialist(row: Mapping[str, Any]) -> bool:
    ability_rank = to_int(first(row, "market_ability_rank", "ability_rank", "snapshot_ability_rank", "能力順位"))
    return (ability_rank is None or ability_rank >= 6) and clean_text(row.get("shadow_reproducibility")) in {"S", "A"}


def is_jra_warning_candidate(row: Mapping[str, Any]) -> bool:
    ability_rank = to_int(first(row, "market_ability_rank", "ability_rank", "snapshot_ability_rank", "能力順位"))
    return (ability_rank is None or ability_rank >= 6) and (
        clean_text(row.get("shadow_pace_eval")) == "○" or clean_text(row.get("shadow_state_eval")) == "A"
    )


def ability_score(row: Mapping[str, Any]) -> float | None:
    return to_float(
        first(
            row,
            "market_ability_score",
            "snapshot_ability_value",
            "ability_value",
            "ability_display_score",
            "能力評価値",
            "raw_score",
            "_raw_score",
        )
    )


def baseline_rank(row: Mapping[str, Any]) -> int | None:
    return to_int(first(row, "current_evaluation_rank", "snapshot_current_evaluation_rank", "AI順位", "ai_rank"))


def baseline_mark(row: Mapping[str, Any]) -> str:
    return normalize_mark(first(row, "mark", "表示印", "old_final_mark", "snapshot_mark"))


def baseline_rank_score(row: Mapping[str, Any]) -> float:
    rank = baseline_rank(row)
    if rank is not None:
        return 100.0 - rank
    ability = ability_score(row)
    return ability if ability is not None else 0.0


def baseline_sort_key(row: Mapping[str, Any]) -> tuple[int, int, float, int]:
    rank = baseline_rank(row)
    return (
        rank if rank is not None else 999,
        BASELINE_MARK_ORDER.get(baseline_mark(row), 8),
        -(ability_score(row) or -9999),
        to_int(first(row, "horse_no", "馬番")) or 999,
    )


def mark_top3_rate(rows: Sequence[Mapping[str, Any]]) -> float:
    if not rows:
        return 0.0
    return pct(sum(1 for row in rows if (to_int(row.get("finish")) or 999) <= 3), len(rows))


def pct(numerator: float, denominator: float) -> float:
    return round((float(numerator) / float(denominator) * 100), 1) if denominator else 0.0


def _read_snapshot(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("snapshot.json"))


def _table_records(table: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = table.get("records")
    if isinstance(records, list):
        return [dict(row) for row in records if isinstance(row, Mapping)]
    columns = table.get("columns")
    data = table.get("data") or table.get("rows")
    if isinstance(columns, list) and isinstance(data, list):
        output = []
        for row in data:
            if isinstance(row, Mapping):
                output.append(dict(row))
            elif isinstance(row, list):
                output.append(dict(zip(columns, row)))
        return output
    return []


def infer_race_type(race_id: str) -> str:
    return "jra" if len(clean_text(race_id)) == 12 and clean_text(race_id).startswith("2026") and clean_text(race_id)[4:6] in {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10"} else "nar"


def horse_no(row: Mapping[str, Any]) -> str:
    return normalize_horse_no(first(row, "horse_no", "馬番", "horse_number", "number"))


def normalize_horse_no(value: Any) -> str:
    number = to_int(value)
    return str(number) if number is not None else clean_text(value)


def first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and clean_text(row.get(key)) != "":
            return row.get(key)
    return None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
