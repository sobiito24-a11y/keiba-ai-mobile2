"""Research-only odds versus model probabilities; never signals an approved bet.

A price comes from EXACTLY ONE selected observation; never fill missing pair
prices from yesterday's data. Model v3 is uncalibrated: do not equate a
reference edge with proven positive expectation or a buy recommendation.
"""
from __future__ import annotations

from datetime import datetime
from itertools import combinations
import math
from typing import Any, Mapping

from . import race_odds as odds

VERSION = "race_value_research_20261109_v1"


def _finite_probability(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and 0 <= x <= 1 else None


def _quinella_pl(i: int, j: int, model_win: Mapping[int, float]) -> float | None:
    """Explicitly labeled Plackett-Luce approximation, never observed frequency."""
    a, b = model_win.get(i), model_win.get(j)
    if a is None or b is None or 1-a <= 1e-10 or 1-b <= 1e-10:
        return None
    return min(1.0, a*b/(1-a) + b*a/(1-b))


def price_state(quote: Mapping[str, Any] | None, start_time: str | None,
                now: datetime | None = None) -> str:
    if not quote:
        return "価格なし"
    state = odds.freshness(quote, start_time, now=now, max_age_seconds=300)
    if quote.get("acquisition_method") == "manual_user_checked":
        if state == "発走前の観測価格（変動します）":
            return "利用者が5分以内に確認（提供元の更新時刻は未確認）"
    return state


def evaluate_reference(prediction: Mapping[str, Any], quote: Mapping[str, Any] | None,
                       *, start_time: str | None = None,
                       now: datetime | None = None) -> dict[str, Any]:
    out = dict(version=VERSION, is_calibrated=False, proven_edge=False,
               mode=prediction.get("mode"), model_id=prediction.get("model_id"),
               status="研究用・未校正", price_state=price_state(quote,start_time,now),
               horses=[], tickets=[], recommendation=None,
               notes="予測確率は未校正。馬連はPlackett–Luce近似。"
                     "モデル間変動幅は信頼区間ではない。オッズは確定払戻ではない。")
    horses = {}
    for row in prediction.get("horses", []):
        try:
            no = int(row["horse_no"])
        except (KeyError, ValueError, TypeError):
            continue
        win = _finite_probability(row.get("win"))
        place = _finite_probability(row.get("place"))
        horses[no] = dict(no=no, name=str(row.get("name") or ""),
                          win=win, place=place,
                          win_range=row.get("win_range"),
                          place_range=row.get("place_range"),
                          cautions=row.get("cautions") or [])
    out["horses"] = [horses[key] for key in sorted(horses)]
    if prediction.get("status") != "reference":
        out["status"] = "確率を表示できません"
        return out
    if not quote:
        return out
    if quote.get("race_id") != prediction.get("race_id") or quote.get("mode") != prediction.get("mode"):
        out["status"] = "レース不一致・オッズ無効"
        return out
    if quote.get("price_status") in ("predicted_odds","final","post_race"):
        out["status"] = "予想・終了後価格のため参考比較しません"
        return out

    wins = {n: h["win"] for n, h in horses.items() if h["win"] is not None}
    wide = {}
    for row in prediction.get("wide", []):
        pair = row.get("horses", [])
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        p = _finite_probability(row.get("probability"))
        if p is not None:
            wide[tuple(sorted(pair))] = p
    for price in quote.get("prices", []):
        kind = price.get("kind")
        nums = price.get("horses")
        if kind not in ("win","place","quinella","wide") or not isinstance(nums,list):
            continue
        if len(nums) != (1 if kind in ("win","place") else 2):
            continue
        if len(set(nums)) != len(nums) or any(n not in horses for n in nums):
            continue
        if set(nums) & set(quote.get("withdrawn") or []):
            continue
        try:
            low = float(price["low"]);high = float(price["high"])
        except (KeyError,ValueError,TypeError):
            continue
        if not math.isfinite(low) or not math.isfinite(high) or not 1 <= low <= high:
            continue
        if kind in ("win","quinella") and low != high:
            continue
        ns=tuple(sorted(nums))
        if kind == "win": p=horses[nums[0]]["win"]
        elif kind == "place": p=horses[nums[0]]["place"]
        elif kind == "wide": p=wide.get(ns)
        else:p=_quinella_pl(ns[0], ns[1], wins)
        # Keep unavailable probabilities unavailable; never substitute ability rank.
        out["tickets"].append(dict(
            kind=kind, horses=list(ns), low=low, high=high,
            probability=p,
            break_even_pct=100.0/low,
            model_prob_pct=100.0*p if p is not None else None,
            model_gross_pct=100.0*p*low if p is not None else None,
            model_margin_pp=100.0*(p-1.0/low) if p is not None else None,
            model_type="未校正馬連近似" if kind=="quinella" else "未校正モデル参考値",
            status="実際の購入価値は未検証",
        ))
    out["tickets"].sort(key=lambda x:(("win","place","wide","quinella").index(x["kind"]),x["horses"]))
    return out
