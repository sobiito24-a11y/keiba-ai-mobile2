from copy import deepcopy
import pytest
from core.nar_display_score import project,BASELINES

@pytest.mark.parametrize('model',list(BASELINES))
def test_fixed_scale_order_ties_and_missing(model):
 values=[-100,-1,-.2,0,0,.1,1,100]
 out=[project(v,model)['value'] for v in values]
 assert out==sorted(out) and out[3]==out[4]
 assert project(None,model,status='outside_group')['status']=='not_calculated'
 assert project(None,model)['status']=='missing'
 assert project(None,model,status='invalid_data')['status']=='error'
 assert project(1,'unknown')['value'] is None
 assert project(float('nan'),model)['raw'] is None
 assert project(100,model)['raw']==100

def test_jra_top5_only_missing_marks_filled_and_reason_preserved():
 from tests.test_jra_final_mark import result
 from core.jra_rank_display import official_jra_result_rows
 p=result(days=0,grade='A')
 for table in [p.overall_table,p.horse_evaluation]:table.loc[table.馬番==5,'v1_final_mark']=''
 before=deepcopy(p)
 rows=official_jra_result_rows(p,p.overall_table.to_dict('records'));by={h['馬番']:h for h in rows}
 assert by[5]['_display_jra_final_mark']=='△' and '正式Top5補完' in by[5]['_display_jra_mark_reasons']
 assert by[6]['_display_jra_final_mark']=='✔︎' and by[8]['_display_jra_final_mark']=='✓'
 assert p.overall_table.equals(before.overall_table)

def test_ages_and_hidden_score_kept():
 from core.game_race_ui import build_view
 from core.prediction_table_ui import prediction_table_records
 rows=[dict(馬番=1,馬名='馬A',性齢='牡3',nar_top5_order_score=10,nar_top5_order_version='nar_f2_actual_course_v1_20261020',nar_final_rank=8,pure_ability_top5_group=False),dict(馬番=2,馬名='馬B',性齢='牝4')]
 view=build_view(rows,prediction_table_records(rows,rows,{},'nar'),rows,'nar')
 a=next(h for h in view if h['no']=='1')
 assert a['internal_score']==10 and a['display_scale']['value'] is not None
 assert a['age3_mixed']
