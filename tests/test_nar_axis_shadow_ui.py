"""NAR axis diagnostics stay frozen in exports, never in normal UI/nav."""
import copy
import json
import pandas as pd
import pytest
from core.models import PredictionResult
from core.axis_confidence_v2 import KEY, attach, snapshot, restore


def sample():
    rows=[dict(馬番=i,馬名=f'H{i}',ability_rank=i,ver3_ability_core=80-i,
               平均指数=60-i,netkeiba_corner4_rank=3,_jockey_course_place_rate=40)
          for i in range(1,11)]
    r=PredictionResult(race_info={'race_id':'202644100610'},race_mode='nar',horse_evaluation=pd.DataFrame(rows),overall_table=pd.DataFrame(rows),attention_horses=['1番 H1','2番 H2','3番 H3','4番 H4'])
    r.debug_info['nar_winprob_calibration']={'horses':[dict(horse_no=str(i),nar_win_probability=.20 if i<=2 else .075) for i in range(1,11)]}
    attach(r)
    assert [h['axis_confidence'] for h in snapshot(r)['horses'][:2]]==['A','B']
    return r


def test_nar_axis_hidden_all_normal_views_and_preserved_snapshot(monkeypatch):
    import app
    from render.mobile_png import _Canvas, _prediction_detail_records
    from core.prediction_history import build_prediction_snapshot
    r=sample();before=copy.deepcopy(r.debug_info);output=[]
    class Sink:
        def markdown(self,value,**kwargs):output.append(value)
        def subheader(self,value,**kwargs):output.append(value)
    monkeypatch.setattr(app,'st',Sink())
    app.render_nar_top5_result_summary(r)
    app.render_prediction_detail_table(r)
    app.render_horse_summary_cards(r)
    app.render_race_summary(r)
    class PngSink:
        def section(self,*args,**kwargs):pass
        def horse_card(self,title,lines,**kwargs):output.extend([title,*lines])
    _Canvas.draw_prediction_conclusion(PngSink(),r)
    html=''.join(output)
    for forbidden in ['軸A','軸B','2頭軸検討可能','相手軸候補','軸にはしない（C）','軸判定：未取得']:
        assert forbidden not in html
    assert '✓' in html and 'H6' in html
    assert app.prediction_detail_records(r)==_prediction_detail_records(r)
    payload=build_prediction_snapshot(r)
    assert payload[KEY]==before[KEY] and r.debug_info==before
    restored=sample();restore(restored,json.loads(json.dumps({KEY:payload[KEY]})))
    assert snapshot(restored)==before[KEY]
    # Poison only research diagnostics: official output and purchase must ignore it.
    formal=copy.deepcopy(app.nar_comparison_from_result(r))
    for h in r.debug_info[KEY]['horses']:h['axis_confidence']='A'
    r.debug_info[KEY]['race_axis_state']='research-only'
    assert app.nar_comparison_from_result(r)==formal


def test_dashboard_keiba_roundtrip_retains_shadow():
    module=pytest.importorskip('core.prediction_snapshot')
    r=sample()
    event=module.load_keiba(module.keiba_bytes(module.build_event_snapshot([module.race_snapshot_from_result(r)])))
    restored=module.restore_prediction_result(event['races'][0])
    assert snapshot(restored)==snapshot(r)
