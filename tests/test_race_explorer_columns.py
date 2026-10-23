"""Every normal table cell can be sorted/filtered without predicting anew."""
from copy import deepcopy
import json

import pytest

from core.race_explorer_columns import columns, records


def horse(no="7", mode="jra"):
    return dict(
        no=no, name="保存馬", mode=mode, frame=3, age="牝4", jockey="今回騎手",
        candidate_formal_score=92.123456789, rank="3", ability="83.7", ability_rank="2",
        distance=dict(value=70.3, rank=5), course=dict(value=65.1, rank=7),
        mark="◎", formal_member=True, score="9.9", internal_score=-999,
        style="差", corner=9, odds="13.6", popularity=6,
        sort_values=dict(odds=13.6, popularity=6),
        odds_time="2026-10-22 14:00", odds_received_at="2026-10-22 14:01",
        odds_source="manual HTML", odds_label="発走前の観測値",
        explorer_facts=dict(
            current_jockey="今回騎手", current_weight=56.0, weight_delta=-1.0,
            weight_label="56kg", weight_delta_label="−1kg", jockey_change="前走騎手 → 今回騎手",
            rest_days=21, rest_label="中2週", training="A",
            metrics=dict(ability=dict(value=83.7, rank=2), distance=dict(value=70.3, rank=5),
                         course=dict(value=65.1, rank=7), average=70.1, maximum=93.2),
            runs=[dict(label=label, time_index=index, condition=condition, date=date,
                       is_maximum=peak) for label, index, condition, date, peak in (
                           ("前走", 71, "京都・芝1800m・右", "2026-10-01", False),
                           ("3走前", 46, "東京・芝1600m・左", "2026-08-01", False),
                           ("2走前", 93.2, "東京・芝1600m・左", "2026-09-01", True))],
            condition_records=[dict(key=key, text=text) for key, text in (
                ("venue", "京都（芝・ダート通算）：1戦1回3着以内（近3走の範囲）"),
                ("surface_distance", "芝1800m：1戦1回3着以内（近3走の範囲）"),
                ("venue_distance", "京都芝1800m：1戦1回3着以内（近3走の範囲）"))],
            plus=["○ 保存済みの好材料", "指数の根拠"], caution="△ 保存済みの注意材料"),
    )


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_schema_covers_every_comparison_cell_and_has_no_ai_mark_or_membership(mode):
    view=[horse(mode=mode)]
    specs=columns(view)
    keys=[item["key"] for item in specs]
    assert len(keys)==len(set(keys))
    assert keys[:10]==["user", "frame", "no", "name", "age", "jockey", "odds", "popularity", "score", "rank"]
    assert keys[keys.index("run_old"):keys.index("run_old")+5]==[
        "run_old", "run_middle", "run_latest", "average", "maximum"]
    assert ("training" in keys)==(mode=="jra")
    assert all(item["type"] in ("number", "rank", "text", "grade", "boolean") for item in specs)
    assert not set(keys).intersection(("mark", "formal_member", "candidate", "pickup", "focus_label"))
    assert keys[-4:]==["record_venue", "record_distance", "record_venue_distance", "materials"]
    record=records(view)["7"]
    assert all(key in record for key in keys)
    assert all(record[item["text_key"]] for item in specs if "text_key" in item)
    if mode=="jra":
        assert next(item for item in specs if item["key"]=="training")["options"]==["A", "B", "C", "D"]
    else:
        assert record["training"] is None


def test_projection_uses_saved_exact_numbers_and_dated_run_labels_without_mutation():
    view=[horse(),horse("2")]
    before=deepcopy(view)
    cells=records(view)
    item=cells["7"]
    assert item["user"] is False
    assert (item["frame"],item["no"],item["score"],item["rank"])==(3,7,92.123456789,3)
    assert (item["ability"],item["ability_rank"])==(83.7,2)
    assert (item["distance"],item["distance_rank"],item["course"],item["course_rank"])==(70.3,5,65.1,7)
    assert [item[key] for key in ("run_old","run_middle","run_latest")]==[46,93.2,71]
    assert item["run_old_condition"]=="東京・芝1600m・左"
    assert item["run_latest_date"]=="2026-10-01"
    assert not item["run_old_is_maximum"] and item["run_middle_is_maximum"]
    assert (item["average"],item["maximum"],item["rest_days"],item["weight_delta"])==(70.1,93.2,21,-1)
    assert item["jockey_change"]=="前走騎手 → 今回騎手"
    assert "芝・ダート通算" in item["record_venue"]
    assert "近3走の範囲" in item["record_distance"]
    assert "保存済みの好材料" in item["materials"] and "保存済みの注意材料" in item["materials"]
    assert not any(mark in item["materials"] for mark in "◎○▲✔△✓")
    json.dumps(cells,allow_nan=False)
    assert view==before
    cells["7"]["score"]=-100
    assert view==before


