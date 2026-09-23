import copy
import json
from pathlib import Path
import pandas as pd
import pytest
from core.prediction_table_ui import (JRA_COLUMNS,NAR_COLUMNS,recent_condition_stars,
    prediction_table_records,prediction_table_html,age_text)

def run(label,venue,distance,value):
    return dict(label=label,racecourse=venue,distance=distance,value=value)

@pytest.mark.parametrize('runs,expected',[
 ([run('前走','浦和',1400,54)],{'★':'★ 54','☆':'—'}),
 ([run('前走','川崎',1400,52)],{'★':'—','☆':'☆ 川崎1400 52'}),
 ([run('前走','浦和',1400,54),run('2走前','船橋',1400,49)],{'★':'★ 54','☆':'☆ 船橋1400 49'}),
 ([run('前走','浦和',1500,60),run('4走前','浦和',1400,99)],{'★':'—','☆':'—'}),
 ([run('3走前','浦和',1400,51),run('前走','浦和',1400,54)],{'★':'★ 54 / 51','☆':'—'}),
])
def test_recent_three_stars(runs,expected):
    row={'_past_runs':runs,'star_max_index':999};before=copy.deepcopy(row)
    assert recent_condition_stars(row,{'racecourse':'浦和','distance':1400})==expected
    assert row==before

def test_unknown_condition_or_run_label_is_not_guessed():
    assert recent_condition_stars({'_past_runs':[run('4走前','浦和',1400,99),run('', '浦和',1400,88)]},{'racecourse':'浦和','distance':1400})=={'★':'—','☆':'—'}
    assert recent_condition_stars({'_past_runs':[run('前走','浦和',1400,55)]},{})=={'★':'—','☆':'—'}

@pytest.mark.parametrize('mode,columns',[('jra',JRA_COLUMNS),('nar',NAR_COLUMNS)])
def test_exact_columns_values_and_read_only(mode,columns):
    rows=[dict(number='6',name='境界馬',ability_rank=6,nar_pure_ability_rank=6,nar_pure_ability_score=49.8,
       jra_top5_rank=7,jra_top5_score=98.8,v1_final_mark='▲',馬年齢='牡4',騎手='森泰斗',騎手詳細='森泰斗【乗替】',
       stable_comment_market='<script>原文</script>',odds=1.2,再現性='○',_past_runs=[])]
    before=copy.deepcopy(rows)
    out=prediction_table_records(rows,[],{'racecourse':'浦和','distance':1400},mode,marks={'6':'▲' if mode=='jra' else ''})
    assert list(out[0])==columns
    assert out[0]['年齢']=='4' and out[0]['騎手（継続 / 乗り替わり）']=='森泰斗（乗替）'
    assert out[0]['最終印']==('▲' if mode=='jra' else '—')
    assert out[0]['JRA順位' if mode=='jra' else '純能力順位']==('7' if mode=='jra' else '6')
    assert rows==before
    html=prediction_table_html(out,mode)
    assert html.count('<th ')==len(columns) and '<script>' not in html
    assert 'overflow-x:auto' in html
    rows[0]['odds']=1000
    assert prediction_table_records(rows,[],{'racecourse':'浦和','distance':1400},mode,marks={'6':'▲' if mode=='jra' else ''})==out

def test_real_saved_star_patterns():
    cases=json.loads((Path(__file__).parent/'fixtures/prediction_star_patterns.json').read_text(encoding='utf-8'))
    assert {x['pattern'] for x in cases}=={'same','away','both','none','multiple'}
    assert {x['mode'] for x in cases}=={'jra','nar'}
    for case in cases:
        assert recent_condition_stars(case['row'],case['race_info'])==case['expected']

@pytest.mark.parametrize('fixture,mode',[('purchase_hanshin_20260921_r8.json','jra'),('purchase_nar_snapshot.json','nar')])
def test_real_web_png_table_parity(fixture,mode):
    import app
    from render.mobile_png import _prediction_detail_records
    from core.models import PredictionResult
    f=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf-8'))
    result=PredictionResult(race_mode=mode,race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    before=result.horse_evaluation.copy(deep=True)
    a=app.prediction_detail_records(result);b=_prediction_detail_records(result)
    assert {h['馬番 / 馬名']:h for h in a}=={h['馬番 / 馬名']:h for h in b}
    assert before.equals(result.horse_evaluation)

def test_main_flow_has_one_conclusion_then_table(monkeypatch):
    import app
    from core.models import PredictionResult
    calls=[]
    class Context:
        def __enter__(self): calls.append('audit')
        def __exit__(self,*args): pass
    monkeypatch.setattr(app.st,'expander',lambda *a,**k:Context())
    for name in ['render_race_header','render_jra_top5_result_summary','render_nar_top5_result_summary','render_prediction_detail_table','render_overall_table','render_race_flow','render_horse_summary_cards','render_backtest_reference','render_raw_text_section']:
        monkeypatch.setattr(app,name,lambda *a,_name=name,**k:calls.append(_name))
    monkeypatch.setattr(app,'build_investment_decision',lambda *a,**k:None)
    monkeypatch.setattr(app,'render_investment_decision',lambda *a:pytest.fail('obsolete block rendered'))
    for mode in ['jra','nar']:
        calls.clear();app.render_colab_style_result(PredictionResult(race_mode=mode))
        assert calls[:4]==['render_race_header',f'render_{mode}_top5_result_summary','render_prediction_detail_table','audit']
        if mode=='jra':assert 'render_backtest_reference' not in calls

@pytest.mark.parametrize('mode,fixture',[('jra','purchase_hanshin_20260921_r8.json'),('nar','purchase_nar_snapshot.json')])
def test_actual_conclusion_renderer_single_card(monkeypatch,mode,fixture):
    import app
    from core.models import PredictionResult
    f=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf-8'))
    result=PredictionResult(race_mode=mode,race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    html=[]
    monkeypatch.setattr(app.st,'markdown',lambda value,**kwargs:html.append(value))
    getattr(app,f'render_{mode}_top5_result_summary')(result)
    assert len(html)==1
    assert html[0].count('ka-dashboard-title">今回の結論')==1
    assert '最終購入判断</div>' not in html[0]
    assert '｜' in html[0] and '<details>' in html[0]
