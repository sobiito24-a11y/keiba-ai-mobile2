# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from core.shadow_ver3 import (
    acceptance_report,
    evaluate_shadow_candidates,
    evaluate_shadow_records,
    funabashi_12_diagnostic,
    load_keiba_races,
)


DEFAULT_INPUTS = [
    Path(r"C:\Users\28011\Desktop\2026-08-23_JRA_all_venues.keiba"),
    Path(r"C:\Users\28011\Desktop\2026-08-24_NAR_all_venues.keiba"),
    Path(r"C:\Users\28011\Desktop\2026-08-27_NAR_all_venues.keiba"),
]
DEFAULT_RECORD_CANDIDATES = [
    PROJECT_ROOT / "work" / "mark_betting_backtest_v1" / "race_mark_details.csv",
    PROJECT_ROOT.parent / "keiba_ai_mobile" / "work" / "mark_betting_backtest_v1" / "race_mark_details.csv",
]


def default_records_csv() -> Path:
    for path in DEFAULT_RECORD_CANDIDATES:
        if path.exists():
            return path
    return DEFAULT_RECORD_CANDIDATES[0]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Research-only Shadow comparison against restored Ver3 baseline.")
    parser.add_argument("--input", type=Path, action="append", default=None)
    parser.add_argument("--result-root", type=Path, default=None)
    parser.add_argument("--records-csv", type=Path, default=default_records_csv())
    args = parser.parse_args()
    races, meta = load_keiba_races(args.input or DEFAULT_INPUTS, result_root=args.result_root)
    summary, details = evaluate_shadow_candidates(races)
    records_summary = pd.DataFrame()
    records_details = pd.DataFrame()
    if args.records_csv.exists():
        records = pd.read_csv(args.records_csv)
        records_summary, records_details = evaluate_shadow_records(records, dataset="existing_182R")
    print("loaded_races", meta.get("loaded_races", 0))
    print("missing_results", len(meta.get("missing_results", [])))
    if meta.get("missing_results"):
        print("missing_sample")
        for item in meta["missing_results"][:10]:
            print(item)
    print("\nBASELINE vs CANDIDATE")
    print(summary.to_string(index=False))
    print("\nDELTA")
    print(acceptance_report(summary).to_string(index=False))
    print("\nBASELINE vs CANDIDATE (RESULT-READY RECORDS)")
    print(records_summary.to_string(index=False))
    print("\nDELTA (RESULT-READY RECORDS)")
    print(acceptance_report(records_summary).to_string(index=False))
    print("\nFUNABASHI_12_DIAGNOSTIC")
    print(funabashi_12_diagnostic(races).to_string(index=False))
    print("\nDETAIL_ROWS", len(details), "RECORD_DETAIL_ROWS", len(records_details))


if __name__ == "__main__":
    main()
