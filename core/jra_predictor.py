from __future__ import annotations

from .models import PredictionResult
from .notebook_bridge import run_notebook_prediction


def predict_jra(
    html_files: dict[str, str],
    file_names: dict[str, str] | None = None,
) -> PredictionResult:
    return run_notebook_prediction("jra", html_files, file_names or {})

