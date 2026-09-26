"""NAR reference probabilities. Never an input to prediction or purchase rules."""
from __future__ import annotations

import copy
import math
from typing import Any, Mapping, Sequence

NAR_WINPROB_MODEL_VERSION = "nar_winprob_v1_20260922_71r_ability_avg"
NAR_WINPROB_ABILITY_COEFFICIENT = 0.01838667
NAR_WINPROB_AVERAGE_COEFFICIENT = 0.02653994
NAR_WINPROB_ABILITY_FILL = 29.2
NAR_WINPROB_AVERAGE_FILL = 22.0
NAR_WINPROB_LABEL = "AI推定勝率（参考）"
NAR_WINPROB_FIELDS = (
    "nar_winprob_score", "nar_win_probability", "nar_winprob_model_version",
    "nar_winprob_pure_ability", "nar_winprob_average_index",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _key(row: Mapping[str, Any]) -> str:
    for name in ("number", "馬番", "horse_no"):
        value = _number(row.get(name))
        if value is not None and value.is_integer() and value > 0:
            return str(int(value))
    return ""


def _feature(row: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        value = _number(row.get(name))
        if value is not None:
            return value
    return None


def annotate_nar_win_probabilities(rows, source_rows=()):
    """Copy rows, join by horse number, read only saved core and recent-three mean.

    A strict majority must have each source feature. Widespread acquisition
    failure must not turn into a synthetic race of median-imputed horses.
    Negative and zero indices are valid. Persisted probabilities take priority.
    """
    rows = list(rows)
    if not rows:
        return []
    sources = list(source_rows)
    keys = [_key(h) for h in rows]
    source_keys = [_key(h) for h in sources]
    valid_ids = all(keys) and len(set(keys)) == len(keys)
    valid_ids = valid_ids and all(source_keys) and len(set(source_keys)) == len(source_keys)
    by_no = dict(zip(source_keys, sources))
    inputs = [by_no.get(key, h) for key, h in zip(keys, rows)]
    # A restored model is frozen; do not replace it with today's coefficients.
    if valid_ids and all(h.get("nar_winprob_model_version") for h in inputs):
        return [dict(row, **{k: h.get(k) for k in NAR_WINPROB_FIELDS}) for row, h in zip(rows, inputs)]
    pure = [_feature(h, ("ver3_ability_core",)) for h in inputs]
    avg = [_feature(h, ("平均指数", "3走平均", "近3走平均", "recent3_average")) for h in inputs]
    available = valid_ids and all(sum(v is not None for v in values) > len(rows) / 2 for values in (pure, avg))
    scores = [None] * len(rows)
    probabilities = [None] * len(rows)
    used_pure, used_avg = [None] * len(rows), [None] * len(rows)
    if available:
        used_pure = [x if x is not None else NAR_WINPROB_ABILITY_FILL for x in pure]
        used_avg = [x if x is not None else NAR_WINPROB_AVERAGE_FILL for x in avg]
        scores = [NAR_WINPROB_ABILITY_COEFFICIENT * a + NAR_WINPROB_AVERAGE_COEFFICIENT * b
                  for a, b in zip(used_pure, used_avg)]
        maximum = max(scores)
        weights = [math.exp(score - maximum) for score in scores]
        total = math.fsum(weights)
        probabilities = [weight / total for weight in weights]
    return [dict(row, nar_winprob_score=score, nar_win_probability=probability,
                 nar_winprob_model_version=NAR_WINPROB_MODEL_VERSION,
                 nar_winprob_pure_ability=a, nar_winprob_average_index=b)
            for row, score, probability, a, b in zip(rows, scores, probabilities, used_pure, used_avg)]


def nar_probability_text(row):
    value = _number(row.get("nar_win_probability"))
    return f"{value * 100:.1f}%" if value is not None and 0 <= value <= 1 else "—"


def nar_win_probability_snapshot(result):
    if result.race_mode != "nar":
        return None
    saved = (result.debug_info or {}).get("nar_winprob_calibration")
    if isinstance(saved, Mapping):
        return copy.deepcopy(saved)
    rows = []
    for table in (result.overall_table, result.horse_evaluation):
        if table is not None and not table.empty:
            rows = table.to_dict("records")
            break
    annotated = annotate_nar_win_probabilities(rows)
    return {
        "model_version": NAR_WINPROB_MODEL_VERSION,
        "pure_ability_coefficient": NAR_WINPROB_ABILITY_COEFFICIENT,
        "average_index_coefficient": NAR_WINPROB_AVERAGE_COEFFICIENT,
        "pure_ability_fill": NAR_WINPROB_ABILITY_FILL,
        "average_index_fill": NAR_WINPROB_AVERAGE_FILL,
        "source_features": ["ver3_ability_core", "平均指数"],
        "horses": [dict(horse_no=_key(h), **{k: h[k] for k in NAR_WINPROB_FIELDS}) for h in annotated],
    }


def nar_winprob_validation_rows(snapshot, finishes=None):
    """Join immutable saved predictions with later results, without refitting.

    finishes is a horse-number -> finish mapping. Missing/DNF results stay null.
    The caller may export these rows; this function never writes the snapshot.
    """
    info = snapshot.get("race_info") or snapshot
    finishes = {str(k): v for k, v in (finishes or {}).items()}
    out = []
    for horse in snapshot.get("horses", []):
        if "nar_winprob_model_version" not in horse:
            continue
        key = _key(horse)
        finish = _number(finishes.get(key))
        finish = int(finish) if finish is not None and finish >= 1 and finish.is_integer() else None
        out.append(dict(race_id=info.get("race_id"), venue=info.get("venue"),
                        horse_no=key, horse_name=horse.get("horse_name"),
                        prediction_created_at=snapshot.get("prediction_created_at") or snapshot.get("created_at") or (snapshot.get("audit") or {}).get("prediction_created_at"),
                        **{k: horse.get(k) for k in NAR_WINPROB_FIELDS},
                        finish=finish, win=(finish == 1) if finish is not None else None))
    return out
