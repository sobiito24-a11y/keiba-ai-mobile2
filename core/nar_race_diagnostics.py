"""NAR race diagnostics built only from saved prediction display values."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .recent_races import build_recent_races


FRONT_LABELS = {"逃げ", "先団", "前方"}
MIDDLE_LABELS = {"中団"}
BACK_LABELS = {"後方"}
POSITION_ORDER = ("front", "middle", "back", "unknown")
POSITION_LABEL_BY_GROUP = {
    "front": "前方",
    "middle": "中団",
    "back": "後方",
    "unknown": "不明",
}
DATA_SHORTAGE_WORDS = ("能力材料不足", "能力評価材料不足", "能力評価なし", "評価不能", "履歴不足", "材料不足")
JRA_VENUES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
COMPARISON_SORT_LABELS = {
    "horse_number": "馬番順",
    "ability": "能力順",
    "current": "今回評価順",
    "corner4_front": "4角前方優先",
}


def build_nar_race_diagnostics(
    rows: Sequence[Mapping[str, Any]],
    *,
    race_mode: str = "nar",
    race_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify NAR horses for display without changing marks or scores."""

    if _text(race_mode).lower() != "nar":
        return {"show": False, "research_only": True}
    horses = [_diagnostic_horse(row) for row in rows if isinstance(row, Mapping)]
    horses = [horse for horse in horses if horse.get("number")]
    if not horses:
        return {"show": False, "research_only": True}

    win_candidates = [horse for horse in horses if _rank_at_most(horse.get("ability_rank"), 3)]
    main_partners = [
        horse
        for horse in horses
        if _rank_at_most(horse.get("ability_rank"), 5) and horse.get("corner4_group") == "front"
    ]
    pace_watch = [horse for horse in horses if horse.get("corner4_group") == "front"]
    ability_outside_watch = [
        horse
        for horse in horses
        if _rank_at_least(horse.get("ability_rank"), 6)
        and (_rank_at_most(horse.get("current_evaluation_rank"), 5) or bool(horse.get("has_recent_top3")))
    ]
    data_insufficient_watch = [horse for horse in horses if horse.get("data_insufficient")]

    positions = {
        point: _position_groups(horses, point)
        for point in ("start", "corner3", "corner4")
    }
    return {
        "show": True,
        "research_only": True,
        "pace": _pace_text(horses, race_info or {}),
        "horses": horses,
        "win_candidates": _sort_horses(win_candidates),
        "main_partners": _sort_horses(main_partners),
        "pace_watch": _sort_horses(pace_watch),
        "ability_outside_watch": _sort_horses(ability_outside_watch),
        "data_insufficient_watch": _sort_horses(data_insufficient_watch),
        "front_at_4c": _sort_horses(pace_watch),
        "positions": positions,
        "summary": {
            "win_candidates": [_short_label(horse) for horse in _sort_horses(win_candidates)],
            "front_at_4c": [_short_label(horse) for horse in _sort_horses(pace_watch)],
            "main_partners": [_short_label(horse) for horse in _sort_horses(main_partners)],
            "ability_outside_watch": [_short_label(horse) for horse in _sort_horses(ability_outside_watch)],
            "data_insufficient_watch": [_short_label(horse) for horse in _sort_horses(data_insufficient_watch)],
        },
    }


