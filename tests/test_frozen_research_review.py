"""Frozen Nov 8 pre-race checks must not change any prediction or purchase."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.frozen_research_review import (
    FROZEN_VERSION, with_frozen_reviews, jra_research_pair_three,
)
from core.race_explorer_cards import detail_html
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html
from core.race_explorer_visuals import _pace, development_html


def horse(mode="jra", no="3", rank=3, course=2, distance=6, grade="B", rest=21):
    return {
        "no": no, "name": f"仮馬{no}", "mode": mode, "ability_rank": str(rank),
        "corner": 2, "training": grade,
        "explorer_facts": {
            "training": grade, "rest_days": rest, "rest_status": "verified" if rest is not None else "unknown",
            "metrics": {
                "ability": {"rank": rank, "value": 55 - rank},
                "distance": {"rank": distance, "value": 44},
                "course": {"rank": course, "value": 40},
                "corner": 2,
            },
        },
    }


def test_nar_prev_corner_is_actual_and_ranks_are_never_replaced():
    a = horse(mode="nar", no="8", rank=8)
    a.update(nar_form_ref_prior_corner=2, nar_form_ref_rank=7, nar_form_ref_pace="未取得")
    b = horse(mode="nar", no="9", rank=9)
    b.update(nar_form_ref_prior_corner=None)
    base = deepcopy([a, b])
    reviewed = with_frozen_reviews([a, b])
    assert reviewed[0]["frozen_review_candidate"] is True
    assert reviewed[0]["frozen_review_label"] == "前走×4角再確認"
    assert reviewed[1]["frozen_review_candidate"] is False
    assert reviewed[1]["frozen_review_label"] == "前走4角未取得"
    assert reviewed[0]["nar_form_ref_rank"] == 7 and reviewed[0]["ability_rank"] == "8"
    assert [a, b] == base and reviewed[0] is not a
    assert all(item["frozen_review_version"] == FROZEN_VERSION for item in reviewed)
    # Research columns must be present on the *real* normal table.
    cols = columns(reviewed)
    assert next(c for c in cols if c["key"] == "frozen_review")["label"] == "NAR見直し"
    assert "frozen_review_reason" in [c["key"] for c in cols]
    table = BeautifulSoup(lineup_html(reviewed), "html.parser")
    assert table.select_one("th.col-frozen_review")
    assert table.select_one('#lineup-sort option[value="frozen_review"]')
    assert "前走×4角再確認" in table.text
    assert "回収率改善は未検証" in table.text
    detail = BeautifulSoup(detail_html(reviewed[0]), "html.parser")
    assert "購入推奨には反映しません" in detail.select_one(".detail-frozen-review").text


def test_past_finish_does_not_stand_in_for_missing_nar_corner():
    a = horse(mode="nar", no="6", rank=6)
    a["position"] = 1  # a last-race finish is NOT a corner
    a["nar_form_ref_prior_corner"] = None
    assert with_frozen_reviews([a])[0]["frozen_review_label"] == "前走4角未取得"


def test_jra_evidence_rest_training_and_surface_or_distance():
    a = horse(no="3", rank=3, grade="B", rest=21, course=2)
    b = horse(no="4", rank=4, grade="D", rest=90)
    c = horse(no="2", rank=2, grade="B", rest=None)
    d = horse(no="5", rank=5, grade="B", rest=21, course=9, distance=9)
    reviewed = with_frozen_reviews([a, b, c, d])
    assert reviewed[0]["frozen_review_candidate"] is True
    assert reviewed[0]["frozen_review_label"] == "相手比較材料"
    assert reviewed[1]["frozen_review_candidate"] is False
    assert reviewed[1]["frozen_review_label"] == "長休＋調教注意"
    assert reviewed[2]["frozen_review_candidate"] is False
    assert "休養間隔が未確認" in reviewed[2]["frozen_review_reason"]
    assert reviewed[3]["frozen_review_candidate"] is False
    assert next(s for s in columns(reviewed) if s["key"] == "frozen_review")["label"] == "JRA相手比較"
    assert "相手比較材料" in BeautifulSoup(lineup_html(reviewed), "html.parser").text


def test_jra_pair_hypothesis_uses_ability_anchor_and_never_fabricates():
    view = [
        horse(no="1", rank=1, grade="C"),
        horse(no="2", rank=2, grade="D", course=2),
        horse(no="3", rank=3, grade="B", course=2),
        horse(no="4", rank=4, grade="A", distance=1),
        horse(no="5", rank=5, grade="D"),
    ]
    old = deepcopy(view)
    assert jra_research_pair_three(view) == ["1", "3", "4"]
    assert view == old
    view[0]["ability_rank"] = None
    view[0]["explorer_facts"]["metrics"]["ability"] = {}
    assert jra_research_pair_three(view) == []
    assert jra_research_pair_three([]) == []


def test_jra_missing_ability_keeps_unknown_and_never_chooses_new_rank():
    a = horse(no="1", rank=1)
    a["ability_rank"] = None
    a["explorer_facts"]["metrics"]["ability"] = {}
    out = with_frozen_reviews([a])
    assert out[0]["frozen_review_label"] == "能力未取得"
    assert not out[0]["frozen_review_candidate"]
    assert records(out)["1"]["ability_rank"] is None


def test_spurious_nar_h_does_not_display_as_measured_pace():
    nar = horse(mode="nar", no="1", rank=1)
    nar["nar_form_ref_pace"] = "未取得"
    nar["pace"] = "H"
    assert _pace([nar], {"pace": "H"}) == ""
    assert "未取得・不一致" in development_html([nar], {"pace": "H"})
    # Real JRA pace still renders; NAR valid pace also still renders.
    jra = horse(mode="jra", no="1", rank=1)
    jra["pace"] = "M"
    assert _pace([jra], {"pace": "M"}) == "M"
    nar["nar_form_ref_pace"] = "H"
    assert _pace([nar], {"pace": "H"}) == "H"
