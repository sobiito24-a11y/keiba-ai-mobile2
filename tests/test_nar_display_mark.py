import copy
import pandas as pd
import pytest
from core.models import PredictionResult
from core.nar_top5_order import annotate,attach,comparison_fields
from core.nar_display_mark import display_mark,summary_rows

def rows(n=5):
 return [dict(馬番=i,馬名=f'horse{i}',ability_rank=i if i<=5 else 5 if i==6 and n==6 else i,
 ver3_ability_core=70-i,netkeiba_corner4_rank=i) for i in range(1,9)]

@pytest.mark.parametrize('n,marks',[(5,['◎','○','▲','✔︎','△']),(6,['◎','○','▲','✔︎','△','△'])])
def test_formal_marks_and_group(n,marks):
 a=annotate(rows(n));assert [h['nar_final_mark'] for h in a if h['pure_ability_top5_group']]==marks

def test_submarks_not_formal_and_all_horses_in_detail():
 import app
 from render.mobile_png import _prediction_detail_records
 data=rows();data[5]['mark']='☆';data[6]['nar_warning_candidate']=True
 p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(data),overall_table=pd.DataFrame(data))
 # Explicit display rows isolate the saved flag; legacy condition tests cover its production.
 from core.nar_check_selection import select
 a=select(annotate(data));assert display_mark(a[5])=='✓' and display_mark(a[6])==''
 assert len(summary_rows(a))==6 and not a[6]['pure_ability_top5_group'] and a[6]['nar_final_mark']==''
 records=app.prediction_detail_records(p);assert len(records)==8 and records==_prediction_detail_records(p)
 assert all(r['NAR最終順位']=='—' for r in records if r['純能力順位'] in ('6','7','8'))
 c=app.nar_comparison_from_result(p);assert len(c['nar_top5_recommendations'])==5
 assert app.nar_display_mark_from_row(next(h for h in c['rows'] if h['number']=='7'))==''
 html=app.nar_purchase_judgement_html(c);assert '狙い' in html
 assert 'horse6' not in html and 'horse7' not in html

def test_frozen_old_rank_projects_new_mark_without_mutation():
 import app
 p=PredictionResult(race_mode='nar',horse_evaluation=pd.DataFrame(rows(6)),overall_table=pd.DataFrame(rows(6)))
 attach(p)
 for h in p.debug_info['nar_top5_corner_order']['horses']:
  if h['nar_final_rank']==4:h['nar_final_mark']='△'
 before=copy.deepcopy(p.debug_info)
 c=app.nar_comparison_from_result(p)
 assert next(h for h in c['rows'] if h['nar_final_rank']==4)['nar_final_mark']=='✔︎'
 assert p.debug_info==before

def test_legacy_warning_conditions_still_used():
 from core.nar_race_diagnostics import _nar_warning_reason
 assert _nar_warning_reason({'corner4_group':'front'},6,False)
 assert _nar_warning_reason({'has_recent_top3':True},6,False)
 assert _nar_warning_reason({'course_index':80},6,False)
 assert not _nar_warning_reason({},6,False)
 assert not _nar_warning_reason({'corner4_group':'front'},5,False)


def test_missing_saved_submark_is_neutral():
 from core.nar_display_mark import submark
 assert submark({'mark':pd.NA,'nar_warning_candidate':False})==''
