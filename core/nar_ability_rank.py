"""Read the authoritative NAR rank; never infer it from scores or AI ranks."""
from typing import Any, Mapping
import math


def canonical_nar_ability_rank(row: Mapping[str, Any]) -> int | None:
    # market_ability_rank is the persisted alias used by legacy .keiba tables.
    for key in ("saved_ability_rank", "ability_rank", "market_ability_rank", "nar_pure_ability_rank"):
        value = row.get(key)
        if isinstance(value, bool):
            continue
        try:
            rank = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(rank) and rank >= 1 and rank.is_integer():
            return int(rank)
    return None
