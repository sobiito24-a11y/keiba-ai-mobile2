"""Mobile reader regressions: display choices cannot rewrite saved predictions."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from core.independent_ai_odds_io import read_archive, restore_race
from core.model_b import KEY as B_KEY, resolve
from core.model_b_archive import add_to_copy
from core.race_odds import KEY as ODDS_KEY, state_for


def _archive(event):
    body = json.dumps(event, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("snapshot.json", body)
        archive.writestr("manifest.json", json.dumps({"snapshot_sha256": sha256(body).hexdigest()}))
    return output.getvalue()


def _saved_event(mode, failure=None):
    """Eight synthetic runners with distinct A/B/number orders, no PC producer."""
    rows = []
    for no, rank in enumerate((4, 1, 7, 2, 8, 3, 6, 5), 1):
        mark = ("◎", "○", "▲", "✔", "△", "✓", "", "")[rank - 1]
        score = 100 - rank + 0.123456789
        rows.append(dict(
            馬番=no, 馬名=f"保存馬{no}", 枠番=no, 馬年齢="牡4",
            ver3_ability_core=70 + no, market_ability_score=70 + no,
            market_ability_rank=rank, 純能力順位=rank,
            _jockey_course_place_rate=30, _jockey_course_starts=20,
            単勝オッズ=round(2.3 + no * 1.1, 1), 人気=9 - no,
            表示印=mark, ai_current_mark=mark, v1_final_mark=mark,
            jra_top5_rank=rank, jra_top5_score=score,
            pure_ability_top5_group=rank <= 5,
            nar_final_rank=rank, nar_final_mark=mark if rank <= 5 else "",
            nar_check_selected=rank == 6,
            nar_top5_order_score=score if rank <= 5 else None,
            nar_top5_order_version="nar_f2_archive_regression",
            nar_top5_order_status="ordered", netkeiba_corner4_rank=rank,
        ))
    if failure == "missing_input":
        rows[0]["ver3_ability_core"] = None
    race = dict(
        race_id="202650101801", race_mode=mode, race_name="合成保存テスト",
        prediction_result=dict(
            race_mode=mode, race_name="合成保存テスト", logic_version="market",
            created_at="2026-10-18T09:00:00+09:00",
            race_info=dict(race_id="202650101801", race_date="2026-10-18",
                           venue="京都" if mode == "jra" else "大井",
                           distance=1200, head_count=8),
            overall_table=dict(columns=list(rows[0]), records=deepcopy(rows)),
            horse_evaluation=dict(columns=list(rows[0]), records=deepcopy(rows)),
            debug_info={},
        ),
    )
    race[ODDS_KEY] = state_for(restore_race(race))
    output, _ = add_to_copy(_archive(dict(schema_version=1, races=[race])))
    event = read_archive(output)[1]
    if failure == "integrity":
        event["races"][0][B_KEY]["horses"][0]["score"] += 1000
    elif failure == "changed_input":
        event["races"][0]["prediction_result"]["overall_table"]["records"][0]["ver3_ability_core"] += 1000
    return read_archive(_archive(event))[1]


def _view(result):
    from app import prediction_detail_records, sorted_display_rows
    from core.game_race_ui import build_view
    from core.material_reconsideration import saved_materials

    rows = sorted_display_rows(result)
    records = prediction_detail_records(result)
    sources = result.overall_table.to_dict("records")
    return build_view(rows, records, sources, result.race_mode, result.race_info,
                      saved_materials(result))


def _select_model(monkeypatch, view, result, model, warnings):
    import streamlit as st
    from core.model_b_ui import render
    from core.newspaper_v2_inputs import race_id

    monkeypatch.setattr(st, "radio", lambda label, options, **kwargs: options[model])
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "warning", lambda message, **kwargs: warnings.append(message))
    return render(view, race_id(result), result)


def _render_and_check(view):
    from core.final_candidate_selection import candidates, formal_score, select_indices
    from core.game_race_ui import candidate_html

    before = deepcopy(view)
    indices = select_indices(view)
    scored = select_indices(view, "score")
    assert 5 <= len(indices) <= 6
    assert set(indices) == set(scored)
    assert sum(view[i]["formal_member"] for i in indices) == 5
    assert sum(not view[i]["formal_member"] for i in indices) <= 1
    assert all(view[i]["mark"] == "✓" for i in indices if not view[i]["formal_member"])
    assert [int(view[i]["no"]) for i in indices] == sorted(int(view[i]["no"]) for i in indices)
    scores = [formal_score(view[i]) for i in scored]
    known = [value for value in scores if value is not None]
    assert known == sorted(known, reverse=True)
    assert scores == known + [None] * (len(scores) - len(known))

    document = BeautifulSoup(candidate_html(view, candidates(view, "最終候補")), "html.parser")
    desktop = document.select("tr.final-candidate-row[data-candidate-index]")
    mobile = document.select("article.final-mobile-card[data-candidate-index]")
    for shown in (desktop, mobile):
        assert len(shown) == len(indices)
        assert [int(item["data-candidate-index"]) for item in shown] == indices
        assert all(item.select_one("[data-final-toggle]") for item in shown)
    assert len(document.select(".final-detail-row[hidden]")) == len(indices)
    assert document.select(".final-score[hidden]")
    assert view == before
    return {view[i]["no"] for i in indices}


def _snapshot_payload(raw):
    with ZipFile(BytesIO(raw)) as archive:
        return archive.read("snapshot.json")


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_mobile_model_switch_sort_and_render_preserve_archive(mode, monkeypatch):
    from core.final_candidate_selection import formal_score

    event = _saved_event(mode)
    original = deepcopy(event)
    raw_before = _archive(event)
    result = restore_race(event["races"][0])
    report = resolve(result)
    assert report["status"] == "ready" and len(report["horses"]) == 8
    view = _view(result)
    view_before = deepcopy(view)
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    frozen = deepcopy(result.debug_info[B_KEY])
    odds = deepcopy(event["races"][0][ODDS_KEY])
    warnings = []

    import core.model_b as model_b
    monkeypatch.setattr(model_b, "predict", lambda *a, **k: pytest.fail("表示操作でBを再計算"))
    a = _select_model(monkeypatch, view, result, 0, warnings)
    a_candidates = _render_and_check(a)
    b = _select_model(monkeypatch, view, result, 1, warnings)
    assert b is not view
    assert all(h["active_model"] == "B" for h in b)
    assert {h["no"] for h in b if h["formal_member"]} == set(report["top5"])
    _render_and_check(b)
    assert any(h["rank"] != h["model_a"]["rank"] for h in b)
    assert [(h["no"], h["odds"], h.get("popularity")) for h in b] == [
        (h["no"], h["odds"], h.get("popularity")) for h in a]
    for horse in b:
        saved = next(h for h in report["horses"] if h["no"] == horse["no"])
        assert formal_score(horse) == saved["score"]
    a_again = _select_model(monkeypatch, view, result, 0, warnings)
    assert a_again == view_before
    assert _render_and_check(a_again) == a_candidates
    assert not warnings

    for actual, expected in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, expected)
    assert result.debug_info[B_KEY] == frozen
    assert view == view_before and event == original
    raw_after = _archive(event)
    assert _snapshot_payload(raw_after) == _snapshot_payload(raw_before)
    loaded_again = read_archive(raw_after)[1]
    assert loaded_again == original
    assert loaded_again["races"][0][ODDS_KEY] == odds
    assert resolve(restore_race(loaded_again["races"][0])) == report


@pytest.mark.parametrize("mode", ["jra", "nar"])
@pytest.mark.parametrize("failure", ["missing_input", "integrity", "changed_input"])
def test_mobile_unusable_saved_b_keeps_a_and_archive(mode, failure, monkeypatch):
    event = _saved_event(mode, failure)
    before = deepcopy(event)
    result = restore_race(event["races"][0])
    report = resolve(result)
    assert report["status"] == ("incomplete" if failure == "missing_input" else "unavailable")
    assert report["fallback_reason"]
    view = _view(result)
    view_before = deepcopy(view)
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    frozen = deepcopy(result.debug_info[B_KEY])
    expected_candidates = _render_and_check(view)
    warnings = []

    fallback = _select_model(monkeypatch, view, result, 1, warnings)
    assert fallback is view and fallback == view_before
    assert _render_and_check(fallback) == expected_candidates
    assert len(warnings) == 1 and "現行A" in warnings[0]
    assert all(h.get("active_model") != "B" for h in fallback)
    for actual, expected in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, expected)
    assert result.debug_info[B_KEY] == frozen
    assert event == before
    assert read_archive(_archive(event))[1] == before
