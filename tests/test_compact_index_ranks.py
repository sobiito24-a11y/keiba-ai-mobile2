"""The compact table/detail share saved values and independent index ranks."""
from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pytest

from core.final_candidate_selection import formal_score, select_indices
from core.race_explorer_cards import detail_html, pickup_html
from core.race_explorer_columns import columns, records
from core.race_explorer_common import comparison_index_html
from core.race_explorer_ui import lineup_html


def horse(no="1", mode="jra"):
    """Contradictory raw fields make accidental independent fallbacks visible."""
    return dict(
        no=str(no), name="保存済みの比較馬", frame=3, mode=mode, age="牝4",
        jockey="今回騎手", formal_member=True, mark="△", rank="4",
        candidate_formal_score=12.8123456789, internal_score=9999, score="9999",
        ability=9999, ability_rank=1,
        distance=dict(value=9999, rank=1), course=dict(value=9999, rank=1),
        star=dict(value=94, rank=1), away=dict(value=79, rank=8),
        average=dict(value=9999, rank=1), corner=1, style="逃",
        model_b=dict(score=9999, rank=1, version="frozen-saved-model"),
        explorer_facts=dict(
            metrics=dict(
                ability=dict(value=16.1, rank=3), distance=dict(value=58, rank=2),
                course=dict(value=56, rank=7), average=11.7, maximum=120,
                corner=11, style="差"),
            current_jockey="今回騎手", previous_jockey="前走騎手",
            jockey_change="前走騎手 → 今回騎手", rest_label="中2週",
            current_weight=55, weight_label="55kg", weight_delta=0,
            weight_delta_label="±0kg", training="A", features=[],
            stable_comment_raw="保存された厩舎原文\n末尾も残す。",
            runs=[dict(label=label, time_index=index, finish=finish,
                       condition="東京・ダ1600m・左", date=date,
                       class_raw="保存クラス", is_maximum=False)
                  for label, index, finish, date in (
                      ("3走前", 8, 11, "2026-07-01"),
                      ("2走前", 15, 1, "2026-08-01"),
                      ("前走", 12, 9, "2026-09-01"))]),
    )


def dom(html):
    return BeautifulSoup(html, "html.parser")


def shown_pair(node):
    pair = node.select_one(".comparison-metric")
    assert pair is not None
    value = pair["data-value"]
    rank = pair["data-rank"]
    return (float(value) if value else None, int(rank) if rank else None)


@pytest.mark.parametrize("saved_rank,expected", [
    (1, "◎1位"), (2, "○2位"), (3, "▲3位"),
    (4, "4位"), (5, "5位"), (10, "10位"), ("3", "▲3位"),
    (None, "―"), (0, "―"), (-1, "―"), (1.5, "―"),
    (True, "―"), ("未取得", "―"), (float("nan"), "―"),
])
def test_rank_glyphs_are_only_for_the_existing_top_three(saved_rank, expected):
    metric = dom(comparison_index_html(16.1, saved_rank))
    assert metric.select_one(".metric-value").text == "16.1"
    assert metric.select_one(".metric-rank").text == expected
    assert not metric.select(".mark,.focus-badge")
    assert "正式印とは別" in metric.select_one(".metric-rank")["title"]


@pytest.mark.parametrize("missing", [
    None, "未取得", "NaN", "Infinity", float("inf"), -float("inf"), True,
])
def test_missing_values_do_not_gain_a_rank_or_invented_zero(missing):
    metric = dom(comparison_index_html(missing, 1))
    assert metric.select_one(".metric-value").text == "未取得"
    assert metric.select_one(".metric-rank").text == "―"
    assert shown_pair(metric) == (None, None)


