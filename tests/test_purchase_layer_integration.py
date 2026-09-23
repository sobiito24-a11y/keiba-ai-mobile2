import copy
import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from core.models import PredictionResult
from core.jra_purchase_navigator import build_jra_purchase_navigation
from core.nar_purchase_judgement import annotate_nar_purchase_judgement
from render import mobile_png
from tests.test_jra_purchase_final_table import _rows
from tests.test_nar_purchase_final_layer import _strong


@pytest.mark.parametrize('training,pace,repro,grade', [('B','○','○','A'),('B','','','B'),('C','','','C')])
def test_purchase_grade_thresholds_leave_prediction_unchanged(training,pace,repro,grade):
    rows=_rows()
    rows[0].update(jra_training_grade=training,v1_pace_eval=pace,v1_reproducibility=repro)
    before=copy.deepcopy(rows)
    nav=build_jra_purchase_navigation(rows,race_mode='jra',race_info={'surface':'芝'})
    assert nav['purchase_grade']==grade
    assert rows==before


def test_purchase_grade_d_missing_and_jump_are_safe():
    rows=_rows()
    for row in rows: row['v1_final_mark']=''
    assert build_jra_purchase_navigation(rows,race_mode='jra',race_info={'surface':'芝'})['purchase_grade']=='D'
    for info,label in [({},'判定材料不足'),({'surface':'障害'},'対象外')]:
        nav=build_jra_purchase_navigation(_rows(),race_mode='jra',race_info=info)
        assert nav['purchase_grade']=='D' and nav['purchase_label']==label


def test_nullable_support_and_layoff_only_affect_purchase_confidence():
    rows=_rows()
    rows[0].update(v1_reproducibility=pd.NA,shadow_reproducibility='○',v1_pace_eval=float('nan'),shadow_pace_eval='○')
    nav=build_jra_purchase_navigation(rows,race_mode='jra',race_info={'surface':'芝'})
    assert nav['purchase_grade']=='A'
    rows[0]['_days_since_last']=90
    before=copy.deepcopy(rows)
    rested=build_jra_purchase_navigation(rows,race_mode='jra',race_info={'surface':'芝'})
    assert rested['axis_candidate']['support_score']==nav['axis_candidate']['support_score']-1.5
    assert rested['buy_groups']==nav['buy_groups']
    assert json.dumps(rows,default=str,sort_keys=True)==json.dumps(before,default=str,sort_keys=True)


def test_venue_profiles_do_not_change_nar_grade_or_prediction():
    results=[]
    for venue in ['水沢','高知','船橋']:
        rows=_strong();before=copy.deepcopy(rows)
        results.append(annotate_nar_purchase_judgement(rows,race_info={'venue':venue}))
        for old,new in zip(before,rows):
            assert all(new[key]==value for key,value in old.items())
    for key in ['race_purchase_judgement','race_purchase_score','axis_support_score','trusted_partner_count','recommended_ticket_mode']:
        assert len({r[key] for r in results})==1


def test_actual_snapshot_web_png_use_entire_field_and_same_marks(monkeypatch):
    import app
    fixture=json.loads((Path(__file__).parent/'fixtures/purchase_hanshin_20260921_r8.json').read_text(encoding='utf-8'))
    result=PredictionResult(race_mode='jra',race_info=fixture['race_info'],horse_evaluation=pd.DataFrame(fixture['rows']),overall_table=pd.DataFrame(fixture['rows']))
    before=result.horse_evaluation.copy(deep=True)
    def nav(rows):
        return build_jra_purchase_navigation(rows,race_mode='jra',race_info=result.race_info,saved_rows=result.overall_table.to_dict('records'))
    web=nav(app.jra_enriched_display_rows(result));png=nav(mobile_png._jra_purchase_rows(result))
    assert web==png
    assert [h['number'] for h in web['buy_groups']['狙い']]==['7','12']
    assert [h['number'] for h in web['hole_attention']]==['10']
    cards=[]
    original=mobile_png._Canvas.horse_card
    def capture(self,title,lines,**kwargs):
        cards.append((title,list(lines)))
        return original(self,title,lines,**kwargs)
    monkeypatch.setattr(mobile_png._Canvas,'horse_card',capture)
    data=mobile_png.render_mobile_png(result)
    image=Image.open(BytesIO(data));image.verify()
    title,lines=cards[0]
    assert not any('最終購入判断' in t for t,_ in cards)
    assert web['purchase_grade'] in title
    assert '狙い：7 レッドフレーザー / 12 リリーサンダー' in lines
    assert '穴注意：10 エアフォースワン' in lines
    pd.testing.assert_frame_equal(result.horse_evaluation,before)


def test_nar_png_purchase_card_keeps_original_prediction(monkeypatch):
    rows=[{'馬番':r['number'],'馬名':r['name'],'market_ability_score':r['nar_pure_ability_score'],'market_ability_rank':r['nar_pure_ability_rank'],'condition_fit_mark':'★','_estimated_position_corner4_label':'先団'} for r in _strong()]
    result=PredictionResult(race_mode='nar',race_info={'venue':'水沢','surface':'ダート'},overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows))
    before=result.overall_table.copy(deep=True);cards=[]
    original=mobile_png._Canvas.horse_card
    def capture(self,title,lines,**kwargs):
        cards.append((title,list(lines)))
        return original(self,title,lines,**kwargs)
    monkeypatch.setattr(mobile_png._Canvas,'horse_card',capture)
    Image.open(BytesIO(mobile_png.render_mobile_png(result))).verify()
    assert '｜' in cards[0][0]
    assert any(line.startswith('軸候補：') for line in cards[0][1])
    assert any(line.startswith('本線：') for line in cards[0][1])
    assert not any('JRA 最終購入判断' in title for title,_ in cards)
    pd.testing.assert_frame_equal(result.overall_table,before)


def test_actual_nar_web_png_purchase_parity_with_different_saved_tables():
    import app
    f=json.loads((Path(__file__).parent/'fixtures/purchase_nar_snapshot.json').read_text(encoding='utf-8'))
    result=PredictionResult(race_mode='nar',race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f['overall']))
    original=mobile_png._nar_comparison_rows(result)
    assert mobile_png._nar_purchase_summary(result)==app.nar_comparison_from_result(result)['race_purchase']
    assert mobile_png._nar_comparison_rows(result)==original
