# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.mark_backtest import (
    add_honmei_maruta_difference_columns,
    attach_value_signals_to_records,
    attach_results,
    build_report_payload,
    discover_race_sources,
    extract_prediction_rows,
    parse_result_html,
    prediction_html_files,
    write_outputs,
)


DEFAULT_JRA_ROOT = Path(r"C:\Users\28011\Documents\Codex\Keiba_AI_Data\JRA\collected")
DEFAULT_NAR_ROOT = Path(r"C:\Users\28011\Documents\Codex\Keiba_AI_Data\NAR\collected")
DEFAULT_OUT_DIR = PROJECT_ROOT / "work" / "mark_betting_backtest"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest current ◎○▲△☆ marks without changing prediction logic.")
    parser.add_argument("--jra-root", type=Path, action="append", default=None)
    parser.add_argument("--nar-root", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Optional total race limit for a quick smoke run.")
    args = parser.parse_args()

    install_runtime_stubs()

    jra_roots = args.jra_root or [DEFAULT_JRA_ROOT]
    nar_roots = args.nar_root or [DEFAULT_NAR_ROOT]
    records, payouts_by_race, meta = run_backtest(jra_roots, nar_roots, limit=args.limit)
    payload = build_report_payload(records, payouts_by_race, meta)
    paths = write_outputs(payload, records, args.out_dir)

    print(f"usable races: {meta['usable_races']}R")
    print(f"JRA/NAR: {meta['jra_races']}R / {meta['nar_races']}R")
    print(f"horses: {meta['horse_count']}")
    print(f"errors: {meta['prediction_error_count']}")
    for name, path in paths.items():
        print(f"{name}: {path}")


def install_runtime_stubs() -> None:
    try:
        from tools.analyze_jra_betting_expectation import install_runtime_stubs as install

        install()
    except Exception:
        pass


def run_backtest(
    jra_roots: list[Path],
    nar_roots: list[Path],
    *,
    limit: int | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]], dict[str, Any]]:
    jra_sources, jra_meta = discover_race_sources(jra_roots, "jra")
    nar_sources, nar_meta = discover_race_sources(nar_roots, "nar")
    sources = [*jra_sources, *nar_sources]
    if limit is not None:
        sources = sources[: max(0, limit)]

    rows: list[dict[str, Any]] = []
    payouts_by_race: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    usable_race_types: dict[str, int] = {"jra": 0, "nar": 0}

    for source in sources:
        try:
            html_files, file_names = prediction_html_files(source.race_dir, source.race_type)
            prediction = predict_from_current_logic(source.race_type, html_files, file_names)
            prediction_rows, _race_info = extract_prediction_rows(prediction, source.race_id, source.race_type)
            if not prediction_rows:
                errors.append(f"{source.race_type}:{source.race_id}: prediction rows empty")
                continue
            finish, payouts = parse_result_html(source.result_path)
            payouts_by_race[source.race_id] = payouts
            rows.extend(attach_results(prediction_rows, finish, payouts))
            usable_race_types[source.race_type] = usable_race_types.get(source.race_type, 0) + 1
        except Exception as exc:  # pragma: no cover - surfaced in generated report
            errors.append(f"{source.race_type}:{source.race_id}: {type(exc).__name__}: {exc}")

    records = attach_value_signals_to_records(add_honmei_maruta_difference_columns(pd.DataFrame(rows)))
    meta: dict[str, Any] = {
        "source": "saved_html",
        "prediction_logic_version": "v3",
        "future_info_isolated": True,
        "future_info_policy": "result.html is excluded from prediction inputs and used only after PredictionResult rows are generated.",
        "jra_discovery": jra_meta,
        "nar_discovery": nar_meta,
        "attempted_races": len(sources),
        "usable_races": int(records["race_id"].nunique()) if not records.empty else 0,
        "jra_races": usable_race_types.get("jra", 0),
        "nar_races": usable_race_types.get("nar", 0),
        "horse_count": int(len(records)),
        "prediction_error_count": len(errors),
        "prediction_errors": errors[:100],
        "available_columns": list(records.columns),
    }
    return records, payouts_by_race, meta


def predict_from_current_logic(race_type: str, html_files: dict[str, str], file_names: dict[str, str]) -> Any:
    sink = io.StringIO()
    if race_type == "jra":
        from core.jra_notebook_logic import predict_jra_from_html

        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            return predict_jra_from_html(html_files, file_names, fetch_past_detail=False)
    if race_type == "nar":
        from core.nar_notebook_logic import predict_nar_from_html

        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            return predict_nar_from_html(html_files, file_names, fetch_past_detail=False)
    raise ValueError(f"Unsupported race_type: {race_type}")


if __name__ == "__main__":
    main()
