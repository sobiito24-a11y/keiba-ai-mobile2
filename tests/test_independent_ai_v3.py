import copy,json
from datetime import datetime,timedelta
import pandas as pd
import pytest
from core.models import PredictionResult
from core.independent_ai import KEY,JST,predict,features,digest,attach,resolve,from_result,restore,saved_fields
from core.independent_ai_odds import evaluate,provider,AuthorizedJsonProvider
from core.independent_ai_registry import freeze,register,settle,settle_saved
from core.independent_ai_ui import markup

def packet(mode='jra'):
    return dict(race_id='202601010101',mode=mode,post_time='2026-10-13T15:00:00+09:00',prediction_created_at='2026-10-13T09:00:00',
        horses=[dict(horse_no=i,name=f'Horse {i}',pure=100-i*3,distance_index=95-i,course_index=90-i,recent3_mean=92-i*2,
        corner4=i,jockey_place_rate=30,jockey_sample_size=40,training='B',rest_days=21,load_change=0) for i in range(1,11)])

def prediction(mode='jra'):
    p=packet(mode);v=predict(p);v.update(input=p,generated_at='2026-10-13T10:00:00+09:00',origin='new_prediction');return v

def quote():
    return dict(race_id='202601010101',source='licensed-test',authorization_reference='test only',
        identities={'1':'Horse 1','2':'Horse 2'},
        observed_at='2026-10-13T11:59:30+09:00',received_at='2026-10-13T11:59:40+09:00',
        prices=[dict(kind='win',horses=[1],low=10,high=10),dict(kind='place',horses=[1],low=3,high=5),dict(kind='wide',horses=[1,2],low=5,high=8)])

NOW=datetime(2026,10,13,12,tzinfo=JST)

@pytest.mark.parametrize('mode',['jra','nar'])
def test_all_horses_probability_and_invariance(mode):
    p=packet(mode);before=copy.deepcopy(p);a=predict(p);assert p==before and a==predict(p)
    assert len(a['horses'])==10 and len(a['wide'])==45
    assert sum(h['win'] for h in a['horses'])==pytest.approx(1)
    assert all(0<=h['place']<=1 and h['win_range'][0]<=h['win']<=h['win_range'][1] for h in a['horses'])
    assert a['profit_validated'] is False and '未校正' in a['calibration_status']

def test_outcomes_odds_marks_do_not_influence_predictions():
    p=packet();a=predict(p)
    for h in p['horses']:h.update(odds=999,finish=1,payout=99999,formal_rank=1,formal_mark='◎')
    b=predict(p)
    assert a['horses']==b['horses'] and a['wide']==b['wide']

def test_absent_data_no_fictitious_probabilities():
    p=packet()
    for h in p['horses']:h['pure']=None
    assert predict(p)['status']=='insufficient'

def test_no_duplicate_horse_number():
    p=packet();p['horses'][1]['horse_no']=1
    with pytest.raises(ValueError):predict(p)

def test_withdrawal_removed_only_independent_output():
    p=packet();p['horses'][0]['known_withdrawn']=True
    assert len(predict(p)['horses'])==9 and len(p['horses'])==10

def test_uncalibrated_virtual_only_and_lower_price():
    p=prediction();v=evaluate(p,quote(),NOW)
    assert v['status']=='virtual_candidate' and v['candidates'] and v['max_virtual_loss_yen']==100
    assert v['proven_recommendation'] is False and v['actual_purchase'] is False
    row=next(x for x in v['price_evaluations'] if x['kind']=='place')
    assert row['reference_gross_return']==pytest.approx(row['probability']*3)

@pytest.mark.parametrize('change',[{'observed_at':'2026-10-13T11:50:00+09:00'}, {'observed_at':'2026-10-13T12:01:00+09:00'}, {'race_id':'other'}, {'observed_at':None},{'authorization_reference':''}])
def test_bad_odds_rejected(change):
    q=quote();q.update(change);v=evaluate(prediction(),q,NOW)
    assert v['status']=='skip' and v['price_evaluations']==[]

def test_after_start_rejected():
    v=evaluate(prediction(),quote(),datetime(2026,10,13,16,tzinfo=JST));assert not v['price_evaluations']

