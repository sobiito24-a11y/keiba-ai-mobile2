from copy import deepcopy
import pytest
from core.race_insight_common import tickets,make_tickets,pace_effect
from core.jra_race_insight import select as jra_select
from core.nar_race_insight import select as nar_select

def horse(no,rank,pure_rank,**kw):
    h=dict(no=str(no),name='テスト'+str(no),mark={1:'◎',2:'○',3:'▲',4:'✔︎',5:'△'}.get(rank,''),
       member=rank<=5,formal_rank=rank,pure_rank=pure_rank,pure=50-pure_rank,conditions=[],
       condition_count=0,pace_effect='neutral',pace='H',risks=[],close_gap=False,gap_to_group=3,
       shift=False,style='先',group='front',corner=rank)
    h.update(kw);return h

def test_nar_ability_leader_remains_opponent_when_mark_is_lower():
    rows=[horse(i,i,6-i) for i in range(1,7)]
    rows[4].update(conditions=['距離1位'],pace_effect='plus')
    before=deepcopy(rows)
    c,o,a=nar_select(rows)
    assert [h['no'] for h in c]==['1','2']
    assert '5' in [h['no'] for h in o]
    assert rows==before
    c2,_,_=jra_select(rows)
    assert c2[0]['no']=='1' # JRA remains anchored to final evaluation.

def test_nar_pure_rank_alone_does_not_promote():
    rows=[horse(i,i,6-i) for i in range(1,7)]
    c,_,_=nar_select(rows)
    assert [h['no'] for h in c]==['1','2']

@pytest.mark.parametrize('select',[jra_select,nar_select])
def test_additional_requires_multiple_independent_reasons(select):
    base=[horse(i,i,i) for i in range(1,6)]
    extra=horse(6,6,6,close_gap=True,gap_to_group=.1,pace_effect='plus')
    assert not select(base+[extra])[2] # Gap + pace without condition not enough.
    extra['conditions']=['距離1位']
    assert select(base+[extra])[2][0]['no']=='6'
    extra['pace_effect']='unknown'
    assert not select(base+[extra])[2]
    extra['pace_effect']='plus';extra['close_gap']=False
    assert not select(base+[extra])[2]

def test_nar_preserves_shift_as_separate_source_no_jra_leak():
    rows=[horse(i,i,i) for i in range(1,6)]+[horse(8,8,9,shift=True,pace='H')]
    assert not nar_select(rows)[2]  # Shadow alone is insufficient.
    rows[-1]['conditions']=['★指数64（3位）']
    rows[-1]['group']='back'
    assert nar_select(rows)[2][0]['no']=='8'
    assert not jra_select(rows)[2]
    rows[-1]['pace']='S'
    assert not nar_select(rows)[2]

@pytest.mark.parametrize('axes,count',[((),20),(('1',),10),(('1','2'),4)])
def test_exact_trio_tickets(axes,count):
    out=tickets(['1','2','3','4','5','6'],axes)
    assert len(out)==count and len({tuple(t) for t in out})==count
    assert all(len(t)==3 and len(set(t))==3 and set(axes)<=set(t) for t in out)

def test_duplicates_invalid_axes_and_short_fields():
    assert tickets(['1','1','2','3'])==[['1','2','3']]
    assert tickets(['1','2'])==[]
    with pytest.raises(ValueError):tickets(['1','2','3'],['9'])

def test_unknown_position_not_imputed_from_style():
    h=horse(6,6,6,style='差',group='unknown',corner=None)
    assert pace_effect(h)=='unknown'

@pytest.mark.parametrize('grade',['D','B'])
def test_existing_navigation_veto(grade):
    rows=[horse(i,i,i,conditions=['距離1位'],pace_effect='plus') for i in range(1,6)]
    bet=make_tickets(rows,rows[:1],dict(purchase_grade=grade))
    assert not bet['combinations']

def test_box_when_axis_evidence_weak_and_missing():
    rows=[horse(i,i,i) for i in range(1,6)]
    b=make_tickets(rows,rows[:2])
    assert b['style']=='BOX' and len(b['combinations'])==10
    rows[0].update(conditions=['コース1位'],pace_effect='plus')
    b=make_tickets(rows,rows[:2])
    assert b['style']=='1頭軸' and b['axes']==['1'] and len(b['combinations'])==6
    rows[1].update(conditions=['距離1位'],pace_effect='plus')
    b=make_tickets(rows,rows[:2])
    assert b['style']=='2頭軸' and len(b['combinations'])==3

