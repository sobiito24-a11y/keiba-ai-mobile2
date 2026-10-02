import copy
import json
from unittest.mock import patch
import pandas as pd
import pytest
from core.newspaper_v2_engine import evaluate_shadow, attach_newspaper_v2_shadow
from core.newspaper_v2_class_inputs import previous_class_evidence, finish_quality, classify_previous, comparison_blockers
from core.newspaper_v2_class_revision import evaluate_class_revision, without_class_reference
from core.newspaper_v2_snapshot import newspaper_v2_snapshot, restore_newspaper_v2_snapshot
from core.models import PredictionResult


def newspaper(name="熊野特別", badge="2勝", venue="中京", finish="5", count="15頭", surface="芝2200"):
    return f'''<h1 class="RaceName">今回</h1><div class="RaceData01">芝2000</div><div class="RaceData02">3歳以上 2勝</div>
    <dl class="HorseList"><span class="Waku_Horse">1</span><div class="Past_Wrapper"><li class="Past">
    <div class="PastDataLine"><span class="Data01">08/30 {venue} 8R</span><span class="Icon_GradeType Icon_GradeType7">{badge}</span></div>
    <span class="RaceName"><a href="https://db.netkeiba.com/race/202607030408/">{name}</a></span><span class="Data03">定量</span>
    <span class="Data04"><span class="Num">{finish}</span></span><span class="Data05">{count}</span><span class="Data09">{surface}</span>
    </li></div></dl>'''


def sample():
    return [dict(馬番=1,馬名="test",ver3_ability_core=50.,ability_rank=1,jra_top5_rank=1,nar_top5_rank=1,
                 jra_top5_score=55.,ver3_final_mark="◎",jra_win_probability=1.,training_market="B")]


def test_real_markup_grade_sibling_not_data03_and_v1_unchanged():
    from core.newspaper_v2_inputs import newspaper_past_evidence
    html=newspaper();old=newspaper_past_evidence(html)
    new=previous_class_evidence(html)['1']
    assert new['class_badge_raw']=='2勝' and new['data03_raw']=='定量'
    assert new['head_count']==15 and new['finish']==5
    assert classify_previous(new)['class_label_v2']=='2勝'
    assert classify_previous(new)['age_restriction_v2']=='不明'
    assert old['1'][0]['race_data2']=='定量'  # frozen v1 behavior preserved


@pytest.mark.parametrize('finish,count,expected',[(1,10,1.),(10,10,-1.),(5,9,0.),(2,2,-1.)])
def test_finish_normalization(finish,count,expected):
    assert finish_quality(dict(finish=finish,head_count=count))==(expected,[])


@pytest.mark.parametrize('f,n',[(None,10),(1,None),(0,10),(11,10),(1,1),(1.5,10),(1,10.5),(float('nan'),10)])
def test_invalid_finish_never_fabricated(f,n):
    value,flags=finish_quality(dict(finish=f,head_count=n))
    assert value is None and flags


@pytest.mark.parametrize('mode',['jra','nar'])
def test_finish_works_without_comparable_class_and_bounds(mode):
    rows=sample();info=dict(race_name='3歳以上 2勝' if mode=='jra' else '一般 C2',racecourse='中山' if mode=='jra' else '浦和',surface='芝')
    html=newspaper(finish='1',count='10頭')
    base=evaluate_shadow(rows,info,mode,html=html,evaluated_at='fixed');before=copy.deepcopy(base)
    new=evaluate_class_revision(rows,info,mode,html=html,base_v1=base)
    h=new['horses'][0];p=mode+'_v2_'
    assert base==before and h[p+'finish_quality_score']==1
    assert h[p+'class_change_score'] is None
    assert h[p+'top5_candidate_score']-base['horses'][0][p+'top5_candidate_score']==pytest.approx(.25)
    assert new['model_version']!=base['model_version']
    assert new['coefficients']['win']['finish_quality']==.375
    assert new['coefficients']['win']['class_change']==.375
    assert new['coefficients']['top5']['finish_quality']+new['coefficients']['top5']['class_change']==base['coefficients']['top5']['class']


def test_transition_works_with_missing_finish():
    from core.jra_class_v2 import classify_jra_class
    rows=sample();info=dict(race_name='3歳以上 1勝',surface='芝',racecourse='東京')
    base=evaluate_shadow(rows,info,'jra',evaluated_at='frozen')
    # Explicit current context and previous class evidence, no inferred age.
    base['horses'][0]['recent_runs']=[dict(race_name='3歳以上 2勝',venue='中京',surface='芝',finish=None,head_count=12)]
    new=evaluate_class_revision(rows,info,'jra',base_v1=base)
    h=new['horses'][0]
    assert h['jra_v2_finish_quality_score'] is None
    assert h['jra_v2_class_change_score']==1
    assert h['class_revision']['contributions']['top5']['class_change']==.25


@pytest.mark.parametrize('kind',['age','venue','family','discipline','unknown_age'])
def test_transition_comparability_restrictions(kind):
    from core.nar_class_v2 import classify_nar_class
    c=classify_nar_class(dict(race_name='一般 C2',racecourse='浦和',surface='ダ'))
    p=copy.deepcopy(c)
    if kind=='age':p['age_restriction_v2']='3歳限定'
    if kind=='venue':p['venue_v2']='船橋'
    if kind=='family':p['class_family']='JRA'
    if kind=='discipline':p['race_discipline_v2']='jump'
    if kind=='unknown_age':p['age_restriction_v2']='不明'
    assert comparison_blockers(c,p)


