"""Future holdout validator does not misclassify historical races or dead-heats."""
from datetime import date

import pytest

from scripts.validate_frozen_weekend import (
    HOLDOUT_START, calculate_three, payouts, research_for_race,
)


def test_dead_heat_payments_require_explicit_pair_list():
    actual = {
        "winner_no": "7", "second_no": "8", "third_no": "2",
        "third_no_extra": "5", "quin_pay": "3090",
        "wide12": "390", "wide13": "730", "wide23": "230",
    }
    with pytest.raises(ValueError, match="Joint third"):
        payouts(actual)
    actual["wide_pair_payouts_json"] = '{"7-8":390,"2-7":730,"5-7":1170,"2-8":230,"5-8":450}'
    assert calculate_three(["7", "1", "5"], actual) == {
        "stake": 300, "wide": 1170, "quin": 0,
    }


def test_archive_projection_requires_observed_pre_race_indices_and_days():
    r = dict(
        race_mode="jra", race_id="future123", race_number="1R",
        date="2026-11-14", venue="京都",
        horses=[
            {"horse_no": "1", "training_short": "C"},
            {"horse_no": "2", "training_short": "D"},
            {"horse_no": "3", "training_short": "B"},
            {"horse_no": "4", "training_short": "A"},
        ],
        prediction_result={
            "overall_table": {"records": [
                {"馬番": i, "market_ability_rank": i, "コース指数": 50 + (i == 3) * 20,
                 "距離指数": 40 + (i == 4) * 20,
                 "_past_runs": [{"position": 2, "race_date": "2026-10-25"}]}
                for i in range(1, 5)
            ]}
        },
    )
    projected = research_for_race(r, "2026-11-14")
    assert projected["pure3"] == ["1", "2", "3"]
    assert projected["jra_frozen3"] == ["1", "3", "4"]
    assert projected["version"].endswith("20261108_v1")
    assert HOLDOUT_START == "2026-11-14"


def test_missing_ability_ranks_do_not_mint_fictional_hypotheses():
    r = dict(race_mode="jra", date="2026-11-14", race_id="jump",
             prediction_result={"overall_table": {"records": [{"馬番": 1}, {"馬番": 2}, {"馬番": 3}]}})
    output = research_for_race(r, "2026-11-14")
    assert output["pure3"] == output["jra_frozen3"] == []
    assert not output["ability_complete"]
