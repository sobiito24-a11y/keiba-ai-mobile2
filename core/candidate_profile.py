"""Display-only facts. No scoring, network or mutation of saved predictions."""
from datetime import date
import re
from statistics import pstdev
from html import escape
from .prediction_table_ui import number, text, pick
from .recent_races import build_recent_races

VERSION='candidate_facts_v1'
REFERENCE_CONFIG={'max_candidates':2,'minimum_reasons':2,'top_rank':5,'stable_sd':5}

def day(value):
    try:return date.fromisoformat(str(value).split('T')[0].replace('/','-'))
    except (ValueError,TypeError):return None

def facts(row,info):
    current=day(pick(info or {},'race_date','date','開催日'));runs=[];excluded=0
    raw=row.get('_past_runs') or row.get('past_runs')
    raw=raw if isinstance(raw,list) else []
    for run in build_recent_races(row):
        d=day(run.get('date'))
        if not current or not d or d>=current:
            excluded+=1;continue
        matches=[r for r in raw if isinstance(r,dict) and day(r.get('race_date',r.get('date')))==d]
        extra=matches[0] if len(matches)==1 else {}
        rid=str(extra.get('race_id',''))
        runs.append({k:text(run.get(k)) for k in ('label','date','venue','surface','distance','turn','finish','passing_order','race_name')}|dict(
            time_index=number(run.get('time_index')),race_id=rid if re.fullmatch(r'20\d{10}',rid) else None,
            class_raw=text(extra.get('race_data2') or extra.get('class_raw_text') or (run.get('race_name') if run.get('race_name') not in ('映像を見る','レース映像','動画') else ''))))
    runs.sort(key=lambda r:day(r['date']),reverse=True);runs=runs[:3]
    values=[r['time_index'] for r in runs];valid=len(runs)==3 and all(v is not None for v in values)
    sd=pstdev(values) if valid else None
    stars=(5 if sd<=3 else 4 if sd<=5 else 3 if sd<=8 else 2 if sd<=12 else 1) if valid else None
    state='判定不可'
    if valid:state='上向き' if values[0]-values[1]>=3 and values[1]-values[2]>=3 else '注意' if values[1]-values[0]>=3 and values[2]-values[1]>=3 else '横ばい'
    from .newspaper_v2_enrichment import conservative_class
    from .newspaper_v2_class_inputs import comparison_blockers
    from .class_context import class_change
    current_context=conservative_class(dict(venue=pick(info or {},'venue','racecourse','競馬場'),surface=pick(info or {},'surface','芝ダート'),race_name=pick(info or {},'race_name','レース名'),race_data2=pick(info or {},'raw_class_text','race_data2')))
    previous_context=conservative_class(dict(venue=runs[0]['venue'],surface=runs[0]['surface'],race_name=runs[0]['class_raw'])) if runs else {}
    shift=class_change(current_context,previous_context) if runs and not comparison_blockers(current_context,previous_context) else '判定不可（クラス体系・年齢条件・会場の照合不足）'
    same=[]
    for run in runs:
        ctx=conservative_class(dict(venue=run['venue'],surface=run['surface'],race_name=run['class_raw']))
        if not comparison_blockers(current_context,ctx) and class_change(current_context,ctx)=='同級':same.append(run)
    from .recent_condition_facts import evaluate
    conditions=evaluate(row,info,runs)
    return dict(condition_facts=conditions,version=VERSION,runs=runs,excluded=excluded,state=state,stability_stars=stars,stability_sd=sd,
        state_reason='同じ保存タイム指数の直近3走を比較。連続3点以上増=上向き、連続3点以上減=注意、それ以外=横ばい。状態全般の保証ではありません。' if valid else '発走日前と確認できる3走の指数が不足',
        rest_days=(current-day(runs[0]['date'])).days if runs else None,
        body_weight=text(pick(row,'馬体重','body_weight')),body_weight_change=text(pick(row,'馬体重増減','body_weight_change')),
        current_class=text(pick(info or {},'raw_class_text','race_data2','class_name')),class_shift=shift,matchups=[],
        same_class_n=len(same),same_class_top3=sum(bool(re.fullmatch(r'[123](?:着)?',r['finish'])) for r in same),
        pace=text(pick(row,'netkeiba_pace','_netkeiba_pace','provider_pace_market')),style_rate=text(pick(row,'脚質複勝率','style_place_rate')),style_n=number(pick(row,'脚質出走回数','style_starts')))

