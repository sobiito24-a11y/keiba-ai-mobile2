import copy,json,sqlite3
from datetime import datetime,timezone,timedelta
from core.new_ai_research import calculate,freeze,correction,CONFIG,digest

def sample():
 return {'race_mode':'jra','race_id':'202608040711','date':'2026-10-18','venue':'京都','distance':2000,'surface':'芝',
 'horses':[{'horse_no':1,'horse_name':'馬A','jra_top5_rank':1,'jra_top5_score':123.5,'ability_value':120}],
 'prediction_result':{'horse_evaluation':{'records':[{'馬番':1,'netkeiba_corner4_rank':1}]}},'mobile_snapshot':{}}

def test_no_mutation_and_missing(tmp_path):
 r=sample();before=copy.deepcopy(r);a=calculate(r,'hash',tmp_path/'none')
 assert r==before and a['models']['A']['rows'][0]['score']==123.5
 assert not a['models']['F1']['complete'] and a['models']['F1']['rows'][0]['score'] is None

def test_immutable_and_dedup(tmp_path):
 a=calculate(sample(),'hash',None);p=tmp_path/'p.sqlite'
 x=freeze(a,p);y=freeze(a,p)
 assert x==y and not x['eligible_pre_race']
 c=sqlite3.connect(p)
 try:c.execute("UPDATE new_ai_frozen SET saved_at='bad'")
 except sqlite3.IntegrityError:c.rollback()
 else:assert False
 b=copy.deepcopy(a);b['keiba_sha256']='changed';z=freeze(b,p)
 assert z['input_sha256']!=x['input_sha256'];assert c.execute('select count(*) from new_ai_frozen').fetchone()[0]==2

def test_shrink():
 assert correction({'status':'no_sample'},CONFIG['JRA']) is None
 assert correction({'status':'observed','n':1,'top3':1},CONFIG['JRA'])<1

def test_schedule(tmp_path):
 a=calculate(sample(),'hash',None,'2026-10-18T15:40:00+09:00')
 f=freeze(a,tmp_path/'p.sqlite',datetime(2026,10,18,12,tzinfo=timezone(timedelta(hours=9))))
 assert not f['eligible_pre_race']

def test_nar_separate():
 r=sample();r['race_mode']='nar';r['mobile_snapshot']['nar_top5_corner_order']={'horses':[{'horse_no':1,'nar_final_rank':1,'nar_top5_order_score':.01}]}
 a=calculate(r,'hash',None)
 assert 'F1' not in a['models'] and a['models']['NAR_Pure']['rows'][0]['score']==120
 assert a['models']['A']['rows'][0]['score']==.01

def test_optional_module_absent(monkeypatch):
 import sys
 from core.game_race_ui import comparison_data
 monkeypatch.setitem(sys.modules,'core.new_ai_research_ui',None)
 groups=comparison_data([],'jra','no-race')
 assert '利用できません' in next(g['html'] for g in groups if g['key']=='research')

def test_panel_missing_db(tmp_path,monkeypatch):
 from core.new_ai_research_ui import panel
 monkeypatch.setenv('KEIBA_RESEARCH_PREDICTIONS',str(tmp_path/'absent.sqlite'))
 assert '未取得' in panel([],'race')
