"""NAR purchase selection based on pure ability and race-fit evidence.

Pure-ability order/marks are never changed here. Morning or previous-day odds
and popularity are explicitly excluded because snapshots can be collected long
before post time. Final odds belong to a separate value check at purchase time.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any


ABILITY_GAP_1_2_THRESHOLDS = {"STRONG": 10.0, "GOOD": 5.0, "CLOSE": 2.0}

PARTNER_TRUST_CONFIG = {
    "base_by_rank": {2: 3.0, 3: 2.0, 4: 2.0, 5: 1.0},
    "front_corner4": 1.0,
    "same_distance": 1.0,
    "same_course": 1.0,
    "recent_top3": 1.0,
    "rising_recent": 0.75,
    "continued_jockey": 0.5,
    "sufficient_data": 0.5,
    "data_insufficient": -2.0,
    "weak_condition": -0.5,
    "falling_recent": -1.0,
    "high_threshold": 4.5,
    "mid_threshold": 3.0,
    "rank5_trusted_threshold": 5.5,
}

AXIS_SUPPORT_CONFIG = {
    "base": 2.0,
    "front_corner4": 1.0,
    "same_distance": 1.0,
    "same_course": 1.0,
    "recent_top3": 1.0,
    "rising_recent": 0.75,
    "continued_jockey": 0.5,
    "sufficient_data": 0.5,
    "data_insufficient": -2.5,
    "falling_recent": -1.0,
    "high_threshold": 4.5,
    "mid_threshold": 3.0,
}

# Descriptive only. Scoring stays neutral until larger payout-joined samples
# validate a venue effect out of sample.
VENUE_PROFILES = {
    "水沢": {
        "grade": "研究A",
        "type": "順位信頼型",
        "sample_races": 24,
        "note": "直近検証24Rでは純能力1位12勝・3着内21R。長期回収率確認までは判定点へ加算しない。",
        "verified_for_scoring": False,
    },
    "高知": {
        "grade": "研究B",
        "type": "Top5選抜型",
        "sample_races": 12,
        "note": "9/22検証では純能力1位0勝だが勝ち馬はTop5に9/12。1位固定よりTop5内選抜向き。",
        "verified_for_scoring": False,
    },
}

PURCHASE_JUDGEMENT_LABELS = {"A": "軸あり", "B": "買い候補", "C": "複数候補", "D": "見送り"}
RECOMMENDED_TICKET_MODES = {
    "AXIS_QUINELLA": "AXIS_QUINELLA",
    "AXIS_WIDE": "AXIS_WIDE",
    "MULTI": "MULTI",
    "PASS": "PASS",
}


def annotate_nar_purchase_judgement(
    horses: Sequence[MutableMapping[str, Any]],
    *,
    race_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    horse_rows = [horse for horse in horses if isinstance(horse, MutableMapping)]
    if not horse_rows:
        return _empty_race_judgement(race_info=race_info)

    ranked = sorted(horse_rows, key=_pure_rank_sort_key)
    top5 = [horse for horse in ranked if (_int(horse.get("nar_pure_ability_rank")) or 999) <= 5]
    honmei = next((horse for horse in ranked if _int(horse.get("nar_pure_ability_rank")) == 1), None)
    taiko = next((horse for horse in ranked if _int(horse.get("nar_pure_ability_rank")) == 2), None)
    ability_gap = _ability_gap(honmei, taiko)
    gap_level = ability_gap_level(ability_gap)

    for horse in horse_rows:
        _attach_partner_trust(horse)

    axis_support = _axis_support(honmei or {})
    trusted_partners = [horse for horse in horse_rows if _is_trusted_partner(horse)]
    trusted_partner_count = len(trusted_partners)
    top5_shortage_count = sum(1 for horse in top5 if _truthy(horse.get("data_insufficient")))
    venue_profile = _venue_profile(race_info or {})

    judgement, score, reasons = _judge_race(
        ability_gap=ability_gap,
        gap_level=gap_level,
        axis_support_level=axis_support["level"],
        trusted_partner_count=trusted_partner_count,
        top5_shortage_count=top5_shortage_count,
    )
    ticket_mode = _recommended_ticket_mode(judgement, trusted_partner_count)

    summary = {
        "race_purchase_judgement": judgement,
        "race_purchase_label": PURCHASE_JUDGEMENT_LABELS.get(judgement, judgement),
        "race_purchase_score": score,
        "race_purchase_reason": " / ".join(reasons),
        "ability_gap_1_2": ability_gap,
        "ability_gap_1_2_level": gap_level,
        "axis_support_score": axis_support["score"],
        "axis_support_level": axis_support["level"],
        "axis_support_reason": axis_support["reason"],
        "trusted_partner_count": trusted_partner_count,
        "recommended_ticket_mode": ticket_mode,
        "top5_data_shortage_count": top5_shortage_count,
        "trusted_partner_numbers": [_text(horse.get("number")) for horse in trusted_partners],
        "venue_profile_grade": venue_profile["grade"],
        "venue_profile_type": venue_profile["type"],
        "venue_profile_sample_races": venue_profile["sample_races"],
        "venue_profile_note": venue_profile["note"],
        "venue_profile_verified_for_scoring": venue_profile["verified_for_scoring"],
        # Compatibility fields only. Never used by this judgement.
        "honmei_market_rank": None,
        "honmei_odds": None,
        "win_bet_allowed": False,
        "win_bet_block_reason": "取得時オッズは購入判定に使用しません。最終オッズは購入直前の期待値確認専用です。",
    }
    for horse in horse_rows:
        horse.update(summary)
    return summary


def ability_gap_level(gap: Any) -> str:
    value = _float(gap)
    if value is None:
        return "UNKNOWN"
    if value >= ABILITY_GAP_1_2_THRESHOLDS["STRONG"]:
        return "STRONG"
    if value >= ABILITY_GAP_1_2_THRESHOLDS["GOOD"]:
        return "GOOD"
    if value >= ABILITY_GAP_1_2_THRESHOLDS["CLOSE"]:
        return "CLOSE"
    return "VERY_CLOSE"


def _attach_partner_trust(horse: MutableMapping[str, Any]) -> None:
    rank = _int(horse.get("nar_pure_ability_rank"))
    if rank not in {2, 3, 4, 5}:
        horse["partner_trust_score"] = None
        horse["partner_trust_level"] = ""
        horse["partner_trust_reason"] = ""
        return
    config = PARTNER_TRUST_CONFIG
    score = float(config["base_by_rank"][rank])
    plus = [f"純能力{rank}位"]
    minus: list[str] = []
    if _text(horse.get("corner4_group")) == "front":
        score += config["front_corner4"]; plus.append("4角前方")
    if _is_positive_mark(horse.get("same_distance")):
        score += config["same_distance"]; plus.append("同距離材料")
    if _is_positive_mark(horse.get("same_course")):
        score += config["same_course"]; plus.append("同コース材料")
    if _truthy(horse.get("has_recent_top3")):
        score += config["recent_top3"]; plus.append("近走3着以内")
    trend = _text(horse.get("recent_trend"))
    if any(word in trend for word in ("上昇", "持ち直し", "反発")):
        score += config["rising_recent"]; plus.append("近走上向き")
    elif any(word in trend for word in ("下降", "急落", "弱含み")):
        score += config["falling_recent"]; minus.append("近走下降")
    if "継続" in _text(horse.get("jockey_change")):
        score += config["continued_jockey"]; plus.append("継続騎乗")
    if _truthy(horse.get("data_insufficient")):
        score += config["data_insufficient"]; minus.append(_text(horse.get("data_insufficient_reason")) or "能力材料不足")
    else:
        score += config["sufficient_data"]; plus.append("データ十分")
    if not _is_positive_mark(horse.get("same_distance")) and not _is_positive_mark(horse.get("same_course")) and rank in {4, 5}:
        score += config["weak_condition"]; minus.append("条件実績弱め")
    level = "HIGH" if score >= config["high_threshold"] else "MID" if score >= config["mid_threshold"] else "LOW"
    horse["partner_trust_score"] = round(score, 2)
    horse["partner_trust_level"] = level
    horse["partner_trust_reason"] = " / ".join(plus + minus)


def _axis_support(horse: Mapping[str, Any]) -> dict[str, Any]:
    if not horse:
        return {"score": 0.0, "level": "LOW", "reason": "純能力1位データなし"}
    config = AXIS_SUPPORT_CONFIG
    score = float(config["base"])
    plus = ["純能力1位"]
    minus: list[str] = []
    if _text(horse.get("corner4_group")) == "front":
        score += config["front_corner4"]; plus.append("4角前方")
    if _is_positive_mark(horse.get("same_distance")):
        score += config["same_distance"]; plus.append("同距離材料")
    if _is_positive_mark(horse.get("same_course")):
        score += config["same_course"]; plus.append("同コース材料")
    if _truthy(horse.get("has_recent_top3")):
        score += config["recent_top3"]; plus.append("近走3着以内")
    trend = _text(horse.get("recent_trend"))
    if any(word in trend for word in ("上昇", "持ち直し", "反発")):
        score += config["rising_recent"]; plus.append("近走上向き")
    elif any(word in trend for word in ("下降", "急落", "弱含み")):
        score += config["falling_recent"]; minus.append("近走下降")
    if "継続" in _text(horse.get("jockey_change")):
        score += config["continued_jockey"]; plus.append("継続騎乗")
    if _truthy(horse.get("data_insufficient")):
        score += config["data_insufficient"]; minus.append(_text(horse.get("data_insufficient_reason")) or "能力材料不足")
    else:
        score += config["sufficient_data"]; plus.append("データ十分")
    level = "HIGH" if score >= config["high_threshold"] else "MID" if score >= config["mid_threshold"] else "LOW"
    return {"score": round(score, 2), "level": level, "reason": " / ".join(plus + minus)}


def _is_trusted_partner(horse: Mapping[str, Any]) -> bool:
    level = _text(horse.get("partner_trust_level"))
    rank = _int(horse.get("nar_pure_ability_rank"))
    if level != "HIGH" or rank is None:
        return False
    if rank in {2, 3, 4}:
        return True
    if rank == 5:
        score = _float(horse.get("partner_trust_score"))
        return score is not None and score >= PARTNER_TRUST_CONFIG["rank5_trusted_threshold"]
    return False


def _judge_race(*, ability_gap: float | None, gap_level: str, axis_support_level: str, trusted_partner_count: int, top5_shortage_count: int) -> tuple[str, float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if ability_gap is None:
        reasons.append("◎○能力差不明")
    else:
        reasons.append(f"◎○能力差{ability_gap:.1f}（{gap_level}）")
        score += {"STRONG": 3.0, "GOOD": 2.0, "CLOSE": 1.0}.get(gap_level, -1.0)
    if axis_support_level == "HIGH":
        score += 3.0; reasons.append("軸条件HIGH")
    elif axis_support_level == "MID":
        score += 1.0; reasons.append("軸条件MID")
    else:
        score -= 1.0; reasons.append("軸条件LOW")
    if trusted_partner_count >= 3:
        score += 3.0; reasons.append(f"信頼相手{trusted_partner_count}頭")
    elif trusted_partner_count >= 2:
        score += 2.0; reasons.append(f"信頼相手{trusted_partner_count}頭")
    elif trusted_partner_count == 1:
        score += 0.5; reasons.append("信頼相手1頭")
    else:
        score -= 1.0; reasons.append("信頼相手なし")
    if top5_shortage_count >= 2:
        score -= 3.0; reasons.append(f"Top5に能力材料不足{top5_shortage_count}頭")
    elif top5_shortage_count == 1:
        score -= 1.0; reasons.append("Top5に能力材料不足1頭")
    else:
        reasons.append("重大なデータ不足なし")
    severe = top5_shortage_count >= 2 or (ability_gap is not None and ability_gap < 2.0 and axis_support_level == "LOW" and trusted_partner_count == 0)
    if severe:
        return "D", round(score, 2), reasons
    if gap_level == "STRONG" and axis_support_level == "HIGH" and trusted_partner_count >= 2 and top5_shortage_count == 0:
        return "A", round(score, 2), reasons
    if (axis_support_level == "HIGH" and trusted_partner_count >= 1 and gap_level in {"STRONG", "GOOD"}) or (axis_support_level in {"HIGH", "MID"} and trusted_partner_count >= 2 and gap_level in {"GOOD", "CLOSE"} and top5_shortage_count == 0):
        return "B", round(score, 2), reasons
    return "C", round(score, 2), reasons


def _recommended_ticket_mode(judgement: str, trusted_partner_count: int) -> str:
    if judgement == "A":
        return RECOMMENDED_TICKET_MODES["AXIS_QUINELLA"] if trusted_partner_count >= 2 else RECOMMENDED_TICKET_MODES["AXIS_WIDE"]
    if judgement == "B":
        return RECOMMENDED_TICKET_MODES["AXIS_WIDE"]
    if judgement == "C":
        return RECOMMENDED_TICKET_MODES["MULTI"]
    return RECOMMENDED_TICKET_MODES["PASS"]


def _venue_profile(race_info: Mapping[str, Any]) -> dict[str, Any]:
    venue = _venue_name(race_info)
    profile = VENUE_PROFILES.get(venue)
    if profile is None:
        return {"grade": "—", "type": "標準型", "sample_races": 0, "note": "会場別の長期払戻検証が十分になるまでは購入判定へ補正しません。", "verified_for_scoring": False}
    return dict(profile)


def _venue_name(race_info: Mapping[str, Any]) -> str:
    direct = _text(_first(race_info, "venue", "venue_name", "place", "track", "競馬場", "開催場"))
    if direct:
        for venue in VENUE_PROFILES:
            if venue in direct:
                return venue
    text = " ".join(_text(value) for value in race_info.values() if isinstance(value, (str, int, float)))
    for venue in VENUE_PROFILES:
        if venue in text:
            return venue
    return ""


def _ability_gap(honmei: Mapping[str, Any] | None, taiko: Mapping[str, Any] | None) -> float | None:
    first = _float((honmei or {}).get("nar_pure_ability_score")); second = _float((taiko or {}).get("nar_pure_ability_score"))
    if first is None or second is None:
        return None
    return round(first - second, 3)


def _pure_rank_sort_key(horse: Mapping[str, Any]) -> tuple[int, float, int]:
    rank = _int(horse.get("nar_pure_ability_rank")); score = _float(horse.get("nar_pure_ability_score")); number = _int(horse.get("number"))
    return (rank if rank is not None else 999, -(score if score is not None else -999999.0), number if number is not None else 999)


def _empty_race_judgement(*, race_info: Mapping[str, Any] | None = None) -> dict[str, Any]:
    venue = _venue_profile(race_info or {})
    return {
        "race_purchase_judgement": "D", "race_purchase_label": PURCHASE_JUDGEMENT_LABELS["D"], "race_purchase_score": 0.0,
        "race_purchase_reason": "出走馬データ不足", "ability_gap_1_2": None, "ability_gap_1_2_level": "UNKNOWN",
        "axis_support_score": 0.0, "axis_support_level": "LOW", "axis_support_reason": "出走馬データ不足",
        "trusted_partner_count": 0, "recommended_ticket_mode": RECOMMENDED_TICKET_MODES["PASS"], "top5_data_shortage_count": 0,
        "trusted_partner_numbers": [], "venue_profile_grade": venue["grade"], "venue_profile_type": venue["type"],
        "venue_profile_sample_races": venue["sample_races"], "venue_profile_note": venue["note"],
        "venue_profile_verified_for_scoring": venue["verified_for_scoring"], "honmei_market_rank": None, "honmei_odds": None,
        "win_bet_allowed": False, "win_bet_block_reason": "取得時オッズは購入判定に使用しません。",
    }


def _is_positive_mark(value: Any) -> bool:
    text = _text(value)
    return text in {"★", "◎", "○"} or ("同" in text and "あり" in text)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() not in {"", "0", "false", "none", "nan", "-", "—", "なし", "×"}


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = row.get(name)
            if not _is_missing(value):
                return value
    return None


def _text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = _text(value).replace(",", "").replace("％", "").replace("%", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null", "<na>"}
