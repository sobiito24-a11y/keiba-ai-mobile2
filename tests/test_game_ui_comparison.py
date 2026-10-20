import copy
import pytest
from core.game_ui_comparison import comparisons
from core.game_race_ui import build_view,document
from core.prediction_table_ui import prediction_table_records


def field(mode):
 rows=[{'馬番':i,'馬名':f'馬{i}','平均指数':100-i,'netkeiba_corner4_rank':11-i,'jra_top5_rank':i,'jra_top5_score':100-i,'jra_pure_ability_rank':i,'jra_pure_ability_score':100-i,'pure_ability_top5_group':i<=5,'nar_final_rank':i if i<=5 else None,'nar_top5_order_score':100-i,'market_ability_rank':i,'ver3_ability_core':100-i,'距離指数':i*10,'コース指数':i*5,'_past_runs':[{'label':'前走','racecourse':'京都','distance':1400,'value':i*3},{'label':'2走前','racecourse':'東京','distance':1400,'value':i*2}]} for i in range(1,11)]
 records=prediction_table_records(rows,rows,{'racecourse':'京都','distance':1400},mode)
 return rows,build_view(rows,records,rows,mode,{'racecourse':'京都','distance':1400})

@pytest.mark.parametrize('mode,count',[('jra',12),('nar',12)])
def test_tabs_keep_formal_marks_order_and_input(mode,count):
 rows,view=field(mode);before=copy.deepcopy(view)
 tabs=comparisons(view,mode)
 assert len(tabs)==count and tabs[0]['key']=='final'
 assert view==before
 assert all(len(t['cards'])<=5 for t in tabs)
 final=tabs[0]
 from core.game_ui_candidate_evidence import normalized_mark,MARK_ORDER
 assert set(final['rows'])=={i for i,h in enumerate(view) if normalized_mark(h['mark']) in MARK_ORDER}
 assert final['kind']=='candidates' and final['cards']==[]
 for key in ['corner','distance','course','star','away']:
  t=next(t for t in tabs if t['key']==key)
  assert [view[x['index']]['no'] for x in t['cards']]==['10','9','8','7','6']
 assert '今回の結論' in document(view)


def test_missing_indices_not_filled_and_zero_valid():
 _,view=field('jra')
 for h in view:h['course']={'value':None,'rank':None,'badge':'未取得'}
 view[0]['course']={'value':0,'rank':1,'badge':'◎'}
 t=next(t for t in comparisons(view,'jra') if t['key']=='course')
 assert t['eligible']==1 and len(t['cards'])==1 and t['cards'][0]['value']=='0'
 assert '未取得馬は対象外' in t['note']


def test_training_order_missing_excluded():
 _,view=field('jra')
 for h in view:h['training']=''
 for i,v in enumerate(['D','B','A','C','B']):view[i]['training']=v
 t=next(t for t in comparisons(view,'jra') if t['key']=='training')
 assert [x['value'] for x in t['cards']]==['A','B','B','C','D']


def test_six_formal_candidates_not_reclassified():
 _,view=field('nar')
 for h in view:h['mark']='△'
 view[5]['formal_member']=False;view[5]['rank']='6';view[5]['mark']='✓'
 t=comparisons(view,'nar')[0]
 assert t['eligible']==10 and len(t['rows'])==10 and view[5]['formal_member'] is False


def test_frame_attachment_only_adds_fact_and_roundtrips():
 import pandas as pd
 from core.models import PredictionResult
 from core.game_ui_frames import attach_saved_frames
 from core.prediction_history import build_prediction_snapshot
 r=PredictionResult(race_mode='nar',race_info={'race_id':'202655101211'},overall_table=pd.DataFrame([{'馬番':1,'馬名':'確認馬','AI点':42,'最終印':'✓'}]))
 html='<link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id=202655101211"><dl class="HorseList"><dt class="Waku8">8</dt><dt class="Waku_Horse">1</dt><dt class="HorseName"><a>確認馬</a></dt></dl>'
 before=r.overall_table.copy(deep=True)
 out=attach_saved_frames(r,{'newspaper':html})
 assert r.overall_table.equals(before)
 assert out.overall_table.drop(columns=['frame_number']).equals(before)
 assert out.overall_table.iloc[0]['frame_number']==8
 payload=build_prediction_snapshot(out)
 assert payload['horses'][0]['frame_number']==8


def test_tab_switch_does_not_mutate_table_or_rerun_python():
    from pathlib import Path
    source=(Path(__file__).parents[1]/'core/game_ui_assets/race.js').read_text(encoding='utf-8')
    part=source.split('function showMetric(key){',1)[1].split("document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener",1)[0]
    assert 'tbody' not in part and 'setComponentValue' not in source
    assert "showMetric('final')" in source
