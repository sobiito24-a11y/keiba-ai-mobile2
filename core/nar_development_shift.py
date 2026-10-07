"""NAR position-shift research only; consumes frozen output, never ranks horses."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from .prediction_table_ui import horse_key, number, pick, text
from .nar_display_mark import display_mark
from .nar_ability_rank import canonical_nar_ability_rank

KEY = "nar_development_shift_shadow"
VERSION = "nar_development_shift_v1_20261008"

def evaluate(data, rows):
    rows = deepcopy(rows)
    for key,alias in [('distance_index','距離指数'),('course_index','コース指数')]:
        values = [number(pick(r,key,alias)) for r in rows]
        for row,value in zip(rows,values):
            if number(row.get(key+'_rank')) is None and value is not None:
                row[key+'_rank'] = 1 + sum(v>value for v in values if v is not None)
    by = {horse_key(r): r for r in rows}
    audit = []
    averages = {horse_key(r): number(pick(r, '平均指数', 'average_index', '3走平均')) for r in rows}
    for h in data.get('horses', []):
        row = by.get(h['horse_no'], {})
        member = row.get('pure_ability_top5_group')
        mark = display_mark(row)
        # Read the saved class-change judgement; never infer it from age or ability.
        statuses = {text(row[k]) for k in ('class_shift_market', 'クラス変動')
                    if text(row.get(k)) in ('同級', '昇級', '降級')}
        status = next(iter(statuses)) if len(statuses) == 1 else None
        rates = [number(row.get(k)) for k in ('_jockey_course_place_rate', 'jockey_course_top3_rate')]
        rates = {r for r in rates if r is not None and 0 <= r <= 100}
        rate = next(iter(rates)) if len(rates) == 1 else None
        style, group = h.get('running_style'), h.get('corner4_group')
        known = [member is not None, 'nar_check_selected' in row or bool(member),
                 style in ('逃','先','差','追'), group in ('front','middle','back'),
                 status is not None, rate is not None]
        value = None if not all(known) else (
            not bool(member) and not mark and style == '先'
            and group in ('middle','back') and status == '同級' and rate >= 25.0)
        # Known exclusions can safely return false even when other inputs are absent.
        if bool(member) or mark or (known[2] and style != '先') or group == 'front' or status in ('昇級','降級') or (rate is not None and rate < 25):
            value = False
        position = {'middle':'中団','back':'後方','front':'先団'}.get(group)
        avg = averages.get(h['horse_no'])
        item = dict(horse_no=h['horse_no'],horse_name=h.get('horse_name'),
            development_shift_shadow=value,
            development_shift_reason=(f'普段先行 → 今回{position}想定 / 同級戦 / 騎手コース複勝率{rate:g}%' if value else ''),
            development_shift_missing=[label for label,ok in zip(
                ('正式候補集合','既存✓選抜','脚質','今回位置','クラス変動','騎手コース複勝率'),known) if not ok],
            development_shift_from_style=style, development_shift_to_position=position,
            development_shift_jockey_place_rate=rate/100 if rate is not None else None,
            development_shift_class_status=status, development_shift_pace=data.get('pace_prediction','不明'),
            formal_mark=mark, pure_ability_top5_group=member, nar_final_rank=number(row.get('nar_final_rank')),
            pure_ability_rank=canonical_nar_ability_rank(row), corner4_rank=h.get('corner4_rank'),
            average_index_rank=1+sum(v>avg for v in averages.values() if v is not None) if avg is not None else None,
            distance_index_rank=number(row.get('distance_index_rank')),
            course_index_rank=number(row.get('course_index_rank')),
            class_source='saved class_shift_market / クラス変動',
            current_class=text(pick(row,'current_class_market','_current_class_label')),
            previous_class=text(pick(row,'previous_class_market','_previous_class_label')),
            class_basis=text(pick(row,'クラス根拠','class_basis_market')))
        item['input_hash'] = hashlib.sha256(json.dumps(item,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
        audit.append(item)
    return dict(model_version=VERSION,race_id=data.get('race_id'),evaluated_at=datetime.now(timezone.utc).isoformat(),
                source='prediction_inputs_only',horses=audit)

def saved(result, data, rows):
    debug=result.debug_info or {}
    old=debug.get(KEY)
    if isinstance(old,dict):
        return deepcopy(old)
    data=deepcopy(data)
    if not data.get('race_id'):
        ids={str((debug.get(k) or {}).get('race_id')) for k in ('course_materials','jockey_course_materials')
             if (debug.get(k) or {}).get('race_id')}
        if len(ids)==1:
            data['race_id']=next(iter(ids))
    return evaluate(data,rows)

def commentary(data, rows, main, eligible, impact, intro, key_sentence):
    """NAR-only four paragraphs; no score/mark/purchase outputs."""
    audit=data['development_shift_audit']
    by={r['horse_no']:r for r in audit['horses']}
    horses={h['horse_no']:h for h in data['horses']}
    evidence=[]
    for h in main:
        row=by.get(h['horse_no'],{})
        facts=[]
        rank=number(row.get('pure_ability_rank'))
        if rank is not None and rank<=3: facts.append(f'純能力{int(rank)}位')
        for label,key in [('距離','distance_index_rank'),('コース','course_index_rank')]:
            n=number(row.get(key))
            if n is not None and n<=3:facts.append(f'{label}指数{int(n)}位')
        if facts:
            ending='展開が厳しくても能力面では残したい。' if impact(h)[0]=='注意' else '能力面の裏付けがあり、今回の展開も噛み合う。' if impact(h)[0]=='プラス' else '能力面の裏付けとして確認したい。'
            evidence.append(h['horse_no']+'は'+'に加え'.join(facts)+'。'+ending)
        elif impact(h)[0]=='プラス':
            evidence.append(h['horse_no']+'は本線の中で今回の展開の恩恵を受けやすい。')
    additions=[]
    # Existing outside marks first, then research qualifiers, then other formal support.
    outside=[h for h in eligible if h.get('development_support_mark') and impact(h)[0]=='プラス']
    shifts=[item for item in audit['horses'] if item.get('development_shift_shadow') is True]
    shifts.sort(key=lambda h:(h['pure_ability_rank'] or float('inf'),number(h['horse_no']) or float('inf')))
    formal=[h for h in eligible if h.get('formal_candidate') and impact(h)[0]=='プラス']
    selected=set()
    for h in outside:
        if len(selected)>=2:break
        selected.add(h['horse_no'])
        additions.append('本線外では'+h['development_support_mark']+h['horse_no']+h['horse_name']+'が相手候補。'+impact(h)[1]+'。')
    for a in shifts:
        if len(selected)>=2:break
        selected.add(a['horse_no'])
        pace=a['development_shift_pace']
        ending={'H':'前が流れる形なら、普段より後ろで脚を溜める形がプラスに働く可能性がある。',
                'M':'普段より控える想定。前が競り合う形なら、脚を溜めて浮上する余地がある。',
                'S':'普段より後ろになる想定で、スローなら位置取りが不利になる可能性もある。'}.get(pace,'ペースが未取得のため、位置取り変化の有利不利は判断を保留したい。')
        additions.append('本線外では'+a['horse_no']+a['horse_name']+'を展開から浮上候補として注目。普段は先行する馬だが今回は'+a['development_shift_to_position']+'想定。同級戦で騎手コース複勝率'+f"{a['development_shift_jockey_place_rate']*100:g}"+'%の裏付けがある。'+ending)
    for h in formal:
        if len(selected)>=2:break
        selected.add(h['horse_no'])
        additions.append('本線以外では'+h['formal_mark']+h['horse_no']+h['horse_name']+'も相手候補。'+impact(h)[1]+'。')
    risks=[h for h in main if h.get('position_difference') and impact(h)[0]=='注意' and h['horse_no'] not in selected]
    if risks:
        key_sentence+=' '+ '・'.join(h['horse_no'] for h in risks)+'は普段の脚質と今回位置が異なり、流れの中で脚を残せるかも確認したい。'
    return [intro,' '.join(evidence) or '本線の能力・条件指数の順位情報が不足しており、展開との比較は保留。',
            ' '.join(additions) or '本線外で今回の展開から取り上げる候補は確認できません。',
            key_sentence]