@pytest.mark.parametrize("index", [0, -33.6, 16.1])
def test_unranked_observations_never_gain_glyphs_even_if_a_rank_is_supplied(index):
    metric = dom(comparison_index_html(index, 1, ranked=False))
    assert shown_pair(metric) == (index, None)
    assert metric.select_one(".metric-rank") is None
    assert not any(mark in metric.text for mark in "◎○▲")


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_every_compact_metric_uses_exactly_the_same_saved_cells_in_table_and_detail(mode):
    h = horse(mode=mode)
    original = deepcopy(h)
    cells = records([h])["1"]
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    rank_keys = dict(score="rank", ability="ability_rank", distance="distance_rank",
                     course="course_rank", star="star_rank", away="away_rank")
    for key in (*rank_keys, "average", "maximum"):
        table_cell = table.select_one("td.col-" + key)
        detail_cell = detail.select_one('.detail-stat[data-metric="' + key + '"]')
        assert table_cell is not None and detail_cell is not None
        expected = (cells[key], cells[rank_keys[key]] if key in rank_keys else None)
        assert shown_pair(table_cell) == shown_pair(detail_cell) == expected
        assert table_cell.select_one(".comparison-metric").decode() == detail_cell.select_one(".comparison-metric").decode()
    assert table.select_one("td.col-course .metric-rank").text == "7位"
    assert table.select_one("td.col-ability .metric-rank").text == "▲3位"
    assert table.select_one("td.col-distance .metric-rank").text == "○2位"
    assert table.select_one("td.col-score .metric-rank").text == "4位"
    assert "9999" not in table.text and "9999" not in detail.text
    assert detail.select_one(".detail-comment-original").text == h["explorer_facts"]["stable_comment_raw"]
    assert [run.h5.text for run in detail.select(".detail-run")] == ["3走前", "2走前", "前走"]
    assert h == original


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_existing_ties_and_distinct_metric_populations_are_not_reranked(mode):
    horses = [horse(str(no), mode) for no in range(1, 6)]
    for h, index, rank in zip(horses, (92, 85, 85, 83, None), (1, 2, 2, 4, None)):
        h["explorer_facts"]["metrics"]["distance"] = dict(value=index, rank=rank)
        h["candidate_formal_score"] = 10  # Equal scores must retain distinct saved ranks.
        h["rank"] = int(h["no"])
    original = deepcopy(horses)
    table = dom(lineup_html(horses))
    assert [row.select_one(".col-distance .metric-rank").text
            for row in table.select("tbody tr[data-horse]")] == ["◎1位", "○2位", "○2位", "4位", "―"]
    assert [row.select_one(".col-score .metric-rank").text
            for row in table.select("tbody tr[data-horse]")] == ["◎1位", "○2位", "▲3位", "4位", "5位"]
    assert [shown_pair(row.select_one(".col-distance"))[1]
            for row in table.select("tbody tr[data-horse]")] == [1, 2, 2, 4, None]
    # The same numerical index may have different ranks in different saved groups.
    horses[0]["explorer_facts"]["metrics"]["distance"] = dict(value=79, rank=9)
    table, detail = dom(lineup_html(horses)), dom(detail_html(horses[0]))
    for key, expected in (("distance", (79, 9)), ("away", (79, 8))):
        assert shown_pair(table.select_one("tbody tr .col-" + key)) == expected
        assert shown_pair(detail.select_one('[data-metric="' + key + '"]')) == expected
    horses[0]["explorer_facts"]["metrics"]["distance"] = deepcopy(original[0]["explorer_facts"]["metrics"]["distance"])
    assert horses == original


