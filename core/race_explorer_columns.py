"""Typed, read-only cells for the normal all-runner comparison table.

The browser may sort and filter these values, but they are never prediction
inputs.  In particular ranks are saved ranks, prices come from the existing
race-wide odds overlay, and absent values remain JSON null rather than zero.
"""
from collections.abc import Mapping
from math import isfinite

from .final_candidate_selection import formal_score
from .race_explorer_common import material_text


_MISSING = frozenset(("", "—", "―", "－", "-", "未取得", "不明", "対象外",
                      "データなし", "未計算", "none", "nan", "nat", "<na>",
                      "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"))
_RUNS = (("run_old", "3走前"), ("run_middle", "2走前"), ("run_latest", "前走"))


def _mapping(item):
    return item if isinstance(item, Mapping) else {}


def _number(item):
    if isinstance(item, bool):
        return None
    try:
        result = float(item)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _integer(item, minimum=1, maximum=None):
    result = _number(item)
    if result is None or not result.is_integer() or result < minimum:
        return None
    return int(result) if maximum is None or result <= maximum else None


def _text(item):
    if item is None or isinstance(item, (bool, Mapping, list, tuple, set)):
        return None
    result = str(item).strip()
    return None if result.casefold() in _MISSING else result


def _material(item):
    values = item if isinstance(item, (list, tuple)) else (item,)
    result = [clean for value in values
              if (raw := _text(value)) and (clean := _text(material_text(raw)))]
    return " / ".join(result) or None


def _spec(key, label, kind, **extra):
    return dict(key=key, label=label, type=kind, **extra)


def columns(view):
    """Return the comparison schema, with training present only for JRA.

    Paired ranks remain independently sortable/filterable but share the value
    cell in the table rather than consuming another horizontal column.

    A numeric historical-index column also has a ``text_key`` pointing to its
    saved condition/date text.  This permits condition searches without
    converting the numeric sort or index range into a lexical comparison.
    """
    jra = bool(view and _mapping(view[0]).get("mode") == "jra")
    result = [
        _spec("user", "自分の✓", "boolean"),
        _spec("frame", "枠番", "number"), _spec("no", "馬番", "number"),
        _spec("name", "馬名", "text"), _spec("age", "性齢", "text"),
        _spec("jockey", "騎手", "text"), _spec("odds", "単勝", "number"),
        _spec("popularity", "人気", "rank"),
        _spec("score", "JRA正式評価スコア" if jra else "NAR最終評価スコア", "number", rank_key="rank"),
        _spec("rank", "正式順位", "rank", table_hidden=True),
        _spec("ability", "純能力指数", "number", rank_key="ability_rank"),
        _spec("ability_rank", "純能力順位", "rank", table_hidden=True),
        _spec("distance", "距離指数", "number", rank_key="distance_rank"),
        _spec("distance_rank", "距離順位", "rank", table_hidden=True),
        _spec("course", "コース指数", "number", rank_key="course_rank"),
        _spec("course_rank", "コース順位", "rank", table_hidden=True),
    ]
    for key, label in (("star", "同場同距離指数"), ("away", "別場同距離指数")):
        if any(_number(_mapping(_mapping(horse).get(key)).get("value")) is not None for horse in view or ()):
            result.extend((_spec(key, label, "number", rank_key=key + "_rank"),
                           _spec(key + "_rank", label + "順位", "rank", table_hidden=True)))
    if any(_reference_score(_mapping(horse)) is not None for horse in view or ()):
        result.append(_spec("reference_score", "参考スコア（正式評価外）", "number"))
    result.extend([
        *(_spec(key, label, "number", text_key=key + "_condition")
          for key, label in _RUNS),
        _spec("average", "3走平均", "number"),
        _spec("maximum", "★最高指数", "number"),
        _spec("style", "想定脚質", "text"),
        _spec("corner", "4角想定", "rank"),
        _spec("rest_days", "前走間隔", "number", unit="日"),
    ])
    if jra:
        result.append(_spec("training", "調教", "grade", options=["A", "B", "C", "D"]))
    result.extend((
        _spec("weight", "今回斤量", "number", unit="kg"),
        _spec("weight_delta", "前走比", "number", unit="kg"),
        _spec("jockey_change", "騎手変更", "text"),
        _spec("record_venue", "同競馬場実績", "text"),
        _spec("record_distance", "同距離実績", "text"),
        _spec("record_venue_distance", "同競馬場・同距離実績", "text"),
        _spec("materials", "判断材料", "text"),
    ))
    return result


def _metric(horse, metrics, key):
    """Read the existing metric cell; an explicit missing cell stays missing."""
    cell = _mapping(metrics.get(key)) if key in metrics else _mapping(horse.get(key))
    if key == "ability" and key not in metrics:
        cell = dict(value=horse.get("ability"), rank=horse.get("ability_rank"))
    index = _number(cell.get("value"))
    return index, _integer(cell.get("rank")) if index is not None else None


