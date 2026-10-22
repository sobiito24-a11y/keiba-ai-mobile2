from copy import deepcopy

from core.candidate_profile import facts
from core.final_candidate_metrics import project


def source():
    return {
        "3走平均": 11.7, "平均指数": 100, "最高指数": 99,
        "★最高指数": 15, "★該当走": "2走前", "star_max_venue": "門別",
        "star_max_surface": "ダ", "star_max_distance": 1000, "star_max_turn": "右",
        "_past_runs": [
            dict(label=label, race_date=date, value=value, position=finish,
                 racecourse="門別", surface="ダ", distance=distance, direction="右")
            for label, date, value, finish, distance in (
                ("3走前", "2026-08-01", 12, 1, 1000),
                ("前走", "2026-10-01", 8, 2, 1100),
                ("2走前", "2026-09-01", 15, 8, 1000),
            )
        ],
    }


def horse(row=None, mode="nar"):
    return dict(
        no="1", mode=mode, ability="51", ability_rank="3",
        distance={"value": 10, "rank": 2}, course={"value": 20, "rank": 1},
        average={"value": 100}, maximum=99,
        profile=facts(row or source(), dict(race_date="2026-10-18", venue="門別", surface="ダ", distance=1000, turn="右")),
        jockey_change_text="継続", weight_delta=-1, plus="同会場好走", caution="休養",
        style="先", corner=4, training="A",
    )


def test_dated_runs_are_oldest_first_and_indices_are_not_finishes():
    row = source()
    h = horse(row)
    before = deepcopy((h, row))
    m = project(h, row)
    assert [r["label"] for r in m["runs"]] == ["3走前", "2走前", "前走"]
    assert [r["time_index"] for r in m["runs"]] == [12, 15, 8]
    assert [r["is_maximum"] for r in m["runs"]] == [False, True, False]
    assert m["runs"][0]["condition"] == "門別・ダ1000m・右"
    assert (h, row) == before


def test_saved_three_average_and_star_peak_keep_their_own_definitions():
    row = source()
    m = project(horse(row), row)
    assert m["average"] == 11.7 and m["average_source"] == "3走平均"
    assert m["maximum"] == 15 and m["maximum_source"] == "★最高指数"
    row.pop("3走平均")
    row.pop("★最高指数")
    m = project(horse(row), row)
    assert m["average"] == 11.7  # Display-only dated three-run mean, never NAR's 平均指数.
    assert m["average_source"] == "dated_profile_runs" and m["average_calculated"]
    assert m["maximum"] is None  # Generic 最高指数 is not the saved star.
    assert project(horse(row, "jra"), row)["average"] == 100


def test_peak_outside_recent_three_never_creates_a_star():
    row = source()
    row["★最高指数"] = 99
    assert not any(r["is_maximum"] for r in project(horse(row), row)["runs"])
    row["★最高指数"] = 15
    row["★該当走"] = "4走前"
    assert not any(r["is_maximum"] for r in project(horse(row), row)["runs"])
    row["★該当走"] = "2走前"
    row["star_max_surface"] = "芝"
    assert not any(r["is_maximum"] for r in project(horse(row), row)["runs"])


def test_current_and_future_starts_never_enter_comparison():
    row = source()
    row["_past_runs"][1]["race_date"] = "2026-10-18"
    row["_past_runs"][2]["race_date"] = "2026-11-01"
    m = project(horse(row), row)
    assert [r["time_index"] for r in m["runs"]] == [12, None, None]
    assert m["stability"]["stars"] is None
    row.pop("3走平均")
    assert project(horse(row), row)["average"] is None


def test_missing_values_do_not_become_zero_or_star_rating():
    m = project(dict(mode="nar", profile={}), {})
    assert m["average"] is m["maximum"] is None
    assert all(r["time_index"] is None and not r["is_maximum"] for r in m["runs"])
    assert all(r["condition"] == "未取得" for r in m["runs"])
    assert m["stability"] == {"stars": None, "text": "未取得"}
    assert m["jockey_change"] == "未取得" and m["rest"] == "未取得"
    assert m["weight_delta"] is None and m["training"] == "対象外"


def test_stability_is_labelled_without_peak_stars_and_conditions_reused():
    m = project(horse(), source())
    assert "/5" in m["stability"]["text"] and "★" not in m["stability"]["text"]
    assert "好走歴あり" in m["same_distance"]
    assert "好走歴あり" in m["same_course"]
    assert m["jockey_change"] == "継続" and m["rest_days"] == 17
    assert m["corner"] == 4 and m["weight_delta"] == -1


def test_rest_conflict_and_existing_weight_audit_are_not_overridden():
    h = horse()
    h["candidate_evidence"] = {"audit": {
        "rest": {"status": "conflict", "days": None},
        "weight": {"delta": None},
    }}
    m = project(h, source())
    assert m["rest_days"] is None and "不一致" in m["rest"]
    assert m["weight_delta"] is None
