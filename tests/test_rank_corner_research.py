import copy
import json

import pytest

from core.rank_corner_research import freeze, join_outcomes, write_frozen
from core.nar_top5_order import annotate


def rows():
    return [dict(horse_no=i, pure=80-i*4, pure_rank=i, corner4=7-i,
                 candidate=i<=5, formal_rank=i, formal_mark='◎' if i==1 else '',
                 formal_score=80-i*4, status='', pace='H',
                 pace_bonus=0., position_bonus=0., repro_bonus=0.,
                 training_bonus=0., state_bonus=0.) for i in range(1,7)]


def test_nar_current_formula_matches_producer_and_no_input_mutation():
    hs=rows();hs[1]['corner4']=None;before=copy.deepcopy(hs)
    official=annotate([dict(number=h['horse_no'],ver3_ability_core=h['pure'],
                           saved_ability_rank=h['pure_rank'],netkeiba_corner4_rank=h['corner4']) for h in hs])
    expected=[int(h['number']) for h in sorted(official,key=lambda h:h['nar_final_rank'])]
    for h in hs:
        h['formal_rank']=expected.index(h['horse_no'])+1
    before=copy.deepcopy(hs)
    out=freeze('1','nar',hs)
    assert out['models']['A']['order']==expected
    assert hs==before
    for m in out['models'].values():
        assert m['order'][1]==2  # missing horse retains ordinal, not full pure fallback
        assert set(m['order'][:5])=={1,2,3,4,5}
    assert out['models']['A']['order']!=out['models']['B']['order']


def test_boundary_tie_all_protected_and_missing_does_not_become_six():
    hs=rows();hs[-1].update(pure_rank=5,candidate=True,pure=60,corner4=None)
    out=freeze('1','nar',hs)
    for m in out['models'].values():
        assert len(m['candidate_group'])==6
        assert m['order'][5]==6
    assert out==freeze('1','nar',list(reversed(hs)))


def test_result_market_fields_never_enter_input_hash_or_ranking():
    hs=rows();expected=freeze('1','nar',hs)
    for h in hs:h.update(finish=1,actual_corner4=1,odds=999,payout=9999)
    assert freeze('1','nar',hs)==expected
    hs[0]['corner4']=1
    assert freeze('1','nar',hs)['input_hash']!=expected['input_hash']


def test_jra_only_saved_decomposition_no_pure_replacement():
    hs=rows()
    for h in hs:h.update(pace_bonus=2.,position_bonus=1.5,training_bonus=.75,formal_score=h['pure']+4.25)
    out=freeze('1','jra',hs,{'discipline':'flat'})
    assert out['models']['B']['scores']['1']==hs[0]['pure']+.75
    assert out['models']['C']['scores']['1']==hs[0]['pure']+.75+1.75
    hs[0]['position_bonus']=None
    out=freeze('1','jra',hs)
    assert 'B' not in out['models']
    assert 'saved_score_components_not_reproducible' in out['exclusions']
    assert not freeze('1','jra',rows(),{'discipline':'jump'})['models']


def test_missing_keys_membership_and_prerace_withdrawal():
    hs=rows();hs[0]['horse_no']=2
    assert not freeze('1','nar',hs)['models']
    hs=rows();hs[0]['candidate']=None
    assert not freeze('1','nar',hs)['models']
    hs=rows();hs[0]['status']='取消'
    out=freeze('1','nar',hs)
    assert all(1 not in m['order'] and 6 not in m['candidate_group'] for m in out['models'].values())


def test_frozen_exclusive_roundtrip_and_separate_outcome_join(tmp_path):
    frozen=freeze('1','nar',rows());before=copy.deepcopy(frozen)
    path=tmp_path/'research.json';write_frozen(path,frozen)
    assert json.loads(path.read_text(encoding='utf-8'))==frozen
    with pytest.raises(FileExistsError):write_frozen(path,frozen)
    joined=join_outcomes(frozen,{'finish':{'1':1}})
    joined['outcomes']['finish']['1']=9
    assert frozen==before


def test_unranked_outside_horse_does_not_invalidate_protected_group():
    hs=rows();hs[-1].update(pure=None,pure_rank=None,formal_rank=None,corner4=None)
    out=freeze('1','nar',hs)
    assert set(out['models'])=={'A','B','C','D'}
    assert all(m['order'][-1]==6 for m in out['models'].values())
    assert hs[-1]['pure_rank'] is None


