from copy import deepcopy

from bs4 import BeautifulSoup
import pytest

from core.final_candidate_selection import select_indices
from core.race_explorer_cards import detail_html, pickup_html


def horse(no=1, mode="jra"):
    metrics = dict(
        ability=dict(value=-2.5, rank=4), distance=dict(value=0, rank=2),
        course=dict(value=31.2, rank=1), average=12.5, maximum=16,
        style="先行", corner=3, plus="○ 同距離実績", caution="△ 斤量増",
    )
    return dict(
        no=str(no), name=f"比較馬{no}", age="牝4", jockey="今回騎手", frame=8,
        mode=mode, mark={1: "◎", 2: "○", 3: "▲", 4: "✔", 5: "△", 6: "✓"}.get(no, "—"),
        rank=no, candidate_formal_score=45.25, formal_member=no <= 5,
        final_metrics=metrics,
        explorer_facts=dict(
            metrics=deepcopy(metrics), current_jockey="今回騎手", previous_jockey="前走騎手",
            jockey_status="changed", jockey_change="乗替：前走騎手 → 今回騎手",
            weight_label="55kg", weight_delta_label="+1kg", rest_label="中2週", training="A",
            features=["東京ダ1600m：2戦1回3着以内", "距離変更", "調教A" if mode == "jra" else "長期休養明け", "省略する4件目"],
            changes=["距離変更 1400m → 1600m"],
            runs=[dict(label=label, date=date, time_index=index, finish=finish,
                       condition="東京・ダ1600m・左", class_raw="2勝クラス", is_maximum=index == 16)
                  for label, date, index, finish in (
                      ("3走前", "2026-07-01", 16, "8"),
                      ("2走前", "2026-08-01", 10, "1"),
                      ("前走", "2026-09-01", 11.5, "3"))],
            condition_records=[dict(key="venue_distance", label="東京ダ1600m", starts=2,
                                    top3=1, unknown=0, scope="開催日前の保存過去3走（近3走の範囲）",
                                    text="東京ダ1600m：2戦1回3着以内（近3走の範囲）")],
            stable_comment_raw="前走は外を回った。\n今回は内枠を生かしたい。 <原文>",
            stable_comment_source="新聞HTML", interpretation="AIによる比較用の考察。",
            plus="○ 同距離実績", caution="△ 斤量増",
        ),
    )


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_pickup_keeps_exact_existing_membership_deduplication_and_number_order(mode):
    horses = [horse(no, mode) for no in (8, 6, 3, 7, 1, 5, 4, 2)]
    horses.insert(0, deepcopy(horses[-1]))
    before = deepcopy(horses)
    doc = BeautifulSoup(pickup_html(horses), "html.parser")
    expected = [horses[index]["no"] for index in select_indices(horses, "no")]
    assert [card["data-horse-open"] for card in doc.select(".pickup-card")] == expected
    assert expected == ["1", "2", "3", "4", "5", "6"]
    assert len(doc.select(".pickup-card")) == 6
    assert horses == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_pickup_has_no_marks_order_or_formal_scores_and_shares_detail_target(mode):
    horses = [horse(no, mode) for no in range(1, 9)]
    doc = BeautifulSoup(pickup_html(horses), "html.parser")
    text = doc.get_text(" ")
    assert not any(mark in text for mark in "◎○▲✔✓△")
    assert "45.25" not in text and "正式" not in text and "番手候補" not in text
    for card in doc.select(".pickup-card"):
        assert card["aria-controls"] == "horse-detail-" + card["data-horse-open"]
        assert card["type"] == "button" and card["aria-expanded"] == "false"
        assert len(card.select(".pickup-features > span")) == 3
        assert card.select_one(".pickup-ability b").text == "-2.5"
        assert "中2週" in card.text and "+1kg" in card.text and "55kg" in card.text
        assert "前走騎手 → 今回騎手" in card.text
    assert ("調教" in text) == (mode == "jra")


