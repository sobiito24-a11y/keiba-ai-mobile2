from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from core.course_materials import (
    attach_course_materials_to_result,
    parse_netkeiba_course_materials,
    parse_netkeiba_jockey_course_stats,
)
from core.market_compare import evaluate_market_table
from core.models import PredictionResult


RACE_ID = "202604020612"


def newspaper_html(*, mode: str = "jra", mobile: bool = False) -> str:
    host = "nar" if mode == "nar" else "race"
    if mobile:
        host += ".sp"
    course = "佐賀1300mダ" if mode == "nar" else "新潟1200m芝 Aコース"
    extra_bias = " BiasPattern222" if mode == "nar" else ""
    return f"""<!doctype html><html><head>
    <meta property="og:url" content="https://{host}.netkeiba.com/race/newspaper.html?race_id={RACE_ID}">
    <link rel="canonical" href="https://{host}.netkeiba.com/race/newspaper.html?race_id={RACE_ID}">
    <title>競馬新聞</title></head><body>
    <section class="AiTenkaiArea01">
      <div class="AiTenkaiBlock02 DevelopOpinionArea">
        <section class="CourseDataArea Time"><div class="CourseDataTitle"><h2>コース情報 {course}</h2></div>
          <div class="Data Pace_H">H</div></section>
        <section class="DevelopOpinionArea"><dl><dd class="NoCheckData"><p>ハイペースが予想されます...</p>
          <div class="FreemiumDummy01"><img src="comment_dummy.png"></div></dd></dl></section>
      </div>
      <table class="PredictRap_Table"><thead><tr><th>馬番</th><th>馬名</th><th>前半3F</th><th>後半3F</th></tr></thead><tbody>
        <tr><td>1</td><td>Horse1</td><td>34.3</td><td>36.3</td></tr>
        <tr><td><img src="table_dummy.png"></td><td></td><td></td><td></td></tr>
      </tbody></table>
    </section>
    <div class="AiTenkaiBlock02"><ul id="CornerSwitch"><li><a id="Corner01"></a></li>
      <li><a id="Corner02"></a></li><li class="Active"><a id="Corner03"></a></li></ul>
      <div class="DevelopImg01{extra_bias}"><div class="DevelopBiasTxt"><span></span></div>
        <div class="DevelopImgWrap">
          <span class="HorseIcon" id="Horse1" style="top:-4%;left:0%"><span class="SpeedUp_03"></span></span>
          <span class="HorseIcon" id="Horse2" style="top:12%;left:50%"><span></span></span>
          <span class="HorseIcon" id="Horse3" style="top:30%;left:100%"><span class="SpeedDown_01"></span></span>
        </div></div>
    </div>
    <script>function updateHorsePosition() {{
      var checkbox1Checked=false; var checkbox2Checked=false;
      if (!checkbox1Checked && !checkbox2Checked) {{ switch (cornerCheck) {{
        case 'Corner01':
          // $("#Horse14").css({{ 'top':'-4%', 'left':'0%', }}).children('span').remove();
          $("#Horse1").css({{ 'top':'-4%', 'left':'0%', }}).children('span').remove();
          $("#Horse2").css({{ 'top':'12%', 'left':'40%', }}).children('span').remove();
          $("#Horse3").css({{ 'top':'30%', 'left':'100%', }}).children('span').remove(); break;
        case 'Corner02':
          $("#Horse1").css({{ 'top':'-4%', 'left':'10%', }}).children('span').remove();
          $("#Horse2").css({{ 'top':'12%', 'left':'50%', }}).children('span').remove();
          $("#Horse3").css({{ 'top':'30%', 'left':'100%', }}).children('span').remove(); break;
        case 'Corner03':
          $("#Horse1").css({{ 'top':'-4%', 'left':'0%', }}).append('<span class="SpeedUp_03"></span>');
          $("#Horse2").css({{ 'top':'12%', 'left':'50%', }}).append('<span class=""></span>');
          $("#Horse3").css({{ 'top':'30%', 'left':'100%', }}).append('<span class="SpeedDown_01"></span>'); break;
      }} }} else if (checkbox1Checked) {{}}
    }}
    // コーナーのクリックイベント
    </script>
    <section class="PositionMapBlock"><dl class="PositionMapImg"><dt>中目有利</dt><dd>
      <ul class="PositionMarkList">
        <li><div><span>33%</span></div><div><span>80%</span></div><div><span>0%</span></div></li>
        <li><div><span>13%</span></div><div><span>17%</span></div><div><span>0%</span></div></li>
        <li><div><span>5%</span></div><div><span>14%</span></div><div><span>0%</span></div></li>
      </ul></dd></dl>
      <div class="PositionPickupHorseWrap"><ul><li><span class="Umaban_Num">1</span>
        <a href="https://db.netkeiba.com/horse/1/">Horse1</a></li></ul><div class="DummyBox02"></div></div>
    </section>
    <table class="Race_HaronTime"><tr class="Header"><th>200m</th><th>400m</th></tr>
      <tr class="HaronTime"><td><img src="pase_dummy.png"></td><td><img src="pase_dummy.png"></td></tr></table>
    <table class="AnaBestTable"><tr><th><div class="PickupHorseTableTitle">騎手</div></th><td>
      <a><div class="AnaBest_HorseBox"><div class="Kyaku_Type_box"><span class="Kyaku_Type_Num">1</span>
      <span class="UmaName">坂井瑠</span></div><span>該当コースランキングへ</span></div></a></td></tr></table>
    </body></html>"""


