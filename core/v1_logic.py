from __future__ import annotations

import math
import re
import ast
import json
from typing import Any, Iterable, Mapping, Sequence


V1_MARKS = ("◎", "○", "▲", "☆", "△", "✔︎")
REPRO_POINTS = {"S": 4.0, "A": 3.0, "B": 2.0, "C": 1.0, "—": 0.0, "-": 0.0, "": 0.0}
PACE_POINTS = {"○": 1.5, "△": 0.5, "×": -1.0, "—": 0.0, "": 0.0}
STATE_POINTS = {"A": 1.5, "B": 0.5, "C": -1.0, "—": 0.0, "": 0.0}
SPECIAL_NAR_CONDITIONS = {("船橋", 2200), ("門別", 1700), ("門別", 1800)}


def build_v1_evaluations(
    rows: Sequence[Mapping[str, Any]],
    race_mode: str,
    race_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mode = text(race_mode).lower() or "jra"
    current = current_condition(rows, race_info or {})
    horses = [build_v1_horse(row, mode, current) for row in rows]
    fill_missing_ability_ranks(horses)
    assign_v1_scores_and_marks(horses)
    recommendations = final_recommendations(horses)
    return {
        "race_mode": mode,
        "current_condition": current,
        "summary": build_v1_summary(horses, current, recommendations),
        "recommendations": recommendations,
        "rows": horses,
        "research_only": False,
    }


def build_v1_horse(row: Mapping[str, Any], race_mode: str, current: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(row)
    runs = recent_runs(raw)
    reproducibility = (
        nar_reproducibility(runs, current)
        if race_mode == "nar"
        else jra_reproducibility(runs, current)
    )
    pace = pace_evaluation(raw)
    state = state_evaluation(raw, runs, race_mode)
    ability_rank = to_int(
        first(raw, "market_ability_rank", "ability_rank", "saved_ability_rank", "能力順位", "ability_rank_for_backtest")
    )
    ability_value = to_float(
        first(
            raw,
            "market_ability_score",
            "ability_value",
            "saved_ability_value",
            "ability_display_score",
            "能力評価値",
            "raw_score",
            "_raw_score",
        )
    )
    current_rank = to_int(
        first(
            raw,
            "current_evaluation_rank",
            "saved_current_evaluation_rank",
            "AI今回評価順位",
            "今回評価順位",
            "今回順位",
            "ai_current_rank",
            "AI順位",
            "ai_rank",
        )
    )
    role = primary_role(raw, reproducibility, pace, state, ability_rank, race_mode, current)
    baseline_mark = text(first(raw, "ai_current_mark", "mark", "saved_mark", "表示印", "display_mark", "最終印", "印"))
    raw.update(
        {
            "baseline_current_evaluation_rank": current_rank,
            "baseline_mark": baseline_mark,
            "v1_reproducibility": reproducibility["rank"],
            "v1_reproducibility_reason": reproducibility["reason"],
            "v1_reproducibility_key": reproducibility["key"],
            "v1_special_distance": reproducibility.get("special_distance", False),
            "v1_pace_eval": pace["rank"],
            "v1_pace_reason": pace["reason"],
            "v1_state_eval": state["rank"],
            "v1_state_reason": state["reason"],
            "v1_role": role,
            "v1_mark": "",
            "v1_order": None,
            "v1_score": 0.0,
            "v1_base_score": 0.0,
            "v1_base_rank": None,
            "v1_final_score": 0.0,
            "v1_final_rank": None,
            "v1_final_mark": "",
            "v1_final_role": role,
            "v1_final_reason": "",
            "_v1_ability_rank": ability_rank,
            "_v1_ability_value": ability_value,
            "_v1_current_rank": current_rank,
            "number": text(first(raw, "number", "horse_no", "馬番", "馬", "horse_number")) or text(raw.get("number")),
            "name": text(first(raw, "name", "horse_name", "馬名")) or text(raw.get("name")),
            "ability_rank": ability_rank,
            "ability_value": ability_value,
            "current_evaluation_rank": current_rank,
        }
    )
    return raw


def fill_missing_ability_ranks(horses: list[dict[str, Any]]) -> None:
    """Fill display-only v1 ability ranks when saved values exist but rank keys do not."""

    ranked = [
        horse
        for horse in horses
        if to_float(horse.get("_v1_ability_value")) is not None
    ]
    ranked = sorted(
        ranked,
        key=lambda horse: (
            -float(to_float(horse.get("_v1_ability_value")) or -999999),
            to_int(first(horse, "horse_no", "馬番", "number")) or 999,
        ),
    )
    for index, horse in enumerate(ranked, start=1):
        if to_int(horse.get("_v1_ability_rank")) is None:
            horse["_v1_ability_rank"] = index
            horse["ability_rank"] = index


def nar_reproducibility(runs: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    venue = text(current.get("venue"))
    distance = to_int(current.get("distance"))
    key = f"{venue}{distance}m" if venue and distance else ""
    if not venue or distance is None or not runs:
        return repro("—", "判定材料不足", key)
    same = [
        run
        for run in runs
        if venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track")) == venue
        and to_int(first(run, "distance", "距離")) == distance
    ]
    same_top3 = [run for run in same if finish_in_top3(run)]
    same_wins = [run for run in same if finish_is_win(run)]
    near_top3 = [
        run
        for run in runs
        if finish_in_top3(run)
        and (
            venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track")) == venue
            or to_int(first(run, "distance", "距離")) == distance
        )
    ]
    special = (venue, distance) in SPECIAL_NAR_CONDITIONS
    if same_wins and len(same_top3) >= 2:
        return repro("S", f"{key}: 勝利あり・複数好走 / {len(same)}走", key, special)
    if len(same_top3) >= 2 and len(same[:3]) >= 2:
        return repro("S", f"{key}: 近走内で複数3着内 / {len(same)}走", key, special)
    if same_top3:
        finishes = "・".join(f"{to_int(first(run, 'finish', '着順'))}着" for run in same_top3 if to_int(first(run, "finish", "着順")) is not None)
        return repro("A", f"{key}: {finishes or '3着内'} / {len(same)}走", key, special)
    if same:
        return repro("C", f"{key}: 同条件経験あり・好走なし / {len(same)}走", key, special)
    if near_top3:
        return repro("B", f"近い条件で3着内あり / {len(near_top3)}走", key, special)
    return repro("—", "未経験", key, special)


def jra_reproducibility(runs: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    venue = text(current.get("venue"))
    surface = normalize_surface(current.get("surface"))
    distance = to_int(current.get("distance"))
    turn = normalize_turn(current.get("turn")) or venue_turn(venue)
    key = "".join(part for part in [surface, str(distance) if distance else "", turn] if part)
    if not surface or distance is None or not runs:
        return repro("—", "判定材料不足", key)
    full_top3 = []
    shape_top3 = []
    shape_count = 0
    surface_distance_count = 0
    surface_distance_top3 = []
    turn_count = 0
    for run in runs:
        run_venue = venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track"))
        run_surface = normalize_surface(first(run, "surface", "芝ダ", "course_type"))
        run_distance = to_int(first(run, "distance", "距離"))
        run_turn = normalize_turn(first(run, "turn", "回り", "direction")) or venue_turn(run_venue)
        same_full = run_venue == venue and run_surface == surface and run_distance == distance and run_turn == turn
        same_shape = run_surface == surface and run_distance == distance and run_turn == turn
        same_sd = run_surface == surface and run_distance == distance
        if same_shape:
            shape_count += 1
        if same_sd:
            surface_distance_count += 1
        if run_turn and turn and run_turn == turn:
            turn_count += 1
        if finish_in_top3(run):
            if same_full:
                full_top3.append(run)
            if same_shape:
                shape_top3.append(run)
            if same_sd:
                surface_distance_top3.append(run)
    if full_top3 or len(shape_top3) >= 2:
        return repro("S", f"{key}: 同型条件で複数好走" if len(shape_top3) >= 2 else f"{key}: 同会場同条件で好走", key)
    if shape_top3:
        return repro("A", f"{key}: 3着内実績あり", key)
    if surface_distance_top3 or surface_distance_count:
        return repro("B", f"{surface}{distance}m: 実績あり", key)
    if turn_count:
        return repro("C", f"{turn}回り経験のみ", key)
    return repro("—", "条件根拠薄い", key)


def repro(rank: str, reason: str, key: str, special_distance: bool = False) -> dict[str, Any]:
    if special_distance and rank in {"S", "A", "B", "C"}:
        reason = f"{reason} / 特殊距離"
    return {"rank": rank, "reason": reason, "key": key, "special_distance": special_distance}


def pace_evaluation(row: Mapping[str, Any]) -> dict[str, str]:
    corner = corner4_group(row)
    style = text(first(row, "running_style", "脚質"))
    if corner == "front":
        suffix = "（逃げ）" if "逃" in style else ""
        return {"rank": "○", "reason": f"4角前方想定{suffix}"}
    if corner == "middle":
        return {"rank": "△", "reason": "4角中団想定"}
    if corner == "back":
        return {"rank": "×", "reason": "4角後方想定"}
    return {"rank": "—", "reason": "位置不明"}


def state_evaluation(row: Mapping[str, Any], runs: Sequence[Mapping[str, Any]], race_mode: str) -> dict[str, str]:
    score = 0
    reasons: list[str] = []
    main_positive = 0
    main_negative = 0
    support_positive = 0
    support_negative = 0
    training = text(first(row, "training", "training_display", "training_short", "調教", "調教評価", "追切評価", "調教/評価/検討材料"))
    training_grade_match = re.search(r"\b([ABCD])\b|^([ABCD])", training)
    training_grade = (training_grade_match.group(1) or training_grade_match.group(2)) if training_grade_match else ""
    if race_mode == "jra" and training:
        if training_grade == "A" or re.search(r"A↑|好調|好気配|動き抜群|仕上抜群|仕上良|仕上上々|上々|良好|力強い", training):
            score += 1
            main_positive += 1
            reasons.append(f"調教{training}")
        elif training_grade in {"C", "D"} or re.search(r"D↓|物足り|弱|不安|平凡|反応平凡|良化遅い", training):
            score -= 1
            main_negative += 1
            reasons.append(f"調教{training}")
    comment = text(
        first(
            row,
            "stable_comment",
            "stable_comment_market",
            "stable_comment_summary",
            "厩舎コメント",
            "newspaper_comment",
            "新聞コメント",
        )
    )
    comment_positive = False
    comment_negative = False
    if race_mode == "jra" and comment:
        if re.search(r"状態はいい|状態は良い|順調|好調|好気配|上向|期待|メド|適性もある|動きもいい|キープ|前向", comment):
            score += 1
            main_positive += 1
            comment_positive = True
            reasons.append("コメント前向き")
        elif re.search(r"不安|重い|慎重|まだ|ズブ|良化遅い|反応平凡", comment):
            score -= 1
            main_negative += 1
            comment_negative = True
            reasons.append("コメント慎重")
    weight_diff = to_float(first(row, "weight_diff", "斤量差", "斤量増減"))
    if weight_diff is not None:
        if race_mode == "jra" and weight_diff <= -2:
            score += 1
            support_positive += 1
            reasons.append("斤量減")
        elif weight_diff >= 3:
            score -= 1
            support_negative += 1
            reasons.append("斤量増")
    interval = text(first(row, "interval", "レース間隔", "間隔"))
    if "連闘" in interval or "休み明け" in interval:
        score -= 1
        support_negative += 1
        reasons.append(interval)
    recent = [to_float(first(run, "time_index", "index", "value", "指数")) for run in list(runs)[:3]]
    recent = [value for value in recent if value is not None]
    if len(recent) >= 2:
        if recent[0] > recent[-1]:
            score += 1
            support_positive += 1
            reasons.append("近走上昇")
        elif recent[0] < recent[-1] - 10:
            score -= 1
            support_negative += 1
            reasons.append("近走下降")
    if not reasons:
        return {"rank": "—", "reason": "材料不足"}
    if race_mode == "nar":
        if score >= 3 and len(reasons) >= 3:
            return {"rank": "A", "reason": " / ".join(reasons)}
        if score > 0:
            return {"rank": "B", "reason": " / ".join(reasons)}
        if score < 0:
            return {"rank": "C", "reason": " / ".join(reasons)}
        return {"rank": "—", "reason": "判断保留：" + " / ".join(reasons)}
    if training_grade == "A" and comment_positive and main_negative == 0:
        return {"rank": "A", "reason": " / ".join(reasons)}
    if main_positive >= 2 and training_grade == "A" and main_negative == 0:
        return {"rank": "A", "reason": " / ".join(reasons)}
    if main_negative and (training_grade in {"C", "D"} or comment_negative or score <= -1):
        return {"rank": "C", "reason": " / ".join(reasons)}
    if main_positive:
        return {"rank": "B", "reason": " / ".join(reasons)}
    if support_negative >= 2 and score <= -2:
        return {"rank": "C", "reason": " / ".join(reasons)}
    if support_positive:
        return {"rank": "B", "reason": " / ".join(reasons)}
    return {"rank": "B", "reason": " / ".join(reasons)}


def primary_role(
    row: Mapping[str, Any],
    reproducibility: Mapping[str, Any],
    pace: Mapping[str, Any],
    state: Mapping[str, Any],
    ability_rank: int | None,
    race_mode: str,
    current: Mapping[str, Any],
) -> str:
    repro_rank = text(reproducibility.get("rank"))
    if ability_rank is not None and ability_rank <= 3 and repro_rank in {"S", "A", "B"}:
        return "軸候補" if ability_rank == 1 else "能力上位"
    if repro_rank in {"S", "A"} and (ability_rank is None or ability_rank >= 4):
        return "条件スペシャリスト"
    if pace.get("rank") == "○" and (ability_rank is None or ability_rank >= 5):
        return "展開穴"
    if reproducibility.get("special_distance") and repro_rank in {"A", "B", "C"}:
        return "条件穴"
    if state.get("rank") == "A" and (ability_rank is None or ability_rank >= 4):
        return "状態上向き"
    return "相手候補"


def assign_v1_scores_and_marks(horses: list[dict[str, Any]]) -> None:
    if not horses:
        return
    ability_values = [to_float(horse.get("_v1_ability_value")) for horse in horses]
    numeric_values = [value for value in ability_values if value is not None]
    max_ability = max(numeric_values) if numeric_values else 0.0
    min_ability = min(numeric_values) if numeric_values else 0.0
    ability_span = max(max_ability - min_ability, 1.0)
    for horse in horses:
        ability = to_float(horse.get("_v1_ability_value"))
        ability_rank = to_int(horse.get("_v1_ability_rank"))
        ability_component = ((ability - min_ability) / ability_span * 10.0) if ability is not None else 0.0
        if ability_rank is not None:
            ability_component += max(0.0, 6.0 - min(ability_rank, 6)) * 0.8
        score = (
            ability_component
            + REPRO_POINTS.get(text(horse.get("v1_reproducibility")), 0.0) * 2.2
            + PACE_POINTS.get(text(horse.get("v1_pace_eval")), 0.0)
            + STATE_POINTS.get(text(horse.get("v1_state_eval")), 0.0)
        )
        if horse.get("v1_special_distance") and horse.get("v1_reproducibility") in {"S", "A", "B"}:
            score += 1.0
        horse["v1_base_score"] = round(score, 3)
        horse["v1_score"] = horse["v1_base_score"]
    base_ordered = sorted(horses, key=v1_base_sort_key)
    for index, horse in enumerate(base_ordered, start=1):
        horse["v1_base_rank"] = index

    final_ordered: list[dict[str, Any]] = []
    used: set[int] = set()
    for horse in base_ordered[:3]:
        final_ordered.append(horse)
        used.add(id(horse))

    remaining = [horse for horse in base_ordered if id(horse) not in used]
    star = best_candidate(remaining, lambda horse: horse.get("v1_role") == "条件スペシャリスト")
    if star is None:
        star = best_candidate(remaining, lambda horse: horse.get("v1_reproducibility") in {"S", "A"})
    if star is not None:
        final_ordered.append(star)
        used.add(id(star))

    delta = best_candidate([horse for horse in base_ordered if id(horse) not in used], lambda horse: True)
    if delta is not None:
        final_ordered.append(delta)
        used.add(id(delta))

    check = best_candidate(
        [horse for horse in base_ordered if id(horse) not in used],
        lambda horse: horse.get("v1_role") in {"条件穴", "展開穴"} or (
            horse.get("v1_reproducibility") in {"A", "B"} and horse.get("v1_pace_eval") == "○"
        ),
    )
    if check is not None:
        final_ordered.append(check)
        used.add(id(check))

    final_ordered.extend(horse for horse in base_ordered if id(horse) not in used)
    for horse in horses:
        horse["v1_mark"] = ""
        horse["v1_order"] = None
        horse["v1_final_mark"] = ""
        horse["v1_final_rank"] = None
        horse["v1_final_score"] = horse.get("v1_base_score", 0.0)
    for index, horse in enumerate(final_ordered, start=1):
        role = final_role_for_rank(index, text(horse.get("v1_role")) or "相手候補")
        mark = final_mark_for_rank(index, role)
        horse["v1_final_rank"] = index
        horse["v1_final_score"] = horse.get("v1_base_score", 0.0)
        horse["v1_final_role"] = role
        horse["v1_final_mark"] = mark
        horse["v1_final_reason"] = final_reason(horse)
        horse["v1_score"] = horse["v1_final_score"]
        horse["v1_role"] = horse["v1_final_role"]
        if mark:
            horse["v1_mark"] = mark
            horse["v1_order"] = index


def best_candidate(horses: Sequence[dict[str, Any]], predicate) -> dict[str, Any] | None:
    candidates = [horse for horse in horses if predicate(horse)]
    return sorted(candidates, key=v1_base_sort_key)[0] if candidates else None


def v1_sort_key(horse: Mapping[str, Any]) -> tuple[float, float, float]:
    return v1_final_sort_key(horse)


def v1_base_sort_key(horse: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -float(to_float(horse.get("v1_base_score")) or to_float(horse.get("v1_score")) or 0.0),
        float(to_int(horse.get("_v1_ability_rank")) or 99),
        float(to_int(first(horse, "horse_no", "馬番", "number", "horse_number")) or 999),
    )


def v1_final_sort_key(horse: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        float(to_int(horse.get("v1_final_rank")) or 999),
        -float(to_float(horse.get("v1_final_score")) or to_float(horse.get("v1_score")) or 0.0),
        float(to_int(first(horse, "horse_no", "馬番", "number", "horse_number")) or 999),
    )


def final_mark_for_rank(rank: int, role: str) -> str:
    if rank == 1:
        return "◎"
    if rank == 2:
        return "○"
    if rank == 3:
        return "▲"
    if rank > 5:
        return "✔︎" if role in {"条件穴", "展開穴"} else ""
    if role == "条件スペシャリスト":
        return "☆"
    if role in {"条件穴", "展開穴"}:
        return "✔︎"
    return "△"


def final_role_for_rank(rank: int, role: str) -> str:
    if rank == 1:
        return "軸候補"
    if rank in {2, 3} and role == "相手候補":
        return "能力上位"
    return role


def final_reason(horse: Mapping[str, Any]) -> str:
    parts = [
        f"能力{to_int(horse.get('_v1_ability_rank')) or '未成立'}位" if to_int(horse.get("_v1_ability_rank")) is not None else "能力未成立",
        f"再現性{text(horse.get('v1_reproducibility')) or '—'}",
        f"展開{text(horse.get('v1_pace_eval')) or '—'}",
        f"状態{text(horse.get('v1_state_eval')) or '—'}",
    ]
    role = text(horse.get("v1_final_role")) or text(horse.get("v1_role"))
    if role and role != "相手候補":
        parts.append(role)
    return " / ".join(parts)


def final_recommendations(horses: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
    return [
        horse
        for horse in sorted(horses, key=v1_final_sort_key)
        if text(horse.get("v1_final_mark")) or text(horse.get("v1_mark"))
    ][:limit]


def build_v1_summary(
    horses: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any] | None = None,
    recommendations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not horses:
        return {}
    ability_top = sorted(
        horses,
        key=lambda horse: (to_int(horse.get("_v1_ability_rank")) or 99, -float(to_float(horse.get("_v1_ability_value")) or -999)),
    )[:3]
    final_top = list(recommendations or final_recommendations(horses))[:5]
    top1, top2 = (ability_top + [None, None])[:2]
    gap_text = ""
    if top1 and top2:
        top1_value = to_float(top1.get("_v1_ability_value"))
        top2_value = to_float(top2.get("_v1_ability_value"))
        if top1_value is not None and top2_value is not None:
            gap = top1_value - top2_value
            gap_text = f"。1位-2位差は{gap:.1f}"
    repro_horses = [
        horse
        for horse in sorted(horses, key=lambda horse: (repro_order(horse.get("v1_reproducibility")), to_int(horse.get("_v1_ability_rank")) or 99))
        if text(horse.get("v1_reproducibility")) in {"S", "A", "B", "C"}
    ]
    strong_repro = [horse for horse in repro_horses if text(horse.get("v1_reproducibility")) in {"S", "A"}]
    pace_counts = counts_by(horses, "v1_pace_eval")
    front = [horse for horse in horses if text(horse.get("v1_pace_eval")) == "○"]
    middle = [horse for horse in horses if text(horse.get("v1_pace_eval")) == "△"]
    back = [horse for horse in horses if text(horse.get("v1_pace_eval")) == "×"]
    state_up = [horse for horse in horses if text(horse.get("v1_state_eval")) == "A"]
    state_down = [horse for horse in horses if text(horse.get("v1_state_eval")) == "C"]
    specialists = [horse for horse in horses if text(horse.get("v1_role")) in {"条件スペシャリスト", "条件穴", "展開穴", "状態上向き"}]
    return {
        "能力": f"上位は{' / '.join(horse_label(horse) for horse in ability_top) or '—'}{gap_text}",
        "再現性": reproducibility_summary(repro_horses, strong_repro, current or {}),
        "展開": pace_summary(front, middle, back, pace_counts),
        "状態": state_summary(state_up, state_down),
        "今回評価": current_eval_summary(final_top),
        "_今回評価_numbers": [text(first(horse, "horse_no", "馬番", "number")) for horse in final_top],
    }


def repro_order(value: Any) -> int:
    return {"S": 0, "A": 1, "B": 2, "C": 3, "—": 4}.get(text(value), 4)


def reproducibility_summary(
    repro_horses: Sequence[Mapping[str, Any]],
    strong_repro: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
) -> str:
    key = "".join(
        part
        for part in [
            text(current.get("venue")),
            f"{to_int(current.get('distance'))}m" if to_int(current.get("distance")) is not None else "",
        ]
        if part
    )
    if strong_repro:
        return f"{key or '今回条件'}でS/A評価は{len(strong_repro)}頭：{' / '.join(horse_label(horse) for horse in strong_repro[:3])}"
    if repro_horses:
        return f"{key or '今回条件'}の経験・近い条件根拠は{len(repro_horses)}頭：{' / '.join(horse_label(horse) for horse in repro_horses[:3])}"
    return f"{key or '今回条件'}で明確な再現性根拠は未確認"


def pace_summary(
    front: Sequence[Mapping[str, Any]],
    middle: Sequence[Mapping[str, Any]],
    back: Sequence[Mapping[str, Any]],
    pace_counts: Mapping[str, int],
) -> str:
    if front or middle or back:
        front_text = f"前方{len(front)}頭"
        middle_text = f"中団{len(middle)}頭"
        back_text = f"後方{len(back)}頭"
        labels = " / ".join(horse_label(horse) for horse in list(front)[:4])
        if labels:
            return f"{front_text}・{middle_text}・{back_text}。4角前方：{labels}"
        return f"{front_text}・{middle_text}・{back_text}"
    unknown = pace_counts.get("—", 0)
    return f"4角位置データ不足（不明{unknown}頭）"


def state_summary(up: Sequence[Mapping[str, Any]], down: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    if up:
        parts.append(f"上向き材料：{' / '.join(horse_label(horse) for horse in up[:3])}")
    if down:
        parts.append(f"不安材料：{' / '.join(horse_label(horse) for horse in down[:3])}")
    return "。".join(parts) if parts else "明確な上向き/下向き材料は少なめ"


def current_eval_summary(final_top: Sequence[Mapping[str, Any]]) -> str:
    if not final_top:
        return "今回の結論は未成立"
    axis = final_top[0]
    main = final_top[1:3]
    rise = [horse for horse in final_top[3:] if text(horse.get("v1_final_role")) != "相手候補"]
    parts = [f"軸：{horse_label(axis)}"]
    if main:
        parts.append(f"本線：{' / '.join(horse_label(horse) for horse in main)}")
    if rise:
        parts.append(f"浮上：{' / '.join(horse_label(horse) for horse in rise)}")
    return "。".join(parts)


def counts_by(horses: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for horse in horses:
        value = text(horse.get(key)) or "—"
        result[value] = result.get(value, 0) + 1
    return result


def horse_label(row: Mapping[str, Any]) -> str:
    no = text(first(row, "horse_no", "馬番", "number"))
    name = text(first(row, "horse_name", "馬名", "name"))
    return " ".join(part for part in [no, name] if part)


def current_condition(rows: Sequence[Mapping[str, Any]], race_info: Mapping[str, Any]) -> dict[str, Any]:
    sample = rows[0] if rows else {}
    venue = venue_key(first(race_info, "venue", "racecourse", "開催場", "競馬場", "場所") or first(sample, "venue", "racecourse", "開催場", "競馬場", "場所"))
    distance = to_int(first(race_info, "distance", "距離") or first(sample, "distance", "距離"))
    surface = normalize_surface(first(race_info, "surface", "course_type", "芝ダ") or first(sample, "surface", "course_type", "芝ダ"))
    turn = normalize_turn(first(race_info, "turn", "回り", "direction") or first(sample, "turn", "回り", "direction")) or venue_turn(venue)
    return {"venue": venue, "distance": distance, "surface": surface, "turn": turn}


def recent_runs(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("recent_runs", "recent_races", "_past_runs", "past_runs", "近走", "recent3_runs"):
        value = row.get(key)
        if isinstance(value, list):
            return [run for run in value if isinstance(run, Mapping)]
        if isinstance(value, str) and value.strip().startswith(("[", "{")):
            parsed = parse_runs_text(value)
            if parsed:
                return parsed
    runs: list[dict[str, Any]] = []
    labels = [("前走", 0), ("2走前", 1), ("3走前", 2)]
    for prefix, _index in labels:
        run: dict[str, Any] = {}
        for key, value in row.items():
            key_text = str(key)
            if key_text.startswith(prefix):
                compact = key_text.replace(prefix, "").strip("_ /")
                run[compact or "index"] = value
        if run:
            runs.append(run)
    return runs


def finish_in_top3(run: Mapping[str, Any]) -> bool:
    finish = to_int(first(run, "finish", "着順", "result", "rank", "position", "previous_finish"))
    return finish is not None and 1 <= finish <= 3


def finish_is_win(run: Mapping[str, Any]) -> bool:
    return to_int(first(run, "finish", "着順", "result", "rank", "position", "previous_finish")) == 1


def parse_runs_text(value: str) -> list[Mapping[str, Any]]:
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except Exception:
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, Mapping)]
    return []


def corner4_group(row: Mapping[str, Any]) -> str:
    text_value = text(
        first(
            row,
            "corner4_group",
            "position_corner4_group_market",
            "corner4_position",
            "position_corner4_label_market",
            "_estimated_position_corner4_label",
            "4角位置",
            "corner4_label",
            "corner4_display",
            "corner4_evaluation",
            "4角評価",
            "4角予想",
            "想定位置",
            "position_path_market",
            "_estimated_position_path",
            "estimated_position",
            "estimated_position_path",
        )
    )
    parts = [part.strip() for part in re.split(r"→|>|/|／", text_value) if part.strip()]
    label = parts[-1] if parts else text_value
    if any(token in label for token in ("front", "逃げ", "逃", "前方", "先頭", "先団")):
        return "front"
    if any(token in label for token in ("middle", "中団")):
        return "middle"
    if any(token in label for token in ("back", "後方", "追込", "追")):
        return "back"
    return "unknown"


def first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and text(row.get(key)) != "":
            return row.get(key)
    return None


def text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None


def normalize_surface(value: Any) -> str:
    value_text = text(value)
    if "芝" in value_text:
        return "芝"
    if "ダ" in value_text or "泥" in value_text:
        return "ダ"
    return ""


def normalize_turn(value: Any) -> str:
    value_text = text(value)
    if "左" in value_text:
        return "左"
    if "右" in value_text:
        return "右"
    if "直" in value_text:
        return "直"
    return ""


def venue_key(value: Any) -> str:
    value_text = text(value)
    for venue in (
        "札幌",
        "函館",
        "福島",
        "新潟",
        "東京",
        "中山",
        "中京",
        "京都",
        "阪神",
        "小倉",
        "門別",
        "盛岡",
        "水沢",
        "浦和",
        "船橋",
        "大井",
        "川崎",
        "金沢",
        "笠松",
        "名古屋",
        "園田",
        "姫路",
        "高知",
        "佐賀",
    ):
        if venue in value_text:
            return venue
    return value_text


def venue_turn(venue: str) -> str:
    return {
        "東京": "左",
        "中京": "左",
        "新潟": "左",
        "中山": "右",
        "京都": "右",
        "阪神": "右",
        "札幌": "右",
        "函館": "右",
        "福島": "右",
        "小倉": "右",
    }.get(venue, "")
