"""Evidence diagnostics must remain independent from formal predictions."""
import copy
import importlib.util
import io
import json
import zipfile

import pandas as pd
import pytest

from core.models import PredictionResult
from core.nar_material_evidence import evaluate_nar_materials
from core.jra_material_evidence import evaluate_jra_materials
from core.material_reconsideration import (
    attach_material_reconsideration, key_for, material_cell,
    material_snapshot, reconsideration_html, saved_materials,
)


def nar_input():
    return dict(race_id="202631093001", date="2026-09-30", horses=[
        dict(horse_no=str(n), horse_name=f"馬{n}", ability_rank=n, ability=80-n,
             distance=70-n, course=70-n, star=None, away=None,
             distance_rank=n, course_rank=n, star_rank=None, away_rank=None,
             runs=[], corner4=None, pace=None, jockey_rate=None, jockey_runs=None)
        for n in range(1, 9)])


def swap_input():
    data = nar_input()
    data["horses"][4].update(distance_rank=8, course_rank=8, jockey_rate=5, jockey_runs=30)
    for h in data["horses"][5:7]:
        h.update(distance_rank=1, course_rank=2, jockey_rate=40, jockey_runs=30)
    return data


def result(mode="nar"):
    rows = [dict(馬番=n, 馬名=f"馬{n}", ability_rank=n, ver3_ability_core=80-n,
                 market_ability_rank=n, market_ability_score=80-n,
                 jra_top5_rank=n, jra_top5_score=90-n, training_market="B 良好",
                 距離指数=70-n, コース指数=70-n, netkeiba_corner4_rank=n,
                 provider_pace_market="S", ver3_final_mark="◎" if n == 1 else "△",
                 _past_runs=[dict(race_date="2026-09-01", racecourse="京都",
                                 surface="芝", distance=1200, label="前走", position=n, value=70-n)])
            for n in range(1, 9)]
    return PredictionResult(
        race_mode=mode, created_at="2026-10-03T08:00:00",
        race_info=dict(race_id="202608040111", race_date="2026-10-03",
                       racecourse="京都", distance=1200, surface="芝", race_data="15:30発走"),
        horse_evaluation=pd.DataFrame(rows), overall_table=pd.DataFrame(rows[::-1]))


def test_nar_strong_requires_multiple_independent_domains():
    data = nar_input()
    h = data["horses"][5]
    h.update(distance_rank=1, course_rank=1, star_rank=1, away_rank=1)
    assert evaluate_nar_materials(data)["horses"][5]["good"] == "○"
    h.update(jockey_rate=30, jockey_runs=20)
    assert evaluate_nar_materials(data)["horses"][5]["good"] == "◎"
    h.update(distance_rank=8, course_rank=8, star_rank=None, away_rank=None,
             jockey_rate=None, jockey_runs=None)
    assert evaluate_nar_materials(data)["horses"][5]["concern"] == "△"
    h.update(jockey_rate=10, jockey_runs=20)
    assert evaluate_nar_materials(data)["horses"][5]["concern"] == "⚠"


def test_missing_is_not_negative_or_positive():
    data = nar_input()
    h = data["horses"][-1]
    for key in ("ability_rank", "distance", "course", "distance_rank", "course_rank"):
        h[key] = None
    out = evaluate_nar_materials(data)["horses"][-1]
    assert out["good"] == out["concern"] == "—"
    assert out["missing"] and out["distance"] is None


def test_one_pair_canonical_rank_priority_and_input_unchanged():
    data = swap_input()
    before = copy.deepcopy(data)
    out = evaluate_nar_materials(data)
    assert data == before
    assert out["official_top5"] == ["1", "2", "3", "4", "5"]
    assert out["shadow_top5"] == ["1", "2", "3", "4", "6"]
    assert out["reconsideration"]["added"] == "6"
    assert out["reconsideration"]["removed"] == "5"
    assert len(set(out["shadow_top5"]) - set(out["official_top5"])) == 1
    data["horses"][4]["jockey_rate"] = None
    assert evaluate_nar_materials(data)["reconsideration"] is None


def test_saved_tie_at_fifth_is_not_trimmed():
    data = swap_input()
    data["horses"][5]["ability_rank"] = 5
    out = evaluate_nar_materials(data)
    assert len(out["official_top5"]) == 6
    assert out["shadow_top5"] == out["official_top5"]
    assert not out["eligible_box"] and out["reconsideration"] is None


def test_nar_training_age_load_alone_are_not_jra_rules():
    data = nar_input()
    h = data["horses"][-1]
    baseline = evaluate_nar_materials(data)["horses"][-1]
    h.update(training_grade="D", rest_days=365, load_change=3, age=9)
    out = evaluate_nar_materials(data)["horses"][-1]
    assert out["good_reasons"] == baseline["good_reasons"]
    assert out["concern_reasons"] == baseline["concern_reasons"]