def build_nar_full_field_comparison(
    rows: Sequence[Mapping[str, Any]],
    *,
    race_mode: str = "nar",
    sort_mode: str = "horse_number",
) -> dict[str, Any]:
    """Build display-only NAR comparison rows from saved prediction values."""

    if _text(race_mode).lower() != "nar":
        return {"show": False, "research_only": True}
    records = [row for row in rows if isinstance(row, Mapping)]
    horses = [_comparison_horse(row) for row in records]
    horses = [horse for horse in horses if horse.get("number")]
    if not horses:
        return {"show": False, "research_only": True}

    ranked = sorted(
        [horse for horse in horses if horse.get("ability_rank") is not None],
        key=lambda horse: (horse.get("ability_rank") or 999, _horse_sort_key(horse.get("number"))),
    )
    top1 = next((horse for horse in ranked if horse.get("ability_rank") == 1), ranked[0] if ranked else None)
    top2 = next((horse for horse in ranked if horse.get("ability_rank") == 2), ranked[1] if len(ranked) > 1 else None)
    top_value = top1.get("ability_value") if top1 else None
    for horse in horses:
        value = horse.get("ability_value")
        if isinstance(top_value, (int, float)) and isinstance(value, (int, float)):
            horse["ability_gap_from_top"] = value - top_value
            horse["ability_gap_text"] = "0" if abs(value - top_value) < 0.0001 else f"{value - top_value:+.1f}"
        else:
            horse["ability_gap_from_top"] = None
            horse["ability_gap_text"] = "—"

    gap_1_2 = None
    if top1 and top2 and isinstance(top1.get("ability_value"), (int, float)) and isinstance(top2.get("ability_value"), (int, float)):
        gap_1_2 = top1["ability_value"] - top2["ability_value"]

    horses = _sort_comparison_horses(horses, sort_mode)
    transfer_watch = bool(
        top1
        and top2
        and top1.get("transfer_status") == "JRA→NAR初戦"
        and top2.get("transfer_status") != "JRA→NAR初戦"
    )
    return {
        "show": True,
        "research_only": True,
        "sort_mode": sort_mode if sort_mode in COMPARISON_SORT_LABELS else "horse_number",
        "sort_labels": COMPARISON_SORT_LABELS,
        "rows": horses,
        "top1": top1,
        "top2": top2,
        "gap_1_2": gap_1_2,
        "transfer_watch": transfer_watch,
    }


