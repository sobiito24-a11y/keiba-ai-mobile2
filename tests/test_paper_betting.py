from copy import deepcopy
import pytest
from core import paper_betting as p

def horses():
 return [dict(no=str(n),name=f'馬{n}',mark='◎' if n==1 else '○',rank=str(n),ability_rank=str(n),formal_member=True,odds=str(2 if n==1 else 10+n),mode='nar',candidate_evidence=dict(plus=['能力上位'],minus=[],audit={})) for n in range(1,7)]
def test_independent_and_bounded():
 h=horses();before=deepcopy(h)
 d=p.build(h,'nar',dict(race_id='123456789012'))
 assert h==before and len(d['strong'])<=2 and len(d['value'])<=2
 assert set(t['kind'] for t in d['tickets'])==set(p.KINDS)
 assert all(t['status'] in ('要確認','見送り') for t in d['tickets'])
def test_incomplete_odds_no_market_value():
 h=horses();h[-1]['odds']='—'
 assert not p.legacy_value(h)
def test_settlement_refund_unknown_and_tampering():
 d=p.build(horses(),'nar',dict(race_id='123456789012'));r=p.freeze(d,True);before=deepcopy(r)
 t=next(t for t in r['tickets'] if t['choices'])
 c=t['choices'][0]
 out=p.settle(r,dict(race_id=r['race_id'],tickets=[dict(kind=t['kind'],horses=c['horses'],status='refund')]))
 assert out['returns']==100 and out['cost']==100 and out['unknown']>0 and r==before
 with pytest.raises(ValueError):p.settle(r,dict(race_id='wrong'))
 bad=deepcopy(r);bad['mode']='jra'
 with pytest.raises(ValueError):p.verify(bad)
def test_no_evidence_is_skip():
 h=horses()
 for x in h:x['candidate_evidence']={}
 assert all(t['status']=='見送り' for t in p.build(h,'nar',dict(race_id='123456789012'))['tickets'])


def test_known_monbetsu_result_and_immutable_record():
    h=horses();d=p.build(h,'nar',dict(race_id='202630101503'))
    d['tickets']=[dict(kind=k,choices=[dict(horses=ns,stake=100)]) for k,ns in [('win',[11]),('place',[7]),('wide',[7,11]),('quinella',[7,11])]]
    record=p.freeze(d,False);before=deepcopy(record)
    result=dict(race_id=record['race_id'],source='keiba.go.jp 2026-10-15 門別3R：既知結果動作試験',tickets=[
        dict(kind='win',horses=[11],status='hit',payout_per_100=170),
        dict(kind='place',horses=[7],status='hit',payout_per_100=190),
        dict(kind='wide',horses=[7,11],status='hit',payout_per_100=170),
        dict(kind='quinella',horses=[7,11],status='miss',payout_per_100=0)])
    out=p.settle(record,result)
    assert out['returns']==530 and out['cost']==400 and out['roi']==132.5
    assert record==before
    d['odds']={'updated':True}
    assert record==before and p.verify(record)==record
