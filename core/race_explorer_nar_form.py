"""Project NAR past-form research onto the *actual* all-runner comparison screen.

View projection only: do not alter .keiba, existing pure-ability ranks,
official historical scores, betting choices, or JRA rows.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nar_recent_form_reference import evaluate_nar_rows


def _horse_number(row: Mapping[str, Any]) -> str:
    for key in ("馬番", "horse_no", "number", "馬", "no"):
        value = row.get(key)
        try:
            if not isinstance(value, bool) and float(value).is_integer() and float(value) > 0:
                return str(int(float(value)))
        except (TypeError, ValueError, OverflowError):
            pass
    return ""


def with_nar_form_reference(
    view: list[dict[str, Any]],
    source_rows: list[Mapping[str, Any]],
    race_info: Mapping[str, Any] | None,
    debug_info: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return copied view rows with independent research indicators, NAR only.

    This is a projection of the same source rows used for the normal screen.
    Previous race fields are dated and never merged with actual results.
    """
    if not view or not all(h.get("mode") == "nar" for h in view):
        return [dict(h) for h in view]
    debug = debug_info if isinstance(debug_info, Mapping) else {}
    shadow = (
        debug.get("nar_newspaper_v2_shadow")
        or debug.get("nar_newspaper_v2_input_enriched_shadow")
        or {}
    )
    ranked = evaluate_nar_rows(source_rows, race_info, shadow)
    keyed = {_horse_number(row): row for row in ranked if _horse_number(row)}
    out = []
    for horse in view:
        projected = dict(horse)
        new = keyed.get(_horse_number(horse), {})
        projected["nar_form_ref_rank"] = new.get("nar_form_ref_rank")
        projected["nar_form_ref_score"] = new.get("nar_form_ref_score")
        projected["nar_form_ref_reason"] = new.get("nar_form_ref_reason") or "前走根拠未取得"
        projected["nar_form_ref_flag"] = new.get("nar_form_ref_flag") or "—"
        projected["nar_form_ref_prior_corner"] = new.get("nar_form_ref_prior_corner")
        projected["nar_form_ref_pace"] = new.get("nar_form_ref_pace") or "未確認"
        out.append(projected)
    return out
