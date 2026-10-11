import copy
import json
import pytest
from bs4 import BeautifulSoup
from core.horse_card_evaluation import card_evaluation_fields, card_evaluation_html


@pytest.mark.parametrize('mode,row,expected', [
 ('jra', dict(jra_top5_score=60,jra_top5_rank=8,v1_pace_eval='○',market_ability_rank=1), ('60.0 / 8位','○')),
 ('jra', dict(jra_top5_score=999,jra_top5_rank=1,_display_jra_top5_score=60,_display_jra_top5_rank=6,v1_pace_eval='×'), ('60.0 / 6位','')),
 ('jra', dict(jra_top5_score=999,jra_top5_rank=1,_display_jra_top5_score=None,_display_jra_top5_rank=None,netkeiba_corner4_rank=1), ('— / —','')),
 ('nar', dict(nar_top5_order_score=-.254,nar_final_rank=2,market_ability_rank=1,netkeiba_corner4_rank=4), ('-0.3 / 2位','4番手')),
 ('nar', dict(nar_top5_order_score=None,nar_final_rank=7,pure_ability_top5_group=False,market_ability_score=88,market_ability_rank=6), ('— / 7位','—')),
 ('nar', dict(nar_top5_order_score=float('nan'),nar_final_rank=float('inf'),netkeiba_corner4_rank=True), ('— / —','—')),
 ('jra', {}, ('— / —','')),
 ('nar', {}, ('— / —','—')),
])
def test_read_only_existing_fields(mode,row,expected):
    before=repr(row)
    fields=card_evaluation_fields(row,mode)
    assert (fields[0][1],fields[1][1])==expected
    assert len(BeautifulSoup(card_evaluation_html(row,mode),'html.parser').select('.horse-evaluation-grid > div'))==2
    assert repr(row)==before


@pytest.mark.parametrize('mode',['jra','nar'])
def test_all_three_card_paths_and_json_restore(mode):
    import app
    from core.prediction_table_ui import recommended_cards_html
    row=dict(馬番=7,馬名='表示確認',jra_top5_score=60.,jra_top5_rank=7,v1_pace_eval='○',
             nar_top5_order_score=-.25,nar_final_rank=7,pure_ability_top5_group=False,
             netkeiba_corner4_rank=4,ver3_ability_core=80.,market_ability_rank=6)
    before=copy.deepcopy(row)
    for restored in [row,json.loads(json.dumps(row,ensure_ascii=False))]:
        htmls=[app.horse_summary_card_html(restored,mode,restored),app.market_horse_card_html(restored,mode),
               recommended_cards_html([dict(number=7,name='表示確認',evaluation_html=card_evaluation_html(restored,mode))])]
        for html in htmls:
            grid=BeautifulSoup(html,'html.parser').select_one('.horse-evaluation-grid')
            assert grid is not None
            assert ('60.0 / 7位' if mode=='jra' else '-0.2 / 7位') in grid.get_text()
    assert row==before