def _a_values(horse):
    # The normal route receives A.  If a research projection is accidentally
    # passed here, copied B scores must not become the A column values.
    if horse.get("active_model") == "B":
        model_a = _mapping(horse.get("model_a"))
        score = (_number(horse.get("candidate_formal_score"))
                 if "candidate_formal_score" in horse else _number(model_a.get("score")))
        rank = _integer(model_a.get("rank"))
        return score, None if horse.get("mode") == "nar" and score is None else rank
    try:
        score = _number(formal_score(horse))
    except (TypeError, ValueError, OverflowError):
        score = None
    rank = _integer(horse.get("rank"))
    # NAR may retain a reference display rank below Top5. It does not attest to
    # a formal score/rank, and must never be shown as such in the normal UI.
    return score, None if horse.get("mode") == "nar" and score is None else rank


def _reference_score(horse):
    saved = _mapping(horse.get("reference_score"))
    return _number(saved.get("value")) if horse.get("mode") == "nar" and saved.get("kind") == "reference" else None


def _record_text(facts):
    raw = facts.get("condition_records")
    return {item.get("key"): _text(item.get("text")) for item in raw
            if isinstance(item, Mapping) and isinstance(item.get("key"), str)} if isinstance(raw, (list, tuple)) else {}


def records(view):
    """Return horse-number keyed JSON scalar cells without changing the view.

    ``user`` is deliberately false for every row.  The browser replaces that
    one cell with its separate manual-selection set.  No AI membership/mark is
    serialized here and no rank is calculated from scores or odds.
    """
    result = {}
    for raw in view or ():
        horse = _mapping(raw)
        no = str(horse.get("no", ""))
        facts = _mapping(horse.get("explorer_facts"))
        metrics = _mapping(facts.get("metrics")) or _mapping(horse.get("final_metrics"))
        sort = _mapping(horse.get("sort_values"))
        prices = _number(sort.get("odds") if "odds" in sort else horse.get("odds"))
        # Partial batches and withdrawals have explicit null overlay cells;
        # never revive an older raw horse price or a guessed popularity rank.
        odds = prices if prices is not None and prices > 0 else None
        popularity = _integer(sort.get("popularity") if "popularity" in sort else horse.get("popularity"))
        score, rank = _a_values(horse)
        ability, ability_rank = _metric(horse, metrics, "ability")
        distance, distance_rank = _metric(horse, metrics, "distance")
        course, course_rank = _metric(horse, metrics, "course")
        star, star_rank = _metric(horse, {}, "star")
        away, away_rank = _metric(horse, {}, "away")
        condition = _record_text(facts)
        plus, caution = _material(facts.get("plus")), _material(facts.get("caution"))
        materials = " / ".join(label + text for label, text in (
            ("プラス：", plus), ("注意：", caution)) if text) or None
        grade = _text(facts.get("training"))
        grade = grade if grade in ("A", "B", "C", "D") and horse.get("mode") == "jra" else None
        current_weight = _number(facts.get("current_weight"))
        item = dict(
            user=False, frame=_integer(horse.get("frame"), maximum=8),
            no=_integer(horse.get("no")), name=_text(horse.get("name")),
            age=_text(horse.get("age")),
            jockey=_text(facts.get("current_jockey", horse.get("jockey"))),
            odds=odds, popularity=popularity, score=score, rank=rank,
            ability=ability, ability_rank=ability_rank,
            distance=distance, distance_rank=distance_rank,
            course=course, course_rank=course_rank,
            star=star, star_rank=star_rank, away=away, away_rank=away_rank,
            reference_score=_reference_score(horse),
            average=_number(metrics.get("average")), maximum=_number(metrics.get("maximum")),
            style=_text(metrics.get("style", horse.get("style"))),
            corner=_integer(metrics.get("corner", horse.get("corner"))),
            rest_days=_integer(facts.get("rest_days"), minimum=0), training=grade,
            weight=current_weight if current_weight is not None and current_weight > 0 else None,
            weight_delta=_number(facts.get("weight_delta")),
            jockey_change=_text(facts.get("jockey_change")),
            record_venue=condition.get("venue"),
            record_distance=condition.get("surface_distance"),
            record_venue_distance=condition.get("venue_distance"), materials=materials,
            rest_label=_text(facts.get("rest_label")),
            weight_label=_text(facts.get("weight_label")),
            weight_delta_label=_text(facts.get("weight_delta_label")),
            plus=plus, caution=caution,
            odds_label=_text(horse.get("odds_label")),
            odds_source=_text(horse.get("odds_source")),
            odds_time=_text(horse.get("odds_time")),
            odds_received_at=_text(horse.get("odds_received_at")),
            withdrawn=isinstance(horse.get("odds"), str) and horse.get("odds") == "取消・除外",
        )
        raw_runs = facts.get("runs")
        if not isinstance(raw_runs, (list, tuple)):
            raw_runs = metrics.get("runs")
        runs = {run.get("label"): run for run in raw_runs if isinstance(run, Mapping)} if isinstance(raw_runs, (list, tuple)) else {}
        for key, label in _RUNS:
            run = _mapping(runs.get(label))
            item[key] = _number(run.get("time_index"))
            item[key + "_condition"] = _text(run.get("condition"))
            item[key + "_date"] = _text(run.get("date"))
            item[key + "_is_maximum"] = run.get("is_maximum") is True and item[key] is not None
        result[no] = item
    return result
