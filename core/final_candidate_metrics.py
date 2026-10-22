"""Read-only facts for the unmarked final-candidate comparison.

The source is the saved prediction row, not a result/settlement row.  In
particular NAR's ``平均指数`` and generic ``最高指数`` are not aliases for the
last-three average and the condition-specific saved ``★最高指数``.
"""
from collections.abc import Mapping

from .prediction_table_ui import number, text, fmt
from .game_ui_information import reasons
from .recent_condition_facts import STATES


RUN_LABELS = ("3走前", "2走前", "前走")
AVERAGE_KEYS = ("3走平均", "近3走平均", "recent3_avg", "recent3_mean")
MAXIMUM_KEYS = ("★最高指数", "★最高", "star_max_index", "_star_high")
MISSING = "未取得"


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _saved_number(row, keys):
    for key in keys:
        value = number(row.get(key))
        if value is not None:
            return value, key
    return None, ""


def _present(value):
    value = text(value)
    return "" if value in ("—", "―", "-", "未取得", "データなし") else value


def _first(row, keys):
    return next((value for key in keys if (value := _present(row.get(key)))), "")


def _condition(run):
    venue, surface = _present(run.get("venue")), _present(run.get("surface"))
    distance, turn = _present(run.get("distance")), _present(run.get("turn"))
    return "・".join(part for part in (venue, surface + distance, turn) if part) or MISSING


def _is_maximum(run, maximum, source):
    """Do not move a saved star from a different historical start to this one."""
    if maximum is None or number(run.get("time_index")) != maximum:
        return False
    label = _first(source, ("★該当走", "star_max_race", "_star_max_race"))
    if label and label != _present(run.get("label")):
        return False
    # Some archives identify the peak by condition instead of a recent label.
    for run_key, saved_keys in (
        ("venue", ("star_max_venue", "_star_max_venue")),
        ("surface", ("star_max_surface", "_star_max_surface")),
        ("turn", ("star_max_turn", "_star_max_turn")),
    ):
        expected = _first(source, saved_keys)
        actual = _present(run.get(run_key))
        if expected and (not actual or expected.replace("ダート", "ダ") != actual.replace("ダート", "ダ")):
            return False
    expected_distance, _ = _saved_number(source, ("star_max_distance", "_star_max_distance"))
    if expected_distance is not None:
        actual_distance = number(_present(run.get("distance")).removesuffix("m"))
        if actual_distance != expected_distance:
            return False
    return True


def _materials(value, extra):
    values = reasons(value)
    for item in extra if isinstance(extra, (list, tuple)) else []:
        values.extend(reasons(item))
    return " / ".join(dict.fromkeys(values)) or "—"


def _condition_record(conditions, key):
    item = _mapping(conditions.get(key))
    state = STATES.get(item.get("state"), "過去走データ不足")
    if item.get("state") in ("placed", "started"):
        return f"{state}（{item.get('top3', 0)}回／{item.get('starts', 0)}走・近3走）"
    return state


def project(horse, source=None):
    """Return display facts without changing either input.

    ``horse.profile.runs`` must be the existing ``candidate_profile.facts``
    projection: its date gate excludes current/future starts.  Missing labels
    remain missing; a finish position is never used as a time index.  Pass the
    saved row as ``source`` to retain the exact average/peak definitions.
    """
    source = _mapping(source)
    profile = _mapping(horse.get("profile"))
    evidence = _mapping(horse.get("candidate_evidence"))
    audit = _mapping(evidence.get("audit"))
    average, average_source = _saved_number(source, AVERAGE_KEYS)
    # In JRA only, the notebook explicitly defines 平均指数 as 3走平均.
    if average is None and horse.get("mode") == "jra":
        average, average_source = _saved_number(source, ("平均指数",))
    maximum, maximum_source = _saved_number(source, MAXIMUM_KEYS)

    by_label = {}
    for run in profile.get("runs", []) or []:
        if isinstance(run, Mapping) and run.get("label") in RUN_LABELS:
            by_label.setdefault(run["label"], run)
    runs = []
    for label in RUN_LABELS:
        run = by_label.get(label, {})
        runs.append(dict(label=label, date=_present(run.get("date")) or "—",
                         time_index=number(run.get("time_index")),
                         condition=_condition(run), is_maximum=_is_maximum(run, maximum, source)))
    # A display-only mean is safe when all three dated pre-race indices exist.
    # Never replace a saved mean or substitute NAR's five-run 平均指数.
    if average is None and all(run["time_index"] is not None for run in runs):
        average = round(sum(run["time_index"] for run in runs) / 3, 1)
        average_source = "dated_profile_runs"

    stars = number(profile.get("stability_stars"))
    stars = int(stars) if stars is not None and stars.is_integer() and 1 <= stars <= 5 else None
    stability = dict(stars=stars, text=f"{stars}/5（指数のばらつき）" if stars else MISSING)
    conditions = _mapping(_mapping(profile.get("condition_facts")).get("conditions"))
    rest_audit = _mapping(audit.get("rest"))
    rest_days = number(rest_audit.get("days")) if rest_audit else number(profile.get("rest_days"))
    rest = (fmt(rest_days) + "日") if rest_days is not None else _present(horse.get("rest")) or MISSING
    if rest_audit.get("status") == "conflict":
        rest_days, rest = None, "未取得（保存間隔と日付が不一致）"
    weights = _mapping(audit.get("weight"))
    weight_delta = number(weights.get("delta")) if weights else number(horse.get("weight_delta"))

    def index(key, saved_keys=()):
        cell = _mapping(horse.get(key))
        value = number(cell.get("value"))
        if value is None:
            value, _ = _saved_number(source, saved_keys)
        return dict(value=value, rank=number(cell.get("rank")))

    return dict(
        ability=dict(value=number(horse.get("ability")), rank=number(horse.get("ability_rank"))),
        distance=index("distance", ("距離指数", "distance_index")),
        course=index("course", ("コース指数", "course_index")),
        average=average, average_source=average_source,
        average_calculated=average_source == "dated_profile_runs",
        maximum=maximum, maximum_source=maximum_source, runs=runs, stability=stability,
        same_distance=_condition_record(conditions, "distance"),
        same_course=_condition_record(conditions, "venue_distance"),
        jockey_change=_present(horse.get("jockey_change_text")) or MISSING,
        rest=rest, rest_days=rest_days, weight_delta=weight_delta,
        plus=_materials(horse.get("plus"), evidence.get("plus")),
        caution=_materials(horse.get("caution"), evidence.get("minus")),
        style=_present(horse.get("style")) or MISSING,
        corner=number(horse.get("corner")),
        training=(_present(horse.get("training")) or MISSING) if horse.get("mode") == "jra" else "対象外",
    )
