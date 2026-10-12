import copy,json,io,zipfile,hashlib
import pytest
from core.independent_ai_odds_io import validate,merge,import_file,attach_archive,read_archive,restore_race,KEY
from core.independent_ai_html_odds import parse
from core.independent_ai_odds import evaluate
from tests.test_independent_ai_v3 import prediction,quote,NOW

def priced():
    q=quote();q['mode']='jra';return q

def archive(p):
    rows=[{'馬番':h['horse_no'],'馬名':h['name'],'ver3_ability_core':75,'純能力順位':h['horse_no'],'最終印':'◎' if h['horse_no']==1 else ''} for h in p['horses']]
    race={'race_id':p['race_id'],'race_mode':p['mode'],'prediction_result':{'race_mode':p['mode'],'race_info':{'race_id':p['race_id']},'overall_table':{'columns':list(rows[0]),'records':rows},'debug_info':{'untouched':'saved narrative'}}}
    body=json.dumps({'races':[race]}).encode();out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('snapshot.json',body);z.writestr('manifest.json',json.dumps({'snapshot_sha256':hashlib.sha256(body).hexdigest()}))
    return out.getvalue()

def test_history_roundtrip_dedupe_and_partial_coverage():
    p=prediction();q=priced();before=copy.deepcopy(p)
    h=merge([],[q],p);assert not h[0]['coverage']['wide']['complete']
    restored=import_file(json.dumps({'odds_history':h}).encode(),'history.json',p,now=NOW)
    assert merge(h,restored,p)==h and p==before
    newer=copy.deepcopy(q);newer['observed_at']='2026-10-13T11:59:35+09:00'
    assert len(merge(h,[newer],p))==2

@pytest.mark.parametrize('edit',[{'race_id':'wrong'},{'mode':'nar'},{'identities':{'1':'wrong'}},{'withdrawn':[999]}])
def test_bad_identity_rejected(edit):
    q=priced();q.update(edit)
    with pytest.raises(ValueError):validate(q,prediction())

def test_cancel_and_reversed_pairs():
    q=priced();q['prices'][-1]['horses']=[2,1]
    assert validate(q,prediction())['prices'][-1]['horses']==[1,2]
    q['withdrawn']=[1];assert not validate(q,prediction())['prices']

def test_archive_adds_only_separate_history():
    p=prediction();raw=archive(p);_,old=read_archive(raw)
    new=attach_archive(raw,p,[priced()]);_,event=read_archive(new)
    row=event['races'][0];h=row.pop(KEY)
    assert event==old and len(h)==1
    _,event=read_archive(new);result=restore_race(event['races'][0])
    assert result.debug_info[KEY]==h
    assert read_archive(attach_archive(new,p,[priced()]))[1]==read_archive(new)[1]

def test_unknown_time_reimport_does_not_refresh_price():
    q=priced();q['observed_at']=None
    restored=import_file(json.dumps(q).encode(),'odds.json',prediction(),now=NOW)[0]
    assert restored['observed_at'] is None and evaluate(prediction(),restored,NOW)['status']=='skip'

def test_dynamic_odds_horse_json_without_prices():
    p=prediction();hs={str(h['horse_no']):{'Umaban':h['horse_no'],'Bamei':h['name']} for h in p['horses']}
    html='<link rel="canonical" href="https://race.netkeiba.com/odds/index.html?race_id='+p['race_id']+'"><script>var horse_list = JSON.parse(\''+json.dumps(hs)+'\');</script><span id="odds-1_1">---.-</span>'
    q=parse(html.encode(),p,now=NOW)
    assert len(q['identities'])==10 and not q['prices'] and q['collection_status']=='prices_missing'

def test_rendered_odds_row_uses_horse_number_not_popularity():
    p=prediction();html='<link rel="canonical" href="https://race.netkeiba.com/odds/index.html?race_id='+p['race_id']+'"><table><tr><td><span id="uno-1_1">2</span></td><td class="Horse_Name">Horse 2</td><td><span id="odds-1_1">8.0</span></td><td><span id="odds-2_1">2.0 - 3.0</span></td></tr></table>'
    q=parse(html.encode(),p,now=NOW)
    assert len(q['prices'])==2 and all(r['horses']==[2] for r in q['prices'])

def test_virtual_candidates_not_proven_and_low_prices_skipped():
    p=prediction();q=priced()
    v=evaluate(p,q,NOW);assert v['candidates'] and not v['proven_recommendation']
    for x in q['prices']:x['low']=x['high']=1
    assert not evaluate(p,q,NOW)['candidates']


def test_history_uses_latest_per_ticket_and_does_not_refresh_old():
    from core.independent_ai_odds import evaluate_history
    p=prediction();a=priced();b=copy.deepcopy(a)
    a['prices']=a['prices'][:1];b['prices']=b['prices'][1:]
    assert len(evaluate_history(p,[a,b],NOW)['price_evaluations'])==3
    b['prices']=[dict(kind='win',horses=[1],low=2,high=2)]
    b['observed_at']=None
    assert not evaluate_history(p,[a,b],NOW)['price_evaluations']
    b['prices']=[];b['withdrawn']=[1]
    assert not evaluate_history(p,[a,b],NOW)['price_evaluations']
