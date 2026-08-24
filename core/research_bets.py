from __future__ import annotations

from typing import Any, Iterable, Mapping


MARK_ORDER = ("◎", "○", "▲", "△", "☆")
JRA_MOBILE_RULE_ID = "JRA_R100_V1"
NAR_RULE_ID = "NAR_V4_R100_V1"
JRA_DASHBOARD_RULE_ID = "JRA_DASH_GUIDE_V1"
JRA_TRIO_ODDS_MIN = 5.0
JRA_TRIO_ODDS_MAX = 10.0


def build_research_bet(
    rows: Iterable[Mapping[str, Any]],
    race_mode: str,
    *,
    context: str = "mobile",
) -> dict[str, Any]:
    source = [dict(row) for row in rows]
    mode = _text(race_mode).lower()
    by_mark = _rows_by_mark(source)
    axis = by_mark.get("◎")
    if axis is None:
        return _empty("◎不在")
    if mode == "nar":
        return _nar_research_bet(axis)
    if context == "dashboard":
        return _jra_dashboard_guide(source, by_mark, axis)
    return _jra_mobile_research_bet(by_mark, axis)


def _jra_mobile_research_bet(by_mark: Mapping[str, Mapping[str, Any]], axis: Mapping[str, Any]) -> dict[str, Any]:
    odds = _float(_first(axis, "actual_odds", "odds_at_prediction", "odds", "オッズ", "単勝オッズ"))
    axis_label = _horse_label(axis)
    lines = [f"◎{axis_label} 単勝 500円"]
    total = 500
    if odds is None:
        trio_condition = "3連複条件：保存◎オッズ未取得"
    elif JRA_TRIO_ODDS_MIN <= odds < JRA_TRIO_ODDS_MAX:
        trio = _trio_candidates(by_mark)
        if trio:
            lines.append("3連複 各100円")
            lines.extend(trio)
            total += len(trio) * 100
            trio_condition = "3連複条件：対象"
        else:
            trio_condition = "3連複条件：印不足のため対象外"
    else:
        trio_condition = "3連複条件：対象外"
    return {
        "show": True,
        "research_rule_id": JRA_MOBILE_RULE_ID,
        "research_bet_mode": "JRA_MOBILE",
        "title": "🧪 JRA研究買い",
        "lines": lines,
        "total": total,
        "reason": "未見100R検証中",
        "note": _odds_text(odds),
        "trio_condition": trio_condition,
    }


def _jra_dashboard_guide(
    rows: list[Mapping[str, Any]],
    by_mark: Mapping[str, Mapping[str, Any]],
    axis: Mapping[str, Any],
) -> dict[str, Any]:
    ability_top = _ability_top_row(rows)
    top_number = _horse_number(ability_top or {})
    axis_number = _horse_number(axis)
    top_matches = bool(top_number and axis_number and top_number == axis_number)
    lines = [f"◎{_horse_label(axis)} 単勝 500円"]
    trio = _trio_candidates(by_mark)
    if trio:
        lines.append("参考：3連複研究候補5点")
        lines.extend(trio)
    reason = "能力1位＝◎" if top_matches else "能力1位と◎は不一致 / ⚠ 能力1位も要確認"
    return {
        "show": True,
        "research_rule_id": JRA_DASHBOARD_RULE_ID,
        "research_bet_mode": "JRA_DASHBOARD_GUIDE",
        "title": "🧪 Dashboard研究ガイド",
        "lines": lines,
        "total": 500,
        "reason": reason,
        "note": "未見100R検証中",
        "trio_condition": "3連複は参考候補",
    }


def _nar_research_bet(axis: Mapping[str, Any]) -> dict[str, Any]:
    if _int(_first(axis, "market_ability_rank", "ability_rank", "能力順位")) != 1:
        return _empty("能力順位1位の◎不在")
    return {
        "show": True,
        "research_rule_id": NAR_RULE_ID,
        "research_bet_mode": "NAR",
        "title": "🧪 NAR研究買い",
        "lines": [f"◎{_horse_label(axis)} 単勝 500円"],
        "total": 500,
        "reason": "能力順位1位を本命採用",
        "note": "NAR Ver4として未見100R検証中",
        "trio_condition": "",
    }


def _trio_candidates(by_mark: Mapping[str, Mapping[str, Any]]) -> list[str]:
    patterns = (("◎", "○", "▲"), ("◎", "○", "△"), ("◎", "○", "☆"), ("◎", "▲", "△"), ("◎", "▲", "☆"))
    lines: list[str] = []
    for marks in patterns:
        if all(mark in by_mark for mark in marks):
            numbers = "-".join(_horse_number(by_mark[mark]) for mark in marks)
            lines.append(f"{'－'.join(marks)} {numbers}")
    return lines


def _rows_by_mark(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        mark = _mark(row)
        if mark in MARK_ORDER and mark not in result:
            result[mark] = row
    return result


def _ability_top_row(rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for row in rows:
        if _int(_first(row, "market_ability_rank", "ability_rank", "能力順位")) == 1:
            return row
    return None


def _mark(row: Mapping[str, Any]) -> str:
    mark = _text(_first(row, "ai_current_mark", "mark", "印", "display_mark", "表示印", "最終印", "old_final_mark"))
    return mark if mark in MARK_ORDER else ""


def _horse_label(row: Mapping[str, Any]) -> str:
    number = _horse_number(row)
    name = _text(_first(row, "馬名", "horse_name", "name"))
    return f"{number} {name}".strip()


def _horse_number(row: Mapping[str, Any]) -> str:
    value = _first(row, "馬番", "馬", "horse_no", "horse_number", "number")
    number = _float(value)
    if number is not None and number.is_integer():
        return str(int(number))
    return _text(value)


def _odds_text(odds: float | None) -> str:
    return "保存◎オッズ：未取得" if odds is None else f"保存◎オッズ：{odds:.1f}倍"


def _empty(reason: str) -> dict[str, Any]:
    return {
        "show": False,
        "research_rule_id": "",
        "research_bet_mode": "",
        "title": "",
        "lines": [],
        "total": 0,
        "reason": reason,
        "note": "",
        "trio_condition": "",
    }


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if _text(value):
                return value
    return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("倍", "").strip()
        if not value or value in {"—", "-", "未取得", "nan", "None"}:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)
