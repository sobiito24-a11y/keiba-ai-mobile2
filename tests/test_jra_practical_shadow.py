import copy
import importlib.util
import io
import json
from pathlib import Path
import zipfile
import pandas as pd
import pytest
from core.models import PredictionResult
from core.jra_practical_shadow import KEY, evaluate_practical_shadow, attach_practical_shadow, practical_snapshot
from core.jra_practical_inputs import practical_inputs
from core.jra_practical_shadow_ui import practical_shadow_html


def inputs():
    return dict(race_id='202608040111', race_date='2026-10-03', time_status='pre_race', pace='S',
                prediction_created_at='2026-10-03T08:00:00', horses=[
        dict(horse_no=str(n), horse_name=f'馬{n}', pure_score=80-n*.1, formal_score=100-n,
             formal_rank=n, corner4_rank=n, training_grade='B', rest_days=20,
             distance_index=70-n, course_index=70-n, star_index=70-n, away_index=70-n,
             distance_rank=n, course_rank=n, star_rank=n, away_rank=n,
             recent_runs=[], head_to_head=[], load_change=0)
        for n in range(1,9)])


def sample_result():
    rows=[dict(馬番=n, 馬名=f'馬{n}', jra_top5_rank=n, jra_top5_score=90-n,
               market_ability_score=80-n, market_ability_rank=n, training_market='B 良好',
               netkeiba_corner4_rank=n, provider_pace_market='S',
               _past_runs=[dict(race_id='202608030111',race_date='2026-09-01',racecourse='京都',
                               surface='芝',distance=1200,label='前走',position=n,value=70-n)])
          for n in range(1,9)]
    return PredictionResult(race_mode='jra',created_at='2026-10-03T08:00:00',
                            race_info=dict(race_id='202608040111',race_date='2026-10-03',racecourse='京都',
                                           distance=1200,surface='芝',race_data='15:30発走'),
                            horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows[::-1]))


def test_whole_field_determinism_and_independent_anchor():
    data=inputs(); old=copy.deepcopy(data)
    first=evaluate_practical_shadow(data,evaluated_at='fixed')
    assert data==old and len(first['horses'])==8
    assert len(first['A'])==len(first['B'])==len(first['C'])==5
    assert evaluate_practical_shadow(data,evaluated_at='fixed')==first
    for h in data['horses']:
        h['formal_score']+=100;h['formal_position_bonus']=999
    second=evaluate_practical_shadow(data,evaluated_at='fixed')
    assert second['B']==first['B']
    assert [h['observed_subtotal'] for h in second['horses']]==[h['observed_subtotal'] for h in first['horses']]


def test_missing_not_imputed_and_missing_cannot_force_swap():
    data=inputs();data['horses'][0]['pure_score']=None
    data['horses'][1]['corner4_rank']=None
    output=evaluate_practical_shadow(data)
    assert output['horses'][0]['observed_subtotal'] is None
    assert output['horses'][1]['components']['position'] is None
    assert output['horses'][1]['score_interval'][0]<output['horses'][1]['score_interval'][1]
    assert not output['B'] and output['C']==output['A']
    assert output['horses'][0]['classification']=='優先度維持・材料不足'


def test_missing_axis_does_not_help_or_penalize_one_horse_in_free_comparison():
    data=inputs();data['horses'][3]['training_grade']=None
    output=evaluate_practical_shadow(data)
    assert 'training' not in output['common_comparison_domains']
    assert output['horses'][3]['components']['training'] is None
    for h in output['horses']:
        assert h['comparison_score']==h['pure_score']+h['components']['position']+h['components']['condition']


def test_guard_requires_both_evidence_and_interval_dominance_max_one():
    data=inputs()
    for n in (5,6):
        data['horses'][n].update(pure_score=90,corner4_rank=1,training_grade='A',distance_rank=1)
    no_caution=evaluate_practical_shadow(data)
    assert set(no_caution['B'])-set(no_caution['A'])
    assert no_caution['swap'] is None
    data['horses'][4].update(training_grade='D',rest_days=120)
    output=evaluate_practical_shadow(data)
    assert output['swap'] and output['swap']['removed']=='5'
    assert len(set(output['C'])-set(output['A']))==1
    assert len(set(output['A'])-set(output['C']))==1
    assert len(output['C'])==len(set(output['C']))==5
    assert output['swap']['reasons']


def test_layoff_and_prior_loss_not_automatic_penalties():
    data=inputs(); baseline=evaluate_practical_shadow(data)
    data['horses'][0].update(rest_days=365,head_to_head=[dict(race_id='old',own_finish=5,opponent_finish=1,opponent_no='2',condition_difference='距離変更')])
    output=evaluate_practical_shadow(data)
    assert output['horses'][0]['observed_subtotal']==baseline['horses'][0]['observed_subtotal']
    assert not output['horses'][0]['negative_reasons']
    assert any('対抗材料' in x for x in output['horses'][0]['decisive_conditions'])


