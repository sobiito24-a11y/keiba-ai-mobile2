"""Read-only facts for race pickup cards and the shared all-runner detail.

Saved prediction metrics keep their existing definitions.  This projection
only changes the order used to present dated history and adds factual labels;
it never writes to prediction rows, profiles, evidence or archive data.
"""
from collections.abc import Mapping
from copy import deepcopy
from datetime import timedelta
import re

from .candidate_profile import day
from .condition_fit import _distance_int, _venue_key
from .final_candidate_metrics import project as candidate_metrics
from .game_ui_candidate_evidence import verified_interval, weight_pair
from .jockey_positive import inputs as jockey_inputs
from .prediction_table_ui import fmt, number, text
from .recent_condition_facts import surface
from .supplementary_assessment import training as training_grade


MISSING = "未取得"
RUN_LABELS = ("3走前", "2走前", "前走")
SCOPE = "開催日前の保存過去3走（近3走の範囲）"
REST_DEFINITION = ("日数は今回開催日から直近の実出走日を引いた暦日数。"
                   "中N週は月曜始まりの開催週間に挟まる週数。"
                   "約Nヶ月は30.4375日を1ヶ月とする概数。")
REST_KEYS = ("_days_since_last", "レース間隔日数", "rest_days", "_新聞前走間隔日数")


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _present(value):
    value = text(value)
    return "" if value in ("—", "―", "-", MISSING, "データなし", "不明", "未計算") else value


def _first(row, keys):
    return next((value for key in keys if (value := _present(row.get(key)))), "")


def _finish(value):
    """Normalize a finish only for deciding whether an actual start occurred."""
    value = _present(value)
    match = re.fullmatch(r"(\d+)(?:\.0)?(?:着)?", value)
    return int(match[1]) if match and int(match[1]) > 0 else value


def _started(run):
    finish = _finish(run.get("finish"))
    return isinstance(finish, int) or finish in ("中止", "失格", "競走中止")


def _condition(run):
    return "・".join(part for part in (
        _present(run.get("venue")),
        _present(run.get("surface")) + _present(run.get("distance")),
        _present(run.get("turn")),
    ) if part) or MISSING


def _runs(profile, metrics, race_info):
    current = day(_first(race_info, ("race_date", "date", "開催日")))
    by_label = {}
    for run in profile.get("runs", []) or []:
        if not isinstance(run, Mapping) or run.get("label") not in RUN_LABELS:
            continue
        previous = day(run.get("date"))
        # candidate_profile already gates these dates; repeat the boundary when
        # current metadata is available so no current result can leak in.
        if previous is None or (current and previous >= current):
            continue
        by_label.setdefault(run["label"], run)
    saved = {run.get("label"): run for run in metrics.get("runs", []) or []
             if isinstance(run, Mapping)}
    result = []
    for label in RUN_LABELS:
        run = by_label.get(label, {})
        metric = saved.get(label, {}) if run else {}
        item = dict(label=label, **{
            key: _present(run.get(key)) or MISSING
            for key in ("date", "finish", "venue", "surface", "distance", "turn", "class_raw")
        })
        index = number(run.get("time_index"))
        item.update(time_index=index, condition=_condition(run),
                    is_maximum=bool(metric.get("is_maximum")) and index is not None
                    and index == number(metric.get("time_index")))
        result.append(item)
    return result


def _rest(source, profile, audit, race_info):
    info = dict(race_info)
    saved_audit = _mapping(audit.get("rest"))
    if not _first(info, ("race_date", "date", "開催日")) and saved_audit.get("race_date"):
        info["race_date"] = saved_audit["race_date"]
    raw_runs = source.get("_past_runs") or source.get("past_runs")
    if not isinstance(raw_runs, (list, tuple)):
        raw_runs = profile.get("runs", []) or []
    normalized = []
    for run in raw_runs:
        if not isinstance(run, Mapping):
            continue
        dated = day(_first(run, ("race_date", "date", "previous_date", "日付")))
        finish = _finish(_first(run, ("position", "finish", "previous_finish", "着順")))
        normalized.append(dict(race_date=dated.isoformat() if dated else None,
                               position="中止" if finish == "競走中止" else finish))
    interval = verified_interval(dict(source, _past_runs=normalized), info)
    days = interval["days"]
    # A prior evidence audit may intentionally have suppressed a conflicting
    # interval; never revive it through a different display fallback.
    conflict = saved_audit.get("status") == "conflict" or interval["status"] == "conflict"
    if days is not None:
        conflict |= any(number(source.get(key)) is not None and number(source[key]) != days
                        for key in REST_KEYS)
    if conflict:
        return None, "未取得（保存間隔と日付が不一致）", "conflict"
    if days is None:
        return None, MISSING, "unknown"
    previous, current = day(interval["last_start"]), day(interval["race_date"])
    weeks = ((current - timedelta(days=current.weekday())) -
             (previous - timedelta(days=previous.weekday()))).days // 7
    if days < 14:
        label = "連闘" if weeks == 1 else f"{days}日ぶり"
    elif days <= 35:
        label = f"中{max(0, weeks - 1)}週"
    elif 40 <= days <= 50:
        label = "約1ヶ月半"
    elif 60 <= days < 120:
        label = f"約{int(days / 30.4375 + .5)}ヶ月"
    else:
        label = f"{days}日ぶり"
    return days, label, "verified"


