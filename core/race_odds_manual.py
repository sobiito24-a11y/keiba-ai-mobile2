"""User-typed observed odds; immutable race-specific observation batch.

Accept only explicitly supplied bets. Never fetch third-party sites, never
invent a live provider timestamp and never reuse an old price for a new batch.
"""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Any, Mapping

from . import race_odds as odds

TYPES = {
    "単勝": "win", "複勝": "place", "馬連": "quinella", "ワイド": "wide",
}
LINE = re.compile(r"^(単勝|複勝|馬連|ワイド)\s+(\d+(?:[-,]\d+)?)\s+(\d+(?:\.\d+)?)(?:[-~](\d+(?:\.\d+)?))?$")


def parse_lines(value: str, identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, str) or len(value) > 10_000:
        raise ValueError("入力は10,000文字以内のテキストにしてください")
    valid = {int(h["horse_no"]) for h in identity["horses"]}
    prices, seen = [], set()
    lines = [unicodedata.normalize("NFKC", x).strip().replace("倍", "").replace("～", "~").replace("−", "-").replace("–", "-") for x in value.splitlines()]
    lines = [x for x in lines if x and not x.startswith("#")]
    if not lines or len(lines) > 120:
        raise ValueError("1〜120行の券種・馬番・表示オッズを入力してください")
    for index, line in enumerate(lines, 1):
        matched = LINE.fullmatch(line)
        if not matched:
            raise ValueError(f"{index}行目：『単勝 3 5.2』『ワイド 3-7 4.5-5.8』の形式で入力してください")
        label, numbers, raw_low, raw_high = matched.groups()
        kind = TYPES[label]
        ns = [int(x) for x in re.split(r"[-,]", numbers)]
        if len(ns) != (1 if kind in ("win", "place") else 2) or len(set(ns)) != len(ns):
            raise ValueError(f"{index}行目：券種に必要な馬番数が一致しません")
        if any(no not in valid for no in ns):
            raise ValueError(f"{index}行目：保存された出走馬にない馬番があります")
        low = float(raw_low)
        high = float(raw_high) if raw_high is not None else low
        if not (1 <= low <= high <= 100000):
            raise ValueError(f"{index}行目：オッズの範囲が不正です")
        if kind in ("win", "quinella") and low != high:
            raise ValueError(f"{index}行目：単勝・馬連のオッズは単一値です")
        key = (kind, tuple(sorted(ns)))
        if key in seen:
            raise ValueError(f"{index}行目：同じ組み合わせが重複しています")
        seen.add(key)
        prices.append(dict(kind=kind, horses=sorted(ns), low=low, high=high))
    return prices


def build_observation(
    text: str,
    identity: Mapping[str, Any],
    *,
    source: str,
    seen_now: bool,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """The user verifies same race & odds; 'observed_at' is USER check time."""
    if not seen_now:
        raise ValueError("外部サイトで対象レース・馬番・価格を今確認した場合だけ取り込めます")
    if not source or len(source.strip()) > 80:
        raise ValueError("確認した外部サイト名を80文字以内で入力してください")
    now = received_at or datetime.now(odds.JST)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("入力時刻にタイムゾーンが必要です")
    prices = parse_lines(text, identity)
    roster = {int(h["horse_no"]):h["name"] for h in identity["horses"]}
    observed = sorted({n for p in prices for n in p["horses"]})
    return odds.validate(dict(
        race_id=identity["race_id"], mode=identity["mode"],
        source="自己確認：" + source.strip(),
        identities={str(n): roster[n] for n in observed},
        prices=prices, withdrawn=[], popularity={},
        acquisition_method="manual_user_checked",
        price_status="user_sighted_not_provider_timestamp",
        received_at=now.isoformat(), observed_at=now.isoformat(),
        observed_time_definition="user_visually_checked_at_not_provider_update",
    ), dict(identity))
