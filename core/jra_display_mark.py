"""Canonical JRA table display mark, shared with purchase navigation.

Preserves the Dashboard's existing display precedence, including blank legacy
fields that intentionally stop fallback. Does not assign or modify any mark.
"""
from typing import Any, Mapping
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
