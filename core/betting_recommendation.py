# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BettingRecommendation:
    ticket_type: str
    label: str
    stars: str
    expected_roi: float | None
    condition: str
    reason: str


RECOMMENDATION_RULES = {
    "win_ai3_value": {
        "ticket_type": "単勝",
        "label": "AI3位",
        "condition": "AI3位 / オッズ8〜20倍",
        "expected_roi": 289.0,
    },
    "win_ai1_value": {
        "ticket_type": "単勝",
        "label": "AI1位",
        "condition": "AI1位 / オッズ8〜20倍",
        "expected_roi": 263.0,
    },
    "wide_ss_c": {
        "ticket_type": "ワイド",
        "label": "SS-C",
        "condition": "SSとC穴候補の組み合わせ",
        "expected_roi": 133.0,
    },
    "trio_ss_a_b_c": {
        "ticket_type": "三連複",
        "label": "SS/A→A/B→SS/A/B/C",
        "condition": "SS・A本線にB/Cを絡める形",
        "expected_roi": 269.0,
    },
}


def build_betting_recommendations(table: Any, *, max_items: int = 3) -> list[BettingRecommendation]:
    """Build display-only betting hints from existing prediction columns.

    The hints use saved JRA audit baselines, but never feed back into AI scores,
    marks, parser output, or ticket generation logic.
    """

    if table is None or not isinstance(table, pd.DataFrame) or table.empty:
        return []
    rows = [dict(row) for row in table.to_dict("records")]
    recommendations: list[BettingRecommendation] = []

    ai3 = _find_by_ai_rank(rows, 3)
    if ai3 and _odds_in_range(ai3, 8.0, 20.0):
        rule = RECOMMENDATION_RULES["win_ai3_value"]
        recommendations.append(_build(rule, f"{_horse_label(ai3)}がAI3位かつ実測妙味帯です。"))

    ai1 = _find_by_ai_rank(rows, 1)
    if ai1 and _odds_in_range(ai1, 8.0, 20.0):
        rule = RECOMMENDATION_RULES["win_ai1_value"]
        recommendations.append(_build(rule, f"{_horse_label(ai1)}がAI1位で、単勝妙味帯に入っています。"))

    ss = _rows_by_group(rows, "SS")
    group_a = _rows_by_group(rows, "A")
    group_b = _rows_by_group(rows, "B")
    group_c = _rows_by_group(rows, "C")
    if ss and group_c:
        rule = RECOMMENDATION_RULES["wide_ss_c"]
        recommendations.append(_build(rule, f"{_horse_label(ss[0])}からC穴候補をワイドで確認。"))
    if ss and group_a and (group_b or group_c):
        rule = RECOMMENDATION_RULES["trio_ss_a_b_c"]
        recommendations.append(_build(rule, "軸・相手本線に押さえ/穴を絡める実測上位パターンです。"))
    return recommendations[:max_items]


def _build(rule: dict[str, Any], reason: str) -> BettingRecommendation:
    roi = _to_float(rule.get("expected_roi"))
    return BettingRecommendation(
        ticket_type=str(rule["ticket_type"]),
        label=str(rule["label"]),
        stars=_stars_for_roi(roi),
        expected_roi=roi,
        condition=str(rule["condition"]),
        reason=reason,
    )


def _find_by_ai_rank(rows: list[dict[str, Any]], rank: int) -> dict[str, Any] | None:
    for row in rows:
        value = _to_float(_pick(row, "ai_rank", "AI順位", "AI点順位"))
        if value is not None and int(value) == rank:
            return row
    return None


def _rows_by_group(rows: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    return [row for row in rows if _text(_pick(row, "display_group", "グループ")) == group]


def _odds_in_range(row: dict[str, Any], low: float, high: float) -> bool:
    odds = _to_float(_pick(row, "単勝オッズ", "オッズ", "odds"))
    return odds is not None and low <= odds <= high


def _stars_for_roi(roi: float | None) -> str:
    if roi is None:
        return "★★★☆☆"
    if roi >= 150:
        return "★★★★★"
    if roi >= 120:
        return "★★★★☆"
    if roi >= 100:
        return "★★★☆☆"
    if roi >= 80:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def _horse_label(row: dict[str, Any]) -> str:
    no = _text(_pick(row, "馬番", "馬", "horse_no"))
    name = _text(_pick(row, "馬名", "horse_name"))
    return " ".join(part for part in [no, name] if part)


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and not _is_missing(row.get(name)):
            return row.get(name)
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return _text(value).lower() in {"", "-", "—", "nan", "none", "null"}


def _to_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(str(value).replace(",", "").replace("倍", "").strip())
    except ValueError:
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
