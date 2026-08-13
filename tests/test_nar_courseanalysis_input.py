from __future__ import annotations

import json
import unittest

import pandas as pd

from core.html_classifier import classify_html, required_kinds
from core.audit_features import add_audit_evaluation_columns, build_audit_export_table
from core.nar_courseanalysis_parser import parse_courseanalysis_html
from core.nar_newspaper_parser import parse_nar_newspaper_html
from core.nar_predictor import predict_nar
from core.nar_json_input import (
    NarJsonDataError,
    build_nar_prediction_inputs_from_uploads,
    classify_nar_uploaded_files,
    parse_horse_weight,
    parse_index,
    parse_speed_index,
)
from core.nar_notebook_logic import parse_nar_speed_table, predict_nar_from_html


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


def jockey_course_html(race_id: str = "202644072106") -> str:
    return f"""<!doctype html><html><head>
    <link rel="canonical" href="https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&amp;mode=courseanalysis&amp;cid=2">
    <title>大井ダ1600mが得意な騎手 データ分析</title></head>
    <body class="race_data_list"><table id="table_sort_back"><thead><tr class="Header">
    <th>馬番</th><th>印</th><th>項目</th><th>1着</th><th>2着</th><th>3着</th><th>4着以下</th>
    <th>出走回数</th><th>勝率</th><th>連対率</th><th>複勝率</th><th>単勝回収率</th><th>複勝回収率</th><th>馬名</th>
    </tr></thead><tbody><tr class="HorseList"><td>1</td><td></td><td>騎手A</td>
    <td>20</td><td>15</td><td>10</td><td>55</td><td>100</td><td>20%</td><td>35%</td><td>45%</td><td>80%</td><td>70%</td><td>テストホースA</td>
    </tr></tbody></table></body></html>"""


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


def spiritual_speed_json(race_id: str = "202635072803") -> dict:
    return {
        "race_id": race_id,
        "data_type": "speed",
        "race": {"race_name": "地方競馬", "race_data_1": "12:00発走 / ダ1400m"},
        "horses": [
            {
                "horse_number": "8",
                "horse_id": "h8",
                "horse_name": "スピリチュアル",
                "max": "60",
                "avg5": "55",
                "distance": "54",
                "course": "53",
                "race3": "52",
                "race2": "51",
                "race1": "50",
            }
        ],
    }


def three_horse_entry_json(race_id: str = "202644072106") -> dict:
    data = base_json("entry", race_id)
    data["horses"].append(
        {
            "frame_number": "3",
            "horse_number": "3",
            "horse_id": "h3",
            "horse_name": "テストホースC",
            "sex_age": "セ6",
            "weight": "57",
            "jockey": "騎手C",
            "horse_weight": "490(-2)",
            "odds": "18.0",
            "popularity": "7",
            "style": "追",
        }
    )
    return data


