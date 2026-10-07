import copy
import json
import pandas as pd
import pytest
from core.models import PredictionResult
from core.race_development import KEY, build, attach, snapshot, restore, render_html, newspaper_inputs


def sample(mode):
    rows=[{'馬番':i,'馬名':f'H{i}','ability_rank':i,'jra_top5_rank':i,
           'ver3_ability_core':80-i,'jra_top5_score':90-i,'平均指数':60-i,
           '脚質':['差し','先行','逃げ','追込'][i-1],
           'netkeiba_corner4_rank':i,'netkeiba_corner4_position':['先団','後方','先団','中団'][i-1],
           'netkeiba_pace':'H','training_grade':'A'} for i in range(1,5)]
    return PredictionResult(race_mode=mode,race_info={'race_id':'202645061711'},
                            overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows))


@pytest.mark.parametrize('mode',['jra','nar'])
def test_read_only_and_formal_invariance(mode):
    import app
    from core.jra_purchase_navigator import build_jra_buy_candidates
    r=sample(mode); original=copy.deepcopy(r)
    formal=lambda: app.nar_comparison_from_result(r) if mode=='nar' else build_jra_buy_candidates(app.sorted_display_rows(r))
    before=copy.deepcopy(formal());table=app.prediction_detail_records(r)
    attach(r)
    assert formal()==before and app.prediction_detail_records(r)==table
    pd.testing.assert_frame_equal(r.overall_table,original.overall_table)
    pd.testing.assert_frame_equal(r.horse_evaluation,original.horse_evaluation)
    assert {k:v for k,v in r.debug_info.items() if k not in (KEY,'nar_development_shift_shadow')}==original.debug_info
    d=snapshot(r)
    assert sum(map(len,d['running_style_groups'].values()))==4
    assert d['running_style_groups']['差']==['1'] and d['corner4_groups']['front']==['1','3']
    assert d['horses'][0]['position_difference']=='いつもより前で運べる想定'
    assert d['horses'][1]['position_difference']=='通常より後ろになる想定'
    assert len(d['development_plus_horses'])<=2
    assert {h['horse_no'] for h in d['development_caution_horses']}=={'1','2'}
    html=render_html(r,True)
    assert '<details' in html and 'open=' not in html and '展開・レース考察を見る' in html
    assert html.index('展開予想')<html.index('4コーナー展開予想')<html.index('レース考察</h4>')
    if mode=='nar':assert '調教' not in html


def test_rank_only_missing_conflict_and_no_axis_or_results_input():
    r=sample('nar');r.overall_table=r.overall_table.drop(columns=['netkeiba_corner4_position','脚質'])
    r.horse_evaluation=None
    d=build(r)
    assert d['corner4_groups']['unknown']==['1','2','3','4']
    assert d['running_style_groups']['不明']==['1','2','3','4']
    assert not d['development_caution_horses'] and not d['development_plus_horses']
    r.overall_table.loc[1,'netkeiba_pace']='S'
    assert build(r)['pace_prediction']=='不明'
    before=build(r);before.pop('generated_at')
    r.overall_table['着順']=1;r.overall_table['単勝オッズ']=999
    r.debug_info['axis_confidence_v2']={'race_axis_state':'BUY','horses':[]}
    after=build(r);after.pop('generated_at')
    for value in (before,after):
        value.get('development_shift_audit',{}).pop('evaluated_at',None)
    assert before==after
    empty=PredictionResult(race_mode='nar')
    assert build(empty)['horse_count']==0 and build(empty)['pace_prediction']=='不明'


