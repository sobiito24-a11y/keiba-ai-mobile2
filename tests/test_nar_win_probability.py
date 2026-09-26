import copy
import io
import json
import math
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from core.models import PredictionResult
from core.nar_win_probability import (
    annotate_nar_win_probabilities, nar_probability_text, nar_win_probability_snapshot,
    nar_winprob_validation_rows, NAR_WINPROB_FIELDS, NAR_WINPROB_LABEL,
)
from core.jra_rescue_shadow import jra_rescue_shadow


def rows(n=5):
    return [dict(馬番=i+1, 馬名=f'H{i+1}', ver3_ability_core=30+i, 平均指数=20+i) for i in range(n)]


def result():
    r=rows()
    for i,h in enumerate(r):h.update(ability_rank=i+1, market_ability_rank=i+1, market_ability_score=h["ver3_ability_core"])
    return PredictionResult(race_mode='nar', race_info={'race_id':'202655092601','venue':'佐賀'},
                            horse_evaluation=pd.DataFrame(r), overall_table=pd.DataFrame(r))


def ps(r):
    return [h['nar_win_probability'] for h in annotate_nar_win_probabilities(r)]


@pytest.mark.parametrize('n',[1,2,5,9,12,18])
def test_sum_formula_and_order(n):
    r=rows(n);p=ps(r)
    assert abs(math.fsum(p)-1)<1e-9
    assert p==sorted(p)
    score=[.01838667*h['ver3_ability_core']+.02653994*h['平均指数'] for h in r]
    exp=[math.exp(s-max(score)) for s in score]
    assert p==pytest.approx([x/sum(exp) for x in exp])


@pytest.mark.parametrize('key',['ver3_ability_core','平均指数'])
def test_monotonic_and_no_mutation(key):
    r=rows();original=copy.deepcopy(r);p=ps(r)
    assert r==original
    r[0][key]+=10
    assert ps(r)[0]>p[0]


def test_imputation_does_not_treat_zero_or_negative_as_missing():
    r=rows();r[0].update(ver3_ability_core=None,平均指数=float('nan'))
    a=annotate_nar_win_probabilities(r)
    assert a[0]['nar_winprob_pure_ability']==29.2
    assert a[0]['nar_winprob_average_index']==22
    r[0].update(ver3_ability_core=0,平均指数=-5)
    a=annotate_nar_win_probabilities(r)
    assert a[0]['nar_winprob_pure_ability']==0
    assert a[0]['nar_winprob_average_index']==-5


@pytest.mark.parametrize('key',['ver3_ability_core','平均指数'])
def test_widespread_or_whole_feature_failure_disables_race(key):
    r=rows()
    for h in r[:3]:h[key]=None
    assert ps(r)==[None]*5
    assert nar_probability_text(annotate_nar_win_probabilities(r)[0])=='—'
    for h in r:h[key]=None
    assert ps(r)==[None]*5


def test_identity_join_not_row_order_and_duplicates_rejected():
    r=rows();display=[{'number':str(h['馬番'])} for h in r]
    a=annotate_nar_win_probabilities(display,list(reversed(r)))
    assert [h['nar_win_probability'] for h in a]==ps(r)
    assert all(h['nar_win_probability'] is None for h in annotate_nar_win_probabilities(display,r+[r[0]]))


def test_market_and_results_not_features():
    r=rows();before=ps(r)
    for h in r:h.update(odds=999,人気=1,popularity=1,market_probability=.99,finish=1,win=True)
    assert ps(r)==before


def test_actual_saga_missing_horses_and_equal_probability():
    f=json.loads((Path(__file__).parent/'fixtures/nar_winprob_20260926_saga1.json').read_text(encoding='utf-8'))
    p=ps(f['rows'])
    assert p==pytest.approx(f['expected_probabilities'])
    by={str(h['馬番']):v for h,v in zip(f['rows'],p)}
    assert by['1']==by['5']==max(p)


