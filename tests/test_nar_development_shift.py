import copy
import json
import pandas as pd
import pytest
from core.nar_development_shift import evaluate, KEY
from core.race_development import snapshot, compose_commentary, attach, restore
from core.models import PredictionResult
from core.prediction_history import build_prediction_snapshot

def inputs():
    row=dict(horse_no='42',馬番=42,馬名='テスト馬',pure_ability_top5_group=False,
             nar_final_rank=9,nar_pure_ability_rank=9,nar_check_selected=False,
             class_shift_market='同級',_jockey_course_place_rate=25.0,
             脚質='先',netkeiba_corner4_position='後方',netkeiba_corner4_rank=9,netkeiba_pace='H')
    h=dict(horse_no='42',horse_name='テスト馬',running_style='先',corner4_group='back',
           corner4_rank=9,corner4_position='後方',position_difference='通常より後ろになる想定')
    return dict(horses=[h],race_id='test',pace_prediction='H',
                running_style_groups={'逃':[],'先':['42'],'差':[],'追':[],'不明':[]}),row

@pytest.mark.parametrize('changes,horse_changes,expected',[
 ({},{},True),
 ({'pure_ability_top5_group':True,'nar_final_rank':4},{},False),
 ({'nar_check_selected':True},{},False),
 ({},{'running_style':'逃'},False),
 ({},{'running_style':'差'},False),
 ({},{'corner4_group':'front'},False),
 ({},{'corner4_group':'middle'},True),
 ({'class_shift_market':'昇級'},{},False),
 ({'class_shift_market':'降級'},{},False),
 ({'_jockey_course_place_rate':24.9},{},False),
 ({'_jockey_course_place_rate':25.0},{},True),
 ({'_jockey_course_place_rate':None},{},None),
 ({'class_shift_market':None},{},None),
 ({},{'running_style':'不明'},None),
 ({},{'corner4_group':'unknown'},None),
 ({'class_shift_market':'同級','クラス変動':'昇級'},{},None),
 ({'_jockey_course_place_rate':25,'jockey_course_top3_rate':30},{},None),
])
def test_exact_conditions(changes,horse_changes,expected):
    data,row=inputs();row.update(changes);data['horses'][0].update(horse_changes)
    before=copy.deepcopy((data,row))
    assert evaluate(data,[row])['horses'][0]['development_shift_shadow'] is expected
    assert (data,row)==before

@pytest.mark.parametrize('pace,phrase',[('S','不利になる可能性'),('M','前が競り合う形'),('H','前が流れる形')])
def test_pace_only_changes_explanation(pace,phrase):
    data,row=inputs();data['pace_prediction']=pace
    out=compose_commentary(data,[row],'nar')
    assert out['development_shift_audit']['horses'][0]['development_shift_shadow'] is True
    assert phrase in out['race_commentary'][2]
    assert '展開から浮上候補' in out['race_commentary'][2]
    assert out['horses'][0]['formal_mark']==''
    assert not out['horses'][0]['selected_check']
    assert row['nar_final_rank']==9
    assert all(x not in ' '.join(out['race_commentary']) for x in ['Shadow','穴馬','妙味','人気薄','高配当'])

def test_market_and_result_independent():
    data,row=inputs();expected=evaluate(data,[row])['horses']
    for k in ['odds','人気','actual_finish','result','payoff','win_probability']:
        row[k]=9999
    assert evaluate(data,[row])['horses']==expected

def test_snapshot_frozen_new_and_legacy_no_mutation():
    data,row=inputs()
    r=PredictionResult(race_mode='nar',overall_table=pd.DataFrame([row]),horse_evaluation=pd.DataFrame([row]),debug_info={'existing_shadow':{'fixed':12},'course_materials':{'race_id':'123456789012'}})
    before=copy.deepcopy(r)
    attach(r)
    assert r.debug_info['existing_shadow']==before.debug_info['existing_shadow']
    pd.testing.assert_frame_equal(r.overall_table,before.overall_table)
    pd.testing.assert_frame_equal(r.horse_evaluation,before.horse_evaluation)
    audit=r.debug_info[KEY]
    assert audit['horses'][0]['development_shift_shadow'] is True
    assert audit['horses'][0]['pure_ability_rank']==9
    assert audit['race_id']=='123456789012'
    payload=json.loads(json.dumps(build_prediction_snapshot(r),ensure_ascii=False))
    assert payload[KEY]==audit
    restored=PredictionResult(race_mode='nar',debug_info={})
    restore(restored,payload)
    assert snapshot(restored)['development_shift_audit']==audit
    # Current source can change; frozen research output must not change.
    restored.overall_table=pd.DataFrame([dict(row,_jockey_course_place_rate=0)])
    assert snapshot(restored)['development_shift_audit']==audit
    legacy=PredictionResult(race_mode='nar',overall_table=pd.DataFrame([{'馬番':1,'馬名':'不足'}]),debug_info={})
    old=copy.deepcopy(legacy.debug_info)
    assert snapshot(legacy)['development_shift_audit']['horses'][0]['development_shift_shadow'] is None
    assert legacy.debug_info==old

def test_jra_never_receives_nar_shadow():
    data,row=inputs()
    out=compose_commentary(data,[row],'jra')
    assert 'development_shift_audit' not in out
