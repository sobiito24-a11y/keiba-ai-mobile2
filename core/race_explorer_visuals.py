"""Read-only race position and raw ability views for the purchase workspace.

These renderers consume the existing A projection. They neither infer a new
pace nor calculate a score, rank, reference candidate or win probability.
"""
from collections.abc import Mapping
from math import isfinite
import unicodedata

from .final_candidate_selection import select_indices
from .race_explorer_common import number_badge, plain, value


_BANDS = ('逃げ・先団', '好位', '中団', '後方', '位置未取得')
_STYLES = (
    ('逃', '逃げ候補'), ('先', '先行候補'),
    ('差', '差し候補'), ('追', '追込候補'), ('', '脚質未取得'),
)
_PACE_KEYS = ('pace', 'netkeiba_pace', '_netkeiba_pace',
              'provider_pace_market', 'pace_scenario_market',
              'predicted_pace', '想定ペース')
_MISSING = ('', '—', '―', '－', '-', '未取得', '不明', 'None', 'nan', '<NA>')


def _mapping(item):
    return item if isinstance(item, Mapping) else {}


def _number(raw):
    if isinstance(raw, bool):
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _rank(raw):
    result = _number(raw)
    return int(result) if result is not None and result >= 1 and result.is_integer() else None


def _rows(view):
    return [horse for horse in (view or ()) if isinstance(horse, Mapping)]


def _horse_button(horse, *, include_name=True):
    name = plain(horse.get('name')) or '馬名未取得'
    content = number_badge(horse)
    if include_name:
        content += '<span class="horse-open-name">' + name + '</span>'
    return ('<button type="button" class="horse-open" data-horse-open="'
            + plain(horse.get('no')) + '" aria-label="'
            + name + 'の詳細を開く">' + content + '</button>')


def _corner(horse, count):
    corner = _rank(horse.get('corner'))
    return corner if corner is not None and corner <= count else None


def _band(horse, count):
    corner = _corner(horse, count)
    return ((corner - 1) * 4) // count if corner is not None and count else 4


def _style(horse):
    raw = str(horse.get('style') or '').strip()
    return {'逃': '逃', '逃げ': '逃', '先': '先', '先行': '先',
            '差': '差', '差し': '差', '追': '追', '追込': '追',
            '追い込み': '追', '追込み': '追'}.get(raw, '')


def _pace(view, race_info):
    """Require agreement across recorded pace fields; never use style counts."""
    sources = [_mapping(race_info)]
    for horse in view:
        audit = _mapping(_mapping(horse.get('candidate_evidence')).get('audit'))
        sources.extend((horse, _mapping(horse.get('profile')), audit))
    recorded = set()
    for source in sources:
        for key in _PACE_KEYS:
            if key not in source:
                continue
            raw = source[key]
            if isinstance(raw, Mapping):
                if str(raw.get('status', '')).lower() in ('conflict', 'inconsistent', 'unknown'):
                    return ''
                raw = raw.get('value', raw.get('pace'))
            if raw is None or str(raw).strip() in _MISSING:
                continue
            label = unicodedata.normalize('NFKC', str(raw)).strip().upper().replace(' ', '')
            aliases = {
                'H': ('H', 'HIGH', 'ハイ', 'ハイペース', 'H(ハイ)', 'H(ハイペース)', 'ハイペース(H)'),
                'M': ('M', 'MIDDLE', 'ミドル', 'ミドルペース', '平均', '平均ペース', 'M(ミドル)', 'M(ミドルペース)', 'ミドルペース(M)'),
                'S': ('S', 'SLOW', 'スロー', 'スローペース', 'S(スロー)', 'S(スローペース)', 'スローペース(S)'),
            }
            normalized = next((pace for pace, labels in aliases.items() if label in labels), '')
            if not normalized:
                return ''
            recorded.add(normalized)
    return next(iter(recorded)) if len(recorded) == 1 else ''


def _corner_text(horse, count):
    raw = horse.get('corner')
    number = _number(raw)
    if number is None:
        return '4角 未取得'
    label = '4角 ' + value(number) + '番手'
    return label + ('（範囲外・位置未判定）' if _corner(horse, count) is None else '')


