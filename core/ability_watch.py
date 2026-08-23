from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd


MARKED_SYMBOLS = {"◎", "○", "▲", "△", "☆"}
JRA_MARKET_SUPPORT_ODDS = 10.0


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if _text(value):
                return value
    return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("倍", "").strip()
        if not value or value in {"—", "-", "未取得", "nan", "None"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def ability_watch_rows(rows: Iterable[Mapping[str, Any]], *, race_mode: str = "jra") -> list[dict[str, Any]]:
    source = [dict(row) for row in rows]
    ability_values = [
        _float(_first(row, "market_ability_score", "ability_value", "能力評価値", "ability_score"))
        for row in source
    ]
    ranked_values = sorted((value for value in ability_values if value is not None), reverse=True)
    ability_gap_1_2 = None
    if len(ranked_values) >= 2:
        ability_gap_1_2 = ranked_values[0] - ranked_values[1]

    result: list[dict[str, Any]] = []
    for row in source:
        mark = _text(_first(row, "ai_current_mark", "mark", "印", "display_mark"))
        ability_rank = _int(_first(row, "market_ability_rank", "ability_rank", "能力順位"))
        ability_value = _float(_first(row, "market_ability_score", "ability_value", "能力評価値", "ability_score"))
        odds = _float(_first(row, "actual_odds", "odds", "オッズ", "単勝オッズ"))
        is_marked = mark in MARKED_SYMBOLS
        top_match = ability_rank == 1 and mark == "◎"
        top3_unmarked = ability_rank is not None and ability_rank <= 3 and not is_marked
        market_supported = (
            _text(race_mode).lower() == "jra"
            and not is_marked
            and odds is not None
            and odds <= JRA_MARKET_SUPPORT_ODDS
        )
        high_risk = bool(top3_unmarked and market_supported)

        if high_risk:
            warning = "⚠ 要注意の無印（能力上位＋市場支持）"
        elif top3_unmarked:
            warning = "⚠ 能力上位の無印"
        elif market_supported:
            warning = "⚠ 市場支持ありの無印"
        else:
            warning = ""

        top_label = ""
        if top_match:
            if ability_gap_1_2 is None:
                top_label = "能力1位＝◎"
            else:
                top_label = f"能力1位＝◎ / 2位との差 +{ability_gap_1_2:.1f}"

        result.append(
            {
                "ability_top_match": top_match,
                "ability_top3_unmarked": bool(top3_unmarked),
                "market_supported_unmarked": bool(market_supported),
                "high_risk_unmarked": high_risk,
                "ability_gap_1_2": ability_gap_1_2,
                "ability_watch_label": top_label or warning,
                "ability_unmarked_warning": warning,
                "ability_top_match_label": top_label,
                "ability_watch_audit": {
                    "mark": mark,
                    "ability_rank": ability_rank,
                    "ability_value": ability_value,
                    "saved_odds": odds,
                    "race_mode": _text(race_mode).lower(),
                },
            }
        )
    return result


def attach_ability_watch_columns(table: pd.DataFrame, *, race_mode: str = "jra") -> pd.DataFrame:
    if table.empty:
        return table.copy()
    annotated = table.copy()
    watch_rows = ability_watch_rows(annotated.to_dict("records"), race_mode=race_mode)
    for key in (
        "ability_top_match",
        "ability_top3_unmarked",
        "market_supported_unmarked",
        "high_risk_unmarked",
        "ability_gap_1_2",
        "ability_watch_label",
        "ability_unmarked_warning",
        "ability_top_match_label",
        "ability_watch_audit",
    ):
        annotated[key] = [row[key] for row in watch_rows]
    return annotated
