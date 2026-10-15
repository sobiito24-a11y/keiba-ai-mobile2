from copy import deepcopy
from datetime import datetime
import itertools
import json
import pytest
from core import race_odds as o


def identity(mode='jra', n=18):
    return dict(race_id='202608040511', mode=mode, horses=[dict(horse_no=i, name=f'馬{i}') for i in range(1,n+1)])


def quote(mode='jra', n=18):
    i=identity(mode,n)
    return dict(race_id=i['race_id'], mode=mode, identities={str(h['horse_no']):h['name'] for h in i['horses']},
                source='test', received_at='2026-10-12T14:00:05+09:00', observed_at='2026-10-12T14:00:00+09:00',
                prices=[dict(kind=k,horses=list(ns),low=2.0,high=3.0 if k in ('place','wide') else 2.0)
                        for k in o.KINDS for ns in (itertools.combinations(range(1,n+1),2) if k in ('quinella','wide') else [(j,) for j in range(1,n+1)])])


@pytest.mark.parametrize('mode',['jra','nar'])
def test_full_batch_four_kinds_no_mutation(mode):
    q=quote(mode);before=deepcopy(q);v=o.validate(q,identity(mode))
    assert q==before
    assert v['horse_count']==18 and v['collection_status']=='complete'
    assert [v['coverage'][k]['count'] for k in o.KINDS]==[18,18,153,153]


@pytest.mark.parametrize('change',[
    lambda q:q.update(race_id='202608040512'), lambda q:q.update(mode='nar'),
    lambda q:q['identities'].update({'1':'別馬'}), lambda q:q['prices'][0].update(low='---.-'),
    lambda q:q['prices'][0].update(low=float('nan')), lambda q:q.update(observed_at='2026-10-12T14:00:00'),
    lambda q:q.update(withdrawn=[19]), lambda q:q['prices'][0].update(horses=[True]),
    lambda q:q['prices'].append(dict(kind='win',horses=[1],low=4,high=4))])
def test_invalid_batch_rejected(change):
    q=quote();change(q)
    with pytest.raises(ValueError):o.validate(q,identity())


def test_duplicate_import_never_refreshes_time():
    q=quote();v=o.merge([], [q],identity());q['received_at']='2026-10-12T15:00:00+09:00'
    assert o.merge(v,[q],identity())==v


def test_partial_does_not_fill_old_prices_or_change_fields():
    view=[dict(no='1',name='馬1',odds='99',score='100',mark='◎'),dict(no='2',name='馬2',odds='88',score='90',mark='✓')]
    before=deepcopy(view);q=quote();q['prices']=q['prices'][:1]
    out=o.overlay(view,o.validate(q,identity()),'更新オッズ')
    assert view==before and out[1]['odds']=='—'
    assert out[0]['score']=='100' and out[0]['mark']=='◎'
    assert out[1]['mark']=='✓'


def test_withdrawal_removes_all_tickets_and_updates_denominators():
    q=quote();q['withdrawn']=[3];v=o.validate(q,identity())
    assert not any(3 in p['horses'] for p in v['prices'])
    assert v['coverage']['wide']==dict(count=136,expected=136)


def test_all_files_atomic():
    q=quote();bad=quote();bad['race_id']='202608040512'
    with pytest.raises(ValueError):o.import_files([('ok.json',json.dumps(q).encode()),('bad.json',json.dumps(bad).encode())],identity())


def test_freshness():
    q=quote();start='2026-10-12T15:00:00+09:00'
    assert '発走前' in o.freshness(q,start,datetime.fromisoformat('2026-10-12T14:01:00+09:00'))
    assert '古い' in o.freshness(q,start,datetime.fromisoformat('2026-10-12T14:10:00+09:00'))
    assert '発走後' in o.freshness(q,start,datetime.fromisoformat('2026-10-12T15:00:00+09:00'))
    q['observed_at']=None
    assert '時刻不明' in o.freshness(q,start,datetime.fromisoformat('2026-10-12T14:01:00+09:00'))
    assert '発走日時未確認' in o.freshness(q,None)


def test_explicit_named_quinella_export_and_popularity_not_horse_number():
    html='''<link rel="canonical" href="https://race.netkeiba.com/odds/index.html?race_id=202608040511">
    <table><tr><td class="Umaban">2</td><td class="Horse_Name">馬2</td><td id="odds-1_1">4.4</td><td id="odds-2_1">1.2〜2.0</td></tr></table>
    <table><tr><th>馬番1</th><th>馬名1</th><th>馬番2</th><th>馬名2</th><th>馬連</th></tr>
    <tr><td>1</td><td>馬1</td><td>2</td><td>馬2</td><td>12.3</td></tr></table>'''
    q=o.import_files([('x.html',html.encode())],identity())[0]
    assert next(p for p in q['prices'] if p['kind']=='win')['horses']==[2]
    assert next(p for p in q['prices'] if p['kind']=='quinella')['horses']==[1,2]
    assert q['observed_at'] is None
    html=html.replace('4.4','---.-').replace('1.2〜2.0','---.-').replace('12.3','---.-')
    assert o.import_files([('x.html',html.encode())],identity())[0]['prices']==[]


