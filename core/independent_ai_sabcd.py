"""Display-only independent AI SABCD trial, pinned to the 2026-10-12 model.

Validated as a stratification on frozen pre-race archives dated 2026-11-15,
16, 18 and 19. Model values are NOT calibrated podium probabilities;
grades are descriptive research buckets, NOT bet recommendations.

No writes to PredictionResult, saved snapshots, official Top5, marks, odds,
or purchasing advice. Abstain on any missing, late, or conflicting evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math
import unicodedata

VERSION = "independent-ai-sabcd-shadow-20261120-v1"
MODEL_ID = "independent_ai_v3_20261012_beta1"
CUTS = (("S", 0.70), ("A", 0.50), ("B", 0.30), ("C", 0.15), ("D", 0.0))


def _name(raw):
    return "".join(unicodedata.normalize("NFKC", str(raw or "")).split())


def _number(raw):
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None


def _timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return moment if moment.tzinfo is not None else None
    except ValueError:
        return None


def _source_is_prestart(prediction, mode, race_id):
    if not isinstance(prediction, Mapping):
        return False
    if prediction.get("status") != "reference":
        return False
    if prediction.get("origin") != "new_prediction":
        return False
    if prediction.get("model_id") != MODEL_ID:
        return False
    if prediction.get("mode") != mode:
        return False
    if not race_id or str(prediction.get("race_id") or "") != str(race_id):
        return False
    packet = prediction.get("input")
    if not isinstance(packet, Mapping) or str(packet.get("race_id") or "") != str(race_id):
        return False
    generated = _timestamp(prediction.get("generated_at"))
    post_time = _timestamp(packet.get("post_time"))
    return bool(generated and post_time and generated < post_time)


def annotate_view(view, prediction, *, race_id=None):
    """Replace ONLY the transient displayed unified grade when fully verified.

    A missing/changed prediction falls back to the existing display unmodified.
    No outcomes, odds, popularity, formal rank or post-race results are read.
    """
    horses = list(view or ())
    if not horses or not all(isinstance(h, dict) for h in horses):
        return view
    modes = {h.get("mode") for h in horses}
    if len(modes) != 1:
        return view
    mode = next(iter(modes))
    if not _source_is_prestart(prediction, mode, race_id):
        return view
    predicted = prediction.get("horses")
    if not isinstance(predicted, list) or len(predicted) != len(horses):
        return view
    source = {}
    for row in predicted:
        if not isinstance(row, Mapping):
            return view
        try:
            key = str(int(row.get("horse_no")))
        except (ValueError, TypeError, OverflowError):
            return view
        score = _number(row.get("place"))
        name = _name(row.get("name"))
        if key in source or not name or score is None:
            return view
        source[key] = (name, score)
    in_view = set()
    for horse in horses:
        key = str(horse.get("no") or "")
        if (not key or key in in_view or key not in source
                or source[key][0] != _name(horse.get("name"))):
            return view
        in_view.add(key)
    if in_view != set(source):
        return view

    # Capture input *quality only* from the same authenticated pre-start
    # packet. Never take feature values from result, odds or a later archive.
    packet = prediction.get("input")
    packet_rows = packet.get("horses") if isinstance(packet, Mapping) else None
    verified_inputs = {}
    if isinstance(packet_rows, list) and len(packet_rows) == len(horses):
        candidate = {}
        for row in packet_rows:
            if not isinstance(row, Mapping):
                break
            try:
                key = str(int(row.get("horse_no")))
            except (TypeError, ValueError, OverflowError):
                break
            if (key in candidate or key not in source
                    or _name(row.get("name")) != source[key][0]):
                break
            candidate[key] = row
        if len(candidate) == len(horses):
            verified_inputs = candidate

    def finite_value(raw, *, minimum=None, integer=False):
        if raw is None or isinstance(raw, bool):
            return None
        try:
            n = float(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(n) or (minimum is not None and n < minimum):
            return None
        if integer and not n.is_integer():
            return None
        return int(n) if integer else n

    ordered = sorted(source, key=lambda no: (-source[no][1], int(no)))
    ranks = {no: index for index, no in enumerate(ordered, 1)}
    # Commit to the temporary projection only after ALL guards pass.
    for horse in horses:
        no = str(horse["no"])
        score = source[no][1]
        grade = next(letter for letter, cutoff in CUTS if score >= cutoff)
        already = horse.get("independent_ai_sabcd") or {}
        if isinstance(already, Mapping) and already.get("version") == VERSION:
            old = horse.get("unified_sabcd_previous")
        else:
            old = horse.get("unified_sabcd")
        previous = dict(old) if isinstance(old, Mapping) else {}
        horse["unified_sabcd_previous"] = previous
        horse["unified_sabcd"] = {
            "grade": grade,
            "rank": ranks[no],
            "strength": None,
            "raw_score": round(score, 6),
            "original_grade": previous.get("grade"),
            "formal_top5_rank": previous.get("formal_top5_rank"),
            "status": "independent_ai_prestart_shadow",
            "reason": (
                "保存済み発走前の独立AI参考3着内モデル値でSABCDを表示分類。"
                "このモデル値は馬券内率として未校正。人数制限なし。"
                "正式Top5・純能力・購入判断は不変。"
                f"旧統合SABCD：{previous.get('grade') or '判定不可'}。"
            ),
            "version": VERSION,
            "retro": False,
        }
        horse["independent_ai_sabcd"] = {
            "grade": grade,
            "rank": ranks[no],
            "score": round(score, 6),
            "version": VERSION,
            "source_model_id": MODEL_ID,
        }
        input_row = verified_inputs.get(no)
        if input_row is None:
            horse["independent_ai_input_quality"] = {"verified": False}
        else:
            checked = ("pure", "distance_index", "course_index", "recent3_mean",
                       "jockey_place_rate", "jockey_sample_size",
                       "rest_days", "load_change")
            missing = [
                key for key in checked if finite_value(
                    input_row.get(key), minimum=0 if key in
                    ("jockey_place_rate", "jockey_sample_size", "rest_days") else None
                ) is None
            ]
            corner = finite_value(input_row.get("corner4"), minimum=1,
                                  integer=True)
            if corner is not None and corner > len(horses):
                corner = None
            if corner is None:
                missing.append("corner4")
            horse["independent_ai_input_quality"] = {
                "verified": True, "corner4": corner,
                "missing": tuple(missing),
            }
    return view
