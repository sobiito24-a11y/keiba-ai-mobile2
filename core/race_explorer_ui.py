"""Normal A comparison workspace: typed table cells and browser-only controls."""
import json

from .prediction_table_ui import number
from .final_candidate_selection import formal_score
from .race_explorer_common import number_badge, plain, value
from .race_explorer_cards import detail_html, pickup_html
from .race_explorer_columns import columns, records
from .race_explorer_visuals import ability_html, development_html


def _cell(horse, cells, key):
    item = cells.get(key)
    if key == 'user':
        return '<label class="user-check-target"><input type="checkbox" class="user-horse-check" data-user-check="'+plain(horse.get('no'))+'" aria-label="自分のチェック '+plain(horse.get('no'))+' '+plain(horse.get('name'))+'"></label>'
    if key == 'no':
        return number_badge(horse)
    if key == 'name':
        no = plain(horse.get('no'))
        return '<button type="button" class="horse-select" data-horse-open="'+no+'" aria-expanded="false" aria-controls="horse-detail-'+no+'"><strong>'+value(item)+'</strong></button>'
    if key in ('run_old','run_middle','run_latest'):
        star = ' <span class="maximum-match" title="保存された最高指数と一致">★</span>' if cells.get(key+'_is_maximum') else ''
        return '<b class="metric-number">'+value(item)+star+'</b><small class="run-condition">'+value(cells.get(key+'_condition'))+'</small><small>'+value(cells.get(key+'_date'))+'</small>'
    if key == 'odds':
        return '<b class="metric-number">'+value(item)+'倍</b>' if item is not None else '<span class="missing-cell">'+('取消・除外' if cells.get('withdrawn') is True else '未取得')+'</span>'
    if key == 'popularity':
        return value(item)+'番人気' if item is not None else '<span class="missing-cell">未取得</span>'
    if key == 'rest_days':
        return value(cells.get('rest_label'))+('<small>'+value(item)+'日</small>' if item is not None else '')
    if key == 'weight':
        return value(item)+'kg' if item is not None else '<span class="missing-cell">未取得</span>'
    if key == 'weight_delta':
        return value(cells.get('weight_delta_label'))
    if key.startswith('record_') or key == 'materials':
        return '<span class="comparison-snippet">'+value(item)+'</span>'
    if item is None:
        return '<span class="missing-cell">未取得</span>'
    if isinstance(item, (int, float)):
        return '<b class="metric-number">'+value(item)+'</b>'
    return value(item)


def _options(schema, first=None):
    ordered = ([spec for spec in schema if spec['key'] == first] + [spec for spec in schema if spec['key'] != first]) if first else schema
    return ''.join('<option value="'+plain(spec['key'])+'">'+plain(spec['label'])+'</option>' for spec in ordered)