def jockey_html(*, mode: str = "jra", race_id: str = RACE_ID, mobile: bool = False) -> str:
    if mode == "nar":
        host = "nar.sp" if mobile else "nar"
    else:
        host = "race.sp" if mobile else "race"
    return f"""<!doctype html><html><head>
    <link rel="canonical" href="https://{host}.netkeiba.com/race/data_list.html?race_id={race_id}&amp;mode=courseanalysis&amp;cid=2">
    <title>テストレース 大井ダ1600mが得意な騎手 データ分析</title></head><body class="race_data_list">
    <table id="table_sort_back"><thead><tr class="Header">
      <th>馬<br>番</th><th>印</th><th>項目</th><th>1着</th><th>2着</th><th>3着</th><th>4着以下</th>
      <th>出走<br>回数</th><th>勝率</th><th>連対率</th><th>複勝率</th><th>単勝回収率</th><th>複勝回収率</th><th>馬名</th>
    </tr></thead><tbody>
      <tr class="HorseList"><td>1</td><td></td><td class="DataTitle_Cell">矢野貴之</td><td>132</td><td>81</td><td>54</td><td>192</td><td>459</td><td>28%</td><td>46%</td><td>58%</td><td>95%</td><td>83%</td><td>Horse1</td></tr>
      <tr class="HorseList"><td>2</td><td></td><td class="DataTitle_Cell">御神本訓史</td><td>42</td><td>27</td><td>15</td><td>100</td><td>184</td><td>22%</td><td>37%</td><td>45%</td><td>61%</td><td>63%</td><td>Horse2</td></tr>
    </tbody></table></body></html>"""


def market_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "馬番": 1,
                "馬名": "Horse1",
                "raw_score": 90.0,
                "_ver3_ability_core": 90.0,
                "オッズ": 11.4,
                "脚質": "差",
                "3走前": 60,
                "2走前": 65,
                "前走": 70,
            },
            {
                "馬番": 2,
                "馬名": "Horse2",
                "raw_score": 87.0,
                "_ver3_ability_core": 87.0,
                "オッズ": 2.5,
                "脚質": "先",
                "3走前": 62,
                "2走前": 64,
                "前走": 66,
            },
        ]
    )


def test_jra_saved_newspaper_extracts_only_explicit_course_facts() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html())
    assert parsed.detected_mode == "jra"
    assert parsed.course_condition == "新潟1200m芝 Aコース"
    assert parsed.pace == "H"
    assert parsed.position_coverage == {"start": 3, "corner3": 3, "corner4": 3}
    assert parsed.four_corner_place_rates["front"] == {"inner": 33, "middle": 80, "outer": 0}
    assert parsed.favorable_position_label == "中目有利"


def test_position_coordinates_are_converted_by_relative_horizontal_order() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html())
    assert parsed.position_categories["start"] == {1: "逃げ", 2: "先団", 3: "中団"}
    assert parsed.position_categories["corner4"] == {1: "逃げ", 2: "先団", 3: "中団"}


def test_jockey_cid2_table_parses_real_rate_columns_for_jra_and_nar() -> None:
    for mode in ("jra", "nar"):
        for mobile in (False, True):
            parsed = parse_netkeiba_jockey_course_stats(jockey_html(mode=mode, mobile=mobile), expected_mode=mode)
            assert parsed.source_status == "取得"
            assert parsed.course_condition == "大井ダ1600m"
            assert parsed.horses[1] == {
                "horse_number": 1,
                "horse_name": "Horse1",
                "jockey_name": "矢野貴之",
                "starts": 459,
                "win_rate": 28.0,
                "quinella_rate": 46.0,
                "place_rate": 58.0,
            }


