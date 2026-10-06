import copy
import json
import pandas as pd
import pytest
from core.nar_check_selection import select, snapshot
from core.nar_top5_order import annotate, attach
from core.nar_display_mark import display_mark
from core.models import PredictionResult


def field(n):
    return annotate([dict(number=i, ability_rank=i, ver3_ability_core=80-i,
                          netkeiba_corner4_rank=3, current_jockey_place_rate=20)
                     for i in range(1, n+1)])


@pytest.mark.parametrize('n,expected', [(8,[6]),(9,[6]),(10,[6,7]),(12,[6,7])])
def test_limits_and_official_invariance(n, expected):
    rows=field(n); before=copy.deepcopy(rows); out=select(rows)
    assert [r['number'] for r in out if r['nar_check_selected']]==expected
    assert rows==before
    for a,b in zip(before,out):
        assert all(b[k]==v for k,v in a.items())
        if display_mark(b)=='✓':
            assert not b['pure_ability_top5_group'] and b['ability_rank']<=8
            assert b['netkeiba_corner4_rank']<=6


def test_priority_and_stable_ties():
    rows=field(12)
    for i in (5,6,7): rows[i]['ability_rank']=6
    rows[5].update(netkeiba_corner4_rank=4,current_jockey_place_rate=99)
    rows[6].update(netkeiba_corner4_rank=3,current_jockey_place_rate=10)
    rows[7].update(netkeiba_corner4_rank=3,current_jockey_place_rate=40)
    assert [r['number'] for r in select(rows) if r['nar_check_selected']]==[7,8]
    rows[5]['netkeiba_corner4_rank']=3
    rows[5]['current_jockey_place_rate']=40
    assert [r['number'] for r in select(rows) if r['nar_check_selected']]==[6,8]
    rows[7]['current_jockey_place_rate']=None
    assert [r['number'] for r in select(rows) if r['nar_check_selected']]==[6,7]


@pytest.mark.parametrize('corner',[None,float('nan'),0,-1,6.5,7])
def test_missing_invalid_corner_not_rescued_by_jockey(corner):
    rows=field(9)
    for r in rows[5:]:r.update(netkeiba_corner4_rank=corner,current_jockey_place_rate=90)
    out=select(rows)
    assert not any(r['nar_check_selected'] for r in out)
    assert out[5]['nar_check_candidate_old'] and not out[5]['nar_check_candidate_new']


def test_tied_group_protected_and_boundary_and_market_independence():
    rows=field(10);rows[5]['pure_ability_top5_group']=True;rows[5]['ability_rank']=5
    rows[7].update(netkeiba_corner4_rank=6,current_jockey_place_rate=None)
    a=select(rows)
    assert [r['number'] for r in a if r['nar_check_selected']]==[7,8]
    assert not a[5]['nar_check_candidate_new'] and not a[8]['nar_check_candidate_new']
    for r in rows:r.update(odds=1.0,popularity=1,mark='✓',nar_warning_candidate=True)
    b=select(rows)
    assert [r['nar_check_selected'] for r in a]==[r['nar_check_selected'] for r in b]


def test_snapshot_roundtrip_and_display_match():
    import app
    from render.mobile_png import _prediction_detail_records
    from core.prediction_history import build_prediction_snapshot
    rows=field(10)
    result=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows))
    attach(result); before=copy.deepcopy(result.debug_info)
    audit=snapshot(result)
    assert json.loads(json.dumps(audit))==audit
    assert build_prediction_snapshot(result)['nar_check_selection']==audit
    assert result.debug_info==before
    table=app.prediction_detail_records(result)
    assert table==_prediction_detail_records(result) and len(table)==10
    assert sum(r['最終印']=='✓' for r in table)==2
    restored=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(json.loads(result.horse_evaluation.to_json(orient='records'))),overall_table=result.overall_table.copy(),debug_info=copy.deepcopy(before))
    assert app.prediction_detail_records(restored)==table
    conclusion=app.nar_comparison_from_result(result)
    assert len(conclusion['nar_top5_recommendations'])==5


def test_selected_checks_in_conclusion_table_and_cards(monkeypatch):
    import app
    from render.mobile_png import _prediction_detail_records
    rows=field(10)
    result=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows))
    attach(result);before=copy.deepcopy(result.debug_info)
    cards=[];html=[]
    original=app.recommended_cards_html
    def capture(values):
        cards.extend(values)
        return original(values)
    class Sink:
        def markdown(self,value,**kwargs):html.append(value)
    monkeypatch.setattr(app,'recommended_cards_html',capture)
    monkeypatch.setattr(app,'st',Sink())
    app.render_nar_top5_result_summary(result)
    assert [str(c['number']) for c in cards if c['mark']=='✓']==['6','7']
    assert all(c['mark']!='✓' for c in cards[:5])
    assert all('圏外' in c['role'] for c in cards[5:])
    assert all('NAR最終順位 —（正式Top5圏外）' in c['lines'] for c in cards[5:])
    table=app.prediction_detail_records(result)
    assert table==_prediction_detail_records(result)
    assert sum(r['最終印']=='✓' for r in table)==2
    assert result.debug_info==before
    assert '追加ヒモ候補' in ''.join(html)
