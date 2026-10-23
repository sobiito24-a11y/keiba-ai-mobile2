from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pytest

from core.final_candidate_selection import formal_score
from core.game_race_ui import build_view, document, frame_number
from core.prediction_table_ui import prediction_table_records
from core.race_explorer_common import index_html, number_badge, value
from core.race_explorer_columns import columns
from core.race_explorer_ui import lineup_html


def field(mode='jra', count=9):
    info = dict(race_id='202610220101', race_date='2026-10-22',
                venue='東京', surface='ダート', distance=1600)
    rows = [dict(馬番=i, 馬名=f'保存馬{i}', 枠番=(i % 8) + 1,
                 jra_top5_score=100 - i + .25, jra_top5_rank=i,
                 nar_top5_order_score=100 - i + .25,
                 nar_final_rank=i if i <= 5 else None,
                 pure_ability_top5_group=i <= 5,
                 ver3_ability_core=85 - i, market_ability_rank=i,
                 netkeiba_corner4_rank=i, netkeiba_running_style='先',
                 netkeiba_pace='M', 距離指数=80 - i, コース指数=70 - i,
                 平均指数=60 - i, 最高指数=75 - i,
                 _past_runs=[dict(label=label, race_date=day, racecourse='東京',
                                  surface='ダート', distance=1600, position=finish,
                                  value=score, turn='左')
                             for label, day, finish, score in [
                                 ('前走', '2026-10-01', 2, 60 - i),
                                 ('2走前', '2026-09-01', 3, 65 - i),
                                 ('3走前', '2026-08-01', 4, 70 - i)]])
            for i in range(1, count + 1)]
    records = prediction_table_records(rows, rows, info, mode)
    return rows, records, info, build_view(rows, records, rows, mode, info)


@pytest.mark.parametrize('mode,count', [(mode, count) for mode in ('jra','nar') for count in (12,16,18)])
def test_normal_layout_full_field_manual_checks_and_source_nonmutation(mode, count):
    rows, records, info, view = field(mode, count)
    saved = deepcopy((rows, records, info, view))
    # Deliberately scramble input order; the main table starts in horse order.
    shown = list(reversed(view))
    doc = BeautifulSoup(document(shown, info['race_id']), 'html.parser')
    assert (rows, records, info, view) == saved
    section_order = [heading.text for heading in doc.select(
        '.overview-accordion > summary .overview-title, #lineup-workspace h2')]
    assert section_order == ['レースピックアップ', 'レース展開予想', '純能力の見える化', '全頭予想・比較一覧']
    overviews=doc.select('details.overview-accordion')
    assert [panel['id'] for panel in overviews]==['race-pickup','race-development','race-ability']
    for panel in overviews:
        assert not panel.has_attr('open') and not panel.has_attr('name')
        assert panel.has_attr('data-persist-panel')
        summary=panel.select_one('summary')
        assert summary.select_one('.overview-description').text.strip()
        assert not summary.select('[data-horse-open], .number-badge, .metric-number')
        assert all(horse['name'] not in summary.text for horse in view)
    lineup = doc.select_one('#lineup-workspace')
    runners = lineup.select('tbody tr[data-horse]')
    assert [row['data-horse'] for row in runners] == [str(i) for i in range(1, count + 1)]
    checks = lineup.select('input[type="checkbox"][data-user-check]')
    assert len(checks) == count
    assert all(not check.has_attr('checked') and check.has_attr('aria-label') for check in checks)
    assert [option['value'] for option in lineup.select('#lineup-filter option')] == ['all', 'selected']
    assert lineup.select_one('#clear-user-selection').text == '選択クリア'
    assert not lineup.select_one('#lineup-sort option').has_attr('disabled')
    assert lineup.select_one('#lineup-sort option')['value'] == 'no'
    assert lineup.select_one('.explorer-table-scroll')['tabindex'] == '0'
    for row in runners:
        assert len(row.select('.col-user,.col-number,.col-name')) == 3
        assert row.select_one('.col-name button[data-horse-open]')['data-horse-open'] == row['data-horse']
    headers = [header.select_one('.column-label').text for header in lineup.select('th')]
    assert headers[headers.index('3走前'):headers.index('3走前')+5] == ['3走前', '2走前', '前走', '3走平均', '★最高指数']
    assert ('調教' in headers) == (mode == 'jra')
    specs=columns(view)
    keys=[spec['key'] for spec in specs]
    table_keys=[spec['key'] for spec in specs if not spec.get('table_hidden')]
    assert [header['data-column'] for header in lineup.select('th')]==table_keys
    assert [button['data-column-sort'] for button in lineup.select('[data-column-sort]')]==table_keys
    assert [button['data-column-filter'] for button in lineup.select('[data-column-filter]')]==table_keys
    assert [option['value'] for option in lineup.select('#filter-column option')]==keys
    assert {option['value'] for option in lineup.select('#lineup-sort option')}==set(keys)
    assert not {'rank','ability_rank','distance_rank','course_rank'}.intersection(table_keys)
    assert 'age' not in table_keys and 'age' in keys
    assert {'rank','ability_rank','distance_rank','course_rank'}.issubset(keys)
    assert all(len(row.select('td'))==len(headers) for row in runners)
    assert lineup.select_one('#filter-min')['type']=='number'
    assert lineup.select_one('#filter-max')['type']=='number'
    assert lineup.select_one('#filter-text')['type']=='search'
    assert lineup.select_one('#clear-column-filters') and lineup.select_one('#active-column-filters')
    assert not lineup.select_one('#lineup-filters').has_attr('open')