def test_no_reference_does_not_fill_a_sixth_card():
    horses = [horse(no) for no in range(1, 9)]
    horses[5]["mark"] = "—"
    assert len(BeautifulSoup(pickup_html(horses), "html.parser").select(".pickup-card")) == 5
    assert "保存されたレースピックアップはありません" in pickup_html([])


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_detail_keeps_oldest_first_distinguishes_finish_and_index_and_preserves_original(mode):
    h = horse(mode=mode)
    h["explorer_facts"]["runs"].reverse()
    before = deepcopy(h)
    doc = BeautifulSoup(detail_html(h), "html.parser")
    runs = doc.select(".detail-run")
    assert [run.h5.text for run in runs] == ["3走前", "2走前", "前走"]
    result = runs[0].select(".detail-run-result > span")
    assert result[0].small.text == "着順" and result[0].b.text == "8"
    assert result[1].small.text == "タイム指数" and result[1].b.text.strip() == "16 ★"
    assert len(doc.select(".maximum-match")) == 1
    assert "2勝クラス" in runs[0].text and "東京・ダ1600m・左" in runs[0].text
    assert doc.select_one(".detail-comment-original").text == h["explorer_facts"]["stable_comment_raw"]
    assert "AIによる比較用" not in doc.select_one(".detail-source-comment").text
    assert "AIによる比較用" in doc.select_one(".detail-interpretation").text
    assert "2戦1回3着以内" in doc.select_one(".detail-conditions").text
    assert "近3走の範囲" in doc.select_one(".detail-conditions").text
    assert "45.25" in doc.select_one(".detail-evaluation").text
    for rank in doc.select('.metric-rank'):
        rank.extract()  # The new index-rank glyphs are not formal AI marks.
    assert not any(mark in doc.get_text() for mark in "◎○▲✔✓△")
    assert h == before


def test_html_escaping_covers_pickup_attributes_detail_text_and_full_source_comment():
    h = horse()
    h["no"] = '1" onclick="evil()'
    h["name"] = '<script>alert("name")</script>'
    facts = h["explorer_facts"]
    facts["current_jockey"] = '<img src=x onerror="evil()">'
    facts["features"] = ['<svg onload="evil()">']
    facts["stable_comment_raw"] = '原文\n<script>alert("source")</script> &末尾'
    facts["interpretation"] = '<iframe src="evil">'
    facts["runs"][0]["class_raw"] = '<a href="evil">クラス</a>'
    doc = BeautifulSoup(pickup_html([h]) + detail_html(h), "html.parser")
    assert not doc.select("script,img,svg,iframe,a,[onclick],[onerror],[onload]")
    assert doc.select_one(".pickup-card")["data-horse-open"] == h["no"]
    assert doc.select_one(".detail-comment-original").text == facts["stable_comment_raw"]


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_missing_facts_remain_missing_and_never_create_features_or_condition_claims(mode):
    h = dict(no="1", name="未取得馬", mode=mode, formal_member=True, rank=1,
             frame=None, candidate_formal_score=None)
    before = deepcopy(h)
    pickup = BeautifulSoup(pickup_html([h]), "html.parser")
    detail = BeautifulSoup(detail_html(h), "html.parser")
    assert not pickup.select(".pickup-features")
    assert len(detail.select(".detail-run")) == 3
    assert detail.select_one(".detail-comment-original").text == "未取得"
    assert "条件別実績は未取得" in detail.text
    assert "初ダート" not in detail.text and "初ブリンカー" not in detail.text
    assert all("未取得" in run.text for run in detail.select(".detail-run"))
    assert h == before


@pytest.mark.parametrize("missing_value", [None, float("nan"), float("inf"), "未取得"])
def test_missing_detail_indices_are_compact_without_hiding_zero_or_negative_values(missing_value):
    h = horse()
    metrics = h["explorer_facts"]["metrics"]
    metrics["distance"] = dict(value=missing_value, rank=1)
    metrics["course"] = dict(value=missing_value, rank=1)
    metrics["maximum"] = missing_value
    metrics["average"] = 0
    before = deepcopy(h)
    doc = BeautifulSoup(detail_html(h), "html.parser")
    assert doc.select_one(".detail-missing-metrics").text == "未取得：距離・コース・★最高"
    stats = doc.select(".detail-stat")
    assert not any("未取得" in stat.text for stat in stats)
    by_label = {stat.small.text: stat for stat in stats}
    assert set(by_label) == {"JRA正式評価スコア", "純能力指数", "3走平均指数", "4角想定"}
    assert by_label["3走平均指数"].b.text == "0"
    assert by_label["純能力指数"].b.text == "-2.5"
    assert h == before


def test_fully_missing_detail_has_one_small_summary_and_keeps_formal_rank_out_of_stats():
    h = dict(no="1", name="未取得馬", mode="nar", formal_member=True, rank=1,
             candidate_formal_score=None)
    doc = BeautifulSoup(detail_html(h), "html.parser")
    assert not doc.select(".detail-stat")
    missing = doc.select(".detail-missing-metrics")
    assert len(missing) == 1
    assert missing[0].text == "未取得：正式評価・純能力・距離・コース・3走平均・★最高・4角想定"
