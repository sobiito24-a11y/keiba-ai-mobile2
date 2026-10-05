"""Canonical JRA table display mark, shared with purchase navigation.

Final-role annotations take precedence; frozen ranks supply the base roles.
This function never writes ranks, scores or stored mark fields.
"""
from typing import Any, Mapping
import math
import re

import pandas as pd


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
        try:
            if bool(missing):
                return True
        except (TypeError, ValueError):
            pass
    except (TypeError, ValueError):
        pass
    return str(value).strip() in {"", "None", "none", "nan", "NaN", "<NA>", "NaT"}


def _text(value: Any) -> str:
    return "" if _missing(value) else re.sub(r"\s+", " ", str(value)).strip()


def jra_display_mark_from_row(row: Mapping[str, Any]) -> str:
    if '_display_jra_final_mark' in row:
        return _text(row.get('_display_jra_final_mark'))
    return jra_base_display_mark_from_row(row)


def jra_base_display_mark_from_row(row: Mapping[str, Any]) -> str:
    # The formal Top5 ranking is the source of truth for the first three
    # roles.  Research/shadow marks must never replace these roles.
    rank = row.get("_display_jra_top5_rank", row.get("jra_top5_rank"))
    try:
        numeric_rank = float(rank)
        rank_value = int(numeric_rank) if not isinstance(rank, bool) and math.isfinite(numeric_rank) and numeric_rank.is_integer() else None
    except (TypeError, ValueError):
        rank_value = None
    if rank_value in (1, 2, 3):
        return {1: "◎", 2: "○", 3: "▲"}[rank_value]
    if '_display_jra_source_mark' in row:
        return _text(row.get('_display_jra_source_mark'))
    for key in ("v1_final_mark", "ver3_final_mark"):
        mark = _text(row.get(key))
        if mark:
            return mark
    if "mark_v4" in row and not _missing(row.get("mark_v4")):
        return _text(row.get("mark_v4"))
    for key in ("表示印", "display_mark"):
        if key in row:
            return _text(row.get(key))
    for key in ("印", "最終印"):
        if key in row and not _missing(row.get(key)):
            return _text(row.get(key))
    return ""