def test_generation_is_read_only_and_ignores_current_results_and_markets():
    import pandas as pd
    from core.models import PredictionResult
    from core.race_development import build
    from core.race_insight import generate
    rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=50-i*.1,nar_pure_ability_rank=i,
               nar_final_rank=i,pure_ability_top5_group=i<=5,nar_check_selected=False,
               脚質='先',netkeiba_pace='S',netkeiba_corner4_rank=i,
               netkeiba_corner4_position='先団',距離指数=80 if i==6 else 60,
               コース指数=70,_jockey_course_place_rate=30,class_shift_market='同級')
          for i in range(1,7)]
    r=PredictionResult(race_mode='nar',overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows),
                       debug_info={'old_shadow':{'fixed':1}})
    before=deepcopy(r)
    a=generate(r,rows,build(r))
    assert a['additional']==['6']
    assert r.debug_info==before.debug_info
    pd.testing.assert_frame_equal(r.overall_table,before.overall_table)
    for row in rows:
        row.update(オッズ=.1,人気=1,actual_finish=1,result='won',payoff=999999)
    r.overall_table=pd.DataFrame(rows);r.horse_evaluation=pd.DataFrame(rows)
    b=generate(r,rows,build(r))
    assert a==b
    assert [s['title'] for s in a['sections']]==['展開予想','中心候補','相手本線','追加注目馬','総合考察']
    assert 'tickets' not in a


def test_horse_number_join_for_star_and_saved_probability():
    import pandas as pd
    from core.models import PredictionResult
    from core.race_development import build
    from core.race_insight_common import facts
    rows=[dict(馬番=i,馬名='馬'+str(i),ver3_ability_core=50,nar_pure_ability_rank=i,
         nar_final_rank=i,pure_ability_top5_group=True,nar_check_selected=False,
         _past_runs=[dict(label='前走',racecourse='大井',distance=1400,value=v)])
         for i,v in [(1,90),(2,30)]]
    r=PredictionResult(race_mode='nar',race_info=dict(racecourse='大井',distance=1400),
      overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows),
      debug_info={'nar_winprob_calibration':{'horses':[{'horse_no':'1','nar_win_probability':.7},{'horse_no':'2','nar_win_probability':.3}]}})
    out=facts(r,list(reversed(rows)),build(r))
    one=next(h for h in out if h['no']=='1')
    assert '★指数90（1位）' in one['conditions']
    assert one['probability']==.7


@pytest.mark.parametrize('select', [jra_select, nar_select])
def test_all_marks_preserved_including_tied_sixth_and_outside_checks(select):
    rows=[horse(i,i,i) for i in range(1,9)]
    rows[5].update(member=True, mark='△')
    rows[6]['mark']='✓';rows[7]['mark']='☆'
    before=deepcopy(rows)
    c,o,a=select(rows)
    assert [h['no'] for h in c]==['1','2']
    assert {h['no'] for h in c+o+a}=={str(i) for i in range(1,9)}
    assert len(o)==6 and rows==before


@pytest.mark.parametrize('select', [jra_select, nar_select])
def test_saved_mark_mismatch_is_not_repaired_by_commentary(select):
    rows=[horse(1,1,5,mark='△'),horse(2,2,3,mark='◎'),horse(3,3,1,mark='○')]
    before=deepcopy(rows)
    assert [h['no'] for h in select(rows)[0]]==['2','3']
    assert rows==before


def test_no_mark_no_automatic_center_from_ability():
    rows=[horse(1,1,1,mark='',conditions=['距離1位'])]
    assert not nar_select(rows)[0]
    assert not jra_select(rows)[0]


def test_training_not_repeated_and_comparison_specific():
    from core.race_insight_common import describe
    anchor=horse(1,1,2)
    h=horse(2,2,1,training='C',previous_training='',rest_days=90,
            weight_change=1,jockey='騎手',jockey_change='継続',pace_effect='risk')
    text=describe(h,'jra','center',anchor)
    assert text.count('調教C')==1 and '調教はC' not in text
    assert '上回り' in text and '+1kg' in text and '90日' in text
    assert 'Hペース' in text
    assert '中心に再評価' not in text


def test_unknown_shadow_inputs_do_not_qualify():
    h=horse(8,8,8,shift=True,conditions=['★1位'],group='back',pure=None)
    assert not nar_select([h])[2]


