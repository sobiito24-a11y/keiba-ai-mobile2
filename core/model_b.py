"""Frozen, outcome-free research B inference. Training lives in an offline tool."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import math
from .model_b_features import transform, extract, RAW_FIELDS, TRANSFORM_VERSION, finite

VERSION='research_b_frozen_20261021_v1'
KEY='model_b_prediction'
MARKS=('◎','○','▲','✔','△')
MODEL_PATH=Path(__file__).with_name('model_b_frozen.json')

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()

def load_artifact():
    if not MODEL_PATH.exists():return None
    value=json.loads(MODEL_PATH.read_text(encoding='utf-8-sig'))
    content={k:v for k,v in value.items() if k!='artifact_sha256'}
    if digest(content)!=value.get('artifact_sha256') or value.get('transform_version')!=TRANSFORM_VERSION:
        raise ValueError('研究Bモデルのハッシュ・特徴量版が一致しません')
    return value

def predict(rows,mode,artifact=None,method='SELECTED'):
    """Raw-score logistic margin, not a calibrated win probability."""
    artifact=artifact if artifact is not None else load_artifact()
    inputs=[{k:h.get(k) for k in RAW_FIELDS} for h in rows]
    inputs.sort(key=lambda h:int(h['no']))
    report=dict(engine_version=VERSION,mode=mode,method=method,input_sha256=digest(inputs),horses=[],status='unavailable',fallback_reason='研究Bの凍結モデル未取得')
    if not artifact:return report
    model=artifact['models'][mode.upper()][method]
    report.update(model_version=model['version'],config_sha256=artifact['artifact_sha256'],config=deepcopy(model),train_end=artifact['train_end'])
    if len({h['no'] for h in inputs})!=len(inputs):raise ValueError('研究Bの馬番が重複')
    try: transformed=transform(inputs)
    except ValueError as e:report.update(status='incomplete',fallback_reason=str(e));return report
    cols=model['features'];weights=model['coefficients']
    if len(cols)!=len(weights) or not all(math.isfinite(float(v)) for v in weights+[model['intercept']]):raise ValueError('研究B係数が不正')
    for raw,h in zip(inputs,transformed):
        terms={k:float(w)*h['features'][k] for k,w in zip(cols,weights)}
        score=float(model['intercept'])+sum(terms.values())
        report['horses'].append(dict(no=h['no'],score=score,rank=None,mark='',contributions=terms,intercept=model['intercept'],features=h['features'],raw_features=raw,missing=h['missing']))
    # Neutral imputation follows source research. All supplementary evidence absent
    # for a runner is a major input failure, rather than an invented last-place score.
    unavailable=[]
    if method=='SELECTED':
        for h in inputs:
            p,n=finite(h.get('jockey_p')),finite(h.get('jockey_n'))
            valid_jockey=p is not None and 0<=p<=100 and n is not None and n>=0 and n.is_integer()
            if mode.lower()=='nar':
                known=valid_jockey or h.get('venue_good') is not None
            else:known=valid_jockey or h.get('gr') in ('A','B','C','D') or h.get('daygap') is not None or h.get('weightdiff') is not None
            if not known:unavailable.append(h['no'])
    if unavailable:
        report.update(status='incomplete',fallback_reason='補助材料が全て未取得の馬：'+','.join(map(str,unavailable)));return report
    order=sorted(report['horses'],key=lambda h:(-h['score'],int(h['no'])))
    for rank,h in enumerate(order,1):h.update(rank=rank,mark=MARKS[rank-1] if rank<=5 else '')
    report.update(status='ready',fallback_reason='',top5=[h['no'] for h in order[:5]],missing_policy='補助特徴の欠損は研究原式の中立変換。欠損状態を別記。純能力欠損・重大欠損はレース全体をAへ復帰')
    return report

def resolve(result):
    saved=(result.debug_info or {}).get(KEY)
    if isinstance(saved,dict):
        content={k:v for k,v in saved.items() if k!='prediction_sha256'}
        if digest(content)!=saved.get('prediction_sha256'):
            return dict(status='unavailable',fallback_reason='保存研究Bの整合性エラー',horses=[])
        if saved.get('race_id') and saved['race_id']!=str((result.race_info or {}).get('race_id','')):
            return dict(status='unavailable',fallback_reason='保存BのレースIDが一致しません',horses=[])
        try:
            current=sorted(({k:h.get(k) for k in RAW_FIELDS} for h in extract(result)),key=lambda h:int(h['no']))
        except (ValueError,KeyError,TypeError):
            return dict(status='unavailable',fallback_reason='固定保存Bの入力を照合できません',horses=[])
        if digest(current)!=saved.get('input_sha256'):
            return dict(status='unavailable',fallback_reason='固定保存後に入力が変化しています。保存Bを上書きせずAを表示します',horses=[])
        return deepcopy(saved)
    try:
        raw=extract(result)
        report=predict(raw,result.race_mode)
        report['evidence']={h['no']:h.get('evidence',{}) for h in raw}
    except (ValueError,KeyError,TypeError,OSError) as e:
        report=dict(status='unavailable',fallback_reason='研究Bを計算できません：'+str(e),horses=[])
    report['historical_recalculation']=any(getattr(result,k,False) for k in ('_jra_snapshot_restored','_material_snapshot_restored','_race_insight_restored'))
    info=result.race_info or {}
    race_day=str(info.get('race_date') or info.get('date') or '').replace('/','-')[:10]
    report['default_allowed']=report.get('status')=='ready' and not report['historical_recalculation'] and len(race_day)==10 and race_day>str(report.get('train_end','9999'))
    return report

def freeze(result):
    saved=(result.debug_info or {}).get(KEY)
    if isinstance(saved,dict):return deepcopy(saved)
    report=resolve(result)
    report.update(race_id=str((result.race_info or {}).get('race_id','')),race_date=(result.race_info or {}).get('race_date'),saved_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),timing_status='取得時点の証明は未確認。保存時刻だけでは発走前性を証明しない')
    report['prediction_sha256']=digest(report)
    return report
