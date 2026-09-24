import copy
import pytest
from core.position_signals import corner4_rank,jra_position_bonus,nar_position_reference,NAR_CORNER4_WIN_RATE_REFERENCE
from core.prediction_table_ui import (display_index_rows,netkeiba_position_text,position_display_text,sex_age_text,load_weight_text,prediction_table_records,prediction_table_html,index_badges_html)
from core.v1_logic import build_v1_evaluations

@pytest.mark.parametrize('rank,bonus',[(1,2),(2,2),(3,1.5),(4,1.5),(5,0),(10,0),(None,0),(0,0),(-1,0),(1.5,0),(True,0),('bad',0)])
def test_jra_position_exact(rank,bonus):
    row={'netkeiba_corner4_rank':rank}
    assert jra_position_bonus(row)==bonus
    assert jra_position_bonus(row,{'race_name':'障害未勝利'})==0
    assert jra_position_bonus(row,{'race_data':'障3100'})==0

@pytest.mark.parametrize('rank',range(1,11))
def test_nar_reference_only(rank):
    row={'netkeiba_corner4_rank':rank,'ability_value':49.8,'ability_rank':6,'odds':1.0}
    before=copy.deepcopy(row)
    fields=nar_position_reference(row)
    assert fields['nar_position_bonus_shadow']==(4 if rank==1 else 0)
    assert fields['nar_corner4_reference_win_rate']==NAR_CORNER4_WIN_RATE_REFERENCE.get(rank)
    assert before==row
    row['odds']=999
    assert fields==nar_position_reference(row)
    assert nar_position_reference({})=={'nar_position_bonus_shadow':0.,'nar_corner4_reference_win_rate':None}

@pytest.mark.parametrize('mode',['jra','nar'])
def test_pipeline_only_allowed_bonus(mode):
    rows=[dict(number=str(n),market_ability_score=80-n,market_ability_rank=n,netkeiba_corner4_rank=6-n,training_grade='B',pace_mark_market='○') for n in range(1,6)]
    old=copy.deepcopy(rows)
    absent=[{k:v for k,v in r.items() if k!='netkeiba_corner4_rank'} for r in rows]
    baseline=build_v1_evaluations(absent,mode,{'surface':'芝'})['rows']
    current=build_v1_evaluations(rows,mode,{'surface':'芝'})['rows']
    assert rows==old
    for before,after in zip(baseline,current):
        for key in ('ability_value','ability_rank','v1_reproducibility','v1_pace_eval','v1_state_eval','jra_repro_bonus','jra_pace_bonus','jra_training_bonus','jra_state_bonus'):
            assert before[key]==after[key]
        if mode=='jra':
            assert after['jra_top5_score']==pytest.approx(before['jra_top5_score']+jra_position_bonus(after))
            assert 'netkeiba4角' in after['v1_final_reason']
        else:
            assert {k:v for k,v in after.items() if k!='netkeiba_corner4_rank'}==before

@pytest.mark.parametrize('path,rank,expected',[
 ('逃げ→逃げ→逃げ',1,'逃げ → 逃げ → 逃げ / 4角1番手'),
 ('先団 → 中団 → 先団',None,'先団 → 中団 → 先団'),
 (None,2,'4角2番手'),(None,None,'—')])
def test_positions(path,rank,expected):
    row={'netkeiba_position_path':path,'netkeiba_corner4_rank':rank}
    assert netkeiba_position_text(row)==expected
    if rank:
        assert f'4角参考勝率 {NAR_CORNER4_WIN_RATE_REFERENCE[rank]:.1f}%' in position_display_text(row,'nar')
    assert '参考勝率' not in position_display_text(row,'jra')


def test_competition_rank_and_no_mutation():
    rows=[dict(number=i,distance_index=v,course_index=v) for i,v in enumerate([75,70,70,50,None],1)]
    before=copy.deepcopy(rows);out=display_index_rows(rows)
    for key in ['distance_index_rank','course_index_rank']:
        assert [r[key] for r in out]==[1,2,2,4,None]
    assert rows==before
    assert [r['distance_index'] for r in out]==[75,70,70,50,None]

