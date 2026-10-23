"""Price display requires a new observation or an explicit saved-price choice."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from core import race_odds as odds
from core.race_odds_ui import render
from tests.test_race_odds import identity, quote


def prices(mode="jra", *, manual=False, partial=False):
    source = quote(mode, n=3)
    source["prices"] = [p for p in source["prices"] if p["kind"] == "win"]
    source["popularity"] = {"1": 2, "2": 1, "3": 3}
    if manual:
        source.update(source="manual_html_fixture", acquisition_method="manual_html",
                      received_at="2026-10-18T15:23:59+09:00",
                      observed_at="2026-10-18T14:03:02+09:00")
        for price in source["prices"]:
            price["low"] = price["high"] = 9.4
    if partial:
        source["prices"] = [source["prices"][1]]
        source["popularity"] = {"2": 3}
    return odds.validate(source, identity(mode, n=3))


def setup_ui(monkeypatch, state, selection=None, mode="jra", *, session=None,
             files=None, fetch=None, screenshot=None):
    import streamlit as st
    import core.independent_ai_odds as provider_module
    import core.race_odds_screenshot_ui as screenshot_ui

    if session is None:
        session = {"unrelated_comparison_state": {"checks": ["1", "3"], "sort": "odds"}}
    captured = {"captions": []}
    ident = identity(mode, n=3)
    monkeypatch.setattr(st, "session_state", session)
    monkeypatch.setattr(st, "secrets", {})
    monkeypatch.setattr(st, "button", lambda label, **k:
                        label == "全頭分をまとめて取り込む" and bool(files)
                        or label == "オッズ更新" and fetch is not None)
    monkeypatch.setattr(st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "spinner", lambda *a, **k: nullcontext())
    monkeypatch.setattr(st, "file_uploader", lambda *a, **k: files)
    monkeypatch.setattr(st, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(st, "markdown", lambda text, **k: captured["captions"].append(text))
    monkeypatch.setattr(st, "info", lambda *a, **k: None)
    monkeypatch.setattr(provider_module, "provider", lambda *a, **k:
                        SimpleNamespace(available=fetch is not None, fetch=lambda rid: deepcopy(fetch)))
    def render_screenshot(ident, current, key):
        if screenshot is not None:
            current["history"] = odds.merge(current["history"], [screenshot], ident)
    monkeypatch.setattr(screenshot_ui, "render", render_screenshot)
    monkeypatch.setattr(odds, "identity_from_result", lambda result: deepcopy(ident))
    monkeypatch.setattr(odds, "state_for", lambda result: deepcopy(state))

    def selectbox(label, options, *, index, format_func, key):
        assert label == "表示するオッズ観測"
        captured.update(default=index, key=key, labels=[format_func(i) for i in options])
        return index if selection is None else selection

    monkeypatch.setattr(st, "selectbox", selectbox)
    view = [dict(no=str(no), name=f"馬{no}", odds="88.8", popularity=1,
                 score=100-no, rank=no, mark="◎", formal_member=True,
                 candidate_formal_score=100-no, sort_values={}) for no in range(1, 4)]
    result = SimpleNamespace(race_info=dict(race_date="2026-10-18", start_time="16:00"))
    return result, view, captured, session


def manual_upload(mode="jra"):
    host = "race.netkeiba.com" if mode == "jra" else "nar.netkeiba.com"
    raw = ('<link rel="canonical" href="https://' + host +
           '/odds/index.html?race_id=202608040511">'
           '<time data-odds-updated-at="2026-10-18T14:03:02+09:00"></time>'
           '<table><tr><th>馬番</th><th>馬名</th><th>単勝</th><th>人気</th></tr>'
           '<tr><td>2</td><td>馬2</td><td>9.4</td><td>3</td></tr></table>').encode()
    upload = SimpleNamespace(name="fresh.html", getvalue=lambda: raw)
    quoted = odds.import_files([(upload.name, raw)], identity(mode, n=3),
                               now=datetime.fromisoformat("2026-10-18T15:23:59+09:00"))[0]
    return upload, quoted


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_saved_prediction_prices_start_missing_until_explicit_selection(mode, monkeypatch):
    state = dict(schema_version=1, saved=[prices(mode)], history=[])
    result, view, ui, session = setup_ui(monkeypatch, state, mode=mode)
    before = deepcopy((view, state, session["unrelated_comparison_state"]))
    displayed = render(result, view)
    assert ui["default"] == 0
    assert ui["labels"][0] == "未取得：新しいHTMLを取り込んでください"
    assert "保存時オッズ" in ui["labels"][1]
    assert "_observation_v3_0_2" in ui["key"]
    assert all(h["odds"] == "—" and h["popularity"] is None for h in displayed)
    assert [(h["score"], h["rank"], h["mark"]) for h in displayed] == [
        (h["score"], h["rank"], h["mark"]) for h in view]
    assert (view, state, session["unrelated_comparison_state"]) == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_user_can_explicitly_view_saved_observation_without_importing(mode, monkeypatch):
    state = dict(schema_version=1, saved=[prices(mode)], history=[])
    result, view, ui, _ = setup_ui(monkeypatch, state, selection=1, mode=mode)
    before = deepcopy((view, state))
    displayed = render(result, view)
    assert ui["default"] == 0
    assert [h["odds"] for h in displayed] == ["2.0"] * 3
    assert [h["popularity"] for h in displayed] == [2, 1, 3]
    assert all(h["odds_label"] == "保存時オッズ" for h in displayed)
    assert (view, state) == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_archived_manual_history_requires_explicit_selection_and_keeps_clocks_distinct(mode, monkeypatch):
    imported = prices(mode, manual=True, partial=True)
    state = dict(schema_version=1, saved=[prices(mode)], history=[imported])
    result, view, ui, _ = setup_ui(monkeypatch, state, selection=2, mode=mode)
    before = deepcopy((view, state))
    displayed = render(result, view)
    assert ui["default"] == 0
    assert "HTML取込日時" in ui["labels"][2]
    assert "15:23:59" in ui["labels"][2] and "14:03:02" not in ui["labels"][2]
    assert [h["odds"] for h in displayed] == ["—", "9.4", "—"]
    assert [h["popularity"] for h in displayed] == [None, 3, None]
    captions = "\n".join(ui["captions"])
    assert "HTML取込日時：2026/10/18 15:23:59 JST" in captions
    assert "提供元更新：2026/10/18 14:03:02 JST" in captions
    assert "HTML取込日時はサイトから価格を取得した日時ではありません" in captions
    assert (view, state) == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_archived_history_is_not_automatically_active_on_initial_display(mode, monkeypatch):
    state = dict(schema_version=1, saved=[prices(mode)], history=[prices(mode, manual=True)])
    result, view, ui, session = setup_ui(monkeypatch, state, mode=mode)
    before = deepcopy((view, state))
    displayed = render(result, view)
    assert ui["default"] == 0
    assert all(h["odds"] == "—" and h["popularity"] is None for h in displayed)
    runtime = next(v for key, v in session.items() if key.endswith("_observation_runtime_v3"))
    assert runtime["active_observation"] is None
    assert runtime["seen_history_ids"] == [state["history"][0]["observation_id"]]
    assert (view, state) == before


@pytest.mark.parametrize("mode,duplicate", [("jra", False), ("nar", False), ("jra", True), ("nar", True)])
def test_fresh_html_import_activates_requested_quote_even_when_already_in_archive(mode, duplicate, monkeypatch):
    upload, incoming = manual_upload(mode)
    state = dict(schema_version=1, saved=[prices(mode)], history=[incoming] if duplicate else [])
    # First display treats both archived saved and historical observations as inactive.
    result, view, initial, session = setup_ui(monkeypatch, state, mode=mode)
    assert all(h["odds"] == "—" for h in render(result, view))
    old_key = initial["key"]
    result, view, ui, _ = setup_ui(monkeypatch, state, mode=mode, files=[upload], session=session)
    before = deepcopy((view, state, session["unrelated_comparison_state"]))
    displayed = render(result, view)
    assert ui["default"] == 2 and ui["key"] != old_key
    assert [h["odds"] for h in displayed] == ["—", "9.4", "—"]
    assert [h["popularity"] for h in displayed] == [None, 3, None]
    assert "提供元更新：2026/10/18 14:03:02 JST" in "\n".join(ui["captions"])
    current = next(v for key, v in session.items()
                   if key.startswith("race_prices_") and isinstance(v, dict) and "schema_version" in v)
    assert set(current) == {"schema_version", "saved", "history"}
    assert len(current["history"]) == 1
    assert (view, state, session["unrelated_comparison_state"]) == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_new_screenshot_history_activates_after_session_metadata_is_initialized(mode, monkeypatch):
    archived = prices(mode)
    fresh = prices(mode, manual=True, partial=True)
    state = dict(schema_version=1, saved=[], history=[archived])
    result, view, ui, _ = setup_ui(monkeypatch, state, mode=mode, screenshot=fresh)
    displayed = render(result, view)
    assert ui["default"] == 2
    assert [h["odds"] for h in displayed] == ["—", "9.4", "—"]


def test_fetch_and_explicit_user_choice_persist_without_reactivating_archived_history(monkeypatch):
    fetched = prices()
    state = dict(schema_version=1, saved=[], history=[fetched])
    result, view, ui, session = setup_ui(monkeypatch, state, fetch=fetched)
    displayed = render(result, view)
    assert ui["default"] == 1 and all(h["odds"] == "2.0" for h in displayed)
    activated_key = ui["key"]
    # No new import: the current-session active quote persists on an ordinary rerender.
    result, view, ui, _ = setup_ui(monkeypatch, state, session=session)
    assert all(h["odds"] == "2.0" for h in render(result, view))
    assert ui["default"] == 1 and ui["key"] == activated_key
    # An explicit choice of missing remains missing on subsequent rerenders.
    result, view, ui, _ = setup_ui(monkeypatch, state, session=session, selection=0)
    assert all(h["odds"] == "—" for h in render(result, view))
    result, view, ui, _ = setup_ui(monkeypatch, state, session=session)
    assert all(h["odds"] == "—" for h in render(result, view))
    assert ui["default"] == 0 and ui["key"] == activated_key


def test_empty_observation_list_still_exposes_explicit_missing_state(monkeypatch):
    state = dict(schema_version=1, saved=[], history=[])
    result, view, ui, _ = setup_ui(monkeypatch, state)
    displayed = render(result, view)
    assert ui["default"] == 0 and len(ui["labels"]) == 1
    assert all(h["odds"] == "—" and h["popularity"] is None for h in displayed)
