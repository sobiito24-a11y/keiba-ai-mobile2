"""Evidence-bound prose over frozen independent predictions; never reorders them."""
from copy import deepcopy
from .independent_ai import number,digest

VERSION='independent_commentary_v1_20261012'

def context(result):
    from .race_development import _rows,STYLE_KEYS,PACE_KEYS,style_label
    from .prediction_table_ui import horse_key
    from .jra_rank_display import official_jra_values
    rows=_rows(result);out={};paces=set()
    for r in rows:
        no=horse_key(r)
        if not no:continue
        def first(keys):return next((r[k] for k in keys if r.get(k) is not None and str(r[k]) not in ('','nan','—')),None)
        rank=number(official_jra_values(r)[0]) if result.race_mode=='jra' else number(r.get('nar_final_rank'))
        style=style_label(first(STYLE_KEYS))
        pace=str(first(PACE_KEYS) or '')
        if pace in ('S','M','H'):paces.add(pace)
        out[str(int(no))]=dict(formal_rank=rank,style=style)
    return dict(horses=out,pace=next(iter(paces)) if len(paces)==1 else '不明',source='saved prediction display facts; not model features')

def label(h):return f"{h['horse_no']}番{h['name']}"

def build(prediction,ctx=None):
    ctx=deepcopy(ctx or {});hs=prediction.get('horses',[])
    if not hs:return dict(version=VERSION,paragraphs=['予測入力が不足しているため考察できません。'],checks=[],context=ctx)
    raw={int(h['horse_no']):h for h in (prediction.get('input') or {}).get('horses',[])}
    def evidence(h):
        r=raw.get(h['horse_no'],{});parts=[]
        for key,title in [('pure','純能力'),('distance_index','距離指数'),('course_index','コース指数'),('recent3_mean','近3走平均')]:
            v=number(r.get(key));vs=[number(x.get(key)) for x in raw.values()]
            if v is not None:
                rank=1+sum(x>v for x in vs if x is not None)
                parts.append(f'{title}{v:g}（入力確認範囲で{rank}位）')
        return '、'.join(parts)
    top=hs[0];r=raw.get(top['horse_no'],{});meta=ctx.get('horses',{}).get(str(top['horse_no']),{})
    position=number(r.get('corner4'));pace=ctx.get('pace','不明');style=meta.get('style','不明')
    lines=[f"AIが最も注目するのは{label(top)}。勝利参考確率{top['win']*100:.1f}%、複勝参考確率{top['place']*100:.1f}%。"+
        ('入力は'+evidence(top)+'。' if evidence(top) else '指数の実数は保存されていないため補足しない。')+
        ('独立モデルでは'+ '、'.join(top.get('reasons',[]))+'。' if top.get('reasons') else '')]
    checks=[]
    if position is not None:
        lead=f'普段の脚質は{style}。' if style!='不明' else '普段の脚質は未取得。'
        lines.append(lead+f'今回の想定4角は{position:g}番手、保存ペースは{pace}。勝ち筋の仮説は、想定位置から大きく遅れず、指数面の持ち味を発揮する形。'
            +('H想定でも競り合いの強さは確定しておらず、位置だけで消耗や差し有利を断定しない。' if pace=='H' else '想定ペースだけで前残り・差し切りを断定しない。'))
        lines.append(f'負け筋の仮説は、4角で想定の{position:g}番手より後ろになり、前との差を詰める負担が増す場合。位置取りが合っても勝利を保証するものではない。')
        checks.append(dict(horse_no=top['horse_no'],kind='corner4',expected=position,hypothesis='想定位置より後退せず運ぶ',risk='想定より後方からの競馬'))
    else:lines.append('勝ち筋・負け筋：想定4角が未取得のため位置取りの具体的仮説は保留。指数の優位だけでは実際の運び方は判断できない。')
    if top.get('cautions'):lines.append('モデルが見ている不安材料は'+ '、'.join(top['cautions'])+'。')
    if len(hs)>1:
        rival=hs[1];rr=raw.get(rival['horse_no'],{})
        comparisons=[]
        for key,title in [('pure','純能力'),('distance_index','距離指数'),('course_index','コース指数')]:
            a,b=number(r.get(key)),number(rr.get(key))
            if a is not None and b is not None and a!=b:
                comparisons.append(f'{title}は{top["horse_no"]}番{a:g}に対し{rival["horse_no"]}番{b:g}')
        if comparisons:
            lines.append(f'次点の{label(rival)}との比較では、'+'、'.join(comparisons[:2])+'。'
                +f'勝利参考確率の差は{(top["win"]-rival["win"])*100:.1f}ポイント。これらの指数単独の順位ではなく、モデルの入力全体による評価です。')
    alternatives=[]
    for rank,h in enumerate(hs[:3],1):
        old=number(ctx.get('horses',{}).get(str(h['horse_no']),{}).get('formal_rank'))
        if old is not None and old!=rank:
            alternatives.append(f"{label(h)}は独立AI{rank}番手、従来の正式順位{old:g}位。"+evidence(h)+'。')
    lines.append('従来評価との違い：'+(' '.join(alternatives[:2]) if alternatives else '上位3頭について順位差を確認できないか、確認できる範囲で同順位。'))
    place=max(hs,key=lambda h:(h['place'],-h['horse_no']))
    ticket=f"単勝の参考候補は勝利参考確率が最も高い{label(top)}、複勝は複勝参考確率が最も高い{label(place)}。"
    if prediction.get('wide'):
        pair=prediction['wide'][0];names={h['horse_no']:label(h) for h in hs}
        ticket+='ワイドは'+ '・'.join(names[n] for n in pair['horses'])+f"が組合せ参考確率{pair['probability']*100:.1f}%で最上位。"
    lines.append(ticket+'これは予測上の候補で、価格を踏まえた仮想購入候補とは別。確率は未校正。')
    value=dict(version=VERSION,paragraphs=lines,checks=checks,context=ctx,prediction_version=prediction.get('version'),input_hash=prediction.get('input_hash'),source='frozen independent prediction')
    value['evidence_hash']=digest(dict(horses=hs,input=prediction.get('input'),context=ctx))
    return value