def _jockey(source, horse, audit):
    values = _mapping(audit.get("jockey")) or jockey_inputs(source)
    current = _present(values.get("current_jockey_name"))
    previous = _present(values.get("previous_jockey_name"))
    if not current:
        # The view may contain a current rider when older saved rows do not.
        current = re.sub(r"[（(](?:継続|継|乗替|乗り替わり|替|—)[）)]$", "",
                         _present(horse.get("jockey"))).strip()
    status = _present(values.get("jockey_change_status"))
    if not current:
        status, change = MISSING, "今回騎手未取得"
    elif not previous:
        status = "乗替" if status == "乗替" else MISSING
        change = "乗替・前走騎手未取得" if status == "乗替" else "前走騎手未取得"
    elif status == "乗替":
        change = f"{previous} → {current}"
    elif status == "継続":
        change = "継続"
    else:
        status, change = MISSING, MISSING
    return current or MISSING, previous or MISSING, status, change


def _weights(source, audit):
    values = _mapping(audit.get("weight"))
    values = values if values else weight_pair(source)
    current, previous = number(values.get("current")), number(values.get("previous"))
    current = current if current is not None and current > 0 else None
    previous = previous if previous is not None and previous > 0 else None
    delta = number(values.get("delta")) if current is not None and previous is not None else None
    label = f"{fmt(current)}kg" if current is not None else MISSING
    delta_label = MISSING if delta is None else "±0kg" if delta == 0 else f"{delta:+g}kg".replace("-", "−")
    return current, previous, delta, label, delta_label


def _current(source, profile, race_info):
    """Do not infer today's distance from a saved historical peak condition."""
    existing = _mapping(_mapping(profile.get("condition_facts")).get("current"))
    venue = _first(race_info, ("venue", "racecourse", "競馬場", "開催場")) or _first(
        source, ("_racecourse", "_current_racecourse", "_current_venue", "racecourse", "venue", "競馬場"))
    ground = _first(race_info, ("surface", "芝ダート", "track_type", "芝ダ", "馬場種別")) or _first(
        source, ("_race_surface", "_current_surface", "surface", "芝ダ", "馬場種別"))
    distance = _distance_int(_first(race_info, ("distance", "距離")) or _first(
        source, ("_race_distance", "race_distance", "distance", "距離")))
    # The existing projection is safe as a venue/surface fallback. Its distance
    # fallback can be star_max_distance, which does not prove today's distance.
    return dict(venue=_venue_key(venue or existing.get("venue")),
                surface=surface(ground or existing.get("surface")), distance=distance)


def _records(current, runs):
    venue, ground, distance = current["venue"], current["surface"], current["distance"]
    short_surface = ground or "馬場未取得"
    distance_text = f"{distance}m" if distance is not None else "距離未取得"
    specs = (
        ("venue_distance", ("venue", "surface", "distance"), (venue or "会場未取得") + short_surface + distance_text),
        ("venue_surface", ("venue", "surface"), (venue or "会場未取得") + ("ダート" if ground == "ダ" else short_surface)),
        ("surface_distance", ("surface", "distance"), short_surface + distance_text),
        ("venue", ("venue",), (venue + "（芝・ダート通算）") if venue else "会場未取得"),
    )
    records = []
    for key, required, label in specs:
        starts = top3 = unknown = 0
        for run in runs:
            if _present(run.get("date")) == "":
                unknown += 1
                continue
            finish = _finish(run.get("finish"))
            if any(word in str(finish) for word in ("取消", "除外")):
                continue
            facts = dict(venue=_venue_key(_present(run.get("venue"))),
                         surface=surface(_present(run.get("surface"))),
                         distance=_distance_int(_present(run.get("distance"))))
            # A known mismatch suffices to exclude a run with another missing
            # field; missing finish/conditions never become invented starts.
            if any(current.get(k) and facts.get(k) and current[k] != facts[k] for k in required):
                continue
            if not all(current.get(k) and facts.get(k) for k in required) or not _started(run):
                unknown += 1
                continue
            starts += 1
            top3 += isinstance(finish, int) and finish <= 3
        detail = (f"{label}：{starts}戦{top3}回3着以内（近3走の範囲）"
                  if all(current.get(k) for k in required)
                  else f"{label}：未取得（今回条件未取得・近3走の範囲）")
        if unknown:
            detail += f"・未確認{unknown}走"
        records.append(dict(key=key, label=label, starts=starts, top3=top3,
                            unknown=unknown, scope=SCOPE, text=detail))
    return records