@pytest.mark.parametrize('row,expected',[
 ({'性齢':'牡4','age':4},'牡4'),({'sex_age':'牝3'},'牝3'),({'age':5},'5歳'),({},'—')])
def test_sex_age(row,expected):
    assert sex_age_text(row)==expected

@pytest.mark.parametrize('row,expected',[
 ({'斤量':56,'斤量増減':0},'56.0kg（±0）'),({'weight':57,'weight_change':1},'57.0kg（+1.0）'),
 ({'weight':54,'weight_change':-2},'54.0kg（-2.0）'),({'斤量':56},'56.0kg'),
 ({'斤量詳細':'56.0kg（+1.0）'},'56.0kg（+1.0）'),({},'—')])
def test_weight(row,expected):
    assert load_weight_text(row)==expected

@pytest.mark.parametrize('mode',['jra','nar'])
def test_table_badges_sticky_and_cards(mode):
    row=dict(number=1,name='確認馬',ability_rank=1,market_ability_score=75,netkeiba_corner4_rank=1,netkeiba_position_path='逃げ→逃げ→逃げ',distance_index=75,course_index=75,性齢='牡4',斤量=56,斤量増減=0)
    records=prediction_table_records([row],[],{},mode)
    keys=list(records[0]);assert keys[keys.index('騎手成績')+1]=='斤量'
    assert records[0]['距離']=='75 / 1位'
    assert '4角1番手' in records[0]['netkeiba想定']
    if mode=='nar': assert '4角参考勝率 28.2%' in records[0]['netkeiba想定']
    html=prediction_table_html(records,mode)
    assert html.count('position:sticky')==2
    assert 'background:#fff' in html and 'font-size:12px' in html and 'padding:4px 6px' in html
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    assert soup.th.text=='馬番 / 馬名'
    assert '1 確認馬' in soup.td.text
    badge=index_badges_html(display_index_rows([row])[0])
    assert badge.count('class="index-badge"')==4 and '75' in badge and '1位' in badge

@pytest.mark.parametrize('mode,fixture',[('jra','purchase_hanshin_20260921_r8.json'),('nar','purchase_nar_snapshot.json')])
def test_real_card_fields_and_snapshot_read_only(monkeypatch,mode,fixture):
    import json
    from pathlib import Path
    import pandas as pd
    import app
    from core.models import PredictionResult
    from bs4 import BeautifulSoup
    f=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf-8'))
    p=PredictionResult(race_mode=mode,race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    before=p.horse_evaluation.copy(deep=True);overall=p.overall_table.copy(deep=True)
    html=[]
    monkeypatch.setattr(app.st,'markdown',lambda value,**k:html.append(value))
    monkeypatch.setattr(app.st,'subheader',lambda *a,**k:None)
    getattr(app,f'render_{mode}_top5_result_summary')(p)
    soup=BeautifulSoup(html[0],'html.parser')
    for card in soup.select('.recommended-horse'):
        assert 'netkeiba想定' in card.text and '複勝率' in card.text
        assert len(card.select('.index-badge'))==4
        assert '条件材料' in card.text
        if mode=='jra':assert '位置bonus' in card.text
        if mode=='nar':assert 'shadow' not in card.text
        else:assert '正式加点なし' in card.text
    html.clear();app.render_horse_summary_cards(p)
    assert len(html)==len(p.horse_evaluation)
    for markup in html:
        assert markup.index('ka-horse-title-line')<markup.index('horse-position-detail')
        assert 'netkeiba想定' in markup and 'index-badge' in markup
    pd.testing.assert_frame_equal(before,p.horse_evaluation)
    pd.testing.assert_frame_equal(overall,p.overall_table)