def test_jra_unknown_ability_rank_is_not_invented_for_tie_break():
    hs=rows();hs[-1].update(pure_rank=None)
    out=freeze('1','jra',hs)
    assert not out['models']
    assert 'missing_candidate_membership_or_ability_rank' in out['exclusions']


def test_saved_official_is_authoritative_when_formula_replay_differs():
    hs=rows()
    frozen=freeze('1','nar',hs,{'formal_origin':'saved'})
    assert frozen['models']['A']['order']==[1,2,3,4,5,6]
    assert frozen['formal_replay_matches'] is False
    assert frozen['models']['A']['definition']['source']=='saved'


def test_ability_ties_and_equal_display_values_never_replace_saved_rank():
    hs=rows()
    hs[0].update(horse_no=12,pure=101.3,pure_rank=2)
    hs[1].update(horse_no=7,pure=101.3,pure_rank=1)
    frozen=freeze('2','nar',hs)
    assert frozen['models']['B']['order'][:2]==[7,12]
    hs[0].update(horse_no=10,pure=18.1,pure_rank=1)
    hs[1].update(horse_no=3,pure=18.1,pure_rank=1)
    hs[2]['horse_no']=13
    assert freeze('3','nar',hs)['models']['B']['order'][:2]==[3,10]
    assert freeze('3','nar',list(reversed(hs)))==freeze('3','nar',hs)


def test_same_race_cannot_be_saved_again_under_another_filename(tmp_path):
    frozen=freeze('1','nar',rows());registry=tmp_path/'shared_registry'
    a=tmp_path/'dashboard';b=tmp_path/'mobile';a.mkdir();b.mkdir()
    write_frozen(a/'one.json',frozen,registry_dir=registry)
    with pytest.raises(FileExistsError):
        write_frozen(b/'different_name.json',frozen,registry_dir=registry)
    assert not (b/'different_name.json').exists()


def test_future_validation_rejects_old_dates_late_writes_and_naive_times(tmp_path):
    from datetime import datetime, timezone
    now=datetime(2026,10,11,0,0,tzinfo=timezone.utc)
    metadata=dict(date='2026-10-11',prediction_created_at='2026-10-10T23:00:00Z',
                  scheduled_post_time='2026-10-11T01:00:00Z',formal_origin='saved')
    frozen=freeze('1','nar',rows(),metadata)
    stored=write_frozen(tmp_path/'future.json',frozen,phase='future_validation',now=now)
    assert stored['validation']['phase']=='future_validation'
    assert 'validation' not in frozen
    assert stored['input_hash']==frozen['input_hash']
    for field,value in [('date','2026-10-10'),('scheduled_post_time','2026-10-10T23:59:00Z'),
                        ('prediction_created_at','2026-10-11T00:00:00'),
                        ('prediction_created_at','2026-10-11T00:30:00Z'),
                        ('scheduled_post_time','2026-10-12T01:00:00Z')]:
        bad=freeze('2','nar',rows(),dict(metadata,**{field:value}))
        with pytest.raises(ValueError):
            write_frozen(tmp_path/'bad.json',bad,phase='future_validation',now=now)
    assert not (tmp_path/'bad.json').exists()


def test_tampered_input_and_wrong_race_outcomes_are_rejected(tmp_path):
    frozen=freeze('1','nar',rows());corrupt=copy.deepcopy(frozen)
    corrupt['inputs']['horses'][0]['pure']=999
    with pytest.raises(ValueError):write_frozen(tmp_path/'bad.json',corrupt)
    with pytest.raises(ValueError):join_outcomes(corrupt,{})
    with pytest.raises(ValueError):join_outcomes(frozen,{'race_id':'2'})
    assert join_outcomes(frozen,{'race_id':'1','actual_corner4':{'1':8}})['research_prediction']==frozen


def test_comparison_output_preserves_formal_marks_and_candidate_membership():
    from core.rank_corner_research import comparison_rows
    hs=rows();hs[-1]['formal_mark']='✓';before=copy.deepcopy(hs)
    result=comparison_rows(freeze('1','nar',hs))
    assert result[-1]['formal_mark']=='✓'
    assert result[-1]['formal_candidate'] is False
    assert result[-1]['ability_gap_from_leader']==20
    assert '正式候補外' in result[-1]['reason']
    assert all(k in result[0] for k in ['A_rank','B_rank','C_rank','D_rank'])
    assert hs==before
