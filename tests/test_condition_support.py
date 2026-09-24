import copy,itertools,json
from pathlib import Path
import pytest
from core.condition_support import annotate_condition_support,matching_recent_runs,condition_support_text
from core.prediction_table_ui import display_index_rows,prediction_table_records,index_badges_html

INFO={'racecourse':'浦和','distance':1400}
def run(value,venue='浦和',label='前走',distance=1400):
    return dict(value=value,racecourse=venue,label=label,distance=distance)

def test_star_away_values_ties_missing_scope_and_unchanged_inputs():
    rows=[dict(number=i,distance_index=v,course_index=v,_past_runs=[run(v),run(v,'川崎','2走前'),run(999,'浦和','4走前')]) for i,v in enumerate([92,85,85,83,None],1)]
    before=copy.deepcopy(rows)
    out=display_index_rows(rows,[],INFO,'jra')
    for field in ['distance_index_rank','course_index_rank','star_index_rank','away_same_distance_index_rank']:
        assert [h[field] for h in out]==[1,2,2,4,None]
    assert [h['star_index_value'] for h in out]==[92,85,85,83,None]
    assert rows==before
    assert out[3]['jra_condition_support_count']==0
    assert out[0]['jra_condition_support_shadow']==1
    assert out[0]['jra_condition_support_label']=='条件強'
    assert out[-1]['jra_condition_support_shadow']==0
    assert out[-1]['jra_condition_support_label']=='通常'

def test_same_away_max_no_double_count_or_fourth_start():
    row={'_past_runs':[run(19),run(19,label='2走前'),run(16,label='3走前'),run(99,label='4走前')]}
    same,away=matching_recent_runs(row,INFO)
    assert len(same)==3 and not away
    out=display_index_rows([row],[],INFO,'jra')[0]
    assert out['star_index_value']==19 and out['away_same_distance_index_value'] is None
    row={'_past_runs':[run(99,distance=1600),run(52,'川崎','2走前'),run(49,'船橋','3走前')]}
    out=display_index_rows([row],[],INFO,'jra')[0]
    assert out['star_index_value'] is None and out['away_same_distance_index_value']==52
    assert out['jra_condition_support_count']==1 and not out['jra_condition_attention']
    assert not display_index_rows([row],[],INFO,'nar')[0]['nar_condition_attention']

@pytest.mark.parametrize('mode',['jra','nar'])
@pytest.mark.parametrize('flags',list(itertools.product([False,True],repeat=4)))
def test_exact_support_rules(mode,flags):
    # Three higher index horses give the subject fourth place when the flag is false.
    rows=[]
    for i in range(4):
        values=[100 if i<3 else 110 if flag else 90 for flag in flags]
        rows.append(dict(number=i,distance_index=values[0],course_index=values[1],
          _past_runs=[run(values[2]),run(values[3],'川崎','2走前')]))
    out=display_index_rows(rows,[],INFO,mode)[3]
    assert out[mode+'_condition_support_count']==sum(flags)
    if mode=='jra':
        assert out['jra_condition_support_shadow']==min(1,sum(w for w,f in zip([.5,.25,.25,.5],flags) if f))
        assert out['jra_condition_attention']==(sum(flags)>=2)
        assert out['jra_condition_support_label']==('条件強' if sum(flags)>=3 else '条件注目' if sum(flags)==2 else '通常')
    else:
        assert out['nar_condition_attention']==((flags[2] and (flags[0] or flags[1])) or sum(flags)>=3)
        for key,flag in zip(['distance','course','star','away'],flags):assert out[f'nar_condition_{key}_top3']==flag
        assert 'jra_condition_support_shadow' not in out