def test_adapter_horse_join_date_filter_and_no_result_odds_features():
    result=sample_result(); before=copy.deepcopy(result)
    first=practical_inputs(result)
    for table in (result.horse_evaluation,result.overall_table):
        table['odds']=999;table['popularity']=1;table['actual_finish']=1;table['payout']=999999
    assert practical_inputs(result)==first
    assert first['time_status']=='pre_race'
    assert first['horses'][0]['rest_days']==32
    assert first['horses'][0]['head_to_head']
    assert first['horses'][0]['star_rank']==1
    result=before
    result.overall_table.at[0,'_past_runs']=[dict(race_id='future',race_date='2026-10-04',racecourse='京都',surface='芝',distance=1200,value=999)]
    output=practical_inputs(result)
    assert all(r['date']<'2026-10-03' for h in output['horses'] for r in h['recent_runs'])


def test_duplicates_fail_closed_body_weight_needs_acquisition_timestamp():
    result=sample_result(); result.overall_table['body_weight']=500
    assert all(h['body_weight'] is None for h in practical_inputs(result)['horses'])
    result.overall_table['body_weight_collected_at']='2026-10-03T07:30:00+09:00'
    assert all(h['body_weight']==500 for h in practical_inputs(result)['horses'])
    result.overall_table=pd.concat([result.overall_table,result.overall_table.iloc[:1]])
    attach_practical_shadow(result)
    assert result.debug_info[KEY]['status']=='input_error'


def test_official_prediction_navigator_probability_and_nar_unchanged():
    import app
    from core.jra_win_probability import jra_win_probability_snapshot
    from core.jra_purchase_navigator import build_jra_purchase_navigation
    result=sample_result()
    def outputs(r):
        return (app.jra_comparison_from_result(r),jra_win_probability_snapshot(r),
                build_jra_purchase_navigation(app.jra_enriched_display_rows(r),race_mode='jra',race_info=r.race_info,
                                              saved_rows=r.overall_table.to_dict('records')))
    before=copy.deepcopy(result);expected=outputs(result)
    attach_practical_shadow(result)
    assert outputs(result)==expected
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)
    assert set(result.debug_info)-set(before.debug_info)=={KEY}
    nar=sample_result();nar.race_mode='nar';original=copy.deepcopy(nar)
    attach_practical_shadow(nar)
    assert nar.debug_info==original.debug_info and practical_shadow_html(nar)==''
    pd.testing.assert_frame_equal(nar.overall_table,original.overall_table)


def test_snapshot_roundtrip_and_old_snapshot_never_replays(monkeypatch):
    from core.prediction_history import prediction_zip_bytes
    result=sample_result();attach_practical_shadow(result)
    saved=copy.deepcopy(result.debug_info[KEY])
    native=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(result))).read('prediction.json'))
    assert native[KEY]==saved
    import core.jra_practical_shadow as module
    monkeypatch.setattr(module,'evaluate_practical_shadow',lambda *a,**kw:pytest.fail('replay'))
    assert '自由選択5頭' in practical_shadow_html(result)
    if importlib.util.find_spec('core.prediction_snapshot'):
        from core.prediction_snapshot import race_snapshot_from_result,build_event_snapshot,keiba_bytes,load_keiba,restore_prediction_result
        restored=restore_prediction_result(load_keiba(keiba_bytes(build_event_snapshot([race_snapshot_from_result(result)])))['races'][0])
        assert restored.debug_info[KEY]==saved
        restored.debug_info.pop(KEY)
        attach_practical_shadow(restored)
        assert KEY not in restored.debug_info
        assert '未計算' in practical_shadow_html(restored)
    result.debug_info.pop(KEY)
    assert '未計算' in practical_shadow_html(result)


def test_jump_after_start_and_unknown_start_do_not_generate_free_five():
    for change in ('jump','late','unknown'):
        result=sample_result()
        if change=='jump':result.race_info['surface']='障'
        elif change=='late':result.created_at='2026-10-03T16:00:00'
        else:result.race_info.pop('race_data')
        attach_practical_shadow(result)
        assert not result.debug_info[KEY]['B']


def test_real_kyoto_all_horses_and_formal_values_retained():
    data=json.loads((Path(__file__).parent/'fixtures/jra_repro_kyoto_20261003_r11.json').read_text(encoding='utf8'))
    result=PredictionResult(race_mode='jra',created_at='2026-10-03T08:00:00',race_info=data['race_info'],
                            horse_evaluation=pd.DataFrame(data['horse_evaluation']),overall_table=pd.DataFrame(data['overall_table']),
                            debug_info={'jra_win_probability_calibration':{'horses':data['formal']}})
    attach_practical_shadow(result)
    output=result.debug_info[KEY]
    assert len(output['horses'])==18
    assert output['A']==['18','16','13','8','6']
    rows={h['horse_no']:h for h in output['horses']}
    for h in data['formal']:
        assert rows[h['horse_no']]['formal_rank']==h['jra_top5_rank']
        assert rows[h['horse_no']]['formal_score']==h['jra_top5_score']
    assert all('netkeiba' not in k or 'actual' not in k for h in output['horses'] for k in h)


def test_escaped_html_and_no_purchase_output():
    result=sample_result();result.horse_evaluation.loc[0,'馬名']='<script>alert(1)</script>'
    attach_practical_shadow(result);html=practical_shadow_html(result)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '購入推奨ではありません' in html
    assert '全頭の評価理由' in html
