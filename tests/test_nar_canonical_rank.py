import copy
import pandas as pd
import pytest
from core.nar_ability_rank import canonical_nar_ability_rank
from core.nar_race_diagnostics import build_full_field_comparison
from core.nar_condition_rescue import build_nar_condition_rescue
from core.models import PredictionResult


def rows():
    return [dict(馬番=str(i),馬名=f"Horse{i}",ability_rank=i,market_ability_rank=1,
                 market_ability_score=60-i if i<5 else 49.8,距離指数=100 if i==6 else i,
                 コース指数=i) for i in range(1,9)]


def test_rounding_never_merges_saved_fifth_and_sixth():
    data=rows();original=copy.deepcopy(data)
    c=build_full_field_comparison(data,race_mode="nar")
    by={h['number']:h for h in c['rows']}
    assert by['5']['nar_pure_ability_score']==by['6']['nar_pure_ability_score']==49.8
    assert by['5']['nar_pure_ability_rank']==5
    assert by['6']['nar_pure_ability_rank']==6
    assert {h['number'] for h in c['nar_top5_recommendations']}=={'1','2','3','4','5'}
    assert by['5']['nar_pure_top5'] and not by['6']['nar_pure_top5']
    rescue=build_nar_condition_rescue(c['rows'])
    assert '6' in {h['number'] for h in rescue} and '5' not in {h['number'] for h in rescue}
    assert data==original


@pytest.mark.parametrize('row,expected',[
    ({'ability_rank':6,'nar_pure_ability_rank':5,'market_ability_rank':4},6),
    ({'saved_ability_rank':7,'ability_rank':6},7),
    ({'nar_pure_ability_rank':6},6),
    ({'market_ability_rank':6},6),
    ({'market_ability_rank':6,'nar_pure_ability_rank':5},6),
    ({'ver3_ability_rank':1,'AI順位':1},None),
    ({'AI順位':1,'ai_rank':1,'current_evaluation_rank':1,'ability_value':99},None),
    ({'ability_rank':0,'nar_pure_ability_rank':6},6),
    ({'ability_rank':5.5},None),
])
def test_canonical_rank_sources(row,expected):
    assert canonical_nar_ability_rank(row)==expected


def test_web_png_export_share_canonical_boundary():
    import app
    from render.mobile_png import _nar_comparison_rows,_nar_condition_rescue
    data=rows();table=pd.DataFrame(data)
    p=PredictionResult(race_mode='nar',horse_evaluation=table,overall_table=table,race_info={'surface':'ダート'})
    web=app.nar_comparison_from_result(p)
    png=_nar_comparison_rows(p)
    expected={str(i):i for i in range(1,9)}
    assert {h['number']:h['nar_pure_ability_rank'] for h in web['rows']}==expected
    assert {h['number']:h['nar_pure_ability_rank'] for h in png}==expected
    exported=app.attach_nar_pure_top5_columns(table,'nar')
    assert dict(zip(exported['馬番'],exported['nar_pure_ability_rank']))==expected
    assert web['condition_rescue']==_nar_condition_rescue(p)
    pd.testing.assert_frame_equal(table,pd.DataFrame(data))
