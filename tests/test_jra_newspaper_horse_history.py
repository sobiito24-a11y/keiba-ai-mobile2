"""JRA full-career stats and Data24 short reviews are distinct, historical evidence."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup
import pandas as pd

from core.jra_newspaper_horse_history import (
    parse_newspaper_horse_history, match_history_to_horse,
    attach_jra_newspaper_history, with_jra_history_context,
)
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html
from core.race_explorer_cards import detail_html


RACE_ID = "202608050201"
HTML = """
<html><head><meta property="og:url"
content="https://race.netkeiba.com/race/shutuba_past.html?race_id=202608050201"></head>
<body>
<dl class="HorseList"><dt class="Waku_Horse">3</dt>
<dt class="HorseName"><a>テストホース</a></dt>
<dd class="Past_Wrapper"><ul>
<li class="Past"><div class="Data01">10/25 京都11R</div><div class="PastDataLine">
<span class="Data24">直線で前が詰まる</span></div></li>
<li class="Past"><div class="Data01">08/23 中京7R</div><div class="PastDataLine">
<span class="Data24">外を回って伸びる</span></div></li>
<li class="Past"><div class="Data01">05/11 東京11R</div><div class="PastDataLine">
<span class="Data24">出遅れから追い込む</span></div></li>
</ul></dd>
<dd class="Performance"><table>
<tr><th>全場ダ</th><td>4</td><td>3</td><td>1</td><td>9</td></tr>
<tr><td>京都ダ1800m</td><td>3</td><td>2</td><td>1</td><td>4</td></tr>
<tr><th>全場ダ1800m</th><td>4</td><td>3</td><td>1</td><td>7</td></tr>
<tr><th>重不ダ</th><td>0</td><td>1</td><td>0</td><td>1</td></tr>
</table></dd><dd class="Stable_Comment"><dl class="Comment_Cell">
<dd>ここまで順調。前走は前が詰まった。</dd></dl></dd>
</dl></body></html>
"""


def source_row():
    return {
        "馬番": 3, "馬名": "テストホース", "market_ability_rank": 5,
        "market_ability_score": 55.5, "final_mark_score": 999,
        "_past_runs": [
            {"label": "前走", "race_date": "2026-10-25", "position": 4},
            {"label": "2走前", "race_date": "2026-08-23", "position": 3},
            {"label": "3走前", "race_date": "2026-05-11", "position": 8},
        ],
    }


def test_per_horse_newspaper_short_notes_and_lifetime_track_records():
    parsed = parse_newspaper_horse_history(HTML, expected_race_id=RACE_ID)
    assert list(parsed) == ["3"]
    horse = parsed["3"]
    assert len(horse["career"]) == 4
    assert horse["career"][1] == {
        "label": "京都ダ1800m", "wins": 3, "seconds": 2, "thirds": 1,
        "other": 4, "starts": 10, "scope": "career_as_of_pre_race_newspaper",
    }
    matched = match_history_to_horse(horse, source_row(), "2026-11-08")
    assert matched["jra_past_short_notes"]["前走"] == "直線で前が詰まる"
    assert matched["jra_past_short_notes"]["2走前"] == "外を回って伸びる"
    assert len(matched["jra_career_performance"]) == 4
    assert "前が詰まった" in matched["jra_trainer_original_quote"]


def test_wrong_race_horse_or_date_never_cross_joins():
    assert parse_newspaper_horse_history(HTML, expected_race_id="202608050202") == {}
    parsed = parse_newspaper_horse_history(HTML, expected_race_id=RACE_ID)
    wrong = dict(source_row(), 馬名="別馬")
    assert match_history_to_horse(parsed["3"], wrong, "2026-11-08")["jra_career_performance"] == []
    shifted = deepcopy(source_row())
    shifted["_past_runs"][0]["race_date"] = "2026-10-24"
    matched = match_history_to_horse(parsed["3"], shifted, "2026-11-08")
    assert "前走" not in matched["jra_past_short_notes"]
    assert "2走前" in matched["jra_past_short_notes"]
    shifted["_past_runs"][1]["race_date"] = "2026-11-09"
    assert "2走前" not in match_history_to_horse(parsed["3"], shifted, "2026-11-08")["jra_past_short_notes"]


def test_raw_HTML_enriches_saved_prediction_without_altering_original_model():
    obj = SimpleNamespace(
        race_mode="jra",
        race_info={"race_date": "2026-11-08", "racecourse": "京都", "surface": "ダ", "distance": 1800},
        source_files={"newspaper": f"jra/{RACE_ID}/{RACE_ID}_newspaper.html"},
        overall_table=pd.DataFrame([source_row()]),
        horse_evaluation=pd.DataFrame([source_row()]),
        debug_info={},
    )
    before = deepcopy(obj.overall_table.to_dict("records"))
    attach_jra_newspaper_history(obj, {"newspaper": HTML})
    after = obj.overall_table.to_dict("records")[0]
    for key in ("market_ability_rank", "market_ability_score", "final_mark_score"):
        assert after[key] == before[0][key]
    assert after["jra_past_short_notes"]["前走"] == "直線で前が詰まる"
    assert after["jra_career_performance"][1]["starts"] == 10
    assert obj.horse_evaluation.iloc[0]["jra_history_status"] == "新聞原文取得"
    assert obj.debug_info["jra_newspaper_horse_history"]["research_only"]


def test_real_comparison_table_places_note_under_recent_index_and_career_by_course():
    row = source_row()
    saved = match_history_to_horse(parse_newspaper_horse_history(HTML, expected_race_id=RACE_ID)["3"],
                                   row, "2026-11-08")
    row.update(saved)
    original = deepcopy(row)
    view = [{
        "mode": "jra", "no": "3", "name": "テストホース", "ability_rank": "5",
        "explorer_facts": {"metrics": {
            "ability": {"value": 55.5, "rank": 5},
            "runs": [
                {"label": "前走", "time_index": 65.0, "date": "2026-10-25"},
                {"label": "2走前", "time_index": 61.0, "date": "2026-08-23"},
                {"label": "3走前", "time_index": 72.0, "date": "2026-05-11"},
            ],
        }},
    }]
    enriched = with_jra_history_context(view, [row], {"racecourse": "京都", "surface": "ダ", "distance": 1800})
    assert row == original and view[0].get("jra_career_performance") is None
    assert enriched[0]["jra_career_current_course"]["wins"] == 3
    schema = columns(enriched)
    assert next(s for s in schema if s["key"] == "career_course")["label"] == "同コース全戦績"
    cells = records(enriched)["3"]
    assert cells["career_course"] == "3-2-1-4"
    assert cells["run_latest_note"] == "直線で前が詰まる"
    shown = BeautifulSoup(lineup_html(enriched), "html.parser")
    assert shown.select_one("td.col-career_course").get_text(strip=True) == "3-2-1-4"
    assert "短評：直線で前が詰まる" in shown.select_one("td.col-run_latest").get_text()
    details = BeautifulSoup(detail_html(enriched[0]), "html.parser")
    assert "全場ダ" in details.select_one(".detail-jra-career").text
    assert "京都ダ1800m" in details.select_one(".detail-jra-career").text
    assert "直線で前が詰まる" in details.select_one(".detail-history").text
    assert not any("詰まる" in key for key in ("final_mark_score", "market_ability_score"))


def test_old_snapshots_do_not_fake_lifetime_zeros_or_newspaper_remarks():
    view = [{"mode": "jra", "no": "3", "name": "テストホース", "ability_rank": "5"}]
    old_row = source_row()
    new = with_jra_history_context(view, [old_row], {"racecourse": "京都", "surface": "ダ", "distance": 1800})
    assert new[0]["jra_career_current_course"] is None
    cells = records(new)["3"]
    assert cells["career_course"] is None
    assert cells["run_latest_note"] is None
    assert "未取得" in BeautifulSoup(detail_html(new[0]), "html.parser").select_one(".detail-jra-career").text


def test_real_fixture_has_pre_race_past_short_notes_and_full_career_records():
    html = (Path(__file__).parent / "fixtures/tanabata_20260712/keiba_data-61.html").read_text(encoding="utf-8")
    observed = parse_newspaper_horse_history(html, expected_race_id="202603020611")
    # The archived genuine newspaper contains actual per-horse Past.Data24 and
    # Performance rows. No inference from the user's screenshots is required.
    assert len(observed) >= 10
    assert any(h.get("career") for h in observed.values())
    assert any(h.get("notes") for h in observed.values())
    assert all(h["career"][0]["scope"] == "career_as_of_pre_race_newspaper"
               for h in observed.values() if h.get("career"))
