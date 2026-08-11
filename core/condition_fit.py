# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

from .purchase_conditions import clean_text, to_float
from .recent_races import build_recent_races


CONDITION_FIT_LABELS = {
    "same_venue_distance": ("★", "同会場距離"),
    "same_turn_distance": ("☆", "同回り距離"),
    "same_distance": ("※", "同距離"),
    "none": ("", "条件実績なし"),
}
CONDITION_FIT_PRIORITY = ("same_venue_distance", "same_turn_distance", "same_distance")


def evaluate_condition_fit(
    row: Mapping[str, Any],
    race_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return direct-condition experience labels without changing prediction scores.

    This is display/audit-only.  It uses existing recent-race records and the
    current race metadata that the prediction result already carries.
    """

    current = _current_condition(row, race_info)
    runs = build_recent_races(row)
    matched_by_level: dict[str, list[dict[str, Any]]] = {
        "same_venue_distance": [],
        "same_turn_distance": [],
        "same_distance": [],
    }
    current_distance = current.get("distance")
    for run in runs:
        run_distance = _distance_int(run.get("distance"))
        if current_distance is None or run_distance is None or current_distance != run_distance:
            continue
        run_record = _matched_run_record(run)
        same_venue = bool(current.get("venue") and _venue_key(current.get("venue")) == _venue_key(run.get("venue")))
        same_turn = bool(current.get("turn") and _turn_key(current.get("turn")) == _turn_key(run.get("turn")))
        if same_venue:
            matched_by_level["same_venue_distance"].append(run_record)
        elif same_turn:
            matched_by_level["same_turn_distance"].append(run_record)
        else:
            matched_by_level["same_distance"].append(run_record)

    level = "none"
    matched: list[dict[str, Any]] = []
    for candidate in CONDITION_FIT_PRIORITY:
        if matched_by_level[candidate]:
            level = candidate
            matched = matched_by_level[candidate]
            break

    mark, label = CONDITION_FIT_LABELS[level]
    reason = _reason(level, current, matched)
    return {
        "condition_fit_mark": mark,
        "condition_fit_level": level,
        "condition_fit_label": label,
        "condition_fit_reason": reason,
        "matched_past_runs": matched,
        "current_condition": current,
    }


def condition_fit_badge_text(
    row: Mapping[str, Any],
    race_info: Mapping[str, Any] | None = None,
) -> str:
    result = evaluate_condition_fit(row, race_info)
    mark = clean_text(result.get("condition_fit_mark"))
    label = clean_text(result.get("condition_fit_label"))
    if mark:
        return f"{mark}{label}"
    return f"—{label}" if label else ""


def _current_condition(row: Mapping[str, Any], race_info: Mapping[str, Any] | None) -> dict[str, Any]:
    race_info = race_info or {}
    venue = _first(
        race_info,
        row,
        ("venue", "racecourse", "place", "競馬場", "開催場"),
        ("_racecourse", "_current_racecourse", "_current_venue", "racecourse", "venue", "競馬場", "開催場"),
    )
    distance = _distance_int(
        _first(
            race_info,
            row,
            ("distance", "距離"),
            ("_race_distance", "race_distance", "distance", "距離", "star_max_distance", "_star_max_distance"),
        )
    )
    surface = _first(
        race_info,
        row,
        ("surface", "track_type", "芝ダ", "馬場種別"),
        ("_race_surface", "_current_surface", "surface", "芝ダ", "馬場種別"),
    )
    turn = _first(
        race_info,
        row,
        ("turn", "direction", "回り"),
        ("_race_turn", "_current_turn", "turn", "direction", "回り", "star_max_turn", "_star_max_turn"),
    )
    return {
        "venue": clean_text(venue),
        "surface": clean_text(surface),
        "distance": distance,
        "turn": _turn_key(turn),
    }


def _first(
    race_info: Mapping[str, Any],
    row: Mapping[str, Any],
    info_names: tuple[str, ...],
    row_names: tuple[str, ...],
) -> Any:
    for name in info_names:
        value = race_info.get(name)
        if not _missing(value):
            return value
    for name in row_names:
        value = row.get(name)
        if not _missing(value):
            return value
    return ""


def _matched_run_record(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label": clean_text(run.get("label")),
        "date": clean_text(run.get("date")),
        "venue": clean_text(run.get("venue")),
        "surface": clean_text(run.get("surface")),
        "distance": _distance_int(run.get("distance")),
        "direction": _turn_key(run.get("turn")),
        "race_name": clean_text(run.get("race_name")),
        "finish": clean_text(run.get("finish")),
        "popularity": clean_text(run.get("popularity")),
        "time_index": clean_text(run.get("time_index")),
        "passing_order": clean_text(run.get("passing_order")),
        "running_style": clean_text(run.get("running_style")),
    }


def _reason(level: str, current: Mapping[str, Any], matched: list[dict[str, Any]]) -> str:
    if level == "none":
        distance = f"{current.get('distance')}m" if current.get("distance") is not None else "今回距離"
        return f"{distance}の近3走実績なし"
    first = matched[0] if matched else {}
    distance = f"{current.get('distance')}m" if current.get("distance") is not None else ""
    if level == "same_venue_distance":
        venue = clean_text(first.get("venue") or current.get("venue"))
        return f"{' '.join(part for part in [venue, distance] if part)}の過去走あり"
    if level == "same_turn_distance":
        turn = clean_text(first.get("direction") or current.get("turn"))
        return f"{' '.join(part for part in [turn + '回り' if turn else '', distance] if part)}の過去走あり"
    return f"{distance}の過去走あり" if distance else "同距離の過去走あり"


def _distance_int(value: Any) -> int | None:
    if _missing(value):
        return None
    number = to_float(value)
    if number is not None:
        return int(number)
    match = re.search(r"\d{3,4}", clean_text(value).replace(",", ""))
    return int(match.group(0)) if match else None


def _venue_key(value: Any) -> str:
    text = clean_text(value)
    text = text.replace("競馬場", "").replace("レース場", "")
    return re.sub(r"\s+", "", text)


def _turn_key(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if "右" in text:
        return "右"
    if "左" in text:
        return "左"
    if "直" in text:
        return "直"
    return text


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return clean_text(value).lower() in {"", "-", "—", "nan", "none", "null", "データなし", "未取得"}
