from core.nar_purchase_judgement import annotate_nar_purchase_judgement
from core.nar_race_diagnostics import build_full_field_comparison


def _horse(no: int, rank: int, score: float, **extra):
    row = {
        "number": str(no),
        "name": f"馬{no}",
        "nar_pure_ability_rank": rank,
        "nar_pure_ability_score": score,
        "nar_top5_rank": rank,
        "corner4_group": "middle",
        "same_distance": "—",
        "same_course": "—",
        "has_recent_top3": False,
        "data_insufficient": False,
    }
    row.update(extra)
    return row


def _strong_partners():
    return [
        _horse(1, 1, 100, market_rank=1, odds=2.8),
        _horse(2, 2, 88, market_rank=2, corner4_group="front", same_distance="★", has_recent_top3=True, jockey_change="継続"),
        _horse(3, 3, 80, market_rank=3, corner4_group="front", same_distance="★", same_course="★"),
        _horse(4, 4, 74, market_rank=4, corner4_group="front", same_course="★", has_recent_top3=True),
        _horse(5, 5, 70),
    ]


def test_strong_market_top_honmei_with_high_partners_is_a_and_win_allowed():
    horses = _strong_partners()
    result = annotate_nar_purchase_judgement(horses)

    assert result["race_purchase_judgement"] == "A"
    assert result["win_bet_allowed"] is True
    assert result["recommended_ticket_mode"] == "WIN"
    assert result["ability_gap_1_2"] == 12
    assert result["trusted_partner_count"] >= 3


def test_odds_under_two_blocks_win_bet_but_keeps_axis_ticket_candidate():
    horses = _strong_partners()
    horses[0]["odds"] = 1.5
    result = annotate_nar_purchase_judgement(horses)

    assert result["race_purchase_judgement"] in {"A", "B"}
    assert result["win_bet_allowed"] is False
    assert result["win_bet_block_reason"] == "◎単勝1倍台のため単勝購入対象外"
    assert result["recommended_ticket_mode"] == "AXIS_QUINELLA"


def test_close_gap_and_no_high_partner_is_c_or_d():
    horses = [
        _horse(1, 1, 100, market_rank=1, odds=2.8),
        _horse(2, 2, 99),
        _horse(3, 3, 98),
        _horse(4, 4, 97),
        _horse(5, 5, 96),
    ]
    result = annotate_nar_purchase_judgement(horses)

    assert result["race_purchase_judgement"] in {"C", "D"}
    assert result["trusted_partner_count"] == 0


def test_market_rank_four_honmei_is_pass_even_with_large_gap():
    horses = _strong_partners()
    horses[0]["market_rank"] = 4
    result = annotate_nar_purchase_judgement(horses)

    assert result["race_purchase_judgement"] == "D"
    assert result["recommended_ticket_mode"] == "PASS"
    assert "◎市場4位" in result["race_purchase_reason"]


def test_odds_under_two_with_no_high_partner_becomes_c_or_d():
    horses = [
        _horse(1, 1, 100, market_rank=1, odds=1.4),
        _horse(2, 2, 88),
        _horse(3, 3, 80),
        _horse(4, 4, 74),
        _horse(5, 5, 70),
    ]
    result = annotate_nar_purchase_judgement(horses)

    assert result["win_bet_allowed"] is False
    assert result["race_purchase_judgement"] in {"C", "D"}


def test_partner_trust_count_centers_on_pure_rank_two_to_four_high():
    horses = [
        _horse(1, 1, 100, market_rank=1, odds=3.0),
        _horse(2, 2, 94, market_rank=2, corner4_group="front", same_distance="★"),
        _horse(3, 3, 90, market_rank=3, corner4_group="front", same_distance="★"),
        _horse(4, 4, 88, corner4_group="front"),
        _horse(5, 5, 86),
    ]
    result = annotate_nar_purchase_judgement(horses)
    by_rank = {horse["nar_pure_ability_rank"]: horse for horse in horses}

    assert by_rank[2]["partner_trust_level"] == "HIGH"
    assert by_rank[3]["partner_trust_level"] == "HIGH"
    assert by_rank[4]["partner_trust_level"] == "MID"
    assert by_rank[5]["partner_trust_level"] == "LOW"
    assert result["trusted_partner_count"] == 2


def test_multiple_data_insufficient_top5_pushes_toward_pass():
    horses = _strong_partners()
    horses[1]["data_insufficient"] = True
    horses[1]["data_insufficient_reason"] = "能力材料不足"
    horses[2]["data_insufficient"] = True
    horses[2]["data_insufficient_reason"] = "初出走"
    result = annotate_nar_purchase_judgement(horses)

    assert result["race_purchase_judgement"] == "D"
    assert "Top5に能力材料不足2頭" in result["race_purchase_reason"]


def test_nar_comparison_uses_pure_rank_marks_and_keeps_jra_rank_unchanged():
    nar_rows = [
        {"馬番": 1, "馬名": "一位", "market_ability_score": 100, "current_evaluation_rank": 3, "_最終印点": 80, "人気": 1, "単勝オッズ": 2.8},
        {"馬番": 2, "馬名": "二位", "market_ability_score": 90, "current_evaluation_rank": 1, "_最終印点": 100},
        {"馬番": 3, "馬名": "三位", "market_ability_score": 80, "current_evaluation_rank": 2, "_最終印点": 90},
        {"馬番": 4, "馬名": "四位", "market_ability_score": 70, "current_evaluation_rank": 6, "_最終印点": 60},
        {"馬番": 5, "馬名": "五位", "market_ability_score": 60, "current_evaluation_rank": 5, "_最終印点": 70},
        {"馬番": 6, "馬名": "六位", "market_ability_score": 50, "current_evaluation_rank": 4, "_最終印点": 75},
    ]
    nar = build_full_field_comparison(nar_rows, race_mode="nar", sort_mode="current")
    assert [row["number"] for row in nar["rows"]] == ["1", "2", "3", "4", "5", "6"]
    assert [row["nar_top5_mark"] for row in nar["rows"]] == ["◎", "○", "▲", "△1", "△2", ""]
    assert nar["rows"][5]["nar_ver3_top5"] is True
    assert nar["rows"][5]["nar_top5_swap_status"] == "VER3_ONLY"

    jra_rows = [
        {"馬番": 1, "馬名": "JRA一", "market_ability_score": 50, "v1_final_rank": 2, "jra_top5_score": 50},
        {"馬番": 2, "馬名": "JRA二", "market_ability_score": 40, "v1_final_rank": 1, "jra_top5_score": 60},
    ]
    jra = build_full_field_comparison(jra_rows, race_mode="jra", sort_mode="current")
    assert [row["number"] for row in jra["rows"]] == ["1", "2"]
    assert all(row.get("nar_top5_rank") is None for row in jra["rows"])
