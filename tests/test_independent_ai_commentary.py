import copy
import pytest
from tests.test_independent_ai_v3 import prediction,quote,NOW
from core.independent_ai_commentary import build,review,decision_text
from core.independent_ai_odds import evaluate
from core.independent_ai_registry import freeze,settle

@pytest.mark.parametrize('mode',['jra','nar'])
def test_evidence_text_preserves_predictions(mode):
    p=prediction(mode);before=copy.deepcopy(p)
    ctx={'pace':'H','horses':{str(h['horse_no']):{'formal_rank':10,'style':'先'} for h in p['horses']}}
    c=build(p,ctx)
    assert p==before and c==build(p,ctx)
    text=''.join(c['paragraphs'])
    assert p['horses'][0]['name'] in text and '仮説' in text and '正式順位10位' in text
    assert '未校正' in text and '純能力' in text

def test_missing_position_no_invented_path():
    p=prediction()
    for h in p['input']['horses']:h['corner4']=None
    c=build(p)
    assert c['checks']==[] and '具体的仮説は保留' in ''.join(c['paragraphs'])

def test_no_market_claim_without_complete_valid_prices():
    p=prediction();d=evaluate(p,quote(),NOW)
    assert '市場と予測' not in ''.join(decision_text(p,d))

def test_review_retains_saved_text_and_unknowns():
    p=prediction();c=build(p);before=copy.deepcopy(c);no=c['checks'][0]['horse_no']
    unknown=review(c,{'finishes':{str(no):3}})
    assert unknown['observations'][0]['finding']=='実4角未取得のため検証不能'
    known=review(c,{'actual_corner4':{str(no):c['checks'][0]['expected']+3}})
    assert known['observations'][0]['finding']=='想定より後方になった'
    assert c==before and known['saved_commentary']==c

def test_fixed_commentary_survives_generator_change(monkeypatch):
    p=prediction();d=evaluate(p,None,NOW);d['commentary']=build(p)
    record=freeze(p,d,NOW);before=copy.deepcopy(record)
    monkeypatch.setattr('core.independent_ai_commentary.build',lambda *a:pytest.fail('Must use saved text'))
    out=settle(record,dict(race_id=p['race_id'],confirmed=True,source='test',finishes={'1':1},statuses={},payouts={}))
    assert record==before and out['commentary_review']['saved_commentary']==d['commentary']

def test_old_fixed_record_without_commentary_still_settles():
    p=prediction();record=freeze(p,evaluate(p,None,NOW),NOW)
    out=settle(record,dict(race_id=p['race_id'],confirmed=True,source='test'))
    assert out['commentary_review']['saved_commentary'] is None

def test_complete_market_and_virtual_reason_are_price_bound():
    p=prediction();q=quote()
    last=p['horses'][-1]['horse_no']
    q['identities']={str(h['horse_no']):h['name'] for h in p['horses']}
    q['prices']=[dict(kind='win',horses=[h['horse_no']],low=1.1 if h['horse_no']==last else 20,high=1.1 if h['horse_no']==last else 20) for h in p['horses']]
    d=evaluate(p,q,NOW);text=''.join(decision_text(p,d))
    assert '市場と予測の順序が異なる' in text and '参考払戻倍率' in text
    q['observed_at']='2026-10-13T10:00:00+09:00'
    assert '市場と予測' not in ''.join(decision_text(p,evaluate(p,q,NOW)))

@pytest.mark.parametrize('invalid',[0,-1,2.5,'(3,4)'])
def test_ambiguous_actual_corner_is_not_an_exact_rank(invalid):
    c=build(prediction());no=c['checks'][0]['horse_no']
    assert review(c,{'actual_corner4':{str(no):invalid}})['observations'][0]['actual'] is None

def test_saved_prediction_and_commentary_resolve_without_regeneration(monkeypatch):
    from types import SimpleNamespace
    from core.independent_ai import KEY,resolve
    p=prediction();p['commentary']=build(p);before=copy.deepcopy(p)
    monkeypatch.setattr('core.independent_ai_commentary.build',lambda *a:pytest.fail('saved text replaced'))
    result=SimpleNamespace(debug_info={KEY:p})
    assert resolve(result)==before and p==before
