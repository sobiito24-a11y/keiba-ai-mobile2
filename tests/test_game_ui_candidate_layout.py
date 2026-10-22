from copy import deepcopy

from bs4 import BeautifulSoup
import pytest

from core.game_race_ui import candidate_html, conclusion_html
from core.final_candidate_selection import candidates, select_indices
from core.final_candidate_metrics import project


def horses(mode='jra'):
    rows=[]
    for i in range(1,10):
        h=dict(no=str(i),name='保存馬'+str(i),mode=mode,age='牡3',jockey='確認騎手',
               frame=3,mark=['◎','○','▲','✔︎','△','✓','✓','✔︎','—'][i-1],
               rank=str(10-i),score=str(80.2+i),internal_score=80.2+i,
               candidate_formal_score=80.2+i if i<=5 else None,formal_member=i<=5,
               ability='51',ability_rank='3',distance={'value':48,'rank':2},course={'value':46,'rank':4},
               style='先',corner=3,training='C',rest='180日',weight_delta=-1,
               plus='距離実績',caution='休養',jockey_change_text='継続',profile={'runs':[
                   dict(label=label,date=date,time_index=value,venue='門別',surface='ダ',distance='1100m',turn='右')
                   for label,date,value in [('3走前','2026-08-01',12),('前走','2026-10-01',8),('2走前','2026-09-01',15)]
               ],'stability_stars':4})
        h['final_metrics']=project(h,{'3走平均':11.7,'★最高指数':15})
        rows.append(h)
    return rows


@pytest.mark.parametrize('mode',['jra','nar'])
def test_accessible_maximum_six_same_members_in_table_and_cards_and_no_mutation(mode):
    view=horses(mode);before=deepcopy(view)
    doc=BeautifulSoup(candidate_html(view,candidates(view,'')),'html.parser')
    expected=[str(i) for i in select_indices(view)]
    for selector in ('.final-candidate-row','.final-mobile-card'):
        assert [r['data-candidate-index'] for r in doc.select(selector)]==expected
        assert len(doc.select(selector))==6
    for button in doc.select('[data-final-toggle]'):
        assert button['aria-expanded']=='false'
        assert doc.find(id=button['aria-controls']).has_attr('hidden')
    assert view==before


def test_default_number_order_has_no_marks_or_formal_rank_and_scores_are_hidden():
    doc=BeautifulSoup(candidate_html(horses(),{}),'html.parser')
    assert doc.select_one('#candidate-sort option[selected]')['value']=='no'
    assert [o['value'] for o in doc.select('#candidate-sort option')]==['no','score']
    assert not doc.select('.mark,.focus-badge,.medal-card,.candidate-score')
    assert all(c.has_attr('hidden') for c in doc.select('.final-score'))
    for c in doc.select('.final-score'):c.decompose()
    assert not any(mark in doc.get_text() for mark in ('◎','○','▲','✔','△','✓'))
    assert '正式順位' not in doc.get_text()
    assert '最終評価スコア' not in ' '.join(th.text for th in doc.select('th'))
    assert '純能力' in doc.text and '3位' in doc.text


def test_recent_indices_are_chronological_peak_and_stability_are_distinct():
    doc=BeautifulSoup(candidate_html(horses(),{}),'html.parser')
    header=[th.get_text() for th in doc.select('.final-table thead th')]
    assert header[header.index('前走'):header.index('前走')+3]==['前走','2走前','3走前']
    runs=doc.select_one('.final-mobile-card').select('.final-recent section')
    assert [r.h4.text for r in runs]==['前走','2走前','3走前']
    assert [r.b.get_text(strip=True).replace('★','') for r in runs]==['8','15','12']
    assert not runs[0].select('.maximum-match') and runs[1].select('.maximum-match')
    assert '門別・ダ1100m・右' in runs[0].text
    assert '4/5（指数のばらつき）' in doc.text and '11.7' in doc.text
    assert '4角 3番手' in doc.text and '-1kg' in doc.text


def test_missing_values_and_escaping():
    view=[dict(no='1',name='<script>馬</script>',mode='jra',formal_member=True,
               mark='◎',rank='1',score='—',ability_rank='—')]
    doc=BeautifulSoup(candidate_html(view,{}),'html.parser')
    assert not doc.select('script')
    assert '<script>馬</script>' in doc.text
    assert doc.select_one('.final-score-value').text=='未取得'
    assert '未取得' in doc.select_one('.final-recent').text


def test_conclusion_is_unmarked_and_original_full_field_projection_is_untouched():
    view=horses();before=deepcopy(view)
    doc=BeautifulSoup(conclusion_html(view),'html.parser')
    assert '6頭' in doc.text and '現行A' in doc.text
    assert not doc.select('.mark,.medal-card')
    assert view==before


def test_jra_training_is_shown_but_nar_does_not_invent_a_training_grade():
    for mode in ('jra','nar'):
        doc=BeautifulSoup(candidate_html(horses(mode),{}),'html.parser')
        headers=[th.text for th in doc.select('.final-table th')]
        assert ('調教' in headers)==(mode=='jra')


def test_final_details_do_not_reintroduce_formal_order_and_imported_odds_remain_visible():
    view=horses()
    view[0].update(overview='◎ 正式1位 最終スコア98',comment='◎ 正式1位',odds='8.6',popularity=3)
    view[0]['final_metrics'].update(plus='○ 今回調教B / ◎ スロー想定',caution='△ 休養')
    before=deepcopy(view)
    doc=BeautifulSoup(candidate_html(view,{}),'html.parser')
    assert '正式1位' not in doc.text and '最終スコア98' not in doc.text
    assert '単勝 8.6倍 · 3人気' in doc.select_one('.final-name').text
    assert not any(mark in doc.text for mark in '◎○▲✔✓△')
    assert '今回調教B' in doc.text and 'スロー想定' in doc.text and '休養' in doc.text
    assert view==before
