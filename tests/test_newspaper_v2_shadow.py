import copy
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from core.class_context import class_change, class_history
from core.jra_class_v2 import classify_jra_class
from core.nar_class_v2 import classify_nar_class
from core.models import PredictionResult
from core.newspaper_v2_engine import evaluate_shadow, attach_newspaper_v2_shadow
from core.newspaper_v2_snapshot import newspaper_v2_snapshot, restore_newspaper_v2_snapshot
from core.newspaper_v2_ui import newspaper_v2_html
from core.newspaper_v2_inputs import newspaper_past_evidence, recent_runs


@pytest.mark.parametrize('name,header,expected', [
    ('芙蓉S','サラ系２歳 オープン','OP'), ('勝浦特別','サラ系３歳以上 ２勝クラス','2勝'),
    ('秋風S','サラ系３歳以上 ３勝クラス','3勝'), ('野分特別','サラ系３歳以上 ２勝クラス','2勝'),
    ('サフラン賞','サラ系２歳 １勝クラス','1勝'), ('茨城新聞杯','サラ系３歳以上 ２勝クラス','2勝'),
    ('兵庫特別','サラ系３歳以上 ２勝クラス','2勝')])
def test_jra_real_header_classes_not_course_letter(name, header, expected):
    out = classify_jra_class(dict(race_name=name, race_data='芝1600m (右 外 C)', race_data2=header, class_label='C級'))
    assert out['class_label_v2'] == expected
    assert out['legacy_class_label'] == 'C級'


def test_grade_scoped_to_race_and_no_css_inference():
    html = '<span class="Icon_GradeType1">別レース</span><h1 class="RaceName ClassB">シリウスS<span class="Icon_GradeType Icon_GradeType3"></span></h1><div class="RaceData02">３歳以上 オープン</div>'
    assert classify_jra_class({}, html)['class_label_v2'] == 'G3'
    assert classify_jra_class({}, '<h1 class="RaceName ClassB GradeType3">特別</h1>')['class_label_v2'] == '不明'
    assert classify_jra_class(dict(race_name='勝浦特別', class_label='B級'))['class_label_v2'] == '不明'


@pytest.mark.parametrize('grade,expected',[('GⅠ','G1'),('GⅡ','G2'),('GⅢ','G3'),('Jpn1','Jpn1'),('JpnⅡ','Jpn2'),('JpnIII','Jpn3'),('L','L')])
def test_explicit_grade_variants(grade,expected):
    assert classify_jra_class({'race_grade':grade,'race_data2':'3歳以上 オープン'})['class_label_v2']==expected


@pytest.mark.parametrize('raw,label,group',[('2歳5組','2歳限定・5組','5'),('3歳3組','3歳限定・3組','3'),('3歳六','3歳限定・六組','六')])
def test_nar_age_restriction_not_b2(raw,label,group):
    out = classify_nar_class(dict(race_name=raw, racecourse='浦和', class_label='B2'))
    assert out['class_label_v2'] == label
    assert out['class_group_v2'] == group
    assert out['class_level_v2'] is None


def test_class_history_separates_previous_and_best():
    c=lambda label:classify_nar_class(dict(race_name='一般 '+label, racecourse='浦和'))
    out=class_history(c('C2'),[{'class':c('C2'),'finish':3},{'class':c('C1'),'finish':5}])
    assert out == dict(previous_to_current='同級',best_recent_class='C1',same_class_good_runs=1)
    j=lambda label:classify_jra_class(dict(race_name='3歳以上 '+label))
    assert class_history(j('1勝'),[{'class':j('1勝'),'finish':4},{'class':j('G3'),'finish':5}])['previous_to_current']=='同級'
    assert class_change(c('C2'),classify_nar_class(dict(race_name='一般 C1',racecourse='大井'))) == '比較不能'
    assert class_change(j('1勝'),c('C1')) == '比較不能'
    assert class_change(j('1勝'),classify_jra_class(dict(race_name='障害 3歳以上 1勝'))) == '比較不能'
    assert class_change(j('1勝'),classify_jra_class(dict(race_name='2歳 1勝'))) == '比較不能'