def three_horse_speed_json(race_id: str = "202644072106") -> dict:
    return {
        "race_id": race_id,
        "data_type": "speed",
        "race": {"race_name": "C2九十", "race_data_1": "17:30発走 / ダ1600m"},
        "horses": [
            {
                "horse_number": "1",
                "horse_id": "h1",
                "horse_name": "テストホースA",
                "max": "72*",
                "avg5": "61",
                "distance": "60",
                "course": "59",
                "race3": "58",
                "race3_venue": "大井",
                "race3_surface": "ダ",
                "race3_distance": "1600",
                "race3_turn": "右",
                "race2": "60",
                "race2_venue": "大井",
                "race2_surface": "ダ",
                "race2_distance": "1600",
                "race2_turn": "右",
                "race1": "62",
                "race1_venue": "船橋",
                "race1_surface": "ダ",
                "race1_distance": "1600",
                "race1_turn": "左",
            },
            {
                "horse_number": "2",
                "horse_id": "h2",
                "horse_name": "テストホースB",
                "max": "66",
                "avg5": "58",
                "distance": "57",
                "course": "56",
                "race3": "55",
                "race3_venue": "大井",
                "race3_surface": "ダ",
                "race3_distance": "1600",
                "race3_turn": "右",
                "race2": "58",
                "race2_venue": "大井",
                "race2_surface": "ダ",
                "race2_distance": "1200",
                "race2_turn": "右",
                "race1": "59",
                "race1_venue": "大井",
                "race1_surface": "ダ",
                "race1_distance": "1600",
                "race1_turn": "右",
            },
            {
                "horse_number": "3",
                "horse_id": "h3",
                "horse_name": "テストホースC",
                "max": "61",
                "avg5": "55",
                "distance": "54",
                "course": "53",
                "race3": "52",
                "race3_venue": "大井",
                "race3_surface": "ダ",
                "race3_distance": "1200",
                "race3_turn": "右",
                "race2": "54",
                "race2_venue": "船橋",
                "race2_surface": "ダ",
                "race2_distance": "1600",
                "race2_turn": "左",
                "race1": "56",
                "race1_venue": "船橋",
                "race1_surface": "ダ",
                "race1_distance": "1400",
                "race1_turn": "左",
            },
        ],
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
              <td class="PastRun">
                <ul>
                  <li class="PastRunItem">
                    <span class="Date">2026/07/01</span>
                    <span class="Place">大井</span>
                    <a href="https://nar.netkeiba.com/race/result.html?race_id=202644070101">前走A</a>
                    <span class="Finish">2着</span>
                    <span class="RaceClass">C1</span>
                    <span class="Jockey"><a href="/jockey/jp1">前走騎手A</a></span>
                    <span class="LoadWeight">55.0</span>
                    <span class="HorseWeight">500(+2)</span>
                  </li>
                  <li class="PastRunItem">
                    <span class="Date">2026/06/01</span>
                    <span class="Jockey"><a href="/jockey/old1">古い騎手</a></span>
                    <span class="LoadWeight">54.0</span>
                  </li>
                </ul>
              </td>
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
              <td class="PastRun">
                <li class="PastRunItem">
                  <span class="Date">2026/07/02</span>
                  <span class="Place">船橋</span>
                  <span class="Finish">5着</span>
                  <span class="RaceClass">C2</span>
                  <span class="Jockey"><a href="/jockey/j2">騎手B</a></span>
                  <span class="LoadWeight">54.0</span>
                  <span class="HorseWeight">478(0)</span>
                </li>
              </td>
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
            <dd class="PastRun">
              <div class="PastRunItem">
                <span class="Date">2026/07/01</span>
                <span class="Place">大井</span>
                <a href="https://nar.netkeiba.com/race/result.html?race_id=202644070101">前走A</a>
                <span class="Finish">2着</span>
                <span class="RaceClass">C1</span>
                <span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/jp1/">前走騎手A</a></span>
                <span class="LoadWeight">55.0</span>
                <span class="HorseWeight">500(+2)</span>
              </div>
              <div class="PastRunItem">
                <span class="Date">2026/06/01</span>
                <span class="RaceClass">C2</span>
                <span class="Finish">3着</span>
                <span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/old1/">古い騎手</a></span>
                <span class="LoadWeight">54.0</span>
              </div>
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
            <dd class="PastRun">
              <div class="PastRunItem">
                <span class="Date">2026/07/02</span>
                <span class="Place">船橋</span>
                <span class="Finish">5着</span>
                <span class="RaceClass">C2</span>
                <span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/j2/">騎手B</a></span>
                <span class="LoadWeight">54.0</span>
                <span class="HorseWeight">478(0)</span>
              </div>
            </dd>
          </dl>
        </div>
      </body>
    </html>
    """


def spiritual_newspaper_html(race_id: str = "202635072803") -> str:
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>地方競馬新聞</title>
        <link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
      </head>
      <body>
        <div class="HorseList_Wrapper">
          <dl class="HorseList" id="past_tr_8">
            <dt class="Waku4 orderfix">4</dt>
            <dt class="Waku Waku_Horse orderfix">8</dt>
            <dt class="HorseName Waku4 HorseListSort orderfix">
              <span class="Vertical"><a href="https://db.netkeiba.com/horse/h8/">スピリチュアル</a></span>
            </dt>
            <dt class="Horse_Info orderfix">
              <dl class="fc">
                <dt class="Horse02"><a href="https://db.netkeiba.com/horse/h8/">スピリチュアル</a></dt>
                <dt class="Horse05"><a href="https://db.netkeiba.com/trainer/result/recent/t8/">水沢・調教師H</a></dt>
                <dt class="Horse06 fc"><div class="Type Type03"><span>差</span></div> 中1週</dt>
                <dt class="Horse07 fc">
                  <div class="Weight UpdateOdds"><span>450kg <span>(0)</span></span></div>
                  <div class="Popular UpdateOdds"><span class="OddsDataTxt transition-color">8.0</span><virtul>(<span>4</span><span>人気)</span></virtul></div>
                </dt>
              </dl>
            </dt>
            <dd class="Jockey HorseListSort order2">
              <span class="Barei">牝5 鹿</span>
              <a href="https://db.netkeiba.com/jockey/result/recent/yamamoto/"><span>山本聡</span></a>
              <br><span> 54.0 </span>
            </dd>
            <dd class="PastRun">
              <div class="PastRunItem">
                <span class="Date">2026/07/14</span>
                <span class="Place">盛岡</span>
                <a href="https://nar.netkeiba.com/race/result.html?race_id=202635071401">前走レース</a>
                <span class="Finish">3着</span>
                <span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/yamamoto/">山本聡</a></span>
                <span class="LoadWeight">54.0</span>
                <span class="HorseWeight">450(0)</span>
              </div>
              <div class="PastRunItem">
                <span class="Date">2026/06/30</span>
                <span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/old/">別騎手</a></span>
                <span class="LoadWeight">52.0</span>
              </div>
            </dd>
          </dl>
        </div>
      </body>
    </html>
    """


def split_previous_jockey_newspaper_html(race_id: str = "202635072803") -> str:
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>地方競馬新聞</title>
        <link rel="canonical" href="https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}">
      </head>
      <body>
        <div class="HorseList_Wrapper">
          <dl class="HorseList" id="past_tr_8">
            <dt class="Waku4 orderfix">4</dt>
            <dt class="Waku Waku_Horse orderfix">8</dt>
            <dt class="HorseName Waku4 HorseListSort orderfix">
              <span class="Vertical"><a href="https://db.netkeiba.com/horse/h8/">スピリチュアル</a></span>
            </dt>
            <dt class="Horse_Info orderfix">
              <dl class="fc">
                <dt class="Horse02"><a href="https://db.netkeiba.com/horse/h8/">スピリチュアル</a></dt>
                <dt class="Horse06 fc"><div class="Type Type03"><span>差</span></div> 中1週</dt>
                <dt class="Horse07 fc">
                  <div class="Weight UpdateOdds"><span>450kg <span>(0)</span></span></div>
                  <div class="Popular UpdateOdds"><span class="OddsDataTxt transition-color">8.0</span><virtul>(<span>4</span><span>人気)</span></virtul></div>
                </dt>
              </dl>
            </dt>
            <dd class="Jockey HorseListSort order2">
              <span class="Barei">牝5 鹿</span>
              <a href="https://nar.netkeiba.com/race/jockey.html?jockey_id=yamamoto"><span>山本聡</span></a>
              <br><span> 54.0 </span>
            </dd>
            <dd class="PastRun">
              <div class="PastRunItem">
                <span class="Date">2026/07/14</span>
                <span class="Place">盛岡</span>
                <a href="https://nar.netkeiba.com/race/result.html?race_id=202635071401">前走レース</a>
                <span class="Finish">3着</span>
                <span class="LoadWeight">54.0</span>
                <span class="HorseWeight">450(0)</span>
              </div>
              <div class="PastRunJockey">
                <span class="Label">騎手</span>
                <a href="https://nar.netkeiba.com/race/jockey.html?jockey_id=yamamoto">山本聡</a>
              </div>
              <div class="PastRunItem">
                <span class="Date">2026/06/30</span>
                <span class="Jockey"><a href="https://nar.netkeiba.com/race/jockey.html?jockey_id=old">別騎手</a></span>
                <span class="LoadWeight">52.0</span>
              </div>
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

    def test_jockey_cid2_upload_is_kept_separate_from_required_courseanalysis(self) -> None:
        classified = classify_nar_uploaded_files(
            [
                upload("entry.json", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("style.html", course_html(["先", "差", "追"])),
                upload("keiba_data-9.html", jockey_course_html()),
            ]
        )
        self.assertEqual(set(classified), {"entry", "speed", "courseanalysis", "jockey"})
        self.assertEqual(classified["jockey"]["data_type"], "jockey")

    def test_optional_jockey_html_is_passed_through_without_conversion(self) -> None:
        source = jockey_course_html()
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("style.html", course_html(["先", "差", "追"])),
                upload("keiba_data-9.html", source),
            ]
        )
        self.assertEqual(package.html_files["jockey"], source)
        self.assertEqual(package.file_names["jockey"], "keiba_data-9.html")

    def test_failed_optional_jockey_fetch_json_does_not_block_prediction_inputs(self) -> None:
        error = {
            "race_id": "202644072106",
            "data_type": "error",
            "error": "このnetkeibaページにはまだ対応していません。",
            "url": (
                "https://nar.netkeiba.com/race/data_list.html?race_id=202644072106"
                "&mode=courseanalysis&cid=2#race_data__menu"
            ),
        }
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("style.html", course_html(["先", "差", "追"])),
                upload("keiba_data-9.html", error),
            ]
        )
        self.assertEqual(package.race_id, "202644072106")
        self.assertNotIn("jockey", package.html_files)

    def test_nar_direct_html_upload_uses_newspaper_instead_of_shutuba(self) -> None:
        self.assertEqual(required_kinds("nar"), ("speed", "newspaper", "style"))
        item = classify_html("newspaper.html", newspaper_html(), "nar")
        self.assertEqual(item.kind, "newspaper")

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

    def test_speed_json_same_condition_star_max_reaches_score_inputs_and_audit(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", three_horse_entry_json()),
                upload("speed.json", three_horse_speed_json()),
                upload(
                    "courseanalysis.html",
                    course_html(["逃", "先", "差", "追"], horse_styles={"1": "先", "2": "差", "3": "追"}),
                ),
            ]
        )

        speed_html = package.html_files["speed"]
        self.assertIn('data-star-venue="大井"', speed_html)
        self.assertIn('data-star-distance="1600"', speed_html)
        self.assertNotIn("data-speed-star-max", speed_html)

        parsed, _ = parse_nar_speed_table(speed_html, session=None, fetch_past_detail=False)
        by_number = parsed.set_index("馬番")
        self.assertEqual(float(by_number.loc[1, "過去1年最高指数"]), 72.0)
        self.assertEqual(float(by_number.loc[1, "★最高"]), 60.0)
        self.assertEqual(by_number.loc[1, "star_max_source"], "recent3_same_condition")
        self.assertEqual(by_number.loc[1, "star_max_race"], "2走前")
        self.assertEqual(float(by_number.loc[2, "過去1年最高指数"]), 66.0)
        self.assertEqual(float(by_number.loc[2, "★最高"]), 59.0)
        self.assertEqual(by_number.loc[2, "star_max_source"], "recent3_same_condition")
        self.assertTrue(pd.isna(by_number.loc[3, "★最高"]))
        self.assertEqual(float(by_number.loc[3, "過去1年最高指数"]), 61.0)
        self.assertEqual(by_number.loc[3, "star_max_source"], "missing")

        audited = add_audit_evaluation_columns(parsed, race_type="nar")
        export = build_audit_export_table(audited)
        self.assertIn("過去1年最高指数", export.columns)
        self.assertIn("★最高指数の取得元", export.columns)
        self.assertIn("star_max_index", export.columns)
        self.assertIn("star_max_race", export.columns)
        self.assertIn("star_match_level", export.columns)
        self.assertIn("star_max_source", export.columns)
        self.assertIn("raw_score", export.columns)

    def test_star_high_requires_recent_same_condition_not_explicit_star_max(self) -> None:
        entry = base_json("entry")
        speed = base_json("speed")
        speed["horses"][0]["max"] = ""
        speed["horses"][0]["star_max"] = "70"
        speed["horses"][0]["race3"] = "70"
        speed["horses"][0]["race3_venue"] = "大井"
        speed["horses"][0]["race3_surface"] = "ダ"
        speed["horses"][0]["race3_distance"] = "1600"
        speed["horses"][1]["max"] = ""
        speed["horses"][1]["distance"] = "64"
        speed["horses"][1]["course"] = "63"

        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", entry),
                upload("speed.json", speed),
                upload("courseanalysis.html", course_html(["先", "差"], horse_styles={"1": "先", "2": "差"})),
            ]
        )
        parsed, _ = parse_nar_speed_table(package.html_files["speed"], session=None, fetch_past_detail=False)
        by_number = parsed.set_index("馬番")

        self.assertEqual(float(by_number.loc[1, "★最高"]), 70.0)
        self.assertEqual(by_number.loc[1, "star_max_source"], "recent3_same_condition")
        self.assertTrue(pd.isna(by_number.loc[2, "★最高"]))
        self.assertEqual(by_number.loc[2, "star_max_source"], "missing")

    def test_newspaper_past_run_conditions_feed_star_max_without_speed_condition_keys(self) -> None:
        speed = base_json("speed")
        html = newspaper_html().replace(
            '<span class="Finish">2',
            '<span class="Course">ダ1600m (右)</span><span class="Finish">2',
            1,
        )
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("newspaper.html", html),
                upload("speed.json", speed),
                upload("courseanalysis.html", course_html(["A", "B"], horse_styles={"1": "A", "2": "B"})),
            ]
        )

        self.assertIn('data-star-distance="1600"', package.html_files["speed"])
        parsed, _ = parse_nar_speed_table(package.html_files["speed"], session=None, fetch_past_detail=False)
        same_condition_rows = parsed[parsed["star_max_source"].eq("recent3_same_condition")]
        self.assertEqual(len(same_condition_rows), 1)
        first = same_condition_rows.iloc[0]

        self.assertEqual(float(first["star_max_index"]), 51.0)
        self.assertEqual(first["star_max_source"], "recent3_same_condition")
        self.assertFalse(parsed["star_max_index"].isna().all())

    def test_json_route_and_colab_equivalent_speed_html_match_for_star_and_scores(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", three_horse_entry_json()),
                upload("speed.json", three_horse_speed_json()),
                upload(
                    "courseanalysis.html",
                    course_html(["逃", "先", "差", "追"], horse_styles={"1": "先", "2": "差", "3": "追"}),
                ),
            ]
        )

        app_result = predict_nar_from_html(package.html_files, package.file_names, fetch_past_detail=False)
        colab_result = predict_nar_from_html(dict(package.html_files), dict(package.file_names), fetch_past_detail=False)
        app_table = app_result.overall_table.set_index("馬番")
        colab_table = colab_result.overall_table.set_index("馬番")

        for horse_number in [1, 2, 3]:
            for column in [
                "過去1年最高指数",
                "★最高指数",
                "★最高指数の取得元",
                "star_max_index",
                "star_max_race",
                "star_max_venue",
                "star_max_distance",
                "star_max_surface",
                "star_max_turn",
                "star_match_level",
                "star_max_source",
                "raw_score",
                "能力評価値",
                "normalized_ai_score",
                "ai_rank",
                "final_mark_score",
                "表示印",
            ]:
                left = app_table.loc[horse_number, column]
                right = colab_table.loc[horse_number, column]
                if pd.isna(left) and pd.isna(right):
                    continue
                self.assertEqual(left, right)

        self.assertFalse(app_table["★最高指数"].isna().all())

    def test_all_missing_indexes_do_not_create_star_high(self) -> None:
        entry = base_json("entry")
        speed = base_json("speed")
        for horse in speed["horses"]:
            for key in ("max", "avg5", "distance", "course", "race3", "race2", "race1"):
                horse[key] = "-"

        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", entry),
                upload("speed.json", speed),
                upload("courseanalysis.html", course_html(["先", "差"], horse_styles={"1": "先", "2": "差"})),
            ]
        )
        parsed, _ = parse_nar_speed_table(package.html_files["speed"], session=None, fetch_past_detail=False)

        self.assertTrue(parsed["★最高"].isna().all())
        self.assertTrue(parsed["star_max_source"].eq("missing").all())

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
        self.assertEqual(first["previous_date"], "2026/07/01")
        self.assertEqual(first["previous_track"], "大井")
        self.assertEqual(first["previous_finish"], "2着")
        self.assertEqual(first["previous_jockey"], "前走騎手A")
        self.assertEqual(first["previous_weight"], "55.0")
        self.assertEqual(first["previous_body_weight"], "500(+2)")
        self.assertIn("C1", first["class_text"])

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
        self.assertEqual(first["previous_date"], "2026/07/01")
        self.assertEqual(first["previous_jockey"], "前走騎手A")
        self.assertEqual(first["previous_weight"], "55.0")
        self.assertEqual(first["前走騎手"], "前走騎手A")
        self.assertEqual(first["前走斤量"], "55.0")
        self.assertIn("C1", first["class_text"])
        second = data["horses"][1]
        self.assertEqual(second["running_style"], "差")
        self.assertEqual(second["horse_weight"], "478(0)")
        self.assertEqual(second["previous_jockey"], "騎手B")
        self.assertEqual(second["previous_weight"], "54.0")

    def test_market_mode_uses_optional_newspaper_class_interval_and_body_weight(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差"], horse_styles={"1": "先", "2": "差"})),
                upload("newspaper.html", newspaper_vertical_html()),
            ]
        )
        result = predict_nar(
            package.html_files,
            package.file_names,
            prediction_logic_version="market",
        )
        first = result.overall_table.loc[result.overall_table["馬番"].eq(1)].iloc[0]
        self.assertEqual(first["race_interval_market"], "中2週")
        self.assertEqual(first["body_weight_market"], "501kg（+31）")
        self.assertEqual(first["current_class_market"], "C2")
        self.assertEqual(first["previous_class_market"], "C1")
        self.assertEqual(first["class_shift_market"], "クラス降級")
        self.assertIn("C2経験あり", first["class_basis_market"])
        self.assertIn("C2好走歴", first["class_basis_market"])

    def test_nar_newspaper_previous_run_keeps_horse_row_mapping(self) -> None:
        data = parse_nar_newspaper_html(spiritual_newspaper_html())
        self.assertEqual(data["race_id"], "202635072803")
        self.assertEqual(len(data["horses"]), 1)
        spiritual = data["horses"][0]
        self.assertEqual(spiritual["horse_number"], "8")
        self.assertEqual(spiritual["horse_name"], "スピリチュアル")
        self.assertEqual(spiritual["jockey"], "山本聡")
        self.assertEqual(spiritual["weight"], "54.0")
        self.assertEqual(spiritual["previous_jockey"], "山本聡")
        self.assertEqual(spiritual["previous_weight"], "54.0")
        self.assertEqual(spiritual["previous_body_weight"], "450(0)")
        self.assertNotEqual(spiritual["previous_jockey"], "別騎手")

    def test_nar_newspaper_previous_jockey_can_use_jockey_id_link_and_split_fragment(self) -> None:
        data = parse_nar_newspaper_html(split_previous_jockey_newspaper_html())
        self.assertEqual(data["race_id"], "202635072803")
        spiritual = data["horses"][0]
        self.assertEqual(spiritual["horse_number"], "8")
        self.assertEqual(spiritual["jockey"], "山本聡")
        self.assertEqual(spiritual["weight"], "54.0")
        self.assertEqual(spiritual["previous_weight"], "54.0")
        self.assertEqual(spiritual["previous_jockey"], "山本聡")
        self.assertNotEqual(spiritual["previous_jockey"], "別騎手")

    def test_nar_newspaper_previous_jockey_can_use_data14_cell(self) -> None:
        html = spiritual_newspaper_html().replace(
            '<span class="Jockey"><a href="https://db.netkeiba.com/jockey/result/recent/yamamoto/">山本聡</a></span>',
            '<span class="Data14">山本聡</span>',
        )
        data = parse_nar_newspaper_html(html)
        spiritual = data["horses"][0]
        self.assertEqual(spiritual["previous_jockey"], "山本聡")
        self.assertEqual(spiritual["_debug_previous_jockey_raw"], "山本聡")
        self.assertEqual(spiritual["_debug_previous_jockey_normalized"], "山本聡")

    def test_spiritual_previous_run_details_reach_display_attrs(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("speed.json", spiritual_speed_json()),
                upload("courseanalysis.html", course_html(["逃", "先", "差", "追"], "202635072803", {"8": "差"})),
                upload("newspaper.html", spiritual_newspaper_html()),
            ]
        )

        speed_html = package.html_files["speed"]
        self.assertIn('data-display-current-load-weight="54.0"', speed_html)
        self.assertIn('data-display-previous-load-weight="54.0"', speed_html)
        self.assertIn('data-display-load-weight-change="0.0"', speed_html)
        self.assertIn('data-display-current-jockey="山本聡"', speed_html)
        self.assertIn('data-display-previous-jockey="山本聡"', speed_html)
        self.assertIn('data-display-jockey-changed="False"', speed_html)

        trace = {row["horse_number"]: row for row in package.debug_logs}
        self.assertEqual(trace["8"]["raw_previous_jockey"], "山本聡")
        self.assertEqual(trace["8"]["normalized_previous_jockey"], "山本聡")
        self.assertEqual(trace["8"]["entry_prev_jockey"], "山本聡")
        self.assertEqual(trace["8"]["merged_prev_jockey"], "山本聡")
        self.assertEqual(trace["8"]["speed_html_previous_jockey"], "山本聡")

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
        self.assertEqual(package.html_files["newspaper_context"], newspaper_html().strip())
        self.assertEqual(package.file_names["newspaper_context"], "newspaper.html")
        self.assertIn("テストホースA", package.html_files["shutuba"])
        self.assertIn('<td class="DataTitle_Cell">先</td>', package.html_files["style"])
        self.assertIn('data-display-previous-load-weight="55.0"', package.html_files["speed"])
        self.assertIn('data-display-previous-jockey="前走騎手A"', package.html_files["speed"])

    def test_newspaper_previous_run_is_carried_when_entry_json_is_preferred(self) -> None:
        package = build_nar_prediction_inputs_from_uploads(
            [
                upload("entry.json", base_json("entry")),
                upload("speed.json", base_json("speed")),
                upload("courseanalysis.html", course_html(["先", "差", "追"])),
                upload("newspaper.html", newspaper_vertical_html()),
            ]
        )

        self.assertEqual(package.entry_source, "entry")
        speed_html = package.html_files["speed"]
        self.assertIn('data-display-previous-load-weight="55.0"', speed_html)
        self.assertIn('data-display-load-weight-change="1.0"', speed_html)
        self.assertIn('data-display-previous-jockey="前走騎手A"', speed_html)
        self.assertIn('data-display-jockey-changed="True"', speed_html)
        self.assertIn('data-display-jockey-changed="False"', speed_html)

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