def test_style_cid1_is_not_accepted_as_jockey_stats() -> None:
    parsed = parse_netkeiba_jockey_course_stats(jockey_html().replace("cid=2", "cid=1"))
    assert parsed.source_status == "騎手コース成績HTMLではない"
    assert parsed.horses == {}


def test_real_tanabata_saved_html_regression() -> None:
    fixture = Path(__file__).parent / "fixtures" / "tanabata_20260712" / "keiba_data-61.html"
    parsed = parse_netkeiba_course_materials(fixture.read_text(encoding="utf-8"), expected_mode="jra")
    assert parsed.race_id == "202603020611"
    assert parsed.course_condition == "福島2000m芝 Bコース"
    assert parsed.pace == "M"
    assert parsed.horse_count == 16
    assert parsed.position_coverage == {"start": 16, "corner3": 16, "corner4": 16}
    assert parsed.favorable_position_label == "フラット"
    assert parsed.favorable_horses[0]["horse_number"] == 13
    assert parsed.favorable_horses_complete is False
    assert parsed.predicted_3f_coverage == 1
    assert parsed.predicted_3f_usable is False
    assert parsed.track_bias_status == "HTML内に実値なし"
    assert parsed.lap_prediction_status == "HTML内に実値なし"


def test_commented_stale_position_is_not_parsed() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html(mode="nar"))
    assert parsed.detected_mode == "nar"
    assert parsed.horse_count == 3
    assert 14 not in parsed.positions["start"]
    assert parsed.position_coverage["start"] == 3


def test_dummy_and_partial_values_are_not_promoted_to_real_data() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html())
    assert parsed.ai_opinion_complete is False
    assert parsed.predicted_3f_coverage == 1
    assert parsed.predicted_3f_usable is False
    assert parsed.favorable_horses_complete is False
    assert parsed.track_bias_status == "HTML内に実値なし"
    assert parsed.lap_prediction_status == "HTML内に実値なし"


def test_bias_pattern_code_is_not_given_an_invented_meaning() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html(mode="nar"))
    assert parsed.track_bias_code == "BiasPattern222"
    assert parsed.track_bias_status == "コードのみ・意味未確定"
    assert parsed.track_bias_text == []


def test_pc_and_mobile_saved_html_use_the_same_parser_contract() -> None:
    pc = parse_netkeiba_course_materials(newspaper_html())
    mobile = parse_netkeiba_course_materials(newspaper_html(mobile=True))
    for name in ("detected_mode", "course_condition", "pace", "position_coverage", "four_corner_place_rates"):
        assert getattr(pc, name) == getattr(mobile, name)


def test_mode_mismatch_is_explicit_and_not_parsed() -> None:
    parsed = parse_netkeiba_course_materials(newspaper_html(mode="nar"), expected_mode="jra")
    assert parsed.source_status == "JRA/NAR不一致"
    assert parsed.positions == {}


def test_non_newspaper_or_missing_area_stays_missing() -> None:
    parsed = parse_netkeiba_course_materials(
        f'<link rel="canonical" href="https://race.netkeiba.com/race/speed.html?race_id={RACE_ID}">'
    )
    assert parsed.source_status == "AI展開予測がHTML内に存在しない"
    assert parsed.course_condition == ""


def test_attachment_changes_no_existing_ability_column() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    before = result.overall_table.copy(deep=True)
    attach_course_materials_to_result(result, {"newspaper": newspaper_html()})
    pd.testing.assert_frame_equal(result.overall_table[before.columns], before)
    assert result.overall_table.loc[0, "_netkeiba_pace"] == "H"
    assert result.overall_table.loc[0, "_position_favorable_horse"] is True


def test_optional_jockey_html_attaches_stats_without_touching_ability() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    before = result.overall_table.copy(deep=True)
    attach_course_materials_to_result(
        result,
        {"newspaper": newspaper_html(), "jockey": jockey_html()},
    )
    pd.testing.assert_frame_equal(result.overall_table[before.columns], before)
    assert result.overall_table.loc[0, "_jockey_course_starts"] == 459
    assert result.overall_table.loc[0, "_jockey_course_place_rate"] == 58.0
    assert result.overall_table.loc[1, "_jockey_course_starts"] == 184
    assert result.overall_table.loc[1, "_jockey_course_place_rate"] == 45.0
    assert result.overall_table.loc[0, "_estimated_position_path"] == "逃げ → 逃げ → 逃げ"


