"""Read-only JRA research candidates: saved pure ability and pre-race corner-4.

Never compute or change predictions, odds, marks, formal scores or bet tickets.
Prespecified 2026-10-18 comparison with the retrospective G policy.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any, Mapping, Sequence

VERSION = "jra_pure5_corner4_top4_fill3_shadow_20261018"
MARK_PRIORITY = {"◎": 0, "○": 1, "▲": 2, "✔": 3, "△": 4, "✓": 5, "☆": 6}


def _rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return int(f) if math.isfinite(f) and f >= 1 and f.is_integer() else None


def _mark(value: Any) -> str:
    return str(value or "").strip().replace("\ufe0e", "").replace("\ufe0f", "")


def _projection(view: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Use only already-rendered JRA rank, mark and numeric pre-race 4-corner fields."""
    projected = []
    for horse in view:
        num = _rank(horse.get("no"))
        if num is None:
            continue
        projected.append({
            "no": num,
            "name": str(horse.get("name") or ""),
            "mark": _mark(horse.get("mark")),
            "formal_rank": _rank(horse.get("rank")),
            "ability_rank": _rank(horse.get("ability_rank")),
            "corner4_rank": _rank(horse.get("corner")),
        })
    return projected


def select(view: Sequence[Mapping[str, Any]], race_key: str = "") -> dict[str, Any]:
    """Compare pure-ability top 3 vs 4-corner-aware top 3 without changing input.

    For faithful comparison with the 262R audit, every runner must have a
    numeric pre-race 4-corner rank. Missing or conflicting sources must not be
    treated as a rear position and never trigger invented completion.
    """
    raw = list(view)
    mode = str(raw[0].get("mode") or "").lower() if raw else ""
    base = {
        "version": VERSION, "race_id": str(race_key), "mode": mode,
        "status": "unavailable", "baseline": [], "shadow": [],
        "reason": "", "input_sha256": None,
        "research_only": True, "bet_recommendation": False,
    }
    if mode != "jra" or any(str(h.get("mode") or "").lower() != "jra" for h in raw):
        return {**base, "reason": "JRA専用の研究表示です。"}
    projected = _projection(raw)
    if not raw or len(projected) != len(raw) or len({x["no"] for x in projected}) != len(raw):
        return {**base, "reason": "馬番が不完全または重複のため未判定。"}
    if any(h["corner4_rank"] is None for h in projected):
        return {**base, "reason": "全頭の発走前4角想定順位が揃っていないため未判定。"}
    marked = [h for h in projected if h["mark"] in MARK_PRIORITY]
    if len(marked) < 3 or any(h["ability_rank"] is None for h in marked):
        return {**base, "reason": "印馬3頭分の保存純能力順位が揃っていないため未判定。"}
    pure = sorted(marked, key=lambda h: (
        h["ability_rank"], MARK_PRIORITY[h["mark"]], h["no"]
    ))
    baseline = pure[:3]
    front = [h for h in pure if h["ability_rank"] <= 5 and h["corner4_rank"] <= 4][:3]
    chosen_numbers = {h["no"] for h in front}
    shadow = (front + [h for h in pure if h["no"] not in chosen_numbers])[:3]
    if len(shadow) != 3:
        return {**base, "reason": "候補3頭を選べないため未判定。"}
    front_numbers = {h["no"] for h in front}
    tagged = [{**h, "selection_reason": (
        "純能力上位5位以内・4角想定4番手以内" if h["no"] in front_numbers
        else "前目候補が3頭未満のため純能力順で補充"
    )} for h in shadow]
    frozen = {
        "version": VERSION,
        "race_id": str(race_key),
        "mode": mode,
        "input": sorted(projected, key=lambda h: h["no"]),
        "baseline": [h["no"] for h in baseline],
        "shadow": [h["no"] for h in shadow],
    }
    digest = sha256(json.dumps(frozen, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
    return {**base, "status": "ready", "baseline": baseline,
            "shadow": tagged, "reason": "", "input_sha256": digest,
            "frozen_input": frozen}


def freeze(view, race_key, exported_at):
    """Separate immutable download payload; odds are observations, never selection inputs."""
    from datetime import datetime
    if datetime.fromisoformat(exported_at).utcoffset() is None:
        raise ValueError('timezone required')
    report = select(view, race_key)
    if report['status'] != 'ready':
        raise ValueError(report['reason'])
    report['exported_at_utc'] = exported_at
    report['time_proof'] = 'local_export_only_not_independent_pre_start_proof'
    report['pre_start_verified'] = False
    report['odds_observations'] = [dict(no=h.get('no'), displayed_odds=h.get('odds'),
        label=h.get('odds_label'), observed_at=h.get('odds_time')) for h in view]
    report['odds_note'] = '未取得値・観測時刻は補完しません。オッズは選出条件に使用しません。'
    report['record_sha256'] = sha256(json.dumps(report,ensure_ascii=False,sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    return report
