"""JRA presentation only: read official saved values, never infer a rank.

Private display fields keep legacy comparison/navigator calculations untouched.
They are attached to copies for rendering, never to PredictionResult or snapshots.
"""
import math


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _key(row):
    for key in ('number', '馬番', '馬', 'horse_no'):
        value = _number(row.get(key))
        if value is not None:
            return str(int(value))
    return ''


def official_jra_values(row):
    return tuple(row.get('_display_' + field, row.get(field))
                 for field in ('jra_top5_rank', 'jra_top5_score'))


def official_jra_sort_key(row):
    rank, _ = official_jra_values(row)
    value = _number(rank)
    # Stable input order for missing/tied official ranks; no inferred ranking.
    return value if value is not None and value > 0 else math.inf


def official_jra_display_rows(rows, source_rows, index_rows=()):
    """Overlay only presentation metadata from the existing result tables."""
    sources = {_key(row): row for row in source_rows}
    indexes = {_key(row): row for row in index_rows}
    out = []
    for row in rows:
        copy = dict(row)
        source, index = sources.get(_key(row), {}), indexes.get(_key(row), {})
        for field in ('jra_top5_rank', 'jra_top5_score'):
            value = source.get(field)
            if _number(value) is None:
                value = index.get(field)
            copy['_display_' + field] = value if _number(value) is not None else None
        out.append(copy)
    return sorted(out, key=official_jra_sort_key)


def official_jra_text(row):
    rank, score = map(_number, official_jra_values(row))
    rank_text = f'{rank:g}位' if rank is not None else '—'
    score_text = f'{score:.1f}' if score is not None else '—'
    return f'JRA Top5 {rank_text} / スコア {score_text}'


def official_jra_result_rows(result, rows):
    """Read frozen Top5 from tables or the saved probability calibration payload.

    Only a fresh UI prediction may use the already-produced formal comparison.
    Loaded results never infer historical ranks from today's comparison.
    """
    def records(table):
        return table.to_dict('records') if table is not None else []
    source = records(result.horse_evaluation) or records(result.overall_table)
    indexes = {_key(h): dict(h) for h in records(result.overall_table)}
    calibration = (result.debug_info or {}).get('jra_win_probability_calibration') or {}
    for horse in calibration.get('horses', []):
        indexes.setdefault(_key(horse), {}).update(horse)
    if getattr(result, '_jra_live_display', False):
        for horse in rows:
            index = indexes.setdefault(_key(horse), {})
            for field in ('jra_top5_rank', 'jra_top5_score'):
                if _number(index.get(field)) is None:
                    index[field] = horse.get(field)
    return official_jra_display_rows(rows, source, list(indexes.values()))
