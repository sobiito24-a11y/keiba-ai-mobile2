"""Versioned reproduction-input repair. Never feeds the formal model.

The formal producer and all its coefficients are reused on copied rows. Only
v1_reproducibility is replaced before assigning the research ranks and marks.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
from .v1_logic import (build_v1_evaluations, current_condition, jra_reproducibility,
                      assign_jra_top5_scores_and_marks, JRA_TOP5_REPRO_BONUS)
from .jra_win_probability import calculate_jra_win_probabilities
from .jra_display_mark import jra_display_mark_from_row
from .position_signals import is_jump_race

KEY = 'jra_repro_input_repair_shadow'
VERSION = 'jra_repro_input_repair_v1'
RUN_KEYS = ('recent_runs', 'recent_races', '_past_runs', 'past_runs', 'recent3_runs')
ALIASES = {
    'race_id': ('race_id', 'past_race_id'),
    'date': ('race_date', 'date', '開催日'),
    'venue': ('racecourse', 'venue', '競馬場', '場所'),
    'surface': ('surface', '芝ダ', 'course_type'),
    'distance': ('distance', '距離'), 'turn': ('direction', 'turn', '回り'),
    'finish': ('finish', 'position', '着順', 'rank'),
    'value': ('value', 'time_index', 'index'), 'label': ('label', 'run_label'),
}


def present(v):
    return v is not None and str(v).strip().lower() not in ('', 'nan', 'none', '<na>', '—', '-')


def num(v):
    try:
        n = float(v)
        return n if math.isfinite(n) and not isinstance(v, bool) else None
    except (ValueError, TypeError):
        return None


def horse_no(row):
    for key in ('horse_no', '馬番', 'number', '馬'):
        n = num(row.get(key))
        if n is not None and n > 0 and n.is_integer():
            return str(int(n))
    raise ValueError('馬番欠損: 行番号による結合禁止')


def records(table):
    return table.to_dict('records') if table is not None else []


def by_horse(rows):
    out = {}
    for row in rows:
        no = horse_no(row)
        if no in out:
            raise ValueError('馬番重複: ' + no)
        out[no] = row
    return out


def day(value):
    match = re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', str(value or ''))
    if match:
        try:
            return datetime(*map(int, match.groups())).date().isoformat()
        except ValueError:
            pass
    return None


def normalize_run(raw, source):
    run, fields = {}, {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if present(raw.get(alias)):
                run[field] = raw[alias]
                fields[field] = source + '.' + alias
                break
    for field in ('distance', 'finish', 'value'):
        if field in run:
            run[field] = num(run[field])
    run['date'] = day(run.get('date'))
    return run, fields


def same_run(a, b):
    if a.get('race_id') and b.get('race_id'):
        return str(a['race_id']) == str(b['race_id'])
    keys = ('date', 'venue', 'surface', 'distance')
    return all(present(a.get(k)) and present(b.get(k)) and a[k] == b[k] for k in keys)


def merged_runs(evaluation, overall, race_date):
    """Field merge only after identity match; conflicting runs are excluded.

    No month/day inference, no positional zip, no current finish/odds inputs.
    Original runs and provenance remain in the audit even when excluded.
    """
    groups, rejected = [], []
    cutoff = day(race_date)
    for table_name, row in [('horse_evaluation', evaluation), ('overall_table', overall)]:
        for key in RUN_KEYS:
            values = row.get(key)
            if isinstance(values, str):
                try:
                    values = json.loads(values)
                except (ValueError, TypeError):
                    rejected.append({'source': table_name+'.'+key, 'reason': '過去走JSON不正'})
                    continue
            if not isinstance(values, list):
                continue
            for raw in values:
                if not isinstance(raw, dict):
                    continue
                run, provenance = normalize_run(raw, table_name+'.'+key)
                target = next((g for g in groups if same_run(g['run'], run)), None)
                if target is None:
                    groups.append({'run': run, 'sources': provenance, 'conflicts': [], 'raw': [deepcopy(raw)]})
                    continue
                target['raw'].append(deepcopy(raw))
                for field, value in run.items():
                    if not present(value):
                        continue
                    if present(target['run'].get(field)) and target['run'][field] != value:
                        if field not in ('label', 'value'):
                            target['conflicts'].append(field)
                    elif not present(target['run'].get(field)):
                        target['run'][field] = value
                        target['sources'][field] = provenance.get(field)
    usable = []
    for group in groups:
        run = group['run']
        reason = ('過去走の項目競合' if group['conflicts'] else
                  '開催日不明' if not cutoff or not run.get('date') else
                  '今回以降の走を除外' if run['date'] >= cutoff else
                  '競走条件不足' if not run.get('surface') or not run.get('distance') else '')
        group['status'] = reason or '有効'
        if not reason:
            usable.append(run)
    usable.sort(key=lambda r: (r['date'], str(r.get('race_id', ''))), reverse=True)
    return usable[:3], {'runs': groups, 'rejected': rejected, 'valid_runs': len(usable[:3]),
                       'missing_reason': '' if usable else '有効な発走前過去走なし'}


def evaluate_repro_candidate(result, *, formal_rows=None, evaluated_at=None):
    if result.race_mode != 'jra':
        return None
    info = result.race_info or {}
    if is_jump_race(info):
        return {'model_version': VERSION, 'status': '障害対象外', 'horses': []}
    evaluations, overall = records(result.horse_evaluation), records(result.overall_table)
    ev, ov = by_horse(evaluations), by_horse(overall)
    source = evaluations or overall
    # Formal formula remains unchanged. This baseline is used only for components.
    base = build_v1_evaluations(source, 'jra', info)['rows']
    frozen = by_horse(formal_rows or [])
    if not frozen:
        from .jra_formal_snapshot import saved_formal_comparison
        saved = saved_formal_comparison(result) or {}
        frozen = by_horse(saved.get('rows', []))
        cal = (result.debug_info or {}).get('jra_win_probability_calibration') or {}
        for no, h in by_horse(cal.get('horses', [])).items():
            frozen[no] = {**frozen.get(no, {}), **h}
    candidate = deepcopy(base)
    audits = {}
    current = current_condition(source, info)
    for horse in candidate:
        no = horse_no(horse)
        left, right = ev.get(no, {}), ov.get(no, {})
        if present(left.get('horse_id')) and present(right.get('horse_id')) and str(left['horse_id']) != str(right['horse_id']):
            raise ValueError('馬番とhorse_idの競合: ' + no)
        runs, audit = merged_runs(ev.get(no, {}), ov.get(no, {}), info.get('race_date') or info.get('date'))
        repro = jra_reproducibility(runs, current)
        horse['v1_reproducibility'] = repro['rank']
        horse['v1_reproducibility_reason'] = repro['reason']
        audits[no] = {**audit, 'normalized_runs': runs, 'repro': repro}
    assign_jra_top5_scores_and_marks(candidate, info)
    probabilities = calculate_jra_win_probabilities([h['jra_top5_score'] for h in candidate])
    rows = []
    for old, new, probability in zip(base, candidate, probabilities):
        no = horse_no(new)
        official = frozen.get(no, old)
        stored_mark = jra_display_mark_from_row(official)
        rows.append({'horse_no': no, 'horse_name': new.get('name') or ev.get(no, ov.get(no, {})).get('馬名'),
                     'formal_rank': official.get('jra_top5_rank'), 'formal_score': official.get('jra_top5_score'),
                     'formal_mark': stored_mark if stored_mark else jra_display_mark_from_row(old),
                     'formal_mark_source': 'saved_canonical' if stored_mark else 'existing_formula_reference_not_saved',
                     'formal_probability': official.get('jra_win_probability'),
                     'formal_source': 'saved' if no in frozen else 'fresh_existing_formula',
                     'candidate_rank': new['jra_top5_rank'], 'candidate_score': new['jra_top5_score'],
                     'candidate_mark': jra_display_mark_from_row(new), 'candidate_probability': probability,
                     'pure_ability': new['jra_pure_ability_score'], 'pure_rank': new.get('_v1_ability_rank'),
                     'repro_grade': new['v1_reproducibility'], 'repro_bonus': new['jra_repro_bonus'],
                     'repro_reason': new['v1_reproducibility_reason'], 'old_repro_bonus': old['jra_repro_bonus'],
                     'pace_bonus': new['jra_pace_bonus'], 'training_bonus': new['jra_training_bonus'],
                     'position_bonus': new['jra_position_bonus'], 'input_audit': audits[no]})
    from .newspaper_v2_inputs import race_id
    payload = {'model_version': VERSION, 'status': 'research_only', 'race_id': race_id(result),
               'evaluated_at': evaluated_at or datetime.now().isoformat(timespec='seconds'),
               'coefficients': dict(JRA_TOP5_REPRO_BONUS), 'horses': rows}
    payload['input_hash'] = hashlib.sha256(json.dumps([current, audits], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return payload


def attach_repro_candidate(result):
    """Fresh predictor only. Restore/UI must never invoke this function."""
    if result.race_mode != 'jra' or KEY in (result.debug_info or {}):
        return result
    try:
        candidate = evaluate_repro_candidate(result)
    except (ValueError, TypeError, KeyError) as exc:
        candidate = {'model_version': VERSION, 'status': 'input_error', 'reason': str(exc), 'horses': []}
    result.debug_info = {**(result.debug_info or {}), KEY: candidate}
    return result


def candidate_snapshot(result):
    saved = (result.debug_info or {}).get(KEY)
    return {KEY: deepcopy(saved)} if result.race_mode == 'jra' and isinstance(saved, dict) else {}


def repro_candidate_html(result):
    from html import escape
    saved = (result.debug_info or {}).get(KEY)
    if result.race_mode != 'jra':
        return ''
    title = '再現性入力修正版（研究候補・正式予想には不使用）'
    if not saved:
        return '<details><summary>'+title+'</summary>未計算（旧Snapshotは再計算しません）</details>'
    cards = []
    for h in sorted(saved.get('horses', []), key=lambda h: h['candidate_rank']):
        label = f"{h['horse_no']} {h['horse_name']}｜正式 {h['formal_rank']}位 {h['formal_score']} → 研究 {h['candidate_rank']}位 {h['candidate_score']} {h['candidate_mark']}"
        reason = f"再現性{h['repro_grade']} +{h['repro_bonus']}：{h['repro_reason']}"
        p = h.get('candidate_probability')
        probability = f'研究推定勝率 {100*p:.1f}%（未校正・参考）' if p is not None else '研究推定勝率 —'
        cards.append('<p>'+escape(label)+'<br>'+escape(reason)+'<br>'+escape(probability)+'</p>')
    return '<details class="jra-repro-research"><summary>'+title+'</summary>'+escape(saved.get('status',''))+''.join(cards)+'</details>'
