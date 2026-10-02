"""Pure shadow computations. Nothing from here is fed back into official tables."""
from __future__ import annotations
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from .class_context import class_change, class_history
from .jra_class_v2 import classify_jra_class
from .nar_class_v2 import classify_nar_class
from .newspaper_v2_inputs import horse_no, number, pick, recent_runs, result_rows, race_id, newspaper_past_evidence, shadow_jockey_inputs, shadow_jockey_change


def configuration():
    return json.loads(Path(__file__).with_name("newspaper_v2_weights.json").read_text(encoding="utf-8"))


def clip(value):
    return max(-1.0, min(1.0, value))


def run_number(value):
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(?:位|着|m)?\s*", str(value if value is not None else ""))
    return number(match[1]) if match else None


def evaluate_shadow(rows, info, mode, *, html="", evaluated_at=None, race_identifier=""):
    if mode not in {"jra", "nar"}:
        raise ValueError("V2 race mode must be jra or nar")
    config = configuration()
    classify = classify_jra_class if mode == "jra" else classify_nar_class
    current = classify(info, html)
    past_evidence = newspaper_past_evidence(html)
    keys = [horse_no(r) for r in rows]
    valid_keys = all(keys) and len(set(keys)) == len(keys)
    excluded = mode == "jra" and current["race_discipline_v2"] == "jump"
    front_count = sum((number(pick(r, "netkeiba_corner4_rank", "_netkeiba_corner4_rank")) or 99) <= 3 for r in rows)
    horses = []
    for row in rows:
        missing, positive, negative = [], [], []
        ability_source = next((k for k in ("ver3_ability_core", "_ver3_ability_core", "nar_pure_ability_score", "pure_ability", "ability_value") if number(row.get(k)) is not None), None)
        ability = number(row.get(ability_source)) if ability_source else None
        if ability is None:
            missing.append("純能力未取得")
        runs = recent_runs(row, past_evidence.get(horse_no(row)))
        indices = [run_number(r.get("time_index")) for r in runs]
        valid_indices = [v for v in indices if v is not None]
        recent = None
        if indices and indices[0] is not None and any(v is not None for v in indices[1:]):
            recent = clip((indices[0] - mean(v for v in indices[1:] if v is not None)) / 10)
        else:
            missing.append("近走指数の時系列不足")
        past = []
        for run in runs:
            # Historical explicit class labels are permissible evidence; preserve raw.
            raw = " ".join(str(run.get(k) or "") for k in ("race_name", "race_data2", "class_label"))
            past_class = classify({"race_name": raw, "racecourse": run.get("venue"), "race_grade": run.get("race_grade")})
            past.append({"class": past_class, "finish": run_number(run.get("finish")), "head_count": run.get("head_count")})
        history = class_history(current, past)
        class_score = None
        if past and class_change(current, past[0]["class"]) != "比較不能":
            p = past[0]
            if p["finish"] is not None and p["head_count"] is not None and 1 <= p["finish"] <= p["head_count"] and p["head_count"] > 1:
                finish_quality = 1 - 2 * (p["finish"] - 1) / (p["head_count"] - 1)
                # A win is not inherently superior to a better-class performance.
                class_score = clip(0.5 * finish_quality + 0.5 * clip((p["class"]["class_level_v2"] - current["class_level_v2"]) / (1 if mode == "jra" else 3)))
        if class_score is None:
            missing.append("クラス・頭数比較不能（補正なし）")
        matched, unmatched = [], []
        for run, index in zip(runs, indices):
            if index is None:
                continue
            target = [info.get("racecourse") or info.get("venue"), number(info.get("distance")), info.get("surface"), info.get("direction") or info.get("turn")]
            observed = [run.get("venue"), run_number(run.get("distance")), run.get("surface"), run.get("turn")]
            if all(target) and all(observed):
                (matched if observed == target else unmatched).append(index)
        condition = clip((mean(matched) - mean(unmatched)) / 10) if matched and unmatched else None
        if condition is None:
            missing.append("同条件と他条件の比較不足")
        corner = number(pick(row, "netkeiba_corner4_rank", "_netkeiba_corner4_rank"))
        pace = str(pick(row, "provider_pace_market", "netkeiba_pace", "_netkeiba_pace") or "")
        pace_score = None
        if corner is not None and corner >= 1 and pace in {"S", "M", "H"}:
            pace_score = 0.0
            if pace == "S":
                pace_score = 1.0 if corner <= 3 else -0.5 if corner > len(rows) * .65 else 0.0
            elif pace == "H" and front_count >= 3:
                pace_score = -1.0 if corner <= 3 else 0.5
        else:
            missing.append("ペースまたは4角順位未取得")
        training_raw = str(pick(row, "training_market", "調教評価", "training_grade", "調教") or "")
        grade = re.search(r"(?<![A-Za-z])[ABCD](?![A-Za-z])", training_raw)
        training = {"A": 1., "B": .5, "C": 0., "D": -.5}.get(grade[0]) if mode == "jra" and grade else None
        if mode == "jra" and training is None:
            missing.append("調教評価未取得")
        starts = number(pick(row, "jockey_course_runs", "_jockey_course_starts"))
        rate = number(pick(row, "jockey_course_top3_rate", "_jockey_course_place_rate"))
        jockey = clip((rate - 25) / 25) if starts is not None and starts >= 20 and rate is not None and 0 <= rate <= 100 else None
        if jockey is None:
            missing.append("騎手成績不足（20走以上のみ）")
        components = dict(ability=ability, recent_form=recent, **{"class": class_score}, condition=condition, pace=pace_score, training=training, jockey=jockey, weight=None)
        reason_labels = {"recent_form": "近走指数の変化", "class": "比較可能クラス・着順", "condition": "同条件と他条件の指数差",
                         "pace": "想定ペース×4角位置", "training": "調教" + (grade[0] if grade else ""), "jockey": "騎手コース複勝率"}
        for name, value in components.items():
            if name != "ability" and value is not None:
                if value > 0:
                    positive.append(f"{reason_labels.get(name, name)} {value:+.2f}")
                elif value < 0:
                    negative.append(f"{reason_labels.get(name, name)} {value:+.2f}")
        if excluded:
            missing.append("障害：対象外／専用モデル未検証")
        scores = {purpose: (sum((components[k] or 0) * w for k, w in weights.items()) if ability is not None and not excluded and valid_keys else None)
                  for purpose, weights in config[mode].items()}
        prefix = mode + "_v2_"
        horse = {"horse_no": horse_no(row), "horse_name": str(pick(row, "horse_name", "馬名") or ""),
                 "pure_ability_rank": number(pick(row, "ability_rank", "nar_pure_ability_rank", "market_ability_rank")),
                 "official_top5_rank": number(pick(row, "jra_top5_rank" if mode == "jra" else "nar_top5_rank")),
                 "class_context": current, "class_history": history, "recent_runs": runs,
                 "legacy_class_shift": pick(row, "class_shift_market", "クラス変動"),
                 "input_sources": {"ability": ability_source, "recent": "saved_newspaper_past_block_with_date_matched_saved_index" if horse_no(row) in past_evidence else "saved_recent3", "class": current["class_source_v2"], "jockey": row.get("_v2_jockey_source", "saved_prediction_fields")},
                 "audit": {"recent_index_sd": pstdev(valid_indices) if len(valid_indices) >= 2 else None,
                           "days_since_last": number(pick(row, "_days_since_last", "days_since_last")),
                           "jockey_change": shadow_jockey_change(row),
                           "load_weight": pick(row, "_current_load_weight", "斤量"),
                           "load_weight_change": pick(row, "weight_change_market", "_load_weight_change"),
                           "existing_reproducibility": pick(row, "v1_reproducibility_rank", "再現性"),
                           "existing_position_bonus": number(row.get("jra_position_bonus")),
                           "corner4_rank": corner, "front_count": front_count, "provider_pace": pace},
                 prefix + "ability_anchor": ability,
                 prefix + "top5_candidate_score": scores["top5"], prefix + "win_candidate_score": scores["win"],
                 prefix + "top5_candidate_rank": None, prefix + "win_candidate_rank": None,
                 prefix + "data_quality": "insufficient" if ability is None or not valid_keys else "partial" if missing else "complete",
                 prefix + "missing_reasons": missing, prefix + "positive_reasons": positive,
                 prefix + "negative_reasons": negative}
        for name, value in components.items():
            if name != "ability":
                horse[prefix + name + "_score"] = value
        horses.append(horse)
    prefix = mode + "_v2_"
    for purpose in ("win", "top5"):
        eligible = [h for h in horses if h[prefix + purpose + "_candidate_score"] is not None]
        ordered = sorted(eligible, key=lambda h: (-h[prefix + purpose + "_candidate_score"], -h[prefix + "ability_anchor"], -(h[prefix + "recent_form_score"] or 0), int(h["horse_no"])))
        for rank, horse in enumerate(ordered, 1):
            horse[prefix + purpose + "_candidate_rank"] = rank
    return {"model_version": mode + "_newspaper_shadow_v1", "evaluated_at": evaluated_at or datetime.now(timezone.utc).isoformat(),
            "race_id": race_identifier, "race_mode": mode, "horse_count": len(horses),
            "status": "excluded_jump" if excluded else "invalid_horse_keys" if not valid_keys else "ok",
            "class_context": current, "coefficients": copy.deepcopy(config[mode]),
            "configuration_version": config["version"], "normalization": config["normalization"],
            "rationale": config["rationale"], "usage": "research_only_not_probability", "horses": horses}


