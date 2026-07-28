from __future__ import annotations

import json
import unittest

import pandas as pd

from core.nar_courseanalysis_parser import parse_courseanalysis_html
from core.nar_newspaper_parser import parse_nar_newspaper_html
from core.nar_json_input import (
    NarJsonDataError,
    build_nar_prediction_inputs_from_uploads,
    classify_nar_uploaded_files,
    parse_horse_weight,
    parse_index,
    parse_speed_index,
)


def course_html(
    labels: list[str],
    race_id: str = "202644072106",
    horse_styles: dict[str, str] | None = None,
) -> str:
    label_text = ",".join(json.dumps(label, ensure_ascii=False) for label in labels)
    win = ",".join(str(value) for value in range(15, 15 - len(labels), -1))
    second = ",".join(str(value) for value in range(13, 13 - len(labels), -1))
    third = ",".join(str(value) for value in range(10, 10 - len(labels), -1))
    outside = ",".join(str(value) for value in range(62, 62 + len(labels)))
    horse_table = ""
    if horse_styles:
        rows = []
        names = {"1": "テストホースA", "2": "テストホースB"}
        for number, style in horse_styles.items():
            rows.append(
                f"""
                <tr class="HorseList">
                  <td>{number}</td>
                  <td class="Horse_Info"><a>{names.get(number, "テストホース")}</a></td>
                  <td class="DataTitle_Cell">{style}</td>
                </tr>
                """
            )
        horse_table = f'<table id="table_sort_back" class="Data01_Table"><tbody>{"".join(rows)}</tbody></table>'
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>C2九十 コース分析</title>
        <link rel="canonical" href="https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&amp;mode=courseanalysis&amp;cid=1">
        <meta property="og:url" content="https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&amp;mode=courseanalysis&amp;cid=1">
      </head>
      <body>
        <h1 class="RaceName">C2九十</h1>
        <div class="RaceNum">6R</div>
        <div class="RaceData01">17:30発走 / ダ1600m (右) / 天候:晴 / 馬場:良</div>
        <div class="RaceData02">6回 大井 2日目 サラ系一般 C2</div>
        <div class="DataGraphWrap1"><canvas id="score1"></canvas></div>
        {horse_table}
        <script>
          var ctx = document.getElementById("score1");
          var myChart = new Chart(ctx, {{
            type: "bar",
            data: {{
              labels: [{label_text}],
              datasets: [
                {{ label: "1着", data: [{win}] }},
                {{ label: "2着", data: [{second}] }},
                {{ label: "3着", data: [{third}] }},
                {{ label: "着外率", data: [{outside}] }}
              ]
            }}
          }});
        </script>
      </body>
    </html>
    """


def base_json(data_type: str, race_id: str = "202644072106") -> dict:
    horses = [
        {
            "frame_number": "1",
            "horse_number": "1",
            "horse_id": "h1",
            "horse_name": "テストホースA",
            "sex_age": "牡4",
            "weight": "56",
            "jockey": "騎手A",
            "horse_weight": "501(+31)",
            "odds": "3.4",
            "popularity": "1",
            "style": "先",
        },
        {
            "frame_number": "2",
            "horse_number": "2",
            "horse_id": "h2",
            "horse_name": "テストホースB",
            "sex_age": "牝5",
            "weight": "54",
            "jockey": "騎手B",
            "horse_weight": "478(0)",
            "odds": "9.8",
            "popularity": "4",
            "style": "差",
        },
    ]
    if data_type == "speed":
        horses = [
            {
                "horse_number": horse["horse_number"],
                "horse_id": horse["horse_id"],
                "horse_name": horse["horse_name"],
                "max": "60*",
                "avg5": "53*",
                "distance": "-5",
                "course": "未",
                "race3": "48",
                "race2": "-",
                "race1": "51",
            }
            for horse in horses
        ]
    return {
        "race_id": race_id,
        "data_type": data_type,
        "race": {"race_name": "C2九十", "race_data_1": "17:30発走 / ダ1600m"},
        "horses": horses,
    }


def upload(name: str, payload: str | dict) -> tuple[str, bytes]:
    if isinstance(payload, dict):
        payload = json.dumps(payload, ensure_ascii=False)
    return name, payload.encode("utf-8")


def newspaper_html(race_id: str = "202644072106") -> str:
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>C2九十 競馬新聞 地方競馬</title>
        <link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
        <meta property="og:url" content="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
      </head>
      <body>
        <h1 class="RaceName">C2九十</h1>
        <div class="RaceData01">17:30発走 / ダ1600m (右)</div>
        <table class="RaceNewspaper">
          <tbody>
            <tr class="HorseList">
              <td class="Waku">1</td>
              <td class="Umaban">1</td>
              <td class="Horse_Info"><a href="https://nar.netkeiba.com/horse/h1">テストホースA</a></td>
              <td class="SexAge">牡4</td>
              <td class="Weight">56</td>
              <td class="Jockey"><a href="/jockey/j1">騎手A</a></td>
              <td class="Trainer"><a href="/trainer/t1">大井・調教師A</a></td>
              <td class="DataTitle_Cell">先</td>
              <td class="HorseWeight">501(+31)</td>
              <td class="Ninki">1</td>
              <td class="Odds">3.4</td>
              <td class="Comment">順調に使えています</td>
              <td class="Pace">前めで運べる</td>
              <td class="AiMark">◎</td>
              <td>前半3F:35.1 後半3F:38.2</td>
            </tr>
            <tr class="HorseList">
              <td class="Waku">2</td>
              <td class="Umaban">2</td>
              <td class="Horse_Info"><a href="https://nar.netkeiba.com/horse/h2">テストホースB</a></td>
              <td class="SexAge">牝5</td>
              <td class="Weight">54</td>
              <td class="Jockey"><a href="/jockey/j2">騎手B</a></td>
              <td class="Trainer"><a href="/trainer/t2">船橋・調教師B</a></td>
              <td class="DataTitle_Cell">差</td>
              <td class="HorseWeight">478(0)</td>
              <td class="Ninki">4</td>
              <td class="Odds">9.8</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """


