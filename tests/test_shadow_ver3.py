from core.shadow_ver3 import evaluate_shadow_race, is_nar_condition_specialist, nar_same_condition_stats


def test_nar_condition_specialist_requires_actual_good_result():
    race_info = {"venue": "船橋", "distance": 2200, "surface": "ダ", "turn": "左"}
    lapland = {
        "horse_no": "5",
        "horse_name": "ラップランド",
        "market_ability_rank": 10,
        "market_ability_score": 48.7,
        "距離指数": 51,
        "コース指数": 61,
        "_past_runs": [
            {"venue": "船橋", "distance": 2200, "surface": "ダ", "turn": "左", "position": 1, "value": 47, "label": "3走前"},
            {"venue": "船橋", "distance": 1600, "surface": "ダ", "turn": "左", "position": 1, "value": 49, "label": "2走前"},
            {"venue": "船橋", "distance": 1600, "surface": "ダ", "turn": "左", "position": 4, "value": 44, "label": "前走"},
        ],
    }
    experience_only = {
        "horse_no": "6",
        "horse_name": "ヒロシゲジャック",
        "market_ability_rank": 9,
        "market_ability_score": 49.6,
        "距離指数": 60,
        "コース指数": 66,
        "_past_runs": [
            {"venue": "船橋", "distance": 2200, "surface": "ダ", "turn": "左", "position": 7, "value": 42, "label": "3走前"},
            {"venue": "川崎", "distance": 2000, "surface": "ダ", "turn": "左", "position": 5, "value": 46, "label": "2走前"},
            {"venue": "川崎", "distance": 2000, "surface": "ダ", "turn": "左", "position": 7, "value": 50, "label": "前走"},
        ],
    }
    lapland.update(nar_same_condition_stats(lapland, race_info))
    experience_only.update(nar_same_condition_stats(experience_only, race_info))
    assert is_nar_condition_specialist(lapland) is True
    assert is_nar_condition_specialist(experience_only) is False


def test_nar_candidate_a_keeps_top5_fixed_and_promotes_specialist_after_top3():
    race_info = {"venue": "船橋", "distance": 2200, "surface": "ダ", "turn": "左"}
    rows = [
        {"horse_no": "1", "horse_name": "A", "current_evaluation_rank": 1, "market_ability_score": 70},
        {"horse_no": "2", "horse_name": "B", "current_evaluation_rank": 2, "market_ability_score": 69},
        {"horse_no": "3", "horse_name": "C", "current_evaluation_rank": 3, "market_ability_score": 68},
        {"horse_no": "4", "horse_name": "D", "current_evaluation_rank": 4, "market_ability_score": 67},
        {
            "horse_no": "5",
            "horse_name": "Special",
            "current_evaluation_rank": 9,
            "market_ability_rank": 9,
            "market_ability_score": 50,
            "距離指数": 51,
            "コース指数": 61,
            "_past_runs": [{"venue": "船橋", "distance": 2200, "position": 1, "value": 50, "label": "前走"}],
        },
        {"horse_no": "6", "horse_name": "E", "current_evaluation_rank": 5, "market_ability_score": 66},
    ]
    result = evaluate_shadow_race(rows, "nar", race_info)["candidate_a"]
    top5 = [row["horse_no"] for row in sorted(result, key=lambda row: row["candidate_a_rank"])[:5]]
    assert len(top5) == 5
    assert top5[:4] == ["1", "2", "3", "5"]
    special = next(row for row in result if row["horse_no"] == "5")
    assert special["candidate_a_mark"] == "☆"