def test_missing_odds_normal_prediction():
    p=prediction();assert p['horses'] and evaluate(p,now=NOW)['status']=='skip'
    assert provider().available is False

def test_connection_requires_explicit_rights():
    with pytest.raises(ValueError):AuthorizedJsonProvider(dict(enabled=True,endpoint='https://example.com'))

def test_provider_name_mismatch_not_valued():
    q=quote();q['identities']['1']='Different horse'
    assert evaluate(prediction(),q,NOW)['price_evaluations']==[]

def test_provider_success_and_failure(monkeypatch):
    import requests
    class Response:
        status_code=200;content=b'{}'
        def json(self):return quote()
    monkeypatch.setattr(requests,'get',lambda *a,**k:Response())
    p=AuthorizedJsonProvider(dict(enabled=True,rights_confirmed=True,authorization_reference='approved',source='licensed-test',endpoint='https://example.test/odds'))
    assert p.fetch('202601010101')['authorization_reference']=='approved'
    Response.status_code=503
    with pytest.raises(ValueError):p.fetch('202601010101')

def test_saved_prediction_survives_model_update(monkeypatch):
    p=prediction();r=PredictionResult('jra',debug_info={KEY:p});before=copy.deepcopy(r)
    monkeypatch.setattr('core.independent_ai.predict',lambda *a:pytest.fail('Saved version must not regenerate'))
    assert resolve(r)==p and r==before
    other=PredictionResult('jra');restore(other,saved_fields(r));assert resolve(other)==p

def test_render_escapes_names_and_no_formal_marks():
    p=prediction();p['horses'][0]['name']='<script>bad</script>';s=markup(p)
    assert '<script>' not in s and '&lt;script&gt;' in s and '参考' in s

def test_registry_freezes_once_and_settles_skip(tmp_path):
    p=prediction();d=evaluate(p,now=NOW);f=freeze(p,d,NOW);path=register(tmp_path,f);before=path.read_bytes();register(tmp_path,f)
    o=dict(race_id=p['race_id'],confirmed=True,source='official-test',statuses={'1':'1'},finishes={'1':1},payouts={'win':{'1':500},'place':{'1':200}})
    value=settle_saved(tmp_path,p['race_id'],o)
    assert value['roi'] is None and value['stake']==0 and path.read_bytes()==before
    f['prediction']['horses'][0]['win']=1
    with pytest.raises(ValueError):register(tmp_path,f)

def test_reserved_and_late_cannot_freeze():
    p=prediction();p['input']['post_time']='2026-10-12T15:00:00+09:00';p['generated_at']='2026-10-12T10:00:00+09:00';p['input_hash']=digest(p['input'])
    n=datetime(2026,10,12,12,tzinfo=JST)
    with pytest.raises(ValueError,match='10/12'):freeze(p,evaluate(p,now=n),n)
    p=prediction()
    with pytest.raises(ValueError):freeze(p,evaluate(p,now=NOW),datetime(2026,10,13,16,tzinfo=JST))

def test_adapter_and_attach_do_not_modify_formal_values():
    rows=[{'馬番':i,'馬名':str(i),'ver3_ability_core':100-i,'jra_top5_rank':i,'最終印':'◎' if i==1 else '',
           'netkeiba_corner4_rank':i,'jra_win_probability':.1,'距離指数':90-i,'コース指数':80-i} for i in range(1,11)]
    r=PredictionResult('jra',race_info={'race_id':'202601010101','race_date':'2026-10-13','race_data':'15:00発走'},overall_table=pd.DataFrame(rows),horse_evaluation=pd.DataFrame(rows),debug_info={'existing_shadow':{'a':1}})
    old=copy.deepcopy(r);attach(r)
    pd.testing.assert_frame_equal(r.overall_table,old.overall_table);pd.testing.assert_frame_equal(r.horse_evaluation,old.horse_evaluation)
    assert r.debug_info['existing_shadow']==old.debug_info['existing_shadow'] and r.race_info==old.race_info
    assert from_result(r)['post_time']=='2026-10-13T15:00:00+09:00'