def development_html(view, race_info=None):
    """Show all existing corner estimates and styles, with conditional notes."""
    horses = _rows(view)
    count = len(horses)
    pace = _pace(horses, race_info)
    pace_label = {'H': 'H（ハイペース）', 'M': 'M（ミドルペース）',
                  'S': 'S（スローペース）'}.get(pace, '未取得・不一致')
    body = ('<section class="development-panel" aria-labelledby="development-title">'
            '<h2 id="development-title">レース展開予測</h2>'
            '<p class="development-pace">既存の想定ペース <strong>' + pace_label + '</strong></p>'
            '<p class="help">保存済みの4角想定を出走頭数に応じた4つの位置帯で表示。脚質は別に確認できます。</p>')
    if not horses:
        return body + '<p class="empty">出走馬の情報は未取得です。</p></section>'

    bands = [[] for _ in _BANDS]
    for horse in horses:
        bands[_band(horse, count)].append(horse)
    body += '<div class="development-lanes">'
    for index, (label, members) in enumerate(zip(_BANDS, bands)):
        if index == 4 and not members:
            continue
        body += ('<section class="development-lane' + (' development-lane-unknown' if index == 4 else '')
                 + '" data-position-band="' + str(index) + '"><h3>' + label + '</h3>')
        for horse in sorted(members, key=lambda h: (_corner(h, count) or count + 1)):
            style = _style(horse)
            body += ('<div class="development-horse">' + _horse_button(horse)
                     + '<small>' + _corner_text(horse, count) + ' · 脚質 '
                     + (plain(horse.get('style')) if style else '未取得') + '</small></div>')
        if not members:
            body += '<p class="empty">該当馬なし</p>'
        body += '</section>'
    body += '</div><div class="development-styles">'
    for style, label in _STYLES:
        members = [horse for horse in horses if _style(horse) == style]
        if not members and not style:
            continue
        body += '<div><h3>' + label + ' <small>' + str(len(members)) + '頭</small></h3>'
        body += ''.join(_horse_button(horse, include_name=False) for horse in members) or '<span class="empty">該当馬なし</span>'
        body += '</div>'
    body += '</div><div class="development-notes"><h3>展開上の注意点</h3>'
    escapes = [horse for horse in horses if _style(horse) == '逃']
    unknown_styles = sum(not _style(horse) for horse in horses)
    body += '<p>保存脚質で確認できる逃げ候補は' + str(len(escapes)) + '頭'
    if escapes:
        body += '（' + '、'.join(_horse_button(horse) for horse in escapes) + '）'
    body += 'です。'
    if len(escapes) >= 2:
        body += '逃げ候補が複数のため、先行争いと序盤の位置取りに注意してください。'
    if unknown_styles:
        body += '脚質未取得の' + str(unknown_styles) + '頭があり、先行勢の構成には未確認の部分があります。'
    body += '</p><p>' + {
        'H': '保存想定はハイペース。速い流れになれば、先団の消耗と差し・追込馬の進路に注目してください。',
        'M': '保存想定はミドルペース。先行勢と中団以降の位置取りの差を確認してください。',
        'S': '保存想定はスローペース。遅い流れになれば、前方の位置取りと後方馬の仕掛けのタイミングに注目してください。',
    }.get(pace, '想定ペースが未取得または不一致のため、前残り・差し有利の判断は保留しています。') + '</p>'
    pickup = [horses[index] for index in select_indices(horses)]
    if pickup:
        body += '<p class="development-pickup"><b>レースピックアップの想定位置</b>：'
        body += ' ／ '.join(_horse_button(horse) + ' ' + _BANDS[_band(horse, count)]
                           + '（' + _corner_text(horse, count) + '）' for horse in pickup)
        body += '</p>'
    return body + '<p class="help">配置・考察は比較の参考情報です。正式スコアへの追加加点はありません。</p></div></section>'


def ability_html(view):
    """Render every raw ability on one linear scale that always includes zero."""
    horses = _rows(view)
    numeric = [_number(horse.get('ability')) for horse in horses]
    known = [number for number in numeric if number is not None]
    lower, upper = min([0.0, *known]), max([0.0, *known])
    if lower == upper:
        upper = 1.0
    # Normalize before subtraction to avoid overflow for finite +/-1e308 data.
    extent = max(abs(lower), abs(upper))
    low, high = lower / extent, upper / extent

    def percent(number):
        return max(0.0, min(100.0, ((number / extent - low) / (high - low)) * 100.0))

    zero = percent(0.0)
    body = ('<section class="ability-panel" aria-labelledby="ability-title">'
            '<h2 id="ability-title">純能力の見える化</h2>'
            '<p class="help">全頭の保存済み純能力指数を高い順に比較。指数は勝率ではありません。数値と順位は既存の表示値です。</p>')
    if not horses:
        return body + '<p class="empty">出走馬の情報は未取得です。</p></section>'
    body += '<div class="ability-chart" role="list" aria-label="全頭の純能力指数・高い順">'
    if known:
        body += ('<div class="ability-row ability-axis" aria-hidden="true"><span class="ability-label">共通の指数尺度</span>'
                 '<div class="ability-track"><span class="ability-tick ability-tick-start">' + value(lower) + '</span>'
                 '<span class="ability-tick ability-tick-end">' + value(upper) + '</span>')
        if 0 < zero < 100:
            body += '<span class="ability-tick ability-tick-zero" style="left:' + f'{zero:.6f}' + '%">0</span>'
        body += '</div><span class="ability-value">指数 / 保存順位</span></div>'
    else:
        body += '<p class="empty">全頭の純能力指数が未取得のため、棒グラフは表示できません。</p>'

    indices = sorted(range(len(horses)), key=lambda i: (numeric[i] is None, -numeric[i] if numeric[i] is not None else 0, i))
    for index in indices:
        horse, number = horses[index], numeric[index]
        rank = _rank(horse.get('ability_rank'))
        body += ('<div class="ability-row" role="listitem" data-horse-no="' + plain(horse.get('no'))
                 + '"><div class="ability-label">' + _horse_button(horse) + '</div>')
        body += '<div class="ability-track" aria-hidden="true">'
        if known:
            body += '<span class="ability-zero" style="left:' + f'{zero:.6f}' + '%"></span>'
        if number is not None:
            end = percent(number)
            body += ('<span class="ability-bar' + (' ability-bar-negative' if number < 0 else '')
                     + '" style="left:' + f'{min(zero, end):.6f}' + '%;width:'
                     + f'{abs(end - zero):.6f}' + '%"></span>')
        else:
            body += '<span class="ability-missing">未取得</span>'
        body += '</div><div class="ability-value"><strong>' + value(number) + '</strong><small>'
        body += (str(rank) + '位' if rank is not None else '順位 未取得') + '</small></div></div>'
    return body + '</div><p class="help">棒の起点は全頭共通の0です。マイナス値は0から左側に表示します。</p></section>'
