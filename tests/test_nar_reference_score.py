from copy import deepcopy
import pytest
from core.nar_reference_score import reference
from core.nar_top5_order import MODEL_VERSION,ABILITY_COEF,CORNER4_COEF
from core.nar_display_score import project

def test_same_equation_scale_and_no_mutation():
 rows=[dict(nar_top5_order_version=MODEL_VERSION,nar_top5_order_status='outside_group',nar_top5_order_pure=70,netkeiba_corner4_rank=4,nar_final_rank=8,nar_final_mark='✓')]
 before=deepcopy(rows);r=reference(rows[0],rows)
 expected=ABILITY_COEF*70+CORNER4_COEF*4
 assert r['kind']=='reference' and r['value']==expected and rows==before
 assert project(expected,MODEL_VERSION)['value']==project(r['value'],MODEL_VERSION)['value']
 official=dict(rows[0],nar_top5_order_score=expected)
 assert reference(official)['kind']=='official'

@pytest.mark.parametrize('change',[{'nar_top5_order_version':'unknown'},{'nar_top5_order_pure':None},{'netkeiba_corner4_rank':None},{'netkeiba_corner4_rank':2.5}])
def test_missing_never_uses_b(change):
 row=dict(nar_top5_order_version=MODEL_VERSION,nar_top5_order_status='outside_group',nar_top5_order_pure=70,netkeiba_corner4_rank=4,model_b_score=99);row.update(change)
 assert reference(row)['value'] is None

def test_incompatible_official_scale_rejected():
 row=dict(nar_top5_order_version=MODEL_VERSION,nar_top5_order_status='outside_group',nar_top5_order_pure=70,netkeiba_corner4_rank=4)
 assert reference(row,[dict(row,nar_top5_order_score=99)])['value'] is None