def test_unconfigured_collector_never_opens_network(tmp_path):
    from core.race_odds_collection import collect
    class Page:
        def goto(self,*a,**kw):raise AssertionError('network must not run')
    assert collect(Page(),'202608040511','jra',tmp_path)['status']=='not_configured'


def test_archive_copy_preserves_prediction_and_original(tmp_path):
    import io,zipfile,hashlib
    import pandas as pd
    from core.models import PredictionResult
    from core.independent_ai_odds_io import restore_race,read_archive
    table=dict(columns=['馬番','馬名','actual_odds'],records=[{'馬番':1,'馬名':'馬1','actual_odds':7.7},{'馬番':2,'馬名':'馬2','actual_odds':8.8}])
    race=dict(race_id='202608040511',race_mode='jra',prediction_result=dict(race_mode='jra',race_info={'race_id':'202608040511'},overall_table=table,horse_evaluation=table,debug_info={}))
    event=dict(races=[race]);body=json.dumps(event).encode();out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('snapshot.json',body);z.writestr('manifest.json',json.dumps(dict(snapshot_sha256=hashlib.sha256(body).hexdigest())))
    raw=out.getvalue();before=hashlib.sha256(raw).hexdigest();r=restore_race(race);ident=o.identity_from_result(r)
    state=o.state_for(r);state['history']=o.merge([], [quote(n=2)],ident)
    copied=o.export_copy(raw,ident,state);saved=read_archive(copied)[1]
    assert saved['races'][0]['prediction_result']==race['prediction_result']
    assert hashlib.sha256(raw).hexdigest()==before
    restored=restore_race(saved['races'][0]);assert o.state_for(restored)==state
    assert read_archive(o.export_copy(copied,ident,state))[1]==saved
    changed=deepcopy(state);changed['saved'][0]['prices'][0]['low']=3
    with pytest.raises(ValueError):o.export_copy(copied,ident,changed)


@pytest.mark.parametrize('mode,host',[('jra','race.netkeiba.com'),('nar','nar.netkeiba.com')])
def test_collector_rendered_numbers_then_builder_sibling_only(tmp_path,mode,host):
    """Synthetic public DOM contract, not evidence of actual provider access."""
    from core.race_odds_collection import collect,attach_collected
    rid='202608040511'
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(enabled=True,rights_confirmed=True,authorization_reference='test-only',
                                     pages={mode:[f'https://{host}/odds/index.html?race_id={{race_id}}']})),encoding='utf-8')
    class Response:status=200
    class Page:
        def goto(self,url,**kw):self.url=url;return Response()
        def wait_for_timeout(self,*a):pass
        def content(self):return '<meta charset="utf-8"><table><tr><td class="Umaban">1</td><td class="Horse_Name">馬1</td><td id="odds-1_1">4.5</td><td id="odds-2_1">1.5〜2.5</td></tr></table>'
    status=collect(Page(),rid,mode,tmp_path,config)
    assert status['pages'][0]['price_count']==2
    table=dict(columns=['馬番','馬名'],records=[{'馬番':1,'馬名':'馬1'}])
    race=dict(race_id=rid,race_mode=mode,prediction_result=dict(race_mode=mode,race_info={'race_id':rid},overall_table=table,horse_evaluation=table,debug_info={}))
    event=dict(races=[race]);before=deepcopy(event)
    new=attach_collected(event,tmp_path)
    assert event==before
    assert new['races'][0]['prediction_result']==race['prediction_result']
    assert new['races'][0][o.KEY]['saved'][0]['prices'][0]['low']==1.5
    assert new['races'][0][o.KEY]['saved'][0]['observed_at'] is None


def test_bad_optional_odds_cannot_break_prediction_restore():
    from core.independent_ai_odds_io import restore_race
    table=dict(columns=['馬番','馬名'],records=[{'馬番':1,'馬名':'馬1'}])
    race=dict(race_id='202608040511',race_mode='jra',prediction_result=dict(race_mode='jra',race_info={'race_id':'202608040511'},overall_table=table,horse_evaluation=table,debug_info={}),race_odds_v1={'saved':[quote(n=2)]})
    r=restore_race(race)
    assert r._race_odds_error and not o.state_for(r)['saved']
    assert r.overall_table.iloc[0]['馬名']=='馬1'
