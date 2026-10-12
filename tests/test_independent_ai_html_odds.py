import pytest
from datetime import datetime
from core.independent_ai import JST
from core.independent_ai_html_odds import parse
from core.independent_ai_odds import evaluate

P={'race_id':'202608040306','mode':'jra','horses':[{'horse_no':1,'name':'ブラックレジェンド'},{'horse_no':2,'name':'テスト馬'}]}
BASE='<link rel="canonical" href="https://race.netkeiba.com/race/newspaper.html?race_id=202608040306">'
DL='<dl><dt class="Horse02"><a href="https://db.netkeiba.com/horse/123/">ブラックレジェンド</a></dt><dt><span id="odds-1_01">8.2</span></dt></dl>'
NOW=datetime(2026,10,11,11,tzinfo=JST)
def test_newspaper_predicted_not_current():
    q=parse((BASE+'<span id="odds_title">予想オッズ</span>'+DL).encode(),P,now=NOW)
    assert q['prices'][0]['low']==8.2 and q['price_status']=='predicted_odds'
    assert q['observed_at'] is None and not evaluate(P,q,NOW)['price_evaluations']
def test_missing_price_time_not_upload_time():
    q=parse((BASE+DL).encode(),P,captured_at=NOW.isoformat(),now=NOW)
    assert q['observed_at'] is None and q['received_at']==NOW.isoformat()
@pytest.mark.parametrize('html',[BASE.replace('202608040306','202608040307')+DL,BASE+DL.replace('ブラックレジェンド','別の馬'),BASE.replace('race.netkeiba.com','nar.netkeiba.com')+DL])
def test_identity_fail_closed(html):
    with pytest.raises(ValueError):parse(html.encode(),P,now=NOW)
def test_scripts_not_executed_and_missing_prices():
    q=parse((BASE+'<script>fetch("secret")</script>').encode(),P,now=NOW)
    assert q['prices']==[] and len(q['missing_kinds'])==3
def test_explicit_table_ranges_and_pair_identity():
    html=BASE+'<div class="OddsUpdateTime">2026年10月11日 10:59:30更新</div><table><tr><th>馬番</th><th>馬名</th><th>複勝</th></tr><tr><td>1</td><td>ブラックレジェンド</td><td>2.1〜3.0</td></tr></table><table><tr><th>馬番1</th><th>馬名1</th><th>馬番2</th><th>馬名2</th><th>ワイド</th></tr><tr><td>1</td><td>ブラックレジェンド</td><td>2</td><td>テスト馬</td><td>5.0-7.0</td></tr></table>'
    q=parse(html.encode(),P,now=NOW)
    assert q['observed_at']=='2026-10-11T10:59:30+09:00'
    assert q['prices']==[{'kind':'place','horses':[1],'low':2.1,'high':3.0},{'kind':'wide','horses':[1,2],'low':5.0,'high':7.0}]
def test_cancelled_and_not_on_sale_not_prices():
    assert parse((BASE+DL.replace('8.2','取消')).encode(),P,now=NOW)['prices']==[]
    assert parse((BASE+DL.replace('8.2','発売前')).encode(),P,now=NOW)['prices']==[]
def test_links_to_other_races_do_not_override_canonical():
    q=parse((BASE+DL+'<a href="https://race.netkeiba.com/race/newspaper.html?race_id=202608040307">7R</a>').encode(),P,now=NOW)
    assert q['race_id']==P['race_id']
