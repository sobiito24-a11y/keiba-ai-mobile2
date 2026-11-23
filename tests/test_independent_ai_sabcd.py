"""Regression tests for the safe pre-race independent-AI display override."""
from copy import deepcopy

import pytest

from core.independent_ai_sabcd import MODEL_ID, annotate_view


def sample():
    view = [
        dict(no=str(i), name=f"競走馬{i}", mode="nar", odds="3.0",
             rank=i, mark="◎" if i == 1 else "—",
             race_context={"race_date": "2026-11-19"},
             unified_sabcd={"grade": "D", "rank": i, "strength": .1,
                            "status": "integrated"})
        for i in range(1, 6)
    ]
    source = dict(
        status="reference", origin="new_prediction", model_id=MODEL_ID,
        mode="nar", race_id="race-123",
        generated_at="2026-11-19T09:00:00+09:00",
        input={"race_id": "race-123", "post_time": "2026-11-19T10:00:00+09:00"},
        horses=[
            dict(horse_no=i, name=f"競走馬{i}", place=p)
            for i, p in enumerate((.71, .52, .31, .16, .09), 1)
        ],
    )
    return view, source


def test_display_grades_are_uncapped_and_original_is_retained():
    view, source = sample()
    saved = deepcopy(source)
    before = deepcopy(view)
    assert annotate_view(view, source, race_id="race-123") is view
    assert [h["unified_sabcd"]["grade"] for h in view] == list("SABCD")
    assert [h["unified_sabcd"]["rank"] for h in view] == list(range(1, 6))
    assert all(h["unified_sabcd_previous"]["grade"] == "D" for h in view)
    assert all(h["unified_sabcd"]["strength"] is None for h in view)
    assert all("未校正" in h["unified_sabcd"]["reason"] for h in view)
    assert source == saved
    for old, new in zip(before, view):
        assert all(old[key] == new[key] for key in old if key != "unified_sabcd")
    # A second call with the same source is not allowed to rewrite official data.
    annotate_view(view, source, race_id="race-123")
    assert all(h["mark"] == ("◎" if i == 1 else "—") for i, h in enumerate(view, 1))


@pytest.mark.parametrize("change", [
    {"origin": "current_reference"},
    {"status": "insufficient"},
    {"model_id": "different_model"},
    {"mode": "jra"},
    {"race_id": "wrong_race"},
    {"generated_at": "2026-11-19T10:01:00+09:00"},
    {"generated_at": "invalid"},
])
def test_non_prestart_or_different_model_never_changes_original_rank(change):
    view, source = sample()
    source.update(change)
    before = deepcopy(view)
    assert annotate_view(view, source, race_id="race-123") == before


def test_invalid_or_partial_horse_identity_abstains_for_whole_race():
    for change in ("name", "partial", "duplicate", "nan"):
        view, source = sample()
        if change == "name":
            source["horses"][1]["name"] = "違う馬"
        elif change == "partial":
            source["horses"].pop()
        elif change == "duplicate":
            source["horses"][2]["horse_no"] = 1
        else:
            source["horses"][2]["place"] = float("nan")
        before = deepcopy(view)
        assert annotate_view(view, source, race_id="race-123") == before


def test_outcome_and_market_data_have_no_effect_on_display_grade():
    view, source = sample()
    annotate_view(view, source, race_id="race-123")
    values = deepcopy([h["unified_sabcd"] for h in view])
    for h in view:
        h["postrace_finish"] = 1
        h["race_results_v1"] = {"finish": 1}
        h["odds"] = "1500.0"
    annotate_view(view, source, race_id="race-123")
    assert [h["unified_sabcd"] for h in view] == values


def test_weak_source_never_invents_missing_scores():
    view, source = sample()
    for p in (None, -1, 1.1, float("inf")):
        test_source = deepcopy(source)
        test_source["horses"][0]["place"] = p
        before = deepcopy(view)
        assert annotate_view(view, test_source, race_id="race-123") == before


def test_zero_or_tied_scores_are_deterministic_and_unlimited():
    view, source = sample()
    for p in source["horses"]:
        p["place"] = .09
    annotate_view(view, source, race_id="race-123")
    assert [h["unified_sabcd"]["grade"] for h in view] == ["D"] * 5
    assert [h["unified_sabcd"]["rank"] for h in view] == [1, 2, 3, 4, 5]


