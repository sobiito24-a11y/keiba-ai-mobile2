# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .purchase_conditions import (
    ASSETS_ANALYSIS_DIR,
    DEFAULT_REPORT_DIR,
    ConditionSpec,
    condition_mask,
    enrich_current_table,
    to_float,
)
from .ticket_strategy_analysis import build_tickets_for_race, unique_nums


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS_JSON = ASSETS_ANALYSIS_DIR / "betting_recommendations.json"
LEGACY_TICKET_JSON = DEFAULT_REPORT_DIR / "ticket_strategy_ranked.json"
LEGACY_CONDITION_JSON = DEFAULT_REPORT_DIR / "purchase_condition_ranked.json"


@dataclass(frozen=True)
class BettingRecommendation:
    ticket_type: str
    label: str
    stars: str
    expected_roi: float | None
    condition: str
    reason: str
    source: str = "fixed"
    risk_label: str = ""


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
        "label": "SS/A→B→SS/A/B/C",
        "condition": "SS・A本線にB/Cを絡める形",
        "expected_roi": 269.0,
    },
}


LAST_LOAD_DIAGNOSTIC: dict[str, Any] = {}


def build_betting_recommendations(
    table: Any,
    *,
    max_items: int = 4,
    json_paths: list[Path] | None = None,
) -> list[BettingRecommendation]:
    """Build display-only betting hints.

    Analysis JSON is preferred when available.  The old fixed rules are used
    only when no JSON exists, so stale hard-coded ROI does not mask a broken
    or newer analysis file.
    """

    if table is None or not isinstance(table, pd.DataFrame) or table.empty:
        return []

    payload, diagnostic = load_recommendation_payload(json_paths)
    LAST_LOAD_DIAGNOSTIC.clear()
    LAST_LOAD_DIAGNOSTIC.update(diagnostic)
    if payload is not None:
        return build_recommendations_from_payload(table, payload, max_items=max_items)
    if diagnostic.get("status") == "parse_error":
        return []
    return build_fixed_betting_recommendations(table, max_items=max_items)


