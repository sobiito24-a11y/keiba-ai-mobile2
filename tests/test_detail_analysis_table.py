from __future__ import annotations

import importlib.util
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

    def set_page_config(self, **_kwargs) -> None:
        return None

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, value, **_kwargs) -> None:
        self.last_dataframe = value.copy()


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


if __name__ == "__main__":
    unittest.main()
