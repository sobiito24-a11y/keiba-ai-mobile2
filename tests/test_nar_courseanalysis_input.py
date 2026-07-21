from __future__ import annotations

import json
import unittest

from core.nar_courseanalysis_parser import parse_courseanalysis_html
from core.nar_json_input import (
    NarJsonDataError,
    build_nar_prediction_inputs_from_uploads,
    classify_nar_uploaded_files,
    parse_horse_weight,
    parse_index,
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
        self.assertIn('<td class="DataTitle_Cell">先</td>', package.html_files["style"])
        self.assertIn("<td>15</td><td>28</td><td>38</td>", package.html_files["style"])

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
        self.assertEqual(parse_horse_weight("501(+31)"), (501, 31))
        self.assertEqual(parse_horse_weight("478(0)"), (478, 0))


if __name__ == "__main__":
    unittest.main()