def test_jra_all_optional_html_bundle_with_jockey_stats_still_predicts_market_view() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    html_files = {
        "speed": f'<html><head><link rel="canonical" href="https://race.netkeiba.com/race/speed.html?race_id={RACE_ID}"></head></html>',
        "newspaper": newspaper_html(),
        "style": f'<html><head><link rel="canonical" href="https://race.netkeiba.com/race/data_list.html?race_id={RACE_ID}&amp;mode=courseanalysis&amp;cid=1"></head></html>',
        "jockey": jockey_html(),
        "oikiri": f'<html><head><link rel="canonical" href="https://race.netkeiba.com/race/oikiri.html?race_id={RACE_ID}"></head></html>',
    }
    attach_course_materials_to_result(result, html_files)
    evaluated = evaluate_market_table(result.overall_table, "jra", {"race_id": RACE_ID})
    assert evaluated["jockey_course_stats_market"].str.contains("28%-46%-58%", regex=False).any()
    assert evaluated["current_evaluation_rank"].notna().all()
    assert evaluated["ai_current_mark"].astype(str).str.len().gt(0).any()


def test_optional_jockey_html_partial_missing_rates_only_leaves_missing_horse_empty() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    partial = jockey_html().replace(
        "<td>184</td><td>22%</td><td>37%</td><td>45%</td>",
        "<td></td><td>22%</td><td>37%</td><td></td>",
    )
    attach_course_materials_to_result(result, {"newspaper": newspaper_html(), "jockey": partial})
    assert result.overall_table.loc[0, "_jockey_course_starts"] == 459
    assert result.overall_table.loc[0, "_jockey_course_place_rate"] == 58.0
    assert pd.isna(result.overall_table.loc[1, "_jockey_course_starts"])
    assert pd.isna(result.overall_table.loc[1, "_jockey_course_place_rate"])


def test_optional_jockey_html_zero_matches_is_reference_only_and_preserves_ability() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    no_match = jockey_html().replace(
        '<tr class="HorseList"><td>1</td>',
        '<tr class="HorseList"><td>7</td>',
        1,
    ).replace(
        '<tr class="HorseList"><td>2</td>',
        '<tr class="HorseList"><td>8</td>',
        1,
    )
    before = evaluate_market_table(source, "jra", {"race_id": RACE_ID})
    attach_course_materials_to_result(result, {"newspaper": newspaper_html(), "jockey": no_match})
    after = evaluate_market_table(result.overall_table, "jra", {"race_id": RACE_ID})
    assert result.overall_table["_jockey_course_place_rate"].isna().all()
    for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
        assert before[column].tolist() == after[column].tolist()


def test_missing_jockey_html_is_not_an_error_and_leaves_rates_empty() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="nar",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    attach_course_materials_to_result(result, {"newspaper": newspaper_html(mode="nar")})
    assert result.debug_info["jockey_course_materials"]["source_status"] == "html内に存在しない"
    assert result.overall_table["_jockey_course_place_rate"].isna().all()


def test_attach_course_materials_skips_empty_tables_without_jockey_dtype_errors() -> None:
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=pd.DataFrame({"馬番": pd.Series(dtype="int64")}),
        horse_evaluation=pd.DataFrame({"馬番": pd.Series(dtype="int64")}),
    )
    attach_course_materials_to_result(result, {"newspaper": newspaper_html(), "jockey": jockey_html()})
    assert result.overall_table.empty
    assert list(result.overall_table.columns) == ["馬番"]


