"""NAR condition rescue is a separate, read-only warning layer.

Saved pure ability remains authoritative. Missing indexes are never imputed;
competition ranks include all valid runners and preserve boundary ties.
"""
from __future__ import annotations
import math
from .nar_ability_rank import canonical_nar_ability_rank
from typing import Any, Mapping, Sequence


def _number(value: Any):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _no(row):
    n = _number(row.get('number', row.get('馬番')))
    return str(int(n)) if n is not None and n > 0 and n.is_integer() else ''


def build_nar_condition_rescue(rows: Sequence[Mapping[str, Any]], *, index_rows=(), ability_rows=(), race_mode='nar') -> list[dict[str, Any]]:
    """Return pure-rank 6..8 horses with distance OR course index rank <= 4.

    This does not assign a prediction mark, alter purchase grade or produce bets.
    index_rows supplies missing pre-race indexes. ability_rows supplies the saved
    rank, avoiding rounded-score ties in the comparison display.
    """
    if race_mode != 'nar':
        return []
    fallback = {_no(row): row for row in index_rows if _no(row)}
    saved = {_no(row): row for row in ability_rows if _no(row)}
    horses = {}
    for row in rows:
        number = _no(row)
        if not number or number in horses:
            continue
        extra = fallback.get(number, {})
        values = {}
        for field, alias in [('distance_index', '距離指数'), ('course_index', 'コース指数')]:
            value = _number(row.get(field, row.get(alias)))
            if value is None:
                value = _number(extra.get(field, extra.get(alias)))
            values[field] = value
        original = saved.get(number)
        rank = canonical_nar_ability_rank(original if original is not None else row)

        horses[number] = dict(number=number, name=str(row.get('name', row.get('馬名', ''))), ability_rank=rank,
                              existing_warning_reason=str(row.get('nar_warning_reason') or ''), **values)
    for field in ['distance_index', 'course_index']:
        valid = [h[field] for h in horses.values() if h[field] is not None]
        for h in horses.values():
            h[field+'_rank'] = 1 + sum(v > h[field] for v in valid) if h[field] is not None else None
    rescued = []
    for h in horses.values():
        rank = h['ability_rank']
        if rank is None or not 6 <= rank <= 8:
            continue
        dr, cr = h['distance_index_rank'], h['course_index_rank']
        if not ((dr is not None and dr <= 4) or (cr is not None and cr <= 4)):
            continue
        h['nar_condition_rescue'] = True
        h['nar_condition_rescue_reason'] = f"純能力{int(rank)}位 / 距離{str(dr)+'位' if dr else '未取得'} / コース{str(cr)+'位' if cr else '未取得'}"
        rescued.append(h)
    return sorted(rescued, key=lambda h: (h['ability_rank'], int(h['number'])))
