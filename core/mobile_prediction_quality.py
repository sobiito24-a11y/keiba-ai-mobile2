"""Non-scoring, read-only input diagnosis for the Mobile race comparison UI.

A display-only warning is preferable to inventing an ability value, an
independent-AI grade, a frame, or a backdated pre-start prediction.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from .prediction_table_ui import horse_key

_JRA_ABILITY = ("jra_pure_ability_score", "ver3_ability_core", "_ver3_ability_core",
                "market_ability_score")
_NAR_ABILITY = ("nar_pure_ability_score", "market_ability_score",
                "ability_value", "saved_ability_value", "ver3_ability_core")


def _map(value):
    return value if isinstance(value, Mapping) else {}


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) else None


def _saved_by_horse(result):
    """Match by stored horse number, without filling a missing score from odds."""
    source = {}
    for key in ("overall_table", "horse_evaluation"):
        table = getattr(result, key, None)
        if table is None or not hasattr(table, "to_dict"):
            continue
        for row in table.to_dict("records"):
            if not isinstance(row, Mapping):
                continue
            no = horse_key(row)
            if not no:
                continue
            record = source.setdefault(no, {})
            for name, value in row.items():
                if _num(value) is not None or (
                        name not in record and value is not None):
                    record[name] = value
    return source


def diagnose(result, view):
    """Return factual (severity, message) notices; never change result/view.

    An unknown grade may be correct: the frozen independent AI is only allowed
    when generated before post time with exact race+horse identity. Never call
    the model again while rendering historical or post-start races.
    """
    horses = [h for h in view or () if isinstance(h, Mapping)]
    if not horses:
        return ()
    mode = getattr(result, "race_mode", None)
    fields = _JRA_ABILITY if mode == "jra" else _NAR_ABILITY
    source = _saved_by_horse(result)
    n = len(horses)
    saved = displayed = framed = graded = 0
    for h in horses:
        raw = _map(source.get(str(h.get("no") or "")))
        if any(_num(raw.get(key)) is not None for key in fields):
            saved += 1
        metrics = _map(_map(h.get("final_metrics")).get("ability"))
        if _num(metrics.get("value")) is not None or _num(h.get("ability")) is not None:
            displayed += 1
        if _num(h.get("frame")) is not None:
            framed += 1
        if _map(h.get("independent_ai_sabcd")).get("grade") in ("S", "A", "B", "C", "D"):
            graded += 1

    notes = []
    if saved == 0:
        notes.append((
            "error",
            f"入力不足：{n}頭すべての純能力指数を元の保存予測から確認できません。"
            "馬名・出走情報だけでは正しい新SABCDは計算できません。"
            + ("中央HTMLアップロードの場合は、netkeibaで指数が全頭表示された状態の"
             "タイム指数HTMLを保存し直し、同じレースの競馬新聞・脚質分析HTMLと"
             "一緒にアップロードしてください。"
             if getattr(result, "_jra_live_display", False) else
             "保存済みレースの場合は指数を記録した元データを確認してください。")
            + "既存の順位や結果から指数を推測して補完しません。",
        ))
    elif displayed == 0:
        notes.append((
            "error",
            f"表示連携の要確認：保存予測には{saved}/{n}頭分の純能力データがありますが、"
            "Mobileの馬別比較欄に反映されていません。"
            "元データは上書きせず、同じレースの保存ファイルと表示経路の照合が必要です。",
        ))
    elif saved < n or displayed < n:
        notes.append((
            "warning",
            f"一部入力不足：純能力の元データは{saved}/{n}頭、一覧に表示された値は"
            f"{displayed}/{n}頭です。欠けた馬の指数・ランクは推測しません。",
        ))

    pred = _map(_map(getattr(result, "debug_info", None)).get("independent_ai_v3"))
    if graded == 0:
        if pred.get("status") == "insufficient":
            reason = "独立AIが必要とする能力入力の不足などにより、参考評価を生成できていません。"
        elif not pred:
            reason = "保存された独立AIの発走前予測記録がありません。"
        elif pred.get("origin") != "new_prediction":
            reason = "保存済みの発走前評価ではなく、後から再算出された参考情報です。"
        elif pred.get("status") != "reference":
            reason = "独立AIの参考評価が利用可能な状態ではありません。"
        else:
            reason = ("保存済みの発走時刻・予測時刻・馬番・馬名・頭数・レースIDの"
                      "厳密な一致を確認できません。")
        notes.append((
            "warning",
            "統合SABCDは判定不可：" + reason +
            " 過去の評価を発走前の予測として再作成せず、既存の予測・正式印も変更しません。",
        ))
    elif graded < n:
        notes.append((
            "warning",
            f"統合SABCDの保存済み発走前照合は{graded}/{n}頭のみ。"
            "不一致の馬は判定不可のままにします。",
        ))
    if mode == "jra" and framed == 0:
        notes.append((
            "warning",
            "枠番が全頭未取得：元の競馬新聞または出走表の枠番データを確認してください。"
            "同一レースの枠番と馬名を照合できる場合のみ表示し、推測で色を付けません。",
        ))
    return tuple(notes)
