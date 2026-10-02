import copy
import json
import pytest
from core.newspaper_v2_enrichment import identity,merge_run,evaluate_enriched,newspaper_runs
from core.newspaper_v2_class_revision import evaluate_class_revision
from core.newspaper_v2_engine import evaluate_shadow


def run(**kw):
    return dict(race_id='202606040104',date='2026-09-05',venue='中山',race_number=4,surface='芝',distance=1800,horse_id='2023100011',race_name='3歳以上1勝クラス',finish=2,head_count=10,source='snapshot_past_run',**kw)


def test_identity_does_not_match_month_day_or_label():
    a=run();b=run();b['race_id']='202506040104';b['date']='2025-09-05'
    assert identity(a,b)[0]=='conflict'
    b=run();b.pop('race_id');b['date']='09/05'
    assert identity(a,b)[0]=='conflict'
    a={k:v for k,v in run().items() if k!='race_id'}
    assert identity(a,a)[0]=='composite'
    a.pop('horse_id');assert identity(a,a)[0]=='unmatched'


def test_merge_preserves_explicit_saved_age_and_class():
    saved=run();html=run();html.update(race_name='特別',class_badge_raw='1勝',source='newspaper_past_block',head_count=12)
    html.pop('horse_id');saved.pop('head_count')
    before=copy.deepcopy(saved)
    r=merge_run(saved,html)
    assert r['class_context']['age_restriction_v2']=='3歳以上'
    assert r['class_context']['class_label_v2']=='1勝'
    assert r['values']['head_count']==12
    assert r['audit']['fields']['race_name']['source']=='snapshot_past_run'
    assert saved==before


def test_unknown_age_not_inferred_from_horse_or_other_run():
    r=run();r['race_name']='特別';r['class_badge_raw']='1勝';r['age']=3
    assert merge_run({},r)['class_context']['age_restriction_v2']=='不明'


def test_conflict_cannot_restore_saved_class():
    a=run();b=run();b.update(race_id='202607030408',venue='中京',race_name='特別',class_badge_raw='2勝')
    merged=merge_run(a,b)
    assert merged['audit']['status']=='conflict'
    assert merged['class_context']['age_restriction_v2']=='不明'


def test_newspaper_badge_not_data03():
    html='''<dl class="HorseList"><span class="Waku_Horse">5</span><div class="Past_Wrapper"><li class="Past"><div class="PastDataLine"><span class="Data01">09/05 中山 4R</span><span class="Icon_GradeType">1勝</span><span class="RaceName"><a href="https://db.netkeiba.com/race/202606040104/">特別</a></span><span class="Data03">定量</span><span class="Data04"><b class="Num">2</b></span><span class="Data05">12頭</span><span class="Data09">芝1800</span></div></li></div></dl>'''
    r=newspaper_runs(html)['5'][0]
    assert r['date']=='2026-09-05' and r['class_badge_raw']=='1勝' and r['head_count']==12
    assert r['race_data2']=='定量'


def test_versioned_result_parent_and_formal_inputs_unchanged():
    rows=[{'horse_no':1,'horse_name':'A','ver3_ability_core':50,'age':3,'odds':100,'finish':1}]
    info={'race_name':'3歳以上1勝クラス','surface':'芝','racecourse':'中山','race_date':'2026-09-27'}
    base=evaluate_shadow(rows,info,'jra');split=evaluate_class_revision(rows,info,'jra',base_v1=base)
    before=copy.deepcopy((rows,base,split))
    result=evaluate_enriched(rows,info,'jra',base_v1=base,base_split=split)
    assert (rows,base,split)==before
    assert result['model_version']=='jra_newspaper_shadow_v3_input_enriched'
    assert result['coefficients']==split['coefficients']
    assert result['horses'][0]['jra_v2_class_change_score'] is None
    assert json.loads(json.dumps(result))==result
    rows[0].update(finish=12,odds=.1,popularity=1)
    again=evaluate_enriched(rows,info,'jra',base_v1=base,base_split=split)
    result.pop("evaluated_at");again.pop("evaluated_at")
    assert result==again

