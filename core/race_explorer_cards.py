"""Read-only pickup cards and the shared, unmarked horse detail panel."""
from collections.abc import Mapping
import re

from .final_candidate_selection import formal_score, select_indices
from .prediction_table_ui import number
from .race_explorer_common import index_html, number_badge, plain, value


RUN_LABELS = ("3走前", "2走前", "前走")
_JUDGEMENT_MARKS = re.compile(r"[◎○▲✔✓△][\ufe0e\ufe0f]?\s*")


def _mapping(item):
    return item if isinstance(item, Mapping) else {}


def _facts(horse):
    return _mapping(horse.get("explorer_facts"))


def _metrics(horse, facts):
    return _mapping(facts.get("metrics")) or _mapping(horse.get("final_metrics"))


def _unmarked(item):
    """Hide old judgement glyphs without modifying their saved source."""
    return _JUDGEMENT_MARKS.sub("", str(item)) if item is not None else None


def _items(item):
    return item if isinstance(item, (list, tuple)) else []


def _ability(horse, metrics):
    return _mapping(metrics.get("ability")) or dict(
        value=horse.get("ability"), rank=horse.get("ability_rank"))


def _corner(horse, metrics):
    corner = number(metrics.get("corner", horse.get("corner")))
    return value(corner) + "番手" if corner is not None else "未取得"


def _state_item(label, content):
    return ('<span class="pickup-state-item"><small>' + plain(label) +
            '</small><span>' + value(content) + '</span></span>')


def pickup_html(view):
    """Use the existing Top5/reference membership, presented in horse-number order."""
    selected = select_indices(view, "no")
    if not selected:
        return '<p class="no-data">保存されたレースピックアップはありません</p>'
    cards = []
    for index in selected:
        horse = view[index]
        facts = _facts(horse)
        metrics = _metrics(horse, facts)
        no = plain(horse.get("no") if horse.get("no") is not None else "")
        name = value(horse.get("name"))
        jockey = facts.get("current_jockey")
        if jockey is None:
            jockey = horse.get("jockey")
        state = []
        if horse.get("mode") == "jra":
            state.append(_state_item("調教", facts.get("training")))
        state.extend(_state_item(label, content) for label, content in (
            ("前走間隔", facts.get("rest_label")),
            ("斤量", facts.get("weight_label")),
            ("前走比", facts.get("weight_delta_label")),
            ("騎手", facts.get("jockey_change")),
        ))
        features = ''.join('<span>' + value(_unmarked(item)) + '</span>'
                           for item in _items(facts.get("features"))[:3])
        cards.append(
            '<button type="button" class="pickup-card" data-horse-open="' + no +
            '" aria-expanded="false" aria-controls="horse-detail-' + no +
            '" aria-label="' + name + 'の詳細を開く">'
            '<span class="pickup-header">' + number_badge(horse) +
            '<span class="pickup-identity"><strong>' + name + '</strong>'
            '<span class="pickup-basics">' + value(horse.get("age")) +
            ' · ' + value(jockey) + '</span></span></span>'
            '<span class="pickup-position"><span>想定脚質 ' +
            value(_unmarked(metrics.get("style", horse.get("style")))) +
            '</span><span>4角想定 ' + _corner(horse, metrics) + '</span></span>'
            '<span class="pickup-state">' + ''.join(state) + '</span>' +
            ('<span class="pickup-features">' + features + '</span>' if features else '') +
            '<span class="pickup-ability"><small>純能力指数</small><b>' +
            value(_ability(horse, metrics).get("value")) + '</b></span>'
            '<span class="pickup-open">詳細を開く <span aria-hidden="true">↗</span></span>'
            '</button>')
    return '<div class="pickup-grid">' + ''.join(cards) + '</div>'


def _definition_list(items, css_class):
    return '<dl class="' + css_class + '">' + ''.join(
        '<div><dt>' + plain(label) + '</dt><dd>' + value(content) + '</dd></div>'
        for label, content in items) + '</dl>'


def _stat(label, content):
    return '<div class="detail-stat"><small>' + plain(label) + '</small>' + content + '</div>'


def _runs_html(facts):
    by_label = {}
    for run in _items(facts.get("runs")):
        if isinstance(run, Mapping) and run.get("label") in RUN_LABELS:
            by_label.setdefault(run["label"], run)
    cards = []
    for label in RUN_LABELS:
        run = by_label.get(label, {})
        cards.append(
            '<article class="detail-run"><h5>' + plain(label) + '</h5>'
            '<div class="detail-run-result"><span><small>着順</small><b>' +
            value(run.get("finish")) + '</b></span><span><small>タイム指数</small><b>' +
            value(run.get("time_index")) +
            (' <span class="maximum-match" title="保存された最高指数と一致">★</span>'
             if run.get("is_maximum") else '') + '</b></span></div>' +
            _definition_list((("開催日", run.get("date")),
                              ("開催条件", run.get("condition")),
                              ("クラス", run.get("class_raw"))), "detail-run-facts") + '</article>')
    return '<div class="detail-runs">' + ''.join(cards) + '</div>'