def load_recommendation_payload(json_paths: list[Path] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    paths = json_paths if json_paths is not None else [DEFAULT_ANALYSIS_JSON, LEGACY_TICKET_JSON, LEGACY_CONDITION_JSON]
    diagnostics: list[dict[str, Any]] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            diagnostics.append({"path": str(path), "status": "missing"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return None, {
                "status": "parse_error",
                "path": str(path),
                "fallback_reason": f"analysis json parse failed: {exc}",
                "checked": diagnostics,
            }
        recommendations = payload.get("recommendations")
        return payload, {
            "status": "loaded",
            "path": str(path),
            "mtime": path.stat().st_mtime,
            "recommendation_count": len(recommendations) if isinstance(recommendations, list) else 0,
            "source_race_count": (payload.get("source") or payload.get("meta") or {}).get("race_count")
            or (payload.get("source") or {}).get("source_race_count"),
            "checked": diagnostics,
        }
    return None, {
        "status": "missing",
        "path": "",
        "fallback_reason": "analysis json not found",
        "checked": diagnostics,
    }


def build_recommendations_from_payload(
    table: pd.DataFrame,
    payload: dict[str, Any],
    *,
    max_items: int,
) -> list[BettingRecommendation]:
    current = enrich_current_table(table)
    raw_items = payload.get("recommendations", [])
    if not isinstance(raw_items, list):
        return []

    matched: list[BettingRecommendation] = []
    used_types: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if not is_displayable_payload_item(item):
            continue
        recommendation = match_payload_item(current, item)
        if recommendation is None:
            continue
        # Keep the section varied; do not fill all slots with one ticket type.
        if recommendation.ticket_type in used_types and len(used_types) < max_items:
            continue
        matched.append(recommendation)
        used_types.add(recommendation.ticket_type)
        if len(matched) >= max_items:
            break

    if len(matched) < max_items:
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            if not is_displayable_payload_item(item):
                continue
            recommendation = match_payload_item(current, item)
            if recommendation is None or recommendation in matched:
                continue
            matched.append(recommendation)
            if len(matched) >= max_items:
                break
    return matched[:max_items]


def is_displayable_payload_item(item: dict[str, Any]) -> bool:
    risk = str(item.get("risk_label") or item.get("ranking_type") or "")
    roi = to_float(item.get("return_rate"))
    if roi is None:
        roi = max(to_float(item.get("win_roi")) or 0.0, to_float(item.get("place_roi")) or 0.0)
    if roi <= 0:
        return False
    if risk == "高リスク" and roi < 120:
        return False
    return True


def match_payload_item(current: pd.DataFrame, item: dict[str, Any]) -> BettingRecommendation | None:
    kind = str(item.get("recommendation_kind") or item.get("kind") or "")
    if kind == "ticket_strategy" or item.get("role_pattern"):
        return match_ticket_strategy_item(current, item)
    if item.get("conditions"):
        return match_purchase_condition_item(current, item)
    return None


def match_ticket_strategy_item(current: pd.DataFrame, item: dict[str, Any]) -> BettingRecommendation | None:
    ticket_type = str(item.get("ticket_type") or "")
    pattern = item.get("role_pattern")
    if not ticket_type or not isinstance(pattern, dict):
        return None
    tickets = build_tickets_for_race(current, pattern, ticket_type)
    if not tickets:
        return None
    picks = format_tickets(tickets, ticket_type)
    roi = to_float(item.get("return_rate"))
    risk = str(item.get("risk_label") or "")
    condition = str(item.get("label") or "")
    note = str(item.get("current_odds_note") or "保存HTMLのレース前オッズ基準。最終オッズで条件外となる可能性があります。")
    reason = (
        f"{risk} / 過去実績 {int(to_float(item.get('purchase_races')) or 0)}R"
        f" / 的中率 {to_float(item.get('hit_rate')) or 0:.1f}%"
        f" / 買い目 {picks}"
        f" / {note}"
    )
    return BettingRecommendation(
        ticket_type=ticket_type,
        label=str(item.get("label") or item.get("strategy_id") or ""),
        stars=str(item.get("stars") or stars_for_roi(roi)),
        expected_roi=roi,
        condition=condition,
        reason=reason,
        source="analysis_json",
        risk_label=risk,
    )


def match_purchase_condition_item(current: pd.DataFrame, item: dict[str, Any]) -> BettingRecommendation | None:
    specs = [ConditionSpec.from_dict(spec) for spec in item.get("conditions", []) if isinstance(spec, dict)]
    if not specs:
        return None
    mask = pd.Series(True, index=current.index)
    for spec in specs:
        mask &= condition_mask(current, spec)
    matched = current[mask].copy()
    if matched.empty:
        return None
    labels = [str(label) for label in item.get("condition_labels", [])] or [spec.label for spec in specs]
    horses = " / ".join(horse_label(row) for _, row in matched.iterrows())
    roi = to_float(item.get("win_roi") if item.get("ticket_type", "").startswith("単勝") else item.get("place_roi"))
    if roi is None:
        roi = max(to_float(item.get("win_roi")) or 0, to_float(item.get("place_roi")) or 0)
    return BettingRecommendation(
        ticket_type=str(item.get("ticket_type") or "条件一致"),
        label=" × ".join(labels),
        stars=str(item.get("stars") or stars_for_roi(roi)),
        expected_roi=roi,
        condition=" / ".join(labels),
        reason=(
            f"一致馬 {horses} / 対象{int(to_float(item.get('target_races')) or 0)}R"
            f" / 単勝回収率{to_float(item.get('win_roi')) or 0:.0f}%"
            f" / 複勝回収率{to_float(item.get('place_roi')) or 0:.0f}%"
        ),
        source="analysis_json",
        risk_label=str(item.get("ranking_type") or ""),
    )


def build_fixed_betting_recommendations(table: pd.DataFrame, *, max_items: int = 3) -> list[BettingRecommendation]:
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
    roi = to_float(rule.get("expected_roi"))
    return BettingRecommendation(
        ticket_type=str(rule["ticket_type"]),
        label=str(rule["label"]),
        stars=stars_for_roi(roi),
        expected_roi=roi,
        condition=str(rule["condition"]),
        reason=reason,
        source="fixed",
    )


def format_tickets(tickets: set[tuple[str, ...]], ticket_type: str) -> str:
    sample = sorted(tickets, key=lambda ticket: tuple(int(x) for x in ticket))[:5]
    sep = "→" if ticket_type in {"馬単", "三連単"} else "-"
    labels = [sep.join(ticket) for ticket in sample]
    if len(tickets) > len(sample):
        labels.append(f"ほか{len(tickets) - len(sample)}点")
    return " / ".join(labels)


def horse_label(row: pd.Series) -> str:
    no = str(row.get("horse_no_eval") or "").strip()
    name = str(row.get("horse_name_eval") or "").strip()
    mark = str(row.get("mark_eval") or "").strip()
    return " ".join(part for part in [no, mark, name] if part)


def _find_by_ai_rank(rows: list[dict[str, Any]], rank: int) -> dict[str, Any] | None:
    for row in rows:
        value = to_float(_pick(row, "ai_rank", "AI順位", "AI点順位"))
        if value is not None and int(value) == rank:
            return row
    return None


def _rows_by_group(rows: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    return [row for row in rows if _text(_pick(row, "display_group", "グループ", "勢力図グループ")) == group]


def _odds_in_range(row: dict[str, Any], low: float, high: float) -> bool:
    odds = to_float(_pick(row, "単勝オッズ", "オッズ", "odds"))
    return odds is not None and low <= odds <= high


def stars_for_roi(roi: float | None) -> str:
    if roi is None:
        return "★★☆☆☆"
    if roi >= 160:
        return "★★★★★"
    if roi >= 130:
        return "★★★★☆"
    if roi >= 105:
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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
