"""Immutable prospective record and separate official settlement; no model calls."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
from .independent_ai import digest,JST
from .independent_ai_odds import timestamp

def freeze(prediction,decision,now=None):
    now=now or datetime.now(JST)
    post=timestamp((prediction.get('input') or {}).get('post_time'))
    generated=timestamp(prediction.get('generated_at'))
    if not post or not generated or not generated<=now<post:raise ValueError('発走前の時刻を確認できません')
    if post.astimezone(JST).date().isoformat()<='2026-10-12':raise ValueError('10/12以前はV3未使用検証へ登録できません')
    if prediction.get('origin')!='new_prediction' or prediction.get('status')!='reference':raise ValueError('保存後の参考再生成は事前予測へ登録できません')
    if not prediction.get('race_id') or prediction.get('input_hash')!=digest(prediction.get('input')):raise ValueError('予測入力ハッシュ不一致')
    if decision.get('prediction_hash')!=digest(prediction):raise ValueError('価格判断と予測が一致しません')
    evaluated=timestamp(decision.get('evaluated_at'))
    if not evaluated or not generated<=evaluated<=now:raise ValueError('判断時刻不一致')
    record=dict(schema_version=1,registered_at=now.isoformat(),prediction=deepcopy(prediction),decision=deepcopy(decision),
        prospective=True,clock_attestation='application clock; not a third-party timestamp',actual_purchase=False)
    record['record_hash']=digest(record)
    return record

def immutable(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('固定済みデータの上書きは禁止です')
        return
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)

def register(root,record):
    verify(record)
    rid=record['prediction']['race_id']
    if not str(rid).isdigit():raise ValueError('レースIDが不正です')
    path=Path(root)/'predictions'/f'{rid}.json';immutable(path,record);return path

def verify(record):
    if record.get('record_hash')!=digest({k:v for k,v in record.items() if k!='record_hash'}):raise ValueError('固定記録のハッシュ不一致')
    restored=freeze(record['prediction'],record['decision'],timestamp(record['registered_at']))
    if restored!=record:raise ValueError('固定記録不一致')

def settle(record,outcome):
    verify(record);pred=record['prediction'];rid=pred['race_id']
    if outcome.get('race_id')!=rid or outcome.get('confirmed') is not True or not outcome.get('source'):raise ValueError('公式結果の同一性と出典を確認してください')
    if outcome.get('special_settlement'):raise ValueError('特殊払戻は確認保留')
    statuses=outcome.get('statuses',{});pay=outcome.get('payouts',{});rows=[]
    for ticket in record['decision'].get('candidates',[]):
        ns=ticket['horses'];kind=ticket['kind'];stake=ticket['virtual_stake_yen']
        if any(str(n) not in statuses for n in ns) or not pay.get(kind):raise ValueError('決済情報不足。0円として処理しません')
        refund=any(statuses[str(n)] in ('取消','除外') for n in ns)
        key='-'.join(map(str,sorted(ns)));amount=stake if refund else pay[kind].get(key,0)*stake/100
        rows.append(dict(kind=kind,horses=ns,stake=stake,payout=amount,refund=refund))
    valid=[r for r in rows if not r['refund']];stake=sum(r['stake'] for r in valid);payout=sum(r['payout'] for r in valid)
    probability_results=[]
    for h in pred['horses']:
        no=str(h['horse_no']);rank=outcome.get('finishes',{}).get(no)
        if isinstance(rank,int):probability_results.append(dict(horse_no=h['horse_no'],win_probability=h['win'],place_probability=h['place'],won=rank==1,
            paid_place=no in pay['place'] if pay.get('place') else None))
    return dict(race_id=rid,record_hash=record['record_hash'],outcome=deepcopy(outcome),tickets=rows,
        stake=stake,payout=payout,profit=payout-stake,roi=payout/stake if stake else None,
        probability_results=probability_results,unused_for_next_model=False,actual_purchase=False)

def settle_saved(root,race_id,outcome):
    if not str(race_id).isdigit():raise ValueError('レースIDが不正です')
    record=json.loads((Path(root)/'predictions'/f'{race_id}.json').read_text(encoding='utf-8'))
    value=settle(record,outcome);path=Path(root)/'results'/f'{race_id}.json';immutable(path,value);return value