def attach_newspaper_v2_shadow(result, html_files=None):
    """Called only by fresh predictors, never by restore or display."""
    key = result.race_mode + "_newspaper_v2_shadow"
    info = dict(result.race_info or {})
    info.setdefault("race_name", result.race_name)
    html_files = html_files or {}
    try:
        rows = shadow_jockey_inputs(result_rows(result), html_files.get("jockey", ""), info, race_id(result), result.race_mode)
        output = evaluate_shadow(rows, info, result.race_mode,
                                 html=html_files.get("newspaper") or html_files.get("newspaper_context") or "",
                                 race_identifier=race_id(result))
        # Fresh predictions only: capture the same formal comparison that the
        # existing UI uses. These ranks are audit labels, never V2 score inputs.
        if result.race_mode == "jra":
            from .v1_logic import build_v1_evaluations
            comparison = build_v1_evaluations(rows, "jra", race_info=info)
            official = {str(h.get("number")): h for h in comparison.get("rows", [])}
        else:
            from .nar_ability_rank import canonical_nar_ability_rank
            official = {horse_no(h): {"nar_top5_rank": canonical_nar_ability_rank(h), "ability_rank": canonical_nar_ability_rank(h)} for h in rows}
        for horse in output["horses"]:
            existing = official.get(horse["horse_no"], {})
            horse["official_top5_rank"] = existing.get(result.race_mode + "_top5_rank")
            horse["pure_ability_rank"] = existing.get("ability_rank", horse["pure_ability_rank"])
            horse["official_rank_source"] = "existing_formal_display_at_prediction"
    except (ValueError, TypeError, KeyError) as exc:
        output = {"model_version": result.race_mode + "_newspaper_shadow_v1", "status": "input_error", "error": str(exc), "horses": []}
    result.debug_info = {**(result.debug_info or {}), key: output}
    # Next research version is a separate sibling, never a replacement of v1.
    if output.get("race_mode") == result.race_mode:
        from .newspaper_v2_class_revision import evaluate_class_revision
        revision_key = result.race_mode + "_newspaper_v2_class_split_shadow"
        try:
            revision = evaluate_class_revision(rows, info, result.race_mode,
                html=html_files.get("newspaper") or html_files.get("newspaper_context") or "",
                base_v1=output)
        except (ValueError, TypeError, KeyError) as exc:
            revision = {"model_version": result.race_mode + "_newspaper_shadow_v2_class_split",
                        "status": "input_error", "error": str(exc), "horses": []}
        result.debug_info = {**result.debug_info, revision_key: revision}
    return result
