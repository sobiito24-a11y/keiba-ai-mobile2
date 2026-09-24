"""Read-only condition support. No prediction or purchase module consumes this layer."""
import math

def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def _text(row, *keys):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip().lower() not in ('', 'nan', 'none', '<na>'):
            return str(value).strip()
    return ''

def matching_recent_runs(row, race_info):
    """Same last-three scope as the existing ★/☆ display; no historical max fallback."""
    venue = _text(race_info, 'racecourse', 'venue', 'track')
    distance = numeric(race_info.get('distance'))
    runs = row.get('_past_runs')
    same, away = [], []
    if not venue or distance is None or not isinstance(runs, list):
        return same, away
    order = {'前走': 0, '2走前': 1, '3走前': 2}
    valid = [r for r in runs if isinstance(r, dict) and r.get('label') in order]
    for run in sorted(valid, key=lambda r: order[r['label']]):
        course = _text(run, 'racecourse', 'venue', 'track', 'previous_track')
        value = numeric(run.get('value'))
        if not course or value is None or numeric(run.get('distance')) != distance:
            continue
        (same if course == venue else away).append(dict(venue=course, distance=distance, value=value))
    return same, away

CONDITION_LABELS = (('distance_index', '距離'), ('course_index', 'コース'),
                    ('star_index', '★'), ('away_same_distance_index', '☆'))

def annotate_condition_support(rows, sources, race_info, mode):
    """Return copied display rows. Distance/course ranks must already span the field."""
    out = []
    for row, source in zip(rows, sources):
        horse = dict(row)
        same, away = matching_recent_runs(source, race_info)
        for key, runs in [('star_index', same), ('away_same_distance_index', away)]:
            horse[key + '_value'] = max((r['value'] for r in runs), default=None)
        out.append(horse)
    for key in ('star_index', 'away_same_distance_index'):
        values = [h[key + '_value'] for h in out if h[key + '_value'] is not None]
        for horse in out:
            value = horse[key + '_value']
            horse[key + '_rank'] = 1 + sum(v > value for v in values) if value is not None else None
    for horse in out:
        flags = [numeric(horse.get(k + '_rank')) is not None and 1 <= float(horse[k + '_rank']) <= 3
                 for k, _ in CONDITION_LABELS]
        count = sum(flags)
        reason = ' / '.join(f'{label}{int(horse[key + "_rank"])}位'
                            for (key, label), flag in zip(CONDITION_LABELS, flags) if flag)
        if mode == 'jra':
            horse['jra_condition_support_shadow'] = min(1.0, sum(w for w, flag in zip((.5, .25, .25, .5), flags) if flag))
            horse['jra_condition_support_count'] = count
            horse['jra_condition_support_label'] = '条件強' if count >= 3 else '条件注目' if count == 2 else '通常'
            horse['jra_condition_attention'] = count >= 2
            horse['jra_condition_support_reason'] = reason
        elif mode == 'nar':
            for suffix, flag in zip(('distance', 'course', 'star', 'away'), flags):
                horse[f'nar_condition_{suffix}_top3'] = flag
            horse['nar_condition_support_count'] = count
            horse['nar_condition_attention'] = (flags[2] and (flags[0] or flags[1])) or count >= 3
            horse['nar_condition_support_reason'] = reason
    return out

def condition_support_display_label(row, mode):
    count = row.get(mode + '_condition_support_count', 0)
    return '条件強' if count >= 3 else '条件注目' if mode == 'jra' and count == 2 else '通常'


def is_formal_top5(row, mode):
    from .nar_ability_rank import canonical_nar_ability_rank
    rank = numeric(row.get('jra_top5_rank')) if mode == 'jra' else canonical_nar_ability_rank(row)
    return rank is not None and 1 <= rank <= 5


def condition_support_text(row, mode):
    count = row.get(mode + '_condition_support_count', 0)
    label = condition_support_display_label(row, mode)
    reason = row.get(mode + '_condition_support_reason') or '該当なし'
    scope = '上位馬の条件確認' if is_formal_top5(row, mode) else '参考条件（候補追加なし）'
    shadow = f'｜shadow +{row.get("jra_condition_support_shadow", 0):.2f}' if mode == 'jra' else ''
    return f'{scope}｜{label}｜条件サポート：{reason}{shadow}（{count}項目・正式加点なし）'


def condition_support_html(row, mode):
    from html import escape
    highlighted = is_formal_top5(row, mode) and condition_support_display_label(row, mode) != '通常'
    style = 'font-size:12px;'
    style += 'font-weight:600;background:#edf3f9;padding:4px;border-radius:4px;' if highlighted else 'color:#64748b;'
    return '<div class="condition-support" style="' + style + '">' + escape(condition_support_text(row, mode)) + '</div>'
