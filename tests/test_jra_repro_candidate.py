import copy
import io
import json
import zipfile
import pandas as pd
import pytest
from core.models import PredictionResult
from core.jra_repro_candidate import (KEY, merged_runs, evaluate_repro_candidate,
                                     attach_repro_candidate, repro_candidate_html)
from core.jra_formal_snapshot import freeze_fresh_formal, saved_formal_comparison


def run(**kwargs):
    return dict(race_id='202608030101', race_date='2026-09-01', racecourse='京都',
                surface='芝',distance=1200,direction='右',position=2,label='前走',**kwargs)


def result_for(mode='jra'):
    evaluation=[{'馬番':n,'馬名':f'馬{n}','market_ability_score':80-n,'market_ability_rank':n,
                 'training':'B','_estimated_position_corner4_label':'先団'} for n in range(1,7)]
    overall=[dict(h,_past_runs=[run()]) for h in reversed(evaluation)]
    return PredictionResult(race_mode=mode,race_info={'race_id':'202608040111','race_date':'2026-10-03',
                            'racecourse':'京都','surface':'芝','distance':1200,'direction':'右'},
                            horse_evaluation=pd.DataFrame(evaluation),overall_table=pd.DataFrame(overall))


def test_merge_by_horse_and_fields_keeps_old_formula():
    result=result_for();before=copy.deepcopy(result)
    payload=evaluate_repro_candidate(result,evaluated_at='fixed')
    assert len(payload['horses'])==6
    for h in payload['horses']:
        assert h['repro_grade']=='S' and h['repro_bonus']==2
        assert h['candidate_score']==h['formal_score']+2
        assert h['pure_ability']==80-int(h['horse_no'])
        assert h['old_repro_bonus']==0
        assert h['candidate_score']==sum(h[k] for k in ('pure_ability','repro_bonus','pace_bonus','training_bonus','position_bonus'))
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)


def test_empty_list_does_not_hide_past_runs_and_duplicates_not_double_counted():
    a=run();b=dict(a);b.pop('position')
    runs,audit=merged_runs({'recent_runs':[],'_past_runs':[b]},{'_past_runs':[a,a]},'2026-10-03')
    assert len(runs)==1 and runs[0]['finish']==2
    assert audit['runs'][0]['sources']['finish']=='overall_table._past_runs.position'


@pytest.mark.parametrize('changed',[{'race_date':'10/01'},{'race_date':'2026-10-03'},
                                    {'race_date':'2026-10-05'},{'surface':None}])
def test_unknown_future_and_missing_conditions_are_not_guessed(changed):
    runs,audit=merged_runs({}, {'_past_runs':[{**run(),**changed}]},'2026-10-03')
    assert not runs and audit['missing_reason']


def test_identity_conflict_and_distinct_races():
    a=run();b={**a,'distance':1600}
    runs,audit=merged_runs({'_past_runs':[a]},{'_past_runs':[b]},'2026-10-03')
    assert not runs and audit['runs'][0]['conflicts']==['distance']
    b['race_id']='202608030102'
    runs,audit=merged_runs({'_past_runs':[a]},{'_past_runs':[b]},'2026-10-03')
    assert len(runs)==2


def test_date_order_three_runs_only():
    runs=[{**run(),'race_id':str(i),'race_date':f'2026-09-0{i}'} for i in range(1,5)]
    out,_=merged_runs({}, {'_past_runs':runs},'2026-10-03')
    assert [r['date'] for r in out]==['2026-09-04','2026-09-03','2026-09-02']


def test_duplicate_horse_number_fails_closed():
    result=result_for();result.overall_table=pd.concat([result.overall_table,result.overall_table.iloc[:1]])
    attach_repro_candidate(result)
    assert result.debug_info[KEY]['status']=='input_error'


def test_results_odds_and_popularity_cannot_affect_candidate():
    result=result_for();expected=evaluate_repro_candidate(result,evaluated_at='fixed')
    for table in (result.horse_evaluation,result.overall_table):
        for field in ('finish','result','確定着順','odds','人気','payoff'):
            table[field]=999
    assert evaluate_repro_candidate(result,evaluated_at='fixed')==expected