def test_mixed_nar_classes_remain_unmapped():
    from core.newspaper_v2_enrichment import conservative_class
    for name in ('3歳以上C3ー2C4','一般 C1 C2','3歳以上C'):
        ctx=conservative_class({'race_name':name,'venue':'門別','surface':'ダ'})
        assert ctx['class_level_v2'] is None
    assert conservative_class({'race_name':'一般 C2','venue':'浦和','surface':'ダ'})['class_level_v2'] is not None


def test_official_header_validates_identity_and_ignores_results():
    from core.newspaper_v2_past_headers import parse_nar_official_header
    html='''<h4>2026年9月9日 門 別 第5競走</h4><section class="raceTitle"><h3>3歳以上 C3-2 C4-1</h3><ul class="dataArea"><li>ダート 1200m（右） 天候：晴 馬場：良 サラブレッド系 一般 定量 ＊電話投票コード</li></ul></section><table><tr><td>1着 人気1 オッズ1.1</td></tr></table>'''
    run={'race_id':'202630090905','date':'2026-09-09','venue':'門別','distance':1200}
    a=parse_nar_official_header(html,run,source='test')
    b=parse_nar_official_header(html.replace('1着 人気1 オッズ1.1','9着 人気9 オッズ999'),run,source='test')
    assert a is not None
    assert '天候' not in a['race_data2']
    # Hash audits bytes; no outcome-derived model feature changes.
    a.pop('input_hash');b.pop('input_hash');assert a==b
    assert parse_nar_official_header(html,{**run,'date':'2025-09-09'},source='test') is None
    assert parse_nar_official_header(html,{**run,'race_id':'202630090906'},source='test') is None


def test_header_wrong_venue_does_not_override_saved():
    source=run();header={**run(),'venue':'阪神','source':'wrong_header'}
    merged=merge_run(source,source,header)
    assert merged['values']['venue']=='中山'
    assert 'header_venue' in merged['audit']['field_conflicts']


def test_restore_all_versions_without_evaluating_or_fetching():
    from unittest.mock import patch
    from core.models import PredictionResult
    from core.newspaper_v2_snapshot import newspaper_v2_snapshot,restore_newspaper_v2_snapshot
    key='jra_newspaper_v2_input_enriched_shadow'
    frozen={key:{'model_version':'old_version','horses':[{'structured_recent_runs':[{'audit':{'acquired_at':None},'input_hash':'abc'}]}]}}
    with patch('core.newspaper_v2_enrichment.evaluate_enriched',side_effect=AssertionError('replay forbidden')),patch('requests.get',side_effect=AssertionError('HTTP forbidden')):
        result=restore_newspaper_v2_snapshot(PredictionResult(race_mode='jra'),frozen)
        assert newspaper_v2_snapshot(result)==frozen
        assert newspaper_v2_snapshot(restore_newspaper_v2_snapshot(PredictionResult(race_mode='jra'),{}))=={}


def test_nar_cache_deduplicates_and_records_fetch_time(tmp_path):
    from unittest.mock import patch,Mock
    from core.newspaper_v2_past_headers import PastHeaderCache,collect_nar_header
    html='<h4>2026年9月9日 門別 第5競走</h4><section class="raceTitle"><h3>3歳以上 C3-2 C4-1</h3><ul class="dataArea"><li>ダート1200m サラブレッド系 一般 定量</li></ul></section>'
    response=Mock(status_code=200,text=html)
    run={'race_id':'202630090905','date':'2026-09-09','venue':'門別','distance':1200}
    cache=PastHeaderCache(tmp_path,allow_http=True)
    with patch('requests.get',return_value=response) as get:
        a=collect_nar_header(cache,run);b=collect_nar_header(cache,run)
        assert a==b and a['acquired_at']
        get.assert_called_once()
    with patch('requests.get',side_effect=AssertionError('cache must avoid HTTP')):
        assert collect_nar_header(PastHeaderCache(tmp_path,allow_http=True),run)==a