@pytest.mark.parametrize('mode',['jra','nar'])
def test_app_collapsible_display_preserves_frozen_data(monkeypatch,mode):
    import app
    import core.race_development as development
    from bs4 import BeautifulSoup
    r=sample(mode);attach(r);before=copy.deepcopy(r.debug_info)
    def no_rebuild(*args,**kwargs):
        raise AssertionError('Frozen explanation must not be recalculated')
    monkeypatch.setattr(development,'build',no_rebuild)
    blocks=[]
    class Sink:
        def markdown(self,value,**kwargs):blocks.append(value)
    monkeypatch.setattr(app,'st',Sink())
    renderer=app.render_nar_top5_result_summary if mode=='nar' else app.render_jra_top5_result_summary
    renderer(r)
    html=''.join(blocks);soup=BeautifulSoup(html,'html.parser')
    panel=soup.select_one('details.development-panel')
    assert panel is not None and not panel.has_attr('open')
    assert panel.find('summary').get_text()=='展開・レース考察を見る'
    assert [h.get_text() for h in panel.select('h4')][:3]==['展開予想','4コーナー展開予想','レース考察']
    assert html.index('今回の結論')<html.index('details class="development-panel"')
    assert not panel.select('script,iframe,form')
    assert r.debug_info==before
    blocks.clear();renderer(r)
    assert ''.join(blocks)==html and r.debug_info==before


@pytest.mark.parametrize('mode',['jra','nar'])
def test_saved_frozen_roundtrip_and_old_snapshot(mode):
    from core.prediction_history import build_prediction_snapshot
    r=sample(mode);attach(r);saved=snapshot(r)
    payload=json.loads(json.dumps(build_prediction_snapshot(r),ensure_ascii=False))
    assert payload[KEY]==saved
    other=sample(mode);other.overall_table['netkeiba_pace']='S'
    restore(other,payload)
    assert snapshot(other)==saved
    assert snapshot(sample(mode))['pace_prediction']=='H'
    try:
        from core.prediction_snapshot import race_snapshot_from_result,build_event_snapshot,keiba_bytes,load_keiba,restore_prediction_result
    except ImportError:
        return
    event=load_keiba(keiba_bytes(build_event_snapshot([race_snapshot_from_result(r)])))
    assert snapshot(restore_prediction_result(event['races'][0]))==saved


def test_explicit_newspaper_style_is_not_position_or_race_specific():
    html='''<link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id=202645061711">
    <table><tr><th>逃げ</th><td><span class="Kyaku_Type_Num">2</span></td></tr>
    <tr><th>差し</th><td><span class="Kyaku_Type_Num">1</span></td></tr></table>'''
    r=sample('nar');d=build(r,html)
    assert d['running_style_groups']['逃']==['2','3']
    assert d['horses'][0]['running_style_source']=='newspaper.Kyaku_Type_Num'
    assert newspaper_inputs(html,'wrong-race','nar')=={}
    assert newspaper_inputs(html,'202645061711','jra')=={}
    # Existing v3 producers sometimes lack race_info.race_id. Two supplied
    # input documents must agree before using their newspaper-only evidence.
    r=sample('nar');r.race_info={}
    attach(r,{'newspaper':html,'speed':html})
    assert snapshot(r)['running_style_groups']['逃']==['2','3']
    r=sample('nar');r.race_info={}
    attach(r,{'newspaper':html,'speed':html.replace('202645061711','202645061712')})
    assert snapshot(r)['running_style_groups']['逃']==['3']


@pytest.mark.parametrize('mode',['jra','nar'])
def test_predictor_runs_explanation_after_existing_predictions(monkeypatch,mode):
    import importlib
    predictor=importlib.import_module('core.'+mode+'_predictor')
    r=sample(mode)
    monkeypatch.setattr(predictor,'predict_'+mode+'_from_html',lambda *a,**k:r)
    monkeypatch.setattr(predictor,'apply_prediction_logic',lambda result,*a:result)
    calls=[]
    paths=[('core.newspaper_v2_engine','attach_newspaper_v2_shadow'),
           ('core.jockey_positive','attach'),('core.material_reconsideration','attach_material_reconsideration'),
           ('core.axis_confidence_v2','attach')]
    paths+= [('core.jra_formal_snapshot','freeze_fresh_formal'),('core.jra_repro_candidate','attach_repro_candidate'),('core.jra_practical_shadow','attach_practical_shadow')] if mode=='jra' else [('core.nar_top5_order','attach')]
    for module,name in paths:
        def stage(result,*a,_name=name,**k):calls.append(_name);return result
        monkeypatch.setattr(importlib.import_module(module),name,stage)
    result=getattr(predictor,'predict_'+mode)({})
    assert KEY in result.debug_info and calls[-1]=='attach'
