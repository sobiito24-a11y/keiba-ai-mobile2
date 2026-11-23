"""New C/D second look: dated evidence, no score effect, safe source notes."""
from copy import deepcopy

from bs4 import BeautifulSoup
import pytest

from core.independent_ai_sabcd import MODEL_ID, annotate_view
from core.race_explorer_cards import detail_html, pickup_html
from core.race_explorer_second_look import (
    input_quality_html, previous_top3_evidence, second_look_html,
)


def horse(grade="C", previous="3着", *, mode="jra"):
    return {
        "no": "7", "name": "保存馬", "mode": mode,
        "mark": "—", "rank": 7, "candidate_formal_score": 10.5,
        "race_context": {
            "race_date": "2026-11-22",
            "class_label": "C級",
            "race_data2": "3歳以上 2勝クラス 14頭",
        },
        "unified_sabcd": {"grade": grade, "rank": 9, "status": "independent_ai_prestart_shadow"},
        "independent_ai_sabcd": {"grade": grade, "source_model_id": MODEL_ID, "score": .19},
        "independent_ai_input_quality": {
            "verified": True, "corner4": None,
            "missing": ("corner4", "recent3_mean"),
        },
        "profile": {
            "class_shift": "判定不可（クラス体系の照合不足）",
            "runs": [{"date": "2026-11-10", "venue": "東京"}],
            "extended_history": [],
        },
        "explorer_facts": {
            "metrics": {},
            "runs": [
                {"label": "3走前", "date": "2026-09-11", "finish": "9着"},
                {"label": "2走前", "date": "2026-10-01", "finish": "7着"},
                {"label": "前走", "date": "2026-11-10", "finish": previous,
                 "venue": "東京", "class_raw": "2勝クラス"},
            ],
        },
    }


@pytest.mark.parametrize("grade", ["C", "D"])
@pytest.mark.parametrize("finish", ["1", "2着", "３着"])
def test_cd_previous_top3_only_in_detail_with_exact_source(grade, finish):
    h = horse(grade, finish)
    original = deepcopy(h)
    item = previous_top3_evidence(h)
    assert item["finish"] in (1, 2, 3)
    assert item["date"] == "2026-11-10"
    content = BeautifulSoup(detail_html(h), "html.parser")
    section = content.select_one('[data-second-look="previous-top3"]')
    assert section is not None
    assert "2026-11-10" in section.text
    assert "2勝クラス" in section.text
    assert "変更しません" in section.text
    assert '[data-second-look="previous-top3"]' not in pickup_html([h])
    assert h == original


@pytest.mark.parametrize("case", ["A", "4th", "missing", "future", "invalid",
                                  "unverified", "mismatched", "undated"])
def test_second_look_abstains_on_weak_or_nonprestart_evidence(case):
    h = horse()
    if case == "A":
        h["independent_ai_sabcd"]["grade"] = "A"
        h["unified_sabcd"]["grade"] = "A"
    elif case == "4th":
        h["explorer_facts"]["runs"][-1]["finish"] = "4着"
    elif case == "missing":
        h["explorer_facts"]["runs"][-1]["finish"] = "未取得"
    elif case == "future":
        h["explorer_facts"]["runs"][-1]["date"] = "2026-11-23"
    elif case == "invalid":
        h["explorer_facts"]["runs"][-1]["finish"] = "失格"
    elif case == "unverified":
        h["independent_ai_sabcd"]["source_model_id"] = "newer_model"
    elif case == "mismatched":
        h["unified_sabcd"]["grade"] = "B"
    elif case == "undated":
        h["race_context"]["race_date"] = ""
    assert previous_top3_evidence(h) is None
    assert second_look_html(h) == ""


def test_quality_explicitly_discloses_4corner_and_class_input_gaps():
    h = horse()
    doc = BeautifulSoup(input_quality_html(h), "html.parser")
    quality = doc.select_one(".detail-input-quality")
    assert quality
    assert "旧クラスラベル" in quality.text and "2勝クラス" in quality.text
    assert "4角予測入力は未取得" in quality.text
    assert "近3走平均" in quality.text
    assert "海外出走の有無を断定できません" in quality.text
    assert "SABCD" in quality.text and "変更しません" in quality.text


def test_foreign_only_reported_when_explicit_foreign_venue_is_recorded():
    h = horse()
    assert "海外開催" not in input_quality_html(h)
    h["profile"]["extended_history"] = [{"venue": "香港", "date": "2026-06-06"}]
    assert "海外開催「香港」あり" in input_quality_html(h)
    h["mode"] = "nar"
    assert "このNAR表示" in input_quality_html(h)


def test_escape_previous_run_name_and_foreign_venue_as_untrusted_text():
    h = horse(mode="jra")
    h["explorer_facts"]["runs"][-1]["venue"] = '<img src=x onerror=alert(1)>'
    h["explorer_facts"]["runs"][-1]["class_raw"] = '<script>alert("x")</script>'
    h["profile"]["extended_history"] = [{"venue": '香港"><svg onload=alert(1)>'}]
    doc = BeautifulSoup(second_look_html(h) + input_quality_html(h), "html.parser")
    assert not doc.select("script,img,svg,[onerror],[onload]")
    assert "<script>" in doc.get_text()
    assert "<img" in doc.get_text()


def test_prestart_packet_quality_is_read_only_and_missing_values_do_not_up_rank():
    view = [dict(no=str(i), name=f"馬{i}", mode="nar",
                 unified_sabcd={"grade": "D", "rank": i},
                 rank=i, mark="—") for i in range(1, 4)]
    horses = [{"horse_no": i, "name": f"馬{i}", "place": p}
              for i, p in ((1, .19), (2, .11), (3, .04))]
    rows = [{"horse_no": i, "name": f"馬{i}", "pure": 71,
             "distance_index": 75, "course_index": 76,
             "recent3_mean": None if i == 1 else 77,
             "corner4": None if i == 1 else i,
             "jockey_place_rate": 30, "jockey_sample_size": 25,
             "rest_days": 14, "load_change": 0} for i in range(1, 4)]
    source = {
        "status": "reference", "origin": "new_prediction", "model_id": MODEL_ID,
        "mode": "nar", "race_id": "race-one",
        "generated_at": "2026-11-22T08:00:00+09:00",
        "input": {"race_id": "race-one",
                  "post_time": "2026-11-22T10:00:00+09:00",
                  "horses": rows},
        "horses": horses,
    }
    old = deepcopy(source)
    annotate_view(view, source, race_id="race-one")
    assert view[0]["independent_ai_sabcd"]["grade"] == "C"
    assert view[0]["independent_ai_input_quality"] == {
        "verified": True, "corner4": None,
        "missing": ("recent3_mean", "corner4"),
    }
    assert view[1]["independent_ai_input_quality"]["corner4"] == 2
    assert view[1]["independent_ai_input_quality"]["missing"] == ()
    assert source == old
    assert all(h["mark"] == "—" and h["rank"] == i
               for i, h in enumerate(view, 1))
    annotate_view(view, source, race_id="race-one")
    assert view[0]["independent_ai_input_quality"]["missing"] == (
        "recent3_mean", "corner4")


def test_incomplete_prestart_packet_does_not_invent_quality_or_review():
    h = horse()
    h["independent_ai_input_quality"] = {"verified": False}
    assert "確認できません" in input_quality_html(h)
    h.pop("independent_ai_sabcd")
    assert input_quality_html(h) == ""
    assert second_look_html(h) == ""
