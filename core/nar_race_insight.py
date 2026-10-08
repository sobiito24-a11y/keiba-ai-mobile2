"""Explain existing NAR marks with ability/fit evidence, not an alternate ranking."""
from .race_insight_common import marked_roles


def additional_routes(h):
    routes = []
    if h['close_gap'] and h['conditions'] and h['pace_effect'] == 'plus':
        routes.append('close_gap_condition_pace')
    # Existing Shadow is necessary but not sufficient for this route.
    # Verify known ability and independent fit/close-gap evidence as well.
    if (h['shift'] and h['pace'] in ('H', 'M') and h['pure'] is not None
            and h['group'] in ('middle', 'back')
            and (h['conditions'] or h['close_gap'])):
        routes.append('shift_with_ability_and_fit_review')
    return routes


def select(horses):
    extras = [h for h in horses if not h['member'] and additional_routes(h)]
    extras.sort(key=lambda h: (h['mark'] not in ('✔︎', '✔', '✓'), not h['shift'],
                               h['pure_rank'] or 999, int(h['no'])))
    extra = extras[:2]
    centers, opponents = marked_roles(horses, extra)
    return centers, opponents, extra
