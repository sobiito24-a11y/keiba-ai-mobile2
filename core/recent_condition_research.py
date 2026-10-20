"""Opt-in exploration only. No production callers, fitting or persisted marks."""
from .prediction_table_ui import number


def scenarios(view, bonus=3.0):
    """A/B preserve frozen ordinals. C swaps 1/2; D/E add fixed raw-score points.

    Missing condition facts are never treated as no experience. Raw-score
    experiments require complete scores and are not comparable across models.
    """
    if not view or any(number(h.get('rank')) is None for h in view):
        return {'status': 'unavailable', 'reason': 'formal_rank_missing'}
    baseline = sorted(view, key=lambda h: (number(h['rank']), int(h['no'])))
    ids = lambda rows: [h['no'] for h in rows]
    result = dict(status='exploratory_only', bonus=bonus, A=ids(baseline), B=ids(baseline))
    condition = lambda h, key: h['profile']['condition_facts']['conditions'][key]
    swapped = list(baseline)
    if len(swapped) > 1 and condition(swapped[0], 'venue')['state'] in ('started', 'absent'):
        swapped[0], swapped[1] = swapped[1], swapped[0]
    result['C'] = ids(swapped)
    for name, key in [('D', 'venue'), ('E', 'turn')]:
        if any(number(h.get('internal_score')) is None for h in view):
            result[name] = None
            result[name+'_reason'] = 'internal_score_missing'
            continue
        # Fixed-rank baseline remains explicit even if saved scores disagree.
        result[name] = ids(sorted(view, key=lambda h: (
            -(number(h['internal_score']) + (bonus if condition(h,key)['top3'] else 0)),
            number(h['rank']), int(h['no']))))
    return result
