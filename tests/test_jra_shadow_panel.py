import json
from copy import deepcopy
from pathlib import Path
from core.jra_corner4_shadow import select, freeze
from core.jra_shadow_panel import candidates, html


def test_golden_centers_and_comparisons():
    cases=json.loads((Path(__file__).parent/'fixtures/jra_corner4_90r_golden.json').read_text(encoding='utf-8'))
    for case in cases:
        view=case['horses'];before=deepcopy(view)
        old=select(view,case['race_id']);new=candidates(view,case['race_id'])
        assert new['shadow']==old['shadow']
        assert new['baseline']==old['baseline']
        assert [h['no'] for h in new['shadow']]==case['expected']
        all_selected=new['shadow']+new['comparison']
        assert len({h['no'] for h in all_selected})==len(all_selected)<=5
        assert all(h['mark']!='—' for h in all_selected)
        assert [h['ability_rank'] for h in new['comparison']]==sorted(h['ability_rank'] for h in new['comparison'])
        assert before==view


def sample():
    return [dict(no=str(i),name=f'馬{i}',mode='jra',mark='◎' if i==1 else '✓',
                 rank=i,ability_rank=i,corner=i) for i in range(1,7)]


def test_missing_short_fields_and_nar():
    v=sample()[:4];assert len(candidates(v)['comparison'])==1
    v[0]['corner']=None;assert candidates(v)['status']=='unavailable'
    assert '未判定' in html(v)
    v=sample();v[0]['mode']='nar';assert html(v)==''
    v=sample();v[3]['mark']='—'
    assert 4 not in [h['no'] for h in candidates(v)['comparison']]


def test_read_only_and_weight_not_penalty():
    v=sample();v[0].update(weight_delta=1.0,jockey_changed=True,jockey_change_text='乗替',plus='—',caution='—')
    before=deepcopy(v);frozen=freeze(v,'x','2026-10-18T01:00:00+00:00')
    result=html(v,'x')
    assert '+1.0kg' in result
    assert 'ポイントUP' in result and 'あり（既存判定）' not in result
    assert '今回注意：—' in result
    assert v==before
    assert freeze(v,'x','2026-10-18T01:00:00+00:00')==frozen
    assert '固定JSONは従来の中心3頭用' in result


def test_official_frames_and_collapsed_details():
    from bs4 import BeautifulSoup
    v=sample();v[0]['frame']=8;v[1]['frame']=8
    root=BeautifulSoup(html(v),'html.parser')
    cards=root.select('.shadow-horse-details')
    assert len(cards)==5 and all(not h.has_attr('open') for h in cards)
    for h in cards[:2]:
        assert h.select_one('.frame').get('title')=='8枠'
        assert '#f295be' in h.select_one('.frame')['style']
    assert cards[2].select_one('.frame').get('title')=='枠番未取得'
    assert cards[0].select_one('summary strong').text=='1 馬1'
    assert cards[0].select_one('.shadow-horse-body') is not None
