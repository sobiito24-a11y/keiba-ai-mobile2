import copy
import json
import math
from pathlib import Path

import pandas as pd
import pytest

from core.jra_win_probability import (
    calculate_jra_win_probabilities, annotate_jra_win_probabilities,
    probability_text, JRA_WIN_PROB_LABEL, JRA_WIN_PROB_CALIBRATION_VERSION,
    jra_win_probability_snapshot,
)
from core.models import PredictionResult
from core.prediction_table_ui import display_index_rows, prediction_table_records, supplementary_card_html, JRA_COLUMNS


@pytest.mark.parametrize('n',[1,2,5,12,18])
def test_full_field_normalization_and_monotonicity(n):
    scores=list(range(n))
    p=calculate_jra_win_probabilities(scores)
    assert abs(math.fsum(p)-1)<1e-9
    assert all(0<x<=1 for x in p)
    assert p==sorted(p)
    assert calculate_jra_win_probabilities([10]*n)==pytest.approx([1/n]*n)


def test_exact_formula_translation_invariance_and_extremes():
    expected=[.65*x/(1+math.exp(1))+.35/2 for x in [1,math.exp(1)]]
    assert calculate_jra_win_probabilities([0,8.5])==pytest.approx(expected)
    assert calculate_jra_win_probabilities([100,108.5])==pytest.approx(expected)
    assert calculate_jra_win_probabilities([-1e308,1e308])==pytest.approx([.175,.825])
    assert calculate_jra_win_probabilities([])==[]


@pytest.mark.parametrize('bad',[None,float('nan'),float('inf'),float('-inf'),'—','',True])
def test_missing_score_disables_entire_race(bad):
    assert calculate_jra_win_probabilities([90,bad,80])==[None,None,None]
    assert probability_text({'jra_win_probability':None})=='—'


def saved_result(mode='jra'):
    name='purchase_hanshin_20260921_r8.json' if mode=='jra' else 'purchase_nar_snapshot.json'
    f=json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf-8'))
    info=dict(f['race_info'],race_id='202609040608' if mode=='jra' else '202642092303')
    return PredictionResult(race_mode=mode,race_info=info,horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))


def test_reference_score_read_only_and_no_market_dependency():
    import app
    from core.jra_purchase_navigator import build_jra_purchase_navigation
    result=saved_result();raw=copy.deepcopy(result)
    official=app.sorted_display_rows(result);before=copy.deepcopy(official)
    nav=build_jra_purchase_navigation(official,race_mode='jra',race_info=result.race_info)
    p=annotate_jra_win_probabilities(official)
    assert official==before
    for a,b in zip(official,p):
        assert {k:b[k] for k in a}==a
    assert build_jra_purchase_navigation(p,race_mode='jra',race_info=result.race_info)==nav
    market=copy.deepcopy(official)
    for row in market:
        row.update(odds=999,actual_odds=.1,人気=99,popularity=99,市場反映勝率=99,単勝期待値=999)
    assert [h['jra_win_probability'] for h in annotate_jra_win_probabilities(market)]==[h['jra_win_probability'] for h in p]
    pd.testing.assert_frame_equal(result.horse_evaluation,raw.horse_evaluation)
    assert math.fsum(h['jra_win_probability'] for h in p)==pytest.approx(1)


def test_web_cards_png_and_nar_separation(monkeypatch):
    import app
    from render.mobile_png import _prediction_detail_records, _Canvas
    result=saved_result();official=app.sorted_display_rows(result)
    out=display_index_rows(official,[],result.race_info,'jra')
    assert all(JRA_WIN_PROB_LABEL in supplementary_card_html(h,'jra') for h in out)
    selected=[dict(h,card_role='本線') for h in official[:2]]
    cards=app.conclusion_horse_cards(result,selected,official)
    assert cards.count(JRA_WIN_PROB_LABEL)==2
    records=app.prediction_detail_records(result)
    assert JRA_COLUMNS[1:4]==['JRAスコア',JRA_WIN_PROB_LABEL,'最終印']
    assert records==_prediction_detail_records(result)
    calls=[]
    canvas=object.__new__(_Canvas)
    monkeypatch.setattr(canvas,'section',lambda *a,**k:None)
    monkeypatch.setattr(canvas,'horse_card',lambda title,lines,**k:calls.extend(lines))
    canvas.draw_prediction_conclusion(result)
    assert any(JRA_WIN_PROB_LABEL in s for s in calls)
    nar=saved_result('nar');nr=app.sorted_display_rows(nar)
    assert not any('jra_win_probability' in h for h in display_index_rows(nr,[],nar.race_info,'nar'))
    assert JRA_WIN_PROB_LABEL not in str(app.prediction_detail_records(nar))
    assert jra_win_probability_snapshot(nar) is None


def test_snapshot_metadata_and_lossless_json():
    from core.prediction_history import build_prediction_snapshot
    result=saved_result();before=result.horse_evaluation.copy(deep=True)
    snap=build_prediction_snapshot(result)
    stored=json.loads(json.dumps(snap,ensure_ascii=False))
    cal=stored['jra_win_probability_calibration']
    assert cal['temperature']==8.5 and cal['uniform_shrinkage']==.35
    assert cal['calibration_version']==JRA_WIN_PROB_CALIBRATION_VERSION
    assert cal==jra_win_probability_snapshot(result)
    probabilities={str(h['horse_no']):h['jra_win_probability'] for h in cal['horses']}
    assert math.fsum(probabilities.values())==pytest.approx(1)
    for h in stored['horses']:
        assert h['jra_win_probability']==probabilities[str(h['horse_no'])]
    assert 'jra_win_probability_calibration' not in build_prediction_snapshot(saved_result('nar'))
    pd.testing.assert_frame_equal(result.horse_evaluation,before)
