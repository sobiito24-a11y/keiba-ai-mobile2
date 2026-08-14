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
    import core.html_classifier as real_html_classifier
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
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    stubs = {
        "requests": requests_stub,
        "streamlit": streamlit,
        "core.audit_features": stub_module(
            "core.audit_features",
            audit_table_to_csv_bytes=noop,
            audit_table_to_json_bytes=noop,
            audit_table_to_markdown=noop,
            build_audit_export_table=noop,
        ),
        "core.jra_predictor": stub_module("core.jra_predictor", predict_jra=noop),
        "core.html_classifier": real_html_classifier,
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
                "sex_age": "牡4",
                "ability_band_v2": "A",
                "market_ability_score": 90,
                "market_ability_rank": 3,
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "ai_current_reason": "能力Aを土台 / 展開適合",
                "actual_odds": 2.3,
                "jockey_display_market": "笹川翼（複50%）",
                "weight_market": "56.0kg",
                "weight_change_market": 1.0,
                "body_weight_market": "494kg（-2）",
                "race_interval_market": "休み明け",
                "current_class_market": "B3",
                "class_shift_market": "クラス降級",
                "class_basis_market": "今回B3 / 前走A2 / B3経験あり",
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
        self.assertIn("A 10 アイビーサムライオ", html)
        self.assertIn("能力3位・今回1位", html)
        self.assertIn("◎｜2.3倍｜牡4｜能力値90.0｜能力3位・今回1位", html)
        self.assertIn("先団 → 先団 → 中団", html)
        self.assertIn("56.0kg（前走比+1.0kg）", html)
        self.assertIn("斤量：56.0kg（前走比+1.0kg）", html)
        self.assertIn("494kg（-2）", html)
        self.assertIn("レース間隔：休み明け", html)
        self.assertIn("クラス：B3｜クラス降級", html)
        self.assertIn("クラス実績：今回B3 / 前走A2 / B3経験あり", html)
        self.assertNotIn("top=", html)
        self.assertNotIn("left=", html)
        self.assertNotIn("未校正", html)
        self.assertNotIn("AI適正", html)

    def test_market_card_shows_ability_value_for_unmarked_horse_with_one_decimal(self) -> None:
        html = self.app.market_horse_card_html(
            {
                "馬番": 9,
                "馬名": "リュウノギフト",
                "sex_age": "牡3",
                "ability_band_v2": "B",
                "market_ability_score": 36.0,
                "market_ability_rank": 6,
                "current_evaluation_rank": 6,
                "ai_current_mark": "",
                "actual_odds": 62.6,
            },
            "nar",
        )

        self.assertIn("B 9 リュウノギフト", html)
        self.assertIn("<b>62.6倍｜牡3｜能力値36.0｜能力6位・今回6位</b>", html)

    def test_market_horse_cards_are_displayed_by_ability_value(self) -> None:
        self.streamlit.markdown_calls = []
        table = pd.DataFrame(
            [
                {
                    "馬番": 1,
                    "馬名": "今回一位",
                    "ability_band_v2": "A",
                    "market_ability_score": 42.0,
                    "market_ability_rank": 3,
                    "current_evaluation_rank": 1,
                    "ai_current_mark": "◎",
                    "actual_odds": 2.0,
                },
                {
                    "馬番": 2,
                    "馬名": "能力一位",
                    "ability_band_v2": "A",
                    "market_ability_score": 51.0,
                    "market_ability_rank": 1,
                    "current_evaluation_rank": 2,
                    "ai_current_mark": "○",
                    "actual_odds": 4.0,
                },
            ]
        )

        self.app.render_market_horse_cards(table, "nar")

        cards = [html for html in self.streamlit.markdown_calls if "ka-horse-card" in html]
        self.assertGreaterEqual(len(cards), 2)
        self.assertIn("A 2 能力一位", cards[0])
        self.assertIn("A 1 今回一位", cards[1])

    def test_market_compare_normal_flow_hides_band_price_and_ai_evaluation_tables(self) -> None:
        result = SimpleNamespace(
            race_mode="jra",
            overall_table=pd.DataFrame(
                [
                    {
                        "馬番": 1,
                        "馬名": "表示確認",
                        "ability_band_v2": "A",
                        "market_ability_score": 73.2,
                        "market_ability_rank": 1,
                        "current_evaluation_rank": 1,
                    }
                ]
            ),
            horse_evaluation=pd.DataFrame(),
            debug_info={},
        )
        calls: list[str] = []
        originals = {
            name: getattr(self.app, name)
            for name in (
                "render_race_header",
                "render_market_race_facts",
                "render_market_band_prices",
                "render_market_ai_evaluation",
                "render_market_horse_cards",
                "render_market_full_table",
                "render_market_user_selection",
                "render_market_audit_details",
            )
        }

        def forbidden(*_args, **_kwargs):
            raise AssertionError("通常UIでは表示しないセクションです")

        try:
            self.app.render_race_header = lambda _result: calls.append("header")
            self.app.render_market_race_facts = lambda _result, _table: calls.append("facts")
            self.app.render_market_band_prices = forbidden
            self.app.render_market_ai_evaluation = forbidden
            self.app.render_market_horse_cards = lambda _table, _mode: calls.append("cards")
            self.app.render_market_full_table = lambda _table, _mode: calls.append("full")
            self.app.render_market_user_selection = lambda _result, _table: calls.append("selection")
            self.app.render_market_audit_details = lambda _result, _table: calls.append("audit")

            self.app.render_market_compare_result(result)
        finally:
            for name, func in originals.items():
                setattr(self.app, name, func)

        self.assertEqual(calls, ["header", "facts", "cards", "full", "selection", "audit"])

    def test_market_ai_evaluation_appends_existing_sex_age_to_horse_name(self) -> None:
        self.streamlit.last_dataframe = None
        self.app.render_market_ai_evaluation(
            pd.DataFrame(
                [
                    {
                        "馬番": 3,
                        "馬名": "オーキッドレディ",
                        "sex_age": "牝5",
                        "current_evaluation_rank": 1,
                        "market_ability_rank": 1,
                        "ability_band_v2": "A",
                        "ai_current_mark": "◎",
                        "actual_odds": 2.4,
                        "ai_current_reason": "能力Aを土台",
                    }
                ]
            )
        )
        result = self.streamlit.last_dataframe
        self.assertIsNotNone(result)
        self.assertEqual(result.loc[0, "馬"], "3 オーキッドレディ（牝5）")

    def test_market_ai_evaluation_uses_short_training_without_raw_lap(self) -> None:
        self.streamlit.last_dataframe = None
        self.app.render_market_ai_evaluation(
            pd.DataFrame(
                [
                    {
                        "馬番": 5,
                        "馬名": "ラップレス",
                        "sex_age": "牡4",
                        "current_evaluation_rank": 1,
                        "market_ability_rank": 1,
                        "ability_band_v2": "A",
                        "ai_current_mark": "◎",
                        "actual_odds": 4.1,
                        "ai_current_reason": "能力Aを土台",
                        "training_market": "B 83.5(16.3)67.2(15.0)",
                    }
                ]
            ),
            "jra",
        )
        result = self.streamlit.last_dataframe
        self.assertIsNotNone(result)
        self.assertIn("B↑ 仕上上々", result.loc[0, "判断材料"])
        self.assertNotIn("83.5", result.loc[0, "判断材料"])

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
                        "class_shift_market": "同級",
                        "class_basis_market": "今回B3 / 前走B3 / B3経験あり",
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
        self.assertEqual(result.loc[0, "クラス変動"], "同級")
        self.assertEqual(result.loc[0, "クラス実績"], "今回B3 / 前走B3 / B3経験あり")

    def test_market_full_table_separates_course_favorable_and_hides_raw_training(self) -> None:
        self.streamlit.last_dataframe = None
        source = pd.DataFrame(
            [
                {
                    "馬番": 7,
                    "馬名": "セブンライト",
                    "馬年齢": "牡4",
                    "ai_current_mark": "◎",
                    "current_evaluation_rank": 1,
                    "ability_band_v2": "A",
                    "market_ability_rank": 1,
                    "market_ability_score": 94,
                    "actual_odds": 5.8,
                    "jockey_display_market": "川田将雅（継）",
                    "weight_market": "56.0kg",
                    "pace_mark_market": "○",
                    "pace_reason_market": "差し向き",
                    "course_development_mark": "○",
                    "course_development_reason": "推定有利馬（7）",
                    "position_path_market": "中団→中団→中団",
                    "training_market": "B 83.5(16.3)67.2(15.0)",
                }
            ]
        )
        before = source.copy(deep=True)

        self.app.render_market_full_table(source, "jra")
        result = self.streamlit.last_dataframe

        self.assertIsNotNone(result)
        self.assertEqual(result.loc[0, "騎手"], "川田将雅（継続）")
        self.assertEqual(result.loc[0, "今回の展開"], "＋ 差し向き")
        self.assertEqual(result.loc[0, "今回のコース材料"], "—")
        self.assertEqual(result.loc[0, "netkeiba推定"], "○ 推定有利馬")
        self.assertEqual(result.loc[0, "調教"], "B↑ 仕上上々")
        self.assertNotIn("83.5", result.to_string())
        pd.testing.assert_frame_equal(source, before)

    def test_market_full_table_hides_year_max_but_keeps_starred_recent_runs_and_core_values(self) -> None:
        self.streamlit.last_dataframe = None
        source = pd.DataFrame(
            [
                {
                    "馬番": 12,
                    "馬名": "フレマチスノーブル",
                    "馬年齢": "牡3",
                    "ai_current_mark": "☆",
                    "current_evaluation_rank": 5,
                    "ability_band_v2": "B",
                    "market_ability_rank": 4,
                    "market_ability_score": 37.4,
                    "actual_odds": 37.8,
                    "jockey_display_market": "安藤洋一（継続）",
                    "weight_market": "54.0kg",
                    "3走前": "★24",
                    "2走前": "14",
                    "前走": "★17",
                    "平均指数": 18.3,
                    "★最高指数": 51.7,
                    "過去1年最高指数": 72,
                    "最高指数": 72,
                    "value_signal": True,
                }
            ]
        )
        before = source.copy(deep=True)

        self.app.render_market_full_table(source, "nar")
        result = self.streamlit.last_dataframe

        self.assertIsNotNone(result)
        self.assertNotIn("最高", result.columns)
        self.assertIn("★", result.columns)
        self.assertEqual(result.loc[0, "★"], "51.7")
        self.assertEqual(result.loc[0, "3走前"], "★24")
        self.assertEqual(result.loc[0, "前走"], "★17")
        for column in (
            "market_ability_score",
            "market_ability_rank",
            "ability_band_v2",
            "current_evaluation_rank",
            "ai_current_mark",
            "value_signal",
        ):
            self.assertEqual(source.loc[0, column], before.loc[0, column])
        pd.testing.assert_frame_equal(source, before)

    def test_market_jockey_display_falls_back_to_detail_and_place_rate(self) -> None:
        row = {
            "騎手詳細": "和田譲【継続】",
            "jockey_market": "和田譲",
            "_jockey_course_place_rate": 30,
        }

        self.assertEqual(self.app.market_jockey_display_text(row), "和田譲（継続・複30%）")

    def test_market_jockey_display_reads_place_rate_from_market_stats(self) -> None:
        row = {
            "騎手詳細": "和田譲【継続】",
            "jockey_market": "和田譲",
            "jockey_course_stats_market": "大井ダ1600｜10%-20%-30%",
        }

        self.assertEqual(self.app.market_jockey_display_text(row), "和田譲（継続・複30%）")

    def test_market_jockey_display_expands_compact_continuation_with_embedded_place_rate(self) -> None:
        row = {
            "jockey_display_market": "矢野貴之（継・複58%）",
            "jockey_market": "矢野貴之",
        }

        self.assertEqual(self.app.market_jockey_display_text(row), "矢野貴之（継続・複58%）")

    def test_market_jockey_display_shows_previous_to_current_with_place_rate(self) -> None:
        row = {
            "騎手詳細": "団野大成 → 川田将雅【乗り替わり】",
            "jockey_market": "川田将雅",
            "_jockey_course_place_rate": 58,
        }

        self.assertEqual(self.app.market_jockey_display_text(row), "団野大成 → 川田将雅（複58%）")

    def test_market_card_restores_weight_change_and_jockey_place_rate_from_sibling_table(self) -> None:
        result = SimpleNamespace(
            overall_table=pd.DataFrame(
                [
                    {
                        "馬番": 10,
                        "馬名": "サンラザール",
                        "ability_band_v2": "A",
                        "market_ability_score": 88.2,
                        "market_ability_rank": 1,
                        "current_evaluation_rank": 1,
                        "ai_current_mark": "◎",
                        "actual_odds": 1.6,
                        "jockey_market": "矢野貴",
                        "jockey_display_market": "矢野貴之（継）",
                        "weight_market": "56.0kg",
                    }
                ]
            ),
            horse_evaluation=pd.DataFrame(
                [
                    {
                        "馬番": 10,
                        "_display_current_load_weight": 56.0,
                        "_display_previous_load_weight": 55.0,
                        "_display_load_weight_change": 1.0,
                        "_jockey_course_place_rate": 58.0,
                        "_jockey_course_starts": 459,
                    }
                ]
            ),
        )

        table = self.app.market_source_table(result)
        source_before = table.copy(deep=True)
        html = self.app.market_horse_card_html(table.iloc[0].to_dict(), "nar")

        self.assertIn("矢野貴之（継続・複58%）", html)
        self.assertIn("56.0kg（前走比+1.0kg）", html)
        self.assertEqual(table.loc[0, "market_ability_score"], 88.2)
        self.assertEqual(table.loc[0, "market_ability_rank"], 1)
        self.assertEqual(table.loc[0, "ability_band_v2"], "A")
        pd.testing.assert_frame_equal(table, source_before)

    def test_market_card_does_not_invent_missing_jockey_place_rate_or_weight_change(self) -> None:
        html = self.app.market_horse_card_html(
            {
                "馬番": 10,
                "馬名": "サンラザール",
                "ability_band_v2": "A",
                "market_ability_score": 88.2,
                "market_ability_rank": 1,
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "actual_odds": 1.6,
                "jockey_display_market": "矢野貴之（継）",
                "weight_market": "56.0kg",
            },
            "nar",
        )

        self.assertIn("矢野貴之（継続）", html)
        self.assertIn("56.0kg", html)
        self.assertNotIn("複", html)
        self.assertNotIn("前走比", html)

    def test_market_card_restores_jockey_change_and_place_rate_when_market_display_is_plain(self) -> None:
        html = self.app.market_horse_card_html(
            {
                "馬番": 12,
                "馬名": "サンバフレイバー",
                "sex_age": "牝7",
                "ability_band_v2": "A",
                "market_ability_score": 51.7,
                "market_ability_rank": 2,
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "actual_odds": 6.9,
                "running_style_market": "差",
                "jockey_market": "和田譲",
                "騎手詳細": "和田譲【継続】",
                "_jockey_course_place_rate": 30,
                "weight_market": "54.0kg",
            },
            "nar",
        )

        self.assertIn("差｜和田譲（継続・複30%）｜54.0kg", html)

    def test_market_source_table_merges_jockey_detail_from_sibling_table_for_display(self) -> None:
        result = SimpleNamespace(
            overall_table=pd.DataFrame(
                [
                    {
                        "馬番": 12,
                        "馬名": "サンバフレイバー",
                        "ability_band_v2": "A",
                        "market_ability_score": 51.7,
                        "market_ability_rank": 2,
                        "current_evaluation_rank": 1,
                        "jockey_market": "和田譲",
                    }
                ]
            ),
            horse_evaluation=pd.DataFrame(
                [
                    {
                        "馬番": 12,
                        "騎手詳細": "和田譲【継続】",
                        "_jockey_course_place_rate": 30,
                    }
                ]
            ),
        )

        table = self.app.market_source_table(result)
        html = self.app.market_horse_card_html(table.iloc[0].to_dict(), "nar")

        self.assertEqual(table.loc[0, "騎手詳細"], "和田譲【継続】")
        self.assertIn("和田譲（継続・複30%）", html)

    def test_market_horse_card_summarizes_training_and_stable_comment(self) -> None:
        html = self.app.market_horse_card_html(
            {
                "馬番": 4,
                "馬名": "コメントスター",
                "sex_age": "牡5",
                "ability_band_v2": "A",
                "market_ability_score": 91,
                "market_ability_rank": 2,
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "ai_current_reason": "能力Aを土台",
                "actual_odds": 3.7,
                "jockey_display_market": "川田将雅（継）",
                "weight_market": "56.0kg",
                "running_style_market": "差し",
                "training_market": "A 83.5(16.3)67.2(15.0)",
                "stable_comment_market": "順調に仕上がって好気配。ここも期待できる。",
            },
            "jra",
        )

        self.assertIn("＋ 調教A↑ 動き抜群", html)
        self.assertIn("厩舎コメント：↑ 好気配", html)
        self.assertIn("厩舎コメント全文", html)
        self.assertNotIn("83.5", html)

    def test_nar_optional_jockey_page_is_fetched_as_raw_html(self) -> None:
        race_id = "202647081305"
        specs = self.app.build_nar_generated_url_specs(race_id)
        jockey = next(spec for spec in specs if spec.kind == "jockey")
        self.assertFalse(jockey.required)
        self.assertIn("mode=courseanalysis", jockey.url)
        self.assertIn("cid=2", jockey.url)
        html = f"""<html><head>
        <link rel="canonical" href="{jockey.url}">
        <title>名古屋ダ1500mが得意な騎手 データ分析</title></head>
        <body class="race_data_list"><table id="table_sort_back">
        <tr><th>出走回数</th><th>複勝率</th></tr></table></body></html>"""
        response = SimpleNamespace(
            status_code=200,
            apparent_encoding="utf-8",
            encoding="utf-8",
            text=html,
        )
        with patch.object(self.app.requests, "get", return_value=response, create=True):
            html_files, file_names = self.app.fetch_generated_html([jockey], race_id)
        self.assertEqual(html_files, {"jockey": html})
        self.assertTrue(file_names["jockey"].endswith(f"_{race_id}.html"))
        self.assertFalse(html_files["jockey"].lstrip().startswith("{"))

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
