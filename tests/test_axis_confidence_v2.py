import copy
import pytest
from core.axis_confidence_v2 import evaluate


def nar(rank=1, p=.15, jockey=35, **extra):
    return dict(pickup_rank=rank,nar_win_probability=p,current_jockey_place_rate=jockey,
                pure_ability_top5_group=True,**extra)


@pytest.mark.parametrize('rank,p,j,grade',[
    (1,.15,35,'A'), (1,.149,35,'B'), (1,.20,24,'B'),
    (1,.199,24.9,'C'),(1,.10,25,'B'),(2,.15,30,'B'),
    (2,.149,40,'C'),(2,.30,29.9,'C'),(3,.50,80,'C'),
    (1,None,80,None),(1,.30,None,None)])
def test_nar_boundaries(rank,p,j,grade):
    row=nar(rank,p,j);before=copy.deepcopy(row)
    assert evaluate([row],'nar')['horses'][0]['axis_confidence']==grade
    assert row==before


@pytest.mark.parametrize('rows,state',[
    ([nar()],'1頭軸候補あり'),
    ([nar(),nar(2,.2,30)],'2頭軸検討可能'),
    ([nar(1,.10,30),nar(2,.2,30)],'B-Bの2頭軸候補'),
    ([nar(1,.1,30)],'無理に1頭軸にしない'),
    ([nar(1,.1,20)],'軸不在 / 見送り寄り')])
def test_race_states(rows,state):
    assert evaluate(rows,'nar')['race_axis_state']==state


def test_limits_and_check_exclusion():
    rows=[nar(1,.3,40),nar(1,.4,40),nar(2,.2,35),nar(2,.3,35),nar(2,.4,35),nar(1,.9,90,nar_check_selected=True)]
    out=evaluate(rows,'nar')['horses']
    assert sum(r['axis_confidence']=='A' for r in out)==1
    assert sum(r['axis_confidence']=='B' for r in out)==2
    assert out[-1]['axis_confidence']=='C'


@pytest.mark.parametrize('rank,p,j,expected',[(1,.20,20,True),(1,.199,40,False),(1,.4,19.9,False),(2,.10,35,True),(2,.099,80,False),(2,.5,34.9,False),(3,.9,99,False),(1,None,40,False)])
def test_jra_shadow_only(rank,p,j,expected):
    row=dict(jra_top5_rank=rank,jra_top5_score=90,jra_win_probability=p,current_jockey_place_rate=j,
             axis_confidence='old',final_mark='◎',pace='H')
    before=copy.deepcopy(row);out=evaluate([row],'jra')['horses'][0]
    assert out['jra_axis_a_shadow']==expected
    assert all(out[k]==v for k,v in before.items()) and row==before


def test_jra_first_rank_priority_and_no_b():
    out=evaluate([dict(jra_top5_rank=2,jra_win_probability=.5,current_jockey_place_rate=80),
                  dict(jra_top5_rank=1,jra_win_probability=.2,current_jockey_place_rate=20)],'jra')
    assert [h['jra_axis_a_shadow'] for h in out['horses']]==[False,True]
    assert all('axis_confidence' not in h for h in out['horses'])


@pytest.mark.parametrize('mode',['nar','jra'])
def test_saved_restore_and_prediction_invariance(mode):
    import pandas as pd
    import json
    from core.models import PredictionResult
    from core.axis_confidence_v2 import snapshot,attach,restore,KEY
    from core.prediction_history import build_prediction_snapshot
    import app
    from render.mobile_png import _prediction_detail_records
    rows=[dict(馬番=i,馬名=f'H{i}',ability_rank=i,ver3_ability_core=80-i,
               netkeiba_corner4_rank=i,jra_top5_rank=i,jra_top5_score=90-i,
               平均指数=60-i,_jockey_course_place_rate=40,jra_win_probability=.25 if i==1 else .15)
          for i in range(1,7)]
    result=PredictionResult(race_mode=mode,overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows))
    result._jra_snapshot_restored=True
    if mode=='jra':
        result.debug_info['jra_win_probability_calibration']={'horses':[dict(horse_no=str(h['馬番']),jra_top5_rank=h['jra_top5_rank'],jra_top5_score=h['jra_top5_score'],jra_win_probability=h['jra_win_probability']) for h in rows]}
    before=copy.deepcopy(result)
    table=app.prediction_detail_records(result)
    formal=app.nar_comparison_from_result(result) if mode=='nar' else app.jra_comparison_from_result(result)
    attach(result)
    assert app.prediction_detail_records(result)==table==_prediction_detail_records(result)
    assert (app.nar_comparison_from_result(result) if mode=='nar' else app.jra_comparison_from_result(result))==formal
    pd.testing.assert_frame_equal(before.overall_table,result.overall_table)
    pd.testing.assert_frame_equal(before.horse_evaluation,result.horse_evaluation)
    assert {k:v for k,v in result.debug_info.items() if k!=KEY}==before.debug_info
    data=json.loads(json.dumps(snapshot(result)))
    assert build_prediction_snapshot(result)[KEY]==data
    restored=copy.deepcopy(before);restore(restored,{KEY:data})
    restored.overall_table['_jockey_course_place_rate']=0
    assert snapshot(restored)==data
    if mode=='jra':
        assert all(h['axis_confidence']==rows[0].get('axis_confidence') for h in data['horses'])


def test_old_jra_missing_formal_rank_not_recomputed():
    import pandas as pd
    from core.models import PredictionResult
    from core.axis_confidence_v2 import snapshot
    result=PredictionResult(race_mode='jra',overall_table=pd.DataFrame([dict(馬番=1,ver3_ability_core=99,_jockey_course_place_rate=90)]))
    result._jra_snapshot_restored=True
    h=snapshot(result)['horses'][0]
    assert h['jra_top5_rank'] is None and not h['jra_axis_a_shadow']


def test_attention_order_is_authoritative_no_sort_or_fallback():
    from core.axis_confidence_v2 import pickup_order
    ranks, issues=pickup_order(['13番 ベルジャッド\n印：○',' 4番 ナック','bad entry','3番 ミチノ'],{'13','4','3'})
    assert ranks=={'13':1,'4':2,'3':4} and issues
    assert pickup_order([],{'1'})[0]=={}
    assert pickup_order(['1番 A','1番 A'],{'1'})[0]=={}
    assert pickup_order(['99番 missing'],{'1'})[0]=={}


def test_snapshot_attention_overrides_formal_and_table_pickup():
    import pandas as pd
    from core.models import PredictionResult
    from core.axis_confidence_v2 import snapshot
    rows=[dict(馬番=i,馬名=f'H{i}',ability_rank=i,ver3_ability_core=80-i,平均指数=50,
               netkeiba_corner4_rank=i,_jockey_course_place_rate=40,pickup_rank=i)
          for i in range(1,6)]
    result=PredictionResult(race_mode='nar',overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows),attention_horses=['3番 H3','2番 H2','1番 H1','4番 H4'])
    data=snapshot(result)
    by={h['horse_no']:h for h in data['horses']}
    assert by['3']['pickup_rank']==1 and by['1']['pickup_rank']==3
    assert by['3']['axis_confidence']=='A' and by['1']['axis_confidence']=='C'
    result.attention_horses=[]
    assert all(h['pickup_rank'] is None and h['axis_reason']=='ピックアップ順位未取得' for h in snapshot(result)['horses'])
