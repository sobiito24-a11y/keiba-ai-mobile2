import copy
from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup
from core.material_display import material_cells, material_html, material_map, explain_selected
from core.horse_card_evaluation import card_evaluation_fields


def evidence():
    return dict(horse_no='1', good='◎', concern='—', good_reasons={'position':'Hペース想定×4角7番手','state':'今回調教B'},concern_reasons={})


@pytest.mark.parametrize('mode',['jra','nar'])
def test_material_cell_uses_existing_verdict_and_never_limits_to_top5(mode):
    from core.material_reconsideration import display_material_cell
    e=evidence();row={'nar_final_rank':6,'jra_top5_rank':6,'v1_pace_eval':'△'}
    before=copy.deepcopy((row,e))
    cells=material_cells(row,mode,e)
    assert cells['今回プラス']==display_material_cell(e)=='◎ Hペース想定×4角7番手 / 今回調教B'
    assert cells['今回注意']=='—'
    html=material_html(row,mode,e)
    assert html.count('Hペース想定×4角7番手')==1
    assert '今回注意' not in html
    assert (row,e)==before
    assert card_evaluation_fields(row,'jra')[1][1]=='△'  # Aggregate ◎ is not a pace-only grade.


def test_no_materials_and_warning_precedence():
    assert material_html({},'jra')==''
    e=evidence();e['concern_reasons']={'rest':'休養183日＋調教C'}
    assert material_cells({},'jra',e)['今回注意']=='△ 休養183日＋調教C'
    row={'_display_jra_mark_reasons':['強い状態注意']}
    assert material_cells(row,'jra',e)['今回注意']=='強い状態注意'
    assert material_cells(row,'nar',e)['今回注意']=='△ 休養183日＋調教C'


def test_material_read_does_not_mutate_saved_result():
    from core.material_reconsideration import condition_key
    result=SimpleNamespace(race_mode='jra',debug_info={condition_key('jra'):{'horses':[evidence()]}})
    before=copy.deepcopy(result.debug_info)
    mapped=material_map(result);mapped['1']['good_reasons']['position']='modified'
    assert result.debug_info==before


def test_new_prose_preserves_selection_and_includes_both_material_sides():
    from core.material_reconsideration import condition_key
    e=evidence();e['concern_reasons']={'rest':'休養183日＋調教C'}
    result=SimpleNamespace(race_mode='jra',debug_info={condition_key('jra'):{'horses':[e]}})
    insight=dict(centers=[],opponents=['1'],additional=[],horses=[dict(no='1',name='対象馬',mark='△',member=False)],selection_audit={'1':{'role':'opponent'}},sections=[dict(paragraphs=[]) for _ in range(5)])
    insight['sections'][2]=dict(paragraphs=['正式6位。'],groups=[dict(horse_numbers=['1'],paragraphs=['正式6位。'])])
    before=copy.deepcopy(insight)
    got=explain_selected(insight,result,[dict(馬番=1)])
    assert got['centers']==before['centers'] and got['opponents']==before['opponents'] and got['additional']==before['additional']
    assert got['selection_audit']==before['selection_audit']
    assert 'Hペース想定×4角7番手' in got['sections'][2]['paragraphs'][0]
    assert '休養183日＋調教C' in got['sections'][4]['paragraphs'][0]
    assert got['sections'][2]['groups'][0]['paragraphs']==got['sections'][2]['paragraphs']


def test_frozen_prose_is_never_replaced(monkeypatch):
    from core.race_insight_snapshot import resolve, freeze, KEY
    saved=dict(insight=dict(sections=[dict(paragraphs=['保存本文']) for _ in range(5)]),generation_version='old')
    result=SimpleNamespace(debug_info={KEY:copy.deepcopy(saved)})
    def forbidden(*args,**kwargs):raise AssertionError('Saved prose must not be regenerated')
    monkeypatch.setattr('core.race_insight.generate',forbidden)
    assert resolve(result)==(saved['insight'],'saved')
    assert freeze(result)==saved and result.debug_info[KEY]==saved


def test_old_card_without_debug_info_is_supported():
    result = SimpleNamespace(race_mode='nar')
    assert material_map(result) == {}
    assert not hasattr(result, 'debug_info')
