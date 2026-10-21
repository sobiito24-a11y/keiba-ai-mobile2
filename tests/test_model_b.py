from copy import deepcopy
from types import SimpleNamespace
import pandas as pd
import pytest
from core.model_b import predict,load_artifact,freeze,resolve,KEY
from core.model_b_features import extract

def inputs():
 return [dict(no=str(i),ability=100-i,jockey_p=30,jockey_n=20,venue_good=True,exact_good=False,gr='B',daygap=20,weightdiff=0) for i in range(1,8)]

def test_no_config_keeps_a(monkeypatch):
 import core.model_b as b
 monkeypatch.setattr(b,'load_artifact',lambda:None)
 assert predict(inputs(),'jra')['status']=='unavailable'

@pytest.mark.parametrize('mode',['jra','nar'])
def test_outcomes_odds_and_corner_excluded(mode):
 rows=inputs();before=deepcopy(rows);a=predict(rows,mode)
 assert rows==before and a['status']=='ready'
 for h in rows:h.update(corner=999,odds=1.1,popularity=1,finish=1,pace='H',formal_score=999)
 assert predict(rows,mode)==a
 assert a['top5']==['1','2','3','4','5']
 assert [h['mark'] for h in a['horses'][:5]]==['◎','○','▲','✔','△']

def test_missing_major_has_no_rank():
 rows=inputs();rows[1]['ability']=None;r=predict(rows,'jra')
 assert r['status']=='incomplete' and not r['horses']
 rows=inputs();rows[1].update(jockey_p=None,jockey_n=None,gr=None,daygap=None,weightdiff=None)
 r=predict(rows,'jra');assert r['status']=='incomplete'
 assert all(h['rank'] is None and not h['mark'] for h in r['horses'])

def test_projection_keeps_a_and_odds():
 from core.model_b_ui import project
 rows=[dict(no=str(i),score=str(100-i),rank=str(i),mark=['◎','○','▲','✔','△','✓','—'][i-1],odds='8.6',popularity=3,sort_values={}) for i in range(1,8)]
 before=deepcopy(rows);shown=project(rows,predict(inputs(),'jra'))
 assert rows==before and shown[0]['model_a']['mark']=='◎' and shown[5]['mark']=='✓'
 assert all(h['odds']=='8.6' and h['popularity']==3 for h in shown)

def test_frozen_prediction_integrity_and_input_change():
 rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=90-i,_jockey_course_place_rate=30,_jockey_course_starts=20) for i in range(1,8)]
 result=SimpleNamespace(overall_table=pd.DataFrame(rows),debug_info={},race_info={'race_id':'202650010101'},race_mode='nar')
 saved=freeze(result);assert saved['status']=='ready'
 result.debug_info[KEY]=saved
 assert resolve(result)==saved and freeze(result)==saved
 result.overall_table.loc[0,'ver3_ability_core']=999
 assert resolve(result)['status']=='unavailable'
 assert result.debug_info[KEY]==saved
 result.debug_info[KEY]['horses'][0]['score']=999
 assert '整合性' in resolve(result)['fallback_reason']

def test_new_future_race_default_and_historical_safety():
 rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=90-i,_jockey_course_place_rate=30,_jockey_course_starts=20) for i in range(1,8)]
 result=SimpleNamespace(overall_table=pd.DataFrame(rows),debug_info={},race_info={'race_id':'202650102201','race_date':'2026-10-22'},race_mode='nar')
 assert resolve(result)['default_allowed']
 result._material_snapshot_restored=True
 assert not resolve(result)['default_allowed']

def test_b0_keeps_raw_ability_not_clipped_standardized_values():
 rows=inputs()+[dict(inputs()[0],no='8',ability=10000)]
 r=predict(rows,'jra',method='B0')
 assert r['status']=='ready' and r['top5'][0]=='8'
 assert next(h['score'] for h in r['horses'] if h['no']=='8')==10000

def test_prediction_timing_never_backdates_recalculation():
 from core.model_b import capture_context
 from datetime import datetime
 from zoneinfo import ZoneInfo
 result=SimpleNamespace(race_info={'race_date':'2026-10-22','start_time':'15:00'})
 now=datetime(2026,10,22,10,tzinfo=ZoneInfo('Asia/Tokyo'))
 r=capture_context(result,now)
 assert r['generated_before_start'] and not r['prestart_inputs_verified'] and r['prediction_origin']=='new_prediction'
 result._material_snapshot_restored=True
 assert capture_context(result,now)['prediction_origin']=='retrospective_recalculation'
 del result._material_snapshot_restored
 result.race_info['race_date']='2026-10-21'
 assert capture_context(result,now)['prediction_origin']=='retrospective_recalculation'

def test_fresh_parser_date_can_be_frozen_and_verified():
 from datetime import date
 rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=90-i,_jockey_course_place_rate=30,_jockey_course_starts=20) for i in range(1,8)]
 result=SimpleNamespace(overall_table=pd.DataFrame(rows),debug_info={},race_info={'race_id':'202650102201','race_date':date(2026,10,22)},race_mode='nar')
 b=freeze(result)
 assert b['race_date']=='2026-10-22' and b['status']=='ready'
 result.debug_info[KEY]=b
 assert resolve(result)==b
