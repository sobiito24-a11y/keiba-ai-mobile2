from __future__ import annotations

import sys
import types
import unittest
import warnings

import pandas as pd


def _install_optional_dependency_stubs() -> None:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.get = lambda *args, **kwargs: None
        sys.modules["requests"] = requests
    if "bs4" not in sys.modules:
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = lambda *args, **kwargs: None
        sys.modules["bs4"] = bs4
    if "IPython.display" not in sys.modules:
        ipython = types.ModuleType("IPython")
        display_mod = types.ModuleType("IPython.display")
        display_mod.display = lambda *args, **kwargs: None
        display_mod.HTML = lambda value="": value
        ipython.display = display_mod
        sys.modules["IPython"] = ipython
        sys.modules["IPython.display"] = display_mod


_install_optional_dependency_stubs()

from core.nar_notebook_logic import (  # noqa: E402
    add_final_marks,
    add_purchase_value_columns,
    parse_index_cell,
    prepare_nar_display_columns,
)
import core.nar_notebook_logic as nar_logic  # noqa: E402
import core.nar_json_input as nar_input  # noqa: E402
import core.jra_notebook_logic as jra_logic  # noqa: E402
from render import mobile_png  # noqa: E402


class NarDataShortageTest(unittest.TestCase):
    def test_empty_newspaper_series_does_not_assign_into_float_column(self) -> None:
        frame = pd.DataFrame(
            {
                "_display_previous_load_weight": pd.Series([55.0], dtype="float64"),
                "_display_previous_load_weight_newspaper": pd.Series([None], dtype="object"),
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            result = nar_logic._coalesce_newspaper_column(frame, "_display_previous_load_weight")
        self.assertEqual(str(result["_display_previous_load_weight"].dtype), "float64")
        self.assertEqual(result.loc[0, "_display_previous_load_weight"], 55.0)
        self.assertNotIn("_display_previous_load_weight_newspaper", result.columns)

    def test_empty_newspaper_series_does_not_assign_into_integer_column(self) -> None:
        frame = pd.DataFrame(
            {
                "_days_since_last": pd.Series([28], dtype="int64"),
                "_days_since_last_newspaper": pd.Series([None], dtype="object"),
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            result = nar_logic._coalesce_newspaper_column(frame, "_days_since_last")
        self.assertEqual(str(result["_days_since_last"].dtype), "int64")
        self.assertEqual(result.loc[0, "_days_since_last"], 28)

    def test_structured_newspaper_value_promotes_only_its_nan_column(self) -> None:
        frame = pd.DataFrame(
            {
                "_past_class_labels": pd.Series([float("nan")], dtype="float64"),
                "_past_class_labels_newspaper": pd.Series([[]], dtype="object"),
                "unrelated_numeric": pd.Series([1.5], dtype="float64"),
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            result = nar_logic._coalesce_newspaper_column(frame, "_past_class_labels")
        self.assertEqual(result.loc[0, "_past_class_labels"], [])
        self.assertEqual(str(result["_past_class_labels"].dtype), "object")
        self.assertEqual(str(result["unrelated_numeric"].dtype), "float64")

    def test_index_cell_ignores_hidden_sort_value_when_display_is_missing(self) -> None:
        class FakeAnchor:
            def __init__(self) -> None:
                self.href = "https://db.netkeiba.com/race//"

            def get(self, key, default=None):
                return self.href if key == "href" else default

            def __getitem__(self, key):
                if key == "href":
                    return self.href
                raise KeyError(key)

        class FakeCell:
            def __init__(self) -> None:
                self.anchor = FakeAnchor()

            def find(self, *args, **kwargs):
                return self.anchor

        original_visible_text = nar_logic.visible_text
        try:
            nar_logic.visible_text = lambda element: "-" if isinstance(element, FakeAnchor) else "100 -"
            parsed = parse_index_cell(FakeCell())
        finally:
            nar_logic.visible_text = original_visible_text

        self.assertIsNone(parsed["value"])

    def test_shortage_horse_does_not_receive_mark_or_ai_score(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "馬番": 1,
                    "馬名": "NoLocalIndex",
                    "AI点": pd.NA,
                    "_地方指数データ不足": True,
                    "単勝オッズ": 4.1,
                    "人気": 2,
                    "脚質": "差",
                    "騎手": "木澤奨(替)",
                }
            ]
        )

        marked = add_final_marks(frame)
        purchase = add_purchase_value_columns(marked)
        prepared = prepare_nar_display_columns(purchase)

        self.assertEqual(prepared.loc[0, "AI点"], "データ不足")
        self.assertEqual(prepared.loc[0, "最終印"], "")
        self.assertEqual(prepared.loc[0, "購入判定"], "データ不足")
        self.assertEqual(prepared.loc[0, "騎手"], "木澤奨(替)")

    def test_pd_na_text_helpers_do_not_use_boolean_context(self) -> None:
        row = {
            "最終印": pd.NA,
            "馬名": pd.NA,
            "騎手": pd.NA,
            "AI点": pd.NA,
            "_地方指数データ不足": pd.NA,
        }

        self.assertEqual(nar_logic._horse_mark_value(pd.Series(row)), "")
        self.assertEqual(nar_logic._ver30_ai_point_display(pd.Series(row)), "-")
        self.assertEqual(mobile_png._pick(row, "騎手"), "")
        self.assertEqual(mobile_png._clean(pd.NA), "")
        self.assertEqual(mobile_png._join_nonempty([pd.NA, "A", ""], sep="/"), "A")

    def test_nar_display_weight_and_jockey_details_from_display_only_fields(self) -> None:
        switched = pd.Series(
            {
                "_current_load_weight": 57.0,
                "_display_previous_load_weight": 56.0,
                "_display_load_weight_change": 1.0,
                "_current_jockey": "今回騎手",
                "_display_previous_jockey": "前走騎手",
                "_display_jockey_changed": True,
            }
        )
        continued = pd.Series(
            {
                "_current_load_weight": 56.0,
                "_display_previous_load_weight": 56.0,
                "_display_load_weight_change": 0.0,
                "_current_jockey": "継続騎手",
                "_display_previous_jockey": "継続騎手",
                "_display_jockey_changed": False,
            }
        )
        missing_previous = pd.Series({"斤量": "55.0", "騎手": "不明騎手"})

        self.assertEqual(nar_logic._ver30_load_weight_detail(switched), "57.0kg（前走比＋1.0kg）")
        self.assertEqual(nar_logic._ver30_jockey_detail(switched), "前走騎手 → 今回騎手【乗り替わり】")
        self.assertEqual(nar_logic._ver30_load_weight_detail(continued), "56.0kg（前走比±0.0kg）")
        self.assertEqual(nar_logic._ver30_jockey_detail(continued), "継続騎手【継続】")
        self.assertEqual(nar_logic._ver30_load_weight_detail(missing_previous), "55.0kg（前走データなし）")
        self.assertEqual(nar_logic._ver30_jockey_detail(missing_previous), "不明騎手【前走データなし】")

    def test_nar_jockey_abbreviated_names_are_continuation(self) -> None:
        examples = [
            ("櫻井光", "櫻井光輔"),
            ("池谷匠", "池谷匠翔"),
            ("山本聡", "山本聡"),
        ]
        for current, previous in examples:
            with self.subTest(current=current, previous=previous):
                self.assertEqual(nar_logic.nar_jockey_changed_value(current, previous), False)
                self.assertEqual(nar_input._nar_jockey_changed_value(current, previous), False)
                self.assertEqual(
                    nar_logic._ver30_jockey_detail(
                        pd.Series({"_current_jockey": current, "_display_previous_jockey": previous})
                    ),
                    f"{current}【継続】",
                )

    def test_nar_jockey_different_names_are_switch(self) -> None:
        self.assertEqual(nar_logic.nar_jockey_changed_value("山本政", "山本聡"), True)
        self.assertEqual(nar_input._nar_jockey_changed_value("山本政", "山本聡"), True)
        self.assertEqual(
            nar_logic._ver30_jockey_detail(
                pd.Series({"_current_jockey": "山本政", "_display_previous_jockey": "山本聡"})
            ),
            "山本聡 → 山本政【乗り替わり】",
        )

    def test_nar_jockey_surname_only_is_pending_not_continuation(self) -> None:
        self.assertEqual(nar_logic.nar_jockey_changed_value("山本聡", "山本"), "pending")
        self.assertEqual(nar_input._nar_jockey_changed_value("山本聡", "山本"), "pending")
        self.assertEqual(
            nar_logic._ver30_jockey_detail(
                pd.Series({"_current_jockey": "山本聡", "_display_previous_jockey": "山本"})
            ),
            "山本聡【判定保留】",
        )

    def test_nar_jockey_missing_values_are_missing_previous_data(self) -> None:
        self.assertIsNone(nar_logic.nar_jockey_changed_value("山本聡", ""))
        self.assertIsNone(nar_input._nar_jockey_changed_value("山本聡", pd.NA))
        self.assertEqual(
            nar_logic._ver30_jockey_detail(pd.Series({"_current_jockey": "山本聡", "_display_previous_jockey": pd.NA})),
            "山本聡【前走データなし】",
        )

    def test_jra_jockey_change_display_is_unchanged(self) -> None:
        self.assertEqual(
            jra_logic._ver30_jockey_detail(
                pd.Series({"_current_jockey": "櫻井光", "_previous_jockey": "櫻井光輔", "_jockey_changed": True})
            ),
            "櫻井光輔 → 櫻井光【乗り替わり】",
        )

    def test_running_style_display_normalization(self) -> None:
        self.assertEqual(nar_logic._ver30_display_running_style("逃"), "逃げ")
        self.assertEqual(nar_logic._ver30_display_running_style("先行"), "先行")
        self.assertEqual(nar_logic._ver30_display_running_style("差し"), "差し")
        self.assertEqual(nar_logic._ver30_display_running_style("追い込み"), "追込")
        self.assertEqual(mobile_png._display_running_style({"脚質": "追"}), "追込")

    def test_colab_nar_newspaper_html_supplies_previous_display_details(self) -> None:
        class FakeSoup:
            def get_text(self, *args, **kwargs):
                return "地方競馬新聞"

            def select_one(self, selector):
                return None

        original_parser = nar_logic.parse_uploaded_nar_newspaper_html
        original_soup = nar_logic.BeautifulSoup
        try:
            nar_logic.BeautifulSoup = lambda *args, **kwargs: FakeSoup()
            nar_logic.parse_uploaded_nar_newspaper_html = lambda html: {
                "race": {"race_name": "テスト", "race_data_1": ""},
                "horses": [
                    {
                        "horse_number": "8",
                        "horse_name": "スピリチュアル",
                        "weight": "54.0",
                        "jockey": "山本聡",
                        "previous_weight": "54.0",
                        "previous_jockey": "山本聡",
                        "horse_weight": "450(0)",
                    }
                ],
            }
            frame = pd.DataFrame(
                [
                    {
                        "馬番": 8,
                        "馬名": "スピリチュアル",
                        "馬体重": "",
                        "馬場適性": "",
                        "_same_going_high": None,
                        "_same_going_count": 0,
                        "_class_shift": "",
                    }
                ]
            )

            result, _, info = nar_logic.apply_nar_newspaper_html_features(frame, {}, "<html></html>")
        finally:
            nar_logic.parse_uploaded_nar_newspaper_html = original_parser
            nar_logic.BeautifulSoup = original_soup

        row = result.iloc[0]
        self.assertEqual(info["previous_detail_count"], 1)
        self.assertEqual(row["_display_current_load_weight"], 54.0)
        self.assertEqual(row["_display_previous_load_weight"], 54.0)
        self.assertEqual(row["_display_load_weight_change"], 0.0)
        self.assertEqual(row["_display_current_jockey"], "山本聡")
        self.assertEqual(row["_display_previous_jockey"], "山本聡")
        self.assertEqual(row["_display_jockey_changed"], False)


if __name__ == "__main__":
    unittest.main()
