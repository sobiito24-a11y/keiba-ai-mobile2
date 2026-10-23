"""Pickup prices are the selected validated observation, without prediction edits."""
from copy import deepcopy
from datetime import datetime

from bs4 import BeautifulSoup
import pytest

from core import race_odds as odds
from core.final_candidate_selection import formal_score, select_indices
from core.race_explorer_cards import pickup_html
from tests.test_race_explorer_cards import horse


RACE_ID = "202608040511"
IMPORTED_AT = datetime.fromisoformat("2026-10-18T15:23:59+09:00")
PRICE_UPDATED_AT = "2026-10-18T14:03:02+09:00"


def field(mode):
    return [horse(no, mode) for no in range(1, 9)]


def identity(view, mode):
    return dict(race_id=RACE_ID, mode=mode,
                horses=[dict(horse_no=int(h["no"]), name=h["name"]) for h in view])


def imported(view, mode, rows, updated=PRICE_UPDATED_AT):
    host = "race.netkeiba.com" if mode == "jra" else "nar.netkeiba.com"
    html = ('<meta charset="utf-8"><link rel="canonical" href="https://' + host +
            '/odds/index.html?race_id=' + RACE_ID + '">')
    if updated is not None:
        html += '<time data-odds-updated-at="' + updated + '"></time>'
    html += '<table><tr><th>馬番</th><th>馬名</th><th>単勝</th><th>人気</th></tr>'
    for no, price, popularity in rows:
        html += ('<tr><td>' + str(no) + '</td><td>比較馬' + str(no) + '</td><td>' +
                 str(price) + '</td><td>' + str(popularity) + '</td></tr>')
    html += '</table>'
    return odds.import_files([("odds.html", html.encode())], identity(view, mode),
                             now=IMPORTED_AT)[0]


def cards(view):
    dom = BeautifulSoup(pickup_html(view), "html.parser")
    return {card["data-horse-open"]: card.get_text(" ", strip=True)
            for card in dom.select(".pickup-card")}


def official(view):
    return [(h["no"], formal_score(h), h["rank"], h["mark"], h["formal_member"])
            for h in view]


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_pickup_without_price_observation_has_explicit_missing_price_and_popularity(mode):
    view = field(mode)
    before = deepcopy(view)
    overlaid = odds.overlay(view, None, "オッズ未取込")
    text = cards(overlaid)
    assert all("単勝 未取得" in card and "人気 未取得" in card for card in text.values())
    assert not any("番人気" in card for card in text.values())
    assert official(overlaid) == official(view)
    assert view == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_pickup_manual_html_shows_supplied_popularity_and_provider_update_time(mode):
    view = field(mode)
    before = deepcopy(view)
    # Price order and popularity intentionally disagree: neither horse number nor
    # lower price may be used to invent the popularity of a horse without it.
    quote = imported(view, mode, [(1, 9.4, 3), (2, 2.1, "—")])
    original_quote = deepcopy(quote)
    overlaid = odds.overlay(view, quote, "HTML取込")
    source_projection = deepcopy(overlaid)
    text = cards(overlaid)
    assert "単勝 9.4倍" in text["1"] and "3番人気" in text["1"]
    assert "単勝 2.1倍" in text["2"] and "人気 未取得" in text["2"]
    assert "番人気" not in text["2"]
    assert "提供元更新" in text["1"] and "14:03:02" in text["1"]
    assert "15:23:59" not in text["1"]
    assert select_indices(overlaid, "no") == select_indices(view, "no")
    assert official(overlaid) == official(view)
    assert view == before and quote == original_quote and overlaid == source_projection


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_missing_provider_timestamp_is_not_replaced_by_html_import_timestamp(mode):
    view = field(mode)
    quote = imported(view, mode, [(1, 4.8, 2)], updated=None)
    text = cards(odds.overlay(view, quote, "HTML取込"))["1"]
    assert quote["observed_at"] is None
    assert "単勝 4.8倍" in text and "2番人気" in text
    assert "提供元更新" in text and "未取得" in text
    assert "15:23:59" not in text


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_partial_price_replacement_and_withdrawal_do_not_show_old_pickup_prices(mode):
    view = field(mode)
    first = imported(view, mode, [(no, 20 + no + .1, no) for no in range(1, 9)])
    old = odds.overlay(view, first, "以前のHTML")
    before = deepcopy(old)
    replacement = imported(view, mode, [(2, "取消", "—"), (3, 7.6, 4)])
    projected = odds.overlay(old, replacement, "更新HTML")
    projected_before = deepcopy(projected)
    text = cards(projected)
    assert "単勝 未取得" in text["1"] and "人気 未取得" in text["1"]
    assert "21.1" not in text["1"]
    assert "取消・除外" in text["2"] and "22.1" not in text["2"]
    assert "番人気" not in text["2"]
    assert "単勝 7.6倍" in text["3"] and "4番人気" in text["3"]
    assert official(projected) == official(old)
    assert select_indices(projected, "no") == select_indices(old, "no")
    assert old == before and projected == projected_before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_explicit_missing_overlay_cell_never_revives_saved_card_price(mode):
    view = field(mode)
    view[0].update(odds="19.8", popularity=None, sort_values={"odds": None})
    before = deepcopy(view)
    text = cards(view)["1"]
    assert "単勝 未取得" in text and "19.8" not in text
    assert "人気 未取得" in text and view == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_compact_card_retains_state_changes_features_and_selected_prices(mode):
    view = field(mode)
    h = view[0]
    h.update(odds="5.2", popularity=3, odds_time="10/18 14:03:02")
    before = deepcopy(view)
    card = BeautifulSoup(pickup_html(view), "html.parser").select_one(".pickup-card")
    labels = [item.small.text for item in card.select(".pickup-state-item")]
    assert labels == (["調教"] if mode == "jra" else []) + ["前走間隔", "前走比", "純能力"]
    assert card.select_one(".pickup-changes").text == "今回斤量 55kg騎手 乗替：前走騎手 → 今回騎手"
    assert len(card.select(".pickup-features > span")) == 3
    assert "5.2倍" in card.select_one(".pickup-prices").text
    assert "3番人気" in card.select_one(".pickup-prices").text
    assert "14:03:02" in card.select_one(".pickup-price-time").text
    assert card.select_one(".pickup-open").text.startswith("詳細を見る")
    assert view == before