def test_explanation_has_no_purchase_dependency(monkeypatch):
    import pandas as pd
    import core.race_insight_common as common
    import core.jra_purchase_navigator as navigator
    from core.race_insight import generate
    from core.models import PredictionResult
    from core.race_development import build
    def forbidden(*args,**kwargs):raise AssertionError('purchase generation called')
    monkeypatch.setattr(common,'make_tickets',forbidden)
    monkeypatch.setattr(navigator,'build_jra_purchase_navigation',forbidden)
    for mode in ['jra','nar']:
        r=PredictionResult(race_mode=mode,overall_table=pd.DataFrame(),horse_evaluation=pd.DataFrame())
        out=generate(r,[],build(r))
        assert 'tickets' not in out
        text=''.join(p for s in out['sections'] for p in s['paragraphs'])
        assert not any(w in text for w in ['BOX','3連複','1頭軸','2頭軸','購入金額','100円'])


@pytest.mark.parametrize('mark', ['', '無印', '—', '-', '未取得'])
def test_unmarked_text_is_not_a_supporting_mark(mark):
    from core.race_insight_common import has_mark
    rows=[horse(1,1,1),horse(8,8,8,mark=mark)]
    assert not has_mark(rows[1])
    for select in [jra_select,nar_select]:
        c,o,a=select(rows)
        assert '8' not in [h['no'] for h in c+o+a]



def test_summary_highlights_lower_mark_strength_without_promoting():
    from core.race_insight import overall
    lead=horse(1,1,3,training='',rest_days=None,weight_change=0)
    low=horse(6,5,1,conditions=['距離指数75（1位）','コース指数75（1位）','★指数69（1位）'],
              group='back',style='追',corner=8,pace='M',training='',weight_change=0)
    before=deepcopy([lead,low])
    text=''.join(overall([lead],[low],[],'nar'))
    assert '△6' in text and '最終5位' in text
    assert '純能力・距離指数・コース指数・★がいずれも1位' in text
    assert '後方' in text and 'Mペース' in text
    assert [lead,low]==before


def test_top_condition_not_invented_and_secondary_is_brief():
    from core.race_insight_common import leading_features,describe
    h=horse(8,8,8,mark='✓',conditions=['距離指数11（2位）'],
            training='',previous_training='',rest_days=21,weight_change=0,jockey='',jockey_change='')
    assert leading_features(h)==[]
    text=describe(h,'nar','opponent')
    assert '距離指数11（2位）' in text
    assert 'Hペースの先行争い' not in text and len(text)<110


def test_prose_does_not_use_repeated_stock_phrases():
    from core.race_insight_common import describe
    h=horse(4,4,4,training='B',previous_training='',rest_days=90,weight_change=0,
            jockey='',jockey_change='',conditions=['距離指数55（2位）'])
    text=describe(h,'jra','opponent',horse(1,1,1))
    for phrase in ['どこで補えるかが焦点','今回条件での指数に裏付けがある','間隔を踏まえた動きにも目を向けたい']:
        assert phrase not in text



def test_opponent_groups_use_membership_not_rank_or_mark_and_preserve_text():
    from core.race_insight import opponent_groups
    from core.race_insight_common import section_html
    horses=[horse(3,3,3),horse(6,6,5,member=True,mark='△'),
            horse(7,2,7,member=False,mark='✔︎'),horse(8,8,8,mark='✓')]
    paragraphs=['既存本文'+str(i) for i in range(4)]
    before=deepcopy(horses)
    groups=opponent_groups(horses,paragraphs)
    assert groups[0]['horse_numbers']==['3','6']
    assert groups[1]['horse_numbers']==['7','8']
    assert [p for g in groups for p in g['paragraphs']]==paragraphs
    html=section_html([dict(title='相手本線',paragraphs=paragraphs,groups=groups)])
    assert html.count('<h4>')==1 and html.count('<h5 ')==2
    assert all(html.count(p)==1 for p in paragraphs)
    assert horses==before


def test_no_reference_group_when_all_opponents_are_formal():
    from core.race_insight import opponent_groups
    from core.race_insight_common import section_html
    groups=opponent_groups([horse(3,3,3)],['説明'])
    assert len(groups)==1
    assert 'その他の印付き馬' not in section_html([dict(title='相手本線',paragraphs=['説明'],groups=groups)])
    assert opponent_groups([],[])==[]
