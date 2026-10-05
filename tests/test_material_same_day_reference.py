"""Same-day diagnostic fallback must not replay official predictions."""
import copy
import importlib.util
import io
import json
import zipfile

import pandas as pd
import pytest

from tests.test_material_reconsideration import result
from core.condition_material_v2 import key_for as condition_key
from core.material_reconsideration import (
    ensure_current_material_reference, attach_material_reconsideration, key_for, saved_materials,
)


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_today_reference_on_restored_result_only_new_key(mode, monkeypatch):
    import core.material_reconsideration as module
    monkeypatch.setattr(module, "current_jst_date", lambda: "2026-10-03")
    r = result(mode)
    r._jra_snapshot_restored = True
    r._material_snapshot_restored = True
    r.debug_info["existing_shadow"] = {"rank": [8, 3, 1]}
    before = copy.deepcopy(r)
    attach_material_reconsideration(r)
    assert r.debug_info == before.debug_info
    ensure_current_material_reference(r)
    assert len(saved_materials(r)) == 8
    assert r.debug_info["existing_shadow"] == before.debug_info["existing_shadow"]
    assert set(r.debug_info) - set(before.debug_info) == {key_for(mode), condition_key(mode)}
    pd.testing.assert_frame_equal(r.horse_evaluation, before.horse_evaluation)
    pd.testing.assert_frame_equal(r.overall_table, before.overall_table)
    p = r.debug_info[key_for(mode)]
    assert p["calculation_context"] == "same_day_saved_inputs_reference"
    assert p["source_prediction_created_at"] == before.created_at
    assert p["input_hash"]
    frozen = copy.deepcopy(p)
    ensure_current_material_reference(r)
    assert r.debug_info[key_for(mode)] == frozen


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_old_future_and_frozen_materials_never_recomputed(mode, monkeypatch):
    r = result(mode)
    for today in ("2026-10-02", "2026-10-04"):
        ensure_current_material_reference(r, today=today)
        assert saved_materials(r) == {}
    ensure_current_material_reference(r, today="2026-10-03")
    saved = copy.deepcopy(r.debug_info)
    import core.material_reconsideration as module
    monkeypatch.setattr(module, "_evaluate_materials", lambda r: pytest.fail("replayed"))
    ensure_current_material_reference(r, today="2026-10-03")
    assert r.debug_info == saved


def test_empty_diagnostic_can_be_filled_but_post_start_input_cannot():
    r = result()
    r.debug_info[key_for("nar")] = {}
    ensure_current_material_reference(r, today="2026-10-03")
    assert len(saved_materials(r)) == 8
    assert r.debug_info[key_for("nar")]["previous_uncomputed"] == {}
    r = result()
    r.created_at = "2026-10-03T16:00:00"
    ensure_current_material_reference(r, today="2026-10-03")
    assert saved_materials(r) == {}
    assert r.debug_info[key_for("nar")]["reason"] == "発走後生成"


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_web_png_export_and_frozen_official_outputs(mode, monkeypatch):
    import app
    from render.mobile_png import _prediction_detail_records
    from core.prediction_history import prediction_zip_bytes
    from core.jra_win_probability import jra_win_probability_snapshot
    from core.jra_purchase_navigator import build_jra_purchase_navigation
    import core.material_reconsideration as module
    monkeypatch.setattr(module, "current_jst_date", lambda: "2026-10-03")
    r = result(mode)
    def formal(r):
        if mode == "nar":
            return app.nar_comparison_from_result(r)
        return (app.jra_comparison_from_result(r), jra_win_probability_snapshot(r),
                build_jra_purchase_navigation(app.jra_enriched_display_rows(r),
                    race_mode="jra", race_info=r.race_info, saved_rows=r.overall_table.to_dict("records")))
    before = copy.deepcopy(formal(r))
    records = app.prediction_detail_records(r)
    if mode == 'jra':
        assert all(x["今回プラス"] != "未計算" and x["今回注意"] != "未計算" for x in records)
    else:
        assert all('今回プラス' not in x and '今回注意' not in x for x in records)
    assert records == _prediction_detail_records(r)
    assert formal(r) == before
    native = json.loads(zipfile.ZipFile(io.BytesIO(prediction_zip_bytes(r))).read("prediction.json"))
    assert native[key_for(mode)] == r.debug_info[key_for(mode)]


def test_dashboard_event_overlay_and_roundtrip_changes_only_material(monkeypatch):
    if importlib.util.find_spec("core.prediction_snapshot") is None:
        return  # Dashboard-only container; Mobile JSON export is tested above.
    import core.material_reconsideration as module
    from core.prediction_snapshot import (
        race_snapshot_from_result, build_event_snapshot, restore_prediction_result,
        update_material_reference, load_keiba, keiba_bytes,
    )
    monkeypatch.setattr(module, "current_jst_date", lambda: "2026-10-04")
    event = build_event_snapshot([race_snapshot_from_result(result())])
    before = copy.deepcopy(event)
    monkeypatch.setattr(module, "current_jst_date", lambda: "2026-10-03")
    restored = restore_prediction_result(event["races"][0])
    key = key_for("nar")
    assert len(saved_materials(restored)) == 8
    updated = update_material_reference(event, event["races"][0]["race_id"], restored)
    assert event == before
    stripped = copy.deepcopy(updated)
    stripped["races"][0]["prediction_result"]["debug_info"].pop(key)
    stripped["races"][0]["mobile_snapshot"].pop(key)
    stripped["races"][0]["prediction_result"]["debug_info"].pop(condition_key("nar"))
    stripped["races"][0]["mobile_snapshot"].pop(condition_key("nar"))
    assert stripped == before
    frozen = copy.deepcopy(restored.debug_info[key])
    recovered = restore_prediction_result(load_keiba(keiba_bytes(updated))["races"][0])
    assert recovered.debug_info[key] == frozen
