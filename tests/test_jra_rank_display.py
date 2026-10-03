"""Official JRA values are presentation inputs, not a new prediction."""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from core.jra_rank_display import official_jra_display_rows, official_jra_values, official_jra_text
from core.models import PredictionResult


def result_for():
    rows = [dict(馬番=i, 馬名=f'テスト{i}', jra_top5_rank=rank,
                 jra_top5_score=score, v1_final_rank=4-rank, v1_final_mark=mark,
                 jra_pure_ability_score=70+i, jra_pure_ability_rank=i,
                 market_ability_score=70+i, ability_rank=i)
            for i, rank, score, mark in [(1, 3, 80.25, '◎'), (2, 1, 85.15, '▲'), (3, 2, 82.25, '✔︎')]]
    return PredictionResult(race_mode='jra', race_info={'racecourse':'阪神','distance':2000},
                            horse_evaluation=pd.DataFrame(rows), overall_table=pd.DataFrame(rows))


def test_official_values_override_legacy_only_in_display():
    result=result_for();source=result.horse_evaluation.to_dict('records')
    calculated=[dict(row,jra_top5_rank=99,jra_top5_score=999) for row in source]
    before=copy.deepcopy(calculated)
    view=official_jra_display_rows(calculated,source)
    assert [h['馬番'] for h in view]==[2,3,1]
    assert official_jra_values(view[0])==(1,85.15)
    assert all(h['jra_top5_rank']==99 and h['jra_top5_score']==999 for h in view)
    assert calculated==before


def test_cards_table_and_png_match_without_changing_selection(monkeypatch):
    import app
    from render.mobile_png import _prediction_detail_records
    result=result_for();before=copy.deepcopy(result)
    rows=app.sorted_display_rows(result)
    selected=[dict(number=str(i),card_role='本線') for i in (1,3,2)]
    saved_selected=copy.deepcopy(selected)
    html=app.conclusion_horse_cards(result,selected,rows)
    cards=BeautifulSoup(html,'html.parser').select('.recommended-horse')
    assert len(cards)==3
    assert ['テスト'+str(i) in card.get_text() for card,i in zip(cards,(2,3,1))]==[True]*3
    for card,row in zip(cards,rows):
        text=card.get_text()
        assert official_jra_text(row) in text
        assert text.index('JRA Top5') < text.index('純能力')
    assert selected==saved_selected
    table=app.prediction_detail_records(result)
    assert [h['JRA順位'] for h in table]==['1','2','3']
    assert [h['JRAスコア'] for h in table]==['85.2','82.2','80.2']
    assert table==_prediction_detail_records(result)
    assert [h['馬番'] for h in app.market_horse_cards_ordered(result.horse_evaluation).to_dict('records')]==[2,3,1]
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)


def test_old_missing_official_rank_is_not_inferred_from_legacy_or_score():
    import app
    from render.mobile_png import _prediction_detail_records
    result=result_for()
    for table in (result.horse_evaluation,result.overall_table):
        table.drop(columns=['jra_top5_rank','jra_top5_score'],inplace=True)
    before=copy.deepcopy(result)
    rows=app.sorted_display_rows(result)
    assert all(official_jra_values(row)==(None,None) for row in rows)
    selected=[dict(number='1',card_role='中心')]
    assert 'JRA Top5 — / スコア —' in app.conclusion_horse_cards(result,selected,rows)
    for row in rows:
        assert 'JRA Top5 — / スコア —' in app.horse_summary_card_html(row,'jra')
    for table in (app.prediction_detail_records(result),_prediction_detail_records(result)):
        assert all(row['JRA順位']=='—' and row['JRAスコア']=='—' for row in table)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)


def test_nar_display_does_not_use_jra_projection(monkeypatch):
    import app
    f=json.loads((Path(__file__).parent/'fixtures/purchase_nar_snapshot.json').read_text(encoding='utf-8'))
    result=PredictionResult(race_mode='nar',race_info=f['race_info'],
                            horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    before=copy.deepcopy(result)
    def forbidden(*args,**kwargs):
        pytest.fail('JRA projection called for NAR')
    monkeypatch.setattr(app,'official_jra_display_rows',forbidden)
    monkeypatch.setattr(app,'official_jra_result_rows',forbidden)
    monkeypatch.setattr(app.st,'markdown',lambda *a,**k:None)
    monkeypatch.setattr(app.st,'subheader',lambda *a,**k:None)
    app.render_nar_top5_result_summary(result)
    app.render_horse_summary_cards(result)
    app.prediction_detail_records(result)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)


def test_display_does_not_change_native_snapshot():
    import io
    import zipfile
    from core.prediction_history import prediction_zip_bytes
    result=result_for();before=copy.deepcopy(result)
    snapshot=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(result))).read('prediction.json'))
    # Saving after rendering must never persist private presentation metadata.
    import app
    app.prediction_detail_records(result)
    snapshot_after=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(result))).read('prediction.json'))
    assert snapshot['horses']==snapshot_after['horses']
    assert '_display_jra_top5_' not in json.dumps(snapshot_after)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)


def test_saved_calibration_supplies_official_rank_without_recalculation():
    import app
    result=result_for()
    for table in (result.horse_evaluation,result.overall_table):
        table.drop(columns=['jra_top5_rank','jra_top5_score'],inplace=True)
    result.debug_info['jra_win_probability_calibration']={'horses':[
        dict(horse_no=str(i),jra_top5_rank=rank,jra_top5_score=score)
        for i,rank,score in [(1,3,80.25),(2,1,85.15),(3,2,82.25)]]}
    before=copy.deepcopy(result)
    records=app.prediction_detail_records(result)
    assert [h['JRA順位'] for h in records]==['1','2','3']
    assert [h['JRAスコア'] for h in records]==['85.2','82.2','80.2']
    assert result.debug_info==before.debug_info
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)


def test_only_fresh_ui_prediction_uses_existing_formal_comparison(monkeypatch):
    import app
    result=result_for()
    for table in (result.horse_evaluation,result.overall_table):
        table.drop(columns=['jra_top5_rank','jra_top5_score'],inplace=True)
    monkeypatch.setattr(app,'predict_from_html_inputs',lambda *a,**k:result)
    got=app.run_prediction('jra',{}, {},prediction_logic_version='market')
    assert got is result
    rows=app.jra_enriched_display_rows(result)
    view=app.official_jra_result_rows(result,rows)
    assert all(official_jra_values(row)==(row['jra_top5_rank'],row['jra_top5_score']) for row in view)
    assert all(official_jra_values(row)[0] is not None for row in view)
    # Runtime context is not a serialized PredictionResult field.
    from dataclasses import asdict
    assert '_jra_live_display' not in asdict(result)
