"""Explain existing JRA marks; no new ranking or score arithmetic."""
from .race_insight_common import marked_roles


def select(horses):
    # JRA additional attention still needs small ability gap + fit + pace.
    extras = [h for h in horses if not h['member'] and h['pace_effect'] == 'plus'
              and h['close_gap'] and h['conditions']]
    extras.sort(key=lambda h: (h['mark'] not in ('✔︎', '✔', '✓'),
                               h['gap_to_group'], h['pure_rank'] or 999, int(h['no'])))
    extra = extras[:2]
    centers, opponents = marked_roles(horses, extra)
    return centers, opponents, extra
