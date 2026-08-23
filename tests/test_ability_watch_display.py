from __future__ import annotations

import copy

import pandas as pd

import app
from core.ability_watch import ability_watch_rows, attach_ability_watch_columns


def watch_row(no: int, rank: int, value: float, mark: str = "", odds: float | None = None) -> dict:
    return {
        "馬番": no,
        "馬名": f"Horse{no}",
        "ability_band_v2": "A",
        "market_ability_rank": rank,
        "market_ability_score": value,
        "ai_current_mark": mark,
        "current_evaluation_rank": no,
        "actual_odds": odds,
        "馬年齢": "牡4",
    }


def test_ability_top_match_and_gap_are_display_only():
    rows = [watch_row(1, 1, 94.2, "◎", 2.8), watch_row(2, 2, 90.0, "○", 4.1)]
    original = copy.deepcopy(rows)
    labels = ability_watch_rows(rows, race_mode="jra")
    assert labels[0]["ability_top_match"] is True
    assert labels[0]["ability_top_match_label"] == "能力1位＝◎ / 2位との差 +4.2"
    assert labels[0]["ability_gap_1_2"] == 4.200000000000003
    assert rows == original


def test_unmarked_warning_patterns_jra_only_for_market_support():
    rows = [
        watch_row(1, 1, 94.0, "○", 2.0),
        watch_row(2, 2, 91.0, "", 6.4),
        watch_row(3, 3, 88.0, "", 18.0),
        watch_row(4, 4, 70.0, "", 8.0),
        watch_row(5, 5, 65.0, "", None),
    ]
    labels = ability_watch_rows(rows, race_mode="jra")
    assert labels[0]["ability_top_match"] is False
    assert labels[1]["high_risk_unmarked"] is True
    assert labels[1]["ability_watch_label"] == "⚠ 要注意の無印（能力上位＋市場支持）"
    assert labels[2]["ability_watch_label"] == "⚠ 能力上位の無印"
    assert labels[3]["ability_watch_label"] == "⚠ 市場支持ありの無印"
    assert labels[4]["ability_watch_label"] == ""
    nar_labels = ability_watch_rows([watch_row(4, 4, 70.0, "", 8.0)], race_mode="nar")
    assert nar_labels[0]["market_supported_unmarked"] is False
    assert nar_labels[0]["ability_watch_label"] == ""


def test_snapshot_odds_at_prediction_is_used_without_recalculation():
    row = {
        "horse_no": 7,
        "horse_name": "SnapshotHorse",
        "ability_rank": 4,
        "ability_value": 72.0,
        "mark": "",
        "odds_at_prediction": "6.4",
    }
    jra_labels = ability_watch_rows([row], race_mode="jra")
    assert jra_labels[0]["market_supported_unmarked"] is True
    assert jra_labels[0]["ability_watch_audit"]["saved_odds"] == 6.4

    nar_labels = ability_watch_rows([row], race_mode="nar")
    assert nar_labels[0]["market_supported_unmarked"] is False
    assert nar_labels[0]["ability_watch_audit"]["saved_odds"] == 6.4
    assert nar_labels[0]["ability_watch_label"] == ""


def test_attach_columns_and_card_html_show_labels_without_changing_prediction_values():
    source = pd.DataFrame(
        [
            watch_row(1, 1, 94.0, "◎", 2.5),
            watch_row(2, 2, 91.0, "", 6.4),
        ]
    )
    before = source[["market_ability_score", "market_ability_rank", "ai_current_mark", "current_evaluation_rank"]].copy(deep=True)
    attached = attach_ability_watch_columns(source, race_mode="jra")
    pd.testing.assert_frame_equal(
        attached[["market_ability_score", "market_ability_rank", "ai_current_mark", "current_evaluation_rank"]],
        before,
    )
    top_html = app.market_horse_card_html(attached.iloc[0].to_dict(), "jra")
    unmarked_html = app.market_horse_card_html(attached.iloc[1].to_dict(), "jra")
    assert "能力1位＝◎ / 2位との差 +3.0" in top_html
    assert "⚠ 要注意の無印（能力上位＋市場支持）" in unmarked_html
