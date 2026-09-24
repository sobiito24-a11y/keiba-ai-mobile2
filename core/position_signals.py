"""Exact pre-race netkeiba position signals; never uses odds or results."""
import math

NAR_CORNER4_WIN_RATE_REFERENCE = {1:28.2, 2:16.9, 3:12.7, 4:14.1, 5:7.0, 6:10.0, 7:5.7, 8:4.4, 9:0.0}

def corner4_rank(row):
    for key in ('netkeiba_corner4_rank', '_netkeiba_corner4_rank'):
        value = row.get(key)
        if isinstance(value, bool):
            continue
        try:
            rank = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(rank) and rank.is_integer() and rank >= 1:
            return int(rank)
    return None

def is_jump_race(info):
    if info.get('is_jump') is True or info.get('is_obstacle') is True:
        return True
    description = ' '.join(str(info.get(k) or '') for k in
        ('surface', 'course_type', 'race_type', 'race_name', 'title', '芝ダ', 'コース', 'race_data', 'distance_label', 'label')).lower()
    return '障' in description or any(k in description for k in ('jump', 'steeplechase', 'hurdle'))

def jra_position_bonus(row, race_info=None):
    if is_jump_race(race_info or {}) or is_jump_race(row):
        return 0.0
    rank = corner4_rank(row)
    return 2.0 if rank in (1,2) else 1.5 if rank in (3,4) else 0.0

def nar_position_reference(row):
    rank = corner4_rank(row)
    return {'nar_position_bonus_shadow': 4.0 if rank == 1 else 0.0,
            'nar_corner4_reference_win_rate': NAR_CORNER4_WIN_RATE_REFERENCE.get(rank)}
