import copy
import pytest
from core.market_rank_audit import build, digest, metrics, seal, save_once, settlement, verify, evaluate_frozen


def fixture():
    return [dict(horse_no=n,name=str(n),formal_rank=n,pure_rank=7-n,
                 formal_rank_source='saved_table',odds=1+n,pure=50-n,
                 formal_score=52-n,pace_bonus=2,position_bonus=0,
                 repro_bonus=0,training_bonus=0,state_bonus=0) for n in range(1,7)]


def test_independence_and_missing():
    rows=fixture(); original=copy.deepcopy(rows)
    r=build('123','jra',rows,{'discipline':'flat'})
    assert rows==original
    assert r['orders']['pure3_market_fill']==[6,5,4,1,2]
    assert len(r['orders']['position_removed'])==6
    rows[0]['finish']=1;rows[0]['payout']=90000
    assert build('123','jra',rows,{'discipline':'flat'})==r
    rows[0]['odds']=1
    assert 'market' not in build('123','jra',rows,{})['orders']
    rows[0]['formal_rank_source']='not_saved'
    assert 'formal' not in build('123','jra',rows,{})['orders']
    rows=fixture();rows[0]['formal_score']=100
    assert 'position_removed' not in build('123','jra',rows,{'discipline':'flat'})['orders']
    assert 'position_removed' not in build('123','nar',fixture(),{'discipline':'flat'})['orders']


def test_ties_cancellation_and_keys():
    rows=fixture();rows[0]['pure_rank']=rows[1]['pure_rank']=1
    rows[2]['status']='取消'
    r=build('123','nar',rows,{})
    assert r['orders']['pure'][:2]==[1,2]
    assert 3 not in r['orders']['formal']
    rows[1]['horse_no']=1
    with pytest.raises(ValueError):build('123','nar',rows,{})


def test_seal_is_immutable_and_not_timestamp_proof(tmp_path):
    r=seal(build('123','jra',fixture(),{}),'2026-10-16T00:00:00+00:00')
    assert verify(r) and not r['prospective_eligible']
    save_once(r,tmp_path)
    with pytest.raises(FileExistsError):save_once(r,tmp_path)
    r['orders']['formal'].reverse()
    assert not verify(r)


def test_ordered_exacta_missing_winning_payout_and_refunds():
    o=dict(confirmed=True,finishes={'1':1,'2':2,'3':3,'4':4},place_places=2,
           payouts={'win':{'1':200},'place':{'1':110,'2':140},'exacta':{'1-2':500},'wide':{'1-2':120}})
    assert settlement('exacta',[1,2],o)==dict(status='hit',payout=500)
    assert settlement('exacta',[2,1],o)==dict(status='miss',payout=0)
    assert settlement('wide',[1,3],o)['status']=='unknown'
    assert settlement('quinella',[1,2],o)['status']=='unknown'
    assert settlement('place',[3],o)['status']=='miss'
    o['refunds']={'win':['4']}
    assert settlement('win',[4],o)==dict(status='refund',payout=100)
    o['confirmed']=False
    assert settlement('win',[1],o)['status']=='unknown'


def test_metrics_both_outlier_conventions():
    ts=[dict(race_id=str(i),cost=100,payout=p,status='hit' if p else 'miss') for i,p in enumerate([1000,200,0])]
    ts.append(dict(race_id='4',cost=100,payout=None,status='unknown'))
    r=metrics(ts,5)
    assert r['cost']==300 and r['unknown']==1 and r['roi']==400
    assert r['roi_without_1_fixed_stake']==pytest.approx(200/3)
    assert r['roi_without_1_removed_purchase']==100
    assert r['skip_rate']==pytest.approx(.2)


def test_result_join_keeps_prediction_and_checks_race():
    r=seal(build('123','jra',fixture(),{})); original=copy.deepcopy(r)
    out=dict(confirmed=True,finishes={str(n):n for n in range(1,7)})
    assert evaluate_frozen(r,'123',out)['comparisons'][0]['winner_caught']
    assert r==original
    with pytest.raises(ValueError):evaluate_frozen(r,'999',out)