def _conditions_html(facts):
    records = []
    for record in _items(facts.get("condition_records")):
        if not isinstance(record, Mapping):
            continue
        text = record.get("text")
        if not text:
            starts, top3 = number(record.get("starts")), number(record.get("top3"))
            label = str(record.get("label") or "条件未取得")
            if (starts is not None and top3 is not None and starts.is_integer()
                    and top3.is_integer() and 0 <= top3 <= starts):
                text = f"{label}：{int(starts)}戦{int(top3)}回3着以内"
            else:
                text = label + "：未取得"
        unknown = number(record.get("unknown"))
        records.append('<li><span>' + value(text) + '</span><small>対象：' +
                       value(record.get("scope")) +
                       (' / 着順未取得 ' + value(unknown) + '走' if unknown else '') +
                       '</small></li>')
    return ('<ul class="detail-condition-records">' + ''.join(records) + '</ul>'
            if records else '<p class="no-data">条件別実績は未取得</p>')


def _material_html(item):
    if isinstance(item, (list, tuple)):
        return '<ul>' + ''.join('<li>' + value(_unmarked(entry)) + '</li>'
                               for entry in item) + '</ul>' if item else '<p>未取得</p>'
    return '<p>' + value(_unmarked(item)) + '</p>'


def detail_html(horse):
    """Render the one shared detail body for pickup and all-runner navigation."""
    facts = _facts(horse)
    metrics = _metrics(horse, facts)
    basic = [
        ("性齢", horse.get("age")),
        ("今回騎手", facts.get("current_jockey")),
        ("前走騎手", facts.get("previous_jockey")),
        ("騎手継続・変更", facts.get("jockey_change")),
        ("現在の斤量", facts.get("weight_label")),
        ("前走比", facts.get("weight_delta_label")),
        ("前走間隔", facts.get("rest_label")),
        ("想定脚質", _unmarked(metrics.get("style", horse.get("style")))),
    ]
    if horse.get("mode") == "jra":
        basic.append(("調教評価", facts.get("training")))
    stats = [
        _stat("A正式評価スコア", index_html(dict(value=formal_score(horse), rank=horse.get("rank")))),
        _stat("純能力指数", index_html(_ability(horse, metrics))),
        _stat("距離指数", index_html(_mapping(metrics.get("distance")) or _mapping(horse.get("distance")))),
        _stat("コース指数", index_html(_mapping(metrics.get("course")) or _mapping(horse.get("course")))),
        _stat("3走平均指数", '<b>' + value(metrics.get("average")) + '</b>'),
        _stat("★最高指数", '<b>' + value(metrics.get("maximum")) + '</b>'),
        _stat("4角想定", '<b>' + _corner(horse, metrics) + '</b>'),
    ]
    changes = ''.join('<li>' + value(_unmarked(item)) + '</li>'
                      for item in _items(facts.get("changes")))
    states = [("前走間隔", facts.get("rest_label")),
              ("斤量の前走比", facts.get("weight_delta_label")),
              ("騎手", facts.get("jockey_change"))]
    if horse.get("mode") == "jra":
        states.append(("調教評価", facts.get("training")))
    raw = facts.get("stable_comment_raw")
    source = facts.get("stable_comment_source")
    original = plain(raw) if isinstance(raw, str) and raw.strip() else '未取得'
    return (
        '<section class="explorer-detail"><header class="detail-header">' + number_badge(horse) +
        '<div><h3>' + value(horse.get("name")) + '</h3><p>馬別詳細</p></div></header>' +
        _definition_list(basic, "detail-basic") +
        '<section class="detail-evaluation"><h4>評価・指数</h4><div class="detail-stats">' +
        ''.join(stats) + '</div>' +
        ('<p class="detail-note">3走平均は確認できた過去3走のタイム指数から算出した表示値です。</p>'
         if metrics.get("average_calculated") else '') + '</section>' +
        '<section class="detail-history"><h4>過去3走</h4>' + _runs_html(facts) + '</section>' +
        '<section class="detail-conditions"><h4>コース・距離実績</h4>' +
        _conditions_html(facts) + '</section>' +
        '<section class="detail-changes"><h4>状態・変更情報</h4>' +
        _definition_list(states, "detail-state-facts") +
        ('<ul>' + changes + '</ul>' if changes else '') + '</section>' +
        '<section class="detail-source-comment"><h4>厩舎コメント原文</h4>' +
        ('<p class="detail-comment-source">出典：' + value(source) + '</p>' if source else '') +
        '<p class="detail-comment-original">' + original + '</p></section>' +
        '<section class="detail-interpretation"><h4>AIによる解釈・考察</h4>' +
        _material_html(facts.get("interpretation")) + '</section>' +
        '<div class="detail-materials"><section class="detail-plus"><h4>プラス材料</h4>' +
        _material_html(facts.get("plus", metrics.get("plus"))) + '</section>' +
        '<section class="detail-caution"><h4>注意材料</h4>' +
        _material_html(facts.get("caution", metrics.get("caution"))) + '</section></div>' +
        '<p class="detail-note">材料は比較のための情報です。正式スコア・順位や候補選定には反映しません。</p>'
        '</section>')
