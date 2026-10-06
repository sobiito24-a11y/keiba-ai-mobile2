"""Race-wide NAR auxiliary checks. Never changes official ranks or marks."""
from .nar_ability_rank import canonical_nar_ability_rank
from .nar_top5_order import horse_no
from .position_signals import corner4_rank
from .jockey_positive import inputs as jockey_inputs

VERSION = 'nar_check_selection_v1_20261006'


def select(rows, source_rows=None):
    sources = {horse_no(r): r for r in (source_rows or rows)}
    out = [dict(r) for r in rows]
    candidates = []
    limit = 1 if len(out) <= 9 else 2
    for index, row in enumerate(out):
        source = dict(row, **sources.get(horse_no(row), {}))
        rank = canonical_nar_ability_rank(source)
        corner = corner4_rank(source)
        rate = jockey_inputs(source)['current_jockey_place_rate']
        # Unknown group/rank is not evidence that a horse is outside Top5.
        group = row.get('pure_ability_top5_group')
        outside = group is False and rank is not None and rank > 5
        ability_ok = rank is not None and 1 <= rank <= 8
        corner_ok = corner is not None and corner <= 6
        jockey_ok = rate is not None and rate >= 25
        candidate = outside and ability_ok and corner_ok
        row.update(nar_check_version=VERSION,
                   nar_check_pure_rank=rank, nar_check_corner4_rank=corner,
                   nar_check_jockey_place_rate=rate,
                   nar_check_candidate_old=outside and sum((ability_ok, corner_ok, jockey_ok)) >= 2,
                   nar_check_candidate_new=candidate,
                   nar_check_selected=False, nar_check_limit=limit)
        if candidate:
            candidates.append((rank, corner, -rate if rate is not None else float('inf'), index))
    # Original row order is the final stable tie-break, never odds/popularity.
    for *_, index in sorted(candidates)[:limit]:
        out[index]['nar_check_selected'] = True
    for row in out:
        row['nar_submark'] = '✓' if row['nar_check_selected'] else ''
    return out


def snapshot(result):
    from .nar_top5_order import result_rows, snapshot as order_snapshot
    rows = result_rows(result)
    by = {horse_no(r): r for r in order_snapshot(result)['horses']}
    merged = [dict(r, **by.get(horse_no(r), {})) for r in rows]
    selected = select(merged, rows)
    return {'model_version': VERSION, 'horses': [
        dict(horse_no=horse_no(r), **{k: v for k, v in r.items() if k.startswith('nar_check_')})
        for r in selected]}
