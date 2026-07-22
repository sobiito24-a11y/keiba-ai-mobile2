from __future__ import annotations

import sys
import types
import unittest

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


class NarDataShortageTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
