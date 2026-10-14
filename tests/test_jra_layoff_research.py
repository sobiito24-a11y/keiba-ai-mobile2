import copy
from datetime import date,timedelta
import pandas as pd
import pytest
from core.jra_layoff_research import rest_evidence,evaluate_candidate,VERSION
from core.models import PredictionResult
from core.jra_formal_snapshot import freeze_fresh_formal,saved_formal_comparison


def sample(days=180,grade='B'):
    day=date(2026,10,14)
    raw=[dict(number=str(i),name=f'馬{i}',market_ability_score=110-i*6,market_ability_rank=i,
              training_grade=grade if i==1 else 'B',_days_since_last=days if i==1 else 21,
              _past_runs=[] if days is None and i==1 else [dict(race_date=(day-timedelta(days=days if i==1 else 21)).isoformat(),position='1')]) for i in range(1,7)]
    return PredictionResult(race_mode='jra',race_info={'race_date':str(day),'surface':'芝','race_id':'202608040511'},horse_evaluation=pd.DataFrame(raw),overall_table=pd.DataFrame(raw))


@pytest.mark.parametrize('days,grade,bonus,mark',[(179,'B',0,'◎'),(180,'A',-2,'○'),(181,'B',-2,'○'),(180,'',-2,'○'),(180,'C',-2,'△'),(180,'D',-2,'△'),(70,'C',0,'△'),(69,'D',0,'◎'),(None,'B',0,'◎')])
def test_boundaries_roles_and_score_rank_are_separate(days,grade,bonus,mark):
    r=sample(days,grade);before=r.overall_table.copy(deep=True)
    freeze_fresh_formal(r,position_scoring=False)
    saved=copy.deepcopy(r.debug_info);formal=saved_formal_comparison(r)
    s=evaluate_candidate(r,formal);h=next(h for h in s['rows'] if h['number']=='1')
    assert s['candidate_version']==VERSION and not s['adopted']
    assert h['jra_layoff_bonus']==bonus and h['research_final_mark']==mark
    assert h['jra_top5_rank']==1
    assert sum(h['research_final_mark']=='◎' for h in s['rows'])==1
    assert h['jra_top5_score']==pytest.approx(h['jra_pure_ability_score']+h['jra_repro_bonus']+h['jra_training_bonus']+bonus)
    assert h['jra_position_bonus']==h['jra_pace_bonus']==0
    pd.testing.assert_frame_equal(before,r.overall_table)
    assert r.debug_info==saved
    assert evaluate_candidate(r,formal)==s
    assert formal==saved_formal_comparison(r)


def test_all_candidates_long_rest_no_forced_honmei():
    r=sample()
    r.overall_table['_past_runs']=[[dict(race_date='2026-01-01',position='2')]]*6
    r.overall_table['_days_since_last']=286
    freeze_fresh_formal(r,position_scoring=False)
    assert not any(h['research_final_mark']=='◎' for h in evaluate_candidate(r,saved_formal_comparison(r))['rows'])


def test_cancelled_starts_conflicts_unknown_and_overseas():
    info={'race_date':'2026-10-14'}
    h={'_past_runs':[{'race_date':'2026-09-01','position':'取消'},{'race_date':'2026-04-17','position':'3','racecourse':'海外'}]}
    assert rest_evidence(h,info)['days']==180
    h['_past_runs'].append({'race_date':'2026-10-01','position':''})
    assert rest_evidence(h,info)['days'] is None
    h['_past_runs'].pop();h['_days_since_last']=20
    assert rest_evidence(h,info)['status']=='conflict'
    assert rest_evidence({'_days_since_last':300},info)['days'] is None
    assert rest_evidence({'_past_runs':float('nan')},info)['days'] is None
    assert rest_evidence({'_past_runs':[{'race_date':'2026-01-01','position':'0'}]},info)['days'] is None


@pytest.mark.parametrize('mode,surface',[('nar','ダ'),('jra','障')])
def test_other_predictions_unchanged(mode,surface):
    a=sample();a.race_mode=mode;a.race_info['surface']=surface;before=copy.deepcopy(a.debug_info)
    with pytest.raises(ValueError):evaluate_candidate(a,{'rows':[]})
    assert a.debug_info==before


def test_old_snapshot_unchanged_and_new_roundtrip():
    import json,zipfile,io
    from core.prediction_history import prediction_zip_bytes
    r=sample();freeze_fresh_formal(r,position_scoring=False)
    old=copy.deepcopy(r.debug_info)
    evaluate_candidate(r,saved_formal_comparison(r))
    assert r.debug_info==old
    payload=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(r))).read('prediction.json'))
    assert payload['jra_formal_comparison_snapshot']==saved_formal_comparison(r)


def test_score_penalty_is_recomputed_not_accumulated():
    r=sample();freeze_fresh_formal(r,position_scoring=False)
    comparison=saved_formal_comparison(r)
    baseline=comparison['rows'][0]['jra_top5_score']
    for _ in range(3):
        comparison=evaluate_candidate(r,comparison)
        assert comparison['rows'][0]['jra_top5_score']==baseline-2
