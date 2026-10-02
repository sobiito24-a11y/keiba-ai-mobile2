"""Separate research version: independent finish quality and class transition.

No formal predictions or v1 payloads are mutated. Coefficients are not fitted.
"""
import copy
import json
from pathlib import Path
from .newspaper_v2_class_inputs import previous_class_evidence, classify_previous, comparison_blockers, finish_quality
from .jra_class_v2 import classify_jra_class
from .nar_class_v2 import classify_nar_class


def configuration():
    return json.loads(Path(__file__).with_name("newspaper_v2_class_split.json").read_text(encoding="utf-8"))


def rank_payload(payload):
    prefix=payload["race_mode"]+"_v2_"
    for purpose in ("top5","win"):
        for h in payload["horses"]:h[prefix+purpose+"_candidate_rank"]=None
        eligible=[h for h in payload["horses"] if h[prefix+purpose+"_candidate_score"] is not None]
        ordered=sorted(eligible,key=lambda h:(-h[prefix+purpose+"_candidate_score"],-h[prefix+"ability_anchor"],-(h[prefix+"recent_form_score"] or 0),int(h["horse_no"])))
        for rank,h in enumerate(ordered,1):h[prefix+purpose+"_candidate_rank"]=rank
    return payload


def evaluate_class_revision(rows, info, mode, *, html="", base_v1=None, evaluated_at=None, race_identifier=""):
    if base_v1 is None:
        from .newspaper_v2_engine import evaluate_shadow
        base_v1=evaluate_shadow(rows,info,mode,html=html,evaluated_at=evaluated_at,race_identifier=race_identifier)
    if base_v1.get("race_mode") != mode or base_v1.get("model_version") != mode+"_newspaper_shadow_v1":
        raise ValueError("class revision requires matching v1 payload")
    out=copy.deepcopy(base_v1);config=configuration();prefix=mode+"_v2_"
    out["model_version"]=mode+"_newspaper_shadow_v2_class_split"
    out["parent_model_version"]=base_v1["model_version"]
    out["configuration_version"]=config["version"]
    out["class_split_configuration"]=config
    out["normalization"] += "; finish_quality=1-2*(finish-1)/(head_count-1); class_change uses only explicit comparable evidence; each receives half the former class weight"
    out["rationale"]["class"] = config["rationale"]
    out["usage"]="next_research_candidate_not_formal_not_probability"
    evidence=previous_class_evidence(html)
    for purpose,w in out["coefficients"].items():
        old=w.pop("class")
        w["finish_quality"]=old*config["finish_fraction_of_v1_class_weight"]
        w["class_change"]=old*config["transition_fraction_of_v1_class_weight"]
    for h in out["horses"]:
        old=h.pop(prefix+"class_score")
        fallback=dict(h["recent_runs"][0]) if h.get("recent_runs") else {}
        fallback["source"]="saved_prediction_first_past_slot"
        from .newspaper_v2_engine import run_number
        fallback["data04_raw"] = str(fallback.get("finish") or "")
        fallback["data05_raw"] = str(fallback.get("head_count") or "")
        fallback["finish"] = run_number(fallback.get("finish"))
        previous=evidence.get(h["horse_no"],fallback)
        current=copy.deepcopy(h["class_context"])
        # v1's implicit flat default is not evidence for cross-discipline comparison.
        if not info.get("surface") and not any(s in current.get("class_raw_v2","") for s in ("芝","ダ","障")):
            current["race_discipline_v2"]="unknown"
        ctx=classify_previous(previous)
        blockers=comparison_blockers(current,ctx)
        a,finish_flags=finish_quality(previous)
        b=None if blockers else max(-1.,min(1.,(ctx["class_level_v2"]-current["class_level_v2"])/(1 if mode=="jra" else 3)))
        # Audit the old gate using exactly the old class extraction, not repaired evidence.
        old_run=fallback
        raw=" ".join(str(old_run.get(k) or "") for k in ("race_name","race_data2","class_label"))
        old_ctx=(classify_jra_class if mode=="jra" else classify_nar_class)({"race_name":raw,"racecourse":old_run.get("venue"),"race_grade":old_run.get("race_grade")})
        _,old_finish_flags=finish_quality(old_run)
        old_blockers=comparison_blockers(h["class_context"],old_ctx)+old_finish_flags
        h[prefix+"finish_quality_score"]=a
        h[prefix+"class_change_score"]=b
        contributions={}
        for purpose,w in out["coefficients"].items():
            old_weight=base_v1["coefficients"][purpose]["class"]
            before=h[prefix+purpose+"_candidate_score"]
            ca=(a or 0)*w["finish_quality"];cb=(b or 0)*w["class_change"]
            h[prefix+purpose+"_candidate_score"]=None if before is None else before-(old or 0)*old_weight+ca+cb
            contributions[purpose]={"v1_combined":(old or 0)*old_weight,"finish_quality":ca,"class_change":cb,"delta":ca+cb-(old or 0)*old_weight}
        h["class_revision"]={"v1_class_score":old,"v1_invalid_reasons":old_blockers if old is None else [],
            "v1_previous_class":old_ctx,"previous_class":ctx,"previous_evidence":previous,
            "finish_invalid_reasons":finish_flags,"transition_invalid_reasons":blockers,"contributions":contributions}
        for kind in ("positive","negative"):
            h[prefix+kind+"_reasons"]=[s for s in h[prefix+kind+"_reasons"] if not s.startswith("比較可能クラス・着順")]
        for name,value in (("前走着順の質",a),("比較可能な前走→今回クラス差",b)):
            if value:
                h[prefix+("positive" if value>0 else "negative")+"_reasons"].append(f"{name} {value:+.2f}")
        missing=[s for s in h[prefix+"missing_reasons"] if s!="クラス・頭数比較不能（補正なし）"]
        missing.extend("着順の質: "+s for s in finish_flags)
        missing.extend("クラス変化: "+s for s in blockers)
        h[prefix+"missing_reasons"]=missing
        if h[prefix+"data_quality"]!="insufficient":h[prefix+"data_quality"]="partial" if missing else "complete"
    return rank_payload(out)


def without_class_reference(base_v1):
    out=copy.deepcopy(base_v1);mode=out["race_mode"];prefix=mode+"_v2_"
    out["model_version"]=mode+"_newspaper_shadow_v1_no_class_reference"
    out["usage"]="ablation_reference_only"
    for purpose,w in out["coefficients"].items():
        old=w["class"];w["class"]=0.
        for h in out["horses"]:
            key=prefix+purpose+"_candidate_score"
            if h[key] is not None:h[key]-=(h[prefix+"class_score"] or 0)*old
    return rank_payload(out)