@pytest.mark.parametrize("bad", [None, "未取得", "—", "nan", "NaN", "Infinity", float("inf"), -float("inf"), True, {"value":7}, 10**1000])
def test_unknown_or_invalid_numeric_cells_are_json_null_never_zero(bad):
    h=horse()
    h.update(candidate_formal_score=bad,rank=bad,frame=bad,corner=bad,popularity=bad,odds=bad)
    h["sort_values"].update(odds=bad,popularity=bad)
    facts=h["explorer_facts"]
    facts.update(current_weight=bad,weight_delta=bad,rest_days=bad)
    facts["metrics"].update(average=bad,maximum=bad,ability=dict(value=bad,rank=bad))
    for run in facts["runs"]:
        run["time_index"]=bad
    item=records([h])["7"]
    for key in ("score","rank","frame","corner","popularity","odds","weight","weight_delta","rest_days",
                "average","maximum","ability","ability_rank","run_old","run_middle","run_latest"):
        assert item[key] is None,key
    assert not item["run_middle_is_maximum"]
    json.dumps(item,allow_nan=False)


def test_zero_and_negative_indices_keep_their_meaning_and_ranks_are_not_recomputed():
    h=horse()
    h["explorer_facts"]["metrics"].update(ability=dict(value=-2.5,rank=12),distance=dict(value=0,rank=18),
                                        course=dict(value=1,rank=1.5),average=0,maximum=-1)
    h["explorer_facts"].update(weight_delta=0,rest_days=0)
    result=records([h])["7"]
    assert (result["ability"],result["ability_rank"],result["distance"],result["distance_rank"])==(-2.5,12,0,18)
    assert result["course_rank"] is None
    assert result["average"]==result["weight_delta"]==result["rest_days"]==0
    assert result["maximum"]==-1


def test_partial_odds_or_withdrawal_cannot_revive_stale_saved_price_or_popularity():
    h=horse()
    h.update(odds="13.6",popularity=None)
    h["sort_values"].update(odds=None,popularity=None)
    result=records([h])["7"]
    assert result["odds"] is None and result["popularity"] is None
    h["popularity"]=6  # An explicit null observation must also win over stale rank text.
    assert records([h])["7"]["popularity"] is None
    assert result["odds_time"]=="2026-10-22 14:00"
    assert result["odds_received_at"]=="2026-10-22 14:01"
    h["odds"]="取消・除外"
    result=records([h])["7"]
    assert result["withdrawn"] and result["odds"] is None
    h.pop("sort_values")
    h.update(odds="4.2",popularity=None)
    result=records([h])["7"]
    assert result["odds"]==4.2 and result["popularity"] is None


def test_explicit_missing_formal_score_never_uses_reference_or_research_b_score():
    h=horse()
    h.update(candidate_formal_score=None,reference_score=dict(kind="reference",value=99),score=99)
    assert records([h])["7"]["score"] is None
    h.update(active_model="B",score=999,rank="1",internal_score=999,
             model_a=dict(score=92.123456789,rank="3"),model_b=dict(score=999,rank=1))
    assert records([h])["7"]["score"] is None
    assert records([h])["7"]["rank"]==3
    h["candidate_formal_score"]=92.123456789
    assert records([h])["7"]["score"]==92.123456789


def test_missing_malformed_display_substructures_stay_renderable_and_uninvented():
    h=dict(no="1",name="</script>保存馬",mode="jra",explorer_facts={
        "metrics":"bad", "runs":"bad", "condition_records":None,"training":"X"},
        final_metrics="bad",sort_values=None)
    before=deepcopy(h)
    item=records([h])["1"]
    assert item["name"]=="</script>保存馬"  # Escaping belongs to HTML/JSON renderer.
    assert all(item[key] is None for key in ("score","ability","distance","maximum","run_old","record_venue","training"))
    assert h==before
    assert records([])=={} and len(columns([]))==31


def test_malformed_optional_peak_and_condition_metadata_do_not_hide_the_field():
    import pandas as pd
    h=horse()
    h["explorer_facts"]["condition_records"].append(dict(key=[],text="壊れた条件キー"))
    h["explorer_facts"]["runs"][0]["is_maximum"]=pd.NA
    h["odds"]=pd.NA
    item=records([h])["7"]
    assert item["run_latest"]==71 and not item["run_latest_is_maximum"]
    assert item["record_venue_distance"].startswith("京都芝1800m：1戦1回")
    assert item["score"]==92.123456789
    assert not item["withdrawn"]
    json.dumps(item,allow_nan=False)