def test_prediction_navigation_unchanged_and_all_surfaces(monkeypatch):
    import app
    from core.prediction_table_ui import display_index_rows, supplementary_card_html
    from render.mobile_png import _prediction_detail_records, _Canvas
    p=result();raw=copy.deepcopy(p);official=app.sorted_display_rows(p)
    nav=app.nar_comparison_from_result(p)
    out=display_index_rows(official,p.overall_table.to_dict('records'),p.race_info,'nar')
    for before,after in zip(official,out):
        for key,value in before.items():
            assert repr(after[key])==repr(value)
    assert all(NAR_WINPROB_LABEL in supplementary_card_html(h,'nar') for h in out)
    assert NAR_WINPROB_LABEL in app.conclusion_horse_cards(p,official[:2],official)
    records=app.prediction_detail_records(p)
    assert records==_prediction_detail_records(p)
    assert all(h[NAR_WINPROB_LABEL]!='—' for h in records)
    calls=[];canvas=object.__new__(_Canvas)
    monkeypatch.setattr(canvas,'section',lambda *a,**k:None)
    monkeypatch.setattr(canvas,'horse_card',lambda title,lines,**k:calls.extend(lines))
    canvas.draw_prediction_conclusion(p)
    assert any(NAR_WINPROB_LABEL in s for s in calls)
    assert repr(app.sorted_display_rows(p))==repr(official)
    assert repr(app.nar_comparison_from_result(p))==repr(nav)
    pd.testing.assert_frame_equal(p.overall_table,raw.overall_table)
    pd.testing.assert_frame_equal(p.horse_evaluation,raw.horse_evaluation)


def test_snapshot_frozen_and_validation_results_join_separate():
    from core.prediction_history import build_prediction_snapshot, prediction_zip_bytes, save_prediction_history
    p=result();snap=build_prediction_snapshot(p);stored=json.loads(json.dumps(snap))
    assert math.fsum(h['nar_win_probability'] for h in stored['horses'])==pytest.approx(1)
    frozen=copy.deepcopy(stored)
    joined=nar_winprob_validation_rows(stored,{'1':1,'2':2})
    assert joined[0]['race_id']=='202655092601'
    assert joined[0]['prediction_created_at']==p.created_at
    by={h['horse_no']:h for h in joined}
    assert by['1']['win'] is True and by['2']['win'] is False and by['3']['win'] is None
    assert stored==frozen
    z=zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(p)))
    assert 'nar_winprob_validation.json' in z.namelist()
    # Retain saved values even if a future model's coefficients change.
    p.debug_info['nar_winprob_calibration']=stored['nar_winprob_calibration']
    p.overall_table['ver3_ability_core']=999
    assert nar_win_probability_snapshot(p)==stored['nar_winprob_calibration']
    enriched=annotate_nar_win_probabilities(stored['horses'])
    assert [h['nar_win_probability'] for h in enriched]==[h['nar_win_probability'] for h in stored['horses']]


def test_history_does_not_overwrite_existing_model(tmp_path):
    from core.prediction_history import save_prediction_history
    p=result();path=save_prediction_history(p,root=tmp_path);before=path.read_bytes()
    p.overall_table['ver3_ability_core']=999
    assert save_prediction_history(p,root=tmp_path)==path
    assert path.read_bytes()==before


def test_jra_rescue_is_shadow_only():
    base={'jra_top5_rank':6,'distance_index_rank':3,'jra_training_grade':'B'}
    old=dict(base)
    assert jra_rescue_shadow(base)['jra_rescue_shadow'] is True
    assert base==old
    assert not jra_rescue_shadow(dict(base,jra_top5_rank=5))['jra_rescue_shadow']
    assert not jra_rescue_shadow(dict(base,jra_training_grade='C'))['jra_rescue_shadow']
    assert jra_rescue_shadow(dict(base,distance_index_rank=8,class_shift_market='降級'))['jra_rescue_shadow']
    assert jra_rescue_shadow(dict(base,jra_training_grade='C',v1_reproducibility='B'))['jra_rescue_shadow']
    assert not jra_rescue_shadow({})['jra_rescue_shadow']
