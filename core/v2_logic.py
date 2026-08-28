from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .v1_logic import (
    corner4_group,
    current_condition,
    finish_in_top3,
    finish_is_win,
    first,
    normalize_surface,
    normalize_turn,
    recent_runs,
    state_trend_runs,
    text,
    to_float,
    to_int,
    venue_key,
    venue_turn,
)


V2_MARKS = ("◎", "○", "▲", "△", "☆")


def build_v2_evaluations(
    rows: Sequence[Mapping[str, Any]],
    race_mode: str,
    race_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build display-only v2 AI scores from saved prediction facts."""

    mode = text(race_mode).lower() or "jra"
    current = current_condition(rows, race_info or {})
    current["pace"] = race_pace(rows, race_info or {})
    horses = [build_v2_horse(row, mode, current) for row in rows if isinstance(row, Mapping)]
    horses = [horse for horse in horses if text(horse.get("number"))]
    fill_missing_ability_ranks(horses)
    assign_v2_marks(horses)
    recommendations = [horse for horse in sorted(horses, key=v2_sort_key) if text(horse.get("v2_final_mark"))][:5]
    return {
        "race_mode": mode,
        "current_condition": current,
        "summary": build_v2_summary(horses, current, recommendations),
        "recommendations": recommendations,
        "rows": horses,
        "research_only": False,
    }


def build_v2_horse(row: Mapping[str, Any], race_mode: str, current: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(row)
    runs = recent_runs(raw)
    ability_value = ability_score(raw)
    ability_rank = ability_rank_value(raw)
    condition = nar_condition_score(runs, current) if race_mode == "nar" else jra_condition_score(runs, current)
    pace = pace_style_score(raw, current)
    recent_or_state = nar_recent_score(runs) if race_mode == "nar" else jra_state_score(raw, runs)
    ai_score = (ability_value or 0.0) + condition["score"] + pace["score"] + recent_or_state["score"]
    raw.update(
        {
            "number": text(first(raw, "horse_no", "馬番", "number", "horse_number", "馬")),
            "name": text(first(raw, "horse_name", "馬名", "name")),
            "ability_rank": ability_rank,
            "ability_value": ability_value,
            "v2_ai_score": round(ai_score, 3),
            "v2_ability_score": ability_value,
            "v2_condition_score": round(float(condition["score"]), 3),
            "v2_condition_reason": condition["reason"],
            "v2_condition_key": condition.get("key", ""),
            "v2_pace_score": round(float(pace["score"]), 3),
            "v2_pace_reason": pace["reason"],
            "v2_recent_state_score": round(float(recent_or_state["score"]), 3),
            "v2_recent_state_reason": recent_or_state["reason"],
            "v2_jockey_score": 0.0,
            "v2_final_mark": "",
            "v2_final_role": "",
            "v2_final_reason": "",
            "v2_top_gap": None,
            "v2_top_gap_text": "—",
        }
    )
    return raw


def ability_score(row: Mapping[str, Any]) -> float | None:
    return to_float(
        first(
            row,
            "market_ability_score",
            "ability_value",
            "saved_ability_value",
            "ability_display_score",
            "能力評価値",
            "raw_score",
            "_raw_score",
        )
    )


def ability_rank_value(row: Mapping[str, Any]) -> int | None:
    return to_int(first(row, "market_ability_rank", "ability_rank", "saved_ability_rank", "能力順位", "ability_rank_for_backtest"))


def fill_missing_ability_ranks(horses: Sequence[dict[str, Any]]) -> None:
    ranked = [horse for horse in horses if to_float(horse.get("ability_value")) is not None]
    ranked = sorted(
        ranked,
        key=lambda horse: (
            -float(to_float(horse.get("ability_value")) or -999999),
            horse_number_sort(horse.get("number")),
        ),
    )
    for index, horse in enumerate(ranked, start=1):
        if to_int(horse.get("ability_rank")) is None:
            horse["ability_rank"] = index


def nar_condition_score(runs: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    venue = venue_key(current.get("venue"))
    distance = to_int(current.get("distance"))
    key = f"{venue}{distance}m" if venue and distance is not None else ""
    if not venue or distance is None or not runs:
        return {"score": 0.0, "reason": "条件材料不足", "key": key}

    same = [run for run in runs if same_venue(run, venue) and same_distance(run, distance)]
    same_top3 = [run for run in same if finish_in_top3(run)]
    same_wins = [run for run in same if finish_is_win(run)]
    near_score = 0.0
    near_reasons: list[str] = []
    if any(finish_in_top3(run) for run in runs if same_venue(run, venue) and not same_distance(run, distance)):
        near_score += 0.5
        near_reasons.append("同会場別距離好走")
    if any(finish_in_top3(run) for run in runs if (not same_venue(run, venue)) and same_distance(run, distance)):
        near_score += 0.5
        near_reasons.append("別会場同距離好走")
    near_score = min(near_score, 1.0)

    if same_wins and len(same_top3) >= 2:
        base = 4.0
        reason = f"{key}: 勝利あり・複数3着内"
    elif len(same_top3) >= 2:
        base = 3.5
        reason = f"{key}: 複数3着内"
    elif len(same_top3) == 1:
        base = 2.5
        reason = f"{key}: 3着内1回"
    elif same:
        base = 0.0
        reason = f"{key}: 経験のみ"
    else:
        base = 0.0
        reason = f"{key}: 未経験"
    if near_reasons:
        reason = f"{reason} / {'・'.join(near_reasons)}"
    return {"score": round(base + near_score, 3), "reason": reason, "key": key}


def jra_condition_score(runs: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> dict[str, Any]:
    venue = venue_key(current.get("venue"))
    surface = normalize_surface(current.get("surface"))
    distance = to_int(current.get("distance"))
    turn = normalize_turn(current.get("turn")) or venue_turn(venue)
    key = "".join(part for part in [surface, str(distance) if distance else "", turn] if part)
    if not surface or distance is None or not runs:
        return {"score": 0.0, "reason": "条件材料不足", "key": key}

    same_full_top3 = 0
    same_shape_top3 = 0
    same_surface_distance_top3 = 0
    same_venue_bonus = 0.0
    for run in runs:
        run_venue = venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track"))
        run_surface = normalize_surface(first(run, "surface", "芝ダ", "course_type"))
        run_distance = to_int(first(run, "distance", "距離"))
        run_turn = normalize_turn(first(run, "turn", "回り", "direction")) or venue_turn(run_venue)
        top3 = finish_in_top3(run)
        same_full = run_venue == venue and run_surface == surface and run_distance == distance and run_turn == turn
        same_shape = run_surface == surface and run_distance == distance and run_turn == turn
        same_sd = run_surface == surface and run_distance == distance
        if top3 and same_full:
            same_full_top3 += 1
            same_venue_bonus = max(same_venue_bonus, 1.0)
        elif run_venue == venue and top3:
            same_venue_bonus = max(same_venue_bonus, 0.5)
        if top3 and same_shape:
            same_shape_top3 += 1
        if top3 and same_sd:
            same_surface_distance_top3 += 1

    if same_full_top3 or same_shape_top3 >= 2:
        base = 3.0
        reason = f"{key}: 同型条件で複数好走" if same_shape_top3 >= 2 else f"{key}: 同会場同条件で好走"
    elif same_shape_top3 == 1:
        base = 2.0
        reason = f"{key}: 同芝ダ同距離同回りで3着内1回"
    elif same_surface_distance_top3:
        base = 1.0
        reason = f"{surface}{distance}m: 同芝ダ同距離で好走"
    else:
        base = 0.0
        reason = "条件根拠薄い"
    score = min(base + same_venue_bonus, 4.0)
    if same_venue_bonus and "同会場" not in reason:
        reason = f"{reason} / 同会場実績"
    return {"score": round(score, 3), "reason": reason, "key": key}


def pace_style_score(row: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    pace = normalize_pace(current.get("pace"))
    style = normalize_style(first(row, "running_style_market", "running_style", "脚質"))
    corner = corner4_group(row)
    if not pace or not style:
        return {"score": 0.0, "reason": "展開材料不足"}
    if pace == "H":
        mapping = {"escape": -1.0, "front": -0.5, "stalker": 1.0, "closer": 0.5}
        labels = {"escape": "ハイペースで逃げ逆風", "front": "ハイペースで先行やや逆風", "stalker": "ハイペースで差し向き", "closer": "ハイペースで追込やや向き"}
    elif pace == "S":
        mapping = {"escape": 1.0, "front": 0.5, "stalker": -0.5, "closer": -1.0}
        labels = {"escape": "スローで逃げ向き", "front": "スローで先行やや向き", "stalker": "スローで差しやや逆風", "closer": "スローで追込逆風"}
    else:
        if corner == "front":
            return {"score": 0.5, "reason": "平均ペースで4角前方"}
        return {"score": 0.0, "reason": "平均ペースで中立"}
    return {"score": mapping.get(style, 0.0), "reason": labels.get(style, "展開中立")}


def nar_recent_score(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [
        to_float(first(run, "time_index", "index", "value", "指数"))
        for run in state_trend_runs(runs)[:3]
    ]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return {"score": 0.0, "reason": "近走材料不足"}
    diff = values[0] - values[-1]
    if diff >= 10:
        return {"score": 0.5, "reason": "近走明確上昇"}
    if diff > 0:
        return {"score": 0.25, "reason": "近走持ち直し"}
    if diff <= -10:
        return {"score": -0.5, "reason": "近走明確下降"}
    if diff < 0:
        return {"score": -0.25, "reason": "近走弱含み"}
    return {"score": 0.0, "reason": "近走横ばい"}


def jra_state_score(row: Mapping[str, Any], runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    training = training_text(row)
    comment = comment_text(row)
    grade = training_grade(training)
    positive_comment = bool(comment and re.search(r"状態はいい|状態は良い|順調|好調|好気配|上向|期待|メド|適性もある|動きもいい|キープ|前向|仕上", comment))
    negative_comment = bool(comment and re.search(r"不安|重い|慎重|まだ|ズブ|良化遅い|反応平凡|物足り|弱", comment))
    good_training = bool(training and re.search(r"好調|好気配|動き抜群|仕上抜群|仕上良|仕上上々|上々|良好|力強い", training))
    bad_training = bool(training and re.search(r"物足り|弱|不安|平凡|反応平凡|良化遅い|D↓|C↓", training))
    if grade == "A" and positive_comment:
        return {"score": 2.0, "reason": f"調教{training}・コメント前向き"}
    if grade == "A":
        return {"score": 1.5, "reason": f"調教{training}"}
    if grade in {"C", "D"} and negative_comment:
        return {"score": -2.0, "reason": f"調教{training}・コメント慎重"}
    if grade == "D":
        return {"score": -2.0, "reason": f"調教{training}"}
    if grade == "C" or bad_training:
        return {"score": -1.0, "reason": f"調教{training}" if training else "状態不安"}
    if grade == "B" and (positive_comment or good_training):
        reason_parts = [f"調教{training}"]
        if positive_comment:
            reason_parts.append("コメント前向き")
        return {"score": 1.0 if positive_comment and good_training else 0.5, "reason": "・".join(reason_parts)}
    trend = nar_recent_score(runs)
    trend_score = max(min(float(trend["score"]), 0.5), -0.5)
    if abs(trend_score) > 0:
        return {"score": trend_score, "reason": trend["reason"]}
    if training or comment:
        return {"score": 0.0, "reason": "状態普通"}
    return {"score": 0.0, "reason": "状態材料不足"}


def assign_v2_marks(horses: Sequence[dict[str, Any]]) -> None:
    if not horses:
        return
    ordered = sorted(horses, key=v2_sort_key)
    top_score = to_float(ordered[0].get("v2_ai_score")) or 0.0
    for index, horse in enumerate(ordered):
        score = to_float(horse.get("v2_ai_score")) or 0.0
        gap = score - top_score
        horse["v2_top_gap"] = round(gap, 3)
        horse["v2_top_gap_text"] = "0" if abs(gap) < 0.0001 else f"{gap:+.1f}"
        role = v2_role(horse, index)
        horse["v2_final_role"] = role
        if index == 0:
            mark = "◎"
        elif role == "条件スペシャリスト" and abs(gap) <= 6.0:
            mark = "☆"
        elif abs(gap) <= 2.0:
            mark = "○"
        elif abs(gap) <= 4.0:
            mark = "▲"
        elif abs(gap) <= 6.0:
            mark = "△"
        else:
            mark = ""
        horse["v2_final_mark"] = mark
        horse["v2_final_reason"] = v2_reason(horse)


def v2_role(horse: Mapping[str, Any], index: int) -> str:
    if index == 0:
        return "軸候補"
    ability_rank = to_int(horse.get("ability_rank"))
    condition_score = to_float(horse.get("v2_condition_score")) or 0.0
    pace_score = to_float(horse.get("v2_pace_score")) or 0.0
    if condition_score >= 2.5 and (ability_rank is None or ability_rank >= 4):
        return "条件スペシャリスト"
    if pace_score >= 0.75 and (ability_rank is None or ability_rank >= 5):
        return "展開穴"
    if ability_rank is not None and ability_rank <= 3:
        return "能力上位"
    return "相手候補"


def v2_reason(horse: Mapping[str, Any]) -> str:
    reasons = [
        v2_reason_component(horse.get("v2_condition_reason")),
        v2_reason_component(horse.get("v2_pace_reason")),
        v2_reason_component(horse.get("v2_recent_state_reason")),
    ]
    return " / ".join(reason for reason in reasons if reason) or "保存済み材料からAI点を算出"


def v2_reason_component(value: Any) -> str:
    reason = text(value)
    if not reason:
        return ""
    if "｜" not in reason:
        return reason
    head, tail = reason.split("｜", 1)
    extra: list[str] = []
    if "コメント前向き" in tail:
        extra.append("コメント前向き")
    if "コメント慎重" in tail:
        extra.append("コメント慎重")
    if "コメント弱気" in tail:
        extra.append("コメント弱気")
    compact = text(head)
    if extra:
        compact = "・".join([compact, *extra])
    return compact or reason


def build_v2_summary(
    horses: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
    recommendations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(horses, key=v2_sort_key)
    top = ordered[:3]
    condition = [
        horse
        for horse in ordered
        if (to_float(horse.get("v2_condition_score")) or 0.0) >= 2.5
    ]
    pace_plus = [horse for horse in ordered if (to_float(horse.get("v2_pace_score")) or 0.0) > 0]
    state_plus = [horse for horse in ordered if (to_float(horse.get("v2_recent_state_score")) or 0.0) > 0]
    state_minus = [horse for horse in ordered if (to_float(horse.get("v2_recent_state_score")) or 0.0) < 0]
    return {
        "能力": ability_summary(top),
        "再現性": condition_summary(condition, current),
        "展開": pace_summary(pace_plus, current),
        "近走/状態": state_summary(state_plus, state_minus),
        "今回評価": final_summary(recommendations),
        "_top_numbers": [text(horse.get("number")) for horse in recommendations[:5]],
    }


def ability_summary(top: Sequence[Mapping[str, Any]]) -> str:
    if not top:
        return "能力値の取得不足"
    return "上位：" + " / ".join(horse_score_label(horse) for horse in top)


def condition_summary(horses: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> str:
    key = "".join(part for part in [text(current.get("venue")), f"{to_int(current.get('distance'))}m" if to_int(current.get("distance")) else ""] if part)
    if horses:
        return f"{key or '今回条件'}で条件加点あり：{' / '.join(horse_label(horse) for horse in horses[:3])}"
    return f"{key or '今回条件'}で強い条件実績は未確認"


def pace_summary(horses: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> str:
    pace = text(current.get("pace")) or "—"
    if horses:
        return f"想定ペース{pace}。展開加点：{' / '.join(horse_label(horse) for horse in horses[:4])}"
    return f"想定ペース{pace}。大きな展開加点は少なめ"


def state_summary(up: Sequence[Mapping[str, Any]], down: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    if up:
        parts.append("上向き：" + " / ".join(horse_label(horse) for horse in up[:3]))
    if down:
        parts.append("不安：" + " / ".join(horse_label(horse) for horse in down[:3]))
    return "。".join(parts) if parts else "近走/状態の大きな加減点は少なめ"


def final_summary(recommendations: Sequence[Mapping[str, Any]]) -> str:
    if not recommendations:
        return "v2 AI点の結論は未成立"
    axis = recommendations[0]
    others = recommendations[1:5]
    if not others:
        return f"軸：{horse_score_label(axis)}"
    return f"軸：{horse_score_label(axis)}。相手：{' / '.join(horse_score_label(horse) for horse in others)}"


def v2_sort_key(horse: Mapping[str, Any]) -> tuple[float, int]:
    return (
        -float(to_float(horse.get("v2_ai_score")) or 0.0),
        horse_number_sort(horse.get("number")),
    )


def horse_label(horse: Mapping[str, Any]) -> str:
    return " ".join(part for part in [text(horse.get("number")), text(horse.get("name"))] if part)


def horse_score_label(horse: Mapping[str, Any]) -> str:
    label = horse_label(horse)
    score = to_float(horse.get("v2_ai_score"))
    return f"{label} {score:.1f}" if score is not None else label


def same_venue(run: Mapping[str, Any], venue: str) -> bool:
    return venue_key(first(run, "venue", "racecourse", "競馬場", "場所", "previous_track")) == venue


def same_distance(run: Mapping[str, Any], distance: int) -> bool:
    return to_int(first(run, "distance", "距離")) == distance


def race_pace(rows: Sequence[Mapping[str, Any]], race_info: Mapping[str, Any]) -> str:
    for source in (race_info, *(rows or ())):
        if not isinstance(source, Mapping):
            continue
        value = text(first(source, "pace", "provider_pace_market", "pace_scenario_market", "想定ペース", "_netkeiba_pace"))
        if value:
            return normalize_pace(value) or value
    return ""


def normalize_pace(value: Any) -> str:
    value_text = text(value).upper()
    if not value_text:
        return ""
    if re.search(r"\bH\b|ハイ", value_text):
        return "H"
    if re.search(r"\bS\b|スロー", value_text):
        return "S"
    if re.search(r"\bM\b|平均|ミドル", value_text):
        return "M"
    return ""


def normalize_style(value: Any) -> str:
    value_text = text(value)
    if "逃" in value_text:
        return "escape"
    if "先" in value_text:
        return "front"
    if "差" in value_text:
        return "stalker"
    if "追" in value_text:
        return "closer"
    return ""


def training_text(row: Mapping[str, Any]) -> str:
    return text(
        first(
            row,
            "training",
            "training_display",
            "training_short",
            "training_grade",
            "training_market",
            "調教",
            "調教評価",
            "追切評価",
            "調教/評価/検討材料",
        )
    )


def comment_text(row: Mapping[str, Any]) -> str:
    value = text(
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
    if value in {"未取得", "対象外"}:
        return ""
    return value


def training_grade(value: Any) -> str:
    match = re.search(r"\b([ABCD])\b|^([ABCD])", text(value))
    return (match.group(1) or match.group(2)) if match else ""


def horse_number_sort(value: Any) -> int:
    number = to_int(value)
    return number if number is not None else 999