def lineup_html(view):
    schema, cells = columns(view), records(view)
    widths = dict(user=42, frame=36, no=44, name=190, age=56, jockey=85, score=120,
                  rank=70, popularity=70, style=70, corner=70, training=60,
                  run_old=134, run_middle=134, run_latest=134, jockey_change=160,
                  record_venue=190, record_distance=190, record_venue_distance=190, materials=220)
    table_width = sum(widths.get(spec['key'], 88) for spec in schema)
    headers = []
    for spec in schema:
        key, label = spec['key'], spec['label']
        cls = 'col-'+key+(' col-number' if key == 'no' else '')
        headers.append('<th scope="col" class="'+cls+'" data-column="'+key+'" aria-sort="none"><button type="button" class="column-sort" data-column-sort="'+key+'" aria-label="'+plain(label)+'で並び替え"><span class="column-label">'+plain(label)+'</span></button><button type="button" class="column-filter" data-column-filter="'+key+'" aria-label="'+plain(label)+'で絞り込む" title="'+plain(label)+'で絞り込む"></button></th>')
    rows = []
    for horse in sorted(view, key=lambda h: (number(h.get('no')) is None, number(h.get('no')) or 0)):
        no = str(horse.get('no', ''))
        row = cells[no]
        content = []
        for spec in schema:
            key = spec['key']
            cls = 'col-'+key+(' col-number' if key == 'no' else '')
            tooltip = str(row.get(key) if row.get(key) is not None else '未取得')
            content.append('<td class="'+cls+'" data-label="'+plain(spec['label'])+'" title="'+plain(tooltip)+'">'+_cell(horse, row, key)+'</td>')
        rows.append('<tr data-row="'+plain(no)+'" data-horse="'+plain(no)+'">'+''.join(content)+'</tr>')
    return ('<section class="lineup-workspace" id="lineup-workspace"><div class="explorer-section-heading"><div><span class="eyebrow">COMPARE ALL RUNNERS</span><h2>全頭予想・比較一覧</h2></div><span class="count">全'+str(len(view))+'頭</span></div>'
            '<p class="help">自分の✓は何頭でも選べます。予測・保存・買い目には反映しません。列見出しで並び替え、馬名から詳細を開けます。</p>'
            '<div class="lineup-toolbar"><label>表示 <select id="lineup-filter"><option value="all">全頭表示</option><option value="selected">自分の✓だけ表示</option></select></label>'
            '<label>並び順 <select id="lineup-sort">'+_options(schema, 'no')+'</select></label>'
            '<label>方向 <select id="lineup-direction"><option value="asc">昇順</option><option value="desc">降順</option></select></label>'
            '<button type="button" id="clear-user-selection">選択クリア</button><span id="selection-count" role="status" aria-live="polite">自分の✓ 0頭</span></div>'
            '<details class="column-filters" id="lineup-filters" data-persist-panel><summary>列で絞り込む <span id="filter-count">条件なし</span></summary><div class="column-filter-editor">'
            '<label>対象列 <select id="filter-column">'+_options(schema)+'</select></label>'
            '<label>取得状況 <select id="filter-presence"><option value="all">すべて</option><option value="known">取得済み</option><option value="missing">未取得のみ</option></select></label>'
            '<div id="filter-number-fields"><label>下限 <input id="filter-min" type="number" step="any" inputmode="decimal"></label><label>上限 <input id="filter-max" type="number" step="any" inputmode="decimal"></label></div>'
            '<label id="filter-text-fields">含む文字・開催条件 <input id="filter-text" type="search"></label>'
            '<label id="filter-choice-field">値 <select id="filter-choice"></select></label>'
            '<button type="button" id="add-column-filter">この条件を適用</button><button type="button" id="clear-column-filters">絞り込み全解除</button></div><p id="column-filter-error" role="status" aria-live="polite"></p>'
            '<p class="help">複数の列を組み合わせられます。間隔は日数、過去走は指数範囲と開催条件で指定できます。未取得は並び順にかかわらず末尾です。</p></details>'
            '<div id="active-column-filters" aria-label="適用中の絞り込み"></div>'
            '<p id="lineup-empty" class="no-data" hidden>条件に合う馬がいません。絞り込みを解除するか、全頭表示に切り替えてください。</p>'
            '<div class="table-scroll explorer-table-scroll" tabindex="0" aria-label="全頭比較・縦横スクロール"><table class="explorer-table" style="--comparison-width:'+str(table_width)+'px;--comparison-mobile-width:'+str(table_width-80)+'px"><thead><tr>'+''.join(headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
            '<p class="help">項目は横へ、全頭は縦へスクロールできます。過去走は3走前 → 2走前 → 前走。★は保存された最高指数との一致です。</p></section>')


def _accordion(panel_id, title, description, body):
    return '<details class="overview-accordion" id="'+panel_id+'" data-persist-panel><summary><span class="overview-title">'+title+'</span><span class="overview-description">'+description+'</span></summary><div class="overview-body">'+body+'</div></details>'


def document(view, race_key='', paper_decision=None, portable=None):
    from .game_race_ui import ASSETS, comparison_data, comparison_html, nar_watch_html, paper_html, odds_status
    context = view[0].get('race_context', {}) if view else {}
    schema, cells = columns(view), records(view)
    horses = []
    for horse in view:
        sort = dict(horse.get('sort_values') or {})
        sort['score'] = sort['final_score'] = formal_score(horse)
        horses.append(dict(no=horse['no'], rank=number(horse.get('rank')), sort=sort, values=cells[str(horse['no'])]))
    payload = dict(experience='race-comparison', active_model='A', race_key=race_key, columns=schema, horses=horses,
                   names=[str(h['no'])+' '+str(h['name']) for h in view], cards=[detail_html(h) for h in view],
                   tabs=comparison_data(view, view[0].get('mode', 'jra') if view else 'jra', race_key, portable))
    data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    css = ''.join((ASSETS/name).read_text(encoding='utf-8') for name in ('race.css', 'race_cards.css', 'race_comparison.css'))
    script = '\n'.join((ASSETS/name).read_text(encoding='utf-8') for name in ('race_comparison.js', 'race.js'))
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+css+'</style><body class="race-explorer"><main>'
            +_accordion('race-pickup', 'レースピックアップ', '既存候補の状態・特徴を必要なときに確認できます。', pickup_html(view))
            +_accordion('race-development', 'レース展開予想', '保存されたペース・脚質・4角想定を確認できます。', development_html(view, context).replace('レース展開予測', 'レース展開予想'))
            +_accordion('race-ability', '純能力の見える化', '全出走馬の指数を共通の尺度で比較できます。', ability_html(view))
            +odds_status(view)+lineup_html(view)
            +'<details class="detail-analysis" id="detail-analysis" data-persist-panel><summary>詳細分析・研究機能 <span>既存の12項目</span></summary>'+comparison_html(view, view[0].get('mode', 'jra') if view else 'jra')+'</details>'
            +'<details class="advanced-research" id="saved-research" data-persist-panel><summary>買い目・保存済み研究情報</summary>'+nar_watch_html(view, portable)+paper_html(view, race_key, paper_decision)+'</details>'
            +'<section id="selected-section" hidden><div id="selected-card"></div></section><p id="selection-status" class="sr-only" role="status" aria-live="polite"></p>'
            +'<noscript>比較する馬の選択や詳細表示にはJavaScriptを有効にしてください。</noscript></main><script type="application/json" id="race-data">'+data+'</script><script>'+script+'</script></body></html>')
