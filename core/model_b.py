"""Independent no-corner model B engine. No production coefficients are invented.

The approved coefficient registry deliberately starts empty until the original
B0-B4 configuration and data provenance can be reproduced.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math

VERSION = 'independent_research_b_v1'
CONFIGS = {}  # mode -> audited configuration; absence must keep model A active.
FEATURES = ('pure','jockey_rate','jockey_n','training','rest_days','weight_delta','venue_top3','distance_top3')
MARKS = ('◎','○','▲','✔','△')

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()

def num(value):
    if isinstance(value,bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def compute(rows, mode, config=None):
    """Only explicit allowlisted, pre-race feature values enter the score/hash."""
    config=deepcopy(config if config is not None else CONFIGS.get(mode))
    inputs=[dict(no=str(h['no']),**{k:h.get(k) for k in FEATURES}) for h in rows]
    report=dict(engine_version=VERSION,mode=mode,input_sha256=digest(inputs),status='unavailable',horses=[],fallback_reason='研究Bの元係数・計算式が未確認',config=config)
    if not config:return report
    if config.get('mode')!=mode or config.get('coefficient_status') not in ('exploratory','validated'):
        raise ValueError('モデル区分・係数の検証状態が不正')
    allowed={'mode','version','coefficient_status','source','jockey_weight','jockey_prior','jockey_strength','training_points','rest_training_points','rest_threshold','weight_delta_weight','venue_points','distance_points'}
    if set(config)-allowed or not config.get('version') or not config.get('source'):raise ValueError('未対応係数または出典不足')
    for k in ('jockey_weight','jockey_prior','jockey_strength','rest_threshold','weight_delta_weight','venue_points','distance_points'):
        if num(config.get(k)) is None:raise ValueError('係数不足: '+k)
    if not 0<=config['jockey_prior']<=1 or config['jockey_strength']<=0 or config['rest_threshold']<0:raise ValueError('縮小補正・休養閾値が不正')
    for k in ('training_points','rest_training_points'):
        if not isinstance(config.get(k),dict) or set(config[k])-set('ABCD') or any(num(v) is None for v in config[k].values()):raise ValueError('調教係数が不正')
    report.update(config_sha256=digest(config),model_version=config['version'],fallback_reason='')
    seen=set()
    for h in inputs:
        if h['no'] in seen:raise ValueError('馬番重複')
        seen.add(h['no']);missing=[];terms={};pure=num(h['pure'])
        if pure is None:missing.append('純能力')
        else:terms['pure']=pure
        if config['jockey_weight']:
            rate,n=num(h['jockey_rate']),num(h['jockey_n'])
            if rate is None or not 0<=rate<=100 or n is None or n<=0 or not n.is_integer():missing.append('騎手複勝率・出走母数')
            else:terms['jockey']=config['jockey_weight']*(n*(rate/100-config['jockey_prior'])/(n+config['jockey_strength']))
        if config['training_points']:
            if h['training'] not in config['training_points']:missing.append('調教')
            else:terms['training']=config['training_points'][h['training']]
        if config['rest_training_points']:
            days=num(h['rest_days'])
            if days is None or days<0 or h['training'] not in config['rest_training_points']:missing.append('休養・調教組合せ')
            else:terms['rest_training']=config['rest_training_points'][h['training']] if days>=config['rest_threshold'] else 0
        if config['weight_delta_weight']:
            v=num(h['weight_delta'])
            if v is None:missing.append('斤量増減')
            else:terms['weight']=v*config['weight_delta_weight']
        # One conditional achievement term prevents the same run being counted twice.
        condition=[]
        for field,key in [('venue_top3','venue_points'),('distance_top3','distance_points')]:
            if config[key]:
                value=h[field]
                if value is not True and value is not False:missing.append(field)
                else:condition.append(config[key] if value else 0)
        if condition:terms['condition']=max(condition)
        report['horses'].append(dict(no=h['no'],score=None if missing else sum(terms.values()),rank=None,mark='',contributions=terms,missing=missing,features=h))
    if not inputs or any(h['missing'] for h in report['horses']):
        report['fallback_reason']='全頭に共通の研究B評価を計算できないためAを表示';report['status']='incomplete';return report
    order=sorted(report['horses'],key=lambda h:(-h['score'],int(h['no'])))
    for i,h in enumerate(order,1):h.update(rank=i,mark=MARKS[i-1] if i<=5 else '')
    report.update(status='ready',top5=[h['no'] for h in order[:5]])
    return report


def features_from_view(view):
    rows=[]
    for h in view:
        p=h.get('profile') or {};conditions=(p.get('condition_facts') or {}).get('conditions',{})
        j=((h.get('candidate_evidence') or {}).get('audit') or {}).get('jockey') or {}
        def placed(key):
            state=(conditions.get(key) or {}).get('state')
            return True if state=='placed' else False if state in ('started','absent') else None
        rows.append(dict(no=h['no'],pure=num(h.get('ability')),jockey_rate=j.get('current_jockey_place_rate'),jockey_n=j.get('current_jockey_sample_size'),training=h.get('training'),rest_days=p.get('rest_days'),weight_delta=h.get('weight_delta'),venue_top3=placed('venue'),distance_top3=placed('distance')))
    return rows
