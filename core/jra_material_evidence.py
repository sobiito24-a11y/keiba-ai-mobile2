"""JRA evidence badges, separate from the fixed NAR hypotheses.

Uses the current JRA practical evidence inputs, not its A/B/C selections.
No badge changes a final mark or a prediction score.
"""
from copy import deepcopy
from .jra_practical_shadow import number

VERSION = 'jra_material_reconsideration_shadow_v1'


def evaluate_jra_materials(data, *, include_base=True):
    out = deepcopy(data)
    if data.get('time_status') != 'pre_race' or data.get('is_jump'):
        return {'model_version': VERSION, 'status': 'excluded_or_time_unverified', 'horses': []}
    for h in out['horses']:
        good, bad, missing = {}, {}, []
        rank = number(h.get('formal_rank'))
        if include_base and rank is not None and rank <= 3:
            good['formal'] = f'正式JRA {rank:g}位'
        c4, pace = number(h.get('corner4_rank')), data.get('pace')
        if c4 is not None and pace in ('S', 'M', 'H'):
            if pace == 'S' and c4 <= 4:
                good['position'] = f'スロー想定×4角{c4:g}番手'
            elif pace in ('M', 'H') and 5 <= c4 <= 8:
                good['position'] = f'{pace}ペース想定×4角{c4:g}番手'
            elif pace == 'S' and c4 >= 9:
                bad['position'] = f'スロー想定×4角{c4:g}番手'
        else:
            missing.append('4角想定／予測ペース')
        hits=[]
        for key,label in [('distance','距離'),('course','コース'),('star','★'),('away','☆')]:
            r=number(h.get(key+'_rank'))
            if r is not None and r<=3:
                hits.append(f'{label}{r:g}位')
            elif r is None:
                missing.append(label)
        if hits:
            good['condition']=' / '.join(hits)
        grade=h.get('training_grade');rest=number(h.get('rest_days'))
        if grade in ('A','B'):
            good['state']='今回調教'+grade
        elif grade=='D':
            bad['state']='今回調教D'
        if rest is not None and rest>=90 and grade in ('C','D'):
            returns=[r for r in h.get('layoff_returns',[]) if number(r.get('finish')) is not None and 1<=r['finish']<=3]
            if returns:
                good['return']='過去休み明け3着内実績あり'
            else:
                bad['state']=f'休養{rest:g}日×調教{grade}（復帰材料を確認）'
        if grade not in ('A','B','C','D'):
            missing.append('調教')
        if h.get('class_change')=='降級':
            good['class']='前走との明示的クラス比較で降級'
        load=number(h.get('load_change'))
        if load is not None and load>=2:
            bad['load']=f'斤量前走比+{load:g}kg（単独の消し材料ではない）'
        h.update(good='◎' if len(good)>=2 else '○' if good else '—',
                 concern='⚠' if len(bad)>=2 else '△' if bad else '—',
                 good_reasons=good,concern_reasons=bad,missing=missing)
    official=sorted([h for h in out['horses'] if number(h.get('formal_rank')) is not None and 1<=h['formal_rank']<=5],key=lambda h:(h['formal_rank'],int(h['horse_no'])))
    top=[str(h['horse_no']) for h in official];shadow=top[:];swap=None
    if len(top)==5 and all(number(h.get('formal_rank')) is not None for h in out['horses']):
        outside=[h for h in out['horses'] if h['formal_rank']>5 and h['good']=='◎' and h['concern']!='⚠']
        inside=[h for h in official if h['concern']=='⚠']
        outside.sort(key=lambda h:(h['formal_rank'],int(h['horse_no'])))
        inside.sort(key=lambda h:(-h['formal_rank'],int(h['horse_no'])))
        if outside and inside:
            added,removed=outside[0],inside[0]
            shadow[shadow.index(str(removed['horse_no']))]=str(added['horse_no'])
            swap={'added':str(added['horse_no']),'removed':str(removed['horse_no']),
                  'positive':added['good_reasons'],'negative':removed['concern_reasons']}
    out.update(model_version=VERSION,official_top5=top,shadow_top5=shadow,reconsideration=swap,
               eligible_box=len(top)==5,status='shadow_only')
    return out
