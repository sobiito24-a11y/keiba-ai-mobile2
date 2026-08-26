from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


MARK_ORDER = ("◎", "○", "▲", "△", "☆")
JRA_MOBILE_RULE_ID = "JRA_R100_V1"
NAR_RULE_ID = "NAR_VER4_AXIS_ML_2_4_V1"
JRA_DASHBOARD_RULE_ID = "JRA_DASH_GUIDE_V1"
JRA_TRIO_ODDS_MIN = 5.0
JRA_TRIO_ODDS_MAX = 10.0
NAR_AXIS_ODDS_MAX = 2.4
NAR_MARK_BY_RANK = {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "☆"}


def build_research_bet(
    rows: Iterable[Mapping[str, Any]],
    race_mode: str,
    *,
    context: str = "mobile",
) -> dict[str, Any]:
    source = [dict(row) for row in rows]
    mode = _text(race_mode).lower()
    by_mark = _rows_by_mark(source)
    if mode == "nar":
        return _nar_research_bet(source)
    axis = by_mark.get("◎")
    if axis is None:
        return _empty("◎不在")
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


def _nar_research_bet(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    ranked = _nar_ranked_rows(rows)
    if any(rank not in ranked for rank in range(1, 6)):
        return _empty("NAR能力順位1〜5位不足")

    axis = ranked[1]
    odds = _valid_odds(_first(axis, "actual_odds", "odds_at_prediction", "odds", "オッズ", "単勝オッズ"))
    monitor = _nar_monitor_lines(rows, ranked)
    base = {
        "show": True,
        "research_rule_id": NAR_RULE_ID,
        "research_bet_mode": "NAR",
        "title": "🧪 NAR Ver4研究ガイド",
        "total": 0,
        "note": "NAR Ver4として未見100R検証中",
        "trio_condition": "",
        "is_valid_odds": odds is not None,
        "odds_available": odds is not None,
        "nar_research_eligible": False,
        "research_status": "",
        "ticket_lines": [],
        "total_stake": 0,
        "monitor_lines": monitor["lines"],
        "monitor_flags": monitor["flags"],
        "monitor_note": "※研究中指標。購入条件ではありません。",
    }
    if odds is None:
        return {
            **base,
            "lines": [
                "【オッズ確定後ルール】",
                "◎2.4倍以下 → 馬連 ◎－○▲△☆ 各100円",
                "◎2.5倍以上 → 研究買い条件外",
                "現在：オッズ未取得",
            ],
            "reason": "オッズ確定後に判定",
            "research_status": "waiting_odds",
        }
    if odds <= NAR_AXIS_ODDS_MAX:
        ticket_lines = _nar_quinella_lines(ranked)
        return {
            **base,
            "lines": [
                "✅ 研究買い条件",
                f"◎{_horse_label(axis)}",
                f"保存オッズ：{_odds_value_text(odds)}",
                "馬連",
                *ticket_lines,
            ],
            "total": 400,
            "reason": "低オッズ◎＝連系軸の未見100R検証中",
            "nar_research_eligible": True,
            "research_status": "eligible",
            "ticket_lines": ticket_lines,
            "total_stake": 400,
        }
    return {
        **base,
        "lines": [
            "今回は研究買い条件外",
            f"◎{_horse_label(axis)}",
            f"保存オッズ：{_odds_value_text(odds)}",
            "現時点では3倍以上の◎について再現性ある固定購入ルールは未確定です。",
            "NAR Ver4予想自体は有効です。",
        ],
        "reason": "◎オッズが2.4倍を超過",
        "research_status": "out_of_rule",
    }


def _nar_ranked_rows(rows: list[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    ranked: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        rank = _int(_first(row, "market_ability_rank", "ability_rank", "能力順位"))
        if rank in NAR_MARK_BY_RANK and rank not in ranked:
            ranked[rank] = row
    return ranked


def _nar_quinella_lines(ranked: Mapping[int, Mapping[str, Any]]) -> list[str]:
    axis_no = _horse_number(ranked[1])
    lines: list[str] = []
    for rank in range(2, 6):
        mark = NAR_MARK_BY_RANK[rank]
        opponent_no = _horse_number(ranked[rank])
        lines.append(f"◎－{mark} {axis_no}-{opponent_no} 100円")
    return lines


def _nar_monitor_lines(rows: list[Mapping[str, Any]], ranked: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    ability_numbers = [_horse_number(ranked[rank]) for rank in range(1, 6)]
    current_ranked: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        rank = _int(_first(row, "current_evaluation_rank", "今回評価順位", "今回順位"))
        if rank in NAR_MARK_BY_RANK and rank not in current_ranked:
            current_ranked[rank] = row
    current_numbers = [_horse_number(current_ranked[rank]) for rank in range(1, 6) if rank in current_ranked]
    top5_match = len(current_numbers) == 5 and ability_numbers == current_numbers

    axis = ranked[1]
    axis_confidence = _text(_first(axis, "axis_confidence", "axis_confidence_v4", "軸信頼度"))
    axis_a = axis_confidence == "A"

    score1 = _float(_first(ranked[1], "market_ability_score", "ability_value", "ability_display_score", "能力評価値"))
    score2 = _float(_first(ranked[2], "market_ability_score", "ability_value", "ability_display_score", "能力評価値"))
    gap = None if score1 is None or score2 is None else score1 - score2
    gap10 = gap is not None and gap >= 10.0

    return {
        "lines": [
            ("✓" if top5_match else "－") + " 能力TOP5・今回評価TOP5一致",
            ("✓" if axis_a else "－") + " axis confidence A",
            ("✓" if gap10 else "－") + " 能力1-2位差 10以上",
        ],
        "flags": {
            "ability_current_top5_match": top5_match,
            "axis_confidence_a": axis_a,
            "ability_gap_1_2_ge_10": gap10,
            "ability_gap_1_2": gap,
        },
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


def _odds_value_text(odds: float) -> str:
    return f"{odds:.1f}倍"


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
        "is_valid_odds": False,
        "odds_available": False,
        "nar_research_eligible": False,
        "research_status": "unavailable",
        "ticket_lines": [],
        "total_stake": 0,
        "monitor_lines": [],
        "monitor_flags": {},
        "monitor_note": "",
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
        if not value or value.lower() in {"—", "-", "未取得", "nan", "none"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _valid_odds(value: Any) -> float | None:
    number = _float(value)
    return number if number is not None and number > 0 else None
