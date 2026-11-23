"""Explain missing Mobile JRA inputs without fabricating a grade or index."""
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd

from core.mobile_prediction_quality import diagnose


def sample_result(source=None, *, mode="jra", prediction=None):
    return SimpleNamespace(
        race_mode=mode,
        overall_table=pd.DataFrame(source if source is not None else [
            {"馬番": 1, "馬名": "保存馬"}]),
        horse_evaluation=pd.DataFrame([]),
        debug_info={"independent_ai_v3": prediction} if prediction is not None else {},
    )


def sample_view(*, ability=None, grade=None, frame=None):
    return [dict(no="1", name="保存馬", mode="jra", frame=frame,
                 ability=ability,
                 final_metrics={"ability": {"value": ability}},
                 independent_ai_sabcd=({"grade": grade} if grade else None))]


def test_entire_source_without_ability_explains_why_blank_rank_is_correct():
    result = sample_result(prediction={"status": "insufficient",
                                       "reason": "能力入力の欠損が多く確率を表示できません"})
    result._jra_live_display = True
    view = sample_view()
    before = (deepcopy(result.overall_table), deepcopy(result.debug_info), deepcopy(view))
    notes = diagnose(result, view)
    assert len(notes) == 3
    assert notes[0][0] == "error"
    assert "すべての純能力指数" in notes[0][1]
    assert "タイム指数HTMLを保存し直し" in notes[0][1]
    assert "統合SABCDは判定不可" in notes[1][1]
    assert "能力入力" in notes[1][1]
    assert "枠番が全頭未取得" in notes[2][1]
    pd.testing.assert_frame_equal(result.overall_table, before[0])
    assert result.debug_info == before[1] and view == before[2]


def test_source_present_but_mobile_ui_missing_is_separately_diagnosed():
    result = sample_result(source=[{"馬番": 1, "馬名": "保存馬",
                                    "ver3_ability_core": 84.7}])
    notes = diagnose(result, sample_view())
    assert notes[0][0] == "error"
    assert "保存予測には1/1頭分" in notes[0][1]
    assert "Mobileの馬別比較欄" in notes[0][1]


def test_valid_ability_and_independent_grade_do_not_trigger_audit():
    result = sample_result(source=[{"馬番": 1, "馬名": "保存馬",
                                    "ver3_ability_core": 78.9}])
    assert diagnose(result, sample_view(ability=78.9, grade="B", frame=1)) == ()


def test_post_generated_source_is_not_disguised_as_prestart_prediction():
    result = sample_result(source=[{"馬番": 1, "馬名": "保存馬",
                                    "ver3_ability_core": 76.0}],
                           prediction={"status": "reference", "origin": "current_reference"})
    notes = diagnose(result, sample_view(ability=76.0, frame=1))
    assert len(notes) == 1
    assert "後から再算出" in notes[0][1]


def test_partial_horse_inputs_identified_without_generating_a_second_horse_score():
    result = sample_result(source=[
        {"馬番": 1, "馬名": "保存馬", "ver3_ability_core": 78.9},
        {"馬番": 2, "馬名": "別馬", "ver3_ability_core": None},
    ], mode="nar")
    view = [dict(no="1", final_metrics={"ability": {"value": 78.9}},
                 independent_ai_sabcd={"grade": "C"}, frame=None),
            dict(no="2", final_metrics={"ability": {"value": None}},
                 independent_ai_sabcd={}, frame=None)]
    notes = diagnose(result, view)
    assert notes[0][0] == "warning"
    assert "純能力の元データは1/2頭" in notes[0][1]
    assert "統合SABCDの保存済み発走前照合は1/2頭のみ" in notes[1][1]
    assert len(notes) == 2