def decision_text(prediction,decision):
    """Price-dependent text kept in the decision, never rewrite the saved prediction prose."""
    texts=[decision['reason']];hs=prediction.get('horses',[]);ranks={h['horse_no']:i+1 for i,h in enumerate(hs)}
    wins={r['horses'][0]:r for r in decision.get('price_evaluations',[]) if r['kind']=='win'}
    # Require whole-field valid win prices before claiming a market rank.
    if hs and set(wins)==set(ranks):
        market=sorted(wins,key=lambda n:(wins[n]['odds_low'],n));n=market[0]
        if ranks[n]>1:
            h=next(h for h in hs if h['horse_no']==n)
            texts.append(f"有効な取得単勝価格で最も低い{label(h)}は、独立AIでは{ranks[n]}番手。市場と予測の順序が異なるが、過大評価と断定はできない。")
    for t in decision.get('candidates',[]):
        texts.append(f"{t['kind']} {'・'.join(map(str,t['horses']))}は、価格下限{t['odds_low']:g}倍×モデル間確率下限{t['probability_lower']*100:.1f}%で参考払戻倍率{t['conservative_gross_return']:.2f}。余裕条件を通過した試験候補で、損失を避けられる保証はない。")
    return texts

def review(commentary,outcome):
    rows=[]
    for c in (commentary or {}).get('checks',[]):
        actual=number((outcome.get('actual_corner4') or {}).get(str(c['horse_no'])))
        if actual is not None and (actual<1 or actual!=int(actual)):actual=None
        rows.append(dict(horse_no=c['horse_no'],hypothesis=c['hypothesis'],risk=c['risk'],expected=c['expected'],actual=actual,
            finding='実4角未取得のため検証不能' if actual is None else '想定より後方になった' if actual>c['expected'] else '想定位置より後退せず運んだ',
            finish=(outcome.get('finishes') or {}).get(str(c['horse_no'])),note='位置仮説の照合であり、勝敗の原因が証明されたわけではない'))
    return dict(saved_commentary=deepcopy(commentary),observations=rows,unverified='適性・調教・消耗が勝敗へ及ぼした因果は着順だけでは検証できない')
