"""JRA-only, one-way display/audit projection of the official Top5 score."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

JRA_WIN_PROB_TEMPERATURE = 8.5
JRA_WIN_PROB_UNIFORM_SHRINKAGE = 0.35
JRA_WIN_PROB_CALIBRATION_VERSION = "jra_winprob_v1_20260919_20260922"
JRA_WIN_PROB_LABEL = "AI推定勝率（参考）"


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def calculate_jra_win_probabilities(scores: Sequence[Any]) -> list[float | None]:
    """Use the complete field; one missing score makes every probability unknown."""
    values = [_score(score) for score in scores]
    if not values:
        return []
    if any(value is None for value in values):
        return [None] * len(values)
    z = [value / JRA_WIN_PROB_TEMPERATURE for value in values]
    maximum = max(z)
    weights = [math.exp(value - maximum) for value in z]
    total = math.fsum(weights)
    shrinkage = JRA_WIN_PROB_UNIFORM_SHRINKAGE
    return [(1.0 - shrinkage) * weight / total + shrinkage / len(values) for weight in weights]


def annotate_jra_win_probabilities(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    probabilities = calculate_jra_win_probabilities([row.get("jra_top5_score") for row in rows])
    return [dict(row, jra_win_probability=probability,
                 jra_win_probability_calibration_version=JRA_WIN_PROB_CALIBRATION_VERSION)
            for row, probability in zip(rows, probabilities)]


def probability_text(row: Mapping[str, Any]) -> str:
    value = _score(row.get("jra_win_probability"))
    return f"{100 * value:.1f}%" if value is not None and 0 <= value <= 1 else "—"


def jra_win_probability_snapshot(result: Any) -> dict[str, Any] | None:
    """Reuse the formal full-field producer, never duplicate the Top5 formula."""
    if result.race_mode != "jra":
        return None
    from .nar_race_diagnostics import build_full_field_comparison

    source = []
    for table in (result.horse_evaluation, result.overall_table):
        if table is not None and not table.empty:
            source = table.to_dict("records")
            break
    comparison = build_full_field_comparison(source, race_mode="jra", sort_mode="current",
                                            race_info=result.race_info or {})
    rows = annotate_jra_win_probabilities(comparison.get("rows", []))
    return {
        "calibration_version": JRA_WIN_PROB_CALIBRATION_VERSION,
        "temperature": JRA_WIN_PROB_TEMPERATURE,
        "uniform_shrinkage": JRA_WIN_PROB_UNIFORM_SHRINKAGE,
        "score_source": "jra_top5_score",
        "horses": [{"horse_no": row.get("number"), "jra_top5_rank": row.get("jra_top5_rank"),
                    "jra_top5_score": row.get("jra_top5_score"),
                    "jra_win_probability": row["jra_win_probability"],
                    "jra_win_probability_calibration_version": JRA_WIN_PROB_CALIBRATION_VERSION}
                   for row in rows],
    }
