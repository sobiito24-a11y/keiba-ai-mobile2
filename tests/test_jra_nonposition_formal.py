"""Fresh JRA scores omit position; historical and NAR paths stay unchanged."""
import copy
import pandas as pd
import pytest
from core.v1_logic import assign_jra_top5_scores_and_marks, build_v1_evaluations
from core.jra_formal_snapshot import freeze_fresh_formal, saved_formal_comparison
from core.models import PredictionResult

@pytest.mark.parametrize('pace,corner',[('○',1),('○',4),('△',6),('×',15),('—',None)])
def test_nonposition_score_and_reference_fields(pace,corner):
    h=dict(number=1,jra_pure_ability_score=80,v1_reproducibility='A',v1_pace_eval=pace,training_grade='B',netkeiba_corner4_rank=corner,_v1_ability_rank=1)
    hs=[h];assign_jra_top5_scores_and_marks(hs,position_scoring=False)
    assert h['jra_top5_score']==82.25
    assert h['jra_pace_bonus']==h['jra_position_bonus']==0
    assert h['netkeiba_corner4_rank']==corner
    assert '参考・スコア補正なし' in h['v1_final_reason']

def example(mode='jra'):
    rows=[dict(number=str(i),name=f'馬{i}',market_ability_score=80-i,market_ability_rank=i,netkeiba_corner4_rank=i,training_grade='B',pace_mark_market='○') for i in range(1,8)]
    return PredictionResult(race_mode=mode,race_info={'race_id':'202608040511','surface':'芝'},horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows))

def test_fresh_formal_has_new_version_and_deterministic_ties():
    r=example();before=r.overall_table.copy(deep=True)
    freeze_fresh_formal(r,position_scoring=False)
    s=saved_formal_comparison(r)
    assert s['formal_score_version']=='jra_nonposition_v1_20261014'
    for h in s['rows']:
        assert h['jra_top5_score']==pytest.approx(h['jra_pure_ability_score']+h['jra_repro_bonus']+h['jra_training_bonus']+h['jra_state_bonus'])
        assert h['jra_position_bonus']==h['jra_pace_bonus']==0
    pd.testing.assert_frame_equal(before,r.overall_table)
    copied=copy.deepcopy(s)
    freeze_fresh_formal(r,position_scoring=True)
    assert saved_formal_comparison(r)==copied

def test_old_saved_formal_never_rewritten():
    r=example();freeze_fresh_formal(r)
    old=copy.deepcopy(r.debug_info)
    freeze_fresh_formal(r,position_scoring=False)
    assert r.debug_info==old

def test_nar_position_toggle_no_effect():
    r=example('nar');rows=r.overall_table.to_dict('records')
    assert build_v1_evaluations(rows,'nar',jra_position_scoring=False)==build_v1_evaluations(rows,'nar')
    old=copy.deepcopy(r.debug_info);freeze_fresh_formal(r,position_scoring=False);assert r.debug_info==old

def test_actual_fresh_entry_uses_new_policy():
    from pathlib import Path
    source=(Path(__file__).parents[1]/'core/jra_predictor.py').read_text(encoding='utf-8')
    assert 'freeze_fresh_formal(result, position_scoring=False)' in source

def test_snapshot_keeps_frozen_new_values():
    import io,json,zipfile
    from core.prediction_history import prediction_zip_bytes
    r=example();freeze_fresh_formal(r,position_scoring=False)
    saved=saved_formal_comparison(r)
    payload=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(r))).read('prediction.json'))
    assert payload['jra_formal_comparison_snapshot']==saved


def test_obstacle_policy_is_not_changed_without_validation():
    a=example();a.race_info['surface']='障';b=copy.deepcopy(a)
    freeze_fresh_formal(a);freeze_fresh_formal(b,position_scoring=False)
    assert a.debug_info==b.debug_info


def test_new_saved_values_override_conflicting_legacy_table_for_ui():
    import app
    r=example();freeze_fresh_formal(r,position_scoring=False)
    expected={str(h['number']):(h['jra_top5_rank'],h['jra_top5_score']) for h in saved_formal_comparison(r)['rows']}
    r.horse_evaluation['jra_top5_score']=999
    r.horse_evaluation['jra_top5_rank']=99
    r._jra_snapshot_restored=True
    rows=app.jra_enriched_display_rows(r)
    for h in rows:
        assert (h['_display_jra_top5_rank'],h['_display_jra_top5_score'])==expected[str(h['number'])]
