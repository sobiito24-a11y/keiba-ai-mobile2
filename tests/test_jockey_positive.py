import copy
import pytest
from core.jockey_positive import evaluate,annotate,snapshot,attach

def data(rate=40,runs=20,prev=20,previous_runs=20,status='乗替'):
 return dict(current_jockey_place_rate=rate,current_jockey_sample_size=runs,previous_jockey_place_rate=prev,previous_jockey_sample_size=previous_runs,jockey_change_status=status)

@pytest.mark.parametrize('mode,rate,runs,expected',[('jra',30,20,True),('jra',29,20,False),('jra',35,19,False),('nar',35,20,True),('nar',34,20,False),('nar',50,19,False)])
def test_absolute_boundary(mode,rate,runs,expected):
 assert evaluate(data(rate,runs),mode)['jockey_absolute_positive']==expected

@pytest.mark.parametrize('rate,prev,pn,status,expected',[(35,20,20,'乗替',True),(34,20,20,'乗替',False),(40,20,19,'乗替',False),(40,20,20,'継続',False),(40,None,20,'乗替',False),(None,20,20,'乗替',False)])
def test_upgrade(rate,prev,pn,status,expected):
 for mode in ['jra','nar']:assert evaluate(data(rate,20,prev,pn,status),mode)['jockey_upgrade_positive']==expected

def test_double_count_shadow_and_missing_neutral():
 for mode in ['jra','nar']:
  r=evaluate(data(),mode);assert r['jockey_positive_count']==1 and r['jockey_absolute_positive'] and r['jockey_upgrade_positive']
  r=evaluate(data(None,None,None,None),mode);assert r['jockey_positive_count']==0 and r['jockey_place_rate_delta'] is None and r['jockey_absolute_status']=='neutral_missing'
  rate=29 if mode=='jra' else 34;r=evaluate(data(rate,20,rate-12,20),mode)
  assert r['jockey_shadow_absolute'] and r['jockey_shadow_upgrade'] and not r['jockey_positive']

def test_saved_display_definition_identity_join_and_market_independence():
 rows=[{'馬番':1,'騎手':'甲','_previous_jockey':'乙','jockey_change_market':'乗替','jockey_course_top3_rate':40,'jockey_course_runs':25,'_jockey_course_condition':'浦和1400'},
       {'馬番':2,'騎手':'乙','jockey_course_top3_rate':20,'jockey_course_runs':35,'_jockey_course_condition':'浦和1400'}]
 before=copy.deepcopy(rows);a=annotate(rows,'nar');assert rows==before
 assert a[0]['jockey_upgrade_positive'] and a[0]['jockey_previous_source'].startswith('same_race')
 for h in rows:h.update(odds=999,popularity=1,actual_finish=1,ability_rank=1)
 b=annotate(rows,'nar');assert a[0]['jockey_positive_reason']==b[0]['jockey_positive_reason']
 rows[1]['_jockey_course_condition']='門別1200'
 assert not annotate(rows,'nar')[0]['jockey_upgrade_positive']

def test_jra_caps_and_nar_group_do_not_change():
 import pandas as pd
 from core.models import PredictionResult
 from core.jra_final_mark import apply_final_marks
 from core.nar_top5_order import annotate as order
 rows=[dict(馬番=i,jra_top5_rank=i,_display_jra_top5_rank=i,jra_top5_score=100-i,ability_rank=i,ver3_ability_core=50-i,netkeiba_corner4_rank=i,jockey_course_top3_rate=90,jockey_course_runs=100,jra_training_grade='C',interval_days=100) for i in range(1,7)]
 p=PredictionResult(race_mode='jra',horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows))
 a=apply_final_marks(p,rows)
 assert all(h['_display_jra_final_mark'] not in ('◎','○','▲') for h in a if h['_display_jra_mark_cap'])
 assert a[-1]['_display_jra_final_mark'] not in ('◎','○','▲')
 assert [(h['nar_final_rank'],h['nar_final_mark']) for h in order(rows)]==[(h['nar_final_rank'],h['nar_final_mark']) for h in order(annotate(rows,'nar'))]

def test_snapshot_frozen_roundtrip():
 import json,pandas as pd
 from core.models import PredictionResult
 p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame([{'馬番':1,'jockey_course_top3_rate':40,'jockey_course_runs':30}]))
 attach(p);before=copy.deepcopy(p.debug_info);p.horse_evaluation['jockey_course_top3_rate']=1
 p.debug_info=json.loads(json.dumps(p.debug_info));assert snapshot(p)==before['jockey_positive_evidence']
def test_saved_change_status_precedes_legacy_name_heuristic():
 from core.jockey_positive import inputs
 row={'騎手':'甲','_previous_jockey':'甲騎手','jockey_change_market':'継続','jockey_course_top3_rate':40,'jockey_course_runs':30,'previous_jockey_place_rate':10,'previous_jockey_sample_size':30}
 assert inputs(row)['jockey_change_status']=='継続'
 assert not evaluate(inputs(row),'jra')['jockey_upgrade_positive']

def test_positive_visible_in_web_png_without_rank_change():
 import pandas as pd
 import app
 from core.models import PredictionResult
 from render.mobile_png import _prediction_detail_records
 rows=[{'馬番':i,'馬名':f'horse{i}','ability_rank':i,'ver3_ability_core':50-i,'netkeiba_corner4_rank':i,'jockey_course_top3_rate':40,'jockey_course_runs':30} for i in range(1,7)]
 p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows))
 web=app.prediction_detail_records(p);png=_prediction_detail_records(p)
 assert web==png
 assert all('騎手強' in h['騎手成績'] for h in web)
