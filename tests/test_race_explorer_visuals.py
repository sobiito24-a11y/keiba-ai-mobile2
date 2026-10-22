from copy import deepcopy
import re

from bs4 import BeautifulSoup
import pytest

from core.final_candidate_selection import select_indices
from core.race_explorer_visuals import ability_html, development_html


def horses(count=9):
    return [dict(no=str(i), name='保存馬' + str(i), mode='jra', frame=(i % 8) + 1,
                 ability=100 - i, ability_rank=i + 2, corner=i,
                 style=('逃', '先', '差', '追')[(i - 1) % 4],
                 rank=i, formal_member=i <= 5, mark='✓' if i == 8 else '',
                 profile={'pace': 'H'}, candidate_evidence={'audit': {}})
            for i in range(1, count + 1)]


def document(html):
    return BeautifulSoup(html, 'html.parser')


def dimensions(element):
    return {key: float(number) for key, number in re.findall(r'(left|width):([\d.]+)%', element['style'])}


def test_all_horses_render_read_only_and_pickup_uses_existing_selection():
    view = horses()
    before = deepcopy(view)
    development = document(development_html(view))
    ability = document(ability_html(view))
    assert view == before
    assert len(development.select('.development-horse')) == len(view)
    assert len(ability.select('.ability-row[role="listitem"]')) == len(view)
    assert [button['data-horse-open'] for button in development.select('.development-pickup button')] == [view[i]['no'] for i in select_indices(view)]
    assert all(row.select_one('[data-horse-open]') for row in ability.select('[role="listitem"]'))
    assert '勝率ではありません' in ability.text
    assert not any(mark in development.text for mark in ('◎', '○', '▲', '✔', '✓', '△'))


def test_saved_corner_and_field_size_define_four_consistent_bands():
    view = horses(8)
    doc = document(development_html(view))
    assert [[button['data-horse-open'] for button in lane.select('button')] for lane in doc.select('.development-lane')] == [['1', '2'], ['3', '4'], ['5', '6'], ['7', '8']]
    # The position estimate stays independent of running style.
    assert '逃' in doc.select_one('[data-position-band="2"]').text
    for index, horse in enumerate(view, start=1):
        row = doc.select('.development-horse')[index - 1]
        assert f'4角 {index}番手' in row.text
        badge = row.select_one('.number-badge')
        assert f'{horse["frame"]}枠' in badge['aria-label']
    view[-1]['corner'] = 9
    view[-2]['corner'] = None
    doc = document(development_html(view))
    unknown = doc.select_one('.development-lane-unknown')
    assert {button['data-horse-open'] for button in unknown.select('button')} == {'7', '8'}
    assert '範囲外・位置未判定' in unknown.text
    assert '4角 未取得' in unknown.text


def test_ability_descending_raw_values_share_zero_scale_and_saved_rank():
    view = horses(5)
    for horse, raw, rank in zip(view, [-10, 0, 10, None, float('inf')], [7, 8, 9, 10, 11]):
        horse.update(ability=raw, ability_rank=rank)
    rows = document(ability_html(view)).select('.ability-row[role="listitem"]')
    assert [row['data-horse-no'] for row in rows] == ['3', '2', '1', '4', '5']
    assert [row.select_one('.ability-value small').text for row in rows] == ['9位', '8位', '7位', '10位', '11位']
    assert [dimensions(row.select_one('.ability-bar')) for row in rows[:3]] == [
        {'left': 50.0, 'width': 50.0}, {'left': 50.0, 'width': 0.0}, {'left': 0.0, 'width': 50.0},
    ]
    assert all(dimensions(row.select_one('.ability-zero'))['left'] == 50 for row in rows)
    assert rows[2].select_one('.ability-bar-negative')
    assert not rows[3].select_one('.ability-bar')
    assert rows[4].select_one('.ability-value strong').text == '未取得'


def test_small_ability_differences_stay_small_and_axis_contains_zero():
    view = horses(2)
    view[0]['ability'], view[1]['ability'] = 100, 99.9
    doc = document(ability_html(view))
    bars = [dimensions(bar) for bar in doc.select('.ability-bar')]
    assert bars == [{'left': 0.0, 'width': 100.0}, {'left': 0.0, 'width': 99.9}]
    assert doc.select_one('.ability-tick-start').text == '0'
    assert doc.select_one('.ability-tick-end').text == '100'


@pytest.mark.parametrize('values', [[-10, -5], [0, 0], [None, float('nan')], [1e308, -1e308]])
def test_nonpositive_missing_and_extreme_finite_values_are_safe(values):
    view = horses(2)
    for horse, raw in zip(view, values):
        horse['ability'] = raw
    doc = document(ability_html(view))
    assert len(doc.select('[role="listitem"]')) == 2
    for element in doc.select('[style]'):
        assert not re.search(r'\b(?:nan|inf)\b', element['style'], re.I)
    for bar in doc.select('.ability-bar'):
        assert all(0 <= number <= 100 for number in dimensions(bar).values())
    if values == [0, 0]:
        assert all(dimensions(bar)['width'] == 0 for bar in doc.select('.ability-bar'))
    if values[0] is None:
        assert not doc.select('.ability-bar')
        assert '全頭の純能力指数が未取得' in doc.text


def test_stored_pace_agreement_missing_and_conflict_never_predict_new_pace():
    view = horses(4)
    doc = document(development_html(view, {'netkeiba_pace': 'ハイペース'}))
    assert doc.select_one('.development-pace strong').text == 'H（ハイペース）'
    assert '速い流れになれば' in doc.text
    view[1]['profile']['pace'] = 'S'
    doc = document(development_html(view))
    assert doc.select_one('.development-pace strong').text == '未取得・不一致'
    assert '前残り・差し有利の判断は保留' in doc.text
    for horse in view:
        horse['profile'].clear()
        horse['style'] = '逃'
    doc = document(development_html(view))
    assert doc.select_one('.development-pace strong').text == '未取得・不一致'
    assert '逃げ候補は4頭' in doc.text
    assert '先行争い' in doc.text
    view[0]['candidate_evidence']['audit']['pace'] = {'value': 'S', 'status': 'verified'}
    assert 'S（スローペース）' in document(development_html(view)).select_one('.development-pace').text
    view[0]['candidate_evidence']['audit']['pace']['status'] = 'conflict'
    assert '未取得・不一致' in document(development_html(view)).select_one('.development-pace').text


def test_names_attributes_and_invalid_measurements_are_escaped():
    view = horses(1)
    view[0].update(no='1" onclick="bad()', name='<script>alert("馬")</script>',
                   ability='<svg onload="bad()">', ability_rank=True,
                   corner=float('nan'), style='<img onerror="bad()">', frame=None)
    for html in (development_html(view), ability_html(view)):
        doc = document(html)
        assert not doc.select('script,svg,img,[onclick],[onerror]')
        assert '<script>alert("馬")</script>' in doc.text
        assert all(button['data-horse-open'] == view[0]['no'] for button in doc.select('[data-horse-open]'))
        assert not doc.select_one('.number-badge').has_attr('style')
    doc = document(ability_html(view))
    assert doc.select_one('.ability-value strong').text == '未取得'
    assert doc.select_one('.ability-value small').text == '順位 未取得'


def test_empty_fields_are_renderable():
    for html in (development_html([]), ability_html([])):
        assert '出走馬の情報は未取得' in document(html).text
