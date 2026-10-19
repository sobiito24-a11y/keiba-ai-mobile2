import copy,io,json,zipfile
import pytest
from core import research_bundle as b
from core.new_ai_research import calculate,freeze,digest

def fixture(tmp_path):
 race={'race_mode':'jra','race_id':'202608040711','date':'2026-10-18','venue':'京都','surface':'芝','distance':2000,'horses':[{'horse_no':1,'horse_name':'馬A','jra_top5_rank':1,'jra_top5_score':123.5,'ability_value':120}], 'prediction_result':{'horse_evaluation':{'records':[{'馬番':1,'netkeiba_corner4_rank':1}]}},'mobile_snapshot':{}}
 event={'schema_version':1,'races':[race]};body=json.dumps(event).encode()
 raw=zip_bytes({'snapshot.json':body,'manifest.json':json.dumps({'snapshot_sha256':b.sha(body)}).encode()})
 report=freeze(calculate(race,b.sha(raw),None),tmp_path/'p.sqlite')
 return raw,event,report

def zip_bytes(files):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,body in files.items():z.writestr(name,body)
 return out.getvalue()

def test_bundle_roundtrip_original_preserved_and_deterministic(tmp_path):
 raw,event,p=fixture(tmp_path);before=copy.deepcopy(p)
 data=b.build(raw,[p]);original,loaded,reports=b.load(data)
 assert original==raw and loaded==event and reports[p['race_id']]==p and p==before
 assert b.build(raw,[p])==data
 assert b.load(raw)==(raw,event,{})
 assert b.load(b.build(raw,[]))[2]=={}

@pytest.mark.parametrize('change',['wrong_hash','wrong_race','wrong_version','wrong_config','wrong_horse'])
def test_research_identity_rejected(tmp_path,change):
 raw,event,p=fixture(tmp_path)
 if change=='wrong_hash':p['keiba_sha256']='x'
 if change=='wrong_race':p['race_id']='202608040712'
 if change=='wrong_version':p['version']='other'
 if change=='wrong_config':p['config']=dict(p['config'],fit=True);p['config_sha256']=digest(p['config'])
 if change=='wrong_horse':p['models']['F1']['rows'][0]['name']='別馬'
 with pytest.raises(ValueError):b.build(raw,[p])

@pytest.mark.parametrize('name',['../escape','/absolute','research/../../escape','secret.html','x\\y','C:/foo'])
def test_no_unlisted_paths(tmp_path,name):
 raw,event,p=fixture(tmp_path)
 with zipfile.ZipFile(io.BytesIO(b.build(raw,[p]))) as z:files={n:z.read(n) for n in z.namelist()}
 files[name]=b'secret'
 with pytest.raises(ValueError):b.load(zip_bytes(files))

def test_tampering_size_duplicate_and_invalid(tmp_path,monkeypatch):
 raw,event,p=fixture(tmp_path);data=b.build(raw,[p])
 with zipfile.ZipFile(io.BytesIO(data)) as z:files={n:z.read(n) for n in z.namelist()}
 files['prediction.keiba']=b'changed'
 with pytest.raises(ValueError):b.load(zip_bytes(files))
 with pytest.raises(ValueError):b.load(b'not zip')
 monkeypatch.setattr(b,'MAX_TOTAL',10)
 with pytest.raises(ValueError):b.load(data)
 monkeypatch.setattr(b,'MAX_TOTAL',256_000_000)
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('x','1');z.writestr('x','2')
 with pytest.raises(ValueError):b.load(out.getvalue())

def test_exact_hash_local_lookup_and_bad_db(tmp_path):
 raw,event,p=fixture(tmp_path)
 found,issues=b.local_reports(raw,event,tmp_path/'p.sqlite',tmp_path/'empty')
 assert found[p['race_id']]==p and not issues
 other=raw+b'changed' # ZIP reader can tolerate trailing bytes, identity cannot.
 assert b.local_reports(other,event,tmp_path/'p.sqlite',tmp_path/'empty')[0]=={}
 (tmp_path/'bad.sqlite').write_bytes(b'broken')
 assert b.local_reports(raw,event,tmp_path/'bad.sqlite',tmp_path/'empty')[1]

def test_context_replaced_and_rejected_inputs_clear_context(tmp_path):
 raw,event,p=fixture(tmp_path);state={}
 b.attach_upload(b.build(raw,[p]),state,False)
 assert state['research_loaded']['reports']
 b.attach_upload(raw,state,False)
 assert state['research_loaded']['reports']=={}
 with pytest.raises(ValueError):b.attach_upload(b'bad',state,False)
 assert 'research_loaded' not in state

