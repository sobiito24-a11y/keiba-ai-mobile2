"""Responsive markup shares the same immutable candidate rows and evidence."""
from copy import deepcopy
import pytest
from bs4 import BeautifulSoup
from core.game_race_ui import candidate_html
from core.game_ui_candidate_evidence import candidates


def test_same_rows_feed_desktop_table_and_mobile_cards_without_duplicates():
    view=[dict(no=str(i),name='保存馬'+str(i),frame=3,mark='✔︎',rank=str(i),
               score='80.2',ability_rank='3',candidate_evidence=dict(
                   plus=['純能力3位','斤量−1.0kg'],minus=['長期休養323日'],neutral=[]))
          for i in range(1,14)]
    before=deepcopy(view)
    group=candidates(view,'① 最終印候補')
    html=BeautifulSoup(candidate_html(view,group),'html.parser')
    assert len(html.select('tbody tr'))==13
    assert len(html.select('[data-top-select]'))==13
    assert len(html.select('[data-candidate-select]'))==13
    for tr in html.select('tbody tr'):
        assert '80.2' in tr.select_one('.candidate-mobile-rating').text
        assert '純能力3位' in tr.select_one('.candidate-mobile-rating').text
        assert '純能力3位 / 斤量−1.0kg' in tr.text
        assert '長期休養323日' in tr.text
    assert view==before


def test_missing_scores_and_escaped_names_are_not_replaced():
    view=[dict(no='1',name='<script>長い馬名</script>',frame=None,mark='✓',rank='—',
               score='—',ability_rank='—',candidate_evidence=dict(plus=[],minus=[],neutral=[]))]
    html=BeautifulSoup(candidate_html(view,candidates(view,'① 最終印候補')),'html.parser')
    assert not html.select('script')
    assert html.select_one('.candidate-desktop-rank').text=='—'
    assert html.select_one('.candidate-mobile-rating').text=='AIスコア —／—純能力 —'
    assert [e.text for e in html.select('.info-reason')]==['—','—']


@pytest.mark.parametrize('plus,minus,empty_count,note',[
    ([],[],2,True),(['純能力1位'],[],1,False),([],['調教C'],1,False),(['調教A'],['長期休養323日'],0,False)])
def test_mobile_empty_rows_are_flagged_without_removing_desktop_cells(plus,minus,empty_count,note):
    view=[dict(no='1',name='確認馬',frame=1,mark='◎',rank='1',score='109.0',ability_rank='1',
               candidate_evidence=dict(plus=plus,minus=minus,neutral=['中立の位置情報']))]
    before=deepcopy(view)
    html=BeautifulSoup(candidate_html(view,candidates(view,'① 最終印候補')),'html.parser')
    assert len(html.select('tbody td'))==6
    assert len(html.select('.candidate-empty-material'))==empty_count
    assert bool(html.select('.candidate-empty-note'))==note
    assert html.select_one('.candidate-desktop-rank').text=='109.0／1位'
    assert view==before


@pytest.mark.parametrize('score,rank,expected',[('—','6','6位'),('—','—','—'),('0.0','2','0.0／2位'),('-1.2','4','-1.2／4位'),('80.2','—','80.2／—')])
def test_desktop_score_precision_and_missing_values(score,rank,expected):
    view=[dict(no='1',name='確認馬',frame=1,mark='✓',rank=rank,score=score,ability_rank='1',candidate_evidence={})]
    html=BeautifulSoup(candidate_html(view,candidates(view,'① 最終印候補')),'html.parser')
    assert html.select_one('.candidate-desktop-rank').text==expected
