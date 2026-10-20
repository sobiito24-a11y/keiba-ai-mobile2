from copy import deepcopy
from core.candidate_profile import facts,enrich,profile_html

def row(values=(70,65,60)):
 return {'_past_runs':[dict(label=label,race_date=date,value=v,position=1,racecourse='東京',surface='芝',distance=1600,race_id='202605010101') for label,date,v in zip(('前走','2走前','3走前'),('2026-10-01','2026-09-01','2026-08-01'),values)]}

def test_date_gate_and_no_mutation():
 r=row();before=deepcopy(r)
 f=facts(r,{'race_date':'2026-10-18'})
 assert len(f['runs'])==3 and f['state']=='上向き' and r==before
 assert facts(r,{'race_date':'2026-09-01'})['state']=='判定不可'
 assert not facts(r,{})['runs']

def test_stability_is_variance_not_ability_or_wins():
 low=facts(row((10,10,10)),{'race_date':'2026-10-18'});high=facts(row((100,100,100)),{'race_date':'2026-10-18'})
 assert low['stability_stars']==high['stability_stars']==5
 assert low['state']=='横ばい'
 assert facts(row((50,60,70)),{'race_date':'2026-10-18'})['state']=='注意'
 assert facts(row((None,60,70)),{'race_date':'2026-10-18'})['stability_stars'] is None

def test_reference_independent_and_no_odds():
 view=[dict(no=str(i),name='<b>馬</b>',mode='jra',mark='—',ability_rank=str(i),course={'rank':i},distance={'rank':i},training='A') for i in range(1,5)]
 source={h['no']:row() for h in view};before=deepcopy(source)
 enrich(view,source,{'race_date':'2026-10-18'})
 assert sum(h['additional_reference'] for h in view)==2
 assert all(h['mark']=='—' for h in view) and source==before
 assert '<b>馬</b>' not in profile_html(view[0])

def test_nar_never_adds_check_or_reference():
 view=[dict(no='1',name='馬',mode='nar',mark='—',ability_rank='1',course={'rank':1},distance={'rank':1})]
 enrich(view,{'1':row()},{'race_date':'2026-10-18'})
 assert not view[0]['additional_reference'] and view[0]['mark']=='—'

def test_two_of_three_includes_evicted_ability_top5_without_changing_checks():
 from core.candidate_profile import nar_two_of_three
 from core.nar_check_selection import select
 rows=[dict(馬番=1,pure_ability_top5_group=False,market_ability_rank=3,netkeiba_corner4_rank=5),dict(馬番=2,pure_ability_top5_group=True,market_ability_rank=1,netkeiba_corner4_rank=1)]
 before=deepcopy(rows)
 assert nar_two_of_three(rows,1)==['1']
 assert not select(rows)[0]['nar_check_selected']
 assert rows==before
