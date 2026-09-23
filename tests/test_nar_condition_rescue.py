import copy,json
from pathlib import Path
import pandas as pd
import pytest
from core.nar_condition_rescue import build_nar_condition_rescue
from core.nar_race_diagnostics import build_full_field_comparison
from core.models import PredictionResult
from core.prediction_history import build_prediction_snapshot


def test_rescue_ties_missing_odds_and_input_unchanged():
    rows=[dict(number=str(n),name=str(n),nar_pure_ability_rank=n,distance_index=100-n,course_index=None) for n in range(1,11)]
    rows[5]['distance_index']=99
    rows[6]['distance_index']=97
    rows[7]['distance_index']=None
    rows[8]['distance_index']=1000
    old=copy.deepcopy(rows)
    rescued=build_nar_condition_rescue(rows)
    assert [h['number'] for h in rescued]==['6']
    assert rows==old
    for row in rows:row.update(actual_odds=999,market_rank=1,ai_rank=1,current_evaluation_rank=1)
    assert build_nar_condition_rescue(rows)==rescued
    assert build_nar_condition_rescue(rows,race_mode='jra')==[]
    assert build_nar_condition_rescue([{'number':1,'nar_pure_ability_rank':6}])==[]


@pytest.mark.parametrize('race_id,expected',[('202642092303',{'7','10'}),('202642092304',{'3','7'})])
def test_urawa_saved_real_prediction_rescue_web_png_and_invariance(race_id,expected):
    import app
    from render.mobile_png import _nar_condition_rescue
    f=next(x for x in json.loads((Path(__file__).parent/'fixtures/nar_urawa_20260923_rescue.json').read_text(encoding='utf-8')) if x['race_id']==race_id)
    result=PredictionResult(race_mode='nar',race_info=dict(f['info'],race_id=race_id,date='2026-09-23',venue='浦和',race_number=str(int(race_id[-2:]))+'R'),horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f['overall']))
    before=copy.deepcopy(f)
    comparison=app.nar_comparison_from_result(result)
    rescue=comparison['condition_rescue']
    assert {h['number'] for h in rescue}==expected
    assert rescue==_nar_condition_rescue(result)
    saved={h['horse_no']:h for h in f['horses']}
    for horse in comparison['rows']:
        assert horse['nar_pure_ability_rank'] == saved[horse['number']]['ability_rank']
    top5 = {h['number'] for h in comparison['nar_top5_recommendations']}
    assert ('3' if race_id.endswith('03') else '1') in top5
    assert not expected & top5
    for h in rescue:assert h['ability_rank']==saved[h['number']]['ability_rank']
    plain=build_full_field_comparison(f['rows'],race_mode='nar',race_info=f['info'],sort_mode='current')
    assert comparison['rows']==plain['rows']
    assert comparison['race_purchase']==plain['race_purchase']
    html=app.nar_top5_conclusion_html(comparison)
    assert '条件適性救済' in html and html.index('NAR 最終購入判断')<html.index('NAR Top5サマリー')
    for h in rescue:
        assert h['nar_condition_rescue_reason'] in html
    assert f==before
    # Mobile exports prediction JSON; .keiba importer lives in Dashboard only.
    snapshot = build_prediction_snapshot(result)
    assert json.loads(json.dumps(snapshot,ensure_ascii=False)) == snapshot
    assert app.nar_comparison_from_result(result)['condition_rescue'] == rescue


def test_saved_rank_wins_over_rounded_display_rank_without_overwrite():
    displayed = [{'number':'1','nar_pure_ability_rank':5,'distance_index':90}, {'number':'2','nar_pure_ability_rank':8,'distance_index':95}]
    saved = [{'number':'1','market_ability_rank':6}, {'number':'2','market_ability_rank':9}]
    before = copy.deepcopy(displayed)
    rescue = build_nar_condition_rescue(displayed,ability_rows=saved)
    assert [h['number'] for h in rescue] == ['1']
    assert rescue[0]['ability_rank'] == 6
    assert displayed == before
