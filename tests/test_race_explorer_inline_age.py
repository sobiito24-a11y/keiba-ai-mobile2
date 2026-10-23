"""The fixed identity cell keeps sex/age beside the full horse name."""
from copy import deepcopy

from bs4 import BeautifulSoup
import pytest

from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html
from tests.test_compact_index_ranks import horse


@pytest.mark.parametrize("mode", ["jra", "nar"])
@pytest.mark.parametrize("name,age,display_age", [
    ("レフレール", "牡3", "牡3"),
    ("ゴールドパートナー", "牡4", "牡4"),
    ("長い馬名を省略せず性齢と並べる比較馬", "牝3", "牝3"),
    ("性齢未取得馬", None, "―"),
])
def test_inline_age_replaces_the_column_without_changing_saved_comparison_values(mode, name, age, display_age):
    h = horse(mode=mode)
    h.update(name=name, age=age)
    before = deepcopy(h)
    original_cells = records([h])
    doc = BeautifulSoup(lineup_html([h]), "html.parser")
    row = doc.select_one("tr[data-horse]")
    identity = row.select_one("td.col-name .horse-select")
    assert identity.strong.text == name
    assert identity.select_one(".horse-age").text == display_age
    assert identity.select_one(".horse-name-age > strong + .horse-age") is not None
    assert identity["data-horse-open"] == h["no"]
    assert identity["aria-controls"] == "horse-detail-" + h["no"]
    assert not doc.select("th.col-age,td.col-age")
    assert doc.select_one("th.col-name .column-label").text == "馬名・性齢"
    assert [td["class"][0] for td in row.select("td")][:5] == [
        "col-user", "col-frame", "col-no", "col-name", "col-jockey"]
    assert doc.select_one('#lineup-sort option[value="age"]').text == "性齢"
    assert doc.select_one('#filter-column option[value="age"]').text == "性齢"
    assert next(spec for spec in columns([h]) if spec["key"] == "age")["table_hidden"]
    for key in ("score", "ability", "distance", "course", "star", "away"):
        paired = row.select_one(".col-" + key + " .comparison-metric")
        assert paired is not None
        assert float(paired["data-value"]) == original_cells[h["no"]][key]
        rank_key = "rank" if key == "score" else key + "_rank"
        assert int(paired["data-rank"]) == original_cells[h["no"]][rank_key]
    assert records([h]) == original_cells and h == before


def test_inline_age_and_full_name_are_escaped_in_the_shared_fixed_cell():
    h = horse()
    h.update(name='<img src=x onerror="bad()">長い馬名', age='<svg onload="bad()">牡3')
    doc = BeautifulSoup(lineup_html([h]), "html.parser")
    assert not doc.select("img,svg,[onerror],[onload]")
    assert doc.select_one("td.col-name strong").text == h["name"]
    assert doc.select_one("td.col-name .horse-age").text == h["age"]
