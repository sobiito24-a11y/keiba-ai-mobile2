"""Portable price history; prediction and original archives are never rewritten in place."""
import copy,csv,io,json,hashlib,zipfile
from datetime import datetime
from .independent_ai import JST,digest,number
from .independent_ai_html_odds import norm,parse

KEY='independent_ai_odds_history'
KINDS=('win','place','wide')

def validate(quote,prediction):
    q=copy.deepcopy(quote)
    if not isinstance(q,dict) or q.get('race_id')!=prediction['race_id'] or q.get('mode')!=prediction['mode']:
        raise ValueError('オッズと予想のレースID・区分が一致しません')
    expected={str(h['horse_no']):norm(h['name']) for h in prediction['horses']}
    identities=q.get('identities',{})
    if not isinstance(identities,dict):raise ValueError('馬名一覧が不正です')
    for no,name in identities.items():
        if no not in expected or norm(name)!=expected[no]:raise ValueError('馬番・馬名が予想と一致しません')
    clean=[];seen={}
    if not isinstance(q.get('prices',[]),list):raise ValueError('価格一覧の形式が不正です')
    for p in q.get('prices',[]):
        if not isinstance(p,dict):raise ValueError('価格行の形式が不正です')
        kind=p.get('kind');ns=p.get('horses',[])
        if kind not in KINDS or not isinstance(ns,list) or not all(type(n) is int for n in ns):raise ValueError('券種・馬番形式が不正です')
        ns=sorted(ns)
        if len(ns)!=(2 if kind=='wide' else 1) or len(ns)!=len(set(ns)):raise ValueError('組合せが不正です')
        if any(str(n) not in identities for n in ns):raise ValueError('価格の馬名照合情報がありません')
        lo=number(p.get('low'));hi=number(p.get('high'))
        if lo is None or hi is None or not 1<=lo<=hi:raise ValueError('有効な価格上下限がありません')
        key=(kind,tuple(ns));value=(lo,hi)
        if key in seen and seen[key]!=value:raise ValueError('同一組合せの価格が競合しています')
        if key not in seen:clean.append(dict(kind=kind,horses=ns,low=lo,high=hi))
        seen[key]=value
    withdrawn=q.get('withdrawn',[])
    if not isinstance(withdrawn,list) or any(str(n) not in expected for n in withdrawn):raise ValueError('取消馬の対応が不正です')
    q['prices']=[p for p in clean if not set(p['horses']).intersection(withdrawn)]
    active=len(expected)-len(set(withdrawn));counts={k:sum(p['kind']==k for p in q['prices']) for k in KINDS}
    expected_counts={'win':active,'place':active,'wide':active*(active-1)//2}
    q['coverage']={k:dict(count=counts[k],expected=expected_counts[k],complete=bool(expected_counts[k] and counts[k]==expected_counts[k])) for k in KINDS}
    q['missing_kinds']=[k for k in KINDS if counts[k]==0]
    q.setdefault('price_status','timestamp_unknown' if not q.get('observed_at') else 'saved_observation')
    q['schema_version']=1
    return q

def merge(history,incoming,prediction):
    out=[];seen=set()
    for raw in [*history,*incoming]:
        q=validate(raw,prediction)
        # Reimporting the same observation must not refresh its age or duplicate it.
        key=digest({k:v for k,v in q.items() if k not in ('received_at','user_reported_captured_at','input_sha256')})
        if key not in seen:out.append(q);seen.add(key)
    return out

def import_file(raw,filename,prediction,now=None):
    if len(raw)>12_000_000:raise ValueError('入力サイズが大きすぎます')
    now=now or datetime.now(JST)
    if filename.lower().endswith(('.html','.htm')):return [validate(parse(raw,prediction,now=now),prediction)]
    try:
        payload=json.loads(raw.decode('utf-8-sig'))
        quotes=payload.get('odds_history') if isinstance(payload,dict) else None
        if quotes is None:quotes=[payload]
        if not isinstance(quotes,list):raise ValueError('価格履歴の形式が不正です')
        out=[]
        for q in quotes:
            q=validate(q,prediction)
            q.setdefault('received_at',now.isoformat())
            q.setdefault('input_sha256',hashlib.sha256(raw).hexdigest())
            q.setdefault('price_status','timestamp_unknown' if not q.get('observed_at') else 'saved_observation')
            out.append(q)
        return out
    except (UnicodeError,TypeError,KeyError,json.JSONDecodeError) as exc:raise ValueError('対応するオッズJSONではありません') from exc

def read_archive(raw):
    if len(raw)>200_000_000:raise ValueError('保存ファイルが大きすぎます')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sorted(z.namelist())!=['manifest.json','snapshot.json']:raise ValueError('未対応の.keiba構造です')
            if any(x.file_size>200_000_000 for x in z.infolist()):raise ValueError('展開サイズが大きすぎます')
            body=z.read('snapshot.json');manifest=json.loads(z.read('manifest.json'))
        if hashlib.sha256(body).hexdigest()!=manifest.get('snapshot_sha256'):raise ValueError('保存ファイルのハッシュ不一致')
        event=json.loads(body)
        if not isinstance(event.get('races'),list):raise ValueError('レース一覧がありません')
        return manifest,event
    except (zipfile.BadZipFile,KeyError,TypeError,json.JSONDecodeError) as exc:raise ValueError('保存ファイルを読み込めません') from exc

def attach_archive(raw,prediction,history):
    manifest,event=read_archive(raw)
    matches=[r for r in event['races'] if str(r.get('race_id'))==prediction['race_id']]
    if len(matches)!=1:raise ValueError('保存ファイル内の対象レースを一意に確認できません')
    r=matches[0]
    if r.get('race_mode')!=prediction['mode']:raise ValueError('保存レース区分が一致しません')
    # Validate identities against the archive, not just the currently displayed race.
    saved=restore_race(r)
    from .independent_ai import from_result
    packet=from_result(saved)
    packet['race_id']=str(r['race_id'])
    r[KEY]=merge(r.get(KEY,[]),history,packet)
    body=json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    manifest['snapshot_sha256']=hashlib.sha256(body).hexdigest()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('snapshot.json',body);z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
    return out.getvalue()

def restore_race(race):
    from dataclasses import fields
    import pandas as pd
    from .models import PredictionResult
    data=copy.deepcopy(race.get('prediction_result') or {})
    if not data or race.get('race_mode') not in ('jra','nar'):raise ValueError('保存予想がありません')
    data['race_mode']=race['race_mode']
    for key in ('overall_table','horse_evaluation'):
        table=data.get(key) or {}
        data[key]=pd.DataFrame(table.get('records',[]),columns=table.get('columns')) if isinstance(table,dict) else pd.DataFrame(table)
    result=PredictionResult(**{k:v for k,v in data.items() if k in {f.name for f in fields(PredictionResult)}})
    result._material_snapshot_restored=True
    if result.race_mode=='jra':result._jra_snapshot_restored=True
    result.debug_info[KEY]=copy.deepcopy(race.get(KEY,[]))
    from .race_odds import restore
    return restore(result, race)