@pytest.mark.parametrize("key,short", [("ability", "純能力"), ("distance", "距離"), ("course", "コース")])
@pytest.mark.parametrize("missing", [{}, None, dict(value=None, rank=1)])
def test_explicit_missing_metric_cannot_revive_conflicting_raw_fallback(key, short, missing):
    h = horse()
    h["explorer_facts"]["metrics"][key] = deepcopy(missing)
    original = deepcopy(h)
    cells = records([h])["1"]
    assert cells[key] is None and cells[key + "_rank"] is None
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    assert shown_pair(table.select_one("td.col-" + key)) == (None, None)
    assert detail.select_one('.detail-stat[data-metric="' + key + '"]') is None
    assert short in detail.select_one(".detail-missing-metrics").text
    assert h == original


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_zero_negative_missing_rank_average_and_corner_keep_their_own_meaning(mode):
    h = horse(mode=mode)
    h["explorer_facts"]["metrics"].update(
        ability=dict(value=-33.6, rank=4), distance=dict(value=0, rank=None),
        course=dict(value=-36, rank=3), average=0, maximum=-1)
    original = deepcopy(h)
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    assert shown_pair(table.select_one("td.col-ability")) == (-33.6, 4)
    assert shown_pair(table.select_one("td.col-distance")) == (0, None)
    assert table.select_one("td.col-distance .metric-rank").text == "―"
    assert shown_pair(table.select_one("td.col-course")) == (-36, 3)
    for key, expected in (("average", 0), ("maximum", -1)):
        for cell in (table.select_one("td.col-" + key), detail.select_one('[data-metric="' + key + '"]')):
            assert shown_pair(cell) == (expected, None)
            assert cell.select_one(".metric-rank") is None
    assert table.select_one("td.col-corner").text == "11番手"
    corner = detail.select_one('[data-metric="corner"]')
    assert corner.b.text == "11番手" and corner.select_one(".metric-rank") is None
    assert not any(mark in corner.text for mark in "◎○▲")
    assert h == original


def test_condition_index_rank_is_not_assigned_to_the_different_saved_maximum():
    h = horse()
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    assert shown_pair(table.select_one("td.col-star")) == (94, 1)
    assert shown_pair(table.select_one("td.col-maximum")) == (120, None)
    assert shown_pair(detail.select_one('[data-metric="star"]')) == (94, 1)
    maximum = detail.select_one('[data-metric="maximum"]')
    assert shown_pair(maximum) == (120, None)
    assert maximum.select_one(".metric-rank") is None


def test_rank_controls_remain_available_without_duplicate_table_columns():
    h = horse()
    original = deepcopy(h)
    schema, table = columns([h]), dom(lineup_html([h]))
    shown = [spec["key"] for spec in schema if not spec.get("table_hidden")]
    hidden = [spec for spec in schema if spec.get("table_hidden")]
    assert {spec["key"] for spec in hidden} == {"age", "rank", "ability_rank", "distance_rank", "course_rank", "star_rank", "away_rank"}
    assert all(spec["type"] == "rank" for spec in hidden if spec["key"] != "age")
    assert next(spec for spec in hidden if spec["key"] == "age")["type"] == "text"
    assert [th["data-column"] for th in table.select("th[data-column]")] == shown
    assert {option["value"] for option in table.select("#lineup-sort option")} == {spec["key"] for spec in schema}
    assert {option["value"] for option in table.select("#filter-column option")} == {spec["key"] for spec in schema}
    for spec in hidden:
        assert table.select_one("td.col-" + spec["key"]) is None
    assert h == original


def test_optional_existing_condition_indices_are_added_only_when_values_exist():
    h = horse()
    h.update(star=dict(value=None, rank=1), away=dict(value="NaN", rank=1))
    assert not {spec["key"] for spec in columns([h])}.intersection(("star", "star_rank", "away", "away_rank"))
    h["star"] = dict(value=0, rank=2)
    keys = {spec["key"] for spec in columns([h])}
    assert {"star", "star_rank"} <= keys and "away" not in keys
    assert shown_pair(dom(lineup_html([h])).select_one("td.col-star")) == (0, 2)


