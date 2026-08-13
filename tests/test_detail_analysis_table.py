from __future__ import annotations

import importlib.util
import inspect
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class StreamlitStub(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.last_dataframe: pd.DataFrame | None = None
        self.markdown_calls: list[str] = []
        self.expander_labels: list[str] = []

    def set_page_config(self, **_kwargs) -> None:
        return None

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, value, **_kwargs) -> None:
        self.last_dataframe = value.copy()

    def markdown(self, value, **_kwargs) -> None:
        self.markdown_calls.append(value)

    def expander(self, label, **_kwargs):
        self.expander_labels.append(label)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


def load_app_module():
    import core.models  # Load the dependency-free model module before stubbing UI dependencies.

    streamlit = StreamlitStub()
    noop = lambda *_args, **_kwargs: None

    def stub_module(name: str, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        return module

    class NarJsonDataError(Exception):
        pass

    class NarJsonPredictionInput:
        pass

    class MobilePngRenderError(Exception):
        pass

    render_package = types.ModuleType("render")
    render_package.__path__ = []
    stubs = {
        "requests": types.ModuleType("requests"),
        "streamlit": streamlit,
        "core.audit_features": stub_module(
            "core.audit_features",
            audit_table_to_csv_bytes=noop,
            audit_table_to_json_bytes=noop,
            audit_table_to_markdown=noop,
            build_audit_export_table=noop,
        ),
        "core.jra_predictor": stub_module("core.jra_predictor", predict_jra=noop),
        "core.html_classifier": stub_module(
            "core.html_classifier",
            DISPLAY_ORDER=[],
            classify_html=noop,
            classify_many=noop,
            kind_label=noop,
            required_kinds=noop,
            validate_upload_bundle=noop,
        ),
        "core.nar_json_input": stub_module(
            "core.nar_json_input",
            NarJsonDataError=NarJsonDataError,
            NarJsonPredictionInput=NarJsonPredictionInput,
            build_nar_prediction_inputs_from_uploads=noop,
        ),
        "core.nar_predictor": stub_module("core.nar_predictor", predict_nar=noop),
        "core.star_trace": stub_module(
            "core.star_trace",
            log_star_trace=lambda _stage, rows: rows,
            star_trace_row=lambda **kwargs: kwargs,
        ),
        "core.version": stub_module("core.version", APP_VERSION="test"),
        "render": render_package,
        "render.mobile_png": stub_module(
            "render.mobile_png",
            MobilePngRenderError=MobilePngRenderError,
            render_mobile_png=noop,
        ),
    }

    module_name = "detail_analysis_app_under_test"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "app.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("app.pyを読み込めません。")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
    return module, streamlit


class DetailAnalysisTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app, cls.streamlit = load_app_module()

    def render_detail(self, race_mode: str, overall_table: pd.DataFrame, horse_evaluation: pd.DataFrame) -> pd.DataFrame:
        self.streamlit.last_dataframe = None
        result = SimpleNamespace(
            race_mode=race_mode,
            overall_table=overall_table,
            horse_evaluation=horse_evaluation,
            debug_info={},
        )
        self.app.render_overall_table(result)
        self.assertIsNotNone(self.streamlit.last_dataframe)
        return self.streamlit.last_dataframe

    def test_detail_indexes_come_from_matching_overall_horse_for_both_modes(self) -> None:
        overall_table = pd.DataFrame(
            [
                {
                    "馬番": 1.0,
                    "馬名": "一番馬",
                    "距離指数": 101,
                    "コース指数": 102,
                    "★最高指数": 103,
                    "3走前": 104,
                    "2走前": 105,
                    "前走": 106,
                    "平均指数": 105,
                },
                {
                    "馬番": 2,
                    "馬名": "二番馬",
                    "距離指数": 201,
                    "コース指数": 202,
                    "★最高指数": 203,
                    "3走前": 204,
                    "2走前": 205,
                    "前走": 206,
                    "平均指数": 205,
                },
            ]
        )
        horse_evaluation = pd.DataFrame(
            [
                {
                    "馬番": "1",
                    "馬名": "一番馬",
                    "表示印": "○",
                    "馬年齢": "4歳",
                    "騎手詳細": "騎手1【継続】",
                    "斤量詳細": "55kg",
                    "脚質": "差し",
                    "単勝オッズ": "5.5",
                    "近3走傾向": "下降",
                    "表示コメント": "一番馬コメント",
                },
                {
                    "馬番": "2",
                    "馬名": "二番馬",
                    "表示印": "◎",
                    "馬年齢": "5歳",
                    "騎手詳細": "騎手2【継続】",
                    "斤量詳細": "56kg",
                    "脚質": "先行",
                    "単勝オッズ": "2.5",
                    "近3走傾向": "上昇",
                    "表示コメント": "二番馬コメント",
                },
            ]
        )

        for race_mode in ("jra", "nar"):
            with self.subTest(race_mode=race_mode):
                detail = self.render_detail(race_mode, overall_table, horse_evaluation)
                self.assertEqual(list(detail["馬"]), ["2 二番馬", "1 一番馬"])

                second = detail.iloc[0]
                self.assertEqual(
                    list(second[["距離", "コース", "★", "3走前", "2走前", "前走", "3走平均"]]),
                    ["201", "202", "203", "204", "205", "206", "205"],
                )
                self.assertEqual(second["グループ"], "SS")
                self.assertEqual(second["騎手"], "騎手2（継）")
                self.assertEqual(second["斤量"], "56")
                self.assertEqual(second["状態"], "上昇")
                self.assertEqual(second["コメント"], "二番馬コメント")

                first = detail.iloc[1]
                self.assertEqual(
                    list(first[["距離", "コース", "★", "3走前", "2走前", "前走", "3走平均"]]),
                    ["101", "102", "103", "104", "105", "106", "105"],
                )
                self.assertEqual(first["グループ"], "A")
                self.assertEqual(first["状態"], "下降")
                self.assertEqual(first["コメント"], "一番馬コメント")

    def test_market_card_hides_raw_coordinates_and_uncalibrated_odds(self) -> None:
        html = self.app.market_horse_card_html(
            {
                "馬番": 10,
                "馬名": "アイビーサムライオ",
                "ability_band_v2": "A",
                "market_ability_score": 90,
                "market_ability_rank": 3,
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "ai_current_reason": "能力Aを土台 / 展開適合",
                "actual_odds": 2.3,
                "jockey_display_market": "笹川翼（複50%）",
                "weight_market": "56.0kg",
                "race_interval_market": "休み明け",
                "current_class_market": "B3",
                "running_style_market": "先",
                "state_arrow": "↗",
                "state_label_market": "持ち直し",
                "state_transition": "60→65→70",
                "position_path_market": "先団 → 先団 → 中団",
                "position_start_market": "top=12%, left=29.41%",
                "position_corner3_market": "top=30%, left=21.56%",
                "fair_odds_display": "未校正",
                "pace_mark_market": "△",
                "pace_reason_market": "ハイペースで先行には厳しめ",
                "course_development_mark": "△",
                "course_development_reason": "ハイペースで先行には厳しめ",
                "plus_materials_display": "近走持ち直し",
                "minus_materials_display": "休み明け",
            },
            "nar",
        )
        self.assertIn("◎ 10 アイビーサムライオ", html)
        self.assertIn("能力3位・今回1位", html)
        self.assertIn("先団 → 先団 → 中団", html)
        self.assertNotIn("top=", html)
        self.assertNotIn("left=", html)
        self.assertNotIn("未校正", html)
        self.assertNotIn("AI適正", html)

    def test_market_full_table_places_jockey_and_weight_after_actual_odds(self) -> None:
        self.streamlit.last_dataframe = None
        self.app.render_market_full_table(
            pd.DataFrame(
                [
                    {
                        "馬番": 2,
                        "馬名": "ケイアイエルナト",
                        "馬年齢": "牡4",
                        "ai_current_mark": "○",
                        "current_evaluation_rank": 2,
                        "ability_band_v2": "A",
                        "market_ability_rank": 1,
                        "market_ability_score": 91,
                        "actual_odds": 3.5,
                        "jockey_display_market": "矢野貴之（複58%）",
                        "weight_market": "56.0kg",
                    }
                ]
            ),
            "nar",
        )
        result = self.streamlit.last_dataframe
        self.assertIsNotNone(result)
        columns = list(result.columns)
        odds_index = columns.index("実オッズ")
        self.assertEqual(columns[odds_index + 1 : odds_index + 3], ["騎手", "斤量"])
        self.assertNotIn("AI適正", columns)
        self.assertEqual(result.loc[0, "騎手"], "矢野貴之（複58%）")

    def test_zero_values_are_kept_and_real_missing_values_use_existing_placeholders(self) -> None:
        overall_table = pd.DataFrame(
            [
                {
                    "馬番": 3.0,
                    "距離指数": 0,
                    "コース指数": 0,
                    "★最高指数": 0,
                    "3走前": 0,
                    "2走前": 0,
                    "前走": 0,
                    "平均指数": 0,
                },
                {
                    "馬番": 4,
                    "距離指数": "0",
                    "コース指数": "0",
                    "star_max_index": "0",
                    "3走前": "0",
                    "2走前": "0",
                    "前走": "0",
                    "平均指数": "0",
                },
                {
                    "馬番": "5",
                    "距離指数": None,
                    "コース指数": float("nan"),
                    "★最高指数": "",
                    "3走前": "",
                    "2走前": None,
                    "前走": float("nan"),
                    "平均指数": "",
                },
            ]
        )
        horse_evaluation = pd.DataFrame(
            [
                {"馬番": "3", "馬名": "数値ゼロ", "表示印": "◎"},
                {"馬番": "4", "馬名": "文字ゼロ", "表示印": "○"},
                {"馬番": "5", "馬名": "欠損", "表示印": "▲"},
            ]
        )

        detail = self.render_detail("jra", overall_table, horse_evaluation)
        target_columns = ["距離", "コース", "★", "3走前", "2走前", "前走", "3走平均"]
        self.assertEqual(list(detail.iloc[0][target_columns]), ["0"] * 7)
        self.assertEqual(list(detail.iloc[1][target_columns]), ["0"] * 7)
        self.assertEqual(
            list(detail.iloc[2][target_columns]),
            ["—", "—", "該当なし", "—", "—", "—", "—"],
        )


class HorseSummaryCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app, cls.streamlit = load_app_module()

    def render_cards(self, race_mode: str, overall_table: pd.DataFrame, horse_evaluation: pd.DataFrame) -> list[str]:
        self.streamlit.markdown_calls.clear()
        self.streamlit.expander_labels.clear()
        result = SimpleNamespace(
            race_mode=race_mode,
            overall_table=overall_table,
            horse_evaluation=horse_evaluation,
        )
        self.app.render_horse_summary_cards(result)
        return list(self.streamlit.markdown_calls)

    def test_card_indexes_come_from_matching_overall_horse_for_both_modes(self) -> None:
        overall_table = pd.DataFrame(
            [
                {
                    "馬番": 1.0,
                    "距離指数": 101,
                    "コース指数": 102,
                    "star_max_index": 103,
                    "3走前": 104,
                    "2走前": 105,
                    "前走": 106,
                    "平均指数": 105,
                    "star_max_race": "2走前",
                    "star_match_level": "venue_distance_surface",
                },
                {
                    "馬番": 2,
                    "距離指数": 201,
                    "コース指数": 202,
                    "★最高指数": 203,
                    "3走前": 204,
                    "2走前": 205,
                    "前走": 206,
                    "平均指数": 205,
                    "★該当走": "前走",
                    "★条件": "東京芝1600m",
                },
            ]
        )
        horse_evaluation = pd.DataFrame(
            [
                {
                    "馬番": "1",
                    "馬名": "一番馬",
                    "表示印": "○",
                    "馬年齢": "牡5",
                    "斤量詳細": "57kg",
                    "騎手詳細": "騎手1【継続】",
                    "脚質": "差し",
                    "近3走傾向": "安定",
                    "表示コメント": "一番馬コメント",
                },
                {
                    "馬番": "2",
                    "馬名": "二番馬",
                    "表示印": "◎",
                    "馬年齢": "牝4",
                    "斤量詳細": "56kg",
                    "騎手詳細": "騎手2【継続】",
                    "脚質": "先行",
                    "近3走傾向": "上昇",
                    "表示コメント": "二番馬コメント",
                },
            ]
        )

        for race_mode in ("jra", "nar"):
            with self.subTest(race_mode=race_mode):
                overall_before = overall_table.copy(deep=True)
                evaluation_before = horse_evaluation.copy(deep=True)
                second, first = self.render_cards(race_mode, overall_table, horse_evaluation)

                self.assertIn("【SS】◎ 2 二番馬", second)
                self.assertIn("★203", second)
                self.assertIn("距離201", second)
                self.assertIn("コース202", second)
                self.assertIn("3走前：204", second)
                self.assertIn("2走前：205", second)
                self.assertIn("前走：206", second)
                self.assertIn("3走平均：205", second)
                self.assertIn("★該当走：前走", second)
                self.assertIn("★条件：東京芝1600m", second)
                self.assertIn("牝4", second)
                self.assertIn("56kg", second)
                self.assertIn("騎手2【継続】", second)
                self.assertIn("脚質：先行", second)
                self.assertIn("状態：上昇", second)
                self.assertIn("コメント：二番馬コメント", second)

                self.assertIn("【A】○ 1 一番馬", first)
                self.assertIn("★103", first)
                self.assertIn("距離101", first)
                self.assertIn("コース102", first)
                self.assertIn("3走前：104", first)
                self.assertIn("2走前：105", first)
                self.assertIn("前走：106", first)
                self.assertIn("3走平均：105", first)
                self.assertIn("★該当走：2走前", first)
                self.assertIn("★条件：今回と同条件", first)
                self.assertIn("状態：安定", first)
                self.assertIn("コメント：一番馬コメント", first)
                pd.testing.assert_frame_equal(overall_table, overall_before)
                pd.testing.assert_frame_equal(horse_evaluation, evaluation_before)

    def test_card_keeps_zero_values_and_uses_placeholders_only_for_real_missing_values(self) -> None:
        horse_row = {"馬番": "1", "馬名": "テスト馬", "表示印": "◎"}
        for value in (0, "0"):
            with self.subTest(value=value):
                overall_row = {
                    "馬番": 1,
                    "距離指数": value,
                    "コース指数": value,
                    "★最高指数": value,
                    "3走前": value,
                    "2走前": value,
                    "前走": value,
                    "平均指数": value,
                    "★該当走": value,
                    "★条件": value,
                }
                html = self.app.horse_summary_card_html(horse_row, "jra", overall_row)
                for expected in (
                    "★0",
                    "距離0",
                    "コース0",
                    "3走前：0",
                    "2走前：0",
                    "前走：0",
                    "3走平均：0",
                    "★該当走：0",
                    "★条件：0",
                ):
                    self.assertIn(expected, html)

        missing_row = {
            "馬番": 1,
            "距離指数": None,
            "コース指数": float("nan"),
            "★最高指数": "",
            "3走前": None,
            "2走前": float("nan"),
            "前走": "",
            "平均指数": None,
            "★該当走": "",
            "★条件": None,
        }
        html = self.app.horse_summary_card_html(horse_row, "nar", missing_row)
        for expected in (
            "★該当なし",
            "距離—",
            "コース—",
            "3走前：—",
            "2走前：—",
            "前走：—",
            "3走平均：—",
            "★該当走：—",
            "★条件：—",
        ):
            self.assertIn(expected, html)

    def test_horse_summary_card_uses_existing_recent_race_records(self) -> None:
        horse_row = {
            "馬番": "8",
            "馬名": "近走馬",
            "表示印": "◎",
            "display_group": "SS",
            "ability_display_score": 88,
            "近3走傾向": "連続上昇",
            "4角予想": "好位",
            "直線評価": "勝ち負け",
        }
        overall_row = {
            "馬番": "8",
            "平均指数": 81,
            "_past_runs": [
                {
                    "label": "前走",
                    "race_date": "2026-08-01",
                    "racecourse": "新潟",
                    "surface": "芝",
                    "distance": 1600,
                    "position": 3,
                    "popularity": 4,
                    "value": 82,
                    "passing_order": "6-6",
                },
                {
                    "label": "2走前",
                    "race_date": "2026-07-15",
                    "racecourse": "東京",
                    "surface": "芝",
                    "distance": 1600,
                    "position": 1,
                    "popularity": 2,
                    "value": 88,
                },
                {
                    "label": "3走前",
                    "race_date": "2026-07-01",
                    "racecourse": "中山",
                    "surface": "芝",
                    "distance": 1800,
                    "position": 6,
                    "popularity": 3,
                    "value": 76,
                },
            ],
        }

        html = self.app.horse_summary_card_html(horse_row, "jra", overall_row)

        self.assertIn("近3走", html)
        self.assertIn("前走", html)
        self.assertIn("前走：新潟 芝 1600m 3着 指数82", html)
        self.assertIn("2走前：東京 芝 1600m 1着 指数88", html)
        self.assertIn("3走前：中山 芝 1800m 6着 指数76", html)
        self.assertNotIn("近3走：前走", html)
        self.assertIn("新潟", html)
        self.assertIn("指数82", html)
        self.assertIn("通過6-6", html)
        self.assertIn("2走前", html)
        self.assertIn("3走前", html)
        self.assertIn("4角", html)
        self.assertIn("直線", html)

    def test_ability_bar_clamps_display_without_mutating_source_values(self) -> None:
        horse_row = {
            "馬番": "1",
            "馬名": "能力上限",
            "表示印": "◎",
            "グループ": "SS",
            "能力評価値": 123.4,
        }
        overall_row = {"馬番": "1", "距離指数": 61, "コース指数": 44}
        horse_before = horse_row.copy()
        overall_before = overall_row.copy()

        html = self.app.horse_summary_card_html(horse_row, "jra", overall_row)

        self.assertEqual(html.count("ka-ability-track"), 1)
        self.assertIn("能力評価", html)
        self.assertIn("<span>100</span>", html)
        self.assertIn("width:100%", html)
        self.assertIn("能力評価値：123.4", html)
        self.assertNotIn("補正前能力", html)
        self.assertNotIn("補正後能力", html)
        self.assertEqual(horse_row, horse_before)
        self.assertEqual(overall_row, overall_before)

        low_html = self.app.horse_summary_card_html(
            {"馬番": "2", "馬名": "能力下限", "表示印": "", "グループ": "Z", "能力評価値": -8.2},
            "nar",
            {"馬番": "2"},
        )
        self.assertIn("<span>0</span>", low_html)
        self.assertIn("width:0%", low_html)

    def test_material_badges_and_first_blinker_are_display_only(self) -> None:
        horse_row = {
            "馬番": "3",
            "馬名": "初装着",
            "表示印": "○",
            "グループ": "A",
            "能力評価値": 91,
            "年齢補正": 2,
            "斤量詳細": "56.0kg（前走比+1.0kg）",
            "騎手詳細": "前走騎手 → 今回騎手【乗り替わり】",
            "状態": "上昇",
            "補足": "初ブリンカー",
        }
        overall_row = {"馬番": "3", "距離指数": 65, "コース指数": 40}

        html = self.app.horse_summary_card_html(horse_row, "jra", overall_row)

        self.assertIn("年齢+2", html)
        self.assertIn("距離◎", html)
        self.assertIn("コース△", html)
        self.assertIn("状態上昇", html)
        self.assertIn("斤量増", html)
        self.assertIn("乗替△", html)
        self.assertIn("初B", html)
        self.assertIn("数値補正：なし", html)
        self.assertIn("二重補正回避", html)

        nar_html = self.app.horse_summary_card_html(horse_row, "nar", overall_row)
        self.assertNotIn("初B", nar_html)

        continued_blinker_html = self.app.horse_summary_card_html(
            {
                "馬番": "4",
                "馬名": "継続馬具",
                "表示印": "△",
                "グループ": "B",
                "能力評価値": 73,
                "補足": "ブリンカー継続",
            },
            "jra",
            {"馬番": "4"},
        )
        self.assertNotIn("初B　", continued_blinker_html)
        self.assertIn("初B：—", continued_blinker_html)


class DisplayGroupViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app, cls.streamlit = load_app_module()

    def test_all_app_views_use_ss_a_b_c_z_and_keep_source_rows_unchanged(self) -> None:
        horse_evaluation = pd.DataFrame(
            [
                {"馬番": 1, "馬名": "本命", "表示印": "◎", "グループ": "SS", "AI点": 100},
                {"馬番": 2, "馬名": "対抗", "表示印": "○", "グループ": "A", "AI点": 90},
                {"馬番": 3, "馬名": "単穴", "表示印": "▲", "グループ": "A", "AI点": 85},
                {"馬番": 4, "馬名": "押さえ", "表示印": "△", "グループ": "B", "AI点": 80},
                {"馬番": 5, "馬名": "穴候補", "表示印": "✓", "グループ": "D", "AI点": 75},
                {"馬番": 6, "馬名": "圏外", "表示印": "", "グループ": "D", "AI点": 70},
            ]
        )
        overall_table = horse_evaluation.copy(deep=True)
        overall_table["display_group"] = ["SS", "A", "A", "B", "C", "Z"]
        overall_table["グループ"] = overall_table["display_group"]
        evaluation_before = horse_evaluation.copy(deep=True)
        overall_before = overall_table.copy(deep=True)
        result = SimpleNamespace(
            race_mode="jra",
            overall_table=overall_table,
            horse_evaluation=horse_evaluation,
            raw_output="",
            ai_race_review="",
            betting_structure="既存買い目本文",
        )

        self.assertEqual([group for group, _label in self.app.POWER_GROUPS], ["SS", "A", "B", "C", "Z"])
        rows = self.app.sorted_display_rows(result)
        self.assertEqual([self.app.display_group_from_row(row) for row in rows], ["SS", "A", "A", "B", "C", "Z"])

        for renderer in (self.app.render_power_map, self.app.render_betting_consideration):
            self.streamlit.markdown_calls.clear()
            renderer(result)
            markup = "\n".join(self.streamlit.markdown_calls)
            self.assertIn(">C<", markup)
            self.assertIn(">Z<", markup)
            self.assertNotIn(">D<", markup)
        self.streamlit.markdown_calls.clear()
        self.app.render_race_flow(result)
        flow_markup = "\n".join(self.streamlit.markdown_calls)
        self.assertIn("レース考察", flow_markup)
        self.assertNotIn("ゴール前の勢力予想", flow_markup)
        self.assertNotIn(">D<", flow_markup)
        self.assertEqual(result.betting_structure, "既存買い目本文")
        self.assertNotIn(
            "render_betting_consideration(result)",
            inspect.getsource(self.app.render_colab_style_result),
        )
        result_source = inspect.getsource(self.app.render_colab_style_result)
        self.assertLess(result_source.index("render_race_summary"), result_source.index("render_power_map"))
        self.assertLess(result_source.index("render_power_map"), result_source.index("render_horse_summary_cards"))
        self.assertLess(result_source.index("render_horse_summary_cards"), result_source.index("render_race_flow"))
        self.assertLess(result_source.index("render_race_flow"), result_source.index("render_investment_decision"))
        self.assertNotIn("render_investment_target_horses", result_source)

        self.streamlit.markdown_calls.clear()
        self.streamlit.expander_labels.clear()
        self.app.render_horse_summary_cards(result)
        card_markup = "\n".join(self.streamlit.markdown_calls)
        self.assertIn("【C】✓ 5 穴候補", card_markup)
        self.assertIn("【Z】 6 圏外", card_markup)
        self.assertNotIn("【D】", card_markup)
        self.assertIn("Zグループの馬も表示", self.streamlit.expander_labels)

        self.streamlit.last_dataframe = None
        self.app.render_overall_table(result)
        self.assertEqual(list(self.streamlit.last_dataframe["グループ"]), ["SS", "A", "A", "B", "C", "Z"])
        pd.testing.assert_frame_equal(horse_evaluation, evaluation_before)
        pd.testing.assert_frame_equal(overall_table, overall_before)


if __name__ == "__main__":
    unittest.main()
