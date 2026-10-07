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
    assert out['race_commentary'][0].startswith('本線は')
    assert all(f'H{i}' in out['race_commentary'][0] for i in (1,2,3))
    assert '2は前で消耗する可能性' in out['race_commentary'][0]
    assert [h['horse_no'] for h in out['development_plus_horses']]==['6','8']
    assert [h['horse_no'] for h in out['development_caution_horses']]==['7']
    assert not any('H10' in line for line in out['race_commentary'])
    assert '主導権' in out['race_commentary'][2]
    assert len(out['race_commentary'])==4
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
    assert 'H想定では前で消耗する可能性' in html
    assert all(word not in html for word in ('展開注意','展開プラス候補','ペースメーカー','推奨理由ではありません','説明のみ・印は変更しません'))
    assert r.debug_info[KEY]==old


@pytest.mark.parametrize('mode',['jra','nar'])
def test_slow_pace_rank_six_boundary_and_check_priority(mode):
    # Horse numbers/names deliberately unrelated to the supplied race.
    ranks=[1,10,2,7,6,5,4,14]
    styles=['先','差','先','差','先','先','逃','先']
    groups=['front','middle','front','middle','front','front','front','back']
    marks=['◎','○','▲','△','△','✓','','']
    horses=[];rows=[]
    for i in range(8):
        n=str(21+i)
        horses.append(dict(horse_no=n,horse_name='Test'+n,running_style=styles[i],
            corner4_group=groups[i],corner4_position={'front':'先団','middle':'中団','back':'後方'}[groups[i]],
            corner4_rank=ranks[i],position_difference='通常より後ろになる想定' if i==7 else ''))
        rows.append(dict(horse_no=n,jra_top5_rank=i+1,nar_final_rank=i+1,pure_ability_top5_group=i<5,
                         nar_check_selected=i==5,_display_jra_final_mark=marks[i]))
    data=dict(horses=horses,pace_prediction='S',running_style_groups={'逃':['27'],'先':['21','23','25','26','28'],'差':['22','24'],'追':[],'不明':[]})
    out=compose_commentary(data,rows,mode)
    assert out['race_commentary'][0].startswith('本線は◎21Test21、○22Test22、▲23Test23。')
    assert '21・23は前目で運べる' in out['race_commentary'][0]
    assert '22は中団以降' in out['race_commentary'][0] and '差し届かず' in out['race_commentary'][0]
    assert out['development_plus_horses'][0]['horse_no']=='26'
    assert all(h['horse_no']!='27' for h in out['development_plus_horses'])
    assert '✓26Test26' in out['race_commentary'][1] and '展開の鍵は27' in out['race_commentary'][2]
    assert '28Test28' in out['race_commentary'][3]


def test_outside_aim_mark_kept_and_unfavorable_checks_omitted():
    horses=[];rows=[]
    for i,(mark,rank,style) in enumerate([('◎',1,'先'),('○',10,'差'),('▲',2,'先'),
                                       ('△',11,'差'),('△',12,'差'),('✔︎',5,'先'),
                                       ('✓',7,'差'),('✓',16,'差'),('✔︎',3,'逃'),('',4,'逃')],1):
        horses.append(dict(horse_no=str(i),horse_name=f'Horse{i}',running_style=style,
            corner4_rank=rank,corner4_group='front' if rank<=6 else 'back',
            corner4_position='先団' if rank<=6 else '後方',position_difference=''))
        rows.append(dict(horse_no=str(i),jra_top5_rank=i,_display_jra_final_mark=mark))
    data=dict(horses=horses,pace_prediction='S',running_style_groups={'逃':['9','10'],'先':['1','3','6'],'差':['2','4','5','7','8'],'追':[],'不明':[]})
    before=copy.deepcopy((data,rows))
    out=compose_commentary(data,rows,'jra')
    assert out['development_plus_horses'][0]['horse_no']=='6'
    assert '既存✔︎' in out['development_plus_horses'][0]['reason']
    assert '✔︎6Horse6' in out['race_commentary'][1]
    assert '✓7Horse7' not in out['race_commentary'][2] and '✓8Horse8' not in out['race_commentary'][2]
    assert '逃げ候補は9・10' in out['race_commentary'][2]
    assert all(h['horse_no']!='10' for h in out['development_plus_horses'])
    assert not out['development_caution_horses']
    assert out['horses'][5]['formal_mark']=='✔︎' and not out['horses'][5]['selected_check']
    assert (data,rows)==before


@pytest.mark.parametrize('mode',['jra','nar'])
@pytest.mark.parametrize('pace,expected',[('S','プラスになり得る'),('H','消耗する可能性'),('M','脚をためられるか'),('不明','判断を保留')])
def test_position_change_is_interpreted_with_pace(mode,pace,expected):
    horse=dict(horse_no='31',horse_name='Sample',running_style='差',corner4_group='front',
        corner4_position='先団',corner4_rank=3,position_difference='いつもより前で運べる想定')
    row=dict(horse_no='31',jra_top5_rank=6,nar_final_rank=6,pure_ability_top5_group=False,
        nar_check_selected=True,_display_jra_final_mark='✓')
    data=dict(horses=[horse],pace_prediction=pace,running_style_groups={'逃':[],'先':[],'差':['31'],'追':[],'不明':[]})
    before=copy.deepcopy((data,row))
    out=compose_commentary(data,[row],mode)
    assert expected in out['race_commentary'][-1]
    assert bool(out['development_plus_horses'])==(pace=='S')
    assert (data,row)==before
    assert not any('ペースメーカー' in line or '展開注意' in line for line in out['race_commentary'])
