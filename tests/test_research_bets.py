from __future__ import annotations

from core.research_bets import build_research_bet


def row(no: int, rank: int, mark: str, odds: float | str | None = None, current_rank: int | None = None) -> dict:
    data = {
        "馬番": no,
        "馬名": f"Horse{no}",
        "market_ability_rank": rank,
        "market_ability_score": 100 - (rank * 3),
        "ai_current_mark": mark,
        "current_evaluation_rank": current_rank or rank,
    }
    if odds is not None:
        data["odds_at_prediction"] = odds
    return data


def marked_rows(axis_odds: float | None = None) -> list[dict]:
    return [
        row(1, 1, "◎", axis_odds),
        row(2, 2, "○", 4.1),
        row(3, 3, "▲", 8.0),
        row(4, 4, "△", 12.0),
        row(5, 5, "☆", 20.0),
    ]


def test_jra_mobile_research_bet_odds_boundaries():
    assert build_research_bet(marked_rows(4.9), "jra", context="mobile")["total"] == 500
    assert build_research_bet(marked_rows(5.0), "jra", context="mobile")["total"] == 1000
    assert build_research_bet(marked_rows(9.9), "jra", context="mobile")["total"] == 1000
    assert build_research_bet(marked_rows(10.0), "jra", context="mobile")["total"] == 500
    assert build_research_bet(marked_rows(None), "jra", context="mobile")["total"] == 500


def test_jra_dashboard_guide_does_not_use_saved_odds_for_total():
    guide = build_research_bet(marked_rows(6.4), "jra", context="dashboard")
    assert guide["research_rule_id"] == "JRA_DASH_GUIDE_V1"
    assert guide["total"] == 500
    assert guide["trio_condition"] == "3連複は参考候補"
    assert any("3連複研究候補" in line for line in guide["lines"])


def test_nar_research_bet_uses_ability_rank_quinella_when_axis_odds_low():
    research = build_research_bet(marked_rows(2.4), "nar", context="mobile")
    assert research["research_rule_id"] == "NAR_VER4_AXIS_ML_2_4_V1"
    assert research["research_status"] == "eligible"
    assert research["total"] == 400
    assert research["ticket_lines"] == [
        "◎－○ 1-2 100円",
        "◎－▲ 1-3 100円",
        "◎－△ 1-4 100円",
        "◎－☆ 1-5 100円",
    ]
    assert all("単勝 500円" not in line for line in research["lines"])
    assert "3連複" not in "\n".join(research["lines"])

    missing = build_research_bet([row(1, 2, "◎", 3.0)], "nar", context="mobile")
    assert missing["show"] is False


def test_nar_research_bet_waits_for_odds_and_marks_out_of_rule():
    waiting = build_research_bet(marked_rows(None), "nar", context="mobile")
    assert waiting["show"] is True
    assert waiting["research_status"] == "waiting_odds"
    assert waiting["total"] == 0
    assert any("オッズ確定後" in line for line in waiting["lines"])

    out = build_research_bet(marked_rows(2.41), "nar", context="mobile")
    assert out["research_status"] == "out_of_rule"
    assert out["total"] == 0
    assert any("研究買い条件外" in line for line in out["lines"])


def test_nar_research_bet_odds_boundaries_and_invalid_values():
    for odds in (2.39, 2.4, 2.40):
        assert build_research_bet(marked_rows(odds), "nar", context="mobile")["research_status"] == "eligible"
    for odds in (2.41, 2.5, 3.0):
        assert build_research_bet(marked_rows(odds), "nar", context="mobile")["research_status"] == "out_of_rule"
    for odds in (0, 0.0, "0", "0倍", "—", "未取得", float("nan"), -1, "bad"):
        assert build_research_bet(marked_rows(odds), "nar", context="mobile")["research_status"] == "waiting_odds"


def test_nar_monitor_tags_do_not_change_research_eligibility():
    rows = [
        row(1, 1, "◎", 2.4, current_rank=5),
        row(2, 2, "○", 4.1, current_rank=4),
        row(3, 3, "▲", 8.0, current_rank=3),
        row(4, 4, "△", 12.0, current_rank=2),
        row(5, 5, "☆", 20.0, current_rank=1),
    ]
    rows[0]["axis_confidence"] = "A"
    rows[0]["market_ability_score"] = 100
    rows[1]["market_ability_score"] = 80
    research = build_research_bet(rows, "nar", context="mobile")
    assert research["research_status"] == "eligible"
    assert research["monitor_flags"]["axis_confidence_a"] is True
    assert research["monitor_flags"]["ability_gap_1_2_ge_10"] is True
    assert research["monitor_flags"]["ability_current_top5_match"] is False
