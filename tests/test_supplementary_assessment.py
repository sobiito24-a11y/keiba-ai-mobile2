import copy
import json
import pytest
from core.supplementary_assessment import annotate, KEY, stable_assessment, rest_text, auxiliary_html
from core.horse_card_evaluation import card_evaluation_fields


def row(n, **kw):
    return dict(馬番=n,馬名='表示確認',running_style_market='先',netkeiba_pace='M',netkeiba_corner4_position='先団',netkeiba_corner4_rank=6,**kw)


def test_position_alone_not_development_and_input_immutable():
    rows=[row(1,v1_pace_eval='○',market_ability_rank=1,_days_since_last=323,training_market='B 気合乗る')]
    before=copy.deepcopy(rows)
    for restored in (rows,json.loads(json.dumps(rows))):
        out=annotate(restored,mode='jra')
        assert not out[0][KEY]['development']
        assert card_evaluation_fields(out[0],'jra')[1]==('展開有利','—')
        assert '323日（約10か月半）' in auxiliary_html(out[0],'jra')
    assert rows==before


@pytest.mark.parametrize('value,expected',[(323,'323日（約10か月半）'),(127,'127日（約4か月）'),(None,'データなし'),(-1,'データなし')])
def test_rest(value,expected):
    assert rest_text({'_days_since_last':value})==expected


@pytest.mark.parametrize('comment,grade',[
 ('Q 舞台変わり',''),('距離は合う。状態は良好。','◎'),
 ('距離は合うが状態はもうひとつ。','○'),('距離は合うとは言えない。',''),
 ('状態は良好。展開次第。','○'),('状態は良好。条件は合う。…','○'),
 ('状態は良くない。',''),('', ''),
])
def test_stable_concrete_clauses(comment,grade):
    result=stable_assessment(comment)
    assert result['grade']==grade
    if 'もうひとつ' in comment:assert result['cautions']


def test_complex_development_and_missing_context():
    rows=[row(i,market_ability_rank=i) for i in range(1,6)]
    for h,s in zip(rows,['逃','逃','先','差','追']):
        h.update(running_style_market=s,netkeiba_pace='H')
    rows[3].update(netkeiba_corner4_position='中団',netkeiba_corner4_rank=7)
    out=annotate(rows,mode='jra')
    assert out[3][KEY]['development']=='◎'
    assert not out[0][KEY]['development']
    rows[2]['running_style_market']=''
    assert not annotate(rows,mode='jra')[3][KEY]['development']


def test_nar_reference_no_marks_rank_changes_and_limit():
    rows=[row(i,pure_ability_top5_group=False,market_ability_rank=i+8,距離指数=100,コース指数=100,condition_reason_market='佐賀 1400mの過去走あり',ver3_final_mark='') for i in range(1,10)]
    before=copy.deepcopy(rows)
    out=annotate(rows,mode='nar')
    assert sum(h[KEY]['reference'] for h in out)==1
    assert '能力8位以内基準外' in out[0][KEY]['check_reason']
    for a,b in zip(rows,out):assert {k:v for k,v in b.items() if k!=KEY}==a
    assert rows==before
    rows.append(row(10,pure_ability_top5_group=False,market_ability_rank=18,距離指数=100,コース指数=100))
    assert sum(h[KEY]['reference'] for h in annotate(rows,mode='nar'))==2
    rows[0]['ver3_final_mark']='✓'
    assert not annotate(rows,mode='nar')[0][KEY]['reference']


def test_missing_membership_not_inferred():
    h=row(1,market_ability_rank=9,距離指数=100,コース指数=100)
    assert not annotate([h],mode='nar')[0][KEY]['reference']


def test_source_rest_recovered_only_on_view():
    rows=[row(1)];source=[row(1,_days_since_last=127)]
    out=annotate(rows,source,'jra')
    assert out[0][KEY]['rest_days']==127
    assert '_days_since_last' not in rows[0]


def test_no_worry_is_not_negative():
    assert stable_assessment('不安はない。')['cautions']==[]

def test_outcome_fields_do_not_affect_assessment():
    h=row(1,market_ability_rank=1)
    a=annotate([h],mode='jra')[0][KEY]
    h.update(finish=1,actual_corner4=1,odds=999,payout=99999)
    assert annotate([h],mode='jra')[0][KEY]==a


def test_selected_check_cannot_be_reference_even_without_display_mark():
    h=row(1,pure_ability_top5_group=False,market_ability_rank=9,距離指数=100,コース指数=100,condition_reason_market='佐賀 1400mの過去走あり',nar_check_selected=True)
    assert not annotate([h],mode='nar')[0][KEY]['reference']
