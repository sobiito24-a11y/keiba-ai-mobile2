from core.nar_purchase_judgement import annotate_nar_purchase_judgement


def _horse(no: int, rank: int, score: float, **extra):
    row = {
        "number": str(no), "name": f"馬{no}", "nar_pure_ability_rank": rank,
        "nar_pure_ability_score": score, "corner4_group": "middle",
        "same_distance": "—", "same_course": "—", "has_recent_top3": False,
        "data_insufficient": False,
    }
    row.update(extra)
    return row


def _strong():
    return [
        _horse(1, 1, 100, corner4_group="front", same_distance="★", has_recent_top3=True),
        _horse(2, 2, 88, corner4_group="front", same_distance="★", has_recent_top3=True, jockey_change="継続"),
        _horse(3, 3, 80, corner4_group="front", same_course="★", has_recent_top3=True),
        _horse(4, 4, 74, corner4_group="front", same_course="★"),
        _horse(5, 5, 70),
    ]


def test_odds_and_popularity_do_not_change_nar_purchase_judgement():
    a = _strong()
    b = _strong()
    for horse in a:
        horse.update(odds=1.1, popularity=1, market_rank=1)
    for horse in b:
        horse.update(odds=999, popularity=99, market_rank=99)
    assert annotate_nar_purchase_judgement(a) == annotate_nar_purchase_judgement(b)


def test_strong_axis_and_trusted_partners_create_axis_grade():
    result = annotate_nar_purchase_judgement(_strong(), race_info={"venue": "水沢"})
    assert result["race_purchase_judgement"] == "A"
    assert result["axis_support_level"] == "HIGH"
    assert result["trusted_partner_count"] >= 2
    assert result["recommended_ticket_mode"] == "AXIS_QUINELLA"
    assert result["venue_profile_type"] == "順位信頼型"
    assert result["venue_profile_verified_for_scoring"] is False


def test_close_gap_and_weak_axis_is_not_forced_buy():
    horses = [_horse(1, 1, 100), _horse(2, 2, 99), _horse(3, 3, 98), _horse(4, 4, 97), _horse(5, 5, 96)]
    result = annotate_nar_purchase_judgement(horses)
    assert result["race_purchase_judgement"] in {"C", "D"}
    assert result["recommended_ticket_mode"] in {"MULTI", "PASS"}


def test_data_shortage_pushes_to_pass():
    horses = _strong()
    horses[1]["data_insufficient"] = True
    horses[2]["data_insufficient"] = True
    result = annotate_nar_purchase_judgement(horses)
    assert result["race_purchase_judgement"] == "D"


def test_honmei_market_compatibility_fields_are_blank():
    result = annotate_nar_purchase_judgement(_strong())
    assert result["honmei_market_rank"] is None
    assert result["honmei_odds"] is None
    assert result["win_bet_allowed"] is False
    assert "オッズ" in result["win_bet_block_reason"]
