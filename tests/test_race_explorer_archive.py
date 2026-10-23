"""The mobile comparison UI must preserve a restored .keiba prediction."""
from contextlib import nullcontext
from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from core.final_candidate_selection import formal_score, select_indices
from core.independent_ai_odds_io import read_archive, restore_race
from core.model_b import KEY as B_KEY, resolve
from core.race_odds import KEY as ODDS_KEY
from tests.test_final_candidate_archive import _archive, _saved_event, _snapshot_payload, _view


def _render_comparison(view):
    from core.game_race_ui import document
    from core.race_explorer_cards import detail_html

    before = deepcopy(view)
    doc = BeautifulSoup(document(view, "saved-mobile-comparison"), "html.parser")
    payload = json.loads(doc.select_one("script#race-data").string)
    assert payload["experience"] == "race-comparison"
    assert payload["active_model"] == "A"
    assert payload["cards"] == [detail_html(horse) for horse in view]
    assert [horse["no"] for horse in payload["horses"]] == [horse["no"] for horse in view]
    for saved, horse in zip(payload["horses"], view):
        assert saved["sort"]["final_score"] == formal_score(horse)

    selected = select_indices(view, "no")
    scored = select_indices(view, "score")
    assert set(selected) == set(scored)
    assert 5 <= len(selected) <= 6
    expected = [view[index]["no"] for index in selected]
    assert len(expected) == len(set(expected))
    pickup = doc.select(".pickup-card[data-horse-open]")
    assert [card["data-horse-open"] for card in pickup] == expected
    assert all(card["aria-controls"] == "horse-detail-" + card["data-horse-open"] for card in pickup)
    assert not any(mark in " ".join(card.get_text(" ") for card in pickup) for mark in "◎○▲✔△✓")

    table = doc.select_one(".lineup-workspace table")
    rows = table.select("tbody tr[data-horse]")
    assert [row["data-horse"] for row in rows] == sorted(
        [horse["no"] for horse in view], key=int)
    assert len(rows) == len(view) == 8
    checks = table.select('input[type="checkbox"][data-user-check]')
    assert len(checks) == len(view)
    assert {check["data-user-check"] for check in checks} == {horse["no"] for horse in view}
    assert all(not check.has_attr("checked") for check in checks)
    for row in rows:
        opener = row.select_one("[data-horse-open]")
        assert opener["data-horse-open"] == row["data-horse"]
        assert opener["aria-controls"] == "horse-detail-" + row["data-horse"]
        assert not row.select(".mark,.focus-badge,.candidate-badge,[data-ai-candidate]")
        for rank in row.select('.metric-rank'):
            rank.extract()  # Permit index-only ranks, never the formal marks.
        assert not any(mark in row.get_text(" ") for mark in "◎○▲✔△✓")
    headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
    assert headers.index("3走前") < headers.index("2走前") < headers.index("前走")
    assert headers.index("前走") < headers.index("3走平均") < headers.index("★最高指数")
    assert view == before
    return expected


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_mobile_comparison_render_and_reorder_preserve_native_archive(mode, monkeypatch):
    from core.model_b_ui import project
    import core.model_b as model_b

    event = _saved_event(mode)
    original = deepcopy(event)
    raw_before = _archive(event)
    result = restore_race(event["races"][0])
    report = resolve(result)
    assert report["status"] == "ready" and len(report["horses"]) == 8
    view = _view(result)
    before = deepcopy(view)
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    frozen = deepcopy(result.debug_info[B_KEY])
    odds = deepcopy(event["races"][0][ODDS_KEY])
    monkeypatch.setattr(model_b, "predict", lambda *a, **k: pytest.fail("UI rendering must not recalculate B"))

    expected = _render_comparison(view)
    by_score = sorted(view, key=lambda horse: (
        formal_score(horse) is None,
        -formal_score(horse) if formal_score(horse) is not None else 0,
        int(horse["no"])))
    assert _render_comparison(by_score) == expected
    assert _render_comparison(list(reversed(view))) == expected

    research = project(view, resolve(result))
    assert research is not view
    assert all(horse["active_model"] == "B" for horse in research)
    assert {horse["no"] for horse in research if horse["formal_member"]} == set(report["top5"])
    for horse in research:
        saved = next(item for item in report["horses"] if item["no"] == horse["no"])
        assert formal_score(horse) == saved["score"]
    assert [(horse["no"], horse["odds"], horse.get("popularity")) for horse in research] == [
        (horse["no"], horse["odds"], horse.get("popularity")) for horse in view]

    for actual, saved in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, saved)
    assert result.debug_info[B_KEY] == frozen
    assert view == before and event == original
    raw_after = _archive(event)
    assert _snapshot_payload(raw_after) == _snapshot_payload(raw_before)
    restored = read_archive(raw_after)[1]
    assert restored == original
    assert restored["races"][0][ODDS_KEY] == odds
    assert resolve(restore_race(restored["races"][0])) == report


@pytest.mark.parametrize("mode", ["jra", "nar"])
@pytest.mark.parametrize("failure", [None, "missing_input", "integrity", "changed_input"])
def test_mobile_normal_app_route_defaults_to_a_without_loading_research_b(mode, failure, monkeypatch):
    import app
    import core.game_race_ui as race_ui
    import core.model_b as model_b
    import core.model_b_ui as research_ui
    import core.paper_betting_ui as paper_ui
    import core.race_odds_ui as odds_ui

    event = _saved_event(mode, failure)
    original = deepcopy(event)
    result = restore_race(event["races"][0])
    expected = _view(result)
    frozen = deepcopy(result.debug_info[B_KEY])
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    calls, choices = [], []

    def default_checkbox(label, *args, **kwargs):
        assert kwargs.get("value", False) is False
        choices.append(label)
        return False

    def fail_research(*args, **kwargs):
        pytest.fail("The normal purchase comparison must not invoke research B")

    monkeypatch.setattr(app.st, "session_state", {})
    monkeypatch.setattr(app.st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(app.st, "checkbox", default_checkbox)
    monkeypatch.setattr(app.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(odds_ui, "render", lambda result, view: view)
    monkeypatch.setattr(paper_ui, "current_decision", lambda *a, **k: None)
    monkeypatch.setattr(paper_ui, "render", lambda *a, **k: None)
    monkeypatch.setattr(race_ui, "render_component", lambda view, *a, **k: calls.append(deepcopy(view)))
    monkeypatch.setattr(model_b, "resolve", fail_research)
    monkeypatch.setattr(model_b, "predict", fail_research)
    monkeypatch.setattr(research_ui, "render", fail_research)
    app.render_game_prediction(result)

    assert choices and len(calls) == 1
    shown = calls[0]
    assert all(horse.get("active_model", "A") == "A" for horse in shown)
    assert [(horse["no"], horse["rank"], horse["mark"], formal_score(horse)) for horse in shown] == [
        (horse["no"], horse["rank"], horse["mark"], formal_score(horse)) for horse in expected]
    for actual, saved in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, saved)
    assert result.debug_info[B_KEY] == frozen and event == original
