"""Independent exploratory watchlist. Never changes formal marks or ranks.

Prespecified v1: both course and distance top3, or one top3 plus supported jockey.
No ability-rank ceiling, no front-position gate; max two. Not efficacy validated.
"""
from .new_ai_research import num
VERSION='nar_outside_condition_watch_v1'

def select(rows,limit=2):
    candidates=[]
    for h in rows:
        rank=num(h.get('formal_rank'))
        if rank is None or rank<=5:continue
        positives=[];missing=[]
        for key,label in [('course_rank','コース指数上位3'),('distance_rank','距離指数上位3')]:
            value=num(h.get(key))
            if value is None:missing.append(key)
            elif 1<=value<=3:positives.append(label)
        n=num(h.get('jockey_n'));p=num(h.get('jockey_rate'))
        if n is None or p is None:missing.append('騎手母数または率')
        elif n>=20 and p>=25:positives.append('騎手コース実績：20走以上・3着内率25%以上')
        condition=sum(x in positives for x in ('コース指数上位3','距離指数上位3'))
        if condition==0 or len(positives)<2:continue
        # Only supported evidence orders the shortlist. No hidden point additions.
        cr=num(h.get('course_rank'));dr=num(h.get('distance_rank'))
        candidates.append({**h,'reasons':positives,'missing':missing,
           'cautions':['探索用・有効性未確定','コース・距離指数は相関があり独立した2根拠とは限らない'],
           'version':VERSION,'_order':(-len(positives),max(cr or 999,dr or 999),rank,int(h['no']))})
    chosen=sorted(candidates,key=lambda h:h['_order'])[:max(0,min(2,limit))]
    return [{k:v for k,v in h.items() if k!='_order'} for h in chosen]

def from_view(view):
    return select([dict(no=h['no'],name=h['name'],formal_rank=h.get('rank'),
        research_rank=h.get('research_rank'),course_rank=h.get('course',{}).get('rank'),
        distance_rank=h.get('distance',{}).get('rank'),style=h.get('style'),corner=h.get('corner'),
        **h.get('research_inputs',{})) for h in view])

def html(view,portable=None):
    from html import escape
    import json
    if not view or view[0].get('mode')!='nar':return ''
    rows=from_view(view);e=lambda v:escape(str(v))
    if portable and portable.get('authority')=='NAR':
        base={str(r['no']):r for r in portable.get('models',{}).get('A',{}).get('rows',[])}
        matches=len(base)==len(view) and all(str(h['no']) in base and h['name']==base[str(h['no'])]['name'] and num(h['rank'])==base[str(h['no'])]['formal_rank'] for h in view)
        model=portable.get('models',{}).get('NAR_P_F1',{})
        if matches and model.get('complete'):
            ranks={str(r['no']):r['research_rank'] for r in model['rows']}
            for r in rows:r['research_rank']=ranks.get(str(r['no']))
    out='<section class="nar-research-watch"><h3>NAR研究注目馬（最大2頭・既存✓とは別）</h3><p>採用注目馬：0頭。探索検証で従来✓を上回らず採用保留です。以下は検証用候補で、正式Top5・印・✓へ反映しません。</p>'
    if not rows:out+='<p>今回は0頭：十分な条件根拠が揃いません。</p>'
    if rows:out+='<details><summary>採用保留の検証候補を確認</summary>'
    for r in rows:
        out+='<details><summary>'+e(r['no'])+' '+e(r['name'])+'／正式'+e(r['formal_rank'])+'位／研究順位 '+e(r.get('research_rank') or '未取得')+'</summary><p>好材料：'+e(' / '.join(r['reasons']))+'</p><p>注意：'+e(' / '.join(r['cautions']))+'</p><p>未取得：'+e(r['missing'])+'</p><pre>'+e(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    if rows:out+='</details>'
    return out+'<small>'+VERSION+'</small></section>'
