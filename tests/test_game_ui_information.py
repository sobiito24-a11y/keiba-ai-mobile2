import copy
from core.game_ui_information import changes,information,reasons
from core.game_race_ui import information_html


def test_no_limit_number_order_and_no_materials_excluded():
    view=[dict(no=str(i),plus='調教A / 調教A',caution='注意' if i%2 else '—',weight_delta=-1,jockey_changed=False,frame=1,name=f'馬{i}',mark='✓') for i in range(18,0,-1)]
    before=copy.deepcopy(view)
    for key in ('materials','changes'):
        group=information(view,key,key)
        assert group['eligible']==18 and group['cards']==[]
        assert [view[i]['no'] for i in group['rows']]==list(map(str,range(1,19)))
        html=information_html(view,group)
        assert html.count('data-top-select=')==18 and 'TOP5' not in html and '位' not in html
    assert view==before
    assert reasons('調教A / 調教A')==['調教A']
    assert information([dict(no='1',plus='—',caution='未計算')],'materials','')['eligible']==0


def test_changes_use_existing_facts_missing_is_not_zero_or_change():
    assert changes({'騎手':'騎手A'})['jockey_change_text']=='—'
    assert changes({'騎手':'騎手A'})['weight_delta'] is None
    assert not changes({'前走騎手':'騎手A'})['jockey_changed']
    assert not changes({'騎手':'騎手B','前走騎手':'未取得'})['jockey_changed']
    v=changes({'騎手':'騎手B','前走騎手':'騎手A','weight_change_market':0})
    assert v['jockey_changed'] and v['weight_delta']==0 and '騎手A → 騎手B' in v['jockey_change_text']
    v=changes({'騎手':'騎手A','前走騎手':'騎手A','_load_weight_change':-2})
    assert not v['jockey_changed'] and v['jockey_change_text']=='継続'
    assert information([dict(no='1',**v)],'changes','')['eligible']==1