def test_freeze_preserves_formal_marks_probability_and_navigator(monkeypatch):
    import app
    from core.jra_win_probability import jra_win_probability_snapshot
    from core.jra_purchase_navigator import build_jra_purchase_navigation
    result=result_for();before=app.jra_comparison_from_result(result)
    prob=jra_win_probability_snapshot(result)
    freeze_fresh_formal(result)
    nav_before=build_jra_purchase_navigation(app.jra_enriched_display_rows(result),race_info=result.race_info,race_mode="jra")
    attach_repro_candidate(result)
    assert saved_formal_comparison(result)==before
    assert jra_win_probability_snapshot(result)==prob
    assert build_jra_purchase_navigation(app.jra_enriched_display_rows(result),race_info=result.race_info,race_mode="jra")==nav_before
    monkeypatch.setattr(app,'build_full_field_comparison',lambda *a,**k:pytest.fail('frozen view recalculated'))
    assert app.jra_comparison_from_result(result)==before
    app.jra_enriched_display_rows(result)


def test_saved_candidate_native_snapshot_and_display_no_replay(monkeypatch):
    from core.prediction_history import prediction_zip_bytes
    import core.jra_repro_candidate as module
    result=result_for();freeze_fresh_formal(result);attach_repro_candidate(result)
    expected=copy.deepcopy(result.debug_info[KEY])
    native=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(result))).read('prediction.json'))
    assert native[KEY]==expected
    restored=copy.deepcopy(result);restored.debug_info=json.loads(json.dumps(restored.debug_info))
    monkeypatch.setattr(module,'evaluate_repro_candidate',lambda *a,**k:pytest.fail('replay'))
    assert restored.debug_info[KEY]==expected
    assert '研究候補' in repro_candidate_html(restored)
    restored.debug_info.pop(KEY)
    assert '未計算' in repro_candidate_html(restored)


def test_nar_and_jump_excluded():
    result=result_for('nar');before=copy.deepcopy(result)
    assert evaluate_repro_candidate(result) is None
    assert attach_repro_candidate(result) is result
    assert freeze_fresh_formal(result) is result
    assert result.debug_info==before.debug_info
    assert repro_candidate_html(result)==''
    result=result_for();result.race_info['surface']='障'
    assert evaluate_repro_candidate(result)['status']=='障害対象外'


def test_real_kyoto_r11_reproduction_is_not_tuned_to_winner():
    from pathlib import Path
    f=json.loads((Path(__file__).parent/'fixtures/jra_repro_kyoto_20261003_r11.json').read_text(encoding='utf-8'))
    result=PredictionResult(race_mode='jra',race_info=f['race_info'],
                            horse_evaluation=pd.DataFrame(f['horse_evaluation']),overall_table=pd.DataFrame(f['overall_table']))
    payload=evaluate_repro_candidate(result,formal_rows=f['formal'])
    rows={h['horse_no']:h for h in payload['horses']}
    for no,rank,score,grade,bonus in [('6',6,103.5,'C',0),('18',1,110.35,'S',2),('8',4,105.65,'S',2)]:
        h=rows[no]
        assert (h['candidate_rank'],h['candidate_score'],h['repro_grade'],h['repro_bonus'])==(rank,score,grade,bonus)
    assert rows['6']['formal_rank']==5


def test_dashboard_keiba_restores_candidate_and_formal_without_rerun(monkeypatch):
    import importlib.util
    if importlib.util.find_spec('core.prediction_snapshot') is None:
        # Mobile's native JSON export is exercised above; no Dashboard loader.
        return
    from core.prediction_snapshot import race_snapshot_from_result,restore_prediction_result,build_event_snapshot,keiba_bytes,load_keiba
    import core.jra_repro_candidate as module
    result=result_for();freeze_fresh_formal(result);attach_repro_candidate(result)
    data=keiba_bytes(build_event_snapshot([race_snapshot_from_result(result)]))
    monkeypatch.setattr(module,'evaluate_repro_candidate',lambda *a,**k:pytest.fail('restore recalculated'))
    restored=restore_prediction_result(load_keiba(data)['races'][0])
    assert restored.debug_info[KEY]==result.debug_info[KEY]
    assert saved_formal_comparison(restored)==saved_formal_comparison(result)
