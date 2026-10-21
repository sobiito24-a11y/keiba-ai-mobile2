import io,json,zipfile,hashlib
from copy import deepcopy
import pytest
from core.model_b_archive import add_to_copy
from core.independent_ai_odds_io import read_archive,restore_race
from core.model_b import KEY,resolve,load_artifact

def archive(event):
 body=json.dumps(event,ensure_ascii=False).encode();out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('snapshot.json',body);z.writestr('manifest.json',json.dumps({'snapshot_sha256':hashlib.sha256(body).hexdigest()}))
 return out.getvalue()

def fixture(mode):
 rows=[{'馬番':i,'馬名':f'馬{i}','ver3_ability_core':90-i,'_jockey_course_place_rate':30,'_jockey_course_starts':20,'formal_rank':i,'formal_mark':['◎','○','▲','✔','△','✓',''][i-1]} for i in range(1,8)]
 return {'schema_version':1,'races':[{'race_id':'202650101801','race_mode':mode,'prediction_result':{'race_mode':mode,'race_info':{'race_id':'202650101801','race_date':'2026-10-18'},'overall_table':{'records':rows},'debug_info':{}}}]}

@pytest.mark.parametrize('mode',['jra','nar'])
def test_copy_roundtrip_preserves_all_a_and_freezes_independent_b(mode):
 event=fixture(mode);before=deepcopy(event);raw=archive(event)
 output,audit=add_to_copy(raw);_,loaded=read_archive(output);b=loaded['races'][0].pop(KEY)
 assert loaded==before and event==before
 assert b['status']=='ready' and len(b['horses'])==7
 assert b['prediction_origin']=='retrospective_recalculation' and not b['prestart_inputs_verified']
 assert b['prediction_at'].endswith('+09:00')
 assert b['config_sha256']==load_artifact()['artifact_sha256']
 loaded['races'][0][KEY]=b
 assert resolve(restore_race(loaded['races'][0]))==b
 twice,audit=add_to_copy(output);assert read_archive(twice)[1]==read_archive(output)[1]
 assert audit[0]['action']=='preserved'

def test_incomplete_preserves_a_and_explicit_failure():
 event=fixture('nar');event['races'][0]['prediction_result']['overall_table']['records'][0]['ver3_ability_core']=None
 output,audit=add_to_copy(archive(event));new=read_archive(output)[1];b=new['races'][0].pop(KEY)
 assert new==event and b['status']=='incomplete' and b['fallback_reason']

def test_tampered_saved_b_is_not_overwritten():
 out,_=add_to_copy(archive(fixture('nar')));e=read_archive(out)[1];e['races'][0][KEY]['horses'][0]['score']=999
 with pytest.raises(ValueError):add_to_copy(archive(e))

def test_snapshot_producer_always_saves_b_without_ui_selection():
 pytest.importorskip('core.prediction_snapshot',reason='mobileはPC生成.keibaの読込経路を検証')
 from tests.test_prediction_snapshot import result_for
 from core.prediction_snapshot import race_snapshot_from_result,build_event_snapshot,keiba_bytes,load_keiba
 from core.model_b import KEY,resolve
 from datetime import date
 for mode in ['jra','nar']:
  result=result_for(mode=mode)
  result.race_info['race_date']=date(2026,10,23)
  result.race_info['start_time']='15:00'
  result.overall_table['ver3_ability_core']=[90-i for i in range(len(result.overall_table))]
  result.overall_table['_jockey_course_place_rate']=30
  result.overall_table['_jockey_course_starts']=20
  before=result.overall_table.copy(deep=True)
  race=race_snapshot_from_result(result)
  assert race[KEY]['status']=='ready'
  assert len(race[KEY]['horses'])==len(result.overall_table)
  assert race[KEY]['prediction_at'].endswith('+09:00')
  assert result.overall_table.equals(before)
  loaded=load_keiba(keiba_bytes(build_event_snapshot([race])))['races'][0]
  assert loaded['prediction_result']==race['prediction_result']
  assert resolve(restore_race(loaded))==race[KEY]
