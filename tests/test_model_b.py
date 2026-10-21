from copy import deepcopy
import pytest
from core.model_b import compute

# Synthetic coefficients only: not production or claimed B0-B4 coefficients.
def config():
 return dict(mode='jra',version='test-only',source='synthetic fixture',coefficient_status='exploratory',jockey_weight=2,jockey_prior=.3,jockey_strength=20,training_points={},rest_training_points={},rest_threshold=90,weight_delta_weight=0,venue_points=1,distance_points=1)
def inputs():
 return [dict(no=str(i),pure=100-i,jockey_rate=30,jockey_n=20,venue_top3=True,distance_top3=True) for i in range(1,8)]
def test_no_config_keeps_a():
 assert compute(inputs(),'jra')['status']=='unavailable'
def test_corner_market_results_cannot_change_score_or_hash():
 rows=inputs();before=deepcopy(rows);a=compute(rows,'jra',config())
 for h in rows:h.update(corner=999,odds=1.1,finish=1,pace='H',formal_score=999)
 b=compute(rows,'jra',config())
 assert a==b and before==inputs()
 assert a['top5']==['1','2','3','4','5']
 assert [h['mark'] for h in a['horses'][:5]]==['◎','○','▲','✔','△']
 assert a['horses'][0]['contributions']['condition']==1

def test_missing_does_not_rank_last_or_create_marks():
 rows=inputs();rows[1]['jockey_n']=None;r=compute(rows,'jra',config())
 assert r['status']=='incomplete' and r['horses'][1]['score'] is None
 assert all(h['rank'] is None and h['mark']=='' for h in r['horses'])
def test_mode_and_unsupported_weights_rejected():
 with pytest.raises(ValueError):compute(inputs(),'nar',config())
 with pytest.raises(ValueError):compute(inputs(),'jra',dict(config(),corner_weight=1))

def test_ui_projection_preserves_a_and_fallback():
 from core.model_b_ui import project
 rows=[dict(no=str(i),score=str(100-i),rank=str(i),mark=['◎','○','▲','✔','△','✓','—'][i-1],sort_values={}) for i in range(1,8)]
 before=deepcopy(rows)
 assert project(rows,{'status':'unavailable'})==before
 report=compute(inputs(),'jra',config());shown=project(rows,report)
 assert rows==before and shown[0]['model_a']['mark']=='◎' and shown[5]['mark']=='✓'
 assert all(h['active_model']=='B' for h in shown)
