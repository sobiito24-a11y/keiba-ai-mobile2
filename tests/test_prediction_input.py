from __future__ import annotations

from unittest.mock import patch

import pytest

from core.models import PredictionResult
from core.prediction_input import normalize_predictor_html_input, predict_from_html_inputs


def result_for(mode: str) -> PredictionResult:
    return PredictionResult(race_mode=mode, status="ok")  # type: ignore[arg-type]


def test_predictor_input_keeps_optional_html_and_does_not_invent_missing_kinds() -> None:
    normalized = normalize_predictor_html_input(
        "nar",
        {"speed": "speed", "newspaper": "paper", "style": "style", "jockey": ""},
        {"speed": "a.html", "newspaper": "b.html", "style": "c.html", "jockey": "d.html"},
    )
    assert list(normalized.html_files) == ["speed", "newspaper", "style", "jockey"]
    assert normalized.html_files["jockey"] == ""
    assert "oikiri" not in normalized.html_files


def test_nar_direct_and_batch_call_boundary_routes_to_same_predictor() -> None:
    html_files = {"speed": "speed", "newspaper": "paper", "style": "style"}
    file_names = {kind: f"{kind}.html" for kind in html_files}
    expected = result_for("nar")
    with patch("core.prediction_input.predict_nar", return_value=expected) as predictor:
        direct = predict_from_html_inputs(
            "nar", html_files, file_names, prediction_logic_version="market"
        )
        batch = predict_from_html_inputs(
            "nar", dict(html_files), dict(file_names), prediction_logic_version="market"
        )
    assert direct is expected
    assert batch is expected
    assert predictor.call_count == 2
    first = predictor.call_args_list[0]
    second = predictor.call_args_list[1]
    assert first.args == second.args
    assert first.kwargs == second.kwargs == {"prediction_logic_version": "market"}


def test_jra_routes_through_canonical_boundary() -> None:
    expected = result_for("jra")
    with patch("core.prediction_input.predict_jra", return_value=expected) as predictor:
        actual = predict_from_html_inputs(
            "jra", {"speed": "x"}, {"speed": "x.html"}, prediction_logic_version="market"
        )
    assert actual is expected
    predictor.assert_called_once()


def test_non_string_html_is_rejected_before_predictor() -> None:
    with pytest.raises(TypeError, match="speed HTMLは文字列"):
        normalize_predictor_html_input("nar", {"speed": b"bytes"}, {})  # type: ignore[dict-item]


def test_mobile_pc_run_prediction_uses_shared_input_boundary() -> None:
    import importlib
    import sys

    google_module = sys.modules.get("google")
    if google_module is not None and not hasattr(google_module, "__path__"):
        for module_name in [name for name in sys.modules if name == "google" or name.startswith("google.")]:
            sys.modules.pop(module_name, None)
    app = importlib.import_module("app")

    expected = result_for("nar")
    html_files = {"speed": "speed", "newspaper": "paper", "style": "style"}
    file_names = {kind: f"{kind}.html" for kind in html_files}
    with patch("app.predict_from_html_inputs", return_value=expected) as boundary:
        actual = app.run_prediction(
            "nar",
            html_files,
            file_names,
            prediction_logic_version="market",
        )
    assert actual is expected
    boundary.assert_called_once_with(
        "nar",
        html_files,
        file_names,
        prediction_logic_version="market",
    )
