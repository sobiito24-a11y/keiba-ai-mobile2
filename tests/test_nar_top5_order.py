import copy
import pandas as pd
from core.models import PredictionResult
from core.nar_top5_order import annotate, attach, snapshot, comparison_fields, MODEL_VERSION

def rows(tied=False):
    ranks=[1,2,3,4,5,5 if tied else 6,7]
    return [dict(number=str(i),name=f'horse{i}',ability_rank=rank,ver3_ability_core=60-i,
                 market_ability_score=60-i,netkeiba_corner4_rank=8-i)
            for i,rank in enumerate(ranks,1)]

def test_group_never_promotes_outside_and_preserves_input():
    data=rows();before=copy.deepcopy(data);out=annotate(data)
    assert data==before
    assert {h['number'] for h in out if h['pure_ability_top5_group']}==set('12345')
    assert next(h for h in out if h['nar_final_mark']=='◎')['number']=='5'
    assert out[5]['nar_final_mark']==out[6]['nar_final_mark']==''
    assert all(h['ability_rank']==before[i]['ability_rank'] for i,h in enumerate(out))

def test_boundary_tie_protects_six_and_two_triangles():
    out=annotate(rows(True))
    assert sum(h['pure_ability_top5_group'] for h in out)==6
    assert sum(h['nar_final_mark']=='△' for h in out)==2
    assert out[6]['nar_final_mark']==''

def test_missing_corner_and_core_protect_slots_without_imputation():
    data=rows();data[2]['netkeiba_corner4_rank']=None;data[0]['ver3_ability_core']=None
    out=annotate(data)
    assert out[2]['nar_final_rank']==3 and out[0]['nar_final_rank']==1
    assert out[2]['nar_top5_order_score'] is None
    assert out[0]['nar_top5_order_score'] is None
    for h in data:h['netkeiba_corner4_rank']=None
    assert [h['nar_final_rank'] for h in annotate(data)]==[1,2,3,4,5,6,7]

def test_unrelated_inputs_do_not_change_rank_or_mark():
    data=rows();a=annotate(data)
    for h in data:h.update(odds=999,popularity=1,distance_index=999,course_index=999,weight_change=-5,training='A',recent3_average=999)
    b=annotate(data)
    assert [(h['nar_final_rank'],h['nar_final_mark']) for h in a]==[(h['nar_final_rank'],h['nar_final_mark']) for h in b]

def test_ties_deterministic_and_duplicate_keys_fail_closed():
    data=rows()
    for h in data:h.update(ver3_ability_core=30,netkeiba_corner4_rank=2)
    assert [h['nar_final_rank'] for h in annotate(data)]==[1,2,3,4,5,6,7]
    data[1]['number']='1'
    assert all(h['nar_final_mark']=='' for h in annotate(data))

def test_snapshot_frozen_and_jra_noop():
    p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows()),overall_table=pd.DataFrame(rows()))
    attach(p);saved=snapshot(p);assert saved['model_version']==MODEL_VERSION
    p.overall_table['netkeiba_corner4_rank']=1
    assert snapshot(p)==saved
    p.race_mode='jra';before=copy.deepcopy(p)
    assert snapshot(p) is None
    attach(p)
    pd.testing.assert_frame_equal(p.overall_table,before.overall_table)
    assert p.debug_info==before.debug_info

def test_web_png_table_and_six_member_conclusion():
    import app
    from render.mobile_png import _prediction_detail_records
    p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows(True)),overall_table=pd.DataFrame(rows(True)))
    table=app.prediction_detail_records(p)
    assert table==_prediction_detail_records(p)
    assert 'NAR最終順位' in table[0] and '純能力順位' in table[0]
    assert '✔︎注目度' not in table[0]
    comparison=app.nar_comparison_from_result(p)
    assert len(comparison['nar_top5_recommendations'])==6
    assert sum(h['nar_final_mark']=='△' for h in comparison['rows'])==2


def test_export_roundtrip_preserves_frozen_order_and_original_tables():
    import json
    from core.prediction_history import build_prediction_snapshot
    from core.nar_top5_order import overlay_saved
    p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows(True)),overall_table=pd.DataFrame(rows(True)))
    before=copy.deepcopy(p)
    attach(p)
    exported=json.loads(json.dumps(build_prediction_snapshot(p),ensure_ascii=False))
    restored=copy.deepcopy(before)
    restored.debug_info={'nar_top5_corner_order':exported['nar_top5_corner_order']}
    restored.horse_evaluation['netkeiba_corner4_rank']=1
    frozen=overlay_saved(restored,restored.horse_evaluation.to_dict('records'))
    expected={h['horse_no']:h['nar_final_rank'] for h in exported['nar_top5_corner_order']['horses']}
    assert {h['number']:h['nar_final_rank'] for h in frozen}==expected
    pd.testing.assert_frame_equal(p.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(p.overall_table,before.overall_table)
    assert sum(h['nar_final_mark']=='△' for h in frozen)==2
