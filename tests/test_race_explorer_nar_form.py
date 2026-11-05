"""Actual NAR mobile screen shows previous-race reference separately from pure ability."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.race_explorer_nar_form import with_nar_form_reference
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html
from core.race_explorer_cards import detail_html


def _source(no: int, ability: float, last_rank: int):
    return dict(
        馬番=no, 馬名=f"船橋馬{no}", market_ability_score=ability,
        market_ability_rank=1 if no == 1 else 2,
        netkeiba_corner4_rank=last_rank,
        _lap_prediction_status="HTML内に実値なし",
        _netkeiba_pace="H",
        _past_runs=[
            dict(label="前走", race_date="2026-11-01", position=4,
                 corner4_rank=last_rank, value=55.0),
        ],
    )


def test_nar_actual_explorer_has_reference_rank_sort_and_horse_evidence():
    source = [_source(1, 80, 4), _source(2, 78, 2)]
    view = [
        dict(mode="nar", no=str(no), name=f"船橋馬{no}", ability_rank=str(no))
        for no in (1, 2)
    ]
    original = deepcopy((view, source))
    revised = with_nar_form_reference(
        view, source, {"date": "2026-11-04", "venue": "船橋", "distance": 1200},
    )
    assert len(revised) == 2
    assert {x["nar_form_ref_rank"] for x in revised} == {1, 2}
    assert revised[1]["nar_form_ref_prior_corner"] == 2
    assert revised[1]["nar_form_ref_pace"] == "未取得"
    assert (view, source) == original

    specs = columns(revised)
    assert "nar_form_rank" in [spec["key"] for spec in specs]
    assert "NAR前走参考順位" in [spec["label"] for spec in specs]
    assert "nar_form_reason" in [spec["key"] for spec in specs]
    assert records(revised)["2"]["nar_form_rank"] in (1, 2)
    doc = BeautifulSoup(lineup_html(revised), "html.parser")
    assert doc.select_one("th.col-nar_form_rank .column-label").text == "NAR前走参考順位"
    assert len(doc.select("td.col-nar_form_rank")) == 2
    assert doc.select_one('#lineup-sort option[value="nar_form_rank"]') is not None
    assert doc.select_one('#filter-column option[value="nar_form_reason"]') is not None
    detail = BeautifulSoup(detail_html(revised[1]), "html.parser")
    assert detail.select_one(".detail-nar-form h4").text == "NAR前走参考順位（研究）"
    assert "前走4角 2番手" in detail.select_one(".detail-nar-form").text
    assert "回収率改善は未検証" in detail.select_one(".detail-nar-form").text


def test_jra_is_not_affected_by_nar_reference_projection():
    view = [dict(mode="jra", no="1", name="中央馬", ability_rank="1")]
    projected = with_nar_form_reference(view, [_source(1, 80, 2)], {"date": "2026-11-04"})
    assert projected == view and projected is not view
    assert "nar_form_rank" not in [c["key"] for c in columns(projected)]
    assert not BeautifulSoup(lineup_html(projected), "html.parser").select(".col-nar_form_rank")


def test_unnamed_or_missing_ability_is_not_filled_with_invented_numbers():
    view = [dict(mode="nar", no="1", name="不明馬", ability_rank=None)]
    projected = with_nar_form_reference(view, [{}], {"date": "2026-11-04"})
    assert projected[0]["nar_form_ref_rank"] is None
    assert records(projected)["1"]["nar_form_rank"] is None
