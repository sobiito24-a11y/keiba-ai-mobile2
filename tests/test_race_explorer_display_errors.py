"""A missing display fact must not prevent the rest of a saved race rendering.

The historical Sonoda error has no supplied traceback/input; these are explicitly
synthetic NAR/JRA regressions, not a claimed reproduction of that incident.
"""
from copy import deepcopy

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from core.final_candidate_selection import formal_score
from core.game_race_ui import document, race_header
from tests.test_final_candidate_archive import _saved_event, _view


def _restore(event):
    # Exercise each repository's native archive restore implementation.
    try:
        from core.prediction_snapshot import restore_prediction_result
    except ImportError:
        from core.independent_ai_odds_io import restore_race as restore_prediction_result
    return restore_prediction_result(event['races'][0])


@pytest.mark.parametrize('mode', ['jra', 'nar'])
@pytest.mark.parametrize('missing', [None, '未取得', 'not-a-number', float('nan'), float('inf')])
def test_one_horse_missing_or_invalid_display_facts_keeps_full_saved_race(mode, missing):
    event = _saved_event(mode)
    event_before = deepcopy(event)
    result = _restore(event)
    # Set only display facts; retained formal scores/ranks/marks stay untouched.
    for key in ('距離指数', 'コース指数', '3走平均', '★最高指数', '_days_since_last',
                '_current_load_weight', '_previous_load_weight'):
        if key not in result.overall_table:
            result.overall_table[key] = None
        result.overall_table.at[0, key] = missing
    result.overall_table['_past_runs'] = [
        [dict(label='前走', race_date='not-a-date', value=missing,
              position='未取得', racecourse='園田', surface='ダ', distance='未取得')],
        *[[] for _ in range(len(result.overall_table)-1)],
    ]
    result.race_info.update(racecourse='園田' if mode == 'nar' else '京都', race_number=1)
    tables = [t.copy(deep=True) for t in (result.overall_table, result.horse_evaluation)]
    view = _view(result)
    formal_before = [(h['no'], formal_score(h), h['rank'], h['mark']) for h in view]
    view_before = deepcopy(view)
    html = document(view, 'synthetic-display-missing')
    header = race_header(result)
    soup = BeautifulSoup(html, 'html.parser')
    assert len(soup.select('.lineup-workspace tr[data-horse]')) == 8
    assert '園田' in header if mode == 'nar' else '京都' in header
    assert '未取得' in html
    assert [(h['no'], formal_score(h), h['rank'], h['mark']) for h in view] == formal_before
    assert view == view_before
    for actual, expected in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, expected)
    assert event == event_before


def test_invalid_saved_prediction_error_is_not_suppressed_by_display_route():
    # Invalid predictions must still fail restore rather than render fabricated
    # scores or hide a serious prediction/archive error behind an empty screen.
    event = _saved_event('nar')
    event['races'][0]['prediction_result'] = {}
    with pytest.raises(ValueError):
        _restore(event)