def test_nar_reference_score_and_outside_rank_never_become_formal_evaluation():
    h = horse("3", "nar")
    h.update(formal_member=False, mark="✓", rank="6", candidate_formal_score=None,
             internal_score=-1.119345315, score="98.8",
             reference_score=dict(kind="reference", value=-1.119345315,
                                  reason="既存の固定式による参考値"))
    h["explorer_facts"]["metrics"]["ability"] = dict(value=-38.7, rank=6)
    h["star"] = dict(value=-56, rank=3)
    original = deepcopy(h)
    cells = records([h])["3"]
    assert cells["score"] is None and cells["rank"] is None
    assert cells["reference_score"] == -1.119345315
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    assert shown_pair(table.select_one("td.col-score")) == (None, None)
    assert table.select_one("td.col-score .metric-rank").text == "―"
    assert detail.select_one('[data-metric="score"]') is None
    for cell in (table.select_one("td.col-reference_score"), detail.select_one('[data-metric="reference_score"]')):
        assert shown_pair(cell) == (-1.119345315, None)
        assert cell.select_one(".metric-rank") is None
        assert not any(mark in cell.text for mark in "◎○▲")
    assert "正式評価外" in table.select_one("th.col-reference_score").text
    assert "正式評価外" in detail.select_one('[data-metric="reference_score"]').text
    assert shown_pair(table.select_one("td.col-star")) == (-56, 3)
    assert h == original and h["rank"] == "6" and h["mark"] == "✓"


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_all_rendering_preserves_formal_top_five_marks_reference_and_saved_payload(mode):
    view = [horse(str(no), mode) for no in range(1, 9)]
    for no, h in enumerate(view, 1):
        h.update(formal_member=no <= 5, rank=str(no),
                 candidate_formal_score=100 - no if mode == "jra" or no <= 5 else None,
                 mark={1: "◎", 2: "○", 3: "▲", 4: "✔", 5: "△", 6: "✓"}.get(no, "—"))
        if mode == "nar" and no > 5:
            h["reference_score"] = dict(kind="reference", value=9999 - no)
    event = dict(races=[dict(horses=view)], format="existing-synthetic-save")
    original = deepcopy(event)
    saved = json.dumps(event, ensure_ascii=False, sort_keys=True)
    membership = [view[i]["no"] for i in select_indices(view)]
    formal = {h["no"]: (formal_score(h), h["rank"], h["mark"]) for h in view}
    assert membership == ["1", "2", "3", "4", "5", "6"]
    for ordered in (view, list(reversed(view))):
        records(ordered)
        table, pickup = dom(lineup_html(ordered)), dom(pickup_html(ordered))
        assert len(table.select("tr[data-horse]")) == 8
        assert [card["data-horse-open"] for card in pickup.select(".pickup-card")] == membership
        assert not table.select(".mark,.focus-badge")
        assert not any(mark in pickup.text for mark in "◎○▲✔△✓")
        for h in ordered:
            detail_html(h)
    assert event == original
    assert json.dumps(event, ensure_ascii=False, sort_keys=True) == saved
    assert [view[i]["no"] for i in select_indices(view)] == membership
    assert {h["no"]: (formal_score(h), h["rank"], h["mark"]) for h in view} == formal


def test_compact_table_and_detail_keep_names_and_original_comments_escaped():
    h = horse('1" onclick="bad()')
    h["name"] = '</script><img src=x onerror="bad()">長い馬名'
    h["explorer_facts"]["stable_comment_raw"] = '<script>bad()</script>\n原文の末尾'
    original = deepcopy(h)
    table, detail = dom(lineup_html([h])), dom(detail_html(h))
    assert not table.select("script,img,[onclick],[onerror]")
    assert not detail.select("script,img,[onclick],[onerror]")
    assert table.select_one("td.col-name [data-horse-open]")["data-horse-open"] == h["no"]
    assert table.select_one("td.col-name strong").text == h["name"]
    assert table.select_one("td.col-name .horse-age").text == h["age"]
    assert detail.select_one(".detail-comment-original").text == h["explorer_facts"]["stable_comment_raw"]
    assert not dom(comparison_index_html('<img src=x onerror="bad()">', 1)).select("img,[onerror]")
    assert h == original
