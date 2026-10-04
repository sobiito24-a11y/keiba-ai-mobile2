"""All JRA views must use the same saved official first-three ranks."""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from core.jra_display_mark import jra_display_mark_from_row
from core.jra_purchase_navigator import build_jra_buy_candidates
from core.models import PredictionResult
from tests.test_jra_rank_display import result_for


def test_all_views_use_saved_rank_despite_conflicting_legacy_and_shadow():
    import app
    from render.mobile_png import _jra_purchase_rows, _prediction_detail_records, _display_mark
    p = result_for()
    p.debug_info['jra_repro_input_repair_shadow'] = {
        'horses': [{'horse_no': '1', 'candidate_rank': 1, 'candidate_mark': '◎'}]}
    before = copy.deepcopy(p)
    rows = app.jra_enriched_display_rows(p)
    nav = build_jra_buy_candidates(rows)
    assert [h['number'] for h in nav['buy_groups']['中心']] == ['2']
    assert [h['number'] for h in nav['buy_groups']['本線']] == ['3', '1']
    expected = {'2': '◎', '3': '○', '1': '▲'}
    assert {str(h['馬番']): app.display_mark_from_row(h, 'jra') for h in rows} == expected
    assert {str(h['馬番']): _display_mark(h, 'jra') for h in _jra_purchase_rows(p)} == expected
    table = app.prediction_detail_records(p)
    assert [h['最終印'] for h in table] == ['◎', '○', '▲']
    assert table == _prediction_detail_records(p)
    selected = [dict(h, card_role=role) for role, horses in nav['buy_groups'].items() for h in horses]
    cards = BeautifulSoup(app.conclusion_horse_cards(p, selected, rows), 'html.parser').select('.recommended-horse')
    for card, no in zip(cards, ('2', '3', '1')):
        assert expected[no] in card.get_text()
        assert f'テスト{no}' in card.get_text()
    for h in app.sorted_display_rows(p):
        title = BeautifulSoup(app.horse_summary_card_html(h, 'jra'), 'html.parser').select_one('.ka-horse-title-line')
        assert expected[str(h['馬番'])] in title.get_text()
    pd.testing.assert_frame_equal(p.horse_evaluation, before.horse_evaluation)
    pd.testing.assert_frame_equal(p.overall_table, before.overall_table)
    assert p.debug_info == before.debug_info


@pytest.mark.parametrize('rank', [4, 5])
@pytest.mark.parametrize('mark', ['△', '✔︎', '☆'])
def test_role_marks_4_and_5_remain_unchanged(rank, mark):
    row = {'jra_top5_rank': rank, 'v1_final_mark': mark, 'candidate_rank': 1, 'candidate_mark': '◎'}
    before = copy.deepcopy(row)
    assert jra_display_mark_from_row(row) == mark
    assert row == before


@pytest.mark.parametrize('rank', [None, True, 1.5, float('inf'), float('nan')])
def test_invalid_rank_never_generates_a_top_three_mark(rank):
    assert jra_display_mark_from_row({'jra_top5_rank': rank, 'v1_final_mark': '△'}) == '△'


def test_existing_kyoto_fixture_keeps_formal_order_not_repaired_order():
    import app
    f = json.loads((Path(__file__).parent/'fixtures/jra_repro_kyoto_20261003_r11.json').read_text(encoding='utf-8'))
    p = PredictionResult(race_mode='jra', race_info=f['race_info'],
                         horse_evaluation=pd.DataFrame(f['horse_evaluation']),
                         overall_table=pd.DataFrame(f['overall_table']))
    p.debug_info['jra_win_probability_calibration'] = {'horses': f['formal']}
    from core.jra_repro_candidate import attach_repro_candidate
    attach_repro_candidate(p)
    view = app.jra_enriched_display_rows(p)
    formal = {str(h['horse_no']): h['jra_top5_rank'] for h in f['formal']}
    for h in view:
        from core.prediction_table_ui import horse_key
        rank = formal[horse_key(h)]
        if rank <= 3:
            assert jra_display_mark_from_row(h) == {1: '◎', 2: '○', 3: '▲'}[rank]
