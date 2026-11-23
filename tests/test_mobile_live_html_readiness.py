"""Mobile JRA HTML upload: do not accept a name-only pseudo prediction."""
from types import SimpleNamespace

import pandas as pd
import pytest

from core.mobile_live_html_readiness import (
    evaluate_live_jra_result, require_live_jra_ability,
)
from core.mobile_prediction_quality import diagnose


def result(values, mode="jra"):
    rows = [
        {"馬番": i, "馬名": f"保存馬{i}", "_ver3_ability_core": value}
        for i, value in enumerate(values, 1)
    ]
    return SimpleNamespace(
        race_mode=mode,
        overall_table=pd.DataFrame(rows),
        horse_evaluation=pd.DataFrame([]),
        debug_info={},
        _jra_live_display=(mode == "jra"),
    )


def test_iphone_name_only_speed_html_does_not_make_false_complete_prediction():
    source = result([None] * 10)
    assert evaluate_live_jra_result(source) == (10, 0)
    with pytest.raises(ValueError, match="0/10頭"):
        require_live_jra_ability(source)
    assert source.overall_table.shape[0] == 10


def test_more_than_half_missing_ability_refuses_unusable_jra_upload():
    source = result([65.1] * 4 + [None] * 6)
    assert evaluate_live_jra_result(source) == (10, 4)
    with pytest.raises(ValueError, match="4/10頭"):
        require_live_jra_ability(source)


def test_partial_but_model_supported_ability_is_warning_not_blocked():
    source = result([65.1] * 5 + [None] * 5)
    notice = require_live_jra_ability(source)
    assert "5/10頭" in notice
    assert "未取得のまま" in notice


def test_fully_valid_html_scores_pass_without_any_recalculation():
    source = result([60.5, 70.8, 91.2])
    old = source.overall_table.copy(deep=True)
    assert evaluate_live_jra_result(source) == (3, 3)
    assert require_live_jra_ability(source) is None
    pd.testing.assert_frame_equal(source.overall_table, old)


def test_nar_flow_is_unchanged():
    source = result([None] * 5, mode="nar")
    assert evaluate_live_jra_result(source) == (0, 0)
    assert require_live_jra_ability(source) is None


def test_live_ui_diagnostic_does_not_ask_for_keiba_when_using_html():
    source = result([None] * 10)
    view = [dict(no=str(i), ability=None, mode="jra", frame=None,
                 independent_ai_sabcd={}, final_metrics={"ability": {"value": None}})
            for i in range(1, 11)]
    notes = diagnose(source, view)
    assert "タイム指数HTMLを保存し直し" in notes[0][1]
    assert ".keiba" not in notes[0][1]
    assert "すべての純能力指数" in notes[0][1]
