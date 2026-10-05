import copy
import io
import json
import zipfile
import pytest
from tests.test_material_reconsideration import nar_input, swap_input, result
from core.condition_material_v2 import evaluate_condition_materials, unique_reasons, key_for
from core.material_reconsideration import (
    attach_material_reconsideration, ensure_current_material_reference,
    ensure_condition_materials, material_snapshot, saved_materials, key_for as legacy_key,
)


@pytest.mark.parametrize('mode', ['jra','nar'])
def test_base_values_never_change_badges(mode):
    data=nar_input()
    if mode=='jra':
        data.update(time_status='pre_race',pace='S')
        for h in data['horses']:
            h.update(formal_rank=h['ability_rank'],training_grade='B',corner4_rank=2)
    before=copy.deepcopy(data)
    first=evaluate_condition_materials(data,mode)
    for h in data['horses']:
        h.update(ability_rank=99,ability=-999,formal_rank=99,formal_score=-999,
                 pure_rank=99,pure_score=-999,jra_top5_rank=99,jra_top5_score=-999)
    second=evaluate_condition_materials(data,mode)
    for a,b in zip(first['horses'],second['horses']):
        assert (a['good'],a['concern'],a['good_reasons'],a['concern_reasons']) == (b['good'],b['concern'],b['good_reasons'],b['concern_reasons'])
        assert 'ability' not in a['good_reasons'] and 'formal' not in a['good_reasons']
    assert first['official_top5'] != second['official_top5']  # Ranks only define comparison membership.
    assert before['horses'][0]['ability_rank']==1


def test_nar_base_only_not_positive_and_condition_domain_not_double_counted():
    data=nar_input()
    data['horses'][0].update(distance_rank=None,course_rank=None)
    assert evaluate_condition_materials(data,'nar')['horses'][0]['good']=='—'
    data['horses'][0].update(distance_rank=1,course_rank=1,star_rank=1,away_rank=1)
    assert evaluate_condition_materials(data,'nar')['horses'][0]['good']=='○'
    data['horses'][0].update(jockey_rate=40,jockey_runs=30)
    assert evaluate_condition_materials(data,'nar')['horses'][0]['good']=='◎'


def test_swap_unchanged_and_dedupe():
    from core.nar_material_evidence import evaluate_nar_materials
    data=swap_input()
    a=evaluate_nar_materials(data);b=evaluate_condition_materials(data,'nar')
    assert a['reconsideration']==b['reconsideration']
    assert a['official_top5']==b['official_top5']
    assert a['shadow_top5']==b['shadow_top5']
    assert unique_reasons({'a':'距離・コースとも順位低位','b':'距離・コースとも下半分','c':'調教B','d':'調教B'}) == {'a':'距離・コースとも順位低位','c':'調教B'}


@pytest.mark.parametrize('mode',['jra','nar'])
def test_frozen_a_and_b_never_overwritten_and_old_missing_not_replayed(mode,monkeypatch):
    from core.prediction_history import prediction_zip_bytes
    r=result(mode);attach_material_reconsideration(r)
    a=copy.deepcopy(r.debug_info[legacy_key(mode)])
    r.debug_info.pop(key_for(mode))
    r._material_snapshot_restored=True
    ensure_condition_materials(r)
    assert r.debug_info[legacy_key(mode)]==a
    assert r.debug_info[key_for(mode)]['source_model_version']==a['model_version']
    before=copy.deepcopy(material_snapshot(r))
    import core.material_reconsideration as boundary
    monkeypatch.setattr(boundary,'evaluate_condition_materials',lambda *a:pytest.fail('replay'))
    ensure_condition_materials(r)
    assert material_snapshot(r)==before
    native=json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(r))).read('prediction.json'))
    assert native[key_for(mode)]==before[key_for(mode)]
    assert native[legacy_key(mode)]==a
    old=result(mode)
    ensure_current_material_reference(old,today='2030-01-01')
    assert saved_materials(old)=={}


def test_columns_after_formal_and_ui_does_not_repeat_short_reason():
    from core.prediction_table_ui import JRA_COLUMNS,NAR_COLUMNS,prediction_table_html
    import app
    for mode,cols in [('jra',JRA_COLUMNS),('nar',NAR_COLUMNS)]:
        if mode == 'nar':
            assert '今回プラス' not in cols and '今回注意' not in cols
            continue
        for main in ('最終印','JRAスコア' if mode=='jra' else '純能力'):
            assert cols.index('今回プラス')>cols.index(main)
        assert cols.index('今回プラス')>next(i for i,c in enumerate(cols) if 'AI推定勝率' in c)
        assert cols[-3:-1]==['今回プラス','今回注意']
        r=result(mode);attach_material_reconsideration(r)
        rows=app.prediction_detail_records(r)
        assert '好材料' not in rows[0] and '不安材料' not in rows[0]
        rows[0]['今回プラス']='○ unique-reason'
        html=prediction_table_html(rows[:1],mode)
        # Once in title, once in visible span, never duplicated summary/body.
        assert html.count('unique-reason')==2
