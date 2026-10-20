from copy import deepcopy
from core.recent_condition_facts import evaluate, materials
from core.candidate_profile import facts
from core.nar_check_selection import select, resolve_saved
from core.evidence_identity import material_items


def runs():
    return [dict(label=label, date=day, venue=venue, surface=surf, turn=turn, distance=dist, finish=finish)
            for label, day, venue, surf, turn, dist, finish in [
                ('前走','2026-10-01','東京','ダ','左','1400m','2'),
                ('2走前','2026-09-01','中京','ダ','左','1600m','1'),
                ('3走前','2026-08-01','東京','芝','左','1400m','1')]]


def test_conditions_do_not_mix_surface_distance_or_venue():
    info=dict(venue='東京',surface='ダ',turn='左',distance=1400)
    before=deepcopy(info)
    d=evaluate({},info,runs())
    assert d['conditions']['venue']['starts']==1
    assert d['conditions']['turn']['starts']==2
    assert d['conditions']['venue_distance']['starts']==1
    assert len(materials(d))==1
    assert info==before


def test_missing_experience_and_no_placing_are_distinct():
    info=dict(venue='京都',surface='ダ',turn='右',distance=1800)
    assert evaluate({},info,runs())['conditions']['venue']['state']=='absent'
    rs=runs();rs[0]['venue']='京都';rs[0]['finish']='8'
    assert evaluate({},info,rs)['conditions']['venue']['state']=='started'
    rs[1]['surface']=''
    assert evaluate({},info,rs)['conditions']['venue']['state']=='missing'
    assert evaluate({},info,[])['conditions']['venue']['state']=='missing'
    assert evaluate({},dict(info,turn=''),runs())['conditions']['turn']['state']=='missing'


def test_current_and_future_results_are_excluded():
    row={'_past_runs':[dict(race_date='2026-10-21',venue='東京',surface='ダ',distance=1400,position=1),
                       dict(race_date='2026-10-20',venue='東京',surface='ダ',distance=1400,position=2)]}
    p=facts(row,dict(race_date='2026-10-21',venue='東京',surface='ダ',distance=1400))
    assert all(r['date']<'2026-10-21' for r in p['runs'])
    assert p['condition_facts']['conditions']['venue']['top3']==1


def test_saved_check_survives_current_fallback_without_new_rule_change():
    rows=[dict(馬番=i, market_ability_rank=i, nar_pure_ability_rank=i,
               pure_ability_top5_group=i<=5, netkeiba_corner4_rank=10,
               表示印='✓' if i==6 else '') for i in range(1,12)]
    original=deepcopy(rows)
    assert not select(rows)[5]['nar_check_selected']
    after=resolve_saved(rows,rows)
    assert after[5]['nar_check_selected']
    assert after[5]['nar_check_source']=='saved_overall_display_mark'
    assert rows==original
    rows[5]['nar_check_selected']=False
    assert not resolve_saved(rows,rows)[5]['nar_check_selected']


def test_weight_reason_semantic_identity():
    items=material_items(['斤量前走比＋3kg（単独の消し材料ではない）',
                          '斤量前走比＋3kg（注意・強制降格なし）','斤量＋3.0kg'])
    assert len(items)==1 and items[0]['key']=='load_weight_change'
    assert len(items[0]['sources'])==3

def test_research_is_separate_and_missing_is_not_a_demotion():
    from core.recent_condition_research import scenarios
    view=[dict(no=str(i),rank=i,internal_score=10-i,profile={'condition_facts':evaluate({}, {}, [])}) for i in (1,2,3)]
    before=deepcopy(view)
    out=scenarios(view)
    assert out['A']==out['B']==out['C']==['1','2','3']
    assert view==before
    view[1]['internal_score']=None
    assert scenarios(view)['D'] is None
