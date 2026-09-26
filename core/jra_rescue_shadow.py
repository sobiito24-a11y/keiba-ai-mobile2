"""Snapshot-only research signal; never used by UI, marks or purchase logic."""
from .v1_logic import to_float, training_grade


def jra_rescue_shadow(row):
    rank = to_float(row.get("jra_top5_rank"))
    reasons = []
    for key, label in (("distance_index_rank", "距離指数Top3"), ("jockey_course_rank", "騎手コース成績Top3")):
        value = to_float(row.get(key))
        if value is not None and 1 <= value <= 3:
            reasons.append(label)
    if row.get("class_shift_market") in {"降級", "クラス降級"}:
        reasons.append("クラス降級")
    quality = []
    if row.get("v1_reproducibility") in {"S", "A", "B"}:
        quality.append("再現性" + row["v1_reproducibility"])
    grade = training_grade(row)
    if grade in {"A", "B"}:
        quality.append("調教" + grade)
    qualifies = rank is not None and rank > 5 and bool(reasons) and bool(quality)
    return {"jra_rescue_shadow": qualifies,
            "jra_rescue_shadow_reasons": reasons + quality if qualifies else []}


def jra_rescue_shadow_snapshot(result):
    if result.race_mode != "jra":
        return None
    from .nar_race_diagnostics import build_full_field_comparison
    from .prediction_table_ui import display_index_rows, horse_key
    source = []
    for table in (result.horse_evaluation, result.overall_table):
        if table is not None and not table.empty:
            source = table.to_dict("records")
            break
    saved = result.overall_table.to_dict("records") if result.overall_table is not None else []
    rows = build_full_field_comparison(source, race_mode="jra", sort_mode="current", race_info=result.race_info or {}).get("rows", [])
    # Reuse existing display-only distance competition ranks, never rerank Top5.
    rows = display_index_rows(rows, saved, result.race_info or {}, "jra")
    return [{"horse_no": horse_key(h), **jra_rescue_shadow(h)} for h in rows]