def enrich(view,sources,info):
    """Called on the UI projection, never on the source prediction rows."""
    for h in view:
        h['profile']=facts(sources.get(h['no'],{}),info)
        from .recent_condition_facts import materials, STATES
        data=h['profile']['condition_facts']
        tags=materials(data)
        h['plus']=' / '.join([v for v in [h.get('plus',''),*tags] if v and v!='—'])
        ev=h.get('candidate_evidence',{})
        ev.setdefault('plus',[]).extend(tags)
        if h.get('mark') in ('◎','○','▲'):
            ev.setdefault('neutral',[]).extend(label+'：'+STATES[data['conditions'][key]['state']]+'（近3走・減点なし）' for key,label in [('venue','同会場'),('turn','同回り')] if data['conditions'][key]['state']!='placed')
        if h.get('mode')=='nar' and h.get('mark') in ('','—','-') and 0<(number(h.get('ability_rank')) or 999)<=8 and data['conditions']['venue']['top3']:
            ev.setdefault('neutral',[]).append('再確認材料：純能力8位以内＋近走同会場好走（✓の追加なし）')
    for h in view:
        for r in h['profile']['runs']:
            if not r['race_id']:continue
            for other in view:
                if h['no']==other['no']:continue
                for o in other['profile']['runs']:
                    if r['race_id']==o['race_id'] and r['date']==o['date'] and r['venue']==o['venue']:
                        h['profile']['matchups'].append(dict(date=r['date'],race_id=r['race_id'],opponent=other['name'],finish=r['finish'],opponent_finish=o['finish'],venue=r['venue'],distance=r['distance']))
    pool=[]
    for h in view:
        reasons=[];p=h['profile']
        for label,k in [('純能力','ability_rank'),('コース','course'),('距離','distance')]:
            rank=number(h.get(k)) if k=='ability_rank' else number((h.get(k) or {}).get('rank'))
            if rank is not None and 1<=rank<=REFERENCE_CONFIG['top_rank']:reasons.append(label+'上位5位')
        if p['stability_sd'] is not None and p['stability_sd']<=REFERENCE_CONFIG['stable_sd']:reasons.append('3走指数のばらつき小（能力水準とは別）')
        if h.get('training')=='A':reasons.append('保存調教A')
        h['reference_facts']=reasons;h['additional_reference']=False
        if h.get('mode')=='jra' and h.get('mark') in ('','—','-') and len(reasons)>=REFERENCE_CONFIG['minimum_reasons']:
            pool.append(h)
    # Fixed exploratory rule; not fitted to observed results. No formal mark written.
    pool.sort(key=lambda h:(-len(h['reference_facts']),number(h.get('ability_rank')) or 999,int(h['no'])))
    for h in pool[:REFERENCE_CONFIG['max_candidates']]:h['additional_reference']=True

def profile_html(h):
    p=h.get('profile') or {};e=lambda v:escape(str(v if v is not None and v!='' else 'データなし'))
    runs=p.get('runs',[]);body='<section class="profile-facts"><h4>過去3走 · 開催日を確認した情報</h4><div class="recent-three">'
    by={r['label']:r for r in runs}
    for label in ('3走前','2走前','前走'):
        r=by.get(label,{})
        body+='<section class="recent-run"><small>'+label+'</small><strong'+(' class="missing-finish"' if not r.get('finish') else '')+'>'+e(r.get('finish'))+'</strong><p>'+e(r.get('date'))+' '+e(r.get('venue'))+'</p><p>'+e(r.get('surface'))+e(r.get('distance'))+'</p><p>'+e(r.get('class_raw'))+'</p><p>タイム指数 '+e(r.get('time_index'))+'</p><small>通過 '+e(r.get('passing_order'))+'</small></section>'
    from .recent_condition_facts import html as condition_html
    body+='</div>'+condition_html(p['condition_facts'])+'<div class="facts"><span>指数推移：<b>'+e(p.get('state','判定不可'))+'</b></span><span>近走安定度 '+('★'*p['stability_stars']+'☆'*(5-p['stability_stars']) if p.get('stability_stars') else '判定不可')+'</span><span>休養 '+e(p.get('rest_days'))+'日</span></div>'
    body+='<p class="help">'+e(p.get('state_reason'))+' 安定度は指数の標準偏差（≤3/5/8/12/それ以上）で5〜1段階。勝率ではありません。</p>'
    body+='<p>今回クラス：'+e(p.get('current_class'))+'／変動：'+e(p.get('class_shift'))+'</p>'
    body+='<p>同級の直近実績：'+e(p.get('same_class_top3'))+'回の3着以内／'+e(p.get('same_class_n'))+'走（直近3走内のみ）</p><p>保存ペース：'+e(p.get('pace'))+'／脚質コース複勝率：'+e(p.get('style_rate'))+'／母数：'+e(p.get('style_n'))+'。母数不明は評価への加点なし。</p>'
    body+='<p>馬体重：'+e(p.get('body_weight'))+'／増減：'+e(p.get('body_weight_change'))+'</p>'
    body+='<details><summary>過去の直接対決（加点なし）</summary>'
    for m in p.get('matchups',[]):body+='<p>'+e(m['date'])+' '+e(m['venue'])+' '+e(m['distance'])+'：'+e(h['name'])+' '+e(m['finish'])+'／'+e(m['opponent'])+' '+e(m['opponent_finish'])+'</p>'
    if not p.get('matchups'):body+='<p>一致する過去レースIDのデータなし</p>'
    body+='</details><p>追加検討根拠：'+e(' / '.join(h.get('reference_facts',[])))+'</p>'
    ev=h.get('candidate_evidence') or {};reasons=ev.get('plus',[])[:2]+ev.get('minus',[])[:1]
    body+='<p><b>総合コメント</b>：'+e('。'.join(reasons) if reasons else '判断材料が不足しています')+'。指数推移は'+e(p.get('state','判定不可'))+'。</p></section>'
    return body

def nar_two_of_three(rows,limit):
    """Comparison only: all unmarked horses, existing priority, no formal changes."""
    from .nar_check_selection import select
    from .nar_top5_order import horse_no
    checked=select(rows);pool=[]
    for h in checked:
        if h.get('pure_ability_top5_group') is not False:continue
        a,c,j=h.get('nar_check_pure_rank'),h.get('nar_check_corner4_rank'),h.get('nar_check_jockey_place_rate')
        if sum((a is not None and 1<=a<=8,c is not None and 1<=c<=6,j is not None and j>=25))>=2:pool.append(h)
    pool.sort(key=lambda h:(h.get('nar_check_pure_rank') or 999,h.get('nar_check_corner4_rank') or 999,-(h.get('nar_check_jockey_place_rate') or 0),int(horse_no(h))))
    return [horse_no(h) for h in pool[:limit]]
