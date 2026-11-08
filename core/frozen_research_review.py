"""Frozen, outcome-free JRA/NAR research checks (2026-11-08).

Research only: never change ability, formal marks, ranks, purchase decisions,
or existing frozen .keiba records. Conditions were devised after Nov 7-8 results.
Next genuinely prospective validation begins with the 2026-11-14 races.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

FROZEN_VERSION = "jra_nar_frozen_review_20261108_v1"
FROZEN_ON = "2026-11-08"
HOLDOUT_START = "2026-11-14"


def _object(x: Any) -> Mapping[str, Any]:
    return x if isinstance(x, Mapping) else {}


def _number(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def _rank(x: Any) -> int | None:
    v = _number(x)
    return int(v) if v is not None and v.is_integer() and v >= 1 else None


def _metric_rank(horse: Mapping[str, Any], key: str) -> int | None:
    facts = _object(horse.get("explorer_facts"))
    metric = _object(_object(facts.get("metrics")).get(key))
    return _rank(metric.get("rank")) or _rank(_object(horse.get(key)).get("rank"))


def _ability_rank(horse: Mapping[str, Any]) -> int | None:
    return _metric_rank(horse, "ability") or _rank(horse.get("ability_rank"))


def _corner(horse: Mapping[str, Any]) -> int | None:
    facts = _object(horse.get("explorer_facts"))
    metric = _object(facts.get("metrics"))
    return _rank(metric.get("corner")) or _rank(horse.get("corner"))


def _jra_evidence(horse: Mapping[str, Any]) -> tuple[str, str, bool]:
    facts = _object(horse.get("explorer_facts"))
    ability = _ability_rank(horse)
    if ability is None:
        return "能力未取得", "能力順位がないため相手比較の候補判定を保留", False
    grade = str(facts.get("training") or horse.get("training") or "").strip().upper()
    status = str(facts.get("rest_status") or "")
    days = _number(facts.get("rest_days")) if status == "verified" else None
    distance = _metric_rank(horse, "distance")
    course = _metric_rank(horse, "course")
    supports = []
    if distance is not None and distance <= 3:
        supports.append("距離指数3位以内")
    if course is not None and course <= 3:
        supports.append("コース指数3位以内")
    if grade in ("A", "B"):
        supports.append("調教A/B")
    concerns = []
    if days is None:
        concerns.append("休養間隔が未確認")
    elif days >= 70:
        concerns.append(f"70日以上の休養（{int(days)}日）")
    if grade in ("C", "D"):
        concerns.append(f"調教{grade}")
    if grade not in ("A", "B", "C", "D"):
        concerns.append("調教未取得")
    qualified = (
        2 <= ability <= 5 and grade in ("A", "B")
        and days is not None and days < 70
        and (distance is not None and distance <= 3 or course is not None and course <= 3)
    )
    if days is not None and days >= 70 and grade in ("C", "D"):
        label = "長休＋調教注意"
    elif qualified:
        label = "相手比較材料"
    elif grade in ("C", "D"):
        label = "調教注意"
    elif days is not None and days >= 70:
        label = "休養注意"
    else:
        label = "条件不足"
    description = " / ".join(supports + concerns) or "確かな比較材料なし"
    return label, description, qualified


def _nar_evidence(horse: Mapping[str, Any]) -> tuple[str, str, bool]:
    ability = _ability_rank(horse)
    pred = _corner(horse)
    previous = _rank(horse.get("nar_form_ref_prior_corner"))
    if ability is None:
        return "能力未取得", "純能力順位がないため判定を保留", False
    if previous is None:
        return "前走4角未取得", "前走着順を4角順位の代わりに使用しません", False
    if pred is None:
        return "今回4角未取得", "今回の4角想定がないため再確認条件を判定できません", False
    # Fixed 2026-11-08; NO bonus and no automatic selection/purchase.
    watch = ability >= 6 and previous <= 3 and pred <= 3
    if watch:
        return (
            "前走×4角再確認",
            f"純能力{ability}位 / 前走実際4角{previous}位 / 今回4角想定{pred}位。"
            "10月別開催では回収率改善を再現できず、購入推奨ではありません",
            True,
        )
    return "—", f"純能力{ability}位 / 前走4角{previous}位 / 今回4角想定{pred}位", False


def with_frozen_reviews(view: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """No outcome/finish/payoff inputs; copy each view, append only review data."""
    result = []
    for raw in view:
        horse = dict(raw)
        mode = str(horse.get("mode") or "").lower()
        if mode == "jra":
            label, description, candidate = _jra_evidence(horse)
        elif mode == "nar":
            label, description, candidate = _nar_evidence(horse)
        else:
            label, description, candidate = "対象外", "対象レース種別ではありません", False
        horse["frozen_review_label"] = label
        horse["frozen_review_reason"] = description
        horse["frozen_review_candidate"] = candidate
        horse["frozen_review_version"] = FROZEN_VERSION
        result.append(horse)
    return result


def jra_research_pair_three(view: list[Mapping[str, Any]]) -> list[str]:
    """Frozen *hypothesis*, not a betting pick. 1 ability anchor + 2 comparators.

    Compare these 3 with pure ability Top3 on an unseen race day; if grade,
    distance, rest, or ability is unavailable no numerical guess is inserted.
    """
    if not view or any(h.get("mode") != "jra" for h in view):
        return []
    enriched = with_frozen_reviews(view)
    ranked = sorted(
        ((r, str(h.get("no") or "")) for h in enriched if (r := _ability_rank(h)) is not None),
        key=lambda item: (item[0], _rank(item[1]) or 999),
    )
    if not ranked or ranked[0][0] != 1:
        return []
    anchor = ranked[0][1]
    candidates = [h for h in enriched if h.get("frozen_review_candidate") and str(h.get("no")) != anchor]
    candidates.sort(key=lambda h: (_ability_rank(h) or 999, _rank(h.get("no")) or 999))
    selected = [anchor] + [str(h["no"]) for h in candidates[:2]]
    # Fill strictly by pre-race ability rank, do not fabricate candidate evidence.
    for rank, number in ranked:
        if len(selected) >= 3:
            break
        if number not in selected:
            selected.append(number)
    return selected if len(selected) == 3 else []
