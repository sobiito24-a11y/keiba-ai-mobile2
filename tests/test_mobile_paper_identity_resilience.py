"""An unverifiable race must not crash the normal Mobile prediction UI."""
from copy import deepcopy
from types import SimpleNamespace
import sys

import pandas as pd

from core.game_race_ui import paper_html
from core.paper_betting_ui import current_decision, render


def result_without_race_id():
    return SimpleNamespace(
        race_mode="jra", race_info={}, source_files={},
        overall_table=pd.DataFrame([{"馬番": 1, "馬名": "履歴馬"}]),
        horse_evaluation=pd.DataFrame([]),
    )


def test_missing_identity_returns_no_optional_paper_decision(monkeypatch):
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    assert current_decision(result_without_race_id(),
                            [{"no": "1", "name": "履歴馬", "ability_rank": 1}]) is None


def test_missing_identity_keeps_paper_html_and_mobile_view_operational(monkeypatch):
    notices = []
    fake_st = SimpleNamespace(session_state={}, info=notices.append)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    result = result_without_race_id()
    before = deepcopy(result.overall_table)
    assert render(result, []) is None
    assert notices and "レースID" in notices[0]
    assert "SABCD" in notices[0]
    message = paper_html([{"mode": "jra", "no": "1", "name": "履歴馬"}], "")
    assert "照合できない" in message
    assert "SABCD" in message
    assert "馬券判断（検証版）" not in message
    pd.testing.assert_frame_equal(result.overall_table, before)


def test_paper_decision_still_works_with_verified_identity(monkeypatch):
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    from core import paper_betting_ui as ui
    identity = {"race_id": "202611230901", "mode": "jra",
                "horses": [{"horse_no": 1, "name": "本番馬"}]}
    state = {"saved": [], "history": []}
    monkeypatch.setattr(ui.o, "identity_from_result", lambda result: identity)
    monkeypatch.setattr(ui.o, "state_for", lambda result: state)
    called = []
    def build(view, mode, verified, quote):
        called.append((view, mode, verified, quote))
        return {"race_id": verified["race_id"]}
    monkeypatch.setattr(ui.p, "build", build)
    view = [{"no": "1", "name": "本番馬", "mode": "jra", "ability_rank": 1}]
    original = deepcopy(view)
    outcome = current_decision(SimpleNamespace(race_mode="jra"), view)
    assert outcome == {"race_id": identity["race_id"]}
    assert called == [(view, "jra", identity, None)]
    assert view == original


def test_all_horses_without_ability_skip_optional_paper_audit(monkeypatch):
    from core import paper_betting_ui as ui
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    def never_build(*args, **kwargs):
        raise AssertionError("Missing source ability must not generate paper bets")
    monkeypatch.setattr(ui.p, "build", never_build)
    assert current_decision(result_without_race_id(), [
        {"no": "1", "name": "保存馬", "ability_rank": "—", "rank": "—"},
        {"no": "2", "name": "保存馬2", "ability_rank": None, "rank": "—"},
    ]) is None


def test_optional_paper_serialization_typeerror_does_not_crash_normal_ui(monkeypatch):
    from core import paper_betting_ui as ui
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    identity = {"race_id": "202611230901", "mode": "jra",
                "horses": [{"horse_no": 1, "name": "本番馬"}]}
    monkeypatch.setattr(ui.o, "identity_from_result", lambda result: identity)
    monkeypatch.setattr(ui.o, "state_for", lambda result: {"saved": [], "history": []})
    # A saved research-side pandas timestamp is not serializable by paper
    # betting's JSON input digest; it must not take down the race viewer.
    view = [{"no": "1", "name": "本番馬", "mode": "jra",
             "rank": 1, "ability_rank": 1, "odds": "—", "formal_member": True,
             "candidate_evidence": {}, "unrelated_audit_date": pd.Timestamp("2026-11-10")}]
    before = deepcopy(view)
    assert current_decision(SimpleNamespace(race_mode="jra"), view) is None
    assert view == before


def test_valid_optional_paper_snapshot_can_still_be_built(monkeypatch):
    from core import paper_betting_ui as ui
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    identity = {"race_id": "202611230901", "mode": "jra",
                "horses": [{"horse_no": 1, "name": "本番馬"}]}
    monkeypatch.setattr(ui.o, "identity_from_result", lambda result: identity)
    monkeypatch.setattr(ui.o, "state_for", lambda result: {"saved": [], "history": []})
    view = [{"no": "1", "name": "本番馬", "mode": "jra",
             "rank": 1, "ability_rank": 1, "odds": "—", "formal_member": True,
             "candidate_evidence": {}}]
    result = current_decision(SimpleNamespace(race_mode="jra"), view)
    assert result and result["race_id"] == identity["race_id"]
    assert result["version"] == ui.p.VERSION
