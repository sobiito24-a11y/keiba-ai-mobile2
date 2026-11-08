"""Yesterday's predictions + user-verified last-minute odds, without false edges."""
from datetime import datetime, timedelta
from copy import deepcopy

import pytest
from core import race_odds
from core.race_odds_manual import parse_lines, build_observation
from core.race_value_research import evaluate_reference, price_state
from core.race_value_research_ui import current_observation


def identity():
    return dict(race_id="202605050111",mode="jra",
                horses=[dict(horse_no=n, name=f"馬{n}") for n in (1,2,3)])


def observed():
    return datetime(2026,11,15,13,0,0,tzinfo=race_odds.JST)


def prediction():
    return dict(status="reference",race_id=identity()["race_id"],mode="jra",
                model_id="test-uncalibrated",horses=[
                    dict(horse_no=1,name="馬1",win=0.5,place=0.8,win_range=[0.4,0.6],place_range=[0.6,0.9]),
                    dict(horse_no=2,name="馬2",win=0.3,place=0.7,win_range=[0.2,0.4],place_range=[0.5,0.8]),
                    dict(horse_no=3,name="馬3",win=0.2,place=0.5,win_range=[0.1,0.3],place_range=[0.3,0.7]),
                ],wide=[dict(horses=[1,2],probability=0.25,range=[.2,.3])])


def test_manual_text_accepts_win_wide_quinella_place_without_fabrication():
    source="単勝 1 5.0\n馬連 1-2 6.4\nワイド 1-2 4.5-5.8\n複勝 2 1.4〜2.1"
    # Width/numeral normalization is safe; no multiple market fallback.
    p=parse_lines(source,identity())
    assert len(p)==4
    assert next(x for x in p if x["kind"]=="wide")["high"]==5.8
    q=build_observation(source,identity(),source="現地サイト",seen_now=True,received_at=observed())
    assert q["observed_at"]==observed().isoformat()
    assert q["observed_time_definition"]=="user_visually_checked_at_not_provider_update"
    assert q["collection_status"]=="partial"
    assert q["source"].startswith("自己確認：")
    assert q["coverage"]["wide"]["count"]==1
    assert q["coverage"]["quinella"]["count"]==1


@pytest.mark.parametrize("text", [
    "単勝 4 5.0",
    "馬連 1-1 12.1",
    "ワイド 1-2 6.0-4.0",
    "単勝 1 5.0-6.0",
    "馬連 1 3.0",
    "単勝 1 5.0\n単勝 1 5.3",
    "単勝 1 nan",
    "単勝 1 0",
    "馬単 1-2 6.1",
])
def test_invalid_ticket_or_fabricated_price_rejected(text):
    with pytest.raises(ValueError):
        parse_lines(text,identity())


def test_user_confirmation_is_required_no_hidden_refresh_of_observed_time():
    with pytest.raises(ValueError,match="今確認"):
        build_observation("単勝 1 5.1",identity(),source="外部サイト",seen_now=False)
    a=build_observation("単勝 1 5.1",identity(),source="外部サイト",seen_now=True,received_at=observed())
    b=build_observation("単勝 1 5.2",identity(),source="外部サイト",seen_now=True,
                        received_at=observed()+timedelta(minutes=2))
    history=race_odds.merge([a],[b],identity())
    assert len(history)==2
    assert history[0]["observed_at"]==observed().isoformat()
    assert history[1]["observed_at"]==(observed()+timedelta(minutes=2)).isoformat()


def test_reference_reports_exact_ticket_break_even_and_uncertainty():
    source="単勝 1 5.0\n馬連 1-2 6.4\nワイド 1-2 4.5-5.8\n複勝 2 1.4-2.1"
    quote=build_observation(source,identity(),source="他サイト",seen_now=True,received_at=observed())
    p=prediction()
    before=deepcopy((p,quote))
    out=evaluate_reference(p,quote,
       start_time="2026-11-15T14:00:00+09:00",now=observed()+timedelta(minutes=1))
    assert (p,quote)==before
    assert out["is_calibrated"] is False and out["proven_edge"] is False
    assert out["recommendation"] is None
    assert len(out["tickets"])==4
    bykind={t["kind"]:t for t in out["tickets"]}
    assert bykind["win"]["model_gross_pct"]==pytest.approx(250.0)
    assert bykind["win"]["break_even_pct"]==pytest.approx(20)
    assert bykind["wide"]["model_gross_pct"]==pytest.approx(112.5)
    assert bykind["wide"]["break_even_pct"]==pytest.approx(100/4.5)
    assert bykind["quinella"]["model_type"]=="未校正馬連近似"
    assert bykind["place"]["model_gross_pct"]==pytest.approx(98.0)
    assert out["price_state"].startswith("利用者が5分以内")


def test_unrelated_race_or_unknown_price_does_not_use_outdated_observations():
    q=build_observation("単勝 1 2.5",identity(),source="外部サイト",seen_now=True,received_at=observed())
    p=prediction()
    assert evaluate_reference(p,dict(q,race_id="202605050112"))["tickets"]==[]
    assert evaluate_reference(p,None)["tickets"]==[]
    assert "古い" in price_state(q,"2026-11-15T14:00:00+09:00",
        now=observed()+timedelta(minutes=15))


def test_untrained_model_does_not_substitute_market_price_as_probability():
    q=build_observation("単勝 1 5.0",identity(),source="外部サイト",seen_now=True,received_at=observed())
    p=prediction();p["status"]="insufficient"
    assert evaluate_reference(p,q)["tickets"]==[]
    assert evaluate_reference(p,q)["status"]=="確率を表示できません"


def test_current_observation_requires_explicit_selected_quote():
    class Result:
        race_mode="jra"
    # Store/session access is private to the selected race; no fallback.
    assert current_observation(Result(),{}) is None


def test_actual_game_ui_contains_price_panel_without_rewriting_prediction():
    from pathlib import Path
    app=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")
    assert "render_value_research(result)" in app
    assert "view = render_prices(result, view)" in app
    odds_ui=(Path(__file__).resolve().parents[1]/"core/race_odds_ui.py").read_text(encoding="utf-8")
    assert "build_observation(typed, identity" in odds_ui
    assert "外部サイト" in odds_ui
