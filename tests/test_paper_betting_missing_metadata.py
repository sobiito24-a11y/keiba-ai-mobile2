"""Sonoda's optional reference metadata must not break the input fingerprint."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import math

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from core import paper_betting as p
from tests.test_paper_betting import horses


@pytest.mark.parametrize("key", ["pure_rank", "corner4_rank"])
@pytest.mark.parametrize("missing", [float("nan"), float("inf"), -float("inf")])
def test_missing_non_candidate_metadata_is_normalized_only_for_the_input_hash(key, missing):
    source = horses()
    source[-1]["reference_selection"] = {key: missing}
    identity = dict(race_id="202650102301", mode="nar")
    before = json.dumps(source, ensure_ascii=False, sort_keys=True)
    expected_source = deepcopy(source)
    expected_source[-1]["reference_selection"][key] = None
    expected = p.build(expected_source, "nar", identity)
    # This is the exact strict-JSON failure that used to stop build().
    with pytest.raises(ValueError, match="Out of range float values"):
        p.digest(dict(horses=source, identity=identity))
    decision = p.build(source, "nar", identity)
    assert decision == expected  # Includes all candidates, tickets and input_hash.
    assert json.dumps(source, ensure_ascii=False, sort_keys=True) == before
    assert math.isfinite(float(decision["strong"][0]["rank"]))
    frozen = p.freeze_user(decision, choice="unrecorded")
    restored = json.loads(json.dumps(frozen, allow_nan=False))
    assert p.verify(restored) == restored


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_finite_input_hash_keeps_the_existing_exact_encoding(mode):
    source = horses()
    source[-1]["reference_selection"] = dict(
        pure_rank=None, corner4_rank=3, jockey_place_rate=0.0,
        nested=[-2.5, True, ("保存値", 1.0)])
    identity = dict(race_id="202650102303", mode=mode)
    before = deepcopy(source)
    encoded = json.dumps(dict(horses=source, identity=identity), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert p.build(source, mode, identity)["input_hash"] == hashlib.sha256(encoded.encode()).hexdigest()
    assert source == before


def test_record_hashing_and_verification_still_reject_nonfinite_tampering():
    source = horses()
    source[0]["reference_selection"] = dict(pure_rank=None)
    record = p.freeze(p.build(source, "nar", dict(race_id="202650102303")))
    assert p.verify(record) is record
    changed = deepcopy(record)
    changed["strong"][0]["reference_selection"]["pure_rank"] = float("nan")
    with pytest.raises(ValueError, match="Out of range float values"):
        p.verify(changed)
    with pytest.raises(ValueError, match="Out of range float values"):
        p.freeze(dict(optional=float("nan")))
    changed = deepcopy(record)
    changed["strong"][0]["rank"] = "99"
    with pytest.raises(ValueError, match="ハッシュが一致しません"):
        p.verify(changed)


def test_unexpected_unsupported_input_is_not_silently_discarded():
    source = horses()
    source[-1]["reference_selection"] = dict(pure_rank=object())
    with pytest.raises(TypeError, match="not JSON serializable"):
        p.build(source, "nar", dict(race_id="202650102303"))


@pytest.mark.parametrize("field", ["pure_rank", "corner4_rank"])
def test_saved_race_app_route_reaches_component_with_nullable_reference_metadata(field, monkeypatch):
    """Keep current_decision/build real after a pandas-null display projection."""
    import app
    import core.game_race_ui as ui
    import core.game_ui_uploads as uploads
    import core.paper_betting_ui as paper_ui
    import core.race_odds_ui as odds_ui
    from core.race_odds import overlay
    from tests.test_final_candidate_archive import _saved_event
    try:
        from core.prediction_snapshot import restore_prediction_result
    except ImportError:
        from core.independent_ai_odds_io import restore_race as restore_prediction_result

    event = _saved_event("nar")
    result = restore_prediction_result(event["races"][0])
    build_view = ui.build_view

    def nullable_view(*args, **kwargs):
        view = build_view(*args, **kwargs)
        # The real archive's dataframe restores an optional null this way.
        # Isolate that projection from this fixture's frozen reference audit.
        target = next(h for h in view if not h["formal_member"])
        target["reference_selection"][field] = float(pd.Series([1, None], dtype=float).iloc[1])
        assert math.isnan(target["reference_selection"][field])
        return view

    monkeypatch.setattr(ui, "build_view", nullable_view)
    tables = [t.copy(deep=True) for t in (result.overall_table, result.horse_evaluation)]
    captured = []

    monkeypatch.setattr(app.st, "session_state", {})
    monkeypatch.setattr(app.st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(app.st, "checkbox", lambda *a, **k: False)
    monkeypatch.setattr(uploads, "uploaded_frames", lambda *a, **k: ({}, []))
    monkeypatch.setattr(odds_ui, "render", lambda result, view: overlay(view, None, "未取得"))
    monkeypatch.setattr(paper_ui, "render", lambda *a, **k: None)

    def render(view, race_key, decision):
        captured.append((ui.document(view, race_key, decision), deepcopy(decision)))

    monkeypatch.setattr(ui, "render_component", render)
    # Keep current_decision()/p.build() real: mocking them would miss the bug.
    app.render_game_prediction(result)
    assert len(captured) == 1
    html, decision = captured[0]
    assert len(BeautifulSoup(html, "html.parser").select("tr[data-horse]")) == 8
    json.dumps(decision, allow_nan=False)
    p.verify(p.freeze(decision))
    for actual, before in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, before)
