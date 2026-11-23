"""Source-limited, display-only review of C/D horses and model input gaps.

Only the saved pre-start independent-AI projection may trigger the C/D
second look. No post-race results, odds, marks, ranks, or purchases are read.
All HTML is escaped and all warnings are non-scoring.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from html import escape
import re
import unicodedata

from .independent_ai_sabcd import MODEL_ID

_FINISH = re.compile(r"([1-9]\d*)(?:着)?")
_MISSING = frozenset(("", "-", "—", "未取得", "未確認", "不明", "None"))
_FOREIGN_VENUES = (
    "海外", "香港", "沙田", "シャティン", "メイダン", "ドバイ", "アスコット",
    "ロンシャン", "シャンティイ", "サンタアニタ", "チャーチルダウンズ",
    "キングアブドゥルアジーズ", "メルボルン", "ランドウィック",
)


def _map(value):
    return value if isinstance(value, Mapping) else {}


def _text(value):
    return str(value if value is not None else "").strip()


def _date(value):
    try:
        return date.fromisoformat(_text(value)[:10])
    except (TypeError, ValueError):
        return None


def _esc(value):
    return escape(_text(value), quote=True)


def previous_top3_evidence(horse):
    """A strictly dated, same-horse previous finish; never a grade adjustment."""
    independent = _map(horse.get("independent_ai_sabcd"))
    grade = independent.get("grade")
    if (grade not in ("C", "D")
            or independent.get("source_model_id") != MODEL_ID
            or _map(horse.get("unified_sabcd")).get("grade") != grade):
        return None

    ctx = _map(horse.get("race_context"))
    today = _date(ctx.get("race_date") or ctx.get("date"))
    if today is None:
        return None
    facts = _map(horse.get("explorer_facts"))
    for run in facts.get("runs") or ():
        if not isinstance(run, Mapping) or run.get("label") != "前走":
            continue
        when = _date(run.get("date"))
        if when is None or when >= today:
            return None
        raw_finish = unicodedata.normalize("NFKC", _text(run.get("finish")))
        match = _FINISH.fullmatch(raw_finish)
        if not match:
            return None
        finish = int(match.group(1))
        if not 1 <= finish <= 3:
            return None
        return {
            "grade": grade,
            "finish": finish,
            "date": when.isoformat(),
            "venue": _text(run.get("venue")),
            "class_raw": _text(run.get("class_raw")),
        }
    return None


def second_look_html(horse):
    """Only horse-detail HTML; never an inline rank tag or selection."""
    item = previous_top3_evidence(horse)
    if not item:
        return ""
    venue = item["venue"] if item["venue"] not in _MISSING else "開催場未取得"
    cls = item["class_raw"] if item["class_raw"] not in _MISSING else "クラス未取得"
    return (
        '<section class="detail-second-look" data-second-look="previous-top3">'
        '<h4>C・D再確認：前走3着以内</h4>'
        '<p>保存された前走：' + _esc(item["date"]) + ' ' + _esc(venue)
        + '、<b>' + str(item["finish"]) + '着</b>。前走クラス・競走名：' + _esc(cls) + '。</p>'
        '<p class="detail-note">前走で好走した事実を再確認するための参考材料です。'
        '前走頭数・相手レベルが未確認なら優劣を推定しません。'
        'SABCDランク、順位、正式印、買い目は変更しません。</p>'
        '</section>'
    )


def _foreign_exposure(horse):
    profile = _map(horse.get("profile"))
    for run in [*(profile.get("runs") or ()), *(profile.get("extended_history") or ())]:
        if not isinstance(run, Mapping):
            continue
        venue = _text(run.get("venue"))
        if venue and any(part in venue for part in _FOREIGN_VENUES):
            return venue
    return None


def _class_notice(horse):
    profile, ctx = _map(horse.get("profile")), _map(horse.get("race_context"))
    shift = _text(profile.get("class_shift"))
    old_label = unicodedata.normalize("NFKC", _text(ctx.get("class_label")))
    raw = unicodedata.normalize("NFKC", _text(ctx.get("race_data2")))
    if horse.get("mode") == "jra" and re.fullmatch(r"[ABCD]級", old_label):
        actual = re.search(r"([123]勝クラス|[23]歳未勝利|未勝利|新馬)", raw)
        if actual:
            return (f"旧クラスラベル「{old_label}」と出走条件「{actual.group(1)}」は"
                    "異なる分類です。旧ラベルをクラス比較の根拠にしません。")
    if not shift or shift.startswith("判定不可"):
        return "前走と今回のクラス水準：比較根拠不足。格上・格下を断定しません。"
    return f"クラス比較の保存済み参考判定：{shift}。独立AIの専用特徴量には未使用。"


def _input_notice(horse):
    quality = _map(horse.get("independent_ai_input_quality"))
    if not quality.get("verified"):
        return "独立AIの入力明細を完全には確認できません。欠損の有無は判定保留です。"
    missing = quality.get("missing") or ()
    names = {
        "pure": "純能力",
        "distance_index": "距離指数", "course_index": "コース指数",
        "recent3_mean": "近3走平均", "jockey_place_rate": "騎手複勝率",
        "jockey_sample_size": "騎手母数", "rest_days": "休養日数",
        "load_change": "斤量増減",
    }
    missing_text = "・".join(names.get(key, key) for key in missing if key != "corner4")
    fourth = quality.get("corner4")
    if fourth is None:
        fourth_notice = "独立AIへの4角予測入力は未取得。欠損補完で推論されています。"
    else:
        fourth_notice = f"独立AIに渡された4角予測は{fourth}番手（実際の通過位置ではありません）。"
    if missing_text:
        fourth_notice += " その他の入力不足：" + missing_text + "。"
    return fourth_notice


def input_quality_html(horse):
    """Expandable source-quality notes, not a grade confidence correction."""
    if not _map(horse.get("independent_ai_sabcd")):
        return ""
    overseas = _foreign_exposure(horse) if horse.get("mode") == "jra" else None
    if horse.get("mode") == "jra":
        if overseas:
            foreign = (f"保存された過去走に海外開催「{overseas}」あり。"
                       "海外実績を単独評価する特徴量は独立AIにありません。")
        else:
            foreign = ("保存された直近の履歴のみでは海外出走の有無を断定できません。"
                       "海外実績の完全性は未確認です。")
    else:
        foreign = "海外実績の個別照合はこのNAR表示では行っていません。"
    rows = [
        ("クラス・相手水準", _class_notice(horse)),
        ("4角・独立AI入力", _input_notice(horse)),
        ("海外実績", foreign),
    ]
    body = "".join("<div><dt>" + _esc(label) + "</dt><dd>" + _esc(note) +
                   "</dd></div>" for label, note in rows)
    return (
        '<details class="detail-input-quality"><summary>入力品質の確認'
        '（クラス・4角・海外）</summary><dl class="detail-research-facts">' + body + '</dl>'
        '<p class="detail-note">欠損や不一致がある参考値を過信しないための表示です。'
        '4角の1〜2番手程度の予測誤差では評価を変更しません。'
        '独立AIのモデル係数・SABCD・正式印・買い目は一切変更しません。</p>'
        '</details>'
    )
