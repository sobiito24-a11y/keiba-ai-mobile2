from __future__ import annotations

from .models import PredictionResult
from .jra_notebook_logic import predict_jra_from_html


def predict_jra(
    html_files: dict[str, str],
    file_names: dict[str, str] | None = None,
) -> PredictionResult:
    return predict_jra_from_html(html_files, file_names or {})
