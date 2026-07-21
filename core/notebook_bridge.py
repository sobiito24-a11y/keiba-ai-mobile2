from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import types
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .models import PredictionResult, RaceMode


NOTEBOOK_FILENAMES: dict[RaceMode, str] = {
    "nar": "netkeiba_nar_ai_prediction_pc_html_colab_venue_trial.ipynb",
    "jra": "netkeiba_ai_prediction_pc_html_colab_jra_venue_trial.ipynb",
}

NOTEBOOK_ENV_VARS: dict[RaceMode, str] = {
    "nar": "KEIBA_NAR_NOTEBOOK_PATH",
    "jra": "KEIBA_JRA_NOTEBOOK_PATH",
}


class DisplayCapture:
    def __init__(self) -> None:
        self.objects: list[Any] = []

    def display(self, obj: Any) -> None:
        self.objects.append(obj)

    def reset(self) -> None:
        self.objects.clear()


def run_notebook_prediction(
    mode: RaceMode,
    html_files: dict[str, str],
    file_names: dict[str, str] | None = None,
    *,
    fetch_past_detail: bool = True,
) -> PredictionResult:
    capture = DisplayCapture()
    _install_notebook_shims(capture)

    notebook_path = _find_notebook_path(mode)
    nb = json.loads(notebook_path.read_text(encoding="utf-8"))

    env = _base_env(mode, html_files, file_names or {}, fetch_past_detail)
    env["display"] = capture.display

    setup_source = "".join(nb["cells"][5]["source"]) + "\n" + "".join(nb["cells"][6]["source"])
    run_source = "".join(nb["cells"][7]["source"])

    raw_buffer = io.StringIO()
    with contextlib.redirect_stdout(raw_buffer):
        exec(setup_source, env)
        capture.reset()
        exec(run_source, env)

    result_df = env.get("result_df")
    race_info = dict(env.get("race_info") or {})
    race_name = str(race_info.get("race_name") or "")

    overall_table = _build_overall_table(env, result_df)
    horse_evaluation = _capture_first_dataframe(
        capture,
        lambda: env["print_ver30_all_horse_rating"](result_df, race_type=mode),
    )
    attention_text = _capture_text(
        capture,
        lambda: env["print_ver30_attention_horses"](result_df, race_type=mode),
    )
    review_text = _capture_text(
        capture,
        lambda: env["print_ver30_ai_race_review"](
            result_df,
            race_info,
            env.get("running_style_info"),
            env.get("ai_confidence_summary"),
            race_type=mode,
        ),
    )
    betting_text = _capture_text(
        capture,
        lambda: env["print_ver30_betting_structure"](
            result_df,
            env.get("ai_confidence_summary"),
            race_type=mode,
        ),
    )

    return PredictionResult(
        race_mode=mode,
        race_name=race_name,
        race_info=race_info,
        overall_table=overall_table,
        horse_evaluation=horse_evaluation,
        attention_horses=_split_attention_horses(attention_text),
        ai_race_review=review_text.strip(),
        betting_structure=betting_text.strip(),
        source_files=dict(file_names or {}),
        status="ok",
        message="NotebookロジックからPredictionResultを生成しました。",
        raw_output=raw_buffer.getvalue(),
    )


def _base_env(
    mode: RaceMode,
    html_files: dict[str, str],
    file_names: dict[str, str],
    fetch_past_detail: bool,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "__name__": "__keiba_ai_mobile_notebook__",
        "FETCH_PAST_RACE_DETAIL": fetch_past_detail,
        "PAST_RACE_SLEEP_SEC": 0.35,
        "SHOW_CORNER_SCENARIO": True,
        "SHOW_TARGET_HORSE_AUDIT": False,
        "html_from_pc_file": html_files.get("speed", ""),
        "html_from_style_file": html_files.get("style", ""),
        "html_from_odds_file": "",
        "html_file_name": file_names.get("speed", ""),
        "style_html_file_name": file_names.get("style", ""),
        "odds_html_file_name": "",
    }
    if mode == "nar":
        env.update(
            {
                "html_from_shutuba_file": html_files.get("shutuba", ""),
                "shutuba_html_file_name": file_names.get("shutuba", ""),
            }
        )
    else:
        env.update(
            {
                "html_from_newspaper_file": html_files.get("newspaper", ""),
                "html_from_oikiri_file": html_files.get("oikiri", ""),
                "newspaper_html_file_name": file_names.get("newspaper", ""),
                "oikiri_html_file_name": file_names.get("oikiri", ""),
            }
        )
    return env


def _find_notebook_path(mode: RaceMode) -> Path:
    env_path = os.environ.get(NOTEBOOK_ENV_VARS[mode])
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    project_root = Path(__file__).resolve().parents[1]
    codex_root = project_root.parents[2]
    candidates = [
        codex_root
        / "2026-06-12"
        / "colab-ai-url-3-url-https"
        / "outputs"
        / NOTEBOOK_FILENAMES[mode],
        project_root / "notebooks" / NOTEBOOK_FILENAMES[mode],
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"{NOTEBOOK_FILENAMES[mode]} が見つかりません。"
        f"{NOTEBOOK_ENV_VARS[mode]} でNotebookパスを指定してください。"
    )


def _install_notebook_shims(capture: DisplayCapture) -> None:
    ipython_mod = types.ModuleType("IPython")
    ipython_display_mod = types.ModuleType("IPython.display")
    ipython_display_mod.display = capture.display
    sys.modules["IPython"] = ipython_mod
    sys.modules["IPython.display"] = ipython_display_mod

    google_mod = sys.modules.get("google") or types.ModuleType("google")
    colab_mod = types.ModuleType("google.colab")
    files_mod = types.ModuleType("google.colab.files")
    files_mod.upload = lambda: {}
    colab_mod.files = files_mod
    google_mod.colab = colab_mod
    sys.modules["google"] = google_mod
    sys.modules["google.colab"] = colab_mod
    sys.modules["google.colab.files"] = files_mod


def _build_overall_table(env: dict[str, Any], result_df: Any) -> pd.DataFrame | None:
    if not isinstance(result_df, pd.DataFrame):
        return None
    display_cols = [column for column in env.get("display_cols", []) if column in result_df.columns]
    if display_cols:
        return result_df[display_cols].copy()
    return result_df.copy()


def _capture_text(capture: DisplayCapture, func: Callable[[], Any]) -> str:
    capture.reset()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        func()
    return buffer.getvalue()


def _capture_first_dataframe(capture: DisplayCapture, func: Callable[[], Any]) -> pd.DataFrame | None:
    _capture_text(capture, func)
    for obj in capture.objects:
        frame = _display_object_to_dataframe(obj)
        if frame is not None:
            return frame
    return None


def _display_object_to_dataframe(obj: Any) -> pd.DataFrame | None:
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    data = getattr(obj, "data", None)
    if isinstance(data, pd.DataFrame):
        return data.copy()
    return None


def _split_attention_horses(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in {"【注目馬】", "注目馬"}:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        blocks.append("\n".join(current))
    return blocks
