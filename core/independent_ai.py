"""Independent experimental inference. No imports of formal rank/mark producers."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone, timedelta
from itertools import combinations
import hashlib
import json
import math
import re
import numpy as np

KEY = 'independent_ai_v3'
VERSION = 'independent_ai_v3_20261012_beta1'
JST = timezone(timedelta(hours=9))
FIELDS = ('ability', 'fit_residual', 'form_residual', 'corner', 'jockey', 'training', 'rest', 'load_change')
LABELS = dict(ability='全頭内の能力差', fit_residual='能力水準に対する距離・コース適性',
              form_residual='能力水準に対する近況', corner='今回の4角想定', jockey='騎手実績（母数考慮）',
              training='調教評価', rest='休養間隔', load_change='斤量変化')

def number(x):
    try:
        n=float(x)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):return None

def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def features(horses):
    """Within-race contrasts, not the saved rank/mark/market probability."""
    n=len(horses)
    def z(key):
        vals=[number(h.get(key)) for h in horses];present=[x for x in vals if x is not None]
        if not present:return [None]*n
        mean=float(np.mean(present));sd=max(float(np.std(present)),1.)
        return [max(-3.,min(3.,(v-mean)/sd)) if v is not None else None for v in vals]
    ability=z('pure');dist=z('distance_index');course=z('course_index');recent=z('recent3_mean')
    rows=[]
    for i,h in enumerate(horses):
        fits=[v for v in (dist[i],course[i]) if v is not None]
        rank=number(h.get('corner4'));rate=number(h.get('jockey_place_rate'));runs=number(h.get('jockey_sample_size'))
        days=number(h.get('rest_days'));change=number(h.get('load_change'))
        rows.append(dict(ability=ability[i],fit_residual=float(np.mean(fits))-ability[i] if fits and ability[i] is not None else None,
            form_residual=recent[i]-ability[i] if recent[i] is not None and ability[i] is not None else None,
            corner=1-(rank-1)/max(n-1,1) if rank is not None and 1<=rank<=n else None,
            jockey=(rate/100*runs+.25*20)/(runs+20) if rate is not None and 0<=rate<=100 and runs is not None and runs>=0 else None,
            training={'A':1.,'B':.5,'C':0.,'D':-.5}.get(str(h.get('training','')).strip()) if h.get('mode')!='nar' else None,
            rest=math.log1p(days) if days is not None and 0<=days<=2000 else None,
            load_change=change if change is not None and abs(change)<=15 else None))
    return rows

def matrix(rows, model):
    a=np.array([[r.get(k) for k in model['fields']] for r in rows],dtype=float)
    miss=~np.isfinite(a);med=np.array(model['median']);scale=np.array(model['scale'])
    return np.column_stack([np.clip((np.where(miss,med,a)-med)/scale,-4,4),miss.astype(float),np.ones(len(a))])

def probabilities(rows, model):
    z=matrix(rows,model)@np.array(model['weights'])
    if model['target']=='place':return 1/(1+np.exp(-np.clip(z,-25,25)))
    p=np.exp(z-z.max());return p/p.sum()

def joint_top3(p):
    """Plackett-Luce approximation; NOT product of individual place probabilities."""
    n=len(p);out={pair:0. for pair in combinations(range(n),2)}
    if n<3:return {}
    for i in range(n):
        for j in range(n):
            if i==j:continue
            d1=1-p[i];d2=1-p[i]-p[j]
            if d1<=1e-12 or d2<=1e-12:continue
            for k in range(n):
                if k in (i,j):continue
                v=float(p[i]*p[j]/d1*p[k]/d2)
                for a,b in ((i,j),(i,k),(j,k)):out[tuple(sorted((a,b)))]+=v
    return out

@lru_cache(maxsize=1)
def artifact():
    return json.loads(Path(__file__).with_name('independent_ai_model.json').read_text(encoding='utf-8'))

def predict(packet, bundle=None):
    """Returns new data; caller inputs, formal predictions and stored odds are untouched."""
    bundle=bundle or artifact();mode=packet.get('mode')
    if mode not in ('jra','nar'):raise ValueError('Unknown race mode')
    hs=sorted([dict(h,mode=mode) for h in packet.get('horses',[]) if not h.get('known_withdrawn')],key=lambda h:int(h['horse_no']))
    if len({int(h['horse_no']) for h in hs})!=len(hs):raise ValueError('Duplicate horse number')
    base=dict(version=VERSION,model_id=bundle['model_id'],model_hash=digest(bundle),race_id=packet.get('race_id'),
        mode=mode,input_hash=digest(packet),calibration_status='未校正・参考確率（過去の時系列検証のみ）',
        profit_validated=False,confidence='低・未来検証待ち',horses=[],wide=[],historical_only=True)
    if len(hs)<3:return dict(base,status='insufficient',reason='出走馬情報が不足')
    fs=features(hs);b=bundle['models'][mode]
    if sum(f['ability'] is not None for f in fs)<len(hs)*.5:
        return dict(base,status='insufficient',reason='能力入力の欠損が多く確率を表示できません')
    wm=b['win'];pm=b['place'];wp=probabilities(fs,wm);pp=probabilities(fs,pm)
    we=[wp]+[probabilities(fs,m) for m in b.get('win_ensemble',[])];pe=[pp]+[probabilities(fs,m) for m in b.get('place_ensemble',[])]
    joint=[joint_top3(p) for p in we];x=matrix(fs,wm);w=np.array(wm['weights'])
    for i,h in enumerate(hs):
        contributions=[(k,float(x[i,j]*w[j])) for j,k in enumerate(wm['fields']) if fs[i].get(k) is not None]
        positive=sorted([a for a in contributions if a[1]>0],key=lambda a:-a[1])[:2]
        negative=sorted([a for a in contributions if a[1]<0],key=lambda a:a[1])[:2]
        missing=[LABELS[k] for k in wm['fields'] if fs[i].get(k) is None]
        base['horses'].append(dict(horse_no=int(h['horse_no']),name=str(h.get('name','')),win=float(wp[i]),place=float(pp[i]),
            win_range=[float(min(p[i] for p in we)),float(max(p[i] for p in we))],
            place_range=[float(min(p[i] for p in pe)),float(max(p[i] for p in pe))],
            reasons=[LABELS[k]+'がモデル内でプラス方向' for k,v in positive],
            cautions=[LABELS[k]+'がモデル内でマイナス方向' for k,v in negative]+(['未取得：'+'・'.join(missing)] if missing else []),
            contributions={k:v for k,v in contributions},missing=missing))
    for pair,p in joint[0].items():
        base['wide'].append(dict(horses=[int(hs[i]['horse_no']) for i in pair],probability=p,
            range=[min(j[pair] for j in joint),max(j[pair] for j in joint)]))
    base['wide'].sort(key=lambda p:(-p['probability'],p['horses']))
    base['horses'].sort(key=lambda h:(-h['win'],h['horse_no']))
    base.update(status='reference',uncertainty_definition='学習日を除外したモデル間の範囲。統計的信頼区間ではありません',
        wide_definition='両馬が3着以内の組合せ近似。複勝払戻対象確率の積ではありません',
        calibration=bundle.get('validation',{}).get(mode,{}))
    return base

def from_result(result):
    """Allowlist adapter; no result, payout, odds, formal rank or mark inputs."""
    from .prediction_table_ui import horse_key
    from .position_signals import corner4_rank
    rows={}
    for table in (result.overall_table,result.horse_evaluation):
        if table is not None:
            for row in table.to_dict('records'):
                no=horse_key(row)
                if no and no.isdigit():rows.setdefault(int(no),{}).update({k:v for k,v in row.items() if v is not None and str(v) not in ('nan','','—')})
    def val(row,*keys):
        return next((row[k] for k in keys if row.get(k) is not None and str(row[k]) not in ('nan','','—')),None)
    hs=[]
    for no,h in sorted(rows.items()):
        hs.append(dict(horse_no=no,name=str(val(h,'馬名','name','horse_name') or ''),
            pure=number(val(h,'ver3_ability_core','_ver3_ability_core','jra_pure_ability_score')),
            distance_index=number(val(h,'距離指数','distance_index')),course_index=number(val(h,'コース指数','course_index')),
            recent3_mean=number(val(h,'平均指数','recent3_mean')),corner4=number(corner4_rank(h)),
            jockey_place_rate=number(val(h,'_jockey_course_place_rate','jockey_course_top3_rate','current_jockey_place_rate')),
            jockey_sample_size=number(val(h,'_jockey_course_starts','jockey_course_runs','current_jockey_sample_size')),
            training=(re.match(r'^\s*([ABCD])(?:\s|$)',str(val(h,'training_market','調教評価','training_grade') or '')) or [None,''])[1] if result.race_mode=='jra' else '',
            rest_days=number(val(h,'_days_since_last','rest_days')),load_change=number(val(h,'_load_weight_change','weight_change_market','load_change')),
            known_withdrawn=str(val(h,'出走状態','status','取消区分') or '') in ('取消','除外')))
    info=result.race_info or {}
    from .prediction_history import _race_info
    identity=_race_info(result)
    post=info.get('post_time') or info.get('scheduled_post_time')
    day=info.get('race_date') or info.get('date')
    clock=re.search(r'(\d{1,2}:\d{2})\s*発走',str(info.get('race_data','')))
    if not post and day and clock:
        try:post=datetime.fromisoformat(str(day).replace('/','-')+'T'+clock[1].zfill(5)).replace(tzinfo=JST).isoformat()
        except ValueError:pass
    if post:
        try:
            dt=datetime.fromisoformat(str(post));post=(dt if dt.tzinfo else dt.replace(tzinfo=JST)).isoformat()
        except ValueError:post=None
    return dict(race_id=str(identity.get('race_id','')),mode=result.race_mode,horses=hs,
        prediction_created_at=str(result.created_at),post_time=post)

def resolve(result):
    saved=(result.debug_info or {}).get(KEY)
    if isinstance(saved,dict) and saved.get('version'):return deepcopy(saved)
    packet=from_result(result)
    value=predict(packet)
    value['generated_at']=datetime.now(JST).isoformat()
    value['input']=packet
    restored=any(getattr(result,k,False) for k in ('_material_snapshot_restored','_jra_snapshot_restored','_race_insight_restored'))
    value['origin']='current_reference' if restored else 'new_prediction'
    return value

def attach(result):
    if KEY not in (result.debug_info or {}):
        try:value=resolve(result)
        except Exception:
            value=dict(version=VERSION,status='unavailable',reason='独立AIを生成できませんでした。既存予想は利用できます。',horses=[],wide=[])
        result.debug_info={**(result.debug_info or {}),KEY:value}
    return result

def saved_fields(result):
    value=(result.debug_info or {}).get(KEY)
    return {KEY:deepcopy(value)} if isinstance(value,dict) else {}

def restore(result,payload):
    odds=payload.get("independent_ai_odds_history")
    if isinstance(odds,list):result.debug_info={**(result.debug_info or {}),"independent_ai_odds_history":deepcopy(odds)}
    value=payload.get(KEY) or (payload.get('mobile_snapshot') or {}).get(KEY)
    if KEY not in (result.debug_info or {}) and isinstance(value,dict):
        result.debug_info={**(result.debug_info or {}),KEY:deepcopy(value)}
