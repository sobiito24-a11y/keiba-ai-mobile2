from core.candidate_summary import interval_label,distance_label,summary
from core.recent_condition_facts import evaluate

def test_interval_calendar_weeks():
    assert interval_label(dict(rest_days=7,runs=[dict(date='2026-10-11')]),'jra')=='連闘'
    assert interval_label(dict(rest_days=14,runs=[dict(date='2026-10-04')]),'jra')=='中1週'
    assert interval_label(dict(rest_days=5,runs=[dict(date='2026-10-13')]),'nar')=='5日（短期連戦）'
    assert interval_label({},'jra')=='間隔不明'

def test_distance_surface_and_unknown():
    info=dict(venue='京都',surface='芝',distance=2000)
    runs=[dict(venue='東京',surface='芝',distance=2000,finish='2')]*3
    facts=evaluate({},info,runs)
    assert facts['conditions']['distance']['state']=='placed'
    assert facts['conditions']['venue_distance']['state']=='absent'
    assert distance_label(dict(condition_facts=facts))=='同距離 3着内'
    assert evaluate({},info,[])['conditions']['distance']['state']=='missing'
    assert evaluate({},info,[dict(r,surface='ダ') for r in runs])['conditions']['distance']['state']=='absent'

def test_stars_reused_not_derived():
    h=dict(mode='nar',profile=dict(stability_stars=3))
    assert '近走 ★★★☆☆' in summary(h)
    assert not any('調教' in v for v in summary(h))
