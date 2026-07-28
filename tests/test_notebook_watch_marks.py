from __future__ import annotations

import unittest

import pandas as pd

from core import jra_notebook_logic, nar_notebook_logic


def _candidate_frame(*, nar: bool = False) -> pd.DataFrame:
    rows = []
    for number in range(1, 6):
        rows.append(
            {
                "馬番": number,
                "馬名": f"テスト{number}",
                "最終印": "",
                "_最終印順": 99,
                "_最終印点": 100 - number,
                "AI点": 95 - number,
                "総合評価点": 100 - number,
                "市場反映勝率": 20 - number,
                "単勝期待値": 1.2 if number <= 3 else 0.8,
                "単勝オッズ": 10 + number,
                "クラス変動": "クラス降級" if number == 1 else "",
                "クラス根拠": "",
                "評価/検討材料": "高指数 / 距離実績",
                "調教/評価/検討材料": "高指数 / コース実績",
                "印理由": "",
                "展開印": "展" if number in (2, 3) else "",
            }
        )
    frame = pd.DataFrame(rows)
    if nar:
        frame["_地方指数データ不足"] = False
    return frame


class NotebookWatchMarksTest(unittest.TestCase):
    def test_nar_apply_watch_marks_limits_hole_marks_to_two(self) -> None:
        result = nar_notebook_logic.apply_watch_marks(_candidate_frame(nar=True), race_type="nar")

        self.assertLessEqual(int(result["最終印"].eq("✓").sum()), 2)
        self.assertEqual(int(result["印理由"].str.contains("穴候補", na=False).sum()), 2)
        self.assertGreaterEqual(int(result["印理由"].str.contains("注意馬", na=False).sum()), 1)

    def test_nar_data_shortage_is_not_promoted_to_watch_mark(self) -> None:
        frame = _candidate_frame(nar=True)
        frame.loc[0, "_地方指数データ不足"] = True

        result = nar_notebook_logic.apply_watch_marks(frame, race_type="nar")

        self.assertNotEqual(result.loc[0, "最終印"], "✓")

    def test_jra_apply_watch_marks_limits_hole_marks_to_two(self) -> None:
        result = jra_notebook_logic.apply_watch_marks(_candidate_frame(), race_type="jra")

        self.assertLessEqual(int(result["最終印"].eq("✓").sum()), 2)
        self.assertEqual(int(result["印理由"].str.contains("穴候補", na=False).sum()), 2)
        self.assertGreaterEqual(int(result["印理由"].str.contains("注意馬", na=False).sum()), 1)


if __name__ == "__main__":
    unittest.main()