def test_transferred_horse_family_comes_from_previous_venue():
    p=classify_previous(previous_class_evidence(newspaper(venue='東京'))['1'])
    assert p['class_family']=='JRA'
    p=classify_previous(previous_class_evidence(newspaper(venue='浦和',name='一般 C1',badge='',surface='ダ1400'))['1'])
    assert p['class_family']=='NAR'


def test_duplicate_and_first_slot_only():
    html=newspaper();past='<li class="Past"><span class="RaceName">G1</span></li>'
    assert previous_class_evidence(html.replace('</li></div>','</li>'+past+'</div>'))['1']['race_name']=='熊野特別'
    with pytest.raises(ValueError):previous_class_evidence(html+html)


def test_ablation_only_removes_old_class_contribution():
    rows=sample();info=dict(race_name='3歳以上 2勝',surface='芝')
    base=evaluate_shadow(rows,info,'jra',html=newspaper(name='3歳以上 1勝'),evaluated_at='frozen');before=copy.deepcopy(base)
    removed=without_class_reference(base)
    for purpose in ['win','top5']:
        expected=base['horses'][0]['jra_v2_'+purpose+'_candidate_score']-(base['horses'][0]['jra_v2_class_score'] or 0)*base['coefficients'][purpose]['class']
        assert removed['horses'][0]['jra_v2_'+purpose+'_candidate_score']==expected
    assert base==before


@pytest.mark.parametrize('mode',['jra','nar'])
def test_outcome_odds_invariance_and_frozen_two_versions(mode):
    rows=sample();info=dict(race_name='3歳以上 2勝',surface='芝');html=newspaper()
    original=copy.deepcopy(rows)
    base=evaluate_shadow(rows,info,mode,html=html,evaluated_at='frozen')
    expected=evaluate_class_revision(rows,info,mode,html=html,base_v1=base)
    for r in rows:r.update(odds=999,popularity=1,finish=1,payout=999999)
    actual=evaluate_class_revision(rows,info,mode,html=html,base_v1=base)
    assert expected==actual
    result=PredictionResult(race_mode=mode,race_info=info,overall_table=pd.DataFrame(original),horse_evaluation=pd.DataFrame(original))
    before=copy.deepcopy(result)
    attach_newspaper_v2_shadow(result,{'newspaper':html})
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    frozen=json.loads(json.dumps(newspaper_v2_snapshot(result),allow_nan=False))
    assert len(frozen)==2
    with patch('core.newspaper_v2_class_revision.evaluate_class_revision',side_effect=AssertionError('No recompute')):
        restored=restore_newspaper_v2_snapshot(before,frozen)
        assert newspaper_v2_snapshot(restored)==frozen
    assert restored.debug_info[mode+'_newspaper_v2_shadow']['model_version']==mode+'_newspaper_shadow_v1'


@pytest.mark.parametrize('mode',['jra','nar'])
def test_both_features_keep_old_maximum_and_other_components(mode):
    from core.jra_class_v2 import classify_jra_class
    from core.nar_class_v2 import classify_nar_class
    classify=classify_jra_class if mode=='jra' else classify_nar_class
    venue='東京' if mode=='jra' else '浦和'
    current='3歳以上 1勝' if mode=='jra' else '一般 C2'
    previous='3歳以上 2勝' if mode=='jra' else '一般 C1'
    info=dict(race_name=current,racecourse=venue,surface='芝' if mode=='jra' else 'ダ')
    base=evaluate_shadow(sample(),info,mode,evaluated_at='frozen')
    p=mode+'_v2_';h=base['horses'][0]
    h['recent_runs']=[dict(race_name=previous,venue=venue,surface=info['surface'],finish=1,head_count=10)]
    revised=evaluate_class_revision(sample(),info,mode,base_v1=base);n=revised['horses'][0]
    assert n[p+'finish_quality_score']==1.
    assert n[p+'class_change_score']==pytest.approx(1 if mode=='jra' else 1/3)
    for part in ['ability_anchor','recent_form_score','condition_score','pace_score','training_score','jockey_score','weight_score']:
        assert n[p+part]==h[p+part]
    for purpose in ['top5','win']:
        c=n['class_revision']['contributions'][purpose]
        assert abs(c['finish_quality'])+abs(c['class_change'])<=base['coefficients'][purpose]['class']


def test_revision_rejects_mixed_parent_and_unknown_family():
    base=evaluate_shadow(sample(),{},'jra')
    with pytest.raises(ValueError):evaluate_class_revision(sample(),{},'nar',base_v1=base)
    p=classify_previous({'venue':'不明会場','race_name':'一般 C2','surface':'ダ'})
    assert p['class_family']=='unknown'
    assert not p['comparable_class_group_v2']


def test_snapshot_finish_suffix_is_numeric_and_noncompletion_is_not_parse_error():
    base=evaluate_shadow(sample(),dict(race_name='3歳以上 1勝',surface='芝'),'jra')
    base['horses'][0]['recent_runs']=[dict(race_name='3歳以上 1勝',venue='東京',surface='芝',finish='2着',head_count=5)]
    new=evaluate_class_revision(sample(),{'surface':'芝'},'jra',base_v1=base)
    assert new['horses'][0]['jra_v2_finish_quality_score']==.5
    assert finish_quality({'finish':None,'head_count':10,'data04_raw':'中'})[1]==['previous_finish_noncompletion_or_withdrawal']
    assert finish_quality({'finish':None,'head_count':10,'data04_raw':'unexpected'})[1]==['previous_finish_parse_failure']