def test_jockey_html_presence_does_not_change_ver3_ability_rank_or_band() -> None:
    source = market_rows()
    without = PredictionResult(
        race_mode="jra",
        race_info={"race_id": RACE_ID},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    with_jockey = copy.deepcopy(without)
    attach_course_materials_to_result(without, {"newspaper": newspaper_html()})
    attach_course_materials_to_result(
        with_jockey,
        {"newspaper": newspaper_html(), "jockey": jockey_html()},
    )
    left = evaluate_market_table(without.overall_table, "jra", {"race_id": RACE_ID})
    right = evaluate_market_table(with_jockey.overall_table, "jra", {"race_id": RACE_ID})
    for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
        assert left[column].tolist() == right[column].tolist()
    assert right.loc[0, "jockey_course_stats_market"].endswith("28%-46%-58%")


def test_race_id_mismatch_is_explicit_and_does_not_attach_rows() -> None:
    source = market_rows()
    result = PredictionResult(
        race_mode="jra",
        race_info={"race_id": "999999999999"},
        overall_table=source.copy(deep=True),
        horse_evaluation=source.copy(deep=True),
    )
    attach_course_materials_to_result(result, {"newspaper": newspaper_html()})
    assert result.debug_info["course_materials"]["source_status"] == "race_id不一致"
    assert "_netkeiba_pace" not in result.overall_table.columns


def test_course_and_pace_changes_do_not_change_core_rank_or_band() -> None:
    first = market_rows()
    second = first.copy(deep=True)
    first["_course_context_status"] = "取得"
    first["_netkeiba_pace"] = "H"
    first["_favorable_position_label"] = "前有利"
    second["_course_context_status"] = "取得"
    second["_netkeiba_pace"] = "S"
    second["_favorable_position_label"] = "後有利"
    left = evaluate_market_table(first, "jra", {"race_id": RACE_ID})
    right = evaluate_market_table(second, "jra", {"race_id": RACE_ID})
    for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
        assert left[column].tolist() == right[column].tolist()


def test_same_scenario_emits_only_one_grouped_course_material() -> None:
    table = market_rows().iloc[[0]].copy()
    table["_course_context_status"] = "取得"
    table["_netkeiba_pace"] = "H"
    table["_favorable_position_label"] = "前有利"
    table["_position_favorable_horse"] = True
    table["_estimated_position_corner4"] = "top=-4%, left=0%"
    result = evaluate_market_table(table, "jra", {"race_id": RACE_ID})
    materials = result.loc[result.index[0], "positive_materials"]
    assert sum(text.startswith("展開/コース：") for text in materials) == 1
    assert result.iloc[0]["course_development_reason"].startswith("推定有利馬")


def test_jockey_rate_and_jockey_name_changes_do_not_change_ability() -> None:
    base = market_rows()
    changed = copy.deepcopy(base)
    changed["騎手"] = ["A", "B"]
    changed["_jockey_course_win_rate"] = [22, 2]
    changed["_jockey_course_quinella_rate"] = [37, 8]
    changed["_jockey_course_place_rate"] = [45, 12]
    changed["_jockey_course_starts"] = [100, 100]
    left = evaluate_market_table(base, "jra", {"race_id": RACE_ID})
    right = evaluate_market_table(changed, "jra", {"race_id": RACE_ID})
    for column in ("market_ability_score", "market_ability_rank", "ability_band_v2"):
        assert left[column].tolist() == right[column].tolist()
    assert right["jockey_course_mark_market"].tolist() == ["○", "△"]


def test_small_jockey_sample_is_reference_only_not_strong_material() -> None:
    table = market_rows().iloc[[0]].copy()
    table["_jockey_course_win_rate"] = 40
    table["_jockey_course_quinella_rate"] = 50
    table["_jockey_course_place_rate"] = 70
    table["_jockey_course_starts"] = 5
    result = evaluate_market_table(table, "nar", {"race_id": RACE_ID})
    assert result.iloc[0]["jockey_course_mark_market"] == "参考"
    assert "サンプル不足" in result.iloc[0]["jockey_course_sample_market"]
    assert not any(text.startswith("騎手：") for text in result.iloc[0]["positive_materials"])


def test_ranking_without_rates_is_reference_only() -> None:
    table = market_rows().iloc[[0]].copy()
    table["_jockey_course_rank"] = 1
    result = evaluate_market_table(table, "jra", {"race_id": RACE_ID})
    assert result.iloc[0]["jockey_course_mark_market"] == "参考"
    assert "率・件数なし" in result.iloc[0]["jockey_course_stats_market"]
    assert not any(text.startswith("騎手：") for text in result.iloc[0]["positive_materials"])


def test_missing_course_and_jockey_data_still_produces_market_view() -> None:
    result = evaluate_market_table(market_rows(), "nar", {"race_id": RACE_ID})
    assert len(result) == 2
    assert set(result["ability_band_v2"]) == {"A"}
    assert set(result["jockey_course_stats_market"]) == {"騎手成績なし"}
    assert set(result["jockey_course_sample_market"]) == {"参考値なし"}
    assert result["course_development_source"].eq("既存の全頭脚質構成").all()