def sample_rows():
    return [dict(馬番=i,馬名=f'H{i}',ver3_ability_core=50+i,ability_rank=4-i,
                 jra_top5_rank=4-i,nar_top5_rank=4-i,jra_top5_score=60+i,
                 ver3_final_mark='◎' if i==3 else '△',jra_win_probability=i/6,
                 netkeiba_corner4_rank=i,provider_pace_market='S',training_market='B',
                 jockey_course_runs=40,jockey_course_top3_rate=30,
                 _past_runs=[dict(label='前走',value=60+i,position=3,head_count=12,race_name='3歳以上 1勝',venue='東京',distance=1600,surface='芝',direction='左'),
                             dict(label='2走前',value=50+i,position=1,head_count=12,race_name='3歳以上 1勝',venue='中山',distance=1600,surface='芝',direction='右')]) for i in range(1,4)]


@pytest.mark.parametrize('mode',['jra','nar'])
def test_deterministic_all_horses_and_official_invariance(mode):
    rows=sample_rows();original=copy.deepcopy(rows)
    info=dict(race_name='3歳以上 1勝' if mode=='jra' else '一般 C2',racecourse='東京',distance=1600,surface='芝',direction='左')
    a=evaluate_shadow(rows,info,mode,evaluated_at='frozen')
    b=evaluate_shadow(list(reversed(rows)),info,mode,evaluated_at='frozen')
    assert len(a['horses'])==3
    assert sorted(a['horses'],key=lambda h:h['horse_no'])==sorted(b['horses'],key=lambda h:h['horse_no'])
    assert rows==original
    for row in rows:row.update(odds=999,popularity=1,finish=1,payout=99999,result={'finish':1},確定着順=1)
    assert evaluate_shadow(rows,info,mode,evaluated_at='frozen')==a
    assert sorted(h[mode+'_v2_win_candidate_rank'] for h in a['horses'])==[1,2,3]
    assert a['model_version']==mode+'_newspaper_shadow_v1'


def test_missing_invalid_and_jump():
    for rows in [[],[{'馬番':1}],[{'馬番':1,'ver3_ability_core':float('nan')}],[{'馬番':1},{'馬番':1}],[{'馬番':'invalid'}]]:
        out=evaluate_shadow(rows,{},'jra')
        assert len(out['horses'])==len(rows)
        assert all(h['jra_v2_win_candidate_rank'] is None for h in out['horses'])
        json.dumps(out,allow_nan=False)
    out=evaluate_shadow(sample_rows(),{'race_name':'障害未勝利'},'jra')
    assert out['status']=='excluded_jump'
    assert all(h['jra_v2_win_candidate_rank'] is None for h in out['horses'])


@pytest.mark.parametrize('mode',['jra','nar'])
def test_attachment_and_frozen_snapshot(mode):
    result=PredictionResult(race_mode=mode,overall_table=pd.DataFrame(sample_rows()),horse_evaluation=pd.DataFrame(sample_rows()),debug_info={'existing':{'x':1}})
    before=copy.deepcopy(result)
    attach_newspaper_v2_shadow(result)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    assert result.race_info==before.race_info
    assert result.debug_info['existing']==before.debug_info['existing']
    frozen=json.loads(json.dumps(newspaper_v2_snapshot(result),allow_nan=False))
    with patch('core.newspaper_v2_engine.evaluate_shadow',side_effect=AssertionError('No replay allowed')):
        restored=restore_newspaper_v2_snapshot(before,frozen)
        assert newspaper_v2_snapshot(restored)==frozen
        assert 'V2勝ち馬候補' in newspaper_v2_html(restored)
        assert '未計算' in newspaper_v2_html(PredictionResult(race_mode=mode))


def test_predictor_post_hook_keeps_dashboard_signature():
    import inspect
    from core.jra_predictor import predict_jra
    from core.nar_predictor import predict_nar
    for fn,mode in [(predict_jra,'jra'),(predict_nar,'nar')]:
        r=PredictionResult(race_mode=mode,overall_table=pd.DataFrame(sample_rows()))
        original=r.overall_table.copy(deep=True)
        with patch(f'core.{mode}_predictor.predict_{mode}_from_html',return_value=r),patch(f'core.{mode}_predictor.apply_prediction_logic',side_effect=lambda result,version:result):
            out=fn({})
        pd.testing.assert_frame_equal(original,out.overall_table)
        assert mode+'_newspaper_v2_shadow' in out.debug_info
    assert 'prediction_logic_version' in inspect.signature(predict_jra).parameters


def test_class_parser_no_name_hardcoding():
    assert classify_jra_class({'race_name':'芙蓉S'})['class_label_v2']=='不明'