def _comparison_horse(row: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = _diagnostic_horse(row)
    runs = _safe_recent_races(row)
    recent_win_count = 0
    recent_top3_count = 0
    for run in runs:
        finish = _int(_first(run, "finish", "position", "previous_finish", "着順"))
        if finish == 1:
            recent_win_count += 1
        if finish is not None and 1 <= finish <= 3:
            recent_top3_count += 1

    same_distance, same_course, same_turn = _condition_fit_cells(row, diagnostic.get("data_insufficient"))
    transfer_status, local_experience = _transfer_status(runs)
    jockey_rate = _jockey_place_rate(row)
    positive_tags, negative_tags = _comparison_materials(
        diagnostic,
        recent_win_count=recent_win_count,
        recent_top3_count=recent_top3_count,
        same_distance=same_distance,
        same_course=same_course,
        same_turn=same_turn,
        transfer_status=transfer_status,
        has_runs=bool(runs),
    )
    return {
        **diagnostic,
        "odds": _text(_first(row, "actual_odds", "odds", "odds_at_prediction", "saved_odds_at_prediction", "単勝オッズ", "実オッズ")),
        "recent_win_count": recent_win_count,
        "recent_top3_count": recent_top3_count,
        "recent_win_label": "★" * recent_win_count if recent_win_count else "—",
        "recent_top3_label": "★" * recent_top3_count if recent_top3_count else "—",
        "same_distance": same_distance,
        "same_course": same_course,
        "same_turn": same_turn,
        "jockey_course_place_rate": jockey_rate,
        "transfer_status": transfer_status,
        "local_experience": local_experience,
        "positive_tags": positive_tags,
        "negative_tags": negative_tags,
    }


def diagnostic_line(horse: Mapping[str, Any]) -> str:
    parts = [
        f"{_text(horse.get('mark'))}{_text(horse.get('number'))} {_text(horse.get('name'))}".strip(),
        _rank_text("能力", horse.get("ability_rank")),
        _value_text(horse.get("ability_value")),
        _rank_text("今回評価", horse.get("current_evaluation_rank")),
        _text(horse.get("running_style")),
        f"4角：{_text(horse.get('corner4_label')) or '不明'}",
    ]
    return " / ".join(part for part in parts if part)


def category_reason(horse: Mapping[str, Any], category: str) -> str:
    if category == "win":
        return "能力TOP3"
    if category == "partner":
        return "能力TOP5＋4角前方"
    if category == "pace":
        return "4角前方想定"
    if category == "outside":
        reasons = []
        if _rank_at_most(horse.get("current_evaluation_rank"), 5):
            reasons.append("今回評価TOP5")
        if horse.get("has_recent_top3"):
            reasons.append("保存近走3着内")
        return "＋".join(reasons) or "能力外警戒"
    if category == "insufficient":
        return _text(horse.get("data_insufficient_reason")) or "能力評価材料不足"
    return ""


def position_group_label(group: str) -> str:
    return POSITION_LABEL_BY_GROUP.get(group, "不明")


def comparison_position_icon(group: str) -> str:
    return {
        "front": "前方",
        "middle": "中団",
        "back": "後方",
        "unknown": "不明",
    }.get(group, "不明")


def _diagnostic_horse(row: Mapping[str, Any]) -> dict[str, Any]:
    ability_rank = _int(_first(row, "market_ability_rank", "ability_rank", "saved_ability_rank", "能力順位"))
    ability_value = _float(_first(row, "market_ability_score", "ability_value", "saved_ability_value", "ability_display_score", "能力評価値"))
    current_rank = _int(_first(row, "current_evaluation_rank", "saved_current_evaluation_rank", "今回評価順位", "今回順位", "ai_current_rank"))
    start_label = _position_label(row, "start")
    corner3_label = _position_label(row, "corner3")
    corner4_label = _position_label(row, "corner4")
    has_recent = _has_recent_top3(row)
    insufficient, reason = _data_insufficient(row, ability_rank, ability_value)
    return {
        "number": _horse_number(_first(row, "馬番", "馬", "horse_no", "horse_number", "number")),
        "name": _text(_first(row, "馬名", "horse_name", "name")),
        "mark": _text(_first(row, "ai_current_mark", "mark", "saved_mark", "表示印", "display_mark", "最終印", "印")),
        "ability_rank": ability_rank,
        "ability_value": ability_value,
        "current_evaluation_rank": current_rank,
        "running_style": _text(_first(row, "running_style_market", "running_style", "脚質")),
        "start_label": start_label,
        "corner3_label": corner3_label,
        "corner4_label": corner4_label,
        "start_group": normalize_position_group(start_label),
        "corner3_group": normalize_position_group(corner3_label),
        "corner4_group": normalize_position_group(corner4_label),
        "has_recent_top3": has_recent,
        "data_insufficient": insufficient,
        "data_insufficient_reason": reason,
    }


def normalize_position_group(value: Any) -> str:
    text = _text(value)
    if not text:
        return "unknown"
    parts = [part.strip() for part in re.split(r"→|>|/|／", text) if part.strip()]
    label = parts[-1] if parts else text
    if label in FRONT_LABELS:
        return "front"
    if label in MIDDLE_LABELS:
        return "middle"
    if label in BACK_LABELS:
        return "back"
    if any(token in label for token in ("逃げ", "先団", "前方")):
        return "front"
    if "中団" in label:
        return "middle"
    if "後方" in label:
        return "back"
    return "unknown"


def _position_label(row: Mapping[str, Any], point: str) -> str:
    point_keys = {
        "start": ("position_start_label_market", "_estimated_position_start_label", "start_position_label", "start_evaluation"),
        "corner3": ("position_corner3_label_market", "_estimated_position_corner3_label", "corner3_position_label"),
        "corner4": ("position_corner4_label_market", "_estimated_position_corner4_label", "corner4_position_label", "corner4_evaluation"),
    }
    direct = _text(_first(row, *point_keys.get(point, ())))
    if direct and direct not in {"位置不明", "未取得"} and "top=" not in direct and "left=" not in direct:
        return direct
    path = _text(_first(row, "position_path_market", "estimated_position", "saved_estimated_position", "estimated_position_label", "想定位置", "推定位置"))
    if path and "top=" not in path and "left=" not in path:
        parts = [part.strip() for part in re.split(r"→|>|/|／", path) if part.strip()]
        indexes = {"start": 0, "corner3": 1, "corner4": 2}
        index = indexes.get(point, 0)
        if len(parts) > index:
            return parts[index]
        if point == "corner4" and parts:
            return parts[-1]
    return ""


def _position_groups(horses: Sequence[Mapping[str, Any]], point: str) -> dict[str, list[dict[str, str]]]:
    result = {group: [] for group in POSITION_ORDER}
    for horse in horses:
        group = _text(horse.get(f"{point}_group")) or "unknown"
        if group not in result:
            group = "unknown"
        result[group].append(
            {
                "number": _text(horse.get("number")),
                "mark": _text(horse.get("mark")),
                "name": _text(horse.get("name")),
            }
        )
    for group in result:
        result[group].sort(key=lambda item: _horse_sort_key(item.get("number")))
    return result


def _sort_comparison_horses(horses: Sequence[Mapping[str, Any]], sort_mode: str) -> list[Mapping[str, Any]]:
    mode = sort_mode if sort_mode in COMPARISON_SORT_LABELS else "horse_number"
    if mode == "ability":
        key = lambda horse: (
            horse.get("ability_rank") if horse.get("ability_rank") is not None else 999,
            _horse_sort_key(horse.get("number")),
        )
    elif mode == "current":
        key = lambda horse: (
            horse.get("current_evaluation_rank") if horse.get("current_evaluation_rank") is not None else 999,
            horse.get("ability_rank") if horse.get("ability_rank") is not None else 999,
            _horse_sort_key(horse.get("number")),
        )
    elif mode == "corner4_front":
        group_order = {"front": 0, "middle": 1, "back": 2, "unknown": 3}
        key = lambda horse: (
            group_order.get(_text(horse.get("corner4_group")), 3),
            horse.get("ability_rank") if horse.get("ability_rank") is not None else 999,
            _horse_sort_key(horse.get("number")),
        )
    else:
        key = lambda horse: _horse_sort_key(horse.get("number"))
    return sorted(horses, key=key)


def _safe_recent_races(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        return build_recent_races(row)
    except Exception:
        return []


def _condition_fit_cells(row: Mapping[str, Any], data_insufficient: Any) -> tuple[str, str, str]:
    level = _text(_first(row, "condition_fit_level", "condition_fit_level_market"))
    mark = _text(_first(row, "condition_fit_mark", "condition_mark_market", "condition_fit_badge", "条件実績マーク"))
    if "★" in mark or level == "same_venue_distance":
        return "★", "★", "★"
    if "☆" in mark or level == "same_turn_distance":
        return "★", "—", "★"
    if "※" in mark or level == "same_distance":
        return "★", "—", "—"
    if data_insufficient:
        return "?", "?", "?"
    return "—", "—", "—"


def _transfer_status(runs: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    venues = [_text(_first(run, "venue", "racecourse", "track", "競馬場")) for run in runs]
    venues = [venue for venue in venues if venue]
    if not venues:
        return "判定不明", "判定不明"
    jra_count = sum(1 for venue in venues if venue in JRA_VENUES)
    local_count = sum(1 for venue in venues if venue and venue not in JRA_VENUES)
    if jra_count and local_count == 0:
        return "JRA→NAR初戦", "初戦"
    if local_count == 1:
        return "地方実績1走", "地方実績1走"
    if local_count == 2:
        return "地方実績2走", "地方実績2走"
    if local_count >= 3:
        return "地方実績十分", "地方実績十分"
    return "判定不明", "判定不明"


def _jockey_place_rate(row: Mapping[str, Any]) -> str:
    rate = _float(_first(row, "_jockey_course_place_rate", "jockey_course_place_rate", "騎手コース複勝率"))
    if rate is None:
        stats = _text(_first(row, "jockey_course_stats_market", "jockey_course_stats", "saved_jockey_course_stats", "騎手コース成績"))
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", stats)
        if len(matches) >= 3:
            rate = _float(matches[2])
        elif len(matches) == 1 and "複" in stats:
            rate = _float(matches[0])
    if rate is None:
        return "—"
    if 0 < rate < 1:
        rate *= 100
    return f"{rate:.0f}%" if float(rate).is_integer() else f"{rate:.1f}%"


def _comparison_materials(
    horse: Mapping[str, Any],
    *,
    recent_win_count: int,
    recent_top3_count: int,
    same_distance: str,
    same_course: str,
    same_turn: str,
    transfer_status: str,
    has_runs: bool,
) -> tuple[list[str], list[str]]:
    plus: list[str] = []
    minus: list[str] = []
    if horse.get("corner4_group") == "front":
        plus.append("4角前方")
    if horse.get("corner4_group") == "back":
        minus.append("4角後方")
    if recent_win_count:
        plus.append("近走勝利")
    if recent_top3_count:
        plus.append("近走3着内")
    elif has_runs:
        minus.append("近走好走なし")
    if same_distance == "★":
        plus.append("同距離")
    if same_course == "★":
        plus.append("同コース")
    elif same_course == "—":
        minus.append("コース実績なし")
    if same_turn == "★":
        plus.append("同回り")
    if _rank_at_most(horse.get("current_evaluation_rank"), 3):
        plus.append("今回評価TOP3")
    if horse.get("data_insufficient"):
        minus.append("能力材料不足")
    if transfer_status == "JRA→NAR初戦":
        minus.append("JRA→NAR初戦")
    return _unique(plus), _unique(minus)


def _has_recent_top3(row: Mapping[str, Any]) -> bool:
    runs = _safe_recent_races(row)
    for run in runs:
        finish = _int(_first(run, "finish", "position", "previous_finish", "着順"))
        if finish is not None and 1 <= finish <= 3:
            return True
    return False


def _data_insufficient(row: Mapping[str, Any], ability_rank: int | None, ability_value: float | None) -> tuple[bool, str]:
    if ability_value is None:
        return True, "能力評価材料不足"
    if ability_rank is None:
        return True, "能力順位なし"
    checks = [
        _first(row, "ability_band_reason", "ability_watch_label", "能力注記", "ability_status"),
        _first(row, "plus_materials_display", "minus_materials_display", "ai_current_reason"),
    ]
    joined = " ".join(_text(value) for value in checks if _text(value))
    for word in DATA_SHORTAGE_WORDS:
        if word in joined:
            return True, word
    return False, ""


def _pace_text(horses: Sequence[Mapping[str, Any]], race_info: Mapping[str, Any]) -> str:
    for source in (race_info, *(horses or ())):
        pace = _text(_first(source, "pace", "provider_pace_market", "pace_scenario_market", "想定ペース"))
        if pace:
            match = re.search(r"\b([HMS])\b", pace.upper())
            return match.group(1) if match else pace
    return "—"


def _sort_horses(horses: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        horses,
        key=lambda horse: (
            horse.get("ability_rank") if horse.get("ability_rank") is not None else 999,
            horse.get("current_evaluation_rank") if horse.get("current_evaluation_rank") is not None else 999,
            _horse_sort_key(horse.get("number")),
        ),
    )


def _unique(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _rank_text(label: str, value: Any) -> str:
    rank = _int(value)
    return f"{label}{rank}位" if rank is not None else ""


def _value_text(value: Any) -> str:
    number = _float(value)
    if number is None:
        return ""
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _short_label(horse: Mapping[str, Any]) -> str:
    return f"{_text(horse.get('mark'))}{_text(horse.get('number'))}".strip()


def _rank_at_most(value: Any, limit: int) -> bool:
    rank = _int(value)
    return rank is not None and rank <= limit


def _rank_at_least(value: Any, limit: int) -> bool:
    rank = _int(value)
    return rank is not None and rank >= limit


def _horse_sort_key(value: Any) -> int:
    number = _int(value)
    return number if number is not None else 999


def _horse_number(value: Any) -> str:
    number = _float(value)
    if number is not None and float(number).is_integer():
        return str(int(number))
    return _text(value)


def _first(values: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if not key:
            continue
        value = values.get(key)
        if _text(value):
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    text = _text(value)
    if not text or text.lower() in {"nan", "none", "null", "—", "-", "未取得", "位置不明"}:
        return None
    text = text.replace(",", "").replace("倍", "").replace("位", "").replace("着", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None
