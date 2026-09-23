"""JRA purchase-selection layer built from existing saved/display values.

The JRA final table is NOT a pure-ability ranking. Final display marks are the
primary selection signal; JRA Top5, reproducibility, pace and training only
change confidence. Pure-ability/Top5 agreement remains available as a research
structure diagnostic and never promotes/demotes a final mark.

No odds, popularity, results, ticket settlement or Snapshot writes belong here.
"""
from __future__ import annotations

import math
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .jra_display_mark import jra_display_mark_from_row


DESCRIPTIONS = {
    "強軸": "補助構造では上位評価が揃っているレース",
    "評価分裂": "補助構造では純能力と今回評価のズレが大きいレース",
    "上位混戦": "補助構造では上位候補が接近しているレース",
}
GUIDES = {
    "強軸": ("最終印を優先", "Top5・再現性・展開・調教は軸信頼の補助材料"),
    "上位混戦": ("最終印を優先", "1頭固定は軸信頼度を確認してから"),
    "評価分裂": ("最終印を優先", "補助評価が割れているため点数を広げすぎない"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _rank(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 1 and number.is_integer() else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "<na>", "—", "-"} else text


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() not in {"", "0", "false", "none", "nan", "-", "—", "なし", "×"}


def classify_jra_horse_role(ability_rank: Any, top5_rank: Any) -> str | None:
    ability, current = _rank(ability_rank), _rank(top5_rank)
    if ability is None or current is None:
        return None
    if ability <= 5:
        return "CORE" if current <= 5 else "ABILITY"
    return "SETUP" if current <= 5 else "OTHER"


def calculate_top5_swap_count(pure_top5: set[str], jra_top5: set[str]) -> int:
    return len(pure_top5 - jra_top5)


def _candidate_from_row(row: Mapping[str, Any], role: str) -> dict[str, Any]:
    number = _rank(row.get("number", row.get("馬番")))
    return {
        "number": str(number) if number is not None else "",
        "name": str(row.get("name") or row.get("馬名") or ""),
        "role": role,
        "mark": jra_display_mark_from_row(row).replace("\ufe0e", "").replace("\ufe0f", ""),
        "top5_rank": _rank(row.get("jra_top5_rank")),
        "top5_score": _number(row.get("jra_top5_score")),
        "reproducibility": _first_text(row, "v1_reproducibility", "shadow_reproducibility", "再現性"),
        "pace": _first_text(row, "v1_pace_eval", "shadow_pace_eval", "展開"),
        "training": _first_text(row, "jra_training_grade", "training_grade", "調教評価"),
        "warning": _truthy(row.get("jra_warning_candidate")),
    }


def build_jra_buy_candidates(rows: Sequence[Mapping[str, Any]], status: str = "強軸") -> dict[str, Any]:
    """Select horses only from the table's final JRA display mark."""
    candidates: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    seen: set[int] = set()

    def order(row: Mapping[str, Any]) -> tuple[float, float]:
        score = _number(row.get("jra_top5_score"))
        return (
            _rank(row.get("jra_top5_rank")) or math.inf,
            -score if score is not None else math.inf,
        )

    roles = {"◎": "中心", "○": "本線", "▲": "本線", "✔": "狙い", "△": "押さえ参考"}
    for row in sorted(rows, key=order):
        number = _rank(row.get("number", row.get("馬番")))
        if number is None or number in seen:
            continue
        seen.add(number)
        mark = jra_display_mark_from_row(row).replace("\ufe0e", "").replace("\ufe0f", "")
        role = roles.get(mark)
        if role:
            candidates.append(_candidate_from_row(row, role))
        elif mark == "✓":
            attention.append(_candidate_from_row(row, "穴注意"))

    groups = {
        role: [horse for horse in candidates if horse["role"] == role]
        for role in ("中心", "本線", "押さえ参考", "狙い")
    }
    return {
        "buy_candidates": [] if status == "評価分裂" else [h for h in candidates if h["role"] != "押さえ参考"],
        "reference_candidates": candidates if status == "評価分裂" else groups["押さえ参考"],
        "buy_groups": groups,
        "hole_attention": attention,
    }


def _saved_interval_days(row: Mapping[str, Any], race_info: Mapping[str, Any]) -> int | None:
    for key in ("_days_since_last", "レース間隔日数", "days_since_last", "_新聞前走間隔日数"):
        value = _number(row.get(key))
        if value is not None and value >= 0 and value.is_integer():
            return int(value)
    runs = row.get("_past_runs")
    if not isinstance(runs, list):
        return None
    previous = [r for r in runs if isinstance(r, Mapping) and r.get("label") == "前走"]
    if len(previous) != 1:
        return None
    try:
        current = date.fromisoformat(str(race_info.get("race_date")))
        last = date.fromisoformat(str(previous[0].get("race_date")))
    except ValueError:
        return None
    days = (current - last).days
    return days if days >= 0 else None


def build_jra_layoff_warnings(
    rows: Sequence[Mapping[str, Any]],
    race_info: Mapping[str, Any],
    saved_rows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    saved: dict[int, list[Mapping[str, Any]]] = {}
    for row in saved_rows:
        number = _rank(row.get("number", row.get("馬番")))
        if number is not None:
            saved.setdefault(number, []).append(row)
    warnings, seen = [], set()
    for row in sorted(rows, key=lambda r: _rank(r.get("jra_top5_rank")) or math.inf):
        number = _rank(row.get("number", row.get("馬番")))
        if number is None or number in seen:
            continue
        seen.add(number)
        days = _saved_interval_days(row, race_info)
        matches = saved.get(number, [])
        if days is None and len(matches) == 1:
            days = _saved_interval_days(matches[0], race_info)
        if days is not None and days >= 90:
            warnings.append({
                "number": str(number),
                "name": str(row.get("name") or row.get("馬名") or ""),
                "days": days,
                "is_top1": _rank(row.get("jra_top5_rank")) == 1,
            })
    return warnings


def classify_jra_race_structure(
    *, leaders_match: bool | None, top5_score_gap: Any, ability_gap: Any, swap_count: Any,
) -> str:
    score_gap, pure_gap, swaps = map(_number, (top5_score_gap, ability_gap, swap_count))
    if (
        not isinstance(leaders_match, bool)
        or score_gap is None
        or pure_gap is None
        or swaps is None
        or min(score_gap, pure_gap, swaps) < 0
        or not swaps.is_integer()
    ):
        return "判定材料不足"
    if leaders_match and score_gap >= 6.0 and pure_gap >= 3.0 and swaps <= 1:
        return "強軸"
    if not leaders_match or swaps >= 2:
        return "評価分裂"
    return "上位混戦"


def _race_kind(info: Mapping[str, Any]) -> str:
    values = [str(info.get(k) or "") for k in ("surface", "course_type", "race_name", "race_data", "distance_label", "label")]
    text = unicodedata.normalize("NFKC", " ".join(values)).lower()
    if "障" in text or any(x in text for x in ("jump", "steeplechase", "hurdle")):
        return "jump"
    surface = unicodedata.normalize("NFKC", str(info.get("surface") or info.get("course_type") or "")).lower()
    if surface in {"芝", "ダ", "ダート", "turf", "dirt"} or "芝" in text or "ダート" in text:
        return "flat"
    return "unknown"


def _positive_signal(value: str) -> bool:
    text = _text(value).upper()
    return bool(text) and (
        text.startswith("A")
        or text in {"◎", "○", "高", "良", "安定"}
        or "好" in text
        or "安定" in text
    )


def _support_score(horse: Mapping[str, Any], layoff_days: int | None = None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    rank = _rank(horse.get("top5_rank"))
    if rank == 1:
        score += 2.5
        reasons.append("Top5 1位")
    elif rank == 2:
        score += 2.0
        reasons.append("Top5 2位")
    elif rank is not None and rank <= 5:
        score += 1.0
        reasons.append(f"Top5 {rank}位")
    if _positive_signal(_text(horse.get("reproducibility"))):
        score += 1.0
        reasons.append("再現性○")
    if _positive_signal(_text(horse.get("pace"))):
        score += 1.0
        reasons.append("展開○")
    training = _text(horse.get("training")).upper()
    if training.startswith("A"):
        score += 2.0
        reasons.append("調教A")
    elif training.startswith("B"):
        score += 0.5
        reasons.append("調教B")
    elif training.startswith("C"):
        score -= 0.5
        reasons.append("調教C")
    if _truthy(horse.get("warning")):
        score -= 1.0
        reasons.append("注意材料あり")
    if layoff_days is not None and layoff_days >= 90:
        score -= 1.5
        reasons.append(f"休養{layoff_days}日")
    return round(score, 2), reasons


def _build_final_purchase_grade(
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
    layoff_warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    centers = list(groups.get("中心") or [])
    mains = list(groups.get("本線") or [])
    aims = list(groups.get("狙い") or [])
    if len(centers) != 1:
        if len(mains) + len(aims) >= 2:
            return {
                "purchase_grade": "C",
                "purchase_label": "複数候補",
                "axis_confidence": "C",
                "axis_candidate": None,
                "purchase_style": "1頭固定せず、最終印の本線・狙いから少点数で確認",
                "purchase_reason_lines": ("中心◎を1頭に絞れない", "最終印の候補は残る"),
            }
        return {
            "purchase_grade": "D",
            "purchase_label": "見送り",
            "axis_confidence": "D",
            "axis_candidate": None,
            "purchase_style": "見送り",
            "purchase_reason_lines": ("中心◎が成立していない",),
        }

    axis = centers[0]
    layoff = next((w for w in layoff_warnings if w.get("number") == axis.get("number")), None)
    support, support_reasons = _support_score(axis, _rank(layoff.get("days")) if layoff else None)
    axis = dict(axis, support_score=support, support_reasons=tuple(support_reasons))
    partner_count = len(mains) + len(aims)

    if support >= 5.0 and partner_count >= 1:
        grade, label, style = "A", "軸あり", "中心◎を軸候補に、本線・狙いから相手を絞る"
    elif support >= 3.0:
        grade, label, style = "B", "買い候補", "中心◎は残すが、ワイド中心で相手を厳選"
    elif partner_count >= 2:
        grade, label, style = "C", "複数候補", "中心固定を弱め、本線・狙いを含めて少点数で確認"
    else:
        grade, label, style = "D", "見送り", "中心◎の補助材料が弱く、無理に買わない"

    reasons = [f"中心◎の補助信頼 {support:.1f}"] + support_reasons
    if partner_count:
        reasons.append(f"本線・狙い{partner_count}頭")
    return {
        "purchase_grade": grade,
        "purchase_label": label,
        "axis_confidence": grade,
        "axis_candidate": axis,
        "purchase_style": style,
        "purchase_reason_lines": tuple(reasons),
    }


def build_jra_purchase_navigation(
    rows: Sequence[Mapping[str, Any]],
    *,
    race_mode: str,
    race_info: Mapping[str, Any],
    saved_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    if race_mode != "jra":
        return {"show": False}

    result: dict[str, Any] = {
        "show": True,
        "status": "判定材料不足",
        "description": "補助構造の必要値を確認できません。",
        "guides": [],
        "horses": [],
        "groups": {k: [] for k in ("CORE", "ABILITY", "SETUP", "OTHER")},
        "axis": None,
        "partners": [],
        "leaders_match": None,
        "top5_score_gap": None,
        "ability_gap": None,
        "swap_count": None,
    }
    kind = _race_kind(race_info)
    if kind == "jump":
        result.update(
            status="対象外",
            description="障害レース：買い方ナビ対象外",
            purchase_grade="D",
            purchase_label="対象外",
            axis_confidence="D",
            purchase_style="対象外",
            purchase_reason_lines=("障害レース",),
            buy_groups={k: [] for k in ("中心", "本線", "押さえ参考", "狙い")},
            hole_attention=[],
            buy_candidates=[],
            reference_candidates=[],
        )
        return result
    if kind != "flat" or len(rows) < 2:
        base = build_jra_buy_candidates(rows, "判定材料不足")
        result.update(base)
        result.update(purchase_grade="D", purchase_label="判定材料不足", axis_confidence="D", axis_candidate=None, purchase_style="判定材料不足のため見送り", purchase_reason_lines=("平地レース・出走馬データを確認できません",))
        return result

    layoff_warnings = build_jra_layoff_warnings(rows, race_info, saved_rows)
    base_candidates = build_jra_buy_candidates(rows, "判定材料不足")
    result.update(base_candidates)
    result["layoff_warnings"] = layoff_warnings
    result.update(_build_final_purchase_grade(base_candidates["buy_groups"], layoff_warnings))

    horses = []
    structure_complete = True
    for row in rows:
        horse = {
            "number": _rank(row.get("number", row.get("馬番"))),
            "name": str(row.get("name") or row.get("馬名") or ""),
            "ability_rank": _rank(row.get("_v1_ability_rank")),
            "ability_value": _number(row.get("jra_pure_ability_score")),
            "top5_rank": _rank(row.get("jra_top5_rank")),
            "top5_score": _number(row.get("jra_top5_score")),
        }
        if any(horse[k] is None for k in ("number", "ability_rank", "ability_value", "top5_rank", "top5_score")):
            structure_complete = False
            break
        horse["number"] = str(horse["number"])
        horse["role"] = classify_jra_horse_role(horse["ability_rank"], horse["top5_rank"])
        horses.append(horse)

    if not structure_complete:
        return result
    n = len(horses)
    if len({h["number"] for h in horses}) != n or {h["top5_rank"] for h in horses} != set(range(1, n + 1)):
        return result
    if any(h["ability_rank"] > n for h in horses):
        return result
    pure_first = [h for h in horses if h["ability_rank"] == 1]
    pure_second = [h for h in horses if h["ability_rank"] == 2]
    if len(pure_first) != 1 or len(pure_second) != 1:
        return result
    ordered = sorted(horses, key=lambda h: h["top5_rank"])
    by_ability = sorted(horses, key=lambda h: h["ability_rank"])
    if any(a["ability_value"] < b["ability_value"] for a, b in zip(by_ability, by_ability[1:])):
        return result
    if any(a["top5_score"] < b["top5_score"] for a, b in zip(ordered, ordered[1:])):
        return result

    pure_top5 = {h["number"] for h in horses if h["ability_rank"] <= 5}
    current_top5 = {h["number"] for h in horses if h["top5_rank"] <= 5}
    match = pure_first[0]["number"] == ordered[0]["number"]
    score_gap = float(Decimal(str(ordered[0]["top5_score"])) - Decimal(str(ordered[1]["top5_score"])))
    ability_gap = float(Decimal(str(pure_first[0]["ability_value"])) - Decimal(str(pure_second[0]["ability_value"])))
    swaps = calculate_top5_swap_count(pure_top5, current_top5)
    status = classify_jra_race_structure(
        leaders_match=match,
        top5_score_gap=score_gap,
        ability_gap=ability_gap,
        swap_count=swaps,
    )
    if status == "判定材料不足":
        return result

    groups = {k: [h for h in ordered if h["role"] == k] for k in result["groups"]}
    axis = ordered[0] if status == "強軸" else None
    partners = [h for h in ordered if 2 <= h["top5_rank"] <= 5 or h["role"] == "ABILITY"] if axis else []
    result.update(
        status=status,
        description=DESCRIPTIONS[status],
        guides=list(GUIDES[status]),
        horses=ordered,
        groups=groups,
        axis=axis,
        partners=partners,
        leaders_match=match,
        top5_score_gap=score_gap,
        ability_gap=ability_gap,
        swap_count=swaps,
    )
    # Preserve legacy candidate fields for audit/tests, but final purchase grade
    # remains mark/support based and is not overridden by the structure status.
    result.update(build_jra_buy_candidates(rows, status))
    result.update(_build_final_purchase_grade(result["buy_groups"], layoff_warnings))
    result["layoff_warnings"] = layoff_warnings
    return result