def test_replay_uses_saved_structured_inputs_without_html_or_network():
    from core.newspaper_v2_enrichment import replay_enriched_inputs
    from unittest.mock import patch
    rows=[{'horse_no':1,'ver3_ability_core':50}]
    info={'race_name':'3歳以上1勝クラス','surface':'芝','racecourse':'中山','race_date':'2026-09-27'}
    result=evaluate_enriched(rows,info,'jra')
    with patch('requests.get',side_effect=AssertionError('No HTTP')),patch('core.newspaper_v2_enrichment.newspaper_runs',side_effect=AssertionError('No HTML')):
        assert replay_enriched_inputs(json.loads(json.dumps(result)))==result

def test_valid_saved_age_join_enables_B_without_changing_coefficients():
    html='''<dl class="HorseList"><span class="Waku_Horse">1</span><div class="Past_Wrapper"><li class="Past"><div class="PastDataLine"><span class="Data01">09/05 中山 4R</span><span class="Icon_GradeType">2勝</span><span class="RaceName"><a href="https://db.netkeiba.com/race/202606040104/">特別</a></span><span class="Data03">定量</span><span class="Data04"><b class="Num">2</b></span><span class="Data05">10頭</span><span class="Data09">芝1800</span></div></li></div></dl>'''
    row={'horse_no':1,'ver3_ability_core':50,'_past_runs':[{'label':'前走','race_id':'202606040104','race_date':'2026-09-05','racecourse':'中山','surface':'芝','distance':1800,'race_name':'3歳以上2勝クラス','position':2,'value':45}]}
    info={'race_name':'3歳以上1勝クラス','racecourse':'中山','surface':'芝','race_date':'2026-09-27'}
    base=evaluate_shadow([row],info,'jra',html=html)
    split=evaluate_class_revision([row],info,'jra',html=html,base_v1=base)
    before=copy.deepcopy((base,split,row))
    result=evaluate_enriched([row],info,'jra',html=html,base_v1=base,base_split=split)
    h=result['horses'][0]
    assert h['jra_v2_finish_quality_score']==pytest.approx(1-2/9)
    assert split['horses'][0]['jra_v2_class_change_score'] is None
    assert h['jra_v2_class_change_score']==1
    assert h['jra_v2_top5_candidate_score']==pytest.approx(split['horses'][0]['jra_v2_top5_candidate_score']+.25)
    assert result['coefficients']==split['coefficients']
    assert (base,split,row)==before
    from core.newspaper_v2_enrichment import replay_enriched_inputs
    assert replay_enriched_inputs(json.loads(json.dumps(result)))==result


def test_future_past_slot_does_not_contribute_A_or_B():
    from core.newspaper_v2_enrichment import enriched_runs
    row={'horse_no':1}
    previous=run();previous['date']='2026-10-01'
    output=enriched_runs(row,[previous],target_date='2026-09-27')
    assert output[0]['audit']['temporal_status']=='not_prior'


def test_netkeiba_header_requires_matching_page_identity():
    from core.newspaper_v2_past_headers import parse_header
    body='<div class="RaceName">3歳以上1勝</div><div class="RaceData01">芝1800</div><div class="RaceData02">3歳以上</div>'
    assert parse_header(body,'202606040104',source='test') is None
    html='<link rel="canonical" href="https://race.netkeiba.com/race/newspaper.html?race_id=202606040104">'+body
    assert parse_header(html,'202606040104',source='test') is not None
    assert parse_header(html,'202606040105',source='test') is None

def test_multiple_saved_matches_do_not_transfer_values():
    from unittest.mock import patch
    from core.newspaper_v2_enrichment import enriched_runs
    first=run();second=run();first['time_index']=100;second['time_index']=20
    newspaper=run();newspaper['race_name']='特別';newspaper['source']='newspaper_past_block'
    with patch('core.newspaper_v2_enrichment.saved_runs',return_value=[first,second]):
        result=enriched_runs({},[newspaper],target_date='2026-09-27')[0]
    assert 'time_index' not in result['values']
    assert 'multiple_saved_matches' in result['audit']['identity_conflicts']
