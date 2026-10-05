import copy
import pandas as pd
import pytest
from bs4 import BeautifulSoup
from core.models import PredictionResult
from core.jra_rank_display import official_jra_result_rows
from core.jra_display_mark import jra_display_mark_from_row
from core.jra_purchase_navigator import build_jra_buy_candidates


def result(days=70, grade='C', count=8):
    rows = [dict(馬番=i, 馬名=f'馬{i}', jra_top5_rank=i, jra_top5_score=100-i,
                 v1_final_mark={4:'✔︎', 5:'△', 6:'✔︎', 7:'△', 8:'✓'}.get(i, '◎'),
                 training_market=grade if i==1 else 'A', _days_since_last=days if i==1 else 10)
            for i in range(1, count+1)]
    return PredictionResult(race_mode='jra', race_info={'race_date':'2026-10-04', 'race_id':'202605040111', 'venue':'東京', 'race_number':'11R'},
        horse_evaluation=pd.DataFrame(rows), overall_table=pd.DataFrame(rows))


@pytest.mark.parametrize('days,grade,capped', [
    (69,'C',False),(70,'C',True),(70,'D',True),(133,'C',True),
    (70,'A',False),(70,'B',False),(70,None,False),(None,'C',False)])
def test_cap_boundary_and_missing_inputs(days, grade, capped):
    p=result(days,grade)
    before=copy.deepcopy(p)
    view=official_jra_result_rows(p,p.horse_evaluation.to_dict('records'))
    marks={h['馬番']:jra_display_mark_from_row(h) for h in view}
    assert marks[1] == ('△' if capped else '◎')
    assert sum(mark=='◎' for mark in marks.values()) == 1
    assert marks[2] == ('◎' if capped else '○')
    assert marks[3] == ('○' if capped else '▲')
    assert marks[4] == ('▲' if capped else '✔︎')
    assert marks[6]=='✔︎' and marks[7]=='△'
    assert {h['馬番']:h['jra_top5_score'] for h in view} == {i:100-i for i in range(1,9)}
    pd.testing.assert_frame_equal(p.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(p.overall_table,before.overall_table)
    assert p.debug_info==before.debug_info


def test_more_than_five_marked_horses_sorted_and_navigation_consistent():
    p=result()
    import app
    from render.mobile_png import _prediction_detail_records, _jra_purchase_rows
    rows=app.sorted_display_rows(p)
    assert [h['馬番'] for h in rows]==[2,3,4,6,1,5,7,8]
    assert [jra_display_mark_from_row(h) for h in rows]==['◎','○','▲','✔︎','△','△','△','✓']
    assert len([h for h in rows if jra_display_mark_from_row(h)])>5
    nav=build_jra_buy_candidates(rows)
    assert [h['number'] for h in nav['buy_groups']['中心']]==['2']
    assert '1' in [h['number'] for h in nav['reference_candidates']]
    assert '1' not in [h['number'] for h in nav['buy_candidates']]
    assert app.prediction_detail_records(p)==_prediction_detail_records(p)
    assert {h['馬番']:jra_display_mark_from_row(h) for h in _jra_purchase_rows(p)}=={
        h['馬番']:jra_display_mark_from_row(h) for h in rows}
    selected=[dict(h,card_role=role) for role,items in nav['buy_groups'].items() for h in items]
    cards=BeautifulSoup(app.conclusion_horse_cards(p,selected,rows),'html.parser').select('.recommended-horse')
    assert '◎' in cards[0].get_text() and '馬2' in cards[0].get_text()
    assert any('休養70日' in c.get_text() and '最大△' in c.get_text() for c in cards)


def test_do_not_fill_main_roles_from_outside_top5_when_all_capped():
    p=result()
    for table in (p.horse_evaluation,p.overall_table):
        table.loc[table.馬番<=5,'training_market']='D'
        table.loc[table.馬番<=5,'_days_since_last']=100
    view=official_jra_result_rows(p,p.horse_evaluation.to_dict('records'))
    assert all(jra_display_mark_from_row(h) not in ('◎','○','▲') for h in view)


def test_weight_changes_and_training_upgrade_never_force_mark_changes():
    p=result(69,'B')
    for table in (p.horse_evaluation,p.overall_table):
        table['weight_change_market']=[3,-3,-1,2,0,-2,0,0]
        table['previous_training_grade']='D'
    view=official_jra_result_rows(p,p.horse_evaluation.to_dict('records'))
    marks={h['馬番']:jra_display_mark_from_row(h) for h in view}
    assert marks[1]=='◎' and marks[2]=='○' and marks[6]=='✔︎'
    assert any('＋3kg' in reason for h in view if h['馬番']==1 for reason in h['_display_jra_mark_reasons'])


def test_native_saved_inputs_roundtrip_reproduces_final_marks():
    import importlib.util
    if importlib.util.find_spec('core.prediction_snapshot') is None:
        pytest.skip('Dashboard container roundtrip')
    from core.prediction_snapshot import serialize_prediction_result, restore_prediction_result, race_snapshot_from_result
    p=result()
    payload=serialize_prediction_result(p)
    rows=official_jra_result_rows(p,p.horse_evaluation.to_dict('records'))
    assert serialize_prediction_result(p)==payload
    restored=restore_prediction_result(race_snapshot_from_result(p))
    after=official_jra_result_rows(restored,restored.horse_evaluation.to_dict('records'))
    fields=('馬番','jra_top5_rank','jra_top5_score','_display_jra_final_mark','_display_jra_mark_cap','_display_jra_mark_reasons')
    assert [{k:h.get(k) for k in fields} for h in after]==[{k:h.get(k) for k in fields} for h in rows]