def test_jra_formal_rank_not_ability_and_no_shadow_feedback():
    data = dict(time_status="pre_race", pace="S", horses=[
        dict(horse_no=str(n), horse_name=f"馬{n}", formal_rank=n,
             pure_rank=9-n, corner4_rank=None, training_grade=None)
        for n in range(1, 9)])
    data["horses"][4].update(corner4_rank=10, training_grade="D")
    data["horses"][5].update(corner4_rank=1, training_grade="B")
    old = copy.deepcopy(data)
    out = evaluate_jra_materials(data)
    assert data == old
    assert out["reconsideration"]["added"] == "6"
    assert out["reconsideration"]["removed"] == "5"
    assert out["horses"][0]["good_reasons"]["formal"] == "正式JRA 1位"
    data["is_jump"] = True
    assert evaluate_jra_materials(data)["horses"] == []


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_adapter_ignores_odds_popularity_current_results_and_preserves_tables(mode):
    from core.material_evidence_inputs import nar_material_inputs
    from core.jra_practical_inputs import practical_inputs
    r = result(mode)
    extract = (lambda x: nar_material_inputs(x)[0]) if mode == "nar" else practical_inputs
    expected = extract(r)
    for table in (r.horse_evaluation, r.overall_table):
        table["odds"] = 999
        table["popularity"] = 1
        table["actual_finish"] = 1
        table["payout"] = 999999
    assert extract(r) == expected
    before = copy.deepcopy(r)
    attach_material_reconsideration(r)
    assert len(saved_materials(r)) == 8
    pd.testing.assert_frame_equal(r.horse_evaluation, before.horse_evaluation)
    pd.testing.assert_frame_equal(r.overall_table, before.overall_table)
    assert set(r.debug_info) - set(before.debug_info) == {key_for(mode)}
    saved = copy.deepcopy(r.debug_info)
    attach_material_reconsideration(r)
    assert r.debug_info == saved


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_snapshot_roundtrip_old_uncomputed_no_replay(mode, monkeypatch):
    from core.prediction_history import prediction_zip_bytes
    r = result(mode)
    attach_material_reconsideration(r)
    saved = material_snapshot(r)
    native = json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(r))).read("prediction.json"))
    assert native[key_for(mode)] == saved[key_for(mode)]
    if importlib.util.find_spec("core.prediction_snapshot"):
        from core.prediction_snapshot import (
            race_snapshot_from_result, build_event_snapshot, keiba_bytes, load_keiba, restore_prediction_result,
        )
        race = load_keiba(keiba_bytes(build_event_snapshot([race_snapshot_from_result(r)])))["races"][0]
        restored = restore_prediction_result(race)
        assert material_snapshot(restored) == saved
        restored.debug_info.pop(key_for(mode))
        attach_material_reconsideration(restored)
        assert saved_materials(restored) == {}
        assert reconsideration_html(restored) == ""
    old = result(mode)
    assert material_cell(None) == "未計算"
    assert saved_materials(old) == {}
    assert reconsideration_html(old) == ""


def test_ui_pair_conditional_escaped_and_table_png_parity():
    import app
    from render.mobile_png import _prediction_detail_records
    r = result()
    assert reconsideration_html(r) == ""
    payload = evaluate_nar_materials(swap_input())
    payload["horses"][5]["horse_name"] = "<script>bad</script>"
    r.debug_info[key_for("nar")] = payload
    html = reconsideration_html(r)
    assert html.count("🔄 Top5再検討候補") == 1
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "正式Top5の変更・購入推奨ではありません" in html
    records = app.prediction_detail_records(r)
    assert records == _prediction_detail_records(r)
    assert "好材料" in records[0] and "不安材料" in records[0]
    assert any(row["好材料"].startswith("◎") for row in records)


def test_jra_official_probability_navigation_are_invariant():
    import app
    from core.jra_win_probability import jra_win_probability_snapshot
    from core.jra_purchase_navigator import build_jra_purchase_navigation
    r = result("jra")
    def official(x):
        return (app.jra_comparison_from_result(x), jra_win_probability_snapshot(x),
                build_jra_purchase_navigation(
                    app.jra_enriched_display_rows(x), race_mode="jra", race_info=x.race_info,
                    saved_rows=x.overall_table.to_dict("records")))
    expected = official(r)
    attach_material_reconsideration(r)
    assert official(r) == expected


def test_nar_time_and_identifier_fail_closed_and_saved_rank_not_rounded():
    from core.material_evidence_inputs import nar_material_inputs
    r = result()
    r.created_at = "2026-10-03T16:00:00"
    attach_material_reconsideration(r)
    assert r.debug_info[key_for("nar")]["status"] == "uncomputed"
    r = result()
    r.horse_evaluation["ver3_ability_core"] = 49.8
    r.overall_table["ver3_ability_core"] = 49.8
    data, error = nar_material_inputs(r)
    assert error is None
    assert {h["horse_no"]: h["ability_rank"] for h in data["horses"]}["6"] == 6
    rows = r.horse_evaluation.to_dict("records")
    rows[0]["馬番"] = 1.5
    with pytest.raises(ValueError, match="horse number"):
        nar_material_inputs(r, saved_rows=rows)
