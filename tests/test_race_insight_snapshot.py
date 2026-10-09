from copy import deepcopy
from unittest.mock import patch
import json
import pandas as pd
import pytest
from core.models import PredictionResult
from core.race_insight_snapshot import KEY, freeze, restore, resolve, display_rows
from core.race_development import build, render_html
from core.race_insight_common import narrative_horses, position_sentence, pace_effect


def result(mode='nar'):
    rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=60-i,
               nar_pure_ability_rank=i,pure_ability_top5_group=i<=5,nar_final_rank=i,
               netkeiba_corner4_rank=i,netkeiba_corner4_position='先団' if i<4 else '中団',
               netkeiba_pace='H',脚質='先' if i<4 else '差',
               jra_top5_rank=i,jra_top5_score=100-i,jra_pure_ability_score=60-i,
               jra_pure_ability_rank=i,距離指数=70-i,コース指数=70-i)
          for i in range(1,7)]
    return PredictionResult(race_mode=mode,race_info={'race_id':'202644100805'},
                            overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows),
                            debug_info={'existing_shadow': {'unchanged':True}})


@pytest.mark.parametrize('mode',['jra','nar'])
def test_freeze_restore_bypasses_updated_generator_and_is_detached(mode):
    r=result(mode);before=deepcopy(r)
    frozen=freeze(r)
    assert freeze(r)==frozen
    assert len(frozen['insight']['sections'])==5
    assert len(frozen['input_sha256'])==64 and frozen['inputs']['horses']==frozen['insight']['horses']
    assert r.debug_info==before.debug_info
    pd.testing.assert_frame_equal(r.horse_evaluation,before.horse_evaluation)
    restored=deepcopy(r);restore(restored,{KEY:json.loads(json.dumps(frozen))})
    with patch('core.race_insight.generate',side_effect=AssertionError('new generator')):
        got,origin=resolve(restored)
        assert got==frozen['insight'] and origin=='saved'
        assert freeze(restored)==frozen
        assert '現行版による参考再生成' not in render_html(restored,True,display_rows(restored))
    got['sections'][0]['paragraphs'].append('mutated returned copy')
    assert resolve(restored)[0]==frozen['insight']


def test_legacy_restore_is_labelled_and_does_not_write_payload():
    r=result();payload={'mobile_snapshot':{}};before=deepcopy(payload)
    restore(r,payload)
    assert resolve(r)[1]=='reference'
    assert '現行版による参考再生成' in render_html(r,True,display_rows(r))
    assert payload==before and KEY not in r.debug_info


def test_mobile_export_and_nested_restore():
    from core.prediction_history import build_prediction_snapshot
    r=result();export=build_prediction_snapshot(r)
    restored=result();restore(restored,{'mobile_snapshot':export})
    assert resolve(restored)[0]==export[KEY]['insight']
    assert KEY not in r.debug_info


def test_input_hash_tracks_evidence_not_outcomes_or_generated_time():
    r=result();a=freeze(r)
    for table in (r.overall_table,r.horse_evaluation):
        table['actual_finish']=1;table['払戻']=100000;table['人気']=1;table['オッズ']=1.1
    b=freeze(r)
    assert a['input_sha256']==b['input_sha256']
    for table in (r.overall_table,r.horse_evaluation):table['netkeiba_pace']='M'
    assert freeze(r)['input_sha256']!=a['input_sha256']


def fact(no,pure,style='先',group='front',conditions=()):
    return dict(no=str(no),pure=pure,pure_rank=no,style=style,group=group,corner=no,
                pace='H',pace_effect='risk',conditions=list(conditions),shift=False)


def test_h_front_ability_and_competition_context_only_changes_prose():
    hs=[fact(1,60,conditions=['コース指数80（1位）']),fact(2,50),fact(3,40,'差','back')]
    original=deepcopy(hs);prose=narrative_horses(hs)
    text=position_sentence(prose['1'])
    assert '最も高く' in text and '粘り込み' in text and '少なさだけでは今回の競り合いや消耗は読み切れない' in text
    assert 'コース指数80' in text and '負担' in text
    assert hs==original and pace_effect(hs[0])=='risk'
    assert '最も高く' not in position_sentence(prose['2'])


def test_missing_style_or_ability_does_not_invent_competition_or_strength():
    hs=[fact(1,None,'不明'),fact(2,None)]
    text=position_sentence(narrative_horses(hs)['1'])
    assert '未確認の情報' in text and '判断は保留' in text
    assert '最も高く' not in text and '逃げ脚質は0頭' not in text


def test_many_escapes_remains_conditional_and_closer_needs_backing():
    hs=[fact(1,60,'逃'),fact(2,50,'逃')]
    assert '競り合う形なら' in position_sentence(narrative_horses(hs)['1'])
    h=fact(3,None,'差','back');h['pace_effect']='plus'
    text=position_sentence(h)
    assert '裏付けは未確認' in text and 'H想定だけで届くとは判断しない' in text


def test_zero_historical_escapes_does_not_claim_no_current_leader():
    from core.race_insight import overview
    hs=[dict(fact(1,60),mark='◎',name='先行馬'),
        dict(fact(2,50,'差'),mark='○',name='差し馬')]
    text=overview(hs,'H')
    assert '今回逃げる馬がいないという意味ではない' in text
    assert '過去脚質の先行は1頭' in text and '今回の前方想定は2頭' in text
    assert '楽に運べる' not in text
    hs[1]['style']='不明'
    assert '確認できた範囲' in overview(hs,'H')


def test_saved_old_generation_version_is_not_upgraded():
    r=result();frozen=freeze(r)
    frozen['generation_version']='race_insight_explanation_v3_20261008'
    frozen['insight']['version']=frozen['generation_version']
    frozen['insight']['sections'][0]['paragraphs']=['保存時点の文章を保持する']
    restore(r,{KEY:frozen})
    with patch('core.race_insight.generate',side_effect=AssertionError('must not upgrade')):
        assert freeze(r)==frozen
        assert resolve(r)[0]['sections'][0]['paragraphs']==['保存時点の文章を保持する']
