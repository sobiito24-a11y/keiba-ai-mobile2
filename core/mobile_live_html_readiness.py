"""Source-only JRA HTML completeness gate for the Mobile upload workflow.

The HTML classifier verifies page type/race identity, but that is not proof
that Safari captured numeric speed-index cells. Reject fully/mostly empty
ability inputs before allowing a misleading completed prediction view.
This does not alter the notebook's calculations or independent AI model.
"""
from __future__ import annotations

from math import isfinite
from collections.abc import Mapping

from .prediction_table_ui import horse_key


ABILITY_KEYS = (
    "_ver3_ability_core", "ver3_ability_core",
    "jra_pure_ability_score",
)


def _number(raw):
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if isfinite(value) else None


def evaluate_live_jra_result(result):
    """Return (total, ability_present) for the already parsed HTML result.

    Compare only numbers from the actual JRA result, never formal ranks,
    odds, post-race outcomes or an unrelated saved .keiba archive.
    """
    if getattr(result, "race_mode", None) != "jra":
        return 0, 0
    table = getattr(result, "overall_table", None)
    rows = table.to_dict("records") if hasattr(table, "to_dict") else []
    horses = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        no = horse_key(row)
        if not no:
            continue
        good = any(_number(row.get(k)) is not None for k in ABILITY_KEYS)
        horses[no] = good or horses.get(no, False)
    return len(horses), sum(horses.values())


def require_live_jra_ability(result):
    """Fail closed for unusable uploaded HTML; avoid fake all-unavailable ranks."""
    if getattr(result, "race_mode", None) != "jra":
        return None
    total, present = evaluate_live_jra_result(result)
    if not total:
        raise ValueError(
            "JRAのタイム指数HTMLから出走馬を確認できません。"
            "同一レースのタイム指数・競馬新聞・脚質分析HTMLを再アップロードしてください。"
        )
    # Independent AI also requires at least half the field with usable
    # ability values; any fewer would always yield a meaningless grade.
    if present * 2 < total:
        raise ValueError(
            f"タイム指数HTMLの数値を{present}/{total}頭しか取得できませんでした。"
            "HTMLの種類・レースIDが揃っていても指数の中身が欠けています。"
            "iPhone Safariでnetkeibaのタイム指数が全頭表示されていることを確認し、"
            "ページを読み込んだ状態でHTMLを保存し直してください。"
            "同じレースの競馬新聞・脚質分析HTMLと一緒に再アップロードしてください。"
            "馬名だけから純能力やSABCDを推測して補いません。"
        )
    if present < total:
        return (
            f"一部の純能力入力が欠損しています（{present}/{total}頭分確認）。"
            "指数がない馬は未取得のまま表示します。"
            "全頭表示のタイム指数HTMLを再保存すると改善する場合があります。"
        )
    return None
