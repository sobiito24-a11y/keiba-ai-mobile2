"""Horse-keyed, whitelisted inputs for the independent JRA practical shadow."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import re
import unicodedata
from .jra_practical_shadow import number
from .jra_repro_candidate import by_horse, records, merged_runs
from .jra_formal_snapshot import saved_formal_comparison
from .position_signals import corner4_rank, is_jump_race
from .newspaper_v2_inputs import race_id

JST = timezone(timedelta(hours=9))


def timestamp(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t if t.tzinfo else t.replace(tzinfo=JST)
    except (TypeError, ValueError):
        return None


def pick_field(sources, keys, numeric=False):
    for source, row in sources:
        for key in keys:
            value = row.get(key)
            if numeric:
                value = number(value)
            if value is not None and str(value).strip() not in ('', 'nan', 'None', '—', '未取得'):
                return value, source + '.' + key
    return None, None


def practical_inputs(result, *, evaluation_context='fresh_pre_race'):
    """Never calls a formal producer. Past result fields alone are allowed.

    Only explicit timestamps establish pre-race status. This adapter does not
    substitute filesystem timestamps or guess missing scheduled start times.
    """
    info = result.race_info or {}
    ev, ov = by_horse(records(result.horse_evaluation)), by_horse(records(result.overall_table))
    frozen = by_horse((saved_formal_comparison(result) or {}).get('rows', []))
    calibration = by_horse(((result.debug_info or {}).get('jra_win_probability_calibration') or {}).get('horses', []))
    day = str(info.get('race_date') or info.get('date') or '')[:10]
    start = timestamp(info.get('scheduled_start_time') or info.get('scheduled_post_time'))
    if start is None and re.fullmatch(r'\d{4}-\d\d-\d\d', day):
        match = re.search(r'(\d{1,2}:\d{2})発走', str(info.get('race_data') or info.get('raw') or ''))
        if match:
            start = timestamp(day + 'T' + match[1])
    created = timestamp(result.created_at)
    pre = created is not None and start is not None and created < start
    horses = []
    paces = set()
    keys = sorted(set(ev) | set(ov), key=int)
    for no in keys:
        e, o = ev.get(no, {}), ov.get(no, {})
        if e.get('horse_id') and o.get('horse_id') and str(e['horse_id']) != str(o['horse_id']):
            raise ValueError('馬番とhorse_idが競合: ' + no)
        sources = [('formal_snapshot', frozen.get(no, {})), ('calibration', calibration.get(no, {})),
                   ('horse_evaluation', e), ('overall_table', o)]
        h = {'horse_no': no, 'sources': {}}
        def read(field, aliases, numeric=False):
            value, source = pick_field(sources, aliases, numeric)
            h[field] = value
            h['sources'][field] = source
        read('horse_name', ('horse_name', '馬名', 'name'))
        read('formal_rank', ('jra_top5_rank',), True)
        read('formal_score', ('jra_top5_score',), True)
        read('formal_position_bonus', ('jra_position_bonus',), True)
        read('pure_score', ('jra_pure_ability_score', 'market_ability_score'), True)
        read('pure_rank', ('_v1_ability_rank', 'market_ability_rank'), True)
        read('training_raw', ('training_market', '調教評価', 'training_grade', '調教', 'training'))
        grade = re.match(r'\s*([ABCD])(?:\b|\s|$)', str(h['training_raw'] or ''))
        h['training_grade'] = grade[1] if grade else None
        read('corner4_rank', ('netkeiba_corner4_rank', '_netkeiba_corner4_rank'), True)
        h['corner4_rank'] = corner4_rank({'netkeiba_corner4_rank': h['corner4_rank']})
        if h['corner4_rank'] is not None and h['corner4_rank'] > len(keys):
            h['corner4_rank'] = None
        pace, source = pick_field(sources, ('provider_pace_market', 'netkeiba_pace', '_netkeiba_pace'))
        if pace in ('S', 'M', 'H'):
            paces.add(pace)
        h['sources']['pace'] = source
        read('distance_index', ('距離指数', 'distance_index'), True)
        read('course_index', ('コース指数', 'course_index'), True)
        read('load_weight', ('_display_current_load_weight', '_current_load_weight', '斤量', 'weight'), True)
        read('load_change', ('weight_change_market', '_display_load_weight_change', '_load_weight_change', '斤量増減'), True)
        read('sex_age', ('性齢', 'sex_age', '馬年齢', '馬齢', 'age', '年齢'))
        age = re.fullmatch(r'(?:牡|牝|セ|騸)?\s*(\d{1,2})(?:歳)?', unicodedata.normalize('NFKC', str(h['sex_age'] or '')))
        h['age'] = int(age[1]) if age else None
        runs, audit = merged_runs(e, o, day)
        h['recent_runs'] = runs
        # Only safe normalized past inputs; no current result / odds in audit.
        h['past_input_status'] = [{'status': g['status'], 'sources': g['sources'], 'conflicts': g['conflicts']}
                                  for g in audit['runs']]
        h['rest_days'] = None
        if runs:
            try:
                h['rest_days'] = (datetime.fromisoformat(day) - datetime.fromisoformat(runs[0]['date'])).days
            except ValueError:
                pass
        h['layoff_returns'] = []
        for newer, older in zip(runs, runs[1:]):
            days = (datetime.fromisoformat(newer['date']) - datetime.fromisoformat(older['date'])).days
            if days >= 90 and number(newer.get('finish')) is not None:
                h['layoff_returns'].append({'race_id': newer.get('race_id'), 'days': days,
                                           'finish': newer['finish'], 'venue': newer.get('venue'),
                                           'surface': newer.get('surface'), 'distance': newer.get('distance')})
        venue = info.get('racecourse') or info.get('venue')
        distance = number(info.get('distance'))
        for field, same in [('star_index', True), ('away_index', False)]:
            values = [r['value'] for r in runs if number(r.get('value')) is not None and distance is not None
                      and number(r.get('distance')) == distance and venue and r.get('venue')
                      and (r['venue'] == venue) == same]
            h[field] = max(values) if values else None
            h['sources'][field] = 'normalized_pre_race_recent3' if values else None
        # Legacy class-shift flags can confuse earlier upper-class experience.
        # Only an explicit, provenance-bearing previous/current context is read.
        h['class_change'] = None
        from .jra_class_v2 import classify_jra_class
        from .class_context import class_change
        current_class = classify_jra_class(info)
        previous_class = None
        if runs:
            matching = [g for g in audit['runs'] if g['status'] == '有効' and g['run'].get('race_id') == runs[0].get('race_id')
                        and g['run'].get('date') == runs[0]['date']]
            contexts = []
            for group in matching:
                for raw in group['raw']:
                    contexts.append(classify_jra_class({k: raw.get(k) for k in
                                                       ('race_name', 'race_data', 'race_data2', 'raw_class_text', 'surface', 'race_grade')}))
            valid = [c for c in contexts if class_change(current_class, c) != '比較不能']
            if valid and len({(c['class_label_v2'], c['comparable_class_group_v2']) for c in valid}) == 1:
                previous_class = valid[0]
                h['class_change'] = class_change(current_class, previous_class)
        h['class_evidence'] = {'current': current_class, 'previous': previous_class,
                               'status': 'comparable' if previous_class else '比較根拠不足（旧降級フラグは使わない）'}
        h['body_weight'] = None
        weight, weight_source = pick_field(sources, ('body_weight', '馬体重'), True)
        weight_at, _ = pick_field(sources, ('body_weight_collected_at',))
        observed = timestamp(weight_at)
        if weight is not None and observed and created and start and observed <= created < start and observed.date().isoformat() == day:
            h['body_weight'] = weight
            h['sources']['body_weight'] = weight_source
            h['body_weight_collected_at'] = observed.isoformat()
        horses.append(h)
    for field in ('distance', 'course', 'star', 'away'):
        values = [h[field + '_index'] for h in horses if h[field + '_index'] is not None]
        for h in horses:
            value = h[field + '_index']
            h[field + '_rank'] = 1 + sum(v > value for v in values) if value is not None else None
    for h in horses:
        h['head_to_head'] = []
        for run in h['recent_runs']:
            if not run.get('race_id') or number(run.get('finish')) is None:
                continue
            for other in horses:
                if other is h:
                    continue
                for past in other['recent_runs']:
                    if past.get('race_id') != run['race_id'] or past.get('date') != run['date'] or number(past.get('finish')) is None:
                        continue
                    same = all(run.get(k) is not None and past.get(k) == run[k] for k in ('venue', 'surface', 'distance'))
                    if not same:
                        continue
                    differences = [f'{label} {run.get(key)}→{current}' for key, current, label in
                                   [('venue', info.get('racecourse') or info.get('venue'), '会場'),
                                    ('surface', info.get('surface'), '馬場'), ('distance', number(info.get('distance')), '距離')]]
                    h['head_to_head'].append({'race_id': run['race_id'], 'date': run['date'],
                                              'own_finish': run['finish'], 'opponent_no': other['horse_no'],
                                              'opponent_finish': past['finish'], 'condition_difference': ' / '.join(differences)})
    return {'race_id': race_id(result), 'race_date': day, 'venue': info.get('racecourse') or info.get('venue'),
            'race_name': info.get('race_name'), 'is_jump': is_jump_race(info),
            'prediction_created_at': result.created_at, 'scheduled_start': start.isoformat() if start else None,
            'time_status': 'pre_race' if pre else 'unverified', 'pace': next(iter(paces)) if len(paces) == 1 else None,
            'pace_conflict': len(paces) > 1, 'evaluation_context': evaluation_context,
            'source_files': deepcopy(result.source_files), 'horses': horses}