def test_missing_models_not_invented_and_no_db_race_only_fallback(tmp_path):
 from core.new_ai_research_ui import panel
 raw,event,p=fixture(tmp_path)
 view=[dict(no='1',name='馬A',rank='1',corner=1,mode='jra',score=123.5)]
 out=panel(view,p['race_id'],p)
 assert '未計算' in out and 'jockey:not_acquired' in out
 assert '研究予想が未取得' in panel(view,p['race_id'])
 assert p['models']['F1']['rows'][0]['score'] is None


def test_cli_bundle_repeat_and_stale_input_guard(tmp_path):
 import subprocess,sys
 from pathlib import Path
 raw,event,p=fixture(tmp_path);source=tmp_path/'sample.keiba';source.write_bytes(raw)
 script=Path(__file__).resolve().parents[1]/'tools/new_ai_research.py'
 cmd=[sys.executable,str(script),'--keiba',str(source),'--stats',str(tmp_path/'missing.sqlite'),'--out',str(tmp_path/'fixed.sqlite'),'--bundle-dir',str(tmp_path/'bundles')]
 first=subprocess.run(cmd,capture_output=True);assert first.returncode==0,first.stderr
 files=list((tmp_path/'bundles').glob('*.zip'));assert len(files)==1
 assert b.load(files[0].read_bytes())[0]==raw
 second=subprocess.run(cmd,capture_output=True);assert second.returncode==0,second.stderr
 assert len(list((tmp_path/'bundles').glob('*.zip')))==1
 import time
 blocked=subprocess.run(cmd+['--not-before-ns',str(time.time_ns()+1_000_000_000)],capture_output=True)
 assert blocked.returncode!=0

def test_automatic_json_lookup_needs_source_and_version(tmp_path):
 raw,event,p=fixture(tmp_path);folder=tmp_path/'json';folder.mkdir()
 target=folder/(p['race_id']+'_test.json')
 target.write_text(json.dumps({'payload':p,'payload_sha256':digest(p)}),encoding='utf-8')
 found,_=b.local_reports(raw,event,tmp_path/'absent.sqlite',folder)
 assert found[p['race_id']]==p
 p['version']='old';target.write_text(json.dumps({'payload':p,'payload_sha256':digest(p)}),encoding='utf-8')
 assert not b.local_reports(raw,event,tmp_path/'absent.sqlite',folder)[0]


def test_wrapper_stops_after_collector_failure(tmp_path):
 import os,subprocess,shutil
 from pathlib import Path
 if os.name!='nt':pytest.skip('Windows BAT')
 tools=Path(__file__).resolve().parents[1]/'tools'
 wrapper=tmp_path/'run.bat';shutil.copyfile(tools/'run_prediction_then_research.bat',wrapper)
 collector=tmp_path/'collector.bat';collector.write_text('@echo off\nexit /b 7\n')
 marker=tmp_path/'called.txt'
 (tmp_path/'new_ai_research.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("called")\n')
 original=tmp_path/'saved.keiba';original.write_bytes(b'existing')
 command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(wrapper),str(collector),str(original),str(tmp_path/'stats.sqlite')]
 result=subprocess.run(command,capture_output=True)
 assert result.returncode==7 and not marker.exists()
 collector.write_text('@echo off\nexit /b 0\n')
 result=subprocess.run(command,capture_output=True)
 assert result.returncode==0 and marker.exists(),result.stderr


def test_wrapper_resolves_paths_before_collector_changes_directory(tmp_path):
 import os,subprocess,shutil
 from pathlib import Path
 if os.name!='nt':pytest.skip('Windows BAT')
 tools=Path(__file__).resolve().parents[1]/'tools'
 shutil.copyfile(tools/'run_prediction_then_research.bat',tmp_path/'run.bat')
 (tmp_path/'elsewhere').mkdir()
 (tmp_path/'collector.bat').write_text('@echo off\ncd /d "'+str(tmp_path/'elsewhere')+'"\nexit /b 0\n')
 original=tmp_path/'saved.keiba';original.write_bytes(b'existing')
 (tmp_path/'new_ai_research.py').write_text('import sys\nfrom pathlib import Path\nassert Path(sys.argv[sys.argv.index("--keiba")+1]).resolve()==Path('+repr(str(original))+')\n')
 result=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c','run.bat','collector.bat','saved.keiba','stats.sqlite'],cwd=tmp_path,capture_output=True)
 assert result.returncode==0,result.stderr