@pytest.mark.parametrize('mode', ['jra', 'nar'])
def test_normal_workspace_has_formal_a_values_and_retains_twelve_collapsed_analyses(mode):
    _, _, info, view = field(mode)
    # Retaining saved B data must never make it the normal displayed model.
    for horse in view:
        horse['active_model'] = 'A'
        horse['model_b'] = {'score': 9999, 'rank': 1, 'version': 'saved-research'}
        horse['mark'] = '◎'
        horse['explorer_facts'].update(plus=['○ 保存済みの距離実績'], caution=['△ 保存済みの状態材料'])
    before = deepcopy(view)
    doc = BeautifulSoup(document(view, info['race_id']), 'html.parser')
    payload = json.loads(doc.select_one('#race-data').string)
    assert payload['active_model'] == 'A'
    assert payload['experience'] == 'race-comparison'
    assert [horse['sort']['score'] for horse in payload['horses']] == [formal_score(horse) for horse in view]
    assert payload['columns']==columns(view)
    assert all(horse['values']['user'] is False for horse in payload['horses'])
    assert [horse['values']['score'] for horse in payload['horses']]==[formal_score(horse) for horse in view]
    table_rows = doc.select('#lineup-workspace tr[data-horse]')
    assert [float(row.select_one('.col-score b').text) for row in table_rows] == [float(f'{formal_score(horse):g}') for horse in view]
    analyses = doc.select_one('details#detail-analysis')
    assert not analyses.has_attr('open')
    assert len(analyses.select('[role="tab"]')) == 12
    assert [tab['data-tab'] for tab in analyses.select('[role="tab"]')] == [
        'final', 'corner', 'ability', 'course', 'distance', 'training',
        'star', 'away', 'average', 'materials', 'changes', 'research']
    assert len(payload['tabs']) == 12
    assert all(detail.find_parent(id='detail-analysis') is not None for detail in doc.select('.metric-comparison'))
    for section in (doc.select_one('#lineup-workspace'), doc.select_one('#race-pickup')):
        assert not section.select('.mark,.focus-badge,.medal-card,.candidate-group')
        for rank in section.select('.metric-rank'):
            rank.extract()  # Index ranks are distinct from hidden formal marks.
        assert not any(mark in section.text for mark in ('◎', '○', '▲', '✔', '△'))
    assert '保存済みの距離実績' in doc.select_one('#lineup-workspace').text
    assert not doc.select('input[name="research-model"], [data-model-switch]')
    assert view == before


def test_names_in_html_and_embedded_detail_json_remain_escaped():
    _, _, _, view = field(count=1)
    name = '</script><img src=x onerror="bad()">'
    view[0]['name'] = name
    view[0]['explorer_facts']['stable_comment_raw'] = '<script>bad()</script>\nコメント全文'
    doc = BeautifulSoup(document(view, 'race</script>key'), 'html.parser')
    assert not doc.select('img,[onerror],[onclick]')
    assert len(doc.select('script')) == 2
    payload = json.loads(doc.select_one('#race-data').string)
    assert payload['names'] == ['1 ' + name]
    detail = BeautifulSoup(payload['cards'][0], 'html.parser')
    assert not detail.select('script,img')
    assert name in detail.text
    assert detail.select_one('.detail-comment-original').text == '<script>bad()</script>\nコメント全文'
    assert 'horse-detail-1' == doc.select_one('#lineup-workspace [data-horse-open]')['aria-controls']


@pytest.mark.parametrize('raw', [float('inf'), -float('inf'), 'INF', '-Infinity', 'NaN'])
def test_common_values_never_display_nonfinite_indices(raw):
    assert value(raw) == '未取得'
    assert '未取得' in index_html({'value': raw, 'rank': 1})
    assert '位' not in index_html({'value': 50, 'rank': 1.5})
    assert '未取得' in index_html('invalid saved metric')


@pytest.mark.parametrize('aliases,expected', [
    ({'枠番': 3}, 3), ({'枠番': 3, 'frame_no': 3}, 3),
    ({'枠番': 3, 'frame_no': 4}, None),
    ({'枠番': 3, 'frame_no': 9}, None),
    ({'枠番': 3, 'frame_no': True}, None),
    ({'frame_no': 0}, None), ({'frame_no': 2.5}, None),
    ({'馬番': 8}, None), ({'枠番': None}, None),
])
def test_frame_aliases_are_explicit_consistent_and_in_range(aliases, expected):
    assert frame_number(aliases) == expected
    badge = BeautifulSoup(number_badge({'no': '18', 'frame': frame_number(aliases)}), 'html.parser').span
    assert badge.has_attr('style') == (expected is not None)


def test_verified_uploaded_frame_only_fills_missing_metadata_and_never_conflict():
    row = dict(馬番=1, 馬名='保存馬1')
    records = prediction_table_records([row], [row], {}, 'jra')
    frames = {'1': dict(frame=8, name='保存馬1')}
    assert build_view([row], records, [row], 'jra', frames=frames)[0]['frame'] == 8
    assert build_view([row], records, [row], 'jra', frames={'1': dict(frame=8, name='別馬')})[0]['frame'] is None
    for aliases in ({'枠番': 3, 'frame_no': 4}, {'枠番': 3, 'frame_no': 9}):
        conflicting = dict(row, **aliases)
        before = deepcopy((conflicting, frames))
        shown = build_view([conflicting], records, [conflicting], 'jra', frames=frames)
        assert shown[0]['frame'] is None
        assert (conflicting, frames) == before
    original, displayed = dict(row, 枠番=3), dict(row, 枠番=4)
    assert build_view([displayed], records, [original], 'jra', frames=frames)[0]['frame'] is None


def test_empty_main_table_has_controls_and_safe_header():
    doc = BeautifulSoup(lineup_html([]), 'html.parser')
    assert not doc.select('tr[data-horse], input[data-user-check]')
    assert doc.select_one('#lineup-filter')
    assert '全0頭' in doc.text