@pytest.mark.parametrize('mode',['jra','nar'])
def test_formal_fields_position_bonus_and_odds_not_changed(mode):
    rows=[dict(number=1,jra_top5_score=80,jra_top5_rank=7,v1_final_mark='△',jra_position_bonus=2,
        ability_value=70,ability_rank=6,nar_top5_rank=6,nar_top5_mark='',purchase_grade='C',distance_index=90,
        course_index=91,_past_runs=[run(85)],odds=1.2,weight_change=-3)]
    before=copy.deepcopy(rows);out=display_index_rows(rows,[],INFO,mode)
    assert rows==before
    for key,value in rows[0].items():assert out[0][key]==value
    rows[0].update(odds=999,weight_change=2,finish=1,payout=10000)
    other=display_index_rows(rows,[],INFO,mode)[0]
    for key in out[0]:
        if 'condition_' in key or key.endswith('_rank'):assert out[0][key]==other[key]

@pytest.mark.parametrize('mode,fixture',[('jra','purchase_hanshin_20260921_r8.json'),('nar','purchase_nar_snapshot.json')])
def test_actual_navigation_unchanged_and_watch_separate(monkeypatch,mode,fixture):
    import app,pandas as pd
    from core.models import PredictionResult
    f=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf-8'))
    p=PredictionResult(race_mode=mode,race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    before=app.sorted_display_rows(p)
    purchase=app.build_jra_purchase_navigation(before,race_mode=mode,race_info=p.race_info,saved_rows=f.get('overall',[])) if mode=='jra' else app.nar_comparison_from_result(p)
    out=app.condition_support_rows(p)
    assert len(out)==len(before)
    for old,new in zip(before,out):
        for key in old:
            assert repr(old[key])==repr(new[key]),key
    html=[];monkeypatch.setattr(app.st,'markdown',lambda x,**k:html.append(x))
    app.render_condition_attention(p)
    if html:assert '購入候補への自動追加なし' in html[0]
    after=app.sorted_display_rows(p)
    assert repr(before)==repr(after)
    after_purchase=app.build_jra_purchase_navigation(after,race_mode=mode,race_info=p.race_info,saved_rows=f.get('overall',[])) if mode=='jra' else app.nar_comparison_from_result(p)
    assert repr(purchase)==repr(after_purchase)

def test_table_star_away_compact_and_original_away_details_retained():
    rows=[dict(number=1,_past_runs=[run(85),run(96,'川崎','2走前')])]
    record=prediction_table_records(rows,[],INFO,'jra')[0]
    assert record['★']=='★85 / 1位'
    assert record['☆'].startswith('☆96 / 1位') and '川崎1400 96' in record['☆']
    assert '正式加点なし' in condition_support_text(display_index_rows(rows,[],INFO,'jra')[0],'jra')

@pytest.mark.parametrize('mode',['jra','nar'])
@pytest.mark.parametrize('count,label',[(0,'通常'),(1,'通常'),(2,'条件注目'),(3,'条件強'),(4,'条件強')])
def test_top5_emphasis_is_display_only(mode,count,label):
    if mode=='nar' and count==2:label='通常'
    from core.condition_support import condition_support_display_label,condition_support_html
    row={mode+'_condition_support_count':count,'jra_top5_rank':5,'ability_rank':5,
         'jra_condition_support_shadow':.75,'nar_condition_attention':False}
    before=copy.deepcopy(row)
    assert condition_support_display_label(row,mode)==label
    html=condition_support_html(row,mode)
    assert ('font-weight:600' in html)==(count >= (3 if mode=='nar' else 2))
    if mode=='nar' and count==2:
        assert '条件注目' not in html and '条件強' not in html
        assert 'background:' not in html and '2項目' in html
    assert '上位馬の条件確認' in html
    row.update(jra_top5_rank=6,ability_rank=6)
    outside=condition_support_html(row,mode)
    assert 'font-weight:600' not in outside
    assert '参考条件（候補追加なし）' in outside and label in outside
    assert row['jra_condition_support_shadow']==before['jra_condition_support_shadow']
    assert row['nar_condition_attention'] is False


def test_normal_view_does_not_render_independent_condition_candidates():
    import app,inspect
    source=inspect.getsource(app.render_colab_style_result)
    assert 'render_condition_attention(result)' not in source
    assert 'render_horse_summary_cards(result)' in source
    assert 'render_prediction_detail_table(result)' in source
