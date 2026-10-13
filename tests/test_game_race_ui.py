import copy,json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from core.game_race_ui import build_view,document,frame_number,index_display,card_html
from core.prediction_table_ui import prediction_table_records

@pytest.mark.parametrize('mode',['jra','nar'])
@pytest.mark.parametrize('count',[7,10,18])
def test_projection_is_readonly_and_keeps_every_horse(mode,count):
    rows=[{'馬番':i,'馬名':f'馬{i}','枠番':min(i,8),'ver3_ability_core':50-i,'market_ability_rank':i,
           'netkeiba_corner4_rank':i,'純能力順位':i,'最終印':'✓' if i==6 else '✔︎' if i==4 else '—',
           '距離指数':90-i,'コース指数':80-i,'休養日数':323} for i in range(1,count+1)]
    before=copy.deepcopy(rows)
    records=prediction_table_records(rows,rows,{},mode)
    saved=copy.deepcopy(records)
    view=build_view(rows,records,rows,mode,{})
    assert rows==before and records==saved
    assert len(view)==len(rows)
    assert [h['no'] for h in view]==[r['馬番 / 馬名'].split()[0] for r in records]
    for h,r in zip(view,records):
        assert h['mark']==r['最終印']
        assert h['score']==r['JRAスコア' if mode=='jra' else 'NAR最終スコア']
        assert h['ability']==r['純能力']
    html=document(view)
    assert 'AI推定勝率' not in html and 'AI独立判断' not in html
    assert len(BeautifulSoup(html,'html.parser').select('tbody tr'))==count
    assert all('probability' not in h for h in view)

@pytest.mark.parametrize('cell,badge',[('113 / 1位','◎'),('113 / 2位','○'),('0 / 5位','△'),('13 / 8位','—'),('—','未取得'),('113','未取得')])
def test_index_uses_existing_rank(cell,badge):
    assert index_display(cell)['badge']==badge


def test_explicit_frame_conflict_missing_and_invalid():
    assert frame_number({'馬番':8}) is None
    assert frame_number({'枠番':3,'frame_no':4}) is None
    assert frame_number({'枠番':8})==8
    assert frame_number({'枠番':float('nan')}) is None


def test_markup_is_escaped_and_marks_distinct():
    from core.game_race_ui import mark_html
    assert 'target' in mark_html('✔︎') and 'check' in mark_html('✓')
    assert '<script>' not in mark_html('<script>')


def test_component_selection_cannot_invoke_prediction():
    source=(Path(__file__).parents[1]/'core/game_ui_assets/race.js').read_text(encoding='utf-8')
    assert 'setComponentValue' not in source
    assert 'fetch(' not in source
    assert 'sessionStorage' in source


def test_normal_route_has_no_independent_ai_or_probability_cards():
    import app,inspect
    source=inspect.getsource(app.render_colab_style_result)
    assert 'render_independent_ai' not in source
    assert 'render_game_prediction' in source
    assert source.index('render_game_prediction')<source.index('render_game_commentary')<source.index('研究・監査情報')


def test_saved_odds_with_unit_are_not_lost():
    rows=[{'馬番':1,'馬名':'確認馬','単勝オッズ':'20.1倍'}]
    records=prediction_table_records(rows,rows,{},'jra')
    assert build_view(rows,records,rows,'jra')[0]['odds']=='20.1'
