import copy
import json
import pandas as pd
import pytest
from core.models import PredictionResult
from core.newspaper_stable_rating import parse, attach, assessment, FIELDS, SOURCE


def html(icon='Icon_Mark_02', number=6, name='対象馬', comment='◎ 調教A 好調'):
    return f'<table class="Stable_Comment"><tr><th>評価</th></tr><tr><td class="Waku">{number}</td><td class="Horse_Name">{name}</td><td class="txt_l">{comment}</td><td class="Hyoka"><span class="Icon_RaceInfo {icon}"></span></td></tr></table>'


@pytest.mark.parametrize('icon,grade',[('Icon_Mark_01','◎'),('Icon_Mark_02','○'),('Icon_Mark_03','△'),('Icon_Mark_04',''),('','')])
def test_only_explicit_provider_rating(icon,grade):
    got=parse(html(icon))['6']
    assert got[FIELDS[0]]==grade
    assert assessment(got)['grade']==grade
    assert got[FIELDS[2]]['reason']


def test_comment_training_prediction_symbols_not_used():
    assert parse('<div class="training"><span class="Icon_RaceInfo Icon_Mark_01"></span>◎ 調教A</div>')=={}
    for row in ({'stable_comment_market':'状態良好。条件が合う◎'}, {'調教評価':'A','最終印':'◎'}, {FIELDS[0]:'◎'}):
        assert assessment(row)['grade']==''


def test_conflicts_and_duplicates_are_not_guessed():
    assert parse(html('Icon_Mark_01 Icon_Mark_02'))['6'][FIELDS[0]]==''
    assert parse(html()+html())['6'][FIELDS[0]]==''


def test_attach_after_prediction_preserves_every_original_value_and_serializes():
    r=PredictionResult(race_mode='jra',overall_table=pd.DataFrame([{'馬番':6,'馬名':'対象馬','jra_top5_score':108.95,'最終印':'◎'}]),
                       horse_evaluation=pd.DataFrame([{'馬番':6}]),debug_info={'independent_ai':{'p':.123},'saved_prose':'保存文章'})
    before=copy.deepcopy(r)
    out=attach(r,{'newspaper':html()})
    pd.testing.assert_frame_equal(r.overall_table,before.overall_table)
    pd.testing.assert_frame_equal(out.overall_table.drop(columns=list(FIELDS)),before.overall_table)
    pd.testing.assert_frame_equal(out.horse_evaluation,before.horse_evaluation)
    assert out.debug_info==before.debug_info and out is not r
    saved=json.loads(json.dumps(out.overall_table.to_dict('records'),ensure_ascii=False))
    assert assessment(saved[0])['grade']=='○'
    assert saved[0][FIELDS[1]]==SOURCE


def test_missing_or_mismatched_name_does_not_assign_to_other_horse():
    r=PredictionResult(race_mode='jra',overall_table=pd.DataFrame([{'馬番':6,'馬名':'別馬'}]))
    out=attach(r,{'newspaper':html()})
    assert out.overall_table.iloc[0][FIELDS[0]]==''
    assert '不一致' in out.overall_table.iloc[0][FIELDS[2]]['reason']
    assert attach(r,{}) is r
    assert '未保存' in assessment(r.overall_table.iloc[0].to_dict())['reason']
    r.race_mode='nar'
    assert attach(r,{'newspaper':html()}) is r


def test_mobile_snapshot_metadata_optional_and_original_fields_unchanged():
    from core.newspaper_stable_rating import snapshot_metadata
    r=PredictionResult(race_mode='jra',overall_table=pd.DataFrame([{'馬番':6,'馬名':'対象馬'}]))
    payload={'horses':[{'horse_no':'6','prediction':{'mark':'◎'}}]}
    before=copy.deepcopy(payload)
    snapshot_metadata(r,payload)
    assert payload==before
    snapshot_metadata(attach(r,{'newspaper':html()}),payload)
    restored=json.loads(json.dumps(payload))
    assert assessment(restored['horses'][0])['grade']=='○'
    for k,v in before['horses'][0].items():assert restored['horses'][0][k]==v
