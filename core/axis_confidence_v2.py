"""Post-prediction axis diagnostics. Never an input to ranking or navigation."""
from copy import deepcopy, copy
import re
from collections import Counter
from .nar_top5_order import number, horse_no

VERSION = 'axis_confidence_v2_20261007'
KEY = 'axis_confidence_v2'


def pickup_order(attention_horses, horse_numbers):
    """Array positions are authoritative; never sort or compact invalid entries."""
    if not isinstance(attention_horses, list) or not attention_horses:
        return {}, ['attention_horses未取得']
    parsed = []
    issues = []
    for index, text in enumerate(attention_horses, 1):
        match = re.match(r'^\s*(\d+)番', text) if isinstance(text, str) else None
        key = str(int(match[1])) if match else None
        parsed.append((index, key))
        if key is None or key not in horse_numbers:
            issues.append(f'{index}番手：馬番解析不能または出走馬に未対応')
    counts = Counter(key for _, key in parsed if key is not None)
    mapping = {}
    for index, key in parsed:
        if key in horse_numbers and counts[key] == 1:
            mapping[key] = index
        elif counts[key] > 1:
            issues.append(f'{index}番手：馬番{key}重複')
    return mapping, issues


def evaluate(rows, mode):
    """Inputs use probability fractions, jockey percentages, frozen pickup rank."""
    out = []
    for source in rows:
        row = dict(source)
        rank = number(row.get('pickup_rank' if mode == 'nar' else 'jra_top5_rank'))
        p = number(row.get('nar_win_probability' if mode == 'nar' else 'jra_win_probability'))
        j = number(row.get('current_jockey_place_rate'))
        valid = rank is not None and rank >= 1 and rank.is_integer() and p is not None and 0 <= p <= 1 and j is not None and 0 <= j <= 100
        if mode == 'nar':
            grade, reason = 'C', '軸にはしない（ピックアップ3番手以下／軸条件未達）'
            if rank is None:
                grade, reason = None, 'ピックアップ順位未取得'
            elif row.get('nar_check_selected'):
                reason = '✓ヒモ候補は軸対象外'
            elif not valid:
                grade, reason = None, '判定不能：順位・AI推定勝率・騎手コース複勝率の不足'
            elif rank == 1:
                if p >= .15 and j >= 35:
                    grade, reason = 'A', '1番手・AI推定勝率15%以上・騎手35%以上：1頭軸候補'
                elif p < .20 and j < 25:
                    reason = '1番手だがAI推定勝率20%未満かつ騎手25%未満'
                else:
                    grade, reason = 'B', '1番手・A未達だが弱条件に該当しない：相手軸候補'
            elif rank == 2 and p >= .15 and j >= 30:
                grade, reason = 'B', '2番手・AI推定勝率15%以上・騎手30%以上：相手軸候補'
            row.update(legacy_axis_confidence=source.get('axis_confidence'), axis_confidence=grade, axis_reason=reason)
        else:
            candidate = valid and ((rank == 1 and p >= .20 and j >= 20) or (rank == 2 and p >= .10 and j >= 35))
            row.update(jra_axis_a_shadow=bool(candidate), jra_axis_shadow_reason='軸A Shadow候補' if candidate else '条件未達' if valid else '判定不能：正式順位・勝率・騎手成績不足')
        out.append(row)
    def priority(row):
        rank = number(row.get('pickup_rank' if mode == 'nar' else 'jra_top5_rank'))
        p = number(row.get('nar_win_probability' if mode == 'nar' else 'jra_win_probability'))
        j = number(row.get('current_jockey_place_rate'))
        last = number(row.get('pure_ability_rank' if mode == 'nar' else 'jra_top5_score'))
        return (rank if rank is not None else float('inf'), -p if p is not None else float('inf'), -j if j is not None else float('inf'), (last if mode == 'nar' else -last) if last is not None else float('inf'))
    if mode == 'nar':
        for grade, limit in [('A', 1), ('B', 2)]:
            for row in sorted([r for r in out if r['axis_confidence'] == grade], key=priority)[limit:]:
                row.update(axis_confidence='C', axis_reason='軸候補上限により対象外')
        a = sum(r['axis_confidence'] == 'A' for r in out)
        b = sum(r['axis_confidence'] == 'B' for r in out)
        state = '2頭軸検討可能' if a and b else '1頭軸候補あり' if a else 'B-Bの2頭軸候補' if b >= 2 else '無理に1頭軸にしない' if b else '軸不在 / 見送り寄り'
    else:
        for row in sorted([r for r in out if r['jra_axis_a_shadow']], key=priority)[1:]:
            row.update(jra_axis_a_shadow=False, jra_axis_shadow_reason='Shadow A上限1頭：正式順位優先')
        state = '軸A Shadowあり' if any(r['jra_axis_a_shadow'] for r in out) else '軸A Shadowなし'
    return dict(model_version=VERSION, race_mode=mode, race_axis_state=state, horses=out)