def test_nar_header_does_not_read_past_run_race_names():
    html='<div class="RaceName">一般 C2</div><div class="RaceData02">サラ系一般 C2</div><span class="RaceName">2歳新馬</span>'
    out=classify_nar_class({'racecourse':'佐賀'},html)
    assert out['class_label_v2']=='C2'
    assert out['age_restriction_v2']=='一般'
    assert out['class_group_v2']==''
    assert classify_nar_class({'race_name':'2歳未勝利'})['class_group_v2']==''
    assert classify_nar_class({'race_name':'2歳未勝利', 'race_data2':'サラ系2歳 2歳 12頭'})['class_group_v2']==''


def test_history_snapshot_carries_v2():
    from core.prediction_history import build_prediction_snapshot
    result=PredictionResult(race_mode='nar',overall_table=pd.DataFrame(sample_rows()))
    attach_newspaper_v2_shadow(result)
    assert build_prediction_snapshot(result)['nar_newspaper_v2_shadow']==result.debug_info['nar_newspaper_v2_shadow']


def test_past_html_join_is_by_horse_number_and_date_not_table_index():
    html='''<dl class="HorseList" id="past_tr_999"><dt class="Waku_Horse">7</dt><dd class="Past_Wrapper"><li class="Past"><span class="Data01">09/10 浦和 1R</span><span class="RaceName">一般 C2</span><span class="Data04"><span class="Num">5</span></span><span class="Data05">12頭</span><span class="Data07">1人気</span></li></dd></dl>'''
    evidence=newspaper_past_evidence(html)
    assert list(evidence)==['7']
    assert evidence['7'][0]['finish']==5
    assert evidence['7'][0]['head_count']==12
    row={'_past_runs':[{'label':'前走','race_date':'2026-09-10','value':70,'position':1}]}
    run=recent_runs(row,evidence['7'])[0]
    assert run['finish']==5 and run['time_index']=='70'
    row['_past_runs'][0]['race_date']='2026-09-09'
    assert recent_runs(row,evidence['7'])[0]['time_index'] is None
    with pytest.raises(ValueError):newspaper_past_evidence(html+html)


def test_jump_course_header_excludes_flat_model():
    assert evaluate_shadow(sample_rows(),{'race_data':'障3140m'},'jra')['status']=='excluded_jump'


def test_native_snapshot_serializes_actual_past_date_and_restores_shadow():
    from datetime import date
    import io
    import zipfile
    from core.prediction_history import prediction_zip_bytes
    rows=sample_rows()
    rows[0]['_past_runs'][0]['race_date']=date(2026,9,20)
    result=PredictionResult(race_mode='jra',overall_table=pd.DataFrame(rows))
    attach_newspaper_v2_shadow(result)
    payload=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(result))).read('prediction.json'))
    assert payload['horses'][0]['recent_races'][0]['date']=='2026-09-20'
    assert payload['jra_newspaper_v2_shadow']==result.debug_info['jra_newspaper_v2_shadow']


def test_shadow_jockey_identity_and_no_formal_mutation():
    from core.newspaper_v2_inputs import shadow_jockey_inputs, shadow_jockey_change
    rows = [{"horse_no": 1, "horse_name": "テスト", "jockey_course_runs": None}]
    html = """<link rel="canonical" href="https://race.netkeiba.com/race/data_list.html?race_id=202606040910&amp;mode=courseanalysis&amp;cid=2">
    <title>中山芝2000mが得意な騎手</title><table id="table_sort_back"><thead><tr>
    <th>馬 番</th><th>馬名</th><th>出走 回数</th><th>複勝率</th></tr></thead>
    <tbody><tr class="HorseList"><td>1</td><td>テスト</td><td>20</td><td>15%</td></tr></tbody></table>"""
    info = {"racecourse": "中山", "surface": "芝", "distance": 2000}
    result = shadow_jockey_inputs(rows, html, info, "202606040910", "jra")
    assert result[0]["jockey_course_runs"] == 20
    assert result[0]["jockey_course_top3_rate"] == 15
    assert rows == [{"horse_no": 1, "horse_name": "テスト", "jockey_course_runs": None}]
    for changed_html, changed_info, race_id, mode in [
        (html, info, "202606040911", "jra"),
        (html.replace("<td>テスト</td>", "<td>別馬</td>"), info, "202606040910", "jra"),
        (html, {**info, "distance": 1800}, "202606040910", "jra"),
        (html, info, "202606040910", "nar"),
    ]:
        assert shadow_jockey_inputs(rows, changed_html, changed_info, race_id, mode) == rows
    assert shadow_jockey_change({"jockey_change_market": "継続", "_previous_jockey": ""}) is None
    assert shadow_jockey_change({"jockey_change_market": "乗替", "_previous_jockey": "前騎手"}) == "乗替"