def _original_comment(source):
    # Market/display comments may be shortened, annotated or generated. Only
    # original fields from the raw saved row are eligible; preserve all bytes
    # of the Python string, including whitespace and line breaks.
    for key in ("stable_comment_raw", "厩舎コメント原文", "新聞コメント", "厩舎コメント", "stable_comment", "馬コメント"):
        value = source.get(key)
        if isinstance(value, str) and _present(value):
            return value, key
    return MISSING, MISSING


def project(horse, source=None, race_info=None):
    """Project display facts from existing pre-race inputs without mutation.

    Pass the raw saved prediction row as ``source``. In particular, an
    annotated display row must not be used as an original stable comment.
    The optional race metadata establishes the current-date boundary.
    """
    horse, source, race_info = _mapping(horse), _mapping(source), _mapping(race_info)
    profile = _mapping(horse.get("profile"))
    evidence = _mapping(horse.get("candidate_evidence"))
    audit = _mapping(evidence.get("audit"))
    metrics = deepcopy(_mapping(horse.get("final_metrics")) or candidate_metrics(horse, source))
    runs = _runs(profile, metrics, race_info)
    rest_days, rest_label, rest_status = _rest(source, profile, audit, race_info)
    current_jockey, previous_jockey, jockey_status, jockey_change = _jockey(source, horse, audit)
    current_weight, previous_weight, weight_delta, weight_label, weight_delta_label = _weights(source, audit)
    grade = (training_grade({"training_grade": horse.get("training")})
             or training_grade(source) or MISSING) if horse.get("mode") == "jra" else "対象外"
    current = _current(source, profile, race_info)
    records = _records(current, runs)
    changes, feature_changes = [], []
    dated = [r for r in runs if day(r.get("date")) and _started(r)]
    latest = max(dated, key=lambda r: day(r["date"])) if dated else {}
    previous_distance = _distance_int(_present(latest.get("distance")))
    if current["distance"] is not None and previous_distance is not None and current["distance"] != previous_distance:
        feature_changes.append(f"距離変更 {previous_distance}→{current['distance']}m")
    previous_surface = surface(_present(latest.get("surface")))
    if current["surface"] and previous_surface and current["surface"] != previous_surface:
        feature_changes.append(f"馬場変更 {previous_surface}→{current['surface']}")
    # No first-turf/dirt/blinker claim can be derived from this three-run
    # window. Current archives have neither full career nor equipment history.
    if rest_days is not None and rest_days >= 90:
        feature_changes.append(("長期休養明け" if rest_days >= 180 else "休養明け") + f"（{rest_days}日）")
    changes.extend(feature_changes)
    if jockey_status == "乗替":
        changes.append("乗替 " + jockey_change if previous_jockey != MISSING else jockey_change)
    if weight_delta is not None:
        changes.append("斤量前走比 " + weight_delta_label)
    if grade not in (MISSING, "対象外"):
        changes.append("調教" + grade)
    features = []
    supported = next((record for record in records if record["starts"] and record["top3"]), None)
    if supported is None:
        supported = next((record for record in records if record["starts"]), None)
    if supported:
        features.append(supported["text"].split("・未確認", 1)[0])
    features.extend(feature_changes)
    if grade == "A":
        features.append("調教A")
    comment, comment_source = _original_comment(source)
    interpretation = " / ".join(dict.fromkeys(
        _present(value) for value in evidence.get("neutral", []) or [] if _present(value)))
    if _present(profile.get("state_reason")):
        interpretation = "。".join(value for value in (
            interpretation, "指数推移：" + (_present(profile.get("state")) or "判定不可"),
            _present(profile.get("state_reason"))) if value)
    return dict(rest_days=rest_days, rest_label=rest_label, rest_status=rest_status,
                rest_definition=REST_DEFINITION,
                current_jockey=current_jockey, previous_jockey=previous_jockey,
                jockey_status=jockey_status, jockey_change=jockey_change,
                current_weight=current_weight, previous_weight=previous_weight,
                weight_delta=weight_delta, weight_label=weight_label, weight_delta_label=weight_delta_label,
                training=grade, runs=runs, condition_records=records,
                features=list(dict.fromkeys(features))[:3], changes=list(dict.fromkeys(changes)),
                stable_comment_raw=comment, stable_comment_source=comment_source,
                interpretation=interpretation or MISSING,
                plus=_present(metrics.get("plus")) or MISSING,
                caution=_present(metrics.get("caution")) or MISSING, metrics=metrics)