def snapshot(result):
    """Read frozen inputs after prediction. No legacy table fields are replaced."""
    result = copy(result)
    for field, default in [("debug_info", {}), ("race_info", {}), ("horse_evaluation", None), ("overall_table", None)]:
        if not hasattr(result, field):
            setattr(result, field, default)
    saved = (result.debug_info or {}).get(KEY)
    if isinstance(saved, dict):
        return deepcopy(saved)
    from .nar_top5_order import result_rows, snapshot as nar_order
    from .nar_ability_rank import canonical_nar_ability_rank
    from .jockey_positive import snapshot as jockey_snapshot
    from .position_signals import corner4_rank
    rows = result_rows(result)
    jockeys = {horse_no(h): h for h in jockey_snapshot(result)['horses']}
    mode = result.race_mode
    if mode == 'nar':
        from .nar_win_probability import nar_win_probability_snapshot
        from .nar_check_selection import snapshot as checks
        order = {horse_no(h): h for h in nar_order(result)['horses']}
        probability = nar_win_probability_snapshot(result)
        selected = {horse_no(h): h for h in checks(result)['horses']}
        pickup, pickup_issues = pickup_order(getattr(result, 'attention_horses', None), {horse_no(h) for h in rows})
    else:
        from .jra_formal_snapshot import saved_formal_comparison
        # Never reconstruct missing historical formal ranks with today's model.
        formal = saved_formal_comparison(result)
        order = {horse_no(h): h for h in (formal or {}).get('rows', [])}
        probability = (result.debug_info or {}).get('jra_win_probability_calibration')
        selected = {}
    probabilities = {horse_no(h): h for h in (probability or {}).get('horses', [])}
    inputs = []
    for row in rows:
        key = horse_no(row)
        official = order.get(key, {})
        prob = probabilities.get(key, {})
        common = dict(horse_no=key, horse_name=row.get('馬名') or row.get('name'),
                      current_jockey_place_rate=jockeys.get(key, {}).get('current_jockey_place_rate'),
                      netkeiba_corner4_rank=corner4_rank(row),
                      predicted_pace=row.get('netkeiba_pace') or (result.race_info or {}).get('pace'),
                      axis_confidence=row.get('axis_confidence'), pure_ability_rank=canonical_nar_ability_rank(row))
        if mode == 'nar':
            common.update(pickup_rank=pickup.get(key),
                          pickup_rank_source='prediction_result.attention_horses_array_order',
                          pure_ability_top5_group=official.get('pure_ability_top5_group', False),
                          nar_check_selected=selected.get(key, {}).get('nar_check_selected', False),
                          nar_win_probability=prob.get('nar_win_probability', row.get('nar_win_probability')))
        else:
            common.update(jra_top5_rank=official.get('jra_top5_rank', prob.get('jra_top5_rank', row.get('jra_top5_rank'))),
                          jra_top5_score=official.get('jra_top5_score', prob.get('jra_top5_score', row.get('jra_top5_score'))),
                          jra_win_probability=prob.get('jra_win_probability', row.get('jra_win_probability')))
        inputs.append(common)
    payload = evaluate(inputs, mode)
    if mode == 'nar':
        payload['pickup_source'] = 'prediction_result.attention_horses'
        payload['pickup_parse_issues'] = pickup_issues
        payload['attention_horses'] = deepcopy(getattr(result, 'attention_horses', None))
    payload['race_id'] = (result.race_info or {}).get('race_id')
    payload['source'] = 'frozen_prediction_inputs_post_prediction'
    return payload


def attach(result):
    result.debug_info = dict(result.debug_info or {}, **{KEY: snapshot(result)})
    return result


def restore(result, payload):
    saved = payload.get(KEY) or (payload.get('mobile_snapshot') or {}).get(KEY)
    if isinstance(saved, dict):
        result.debug_info = dict(result.debug_info or {}, **{KEY: deepcopy(saved)})
    return result


def summary_lines(payload):
    horses = payload['horses']
    def names(rows):
        return ' / '.join(str(h['horse_no']) + ' ' + str(h.get('horse_name') or '') for h in rows) or 'なし'
    if payload['race_mode'] == 'nar':
        lines = [payload['race_axis_state'],
                 '軸A（1頭軸候補）：' + names([h for h in horses if h['axis_confidence'] == 'A']),
                 '軸B（相手軸候補）：' + names([h for h in horses if h['axis_confidence'] == 'B'])]
        if any(h['axis_confidence'] is None for h in horses):
            lines.append('入力不足の馬は軸判定未取得')
        return lines
    return ['軸A Shadow（未正式採用）：' + names([h for h in horses if h['jra_axis_a_shadow']])]


def summary_html(result):
    from html import escape
    return '<div class="ka-note">' + '<br>'.join(escape(line) for line in summary_lines(snapshot(result))) + '</div>'


def horse_label(result, key):
    if result.race_mode != 'nar':
        return ''
    horse = next((h for h in snapshot(result)['horses'] if h['horse_no'] == str(key)), {})
    grade = horse.get('axis_confidence')
    return {'A':'軸A｜1頭軸候補','B':'軸B｜相手軸候補','C':'軸にはしない（C）'}.get(grade, '軸判定：未取得')
