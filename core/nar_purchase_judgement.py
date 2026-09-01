"""Race purchase judgement for NAR pure-ability Top5.

This module does not change horse order or marks.  It only annotates whether
the race is suitable to buy, and how reliable the pure-ability Top5 partners are.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any


ABILITY_GAP_1_2_THRESHOLDS = {
    "STRONG": 10.0,
    "GOOD": 5.0,
    "CLOSE": 2.0,
}

PARTNER_TRUST_CONFIG = {
    "base_by_rank": {2: 3.0, 3: 2.0, 4: 2.0, 5: 1.0},
    "market_rank_1": 2.0,
    "market_rank_2_3": 1.25,
    "front_corner4": 1.0,
    "same_distance": 1.0,
    "same_course": 1.0,
    "recent_top3": 1.0,
    "rising_recent": 0.75,
    "continued_jockey": 0.5,
    "sufficient_data": 0.5,
    "data_insufficient": -2.0,
    "very_low_market": -1.5,
    "weak_condition": -0.5,
    "falling_recent": -1.0,
    "high_threshold": 5.0,
    "mid_threshold": 3.0,
    "rank5_trusted_threshold": 6.5,
}

PURCHASE_JUDGEMENT_LABELS = {
    "A": "勝負",
    "B": "買い",
    "C": "注意",
    "D": "見送り",
}

RECOMMENDED_TICKET_MODES = {
    "WIN": "WIN",
    "AXIS_EXACTA": "AXIS_EXACTA",
    "AXIS_QUINELLA": "AXIS_QUINELLA",
    "AXIS_WIDE": "AXIS_WIDE",
    "MULTI": "MULTI",
    "PASS": "PASS",
}


def annotate_nar_purchase_judgement(horses: Sequence[MutableMapping[str, Any]]) -> dict[str, Any]:
    """Attach NAR race purchase judgement and partner trust fields in place."""

    horse_rows = [horse for horse in horses if isinstance(horse, MutableMapping)]
    if not horse_rows:
        return _empty_race_judgement()

    ranked = sorted(horse_rows, key=_pure_rank_sort_key)
    top5 = [horse for horse in ranked if (_int(horse.get("nar_pure_ability_rank")) or 999) <= 5]
    honmei = next((horse for horse in ranked if _int(horse.get("nar_pure_ability_rank")) == 1), None)
    taiko = next((horse for horse in ranked if _int(horse.get("nar_pure_ability_rank")) == 2), None)
    ability_gap = _ability_gap(honmei, taiko)
    gap_level = ability_gap_level(ability_gap)

    for horse in horse_rows:
        _attach_partner_trust(horse)

    trusted_partners = [
        horse
        for horse in horse_rows
        if _is_trusted_partner(horse)
    ]
    trusted_partner_count = len(trusted_partners)
    top5_shortage_count = sum(1 for horse in top5 if _truthy(horse.get("data_insufficient")))
    honmei_market_rank = _market_rank(honmei or {})
    honmei_odds = _odds(honmei or {})

    judgement, score, reasons = _judge_race(
        ability_gap=ability_gap,
        gap_level=gap_level,
        honmei_market_rank=honmei_market_rank,
        honmei_odds=honmei_odds,
        trusted_partner_count=trusted_partner_count,
        top5_shortage_count=top5_shortage_count,
    )
    win_allowed, win_block_reason = _win_bet_allowed(judgement, honmei_odds)
    ticket_mode = _recommended_ticket_mode(judgement, win_allowed, trusted_partner_count)

    summary = {
        "race_purchase_judgement": judgement,
        "race_purchase_label": PURCHASE_JUDGEMENT_LABELS.get(judgement, judgement),
        "race_purchase_score": score,
        "race_purchase_reason": " / ".join(reasons),
        "ability_gap_1_2": ability_gap,
        "ability_gap_1_2_level": gap_level,
        "honmei_market_rank": honmei_market_rank,
        "honmei_odds": honmei_odds,
        "win_bet_allowed": win_allowed,
        "win_bet_block_reason": win_block_reason,
        "trusted_partner_count": trusted_partner_count,
        "recommended_ticket_mode": ticket_mode,
        "top5_data_shortage_count": top5_shortage_count,
        "trusted_partner_numbers": [_text(horse.get("number")) for horse in trusted_partners],
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
    plus_reasons: list[str] = [f"純能力{rank}位"]
    minus_reasons: list[str] = []

    market_rank = _market_rank(horse)
    if market_rank == 1:
        score += float(config["market_rank_1"])
        plus_reasons.append("市場1位")
    elif market_rank is not None and 2 <= market_rank <= 3:
        score += float(config["market_rank_2_3"])
        plus_reasons.append("市場上位")
    elif market_rank is not None and market_rank >= 8:
        score += float(config["very_low_market"])
        minus_reasons.append("市場評価低い")

    if _text(horse.get("corner4_group")) == "front":
        score += float(config["front_corner4"])
        plus_reasons.append("4角前方")
    if _is_positive_mark(horse.get("same_distance")):
        score += float(config["same_distance"])
        plus_reasons.append("同距離材料")
    if _is_positive_mark(horse.get("same_course")):
        score += float(config["same_course"])
        plus_reasons.append("同コース材料")
    if _truthy(horse.get("has_recent_top3")):
        score += float(config["recent_top3"])
        plus_reasons.append("近走3着以内")
    trend = _text(horse.get("recent_trend"))
    if any(word in trend for word in ("上昇", "持ち直し", "反発")):
        score += float(config["rising_recent"])
        plus_reasons.append("近走上向き")
    elif any(word in trend for word in ("下降", "急落", "弱含み")):
        score += float(config["falling_recent"])
        minus_reasons.append("近走下降")
    if "継続" in _text(horse.get("jockey_change")):
        score += float(config["continued_jockey"])
        plus_reasons.append("継続騎乗")

    data_insufficient = _truthy(horse.get("data_insufficient"))
    if data_insufficient:
        score += float(config["data_insufficient"])
        minus_reasons.append(_text(horse.get("data_insufficient_reason")) or "能力材料不足")
    else:
        score += float(config["sufficient_data"])
        plus_reasons.append("データ十分")

    if not _is_positive_mark(horse.get("same_distance")) and not _is_positive_mark(horse.get("same_course")) and rank in {4, 5}:
        score += float(config["weak_condition"])
        minus_reasons.append("条件実績弱め")

    level = "HIGH" if score >= float(config["high_threshold"]) else "MID" if score >= float(config["mid_threshold"]) else "LOW"
    reasons = plus_reasons + minus_reasons
    horse["partner_trust_score"] = round(score, 2)
    horse["partner_trust_level"] = level
    horse["partner_trust_reason"] = " / ".join(reasons)


def _is_trusted_partner(horse: Mapping[str, Any]) -> bool:
    level = _text(horse.get("partner_trust_level"))
    rank = _int(horse.get("nar_pure_ability_rank"))
    if level != "HIGH" or rank is None:
        return False
    if rank in {2, 3, 4}:
        return True
    if rank == 5:
        score = _float(horse.get("partner_trust_score"))
        return score is not None and score >= float(PARTNER_TRUST_CONFIG["rank5_trusted_threshold"])
    return False


def _judge_race(
    *,
    ability_gap: float | None,
    gap_level: str,
    honmei_market_rank: int | None,
    honmei_odds: float | None,
    trusted_partner_count: int,
    top5_shortage_count: int,
) -> tuple[str, float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if honmei_market_rank == 1:
        score += 3.0
        reasons.append("◎市場1位")
    elif honmei_market_rank is not None and 2 <= honmei_market_rank <= 3:
        score += 1.0
        reasons.append(f"◎市場{honmei_market_rank}位")
    elif honmei_market_rank is not None and honmei_market_rank >= 4:
        score -= 4.0
        reasons.append(f"◎市場{honmei_market_rank}位")

    if ability_gap is None:
        reasons.append("◎○能力差不明")
    else:
        reasons.append(f"◎○能力差{ability_gap:.1f}（{gap_level}）")
        if gap_level == "STRONG":
            score += 3.0
        elif gap_level == "GOOD":
            score += 2.0
        elif gap_level == "CLOSE":
            score += 1.0
        else:
            score -= 1.0

    if trusted_partner_count >= 3:
        score += 3.0
        reasons.append(f"信頼相手{trusted_partner_count}頭")
    elif trusted_partner_count >= 2:
        score += 2.0
        reasons.append(f"信頼相手{trusted_partner_count}頭")
    elif trusted_partner_count == 1:
        score += 0.5
        reasons.append("信頼相手1頭")
    else:
        score -= 1.0
        reasons.append("信頼相手なし")

    if top5_shortage_count >= 2:
        score -= 3.0
        reasons.append(f"Top5に能力材料不足{top5_shortage_count}頭")
    elif top5_shortage_count == 1:
        score -= 1.0
        reasons.append("Top5に能力材料不足1頭")
    else:
        reasons.append("重大なデータ不足なし")

    severe_pass = (
        (honmei_market_rank is not None and honmei_market_rank >= 4)
        or top5_shortage_count >= 2
        or (ability_gap is not None and ability_gap < 2.0 and trusted_partner_count == 0)
    )
    if severe_pass:
        return "D", round(score, 2), reasons
    if honmei_odds is not None and 1.0 <= honmei_odds < 2.0 and trusted_partner_count <= 1:
        reasons.append("◎単勝1倍台で相手信頼不足")
        return "C", round(score, 2), reasons
    if honmei_market_rank == 1 and ability_gap is not None and ability_gap >= 10.0 and trusted_partner_count >= 2 and top5_shortage_count == 0:
        return "A", round(score, 2), reasons
    if (
        honmei_market_rank == 1
        and ability_gap is not None
        and ability_gap >= 5.0
        and trusted_partner_count >= 2
    ) or (
        ability_gap is not None
        and 2.0 <= ability_gap < 5.0
        and trusted_partner_count >= 3
        and top5_shortage_count == 0
        and not (honmei_market_rank is not None and honmei_market_rank >= 4)
    ):
        return "B", round(score, 2), reasons
    return "C", round(score, 2), reasons


def _win_bet_allowed(judgement: str, honmei_odds: float | None) -> tuple[bool, str]:
    if honmei_odds is not None and 1.0 <= honmei_odds < 2.0:
        return False, "◎単勝1倍台のため単勝購入対象外"
    if judgement not in {"A", "B"}:
        return False, f"購入判定{judgement}のため単勝購入対象外"
    return True, ""


def _recommended_ticket_mode(judgement: str, win_allowed: bool, trusted_partner_count: int) -> str:
    if judgement not in {"A", "B"}:
        return RECOMMENDED_TICKET_MODES["PASS"]
    if win_allowed:
        return RECOMMENDED_TICKET_MODES["WIN"]
    if trusted_partner_count >= 2:
        return RECOMMENDED_TICKET_MODES["AXIS_QUINELLA"]
    return RECOMMENDED_TICKET_MODES["PASS"]


def _ability_gap(honmei: Mapping[str, Any] | None, taiko: Mapping[str, Any] | None) -> float | None:
    first = _float((honmei or {}).get("nar_pure_ability_score"))
    second = _float((taiko or {}).get("nar_pure_ability_score"))
    if first is None or second is None:
        return None
    return round(first - second, 3)


def _pure_rank_sort_key(horse: Mapping[str, Any]) -> tuple[int, float, int]:
    rank = _int(horse.get("nar_pure_ability_rank"))
    score = _float(horse.get("nar_pure_ability_score"))
    number = _int(horse.get("number"))
    return (
        rank if rank is not None else 999,
        -(score if score is not None else -999999.0),
        number if number is not None else 999,
    )


def _empty_race_judgement() -> dict[str, Any]:
    return {
        "race_purchase_judgement": "D",
        "race_purchase_label": PURCHASE_JUDGEMENT_LABELS["D"],
        "race_purchase_score": 0.0,
        "race_purchase_reason": "出走馬データ不足",
        "ability_gap_1_2": None,
        "ability_gap_1_2_level": "UNKNOWN",
        "honmei_market_rank": None,
        "honmei_odds": None,
        "win_bet_allowed": False,
        "win_bet_block_reason": "出走馬データ不足",
        "trusted_partner_count": 0,
        "recommended_ticket_mode": RECOMMENDED_TICKET_MODES["PASS"],
        "top5_data_shortage_count": 0,
        "trusted_partner_numbers": [],
    }


def _market_rank(row: Mapping[str, Any]) -> int | None:
    return _int(_first(row, "market_rank", "popularity_rank", "人気", "単勝人気", "market_popularity_rank", "odds_rank", "人気順位", "市場順位"))


def _odds(row: Mapping[str, Any]) -> float | None:
    return _float(_first(row, "honmei_odds", "actual_odds", "odds", "odds_at_prediction", "saved_odds_at_prediction", "単勝オッズ", "実オッズ"))


def _is_positive_mark(value: Any) -> bool:
    text = _text(value)
    return text in {"★", "◎", "○"} or ("同" in text and "あり" in text)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    return text not in {"", "0", "false", "none", "nan", "-", "—", "なし", "×"}


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
    if number is None:
        return None
    return int(number)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null", "<na>"}
