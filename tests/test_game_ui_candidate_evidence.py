import copy
import pytest
from core.game_ui_candidate_evidence import candidates, evidence, verified_interval, weight_pair
from core.supplementary_assessment import KEY


def horse(mode='jra'):
    return dict(no='1', mode=mode, mark='△', rank='9', score='80', training='B', corner=7,
                ability='90', ability_rank='2', course=dict(value=100,rank=1),
                distance=dict(value=None,rank=1), star=dict(value=0,rank=3),
                away=dict(value=None,rank=None),average=dict(value=88,rank=4))


def row(days=180):
    from datetime import date,timedelta
    return {'_past_runs':[{'race_date':str(date(2026,10,14)-timedelta(days=days)), 'position':3}],
            '_days_since_last':days, '_current_load_weight':56,'_previous_load_weight':58}


def test_all_formal_marks_no_top5_filter_or_badge_confusion():
    marks=['—','✓','✔︎','☆','△','▲','○','◎','△','✓','✔','無印']
    hs=[dict(horse(),no=str(i+1),mark=m,rank=str(i+1),formal_member=i<5) for i,m in enumerate(marks)]
    before=copy.deepcopy(hs)
    g=candidates(hs,'① 最終印候補')
    assert g['eligible']==10 and len(g['rows'])==10
    assert [hs[i]['mark'] for i in g['rows']]==['◎','○','▲','✔︎','✔','△','△','✓','✓','☆']
    assert hs==before and g['cards']==[]


@pytest.mark.parametrize('days,label',[(89,None),(90,'休養90日'),(179,'休養179日'),(180,'長期休養180日'),(323,'長期休養323日')])
def test_confirmed_days_and_weight_no_mutation(days,label):
    h=horse();r=row(days);before=copy.deepcopy((h,r))
    ev=evidence(h,r,{'race_date':'2026-10-14'})
    assert ('純能力2位' in ev['plus'] and 'コース1位' in ev['plus'] and '★3位' in ev['plus'])
    assert '斤量−2.0kg' in ev['plus']
    assert (ev['minus']==[label]) if label else not ev['minus']
    assert '調教B' not in ev['plus'] and (h,r)==before
    assert not any('距離' in x for x in ev['plus'])


def test_missing_conflicting_cancelled_and_future_dates():
    assert verified_interval({'_days_since_last':323},{'race_date':'2026-10-14'})['days'] is None
    r=row();r['_past_runs'].append({'race_date':'2026-10-13','position':'取消'})
    r['_past_runs'].append({'race_date':'2026-10-15','position':1})
    assert verified_interval(r,{'race_date':'2026-10-14'})['days']==180
    r['_past_runs'].append({'race_date':'2026-10-12','position':''})
    assert verified_interval(r,{'race_date':'2026-10-14'})['days'] is None
    r=row();r['_days_since_last']=181
    assert verified_interval(r,{'race_date':'2026-10-14'})['status']=='conflict'


@pytest.mark.parametrize('mode,grade,positive,negative',[('jra','A',True,False),('jra','B',False,False),('jra','C',False,True),('jra','D',False,True),('nar','A',False,False)])
def test_training_is_separate_from_rest(mode,grade,positive,negative):
    h=horse(mode);h['training']=grade
    ev=evidence(h,row(),{'race_date':'2026-10-14'})
    assert ('調教'+grade in ev['plus'])==positive
    assert ('調教'+grade in ev['minus'])==negative
    assert '長期休養180日' in ev['minus']


def test_weights_require_both_actual_values_and_agreement():
    assert weight_pair({'weight_change_market':-2,'斤量':54})['delta'] is None
    assert weight_pair({'_current_load_weight':58,'_previous_load_weight':56,'weight_change_market':-2})['delta'] is None
    r={'_current_load_weight':58,'_previous_load_weight':56}
    assert '斤量＋2.0kg' in evidence(horse(),r,{})['minus']


def test_development_neutral_without_compound_support():
    r={KEY:{'pace':'H'},'netkeiba_running_style':'差','netkeiba_corner4_position':'中団',
       'course_development_mark':'○','course_development_reason':'差し向き'}
    ev=evidence(horse(),r,{})
    assert ev['neutral']==['位置・脚質の参考：H想定／差脚質／4角7番手']
    assert not any('展開' in x for x in ev['plus']+ev['minus'])
    r[KEY].update(development='◎',development_reason='既存の複合根拠')
    ev=evidence(horse(),r,{})
    assert any('条件付き' in x for x in ev['plus']) and not ev['neutral']


@pytest.mark.parametrize('mode,rate,n,expected',[('jra',30,20,True),('jra',29.9,20,False),('nar',34.9,20,False),('nar',35,20,True),('jra',50,19,False)])
def test_existing_jockey_thresholds(mode,rate,n,expected):
    r={'current_jockey_name':'騎手A','current_jockey_place_rate':rate,'current_jockey_sample_size':n}
    assert ('騎手実績良好' in evidence(horse(mode),r,{})['plus'])==expected


def test_upgrade_requires_names_comparable_condition_and_samples():
    r=dict(current_jockey_name='騎手A',previous_jockey_name='騎手B',current_jockey_place_rate=40,
           previous_jockey_place_rate=24,current_jockey_sample_size=20,previous_jockey_sample_size=20,
           jockey_change_status='乗替',jockey_course_condition='京都芝1400',previous_jockey_stat_condition='京都芝1400')
    assert '騎手強化（複勝率＋16pt）' in evidence(horse(),r,{})['plus']
    for key in ['previous_jockey_name','previous_jockey_stat_condition','previous_jockey_sample_size']:
        missing=dict(r);missing.pop(key)
        assert not any('騎手強化' in x for x in evidence(horse(),missing,{})['plus'])
    r['current_jockey_place_rate']=10
    assert not any('騎手' in x for x in evidence(horse(),r,{})['minus'])


def test_materials_outcomes_odds_never_supply_evidence():
    h=horse();h['plus']='架空材料';h['caution']='架空注意'
    r=row();a=evidence(h,r,{'race_date':'2026-10-14'})
    r.update(finish_position=1,payout=100000,actual_odds=100)
    assert evidence(h,r,{'race_date':'2026-10-14'})==a
    assert '架空' not in str(a)
