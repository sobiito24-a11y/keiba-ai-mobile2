from __future__ import annotations

from .models import PredictionResult
from .nar_notebook_logic import predict_nar_from_html


def predict_nar(
    html_files: dict[str, str],
    file_names: dict[str, str] | None = None,
) -> PredictionResult:
    return predict_nar_from_html(html_files, file_names or {})
