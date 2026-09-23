import copy,json
from pathlib import Path
import pandas as pd
import pytest
from core.prediction_table_ui import recent_condition_stars,jockey_place_text,prediction_table_html
from core.models import PredictionResult

@pytest.mark.parametrize('row,expected',[
 ({'jockey_course_top3_rate':13,'jockey_course_runs':15},'複勝率 13%'),
 ({'jockey_course_stats_market':'浦和1400m | 7%-10%-23%'},'複勝率 23%'),
 ({'騎手詳細':'森【継続】 複0%'},'複勝率 0%'),
 ({'jockey_course_runs':15},'複勝率 —'),
 ({'jockey_course_stats_market':'勝率 13%'},'複勝率 —')])
def test_jockey_place_only(row,expected):
    before=copy.deepcopy(row)
    assert jockey_place_text(row)==expected
    assert row==before

def test_star_max_duplicate_and_zero():
    runs=[dict(label=label,racecourse='浦和',distance=1400,value=value) for label,value in zip(['前走','2走前','3走前'],[19,19,16])]
    before=copy.deepcopy(runs)
    assert recent_condition_stars({'_past_runs':runs},{'racecourse':'浦和','distance':1400})['★']=='★19'
    assert runs==before
    runs[0]['value']=0
    assert recent_condition_stars({'_past_runs':runs[:1]},{'racecourse':'浦和','distance':1400})['★']=='★0'

@pytest.mark.parametrize('mode,fixture',[('jra','purchase_hanshin_20260921_r8.json'),('nar','purchase_nar_snapshot.json')])
def test_real_recommended_and_all_horses(monkeypatch,mode,fixture):
    import app
    from bs4 import BeautifulSoup
    f=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf-8'))
    p=PredictionResult(race_mode=mode,race_info=f['race_info'],horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall',f['rows'])))
    before=p.horse_evaluation.copy(deep=True);html=[]
    monkeypatch.setattr(app.st,'markdown',lambda x,**k:html.append(x))
    monkeypatch.setattr(app.st,'subheader',lambda *a,**k:None)
    getattr(app,f'render_{mode}_top5_result_summary')(p)
    soup=BeautifulSoup(html[0],'html.parser')
    cards=soup.select('.recommended-horse');assert len(cards)>=5
    assert soup.select('.recommended-horses')[0].get('style').find('repeat(2')>=0
    titles=[h.b.get_text() for h in cards];assert len(titles)==len(set(titles))
    if mode=='jra':
        nav=app.build_jra_purchase_navigation(app.jra_enriched_display_rows(p),race_mode=mode,race_info=p.race_info,saved_rows=p.overall_table.to_dict('records'))
        expected={h['number'] for group in nav['buy_groups'].values() for h in group}|{h['number'] for h in nav['hole_attention']}
    else:
        c=app.nar_comparison_from_result(p);rescue=c['condition_rescue'];rescued={h['number'] for h in rescue}
        expected={h['number'] for h in c['rows'] if h['nar_pure_ability_rank'] and h['nar_pure_ability_rank']<=5}|rescued|{h['number'] for h in app.nar_warning_rows(c['rows'])[:3]}
    import re
    assert {re.search(r'\d+',t)[0] for t in titles}==expected
    html.clear();app.render_horse_summary_cards(p)
    assert len(html)==len(p.horse_evaluation)
    assert before.equals(p.horse_evaluation)