def newspaper_vertical_html(race_id: str = "202644072106") -> str:
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>C2九十 競馬新聞 地方競馬</title>
        <link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
        <meta property="og:url" content="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
      </head>
      <body>
        <h1 class="RaceName">C2九十</h1>
        <div class="RaceData01">17:30発走 / ダ1600m (右)</div>
        <div class="HorseList_Wrapper">
          <dl class="HorseList" data-index="0" id="past_tr_1">
            <dt class="Waku1 orderfix">1</dt>
            <dt class="Waku Waku_Horse orderfix">1</dt>
            <dt class="HorseName Waku1 HorseListSort orderfix">
              <span class="Vertical"><a href="https://db.netkeiba.com/horse/h1/">テストホースA</a></span>
            </dt>
            <dt class="Horse_Select orderfix"><select id="past_mark_1"><option>--</option></select></dt>
            <dt class="Horse_Info orderfix">
              <dl class="fc">
                <dt class="Horse01 fc">父A</dt>
                <dt class="Horse02"><a href="https://db.netkeiba.com/horse/h1/">テストホースA</a></dt>
                <dt class="Horse05"><a href="https://db.netkeiba.com/trainer/result/recent/t1/">大井・調教師A</a></dt>
                <dt class="Horse06 fc"><div class="Type Type02"><span>先</span></div> 中2週</dt>
                <dt class="Horse07 fc">
                  <div class="Weight UpdateOdds"><span>501kg <span>(+31)</span></span></div>
                  <div class="Popular UpdateOdds"><span class="OddsDataTxt transition-color">3.4</span><virtul>(<span>1</span><span>人気)</span></virtul></div>
                </dt>
              </dl>
            </dt>
            <dd class="Jockey HorseListSort order2">
              <span class="Barei">牡4 鹿</span>
              <a href="https://db.netkeiba.com/jockey/result/recent/j1/"><span><span class="Change">替</span>騎手A</span></a>
              <br><span>初騎乗</span><br><span> ▲56.0 </span>
            </dd>
          </dl>
          <dl class="HorseList" data-index="1" id="past_tr_2">
            <dt class="Waku2 orderfix">2</dt>
            <dt class="Waku Waku_Horse orderfix">2</dt>
            <dt class="HorseName Waku2 HorseListSort orderfix">
              <span class="Vertical"><a href="https://db.netkeiba.com/horse/h2/">テストホースB</a></span>
            </dt>
            <dt class="Horse_Info orderfix">
              <dl class="fc">
                <dt class="Horse02"><a href="https://db.netkeiba.com/horse/h2/">テストホースB</a></dt>
                <dt class="Horse05"><a href="https://db.netkeiba.com/trainer/result/recent/t2/">船橋・調教師B</a></dt>
                <dt class="Horse06 fc"><div class="Type Type03"><span>差</span></div> 中5週</dt>
                <dt class="Horse07 fc">
                  <div class="Weight UpdateOdds"><span>478kg <span>(0)</span></span></div>
                  <div class="Popular UpdateOdds"><span class="OddsDataTxt transition-color">9.8</span><virtul>(<span>4</span><span>人気)</span></virtul></div>
                </dt>
              </dl>
            </dt>
            <dd class="Jockey HorseListSort order2">
              <span class="Barei">牝5 栗</span>
              <a href="https://db.netkeiba.com/jockey/result/recent/j2/"><span>騎手B</span></a>
              <br><span>0-1-0-2</span><br><span> 54.0 </span>
            </dd>
          </dl>
        </div>
      </body>
    </html>
    """


class NarCourseAnalysisInputTest(unittest.TestCase):
    def test_parse_courseanalysis_html_three_labels(self) -> None:
        data = parse_courseanalysis_html(course_html(["先", "差", "追"]))
        self.assertEqual(data["race_id"], "202644072106")
        self.assertEqual([item["style"] for item in data["running_styles"]], ["先", "差", "追"])
        first = data["running_styles"][0]
        self.assertEqual(first["win_rate"], 15)
        self.assertEqual(first["quinella_rate"], 28)
        self.assertEqual(first["place_rate"], 38)
        self.assertEqual(first["outside_rate"], 62)

    def test_parse_courseanalysis_html_four_labels(self) -> None:
        data = parse_courseanalysis_html(course_html(["逃", "先", "差", "追"]))
        self.assertEqual(len(data["running_styles"]), 4)
        self.assertEqual(data["running_styles"][3]["style"], "追")

    def test_parse_courseanalysis_html_keeps_horse_styles_separate(self) -> None:
        data = parse_courseanalysis_html(course_html(["先", "差", "追"], horse_styles={"1": "追", "2": "先"}))
        self.assertEqual([item["style"] for item in data["running_styles"]], ["先", "差", "追"])
        self.assertEqual(
            [(item["horse_number"], item["running_style"]) for item in data["horse_running_styles"]],
            [("1", "追"), ("2", "先")],
        )

    def test_classify_mixed_json_and_courseanalysis_html(self) -> None:
        classified = classify_nar_uploaded_files(
            [
                upload("same.html", base_json("entry")),
                upload("same.html", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"])),
            ]
        )
        self.assertEqual(set(classified), {"entry", "speed", "courseanalysis"})
        self.assertEqual(classified["courseanalysis"]["running_styles"][1]["style"], "差")

    def test_build_inputs_accepts_courseanalysis_html(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.html", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"])),
            ]
        )
        self.assertEqual(package.race_id, "202644072106")
        self.assertEqual(package.entry_count, 2)
        self.assertEqual(package.speed_count, 2)
        self.assertEqual(package.running_styles, ("先", "差", "追"))
        self.assertEqual(package.horse_style_count, 2)
        self.assertIn('<td class="Speed_List03 MaxIndex"><a>60</a></td>', package.html_files["speed"])
        self.assertIn('<td class="Speed_List04 Avg5Index">53</td>', package.html_files["speed"])
        self.assertIn('<td class="DataTitle_Cell">先</td>', package.html_files["style"])
        self.assertIn("<td>15</td><td>28</td><td>38</td>", package.html_files["style"])

    def test_previous_weight_and_jockey_are_carried_as_display_only_attributes(self) -> None:
        entry = base_json("entry")
        entry["horses"][0]["previous_weight"] = "55.0"
        entry["horses"][0]["previous_jockey"] = "前走騎手A"
        entry["horses"][1]["前走斤量"] = "54.0"
        entry["horses"][1]["前走騎手"] = "騎手B"

        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", entry),
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"])),
            ]
        )

        speed_html = package.html_files["speed"]
        self.assertIn('data-display-previous-load-weight="55.0"', speed_html)
        self.assertIn('data-display-load-weight-change="1.0"', speed_html)
        self.assertIn('data-display-previous-jockey="前走騎手A"', speed_html)
        self.assertIn('data-display-jockey-changed="True"', speed_html)
        self.assertIn('data-display-jockey-changed="False"', speed_html)

    def test_parse_nar_newspaper_html_extracts_entry_fields(self) -> None:
        data = parse_nar_newspaper_html(newspaper_html())
        self.assertEqual(data["race_id"], "202644072106")
        self.assertEqual(len(data["horses"]), 2)
        first = data["horses"][0]
        self.assertEqual(first["horse_number"], "1")
        self.assertEqual(first["horse_name"], "テストホースA")
        self.assertEqual(first["horse_id"], "h1")
        self.assertEqual(first["frame_number"], "1")
        self.assertEqual(first["running_style"], "先")
        self.assertEqual(first["jockey"], "騎手A")
        self.assertEqual(first["weight"], "56")
        self.assertEqual(first["trainer"], "調教師A")
        self.assertEqual(first["affiliation"], "大井")
        self.assertEqual(first["horse_weight"], "501(+31)")
        self.assertEqual(first["popularity"], "1")
        self.assertEqual(first["odds"], "3.4")
        self.assertEqual(first["ai_mark"], "◎")
        self.assertEqual(first["early_3f"], "35.1")
        self.assertEqual(first["late_3f"], "38.2")

    def test_parse_nar_newspaper_vertical_html_extracts_all_horses(self) -> None:
        data = parse_nar_newspaper_html(newspaper_vertical_html())
        self.assertEqual(data["race_id"], "202644072106")
        self.assertEqual(len(data["horses"]), 2)
        first = data["horses"][0]
        self.assertEqual(first["horse_number"], "1")
        self.assertEqual(first["horse_name"], "テストホースA")
        self.assertEqual(first["horse_id"], "h1")
        self.assertEqual(first["frame_number"], "1")
        self.assertEqual(first["running_style"], "先")
        self.assertEqual(first["race_interval"], "中2週")
        self.assertEqual(first["jockey"], "騎手A")
        self.assertEqual(first["sex_age"], "牡4")
        self.assertEqual(first["weight"], "56.0")
        self.assertEqual(first["trainer"], "調教師A")
        self.assertEqual(first["affiliation"], "大井")
        self.assertEqual(first["horse_weight"], "501(+31)")
        self.assertEqual(first["popularity"], "1")
        self.assertEqual(first["odds"], "3.4")
        second = data["horses"][1]
        self.assertEqual(second["running_style"], "差")
        self.assertEqual(second["horse_weight"], "478(0)")

    def test_newspaper_html_can_replace_entry_json(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"])),
                upload("newspaper.html", newspaper_html()),
            ]
        )
        self.assertEqual(package.entry_source, "nar_newspaper_html")
        self.assertEqual(package.entry_count, 2)
        self.assertEqual(package.horse_style_count, 2)
        self.assertIn("テストホースA", package.html_files["shutuba"])
        self.assertIn('<td class="DataTitle_Cell">先</td>', package.html_files["style"])

    def test_horse_styles_from_courseanalysis_html_are_used_when_json_has_none(self) -> None:
        entry = base_json("entry")
        for horse in entry["horses"]:
            horse.pop("style", None)
            horse.pop("running_style", None)
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.html", entry),
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"], horse_styles={"1": "追", "2": "先"})),
            ]
        )
        self.assertEqual(package.horse_style_count, 2)
        self.assertIn('<td class="DataTitle_Cell">追</td>', package.html_files["style"])
        self.assertIn("<td>13</td><td>24</td><td>32</td>", package.html_files["style"])

    def test_race_id_mismatch_raises(self) -> None:
        with self.assertRaises(NarJsonDataError):
            build_nar_prediction_inputs_from_uploads(
                [
                    upload("entry.json", base_json("entry", "202644072106")),
                    upload("speed.json", base_json("speed", "202644072107")),
                    upload("courseanalysis.html", course_html(["先", "差", "追"], "202644072106")),
                ]
            )

    def test_parse_index_and_horse_weight(self) -> None:
        self.assertEqual(parse_index("53*"), 53)
        self.assertEqual(parse_index("-5"), -5)
        self.assertIsNone(parse_index("未"))
        self.assertIsNone(parse_index(""))
        self.assertIsNone(parse_speed_index("100"))
        self.assertEqual(parse_speed_index("-5"), -5)
        self.assertIsNone(parse_speed_index(pd.NA))
        self.assertEqual(parse_horse_weight("501(+31)"), (501, 31))
        self.assertEqual(parse_horse_weight("478(0)"), (478, 0))
        self.assertEqual(parse_horse_weight(pd.NA), (None, None))


if __name__ == "__main__":
    unittest.main()
