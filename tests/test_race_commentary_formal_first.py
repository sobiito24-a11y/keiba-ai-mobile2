import copy
import pytest
from core.race_development import compose_commentary, render_html, KEY
from core.models import PredictionResult


@pytest.mark.parametrize('mode',['jra','nar'])
def test_formal_first_checks_only_and_conflict_caution(mode):
    horses=[];rows=[]
    for i in range(1,11):
        horses.append(dict(horse_no=str(i),horse_name=f'H{i}',running_style='差',corner4_group='middle',
            corner4_position='中団',corner4_rank=i,position_difference='',average_index=1000 if i==10 else 10))
        rows.append(dict(馬番=i,jra_top5_rank=i,nar_final_rank=i,pure_ability_top5_group=i<=5,
            nar_check_selected=i in (6,7,8),_display_jra_final_mark={1:'◎',2:'○',3:'▲',4:'✔︎',5:'△',6:'✓',7:'✓',8:'✓'}.get(i,'')))
    horses[1].update(running_style='先',corner4_group='front',corner4_position='先団')
    horses[6].update(corner4_group='front',corner4_position='先団',position_difference='いつもより前で運べる想定')
    data=dict(horses=horses,pace_prediction='H',running_style_groups={'逃':[],'先':['2'],'差':list(map(str,[1,3,4,5,6,7,8,9,10])),'追':[],'不明':[]})
    original=copy.deepcopy((data,rows))
    out=compose_commentary(data,rows,mode)
    assert out['race_commentary'][0].startswith('正式Top5・最終印の本線は')
    assert all(f'H{i}' in out['race_commentary'][0] for i in (1,2,3))
    assert '向かい風' in out['race_commentary'][2]
    assert [h['horse_no'] for h in out['development_plus_horses']]==['6','8']
    assert [h['horse_no'] for h in out['development_caution_horses']]==['7']
    assert not any('H10' in line for line in out['race_commentary'])
    assert 'ペースメーカー' in out['race_commentary'][-1]
    assert (data,rows)==original
    for pace in ['M','不明']:
        assert not compose_commentary(dict(data,pace_prediction=pace),rows,mode)['development_plus_horses']


def test_old_saved_watch_is_not_a_recommendation_or_overwritten():
    h=dict(horse_no='9',horse_name='UNMARKED',running_style='差',corner4_position='先団',
           corner4_group='front',corner4_rank=2,position_difference='いつもより前で運べる想定')
    old=dict(model_version='race_development_display_v1',generated_at='frozen',horses=[h],horse_count=1,
        running_style_groups={'逃':[],'先':[],'差':['9'],'追':[],'不明':[]},corner4_groups={'front':['9'],'middle':[],'back':[],'unknown':[]},
        pace_prediction='H',race_commentary=['old recommendation'],development_summary=[],development_watch_horses=[dict(h,reason='old')])
    r=PredictionResult(race_mode='nar',debug_info={KEY:copy.deepcopy(old)})
    html=render_html(r,True)
    assert '展開注目' not in html and 'old recommendation' not in html
    assert '展開注意' in html and '推奨理由ではありません' in html
    assert r.debug_info[KEY]==old
